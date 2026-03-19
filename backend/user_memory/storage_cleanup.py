"""Cleanup helpers and periodic reconciliation for user-memory hybrid indexing."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from sqlalchemy import text

from database.connection import get_connection_pool, get_db_session
from database.models import (
    SessionLedger,
    SessionLedgerEvent,
    SkillCandidate,
    UserMemoryEntry,
    UserMemoryLink,
    UserMemoryRelation,
    UserMemoryView,
)
from shared.config import Config, get_config
from user_memory.indexing_jobs import enqueue_user_memory_delete_user_job, enqueue_user_memory_upsert_job
from user_memory.vector_index import (
    build_user_memory_embedding_signature,
    build_user_memory_collection_name,
    compact_user_memory_vectors,
    delete_user_memory_vector,
    get_user_memory_vector_index_state,
    iterate_user_memory_vectors,
    resolve_active_user_memory_collection,
    set_user_memory_vector_index_state,
)

logger = logging.getLogger(__name__)
LEGACY_USER_MEMORY_ENTRIES_COLLECTION = "user_memory_entries"


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
class UserMemoryVectorCleanupSettings:
    """Configuration for periodic user-memory reconcile and compaction."""

    enabled: bool = True
    run_on_startup: bool = True
    startup_delay_seconds: int = 300
    interval_seconds: int = 21600
    dry_run: bool = False
    batch_size: int = 500
    compact_on_cycle: bool = True
    advisory_lock_id: int = 73012023
    use_advisory_lock: bool = True


def load_user_memory_vector_cleanup_settings(
    config: Optional[Config] = None,
) -> UserMemoryVectorCleanupSettings:
    cfg = config or get_config()
    raw = cfg.get("user_memory.vector_cleanup", {}) or {}
    return UserMemoryVectorCleanupSettings(
        enabled=_cfg_bool(raw.get("enabled"), True),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 300, minimum=0),
        interval_seconds=_cfg_int(raw.get("interval_seconds"), 21600, minimum=60),
        dry_run=_cfg_bool(raw.get("dry_run"), False),
        batch_size=_cfg_int(raw.get("batch_size"), 500, minimum=1),
        compact_on_cycle=_cfg_bool(raw.get("compact_on_cycle"), True),
        advisory_lock_id=_cfg_int(raw.get("advisory_lock_id"), 73012023, minimum=1),
        use_advisory_lock=_cfg_bool(raw.get("use_advisory_lock"), True),
    )


def _acquire_advisory_lock(lock_id: int):
    session = get_connection_pool().get_raw_session()
    try:
        acquired = bool(
            session.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}).scalar()
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
        session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
    except Exception as exc:
        logger.warning("Failed to release user-memory vector cleanup lock %s cleanly: %s", lock_id, exc)
    finally:
        session.close()


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
            "memory_relations": 0,
            "memory_links": 0,
            "memory_views": 0,
            "skill_candidates": 0,
            "vector_delete_job_enqueued": False,
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
    memory_relations = (
        session.query(UserMemoryRelation)
        .filter(UserMemoryRelation.user_id == normalized_user_id)
        .count()
    )
    memory_views = (
        session.query(UserMemoryView).filter(UserMemoryView.user_id == normalized_user_id).count()
    )
    skill_candidates = (
        session.query(SkillCandidate).filter(SkillCandidate.user_id == normalized_user_id).count()
    )

    vector_delete_job_enqueued = False
    active_collection = None
    if not dry_run:
        try:
            active_collection = resolve_active_user_memory_collection(session=session)
        except Exception:
            active_collection = build_user_memory_collection_name()
        try:
            enqueue_user_memory_delete_user_job(
                session,
                user_id=normalized_user_id,
                collection_name=active_collection,
                embedding_signature=build_user_memory_embedding_signature(),
                payload={"reason": "user_deleted"},
            )
            vector_delete_job_enqueued = True
        except Exception:
            vector_delete_job_enqueued = False
        (
            session.query(UserMemoryLink)
            .filter(UserMemoryLink.user_id == normalized_user_id)
            .delete(synchronize_session=False)
        )
        (
            session.query(UserMemoryRelation)
            .filter(UserMemoryRelation.user_id == normalized_user_id)
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
            session.query(SkillCandidate)
            .filter(SkillCandidate.user_id == normalized_user_id)
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
        "memory_relations": memory_relations,
        "memory_links": memory_links,
        "memory_views": memory_views,
        "skill_candidates": skill_candidates,
        "vector_delete_job_enqueued": vector_delete_job_enqueued,
        "vector_collection_name": active_collection,
        "deleted": not dry_run,
    }


def _expected_entry_keys(session) -> Set[Tuple[str, int]]:
    return {
        ("entry", int(row[0]))
        for row in session.query(UserMemoryEntry.id)
        .filter(UserMemoryEntry.status.in_(["active", "superseded"]))
        .all()
        if row[0] is not None
    }


def _expected_view_keys(session) -> Set[Tuple[str, int]]:
    return {
        ("view", int(row[0]))
        for row in session.query(UserMemoryView.id)
        .filter(UserMemoryView.status.in_(["active", "superseded"]))
        .all()
        if row[0] is not None
    }


def reconcile_user_memory_vectors(
    *,
    dry_run: bool = False,
    batch_size: int = 500,
    compact_on_cycle: bool = True,
) -> Dict[str, Any]:
    """Compare PostgreSQL rows against Milvus vectors and repair drift."""

    started = time.monotonic()
    active_collection = resolve_active_user_memory_collection()
    active_signature = build_user_memory_embedding_signature()
    with get_db_session() as session:
        expected_keys = _expected_entry_keys(session) | _expected_view_keys(session)
        expected_entry_rows = list(
            session.query(UserMemoryEntry)
            .filter(UserMemoryEntry.status.in_(["active", "superseded"]))
            .all()
        )
        expected_view_rows = list(
            session.query(UserMemoryView)
            .filter(UserMemoryView.status.in_(["active", "superseded"]))
            .all()
        )

        actual_vectors = list(iterate_user_memory_vectors(collection_name=active_collection, batch_size=batch_size))
        actual_keys = {
            (str(item.get("source_kind") or ""), int(item.get("source_id") or 0))
            for item in actual_vectors
            if item.get("source_kind") and item.get("source_id") is not None
        }

        missing_keys = sorted(expected_keys - actual_keys)
        orphan_keys = sorted(actual_keys - expected_keys)

        stale_rows = []
        for row in [*expected_entry_rows, *expected_view_rows]:
            if str(getattr(row, "vector_collection_name", "") or "") != active_collection:
                stale_rows.append(row)

        enqueued_missing = 0
        deleted_orphans = 0
        if not dry_run:
            for row in stale_rows:
                row.vector_sync_state = "pending"
                row.vector_collection_name = active_collection
                row.vector_document_hash = None
                row.vector_indexed_at = None
                row.vector_error = None

            for source_kind, source_id in missing_keys:
                if source_kind == "entry":
                    row = next((item for item in expected_entry_rows if int(item.id) == int(source_id)), None)
                else:
                    row = next((item for item in expected_view_rows if int(item.id) == int(source_id)), None)
                if row is None:
                    continue
                enqueue_user_memory_upsert_job(
                    session,
                    source_kind=source_kind,
                    source_id=int(source_id),
                    user_id=str(row.user_id),
                    collection_name=active_collection,
                    embedding_signature=active_signature,
                    payload={"reason": "reconcile_missing"},
                )
                row.vector_sync_state = "pending"
                row.vector_collection_name = active_collection
                enqueued_missing += 1

            for source_kind, source_id in orphan_keys:
                delete_user_memory_vector(
                    source_kind=source_kind,
                    source_id=int(source_id),
                    collection_name=active_collection,
                )
                deleted_orphans += 1

            session.flush()

        if not dry_run and compact_on_cycle:
            compact_user_memory_vectors(collection_name=active_collection)

        state = get_user_memory_vector_index_state(session=session)
        state["last_reconcile_at"] = datetime_now_iso()
        set_user_memory_vector_index_state(state, session=session)

    duration_ms = round((time.monotonic() - started) * 1000, 2)
    return {
        "collection_name": active_collection,
        "missing_vectors": len(missing_keys),
        "orphan_vectors": len(orphan_keys),
        "stale_rows": len(stale_rows),
        "enqueued_missing": enqueued_missing,
        "deleted_orphans": deleted_orphans,
        "dry_run": dry_run,
        "compacted": bool(compact_on_cycle and not dry_run),
        "duration_ms": duration_ms,
        "actual_vector_count": len(actual_keys),
        "expected_vector_count": len(expected_keys),
    }


def datetime_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def run_user_memory_vector_cleanup_once(
    settings: Optional[UserMemoryVectorCleanupSettings] = None,
    *,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Run one reconcile/cleanup cycle."""

    cfg = settings or load_user_memory_vector_cleanup_settings()
    started = time.monotonic()
    if not cfg.enabled:
        return {
            "status": "disabled",
            "reason": reason,
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
                "error": f"Advisory lock failed: {exc}",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "cleanup": None,
            }
        if lock_session is None:
            return {
                "status": "skipped",
                "reason": reason,
                "skip_reason": "lock_not_acquired",
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
                "cleanup": None,
            }

    try:
        cleanup = reconcile_user_memory_vectors(
            dry_run=cfg.dry_run,
            batch_size=cfg.batch_size,
            compact_on_cycle=cfg.compact_on_cycle,
        )
        return {
            "status": "ok",
            "reason": reason,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "cleanup": cleanup,
        }
    finally:
        if lock_session is not None:
            _release_advisory_lock(cfg.advisory_lock_id, lock_session)


class UserMemoryVectorCleanupManager:
    """Periodic scheduler for user-memory vector reconcile/cleanup."""

    def __init__(self, settings: Optional[UserMemoryVectorCleanupSettings] = None):
        self.settings = settings or load_user_memory_vector_cleanup_settings()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False

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
        result = await asyncio.to_thread(
            run_user_memory_vector_cleanup_once,
            self.settings,
            reason=reason,
        )
        logger.info("User-memory vector cleanup cycle finished", extra=result)
        return result

    async def _run_loop(self) -> None:
        if self.settings.run_on_startup and self.settings.startup_delay_seconds > 0:
            await asyncio.sleep(self.settings.startup_delay_seconds)
        while not self._shutdown:
            try:
                await self.run_once(reason="scheduled")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("User-memory vector cleanup cycle failed: %s", exc, exc_info=True)
            await asyncio.sleep(self.settings.interval_seconds)


def drop_legacy_user_memory_vector_collection(
    *,
    milvus_conn: Optional[Any] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Drop the unused legacy Milvus collection if it still exists."""

    connection = milvus_conn
    if connection is None:
        from memory_system.milvus_connection import get_milvus_connection

        connection = get_milvus_connection()

    try:
        exists = bool(connection.collection_exists(LEGACY_USER_MEMORY_ENTRIES_COLLECTION))
    except Exception as exc:
        logger.warning(
            "Failed to inspect legacy user-memory Milvus collection",
            extra={"collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION, "error": str(exc)},
        )
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": None,
            "dropped": False,
            "dry_run": dry_run,
            "error": str(exc),
        }

    if not exists:
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": False,
            "dropped": False,
            "dry_run": dry_run,
            "error": None,
        }

    if dry_run:
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": True,
            "dropped": False,
            "dry_run": True,
            "error": None,
        }

    try:
        connection.drop_collection(LEGACY_USER_MEMORY_ENTRIES_COLLECTION)
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": True,
            "dropped": True,
            "dry_run": False,
            "error": None,
        }
    except Exception as exc:
        logger.warning(
            "Failed to drop legacy user-memory Milvus collection",
            extra={"collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION, "error": str(exc)},
        )
        return {
            "collection": LEGACY_USER_MEMORY_ENTRIES_COLLECTION,
            "exists": True,
            "dropped": False,
            "dry_run": False,
            "error": str(exc),
        }


_vector_cleanup_manager: Optional[UserMemoryVectorCleanupManager] = None


async def initialize_user_memory_vector_cleanup_manager() -> Optional[UserMemoryVectorCleanupManager]:
    """Start the shared user-memory vector cleanup manager."""

    global _vector_cleanup_manager
    if _vector_cleanup_manager is None:
        _vector_cleanup_manager = UserMemoryVectorCleanupManager()
    started = await _vector_cleanup_manager.start()
    return _vector_cleanup_manager if started else None


async def shutdown_user_memory_vector_cleanup_manager() -> None:
    """Stop the shared user-memory vector cleanup manager."""

    global _vector_cleanup_manager
    if _vector_cleanup_manager is None:
        return
    await _vector_cleanup_manager.stop()
    _vector_cleanup_manager = None


__all__ = [
    "LEGACY_USER_MEMORY_ENTRIES_COLLECTION",
    "UserMemoryVectorCleanupManager",
    "UserMemoryVectorCleanupSettings",
    "drop_legacy_user_memory_vector_collection",
    "initialize_user_memory_vector_cleanup_manager",
    "load_user_memory_vector_cleanup_settings",
    "prepare_user_memory_rows_for_user_deletion",
    "reconcile_user_memory_vectors",
    "run_user_memory_vector_cleanup_once",
    "shutdown_user_memory_vector_cleanup_manager",
]
