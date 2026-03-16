"""Cleanup helpers for reset-era user-memory rows and legacy Milvus vectors."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from sqlalchemy import text

from database.connection import get_db_session
from database.models import (
    SessionLedger,
    SessionLedgerEvent,
    SkillProposal,
    UserMemoryEntry,
    UserMemoryLink,
    UserMemoryView,
)
from shared.config import Config, get_config
from user_memory.vector_collection import USER_MEMORY_ENTRIES_COLLECTION

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


def _chunked(values: Sequence[str], batch_size: int) -> Iterable[List[str]]:
    size = max(int(batch_size), 1)
    for idx in range(0, len(values), size):
        yield list(values[idx : idx + size])


def _quote_milvus_string(value: str) -> str:
    return '"' + str(value or "").replace("\\", "\\\\").replace('"', '\\"') + '"'


@dataclass(frozen=True)
class UserMemoryVectorCleanupSettings:
    """Configuration for scheduled orphan-vector cleanup."""

    enabled: bool = True
    run_on_startup: bool = True
    startup_delay_seconds: int = 360
    interval_seconds: int = 21600
    dry_run: bool = False
    batch_size: int = 500
    compact_on_cycle: bool = True
    advisory_lock_id: int = 73012023
    use_advisory_lock: bool = True

    def with_defaults(self) -> "UserMemoryVectorCleanupSettings":
        return UserMemoryVectorCleanupSettings(
            enabled=self.enabled,
            run_on_startup=self.run_on_startup,
            startup_delay_seconds=self.startup_delay_seconds,
            interval_seconds=self.interval_seconds,
            dry_run=self.dry_run,
            batch_size=self.batch_size,
            compact_on_cycle=self.compact_on_cycle,
            advisory_lock_id=self.advisory_lock_id,
            use_advisory_lock=self.use_advisory_lock,
        )


def load_user_memory_vector_cleanup_settings(
    config: Optional[Config] = None,
) -> UserMemoryVectorCleanupSettings:
    """Load settings from ``user_memory.vector_cleanup``."""

    cfg = config or get_config()
    raw = cfg.get("user_memory.vector_cleanup", {}) or {}
    settings = UserMemoryVectorCleanupSettings(
        enabled=_cfg_bool(raw.get("enabled"), True),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 360, minimum=0),
        interval_seconds=_cfg_int(raw.get("interval_seconds"), 21600, minimum=60),
        dry_run=_cfg_bool(raw.get("dry_run"), False),
        batch_size=_cfg_int(raw.get("batch_size"), 500, minimum=1, maximum=5000),
        compact_on_cycle=_cfg_bool(raw.get("compact_on_cycle"), True),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012023),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
    )
    return settings.with_defaults()


def delete_user_memory_entry_vectors(
    entry_ids: Iterable[Any],
    *,
    milvus_conn: Optional[Any] = None,
    dry_run: bool = False,
    batch_size: int = 500,
    force_refresh: bool = True,
) -> Dict[str, Any]:
    """Delete one or more legacy user-memory vectors by ``entry_id``."""

    normalized_entry_ids = sorted(
        {str(entry_id).strip() for entry_id in entry_ids if str(entry_id).strip()}
    )
    if not normalized_entry_ids:
        return {
            "attempted": False,
            "requested_entry_ids": 0,
            "deleted_entry_ids": 0,
            "errors": [],
        }

    connection = milvus_conn
    if connection is None:
        from memory_system.milvus_connection import get_milvus_connection

        connection = get_milvus_connection()

    if not connection.collection_exists(USER_MEMORY_ENTRIES_COLLECTION):
        return {
            "attempted": False,
            "requested_entry_ids": len(normalized_entry_ids),
            "deleted_entry_ids": 0,
            "errors": [],
        }

    collection = connection.get_collection(
        USER_MEMORY_ENTRIES_COLLECTION,
        force_refresh=force_refresh,
    )
    deleted_entry_ids = 0
    errors: List[str] = []
    for batch in _chunked(normalized_entry_ids, batch_size):
        expr = (
            "entry_id in [" + ", ".join(_quote_milvus_string(entry_id) for entry_id in batch) + "]"
        )
        try:
            if not dry_run:
                collection.delete(expr)
            deleted_entry_ids += len(batch)
        except Exception as exc:
            logger.warning(
                "Failed to delete user-memory vectors",
                extra={"entry_ids": batch, "error": str(exc)},
            )
            errors.append(str(exc))

    return {
        "attempted": True,
        "requested_entry_ids": len(normalized_entry_ids),
        "deleted_entry_ids": deleted_entry_ids,
        "errors": errors,
    }


def trigger_user_memory_collection_compaction(
    *,
    milvus_conn: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Trigger Milvus compaction for the legacy user-memory collection."""

    connection = milvus_conn
    if connection is None:
        from memory_system.milvus_connection import get_milvus_connection

        connection = get_milvus_connection()

    if not connection.collection_exists(USER_MEMORY_ENTRIES_COLLECTION):
        return {"attempted": False, "triggered": False, "error": None}

    try:
        collection = connection.get_collection(
            USER_MEMORY_ENTRIES_COLLECTION,
            force_refresh=False,
        )
        if not dry_run:
            collection.compact()
        return {"attempted": True, "triggered": True, "error": None}
    except Exception as exc:
        logger.warning(
            "Failed to trigger user-memory Milvus compaction",
            extra={"error": str(exc)},
        )
        return {"attempted": True, "triggered": False, "error": str(exc)}


def _load_live_user_memory_entry_ids() -> Set[str]:
    live_ids: Set[str] = set()
    with get_db_session() as session:
        query = session.query(UserMemoryEntry.id).yield_per(1000)
        for row in query:
            entry_id = row[0] if isinstance(row, tuple) else getattr(row, "id", row)
            if entry_id is not None:
                live_ids.add(str(entry_id))
    return live_ids


def cleanup_orphaned_user_memory_vectors(
    *,
    live_entry_ids: Set[str],
    batch_size: int,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Delete Milvus rows whose ``entry_id`` no longer exists in PostgreSQL."""

    from memory_system.milvus_connection import get_milvus_connection

    connection = get_milvus_connection()
    if not connection.collection_exists(USER_MEMORY_ENTRIES_COLLECTION):
        return {
            "scanned_rows": 0,
            "orphaned_entry_ids": 0,
            "deleted_entry_ids": 0,
            "errors": [],
        }

    collection = connection.get_collection(USER_MEMORY_ENTRIES_COLLECTION, force_refresh=True)
    iterator = collection.query_iterator(
        batch_size=max(int(batch_size), 1),
        expr=None,
        output_fields=["entry_id"],
    )

    scanned_rows = 0
    orphaned_ids: Set[str] = set()
    try:
        while True:
            rows = iterator.next()
            if not rows:
                break
            scanned_rows += len(rows)
            for row in rows:
                entry_id = str((row or {}).get("entry_id") or "").strip()
                if entry_id and entry_id not in live_entry_ids:
                    orphaned_ids.add(entry_id)
    finally:
        iterator.close()

    delete_result = delete_user_memory_entry_vectors(
        sorted(orphaned_ids),
        milvus_conn=connection,
        dry_run=dry_run,
        batch_size=batch_size,
        force_refresh=False,
    )
    return {
        "scanned_rows": scanned_rows,
        "orphaned_entry_ids": len(orphaned_ids),
        "deleted_entry_ids": int(delete_result.get("deleted_entry_ids") or 0),
        "errors": list(delete_result.get("errors") or []),
    }


def prepare_user_memory_rows_for_user_deletion(
    session: Any,
    *,
    user_id: str,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Delete reset-era user-memory rows for one user inside an existing DB transaction."""

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return {
            "user_id": normalized_user_id,
            "entry_ids": [],
            "session_ids": [],
            "session_ledgers": 0,
            "session_events": 0,
            "memory_entries": 0,
            "memory_links": 0,
            "memory_views": 0,
            "skill_proposals": 0,
            "deleted": False,
        }

    entry_ids = [
        str(row[0])
        for row in session.query(UserMemoryEntry.id)
        .filter(UserMemoryEntry.user_id == normalized_user_id)
        .all()
        if row[0] is not None
    ]
    session_ids = [
        int(row[0])
        for row in session.query(SessionLedger.id)
        .filter(SessionLedger.user_id == normalized_user_id)
        .all()
        if row[0] is not None
    ]

    session_events = 0
    if session_ids:
        session_events = (
            session.query(SessionLedgerEvent)
            .filter(SessionLedgerEvent.session_ledger_id.in_(session_ids))
            .count()
        )

    memory_links = (
        session.query(UserMemoryLink).filter(UserMemoryLink.user_id == normalized_user_id).count()
    )
    memory_views = (
        session.query(UserMemoryView).filter(UserMemoryView.user_id == normalized_user_id).count()
    )
    skill_proposals = (
        session.query(SkillProposal).filter(SkillProposal.user_id == normalized_user_id).count()
    )

    if not dry_run:
        (
            session.query(UserMemoryLink)
            .filter(UserMemoryLink.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(UserMemoryEntry)
            .filter(UserMemoryEntry.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(UserMemoryView)
            .filter(UserMemoryView.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(SkillProposal)
            .filter(SkillProposal.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(SessionLedger)
            .filter(SessionLedger.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        session.flush()

    return {
        "user_id": normalized_user_id,
        "entry_ids": entry_ids,
        "session_ids": session_ids,
        "session_ledgers": len(session_ids),
        "session_events": session_events,
        "memory_entries": len(entry_ids),
        "memory_links": memory_links,
        "memory_views": memory_views,
        "skill_proposals": skill_proposals,
        "deleted": not dry_run,
    }


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
        logger.warning("Failed to release user-memory cleanup lock %s cleanly: %s", lock_id, exc)
    finally:
        session.close()


def run_user_memory_vector_cleanup_once(
    settings: Optional[UserMemoryVectorCleanupSettings] = None,
    *,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Run one user-memory vector cleanup cycle."""

    cfg = (settings or load_user_memory_vector_cleanup_settings()).with_defaults()
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
        live_entry_ids = _load_live_user_memory_entry_ids()
        vector_cleanup = cleanup_orphaned_user_memory_vectors(
            live_entry_ids=live_entry_ids,
            batch_size=cfg.batch_size,
            dry_run=cfg.dry_run,
        )
        compaction = {"attempted": False, "triggered": False, "error": None}
        if cfg.compact_on_cycle:
            compaction = trigger_user_memory_collection_compaction(dry_run=cfg.dry_run)

        cleanup = {
            "live_entry_ids": len(live_entry_ids),
            "vector_cleanup": vector_cleanup,
            "compaction": compaction,
        }
        return {
            "status": "ok",
            "reason": reason,
            "dry_run": cfg.dry_run,
            "cleanup": cleanup,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class UserMemoryVectorCleanupManager:
    """Periodic scheduler for orphaned user-memory vector cleanup."""

    def __init__(self, settings: Optional[UserMemoryVectorCleanupSettings] = None):
        self.settings = (settings or load_user_memory_vector_cleanup_settings()).with_defaults()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self._run_lock = asyncio.Lock()

    async def start(self) -> bool:
        if not self.settings.enabled:
            logger.info("User-memory vector cleanup is disabled by config")
            return False
        if self._task and not self._task.done():
            return True

        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "User-memory vector cleanup manager started",
            extra={
                "interval_seconds": self.settings.interval_seconds,
                "batch_size": self.settings.batch_size,
                "dry_run": self.settings.dry_run,
                "compact_on_cycle": self.settings.compact_on_cycle,
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
        logger.info("User-memory vector cleanup manager stopped")

    async def run_once(self, *, reason: str = "manual") -> Dict[str, Any]:
        async with self._run_lock:
            result = await asyncio.to_thread(
                run_user_memory_vector_cleanup_once,
                self.settings,
                reason=reason,
            )
            level = (
                logging.INFO
                if result.get("status") in {"ok", "disabled", "skipped"}
                else logging.WARNING
            )
            cleanup = result.get("cleanup") or {}
            vector_cleanup = cleanup.get("vector_cleanup") or {}
            logger.log(
                level,
                "User-memory vector cleanup cycle finished",
                extra={
                    "status": result.get("status"),
                    "reason": reason,
                    "dry_run": result.get("dry_run"),
                    "live_entry_ids": cleanup.get("live_entry_ids"),
                    "orphaned_entry_ids": vector_cleanup.get("orphaned_entry_ids"),
                    "deleted_entry_ids": vector_cleanup.get("deleted_entry_ids"),
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
                logger.warning("Startup user-memory vector cleanup cycle failed: %s", exc)

        while not self._shutdown:
            should_stop = await self._sleep_or_stop(self.settings.interval_seconds)
            if should_stop:
                break
            try:
                await self.run_once(reason="scheduled")
            except Exception as exc:
                logger.warning("Scheduled user-memory vector cleanup cycle failed: %s", exc)


_user_memory_vector_cleanup_manager: Optional[UserMemoryVectorCleanupManager] = None
_user_memory_vector_cleanup_manager_lock = threading.Lock()


def get_user_memory_vector_cleanup_manager() -> UserMemoryVectorCleanupManager:
    """Return the global user-memory vector cleanup manager singleton."""

    global _user_memory_vector_cleanup_manager
    with _user_memory_vector_cleanup_manager_lock:
        if _user_memory_vector_cleanup_manager is None:
            _user_memory_vector_cleanup_manager = UserMemoryVectorCleanupManager()
        return _user_memory_vector_cleanup_manager


async def initialize_user_memory_vector_cleanup_manager() -> (
    Optional[UserMemoryVectorCleanupManager]
):
    """Initialize and start the user-memory vector cleanup manager if enabled."""

    manager = get_user_memory_vector_cleanup_manager()
    started = await manager.start()
    return manager if started else None


async def shutdown_user_memory_vector_cleanup_manager() -> None:
    """Shutdown the user-memory vector cleanup manager singleton."""

    global _user_memory_vector_cleanup_manager
    with _user_memory_vector_cleanup_manager_lock:
        manager = _user_memory_vector_cleanup_manager
        _user_memory_vector_cleanup_manager = None

    if manager is not None:
        await manager.stop()
