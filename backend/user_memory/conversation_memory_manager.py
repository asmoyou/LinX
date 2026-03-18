"""Scheduled manager for segmented persistent-conversation memory extraction."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional

from sqlalchemy import text

from database.connection import get_connection_pool
from user_memory.conversation_memory_service import (
    ConversationMemoryExtractionSettings,
    ConversationMemoryService,
    load_conversation_memory_extraction_settings,
)

logger = logging.getLogger(__name__)


def _acquire_advisory_lock(lock_id: int):
    """Acquire a PostgreSQL advisory lock; returns a held session or ``None``."""

    session = get_connection_pool().get_raw_session()
    try:
        acquired = bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": int(lock_id)}
            ).scalar()
        )
        if not acquired:
            session.close()
            return None
        return session
    except Exception:
        session.close()
        raise


def _release_advisory_lock(lock_id: int, session) -> None:
    """Release a PostgreSQL advisory lock and close the backing session."""

    try:
        session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": int(lock_id)})
    except Exception as exc:
        logger.warning("Failed to release conversation-memory lock %s cleanly: %s", lock_id, exc)
    finally:
        session.close()


async def run_conversation_memory_scan_once(
    settings: Optional[ConversationMemoryExtractionSettings] = None,
    *,
    reason: str = "scheduled",
    include_all_pending: bool = False,
) -> Dict[str, Any]:
    """Run one scheduled scan cycle for persistent-conversation memory extraction."""

    cfg = (settings or load_conversation_memory_extraction_settings()).with_defaults()
    started = time.monotonic()
    if not cfg.enabled:
        return {
            "status": "disabled",
            "reason": reason,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "processed": 0,
        }

    lock_session = None
    if cfg.use_advisory_lock:
        try:
            lock_session = _acquire_advisory_lock(cfg.advisory_lock_id)
        except Exception as exc:
            return {
                "status": "error",
                "reason": reason,
                "error": f"Advisory lock failed: {exc}",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "processed": 0,
            }
        if lock_session is None:
            return {
                "status": "skipped",
                "reason": reason,
                "skip_reason": "lock_not_acquired",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "processed": 0,
            }

    try:
        service = ConversationMemoryService(settings=cfg)
        processed = await service.scan_idle_conversations(
            limit=cfg.scan_limit,
            reason=reason,
            include_all_pending=include_all_pending,
        )
        return {
            "status": "ok",
            "reason": reason,
            "processed": len(processed),
            "conversation_ids": [str(conversation_id) for conversation_id in processed],
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class ConversationMemoryManager:
    """Periodic scheduler for segmented persistent-conversation memory extraction."""

    def __init__(self, settings: Optional[ConversationMemoryExtractionSettings] = None):
        self.settings = (settings or load_conversation_memory_extraction_settings()).with_defaults()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._run_lock = asyncio.Lock()

    async def start(self) -> bool:
        """Start scheduled extraction when enabled."""

        if not self.settings.enabled:
            logger.info("Conversation memory extraction is disabled by config")
            return False
        if self._task and not self._task.done():
            return True
        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Conversation memory manager started",
            extra={
                "interval_seconds": self.settings.interval_seconds,
                "idle_timeout_minutes": self.settings.idle_timeout_minutes,
                "scan_limit": self.settings.scan_limit,
            },
        )
        return True

    async def stop(self, *, flush_pending: bool = False) -> None:
        """Stop the scheduled manager and optionally flush pending deltas."""

        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        if flush_pending and self.settings.enabled:
            try:
                await self.run_once(reason="shutdown", include_all_pending=True)
            except Exception as exc:
                logger.warning("Conversation memory shutdown flush failed: %s", exc)
        logger.info("Conversation memory manager stopped")

    async def run_once(
        self,
        *,
        reason: str = "manual",
        include_all_pending: bool = False,
    ) -> Dict[str, Any]:
        """Run one scan cycle under an in-process lock."""

        async with self._run_lock:
            result = await run_conversation_memory_scan_once(
                self.settings,
                reason=reason,
                include_all_pending=include_all_pending,
            )
            level = logging.INFO if result.get("status") in {"ok", "disabled", "skipped"} else logging.WARNING
            logger.log(
                level,
                "Conversation memory scan finished",
                extra={
                    "status": result.get("status"),
                    "reason": reason,
                    "processed": result.get("processed"),
                    "duration_ms": result.get("duration_ms"),
                    "skip_reason": result.get("skip_reason"),
                    "error": result.get("error"),
                },
            )
            return result

    async def _sleep_or_stop(self, seconds: int) -> bool:
        if seconds <= 0:
            return self._shutdown
        try:
            await asyncio.sleep(seconds)
            return self._shutdown
        except asyncio.CancelledError:
            return True

    async def _run_loop(self) -> None:
        if self.settings.startup_delay_seconds > 0:
            should_stop = await self._sleep_or_stop(self.settings.startup_delay_seconds)
            if should_stop:
                return
        if self.settings.run_on_startup and not self._shutdown:
            try:
                await self.run_once(reason="startup")
            except Exception as exc:
                logger.warning("Startup conversation memory scan failed: %s", exc)
        while not self._shutdown:
            should_stop = await self._sleep_or_stop(self.settings.interval_seconds)
            if should_stop:
                break
            try:
                await self.run_once(reason="scheduled")
            except Exception as exc:
                logger.warning("Scheduled conversation memory scan failed: %s", exc)


_conversation_memory_manager: Optional[ConversationMemoryManager] = None
_conversation_memory_manager_lock = threading.Lock()


def get_conversation_memory_manager() -> ConversationMemoryManager:
    """Return the global conversation-memory manager singleton."""

    global _conversation_memory_manager
    with _conversation_memory_manager_lock:
        if _conversation_memory_manager is None:
            _conversation_memory_manager = ConversationMemoryManager()
        return _conversation_memory_manager


async def initialize_conversation_memory_manager() -> Optional[ConversationMemoryManager]:
    """Initialize and start the conversation-memory manager if enabled."""

    manager = get_conversation_memory_manager()
    started = await manager.start()
    return manager if started else None


async def shutdown_conversation_memory_manager(*, flush_pending: bool = True) -> None:
    """Shutdown the conversation-memory manager singleton."""

    global _conversation_memory_manager
    with _conversation_memory_manager_lock:
        manager = _conversation_memory_manager
        _conversation_memory_manager = None
    if manager is not None:
        await manager.stop(flush_pending=flush_pending)


__all__ = [
    "ConversationMemoryManager",
    "get_conversation_memory_manager",
    "initialize_conversation_memory_manager",
    "run_conversation_memory_scan_once",
    "shutdown_conversation_memory_manager",
]
