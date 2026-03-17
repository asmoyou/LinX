"""Background worker for user-memory vector indexing jobs."""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from memory_system.embedding_service import get_embedding_service
from shared.config import Config, get_config
from shared.metrics import (
    user_memory_embedding_job_latency_seconds,
    user_memory_embedding_jobs_pending,
)
from user_memory.indexing_jobs import (
    ClaimedUserMemoryJob,
    claim_user_memory_jobs,
    count_pending_user_memory_jobs,
    mark_user_memory_job_done,
    requeue_stale_user_memory_jobs,
    reschedule_user_memory_job,
)
from user_memory.vector_documents import (
    build_entry_vector_content,
    build_entry_vector_metadata,
    build_view_vector_content,
    build_view_vector_metadata,
    compute_vector_document_hash,
    datetime_to_epoch_seconds,
)
from user_memory.vector_index import (
    bootstrap_user_memory_vector_index,
    build_user_memory_vector_metadata,
    delete_user_memory_vector,
    delete_user_memory_vectors_for_user,
    upsert_user_memory_vector,
)

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
class UserMemoryIndexingSettings:
    """Configuration for the background vector indexing worker."""

    enabled: bool = True
    run_on_startup: bool = True
    startup_delay_seconds: int = 10
    poll_interval_seconds: int = 5
    batch_size: int = 32
    stale_lock_seconds: int = 900
    max_attempts: int = 8
    retry_backoff_seconds: int = 30


def load_user_memory_indexing_settings(
    config: Optional[Config] = None,
) -> UserMemoryIndexingSettings:
    cfg = config or get_config()
    raw = cfg.get("user_memory.vector_indexing", {}) or {}
    return UserMemoryIndexingSettings(
        enabled=_cfg_bool(raw.get("enabled"), True),
        run_on_startup=_cfg_bool(raw.get("run_on_startup"), True),
        startup_delay_seconds=_cfg_int(raw.get("startup_delay_seconds"), 10, minimum=0),
        poll_interval_seconds=_cfg_int(raw.get("poll_interval_seconds"), 5, minimum=1),
        batch_size=_cfg_int(raw.get("batch_size"), 32, minimum=1),
        stale_lock_seconds=_cfg_int(raw.get("stale_lock_seconds"), 900, minimum=60),
        max_attempts=_cfg_int(raw.get("max_attempts"), 8, minimum=1),
        retry_backoff_seconds=_cfg_int(raw.get("retry_backoff_seconds"), 30, minimum=1),
    )


class UserMemoryIndexingWorker:
    """Async lifecycle wrapper around the DB-backed indexing queue."""

    def __init__(self, settings: Optional[UserMemoryIndexingSettings] = None):
        self.settings = settings or load_user_memory_indexing_settings()
        self._task: Optional[asyncio.Task] = None
        self._shutdown = False
        self.worker_id = f"{socket.gethostname()}:{id(self)}"

    async def start(self) -> bool:
        if not self.settings.enabled:
            logger.info("User-memory indexing worker is disabled by config")
            return False
        if self._task and not self._task.done():
            return True
        bootstrap_user_memory_vector_index(build_state="ready")
        recovered_jobs = requeue_stale_user_memory_jobs(
            stale_after_seconds=min(self.settings.stale_lock_seconds, 120),
        )
        self._shutdown = False
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "User-memory indexing worker started",
            extra={
                "poll_interval_seconds": self.settings.poll_interval_seconds,
                "batch_size": self.settings.batch_size,
                "recovered_jobs": recovered_jobs,
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
        logger.info("User-memory indexing worker stopped")

    async def run_once(self, *, reason: str = "manual") -> Dict[str, Any]:
        result = await asyncio.to_thread(
            run_user_memory_indexing_once,
            self.settings,
            worker_id=self.worker_id,
            reason=reason,
        )
        logger.info("User-memory indexing cycle finished", extra=result)
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
                logger.warning("User-memory indexing cycle failed: %s", exc, exc_info=True)
            await asyncio.sleep(self.settings.poll_interval_seconds)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_source_row(job: ClaimedUserMemoryJob):
    from database.connection import get_db_session
    from database.models import UserMemoryEntry, UserMemoryView

    if job.source_kind == "entry":
        with get_db_session() as session:
            return (
                session.query(UserMemoryEntry)
                .filter(UserMemoryEntry.id == int(job.source_id))
                .one_or_none()
            )
    if job.source_kind == "view":
        with get_db_session() as session:
            return (
                session.query(UserMemoryView)
                .filter(UserMemoryView.id == int(job.source_id))
                .one_or_none()
            )
    return None


def _mark_row_synced(
    *,
    source_kind: str,
    source_id: int,
    collection_name: str,
    document_hash: str,
) -> None:
    from database.connection import get_db_session
    from database.models import UserMemoryEntry, UserMemoryView

    with get_db_session() as session:
        if source_kind == "entry":
            row = (
                session.query(UserMemoryEntry)
                .filter(UserMemoryEntry.id == int(source_id))
                .one_or_none()
            )
        else:
            row = (
                session.query(UserMemoryView)
                .filter(UserMemoryView.id == int(source_id))
                .one_or_none()
            )
        if row is None:
            return
        row.vector_sync_state = "synced"
        row.vector_document_hash = document_hash
        row.vector_collection_name = collection_name
        row.vector_indexed_at = _now()
        row.vector_error = None
        session.flush()


def _mark_row_deleted(*, source_kind: str, source_id: int) -> None:
    from database.connection import get_db_session
    from database.models import UserMemoryEntry, UserMemoryView

    with get_db_session() as session:
        if source_kind == "entry":
            row = (
                session.query(UserMemoryEntry)
                .filter(UserMemoryEntry.id == int(source_id))
                .one_or_none()
            )
        else:
            row = (
                session.query(UserMemoryView)
                .filter(UserMemoryView.id == int(source_id))
                .one_or_none()
            )
        if row is None:
            return
        row.vector_sync_state = "deleted"
        row.vector_error = None
        row.vector_collection_name = None
        session.flush()


def _mark_row_failed(*, source_kind: str, source_id: int, error: str) -> None:
    from database.connection import get_db_session
    from database.models import UserMemoryEntry, UserMemoryView

    with get_db_session() as session:
        if source_kind == "entry":
            row = (
                session.query(UserMemoryEntry)
                .filter(UserMemoryEntry.id == int(source_id))
                .one_or_none()
            )
        else:
            row = (
                session.query(UserMemoryView)
                .filter(UserMemoryView.id == int(source_id))
                .one_or_none()
            )
        if row is None:
            return
        row.vector_sync_state = "failed"
        row.vector_error = str(error or "")[:4000] or None
        session.flush()


def _build_upsert_document(job: ClaimedUserMemoryJob) -> Optional[Dict[str, Any]]:
    row = _load_source_row(job)
    if row is None:
        return None

    if job.source_kind == "entry":
        content = build_entry_vector_content(row)
        metadata = build_entry_vector_metadata(row)
        source_metadata = {
            "source_kind": "entry",
            "source_id": int(row.id),
            "user_id": str(row.user_id),
            "status": str(row.status or "active"),
            "entry_type": getattr(row, "entry_type", None),
            "fact_kind": getattr(row, "fact_kind", None),
            "importance": float(row.importance or 0.0),
            "confidence": float(row.confidence or 0.0),
            "updated_at_ts": datetime_to_epoch_seconds(row.updated_at or row.created_at),
            "content": content,
            "metadata": metadata,
        }
    else:
        content = build_view_vector_content(row)
        metadata = build_view_vector_metadata(row)
        source_metadata = {
            "source_kind": "view",
            "source_id": int(row.id),
            "user_id": str(row.user_id),
            "status": str(row.status or "active"),
            "view_type": getattr(row, "view_type", None),
            "importance": float((row.view_data or {}).get("importance") or 0.0),
            "confidence": float((row.view_data or {}).get("confidence") or 0.0),
            "updated_at_ts": datetime_to_epoch_seconds(row.updated_at or row.created_at),
            "content": content,
            "metadata": metadata,
        }

    embedding = get_embedding_service(scope="user_memory").generate_embedding(content)
    document_hash = compute_vector_document_hash(source_metadata)
    document = build_user_memory_vector_metadata(
        source_kind=source_metadata["source_kind"],
        source_id=source_metadata["source_id"],
        user_id=source_metadata["user_id"],
        status=source_metadata["status"],
        entry_type=source_metadata.get("entry_type"),
        fact_kind=source_metadata.get("fact_kind"),
        view_type=source_metadata.get("view_type"),
        importance=source_metadata.get("importance"),
        confidence=source_metadata.get("confidence"),
        updated_at_ts=source_metadata.get("updated_at_ts"),
        content=source_metadata.get("content"),
        metadata=source_metadata.get("metadata"),
    )
    document["embedding"] = embedding
    document["_document_hash"] = document_hash
    return document


def _process_job(job: ClaimedUserMemoryJob, settings: UserMemoryIndexingSettings) -> str:
    if job.operation == "delete_user":
        delete_user_memory_vectors_for_user(
            user_id=job.user_id,
            collection_name=job.collection_name,
        )
        return "deleted_user"

    if job.operation == "delete":
        if job.source_id is not None:
            delete_user_memory_vector(
                source_kind=job.source_kind,
                source_id=job.source_id,
                collection_name=job.collection_name,
            )
            _mark_row_deleted(source_kind=job.source_kind, source_id=job.source_id)
        return "deleted"

    document = _build_upsert_document(job)
    if document is None:
        if job.source_id is not None:
            delete_user_memory_vector(
                source_kind=job.source_kind,
                source_id=job.source_id,
                collection_name=job.collection_name,
            )
        return "missing_source_deleted"

    upsert_user_memory_vector(document, collection_name=job.collection_name)
    _mark_row_synced(
        source_kind=job.source_kind,
        source_id=int(document["source_id"]),
        collection_name=job.collection_name,
        document_hash=str(document["_document_hash"]),
    )
    return "upserted"


def run_user_memory_indexing_once(
    settings: Optional[UserMemoryIndexingSettings] = None,
    *,
    worker_id: str,
    reason: str = "manual",
) -> Dict[str, Any]:
    """Run one indexing batch in the current thread."""

    cfg = settings or load_user_memory_indexing_settings()
    started = time.monotonic()
    if not cfg.enabled:
        user_memory_embedding_jobs_pending.set(float(count_pending_user_memory_jobs()))
        return {
            "status": "disabled",
            "reason": reason,
            "pending_jobs": count_pending_user_memory_jobs(),
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        }

    bootstrap_user_memory_vector_index(build_state="ready")
    jobs = claim_user_memory_jobs(
        worker_id=worker_id,
        batch_size=cfg.batch_size,
        stale_after_seconds=cfg.stale_lock_seconds,
    )
    processed = 0
    succeeded = 0
    failed = 0
    for job in jobs:
        processed += 1
        job_started = time.monotonic()
        try:
            _process_job(job, cfg)
            mark_user_memory_job_done(job.id)
            succeeded += 1
        except Exception as exc:
            terminal = int(job.attempt_count or 0) >= int(cfg.max_attempts)
            if job.source_id is not None and job.source_kind in {"entry", "view"}:
                _mark_row_failed(
                    source_kind=job.source_kind,
                    source_id=int(job.source_id),
                    error=str(exc),
                )
            reschedule_user_memory_job(
                job.id,
                error=str(exc),
                backoff_seconds=cfg.retry_backoff_seconds,
                terminal=terminal,
            )
            logger.warning(
                "User-memory indexing job failed",
                extra={
                    "job_id": job.id,
                    "job_key": job.job_key,
                    "terminal": terminal,
                    "attempt_count": job.attempt_count,
                    "error": str(exc),
                },
            )
            failed += 1
        finally:
            user_memory_embedding_job_latency_seconds.observe(time.monotonic() - job_started)

    pending_jobs = count_pending_user_memory_jobs()
    user_memory_embedding_jobs_pending.set(float(pending_jobs))
    return {
        "status": "ok",
        "reason": reason,
        "claimed_jobs": len(jobs),
        "processed_jobs": processed,
        "succeeded_jobs": succeeded,
        "failed_jobs": failed,
        "pending_jobs": pending_jobs,
        "duration_ms": round((time.monotonic() - started) * 1000, 2),
    }


_indexing_worker: Optional[UserMemoryIndexingWorker] = None


async def initialize_user_memory_indexing_worker() -> Optional[UserMemoryIndexingWorker]:
    """Start the background worker when enabled."""

    global _indexing_worker
    if _indexing_worker is None:
        _indexing_worker = UserMemoryIndexingWorker()
    started = await _indexing_worker.start()
    return _indexing_worker if started else None


async def shutdown_user_memory_indexing_worker() -> None:
    """Stop the shared background worker."""

    global _indexing_worker
    if _indexing_worker is None:
        return
    await _indexing_worker.stop()
    _indexing_worker = None


__all__ = [
    "UserMemoryIndexingSettings",
    "UserMemoryIndexingWorker",
    "initialize_user_memory_indexing_worker",
    "load_user_memory_indexing_settings",
    "run_user_memory_indexing_once",
    "shutdown_user_memory_indexing_worker",
]
