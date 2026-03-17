"""DB-backed job queue for user-memory vector indexing."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from sqlalchemy import and_, or_

from database.connection import get_db_session
from database.models import UserMemoryEmbeddingJob

logger = logging.getLogger(__name__)

USER_MEMORY_JOB_STATUS_PENDING = "pending"
USER_MEMORY_JOB_STATUS_PROCESSING = "processing"
USER_MEMORY_JOB_STATUS_DONE = "done"
USER_MEMORY_JOB_STATUS_FAILED = "failed"

USER_MEMORY_SOURCE_KINDS = {"entry", "view", "user_delete", "reindex"}
USER_MEMORY_OPERATIONS = {"upsert", "delete", "delete_user"}


@dataclass(frozen=True)
class ClaimedUserMemoryJob:
    """Serializable claimed job payload used by the worker."""

    id: int
    job_key: str
    source_kind: str
    source_id: Optional[int]
    user_id: str
    operation: str
    collection_name: str
    embedding_signature: str
    payload: Dict[str, Any]
    attempt_count: int
    available_at: Optional[datetime]
    locked_at: Optional[datetime]
    locked_by: Optional[str]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _job_payload(payload: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return dict(payload or {})


def build_user_memory_job_key(
    *,
    source_kind: str,
    source_id: Optional[int],
    user_id: str,
    operation: str,
    collection_name: Optional[str] = None,
    embedding_signature: Optional[str] = None,
) -> str:
    """Build the stable dedupe key for one indexing operation."""

    normalized_kind = str(source_kind or "").strip().lower()
    normalized_operation = str(operation or "").strip().lower()
    if normalized_kind == "entry":
        return f"entry:{int(source_id)}:{normalized_operation}:{embedding_signature or ''}"
    if normalized_kind == "view":
        return f"view:{int(source_id)}:{normalized_operation}:{embedding_signature or ''}"
    if normalized_operation == "delete_user":
        return f"user:{str(user_id)}:delete:{collection_name or ''}"
    if normalized_kind == "reindex":
        return f"reindex:{str(user_id)}:{collection_name or ''}:{embedding_signature or ''}"
    raise ValueError(f"Unsupported user-memory job identity: {source_kind}/{operation}")


def enqueue_user_memory_job(
    session,
    *,
    source_kind: str,
    source_id: Optional[int],
    user_id: str,
    operation: str,
    collection_name: str,
    embedding_signature: str,
    payload: Optional[Mapping[str, Any]] = None,
    available_at: Optional[datetime] = None,
) -> UserMemoryEmbeddingJob:
    """Create or refresh one user-memory indexing job inside an existing transaction."""

    normalized_kind = str(source_kind or "").strip().lower()
    normalized_operation = str(operation or "").strip().lower()
    if normalized_kind not in USER_MEMORY_SOURCE_KINDS:
        raise ValueError(f"Unsupported user-memory source kind: {source_kind}")
    if normalized_operation not in USER_MEMORY_OPERATIONS:
        raise ValueError(f"Unsupported user-memory job operation: {operation}")

    job_key = build_user_memory_job_key(
        source_kind=normalized_kind,
        source_id=source_id,
        user_id=user_id,
        operation=normalized_operation,
        collection_name=collection_name,
        embedding_signature=embedding_signature,
    )
    existing = (
        session.query(UserMemoryEmbeddingJob)
        .filter(UserMemoryEmbeddingJob.job_key == job_key)
        .one_or_none()
    )
    if existing is None:
        existing = UserMemoryEmbeddingJob(job_key=job_key)
        session.add(existing)

    existing.source_kind = normalized_kind
    existing.source_id = int(source_id) if source_id is not None else None
    existing.user_id = str(user_id)
    existing.operation = normalized_operation
    existing.collection_name = str(collection_name)
    existing.embedding_signature = str(embedding_signature)
    existing.payload = _job_payload(payload)
    existing.status = USER_MEMORY_JOB_STATUS_PENDING
    existing.available_at = available_at or _utc_now()
    existing.locked_at = None
    existing.locked_by = None
    existing.last_error = None
    session.flush()
    return existing


def enqueue_user_memory_upsert_job(
    session,
    *,
    source_kind: str,
    source_id: int,
    user_id: str,
    collection_name: str,
    embedding_signature: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> UserMemoryEmbeddingJob:
    """Enqueue an upsert job for one entry or view."""

    return enqueue_user_memory_job(
        session,
        source_kind=source_kind,
        source_id=source_id,
        user_id=user_id,
        operation="upsert",
        collection_name=collection_name,
        embedding_signature=embedding_signature,
        payload=payload,
    )


def enqueue_user_memory_delete_job(
    session,
    *,
    source_kind: str,
    source_id: int,
    user_id: str,
    collection_name: str,
    embedding_signature: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> UserMemoryEmbeddingJob:
    """Enqueue a delete job for one entry or view."""

    return enqueue_user_memory_job(
        session,
        source_kind=source_kind,
        source_id=source_id,
        user_id=user_id,
        operation="delete",
        collection_name=collection_name,
        embedding_signature=embedding_signature,
        payload=payload,
    )


def enqueue_user_memory_delete_user_job(
    session,
    *,
    user_id: str,
    collection_name: str,
    embedding_signature: str,
    payload: Optional[Mapping[str, Any]] = None,
) -> UserMemoryEmbeddingJob:
    """Enqueue a bulk delete job for one user."""

    return enqueue_user_memory_job(
        session,
        source_kind="user_delete",
        source_id=None,
        user_id=user_id,
        operation="delete_user",
        collection_name=collection_name,
        embedding_signature=embedding_signature,
        payload=payload,
    )


def claim_user_memory_jobs(
    *,
    worker_id: str,
    batch_size: int,
    stale_after_seconds: int = 900,
) -> List[ClaimedUserMemoryJob]:
    """Claim a batch of pending user-memory indexing jobs."""

    now = _utc_now()
    stale_cutoff = now - timedelta(seconds=max(int(stale_after_seconds), 60))
    with get_db_session() as session:
        query = (
            session.query(UserMemoryEmbeddingJob)
            .filter(
                UserMemoryEmbeddingJob.available_at <= now,
                or_(
                    UserMemoryEmbeddingJob.status == USER_MEMORY_JOB_STATUS_PENDING,
                    and_(
                        UserMemoryEmbeddingJob.status == USER_MEMORY_JOB_STATUS_PROCESSING,
                        UserMemoryEmbeddingJob.locked_at <= stale_cutoff,
                    ),
                ),
            )
            .order_by(
                UserMemoryEmbeddingJob.available_at.asc(),
                UserMemoryEmbeddingJob.id.asc(),
            )
            .with_for_update(skip_locked=True)
            .limit(max(int(batch_size), 1))
        )
        jobs = list(query.all())
        claimed: List[ClaimedUserMemoryJob] = []
        for job in jobs:
            job.status = USER_MEMORY_JOB_STATUS_PROCESSING
            job.locked_at = now
            job.locked_by = str(worker_id)
            job.attempt_count = int(job.attempt_count or 0) + 1
            payload = _job_payload(job.payload)
            claimed.append(
                ClaimedUserMemoryJob(
                    id=int(job.id),
                    job_key=str(job.job_key),
                    source_kind=str(job.source_kind),
                    source_id=int(job.source_id) if job.source_id is not None else None,
                    user_id=str(job.user_id),
                    operation=str(job.operation),
                    collection_name=str(job.collection_name),
                    embedding_signature=str(job.embedding_signature),
                    payload=payload,
                    attempt_count=int(job.attempt_count or 0),
                    available_at=job.available_at,
                    locked_at=job.locked_at,
                    locked_by=job.locked_by,
                )
            )
        session.flush()
        return claimed


def requeue_stale_user_memory_jobs(
    *,
    stale_after_seconds: int,
) -> int:
    """Return stale processing jobs to pending so the current worker can reclaim them."""

    stale_cutoff = _utc_now() - timedelta(seconds=max(int(stale_after_seconds), 1))
    with get_db_session() as session:
        jobs = (
            session.query(UserMemoryEmbeddingJob)
            .filter(
                UserMemoryEmbeddingJob.status == USER_MEMORY_JOB_STATUS_PROCESSING,
                UserMemoryEmbeddingJob.locked_at.isnot(None),
                UserMemoryEmbeddingJob.locked_at <= stale_cutoff,
            )
            .all()
        )
        for job in jobs:
            job.status = USER_MEMORY_JOB_STATUS_PENDING
            job.locked_at = None
            job.locked_by = None
        session.flush()
        return len(jobs)


def mark_user_memory_job_done(job_id: int) -> None:
    """Mark one indexing job as completed."""

    with get_db_session() as session:
        job = (
            session.query(UserMemoryEmbeddingJob)
            .filter(UserMemoryEmbeddingJob.id == int(job_id))
            .one_or_none()
        )
        if job is None:
            return
        job.status = USER_MEMORY_JOB_STATUS_DONE
        job.locked_at = None
        job.locked_by = None
        job.last_error = None
        session.flush()


def reschedule_user_memory_job(
    job_id: int,
    *,
    error: str,
    backoff_seconds: int,
    terminal: bool = False,
) -> None:
    """Retry or fail a job after one worker error."""

    with get_db_session() as session:
        job = (
            session.query(UserMemoryEmbeddingJob)
            .filter(UserMemoryEmbeddingJob.id == int(job_id))
            .one_or_none()
        )
        if job is None:
            return
        job.status = (
            USER_MEMORY_JOB_STATUS_FAILED if terminal else USER_MEMORY_JOB_STATUS_PENDING
        )
        job.available_at = _utc_now() + timedelta(seconds=max(int(backoff_seconds), 1))
        job.locked_at = None
        job.locked_by = None
        job.last_error = str(error or "")[:4000] or None
        session.flush()


def list_user_memory_jobs(
    *,
    statuses: Optional[Sequence[str]] = None,
    limit: int = 100,
) -> List[UserMemoryEmbeddingJob]:
    """List recent jobs for diagnostics."""

    with get_db_session() as session:
        query = session.query(UserMemoryEmbeddingJob)
        if statuses:
            query = query.filter(UserMemoryEmbeddingJob.status.in_(list(statuses)))
        query = query.order_by(UserMemoryEmbeddingJob.created_at.desc(), UserMemoryEmbeddingJob.id.desc())
        query = query.limit(max(int(limit), 1))
        return list(query.all())


def count_pending_user_memory_jobs() -> int:
    """Return the number of claimable indexing jobs."""

    with get_db_session() as session:
        stale_cutoff = _utc_now() - timedelta(seconds=60)
        return int(
            session.query(UserMemoryEmbeddingJob)
            .filter(
                or_(
                    UserMemoryEmbeddingJob.status == USER_MEMORY_JOB_STATUS_PENDING,
                    and_(
                        UserMemoryEmbeddingJob.status == USER_MEMORY_JOB_STATUS_PROCESSING,
                        UserMemoryEmbeddingJob.locked_at <= stale_cutoff,
                    ),
                )
            )
            .count()
        )


__all__ = [
    "ClaimedUserMemoryJob",
    "USER_MEMORY_JOB_STATUS_DONE",
    "USER_MEMORY_JOB_STATUS_FAILED",
    "USER_MEMORY_JOB_STATUS_PENDING",
    "USER_MEMORY_JOB_STATUS_PROCESSING",
    "build_user_memory_job_key",
    "claim_user_memory_jobs",
    "count_pending_user_memory_jobs",
    "enqueue_user_memory_delete_job",
    "enqueue_user_memory_delete_user_job",
    "enqueue_user_memory_job",
    "enqueue_user_memory_upsert_job",
    "list_user_memory_jobs",
    "mark_user_memory_job_done",
    "requeue_stale_user_memory_jobs",
    "reschedule_user_memory_job",
]
