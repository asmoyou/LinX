"""Lifecycle manager for persistent conversations."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select, text

from agent_framework.conversation_history_compaction import (
    ConversationHistoryCompactionService,
    load_conversation_history_compaction_settings,
)
from agent_framework.conversation_storage_cleanup import (
    collect_conversation_storage_refs,
    delete_object_references,
)
from agent_framework.persistent_conversations import get_persistent_conversation_runtime_service
from database.connection import get_connection_pool, get_db_session
from database.models import AgentConversation, AgentConversationSnapshot, AgentSchedule
from shared.config import Config, get_config

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _cfg_int(
    value: Any,
    default: int,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


@dataclass(frozen=True)
class ConversationLifecycleSettings:
    enabled: bool = True
    run_on_startup: bool = True
    startup_delay_seconds: int = 30
    interval_seconds: int = 300
    archive_after_days: int = 30
    delete_after_days: int = 90
    scan_limit: int = 200
    dry_run: bool = False
    advisory_lock_id: int = 73012025
    use_advisory_lock: bool = True

    def with_defaults(self) -> "ConversationLifecycleSettings":
        return ConversationLifecycleSettings(
            enabled=self.enabled,
            run_on_startup=self.run_on_startup,
            startup_delay_seconds=self.startup_delay_seconds,
            interval_seconds=self.interval_seconds,
            archive_after_days=self.archive_after_days,
            delete_after_days=self.delete_after_days,
            scan_limit=self.scan_limit,
            dry_run=self.dry_run,
            advisory_lock_id=self.advisory_lock_id,
            use_advisory_lock=self.use_advisory_lock,
        )


def load_conversation_lifecycle_settings(
    config: Optional[Config] = None,
) -> ConversationLifecycleSettings:
    cfg = config or get_config()
    raw = cfg.get("persistent_conversations.lifecycle", {}) or {}
    return ConversationLifecycleSettings(
        enabled=_cfg_bool(raw.get("enabled"), True),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 30, minimum=0),
        interval_seconds=_cfg_int(raw.get("interval_seconds"), 300, minimum=60),
        archive_after_days=_cfg_int(raw.get("archive_after_days"), 30, minimum=1, maximum=3650),
        delete_after_days=_cfg_int(raw.get("delete_after_days"), 90, minimum=2, maximum=3650),
        scan_limit=_cfg_int(raw.get("scan_limit"), 200, minimum=1, maximum=5000),
        dry_run=_cfg_bool(raw.get("dry_run"), False),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012025),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
    ).with_defaults()


def _acquire_advisory_lock(lock_id: int):
    session = get_connection_pool().get_raw_session()
    try:
        acquired = bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": int(lock_id)},
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
    try:
        session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": int(lock_id)})
    except Exception as exc:
        logger.warning("Failed to release conversation lifecycle lock %s cleanly: %s", lock_id, exc)
    finally:
        session.close()


async def run_conversation_lifecycle_once(
    settings: Optional[ConversationLifecycleSettings] = None,
    *,
    reason: str = "manual",
) -> dict[str, Any]:
    cfg = (settings or load_conversation_lifecycle_settings()).with_defaults()
    started = time.monotonic()
    if not cfg.enabled:
        return {
            "status": "disabled",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
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
            }
        if lock_session is None:
            return {
                "status": "skipped",
                "reason": reason,
                "skip_reason": "lock_not_acquired",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            }

    manager = ConversationLifecycleManager(cfg)
    try:
        result = await manager.run_cycle(reason=reason)
        result["duration_ms"] = round((time.monotonic() - started) * 1000, 2)
        return result
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class ConversationLifecycleManager:
    def __init__(self, settings: Optional[ConversationLifecycleSettings] = None) -> None:
        self.settings = (settings or load_conversation_lifecycle_settings()).with_defaults()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._run_lock = asyncio.Lock()
        history_settings = load_conversation_history_compaction_settings()
        self._history_service = ConversationHistoryCompactionService(settings=history_settings)

    async def start(self) -> bool:
        if not self.settings.enabled:
            logger.info("Persistent conversation lifecycle manager is disabled by config")
            return False
        if self._task and not self._task.done():
            return True
        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Persistent conversation lifecycle manager started",
            extra={
                "interval_seconds": self.settings.interval_seconds,
                "archive_after_days": self.settings.archive_after_days,
                "delete_after_days": self.settings.delete_after_days,
                "dry_run": self.settings.dry_run,
            },
        )
        return True

    async def stop(self) -> None:
        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Persistent conversation lifecycle manager stopped")

    async def run_once(self, *, reason: str = "manual") -> dict[str, Any]:
        async with self._run_lock:
            result = await run_conversation_lifecycle_once(self.settings, reason=reason)
            level = (
                logging.INFO
                if result.get("status") in {"ok", "disabled", "skipped"}
                else logging.WARNING
            )
            logger.log(
                level,
                "Persistent conversation lifecycle cycle finished",
                extra=result,
            )
            return result

    async def run_cycle(self, *, reason: str = "manual") -> dict[str, Any]:
        now = _utcnow()
        compaction_ids = self._list_compaction_candidates(limit=self.settings.scan_limit)
        archive_ids = self._list_archive_candidates(now=now, limit=self.settings.scan_limit)
        delete_ids = self._list_delete_candidates(now=now, limit=self.settings.scan_limit)

        compacted = 0
        archived = 0
        deleted = 0

        for conversation_id in compaction_ids:
            result = await self._history_service.compact_conversation(
                conversation_id,
                reason="scheduled",
            )
            if result.get("status") == "ok":
                compacted += 1

        for conversation_id in archive_ids:
            if await self._archive_conversation(conversation_id, now=now):
                archived += 1

        for conversation_id in delete_ids:
            if await self._delete_conversation(conversation_id):
                deleted += 1

        return {
            "status": "ok",
            "reason": reason,
            "dry_run": self.settings.dry_run,
            "compacted": compacted,
            "archived": archived,
            "deleted": deleted,
            "compaction_candidates": len(compaction_ids),
            "archive_candidates": len(archive_ids),
            "delete_candidates": len(delete_ids),
        }

    def _list_compaction_candidates(self, *, limit: int) -> list[UUID]:
        with get_db_session() as session:
            protected_conversations = select(AgentSchedule.bound_conversation_id).where(
                AgentSchedule.status.in_(["active", "paused"])
            )
            rows = (
                session.query(AgentConversation.conversation_id)
                .filter(AgentConversation.status == "active")
                .filter(~AgentConversation.conversation_id.in_(protected_conversations))
                .order_by(AgentConversation.updated_at.asc())
                .limit(limit)
                .all()
            )
        return [row[0] for row in rows]

    def _list_archive_candidates(self, *, now: datetime, limit: int) -> list[UUID]:
        cutoff = now - timedelta(days=self.settings.archive_after_days)
        with get_db_session() as session:
            protected_conversations = select(AgentSchedule.bound_conversation_id).where(
                AgentSchedule.status.in_(["active", "paused"])
            )
            rows = (
                session.query(AgentConversation.conversation_id)
                .filter(AgentConversation.status == "active")
                .filter(AgentConversation.last_message_at.isnot(None))
                .filter(AgentConversation.last_message_at <= cutoff)
                .filter(AgentConversation.storage_tier != "archived")
                .filter(~AgentConversation.conversation_id.in_(protected_conversations))
                .order_by(AgentConversation.last_message_at.asc())
                .limit(limit)
                .all()
            )
        return [row[0] for row in rows]

    def _list_delete_candidates(self, *, now: datetime, limit: int) -> list[UUID]:
        cutoff = now - timedelta(days=self.settings.delete_after_days)
        with get_db_session() as session:
            protected_conversations = select(AgentSchedule.bound_conversation_id).where(
                AgentSchedule.status.in_(["active", "paused"])
            )
            rows = (
                session.query(AgentConversation.conversation_id)
                .filter(AgentConversation.status == "active")
                .filter(
                    (
                        AgentConversation.delete_after.isnot(None)
                        & (AgentConversation.delete_after <= now)
                    )
                    | (
                        AgentConversation.last_message_at.isnot(None)
                        & (AgentConversation.last_message_at <= cutoff)
                    )
                )
                .filter(~AgentConversation.conversation_id.in_(protected_conversations))
                .order_by(AgentConversation.last_message_at.asc())
                .limit(limit)
                .all()
            )
        return [row[0] for row in rows]

    async def _archive_conversation(self, conversation_id: UUID, *, now: datetime) -> bool:
        if self.settings.dry_run:
            return True

        await self._history_service.compact_conversation(
            conversation_id,
            reason="archive",
            recent_turn_window=10,
        )

        snapshot_refs_to_delete: set[str] = set()
        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                return False

            latest_ready_snapshot = (
                session.query(AgentConversationSnapshot)
                .filter(AgentConversationSnapshot.conversation_id == conversation_id)
                .filter(AgentConversationSnapshot.snapshot_status == "ready")
                .order_by(AgentConversationSnapshot.generation.desc())
                .first()
            )
            snapshot_rows = (
                session.query(AgentConversationSnapshot)
                .filter(AgentConversationSnapshot.conversation_id == conversation_id)
                .all()
            )
            keep_snapshot_id = latest_ready_snapshot.snapshot_id if latest_ready_snapshot else None
            for snapshot in snapshot_rows:
                if keep_snapshot_id and snapshot.snapshot_id == keep_snapshot_id:
                    continue
                for ref in (snapshot.archive_ref, snapshot.manifest_ref):
                    if ref:
                        snapshot_refs_to_delete.add(str(ref))
                session.delete(snapshot)

            conversation.storage_tier = "archived"
            conversation.archived_at = conversation.archived_at or now
            base_time = conversation.last_message_at or conversation.updated_at or now
            conversation.delete_after = base_time + timedelta(days=self.settings.delete_after_days)
            conversation.updated_at = now
            if latest_ready_snapshot is not None:
                conversation.latest_snapshot_id = latest_ready_snapshot.snapshot_id
            session.commit()

        delete_object_references(snapshot_refs_to_delete)
        return True

    async def _delete_conversation(self, conversation_id: UUID) -> bool:
        if self.settings.dry_run:
            return True

        runtime = get_persistent_conversation_runtime_service().get_active_runtime(conversation_id)
        if runtime is not None:
            await get_persistent_conversation_runtime_service().release_runtime(
                conversation_id,
                reason="delete",
            )

        refs: dict[str, set[str]] | None = None
        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                return False
            refs = collect_conversation_storage_refs(session, conversation_id)
            session.delete(conversation)
            session.commit()

        combined_refs = set()
        for key in ("snapshot_refs", "archive_refs", "attachment_refs"):
            combined_refs.update(refs.get(key) or set())
        delete_object_references(combined_refs)
        return True

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
                logger.warning("Startup persistent conversation lifecycle cycle failed: %s", exc)

        while not self._shutdown:
            should_stop = await self._sleep_or_stop(self.settings.interval_seconds)
            if should_stop:
                break
            try:
                await self.run_once(reason="scheduled")
            except Exception as exc:
                logger.warning("Scheduled persistent conversation lifecycle cycle failed: %s", exc)


_lifecycle_manager: Optional[ConversationLifecycleManager] = None
_lifecycle_manager_lock = threading.Lock()


def get_conversation_lifecycle_manager() -> ConversationLifecycleManager:
    global _lifecycle_manager
    with _lifecycle_manager_lock:
        if _lifecycle_manager is None:
            _lifecycle_manager = ConversationLifecycleManager()
        return _lifecycle_manager


async def initialize_conversation_lifecycle_manager() -> Optional[ConversationLifecycleManager]:
    manager = get_conversation_lifecycle_manager()
    started = await manager.start()
    return manager if started else None


async def shutdown_conversation_lifecycle_manager() -> None:
    global _lifecycle_manager
    with _lifecycle_manager_lock:
        manager = _lifecycle_manager
        _lifecycle_manager = None
    if manager is not None:
        await manager.stop()


__all__ = [
    "ConversationLifecycleManager",
    "ConversationLifecycleSettings",
    "get_conversation_lifecycle_manager",
    "initialize_conversation_lifecycle_manager",
    "load_conversation_lifecycle_settings",
    "run_conversation_lifecycle_once",
    "shutdown_conversation_lifecycle_manager",
]
