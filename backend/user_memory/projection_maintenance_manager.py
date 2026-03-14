"""Scheduled consolidation manager for reset-era projection maintenance."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy import text

from shared.config import Config, get_config
from user_memory.projection_maintenance_service import get_projection_maintenance_service

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
class ProjectionMaintenanceSettings:
    """Configuration for scheduled projection consolidation."""

    enabled: bool = False
    run_on_startup: bool = True
    startup_delay_seconds: int = 180
    interval_seconds: int = 21600
    dry_run: bool = False
    limit: Optional[int] = 5000
    advisory_lock_id: int = 73012020
    use_advisory_lock: bool = True

    def with_defaults(self) -> "ProjectionMaintenanceSettings":
        return ProjectionMaintenanceSettings(
            enabled=self.enabled,
            run_on_startup=self.run_on_startup,
            startup_delay_seconds=self.startup_delay_seconds,
            interval_seconds=self.interval_seconds,
            dry_run=self.dry_run,
            limit=self.limit,
            advisory_lock_id=self.advisory_lock_id,
            use_advisory_lock=self.use_advisory_lock,
        )


def load_projection_maintenance_settings(
    config: Optional[Config] = None,
) -> ProjectionMaintenanceSettings:
    """Load settings from ``user_memory.consolidation``."""

    cfg = config or get_config()
    raw = cfg.get("user_memory.consolidation", {}) or {}

    limit_raw = raw.get("limit")
    limit = _cfg_int(limit_raw, 5000, minimum=1, maximum=50000) if limit_raw is not None else 5000
    settings = ProjectionMaintenanceSettings(
        enabled=_cfg_bool(raw.get("enabled"), False),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 180, minimum=0),
        interval_seconds=_cfg_int(raw.get("interval_seconds"), 21600, minimum=60),
        dry_run=_cfg_bool(raw.get("dry_run"), False),
        limit=limit,
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012020),
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
        logger.warning("Failed to release projection lock %s cleanly: %s", lock_id, exc)
    finally:
        session.close()


def run_projection_maintenance_once(
    settings: Optional[ProjectionMaintenanceSettings] = None,
    *,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Run one projection consolidation cycle."""

    cfg = (settings or load_projection_maintenance_settings()).with_defaults()
    started = time.monotonic()
    if not cfg.enabled:
        return {
            "status": "disabled",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "maintenance": None,
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
                "maintenance": None,
            }
        if lock_session is None:
            return {
                "status": "skipped",
                "reason": reason,
                "dry_run": cfg.dry_run,
                "skip_reason": "lock_not_acquired",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "maintenance": None,
            }

    try:
        service = get_projection_maintenance_service()
        result = service.run_maintenance(
            dry_run=cfg.dry_run,
            limit=cfg.limit,
        )
        payload = service.to_dict(result)
        consolidation = payload.get("consolidation") or {}
        total_updates = (
            int(consolidation.get("user_status_updates") or 0)
            + int(consolidation.get("skill_proposal_status_updates") or 0)
            + int(consolidation.get("skill_proposal_duplicate_supersedes") or 0)
            + int(consolidation.get("user_entry_status_updates") or 0)
            + int(consolidation.get("user_duplicate_entry_supersedes") or 0)
        )
        return {
            "status": "ok",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "maintenance": payload,
            "total_updates": total_updates,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class ProjectionMaintenanceManager:
    """Periodic scheduler for projection consolidation."""

    def __init__(self, settings: Optional[ProjectionMaintenanceSettings] = None):
        self.settings = (settings or load_projection_maintenance_settings()).with_defaults()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._run_lock = asyncio.Lock()

    async def start(self) -> bool:
        """Start scheduled maintenance when enabled."""

        if not self.settings.enabled:
            logger.info("Projection maintenance is disabled by config")
            return False
        if self._task and not self._task.done():
            return True

        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "Projection maintenance manager started",
            extra={
                "interval_seconds": self.settings.interval_seconds,
                "dry_run": self.settings.dry_run,
                "limit": self.settings.limit,
            },
        )
        return True

    async def stop(self) -> None:
        """Stop scheduled maintenance."""

        self._shutdown = True
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("Projection maintenance manager stopped")

    async def run_once(self, *, reason: str = "manual") -> Dict[str, Any]:
        """Run one maintenance cycle in a worker thread."""

        async with self._run_lock:
            result = await asyncio.to_thread(
                run_projection_maintenance_once,
                self.settings,
                reason=reason,
            )
            level = (
                logging.INFO
                if result.get("status") in {"ok", "disabled", "skipped"}
                else logging.WARNING
            )
            logger.log(
                level,
                "Projection maintenance cycle finished",
                extra={
                    "status": result.get("status"),
                    "reason": reason,
                    "dry_run": result.get("dry_run"),
                    "total_updates": result.get("total_updates"),
                    "duration_ms": result.get("duration_ms"),
                    "skip_reason": result.get("skip_reason"),
                    "error": result.get("error"),
                },
            )
            return result

    async def _sleep_or_stop(self, seconds: int) -> bool:
        """Return ``True`` if shutdown requested during wait."""

        if seconds <= 0:
            return self._shutdown
        try:
            await asyncio.sleep(seconds)
            return self._shutdown
        except asyncio.CancelledError:
            return True

    async def _run_loop(self) -> None:
        """Background loop for periodic maintenance."""

        if self.settings.startup_delay_seconds > 0:
            should_stop = await self._sleep_or_stop(self.settings.startup_delay_seconds)
            if should_stop:
                return

        if self.settings.run_on_startup and not self._shutdown:
            try:
                await self.run_once(reason="startup")
            except Exception as exc:
                logger.warning("Startup projection maintenance cycle failed: %s", exc)

        while not self._shutdown:
            should_stop = await self._sleep_or_stop(self.settings.interval_seconds)
            if should_stop:
                break
            try:
                await self.run_once(reason="scheduled")
            except Exception as exc:
                logger.warning("Scheduled projection maintenance cycle failed: %s", exc)


_projection_maintenance_manager: Optional[ProjectionMaintenanceManager] = None
_projection_maintenance_manager_lock = threading.Lock()


def get_projection_maintenance_manager() -> ProjectionMaintenanceManager:
    """Return global projection maintenance manager singleton."""

    global _projection_maintenance_manager
    with _projection_maintenance_manager_lock:
        if _projection_maintenance_manager is None:
            _projection_maintenance_manager = ProjectionMaintenanceManager()
        return _projection_maintenance_manager


async def initialize_projection_maintenance_manager() -> Optional[ProjectionMaintenanceManager]:
    """Initialize and start the projection maintenance manager if enabled."""

    manager = get_projection_maintenance_manager()
    started = await manager.start()
    return manager if started else None


async def shutdown_projection_maintenance_manager() -> None:
    """Shutdown the projection maintenance manager singleton."""

    global _projection_maintenance_manager
    with _projection_maintenance_manager_lock:
        manager = _projection_maintenance_manager
        _projection_maintenance_manager = None

    if manager is not None:
        await manager.stop()
