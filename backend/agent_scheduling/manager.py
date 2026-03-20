"""Background manager for planning and executing agent schedule runs."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text

from agent_scheduling.service import (
    claim_queued_schedule_run_ids,
    cleanup_terminal_one_time_schedules,
    execute_schedule_run,
    plan_due_schedule_runs,
)
from database.connection import get_connection_pool
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


def _cfg_int(value: Any, default: int, *, minimum: Optional[int] = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    return parsed


@dataclass(frozen=True)
class AgentScheduleManagerSettings:
    enabled: bool = True
    run_on_startup: bool = True
    startup_delay_seconds: int = 15
    planner_interval_seconds: int = 30
    executor_interval_seconds: int = 10
    planner_batch_limit: int = 50
    executor_batch_limit: int = 5
    cleanup_interval_seconds: int = 3600
    cleanup_batch_limit: int = 100
    terminal_once_retention_days: int = 5
    advisory_lock_id: int = 73042026
    use_advisory_lock: bool = True


def load_agent_schedule_manager_settings(
    config: Optional[Config] = None,
) -> AgentScheduleManagerSettings:
    cfg = config or get_config()
    raw = cfg.get("agent_schedule", {}) or {}
    return AgentScheduleManagerSettings(
        enabled=_cfg_bool(raw.get("enabled"), True),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 15, minimum=0),
        planner_interval_seconds=_cfg_int(raw.get("planner_interval_seconds"), 30, minimum=5),
        executor_interval_seconds=_cfg_int(raw.get("executor_interval_seconds"), 10, minimum=2),
        planner_batch_limit=_cfg_int(raw.get("planner_batch_limit"), 50, minimum=1),
        executor_batch_limit=_cfg_int(raw.get("executor_batch_limit"), 5, minimum=1),
        cleanup_interval_seconds=_cfg_int(raw.get("cleanup_interval_seconds"), 3600, minimum=60),
        cleanup_batch_limit=_cfg_int(raw.get("cleanup_batch_limit"), 100, minimum=1),
        terminal_once_retention_days=_cfg_int(
            raw.get("terminal_once_retention_days"), 5, minimum=1
        ),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73042026, minimum=1),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
    )


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
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to release schedule planner advisory lock %s: %s", lock_id, exc)
    finally:
        session.close()


class AgentScheduleManager:
    def __init__(self, settings: Optional[AgentScheduleManagerSettings] = None) -> None:
        self.settings = settings or load_agent_schedule_manager_settings()
        self._planner_task: Optional[asyncio.Task] = None
        self._executor_task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._last_cleanup_monotonic: Optional[float] = None

    async def start(self) -> bool:
        if not self.settings.enabled:
            logger.info("Agent schedule manager is disabled by config")
            return False
        if self._planner_task and not self._planner_task.done():
            return True

        self._shutdown = False
        self._planner_task = asyncio.create_task(self._planner_loop())
        self._executor_task = asyncio.create_task(self._executor_loop())
        logger.info(
            "Agent schedule manager started",
            extra={
                "planner_interval_seconds": self.settings.planner_interval_seconds,
                "executor_interval_seconds": self.settings.executor_interval_seconds,
                "planner_batch_limit": self.settings.planner_batch_limit,
                "executor_batch_limit": self.settings.executor_batch_limit,
            },
        )
        return True

    async def stop(self) -> None:
        self._shutdown = True
        tasks = [task for task in [self._planner_task, self._executor_task] if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                continue

    async def _planner_loop(self) -> None:
        if self.settings.run_on_startup and self.settings.startup_delay_seconds > 0:
            await asyncio.sleep(self.settings.startup_delay_seconds)
        while not self._shutdown:
            started = time.monotonic()
            try:
                await self._run_planner_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Agent schedule planner cycle failed: %s", exc, exc_info=True)
            elapsed = time.monotonic() - started
            sleep_for = max(self.settings.planner_interval_seconds - elapsed, 1)
            await asyncio.sleep(sleep_for)

    async def _executor_loop(self) -> None:
        if self.settings.run_on_startup and self.settings.startup_delay_seconds > 0:
            await asyncio.sleep(self.settings.startup_delay_seconds)
        while not self._shutdown:
            started = time.monotonic()
            try:
                run_ids = claim_queued_schedule_run_ids(limit=self.settings.executor_batch_limit)
                for run_id in run_ids:
                    await execute_schedule_run(run_id=run_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("Agent schedule executor cycle failed: %s", exc, exc_info=True)
            elapsed = time.monotonic() - started
            sleep_for = max(self.settings.executor_interval_seconds - elapsed, 1)
            await asyncio.sleep(sleep_for)

    async def _run_planner_once(self) -> dict[str, int]:
        lock_session = None
        if self.settings.use_advisory_lock:
            lock_session = _acquire_advisory_lock(self.settings.advisory_lock_id)
            if lock_session is None:
                return {"queued": 0, "skipped": 0, "cleaned": 0}
        try:
            results = plan_due_schedule_runs(limit=self.settings.planner_batch_limit)
            cleaned = 0
            if self._should_run_cleanup():
                cleaned = cleanup_terminal_one_time_schedules(
                    retention_days=self.settings.terminal_once_retention_days,
                    limit=self.settings.cleanup_batch_limit,
                )
                self._last_cleanup_monotonic = time.monotonic()
                if cleaned > 0:
                    logger.info(
                        "Cleaned terminal one-time schedules",
                        extra={"cleaned": cleaned},
                    )
            results["cleaned"] = cleaned
            return results
        finally:
            if lock_session is not None:
                _release_advisory_lock(self.settings.advisory_lock_id, lock_session)

    def _should_run_cleanup(self) -> bool:
        if self.settings.terminal_once_retention_days <= 0:
            return False
        if self._last_cleanup_monotonic is None:
            return True
        return (
            time.monotonic() - self._last_cleanup_monotonic
            >= self.settings.cleanup_interval_seconds
        )


_agent_schedule_manager: Optional[AgentScheduleManager] = None


async def initialize_agent_schedule_manager() -> Optional[AgentScheduleManager]:
    global _agent_schedule_manager
    if _agent_schedule_manager is None:
        _agent_schedule_manager = AgentScheduleManager()
    started = await _agent_schedule_manager.start()
    return _agent_schedule_manager if started else None


async def shutdown_agent_schedule_manager() -> None:
    global _agent_schedule_manager
    if _agent_schedule_manager is None:
        return
    await _agent_schedule_manager.stop()
    _agent_schedule_manager = None


def get_agent_schedule_manager() -> Optional[AgentScheduleManager]:
    return _agent_schedule_manager
