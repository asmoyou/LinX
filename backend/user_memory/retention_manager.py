"""Scheduled retention manager for session-ledger provenance rows."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from user_memory.session_ledger_repository import get_session_ledger_repository
from shared.config import Config, get_config

logger = logging.getLogger(__name__)


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
class SessionLedgerRetentionSettings:
    """Configuration for session-ledger retention cleanup."""

    enabled: bool = False
    retention_days: int = 14
    run_on_startup: bool = True
    startup_delay_seconds: int = 120
    interval_seconds: int = 21600
    batch_size: int = 1000
    dry_run: bool = False
    advisory_lock_id: int = 73012021
    use_advisory_lock: bool = True

    def with_defaults(self) -> "SessionLedgerRetentionSettings":
        return SessionLedgerRetentionSettings(
            enabled=self.enabled,
            retention_days=self.retention_days,
            run_on_startup=self.run_on_startup,
            startup_delay_seconds=self.startup_delay_seconds,
            interval_seconds=self.interval_seconds,
            batch_size=self.batch_size,
            dry_run=self.dry_run,
            advisory_lock_id=self.advisory_lock_id,
            use_advisory_lock=self.use_advisory_lock,
        )


def load_session_ledger_retention_settings(
    config: Optional[Config] = None,
) -> SessionLedgerRetentionSettings:
    """Load settings from ``session_ledger``."""

    cfg = config or get_config()
    raw = cfg.get("session_ledger", {}) or {}
    settings = SessionLedgerRetentionSettings(
        enabled=_cfg_bool(raw.get("enabled"), False),
        retention_days=_cfg_int(raw.get("retention_days"), 14, minimum=1, maximum=3650),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 120, minimum=0),
        interval_seconds=_cfg_int(raw.get("cleanup_interval_seconds"), 21600, minimum=60),
        batch_size=_cfg_int(raw.get("batch_size"), 1000, minimum=1, maximum=50000),
        dry_run=_cfg_bool(raw.get("dry_run"), False),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012021),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
    )
    return settings.with_defaults()


def _acquire_advisory_lock(lock_id: int):
    """Acquire PostgreSQL advisory lock; returns held session or ``None``."""

    from database.connection import get_connection_pool

    session = get_connection_pool().get_raw_session()
    try:
        acquired = bool(
            session.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
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
    """Release PostgreSQL advisory lock and close the lock session."""

    try:
        session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
    except Exception as exc:
        logger.warning(
            "Failed to release session-ledger retention lock %s cleanly: %s", lock_id, exc
        )
    finally:
        session.close()


def run_session_ledger_retention_once(
    settings: Optional[SessionLedgerRetentionSettings] = None,
    *,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Run one session-ledger cleanup cycle."""

    cfg = (settings or load_session_ledger_retention_settings()).with_defaults()
    started = time.monotonic()
    if not cfg.enabled:
        return {
            "status": "disabled",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "cleanup": None,
        }

    lock_session = None
    if cfg.use_advisory_lock:
        try:
            lock_session = _acquire_advisory_lock(cfg.advisory_lock_id)
        except Exception as exc:
            return {
                "status": "error",
                "reason": reason,
                "dry_run": cfg.dry_run,
                "error": f"Advisory lock failed: {exc}",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "cleanup": None,
            }
        if lock_session is None:
            return {
                "status": "skipped",
                "reason": reason,
                "dry_run": cfg.dry_run,
                "skip_reason": "lock_not_acquired",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "cleanup": None,
            }

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=cfg.retention_days)
        cleanup = get_session_ledger_repository().cleanup_sessions_ended_before(
            cutoff=cutoff,
            limit=cfg.batch_size,
            dry_run=cfg.dry_run,
        )
        return {
            "status": "ok",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "retention_days": cfg.retention_days,
            "cutoff": cutoff.isoformat(),
            "cleanup": cleanup,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class SessionLedgerRetentionManager:
    """Periodic scheduler for session-ledger retention cleanup."""

    def __init__(self, settings: Optional[SessionLedgerRetentionSettings] = None):
        self.settings = (settings or load_session_ledger_retention_settings()).with_defaults()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._run_lock = asyncio.Lock()

    async def start(self) -> bool:
        """Start scheduled cleanup when enabled."""

        if not self.settings.enabled:
            logger.info("Session ledger retention is disabled by config")
            return False
        if self._task and not self._task.done():
            return True

        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Session ledger retention manager started",
            extra={
                "retention_days": self.settings.retention_days,
                "interval_seconds": self.settings.interval_seconds,
                "batch_size": self.settings.batch_size,
                "dry_run": self.settings.dry_run,
            },
        )
        return True

    async def stop(self) -> None:
        """Stop scheduled cleanup."""

        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Session ledger retention manager stopped")

    async def run_once(self, *, reason: str = "manual") -> Dict[str, Any]:
        """Run one cleanup cycle in a worker thread."""

        async with self._run_lock:
            result = await asyncio.to_thread(
                run_session_ledger_retention_once,
                self.settings,
                reason=reason,
            )
            level = (
                logging.INFO
                if result.get("status") in {"ok", "disabled", "skipped"}
                else logging.WARNING
            )
            cleanup = result.get("cleanup") or {}
            logger.log(
                level,
                "Session ledger retention cycle finished",
                extra={
                    "status": result.get("status"),
                    "reason": reason,
                    "retention_days": result.get("retention_days"),
                    "dry_run": result.get("dry_run"),
                    "scanned_sessions": cleanup.get("scanned_sessions"),
                    "deleted_sessions": cleanup.get("deleted_sessions"),
                    "detached_materializations": cleanup.get("detached_materializations"),
                    "detached_entries": cleanup.get("detached_entries"),
                    "detached_links": cleanup.get("detached_links"),
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
                logger.warning("Startup session-ledger retention cycle failed: %s", exc)

        while not self._shutdown:
            should_stop = await self._sleep_or_stop(self.settings.interval_seconds)
            if should_stop:
                break
            try:
                await self.run_once(reason="scheduled")
            except Exception as exc:
                logger.warning("Scheduled session-ledger retention cycle failed: %s", exc)


_retention_manager: Optional[SessionLedgerRetentionManager] = None
_retention_manager_lock = threading.Lock()


def get_session_ledger_retention_manager() -> SessionLedgerRetentionManager:
    """Return global session-ledger retention manager singleton."""

    global _retention_manager
    with _retention_manager_lock:
        if _retention_manager is None:
            _retention_manager = SessionLedgerRetentionManager()
        return _retention_manager


async def initialize_session_ledger_retention_manager() -> Optional[SessionLedgerRetentionManager]:
    """Initialize and start session-ledger retention manager if enabled."""

    manager = get_session_ledger_retention_manager()
    started = await manager.start()
    return manager if started else None


async def shutdown_session_ledger_retention_manager() -> None:
    """Shutdown session-ledger retention manager singleton."""

    global _retention_manager
    with _retention_manager_lock:
        manager = _retention_manager
        _retention_manager = None

    if manager is not None:
        await manager.stop()
