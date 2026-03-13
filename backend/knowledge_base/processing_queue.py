"""Processing job queue using Redis.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import List, Optional

from redis.exceptions import TimeoutError as RedisTimeoutError

from message_bus.redis_manager import RedisConnectionManager, get_redis_manager
from shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)


class JobStatus(Enum):
    """Status of processing job."""

    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProcessingJob:
    """Processing job for document."""

    job_id: str
    document_id: str
    file_key: str
    bucket: str
    mime_type: str
    user_id: str
    task_id: Optional[str]
    status: JobStatus
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    cancel_requested: bool = False
    cancel_requested_at: Optional[str] = None


class ProcessingQueue:
    """Manage document processing job queue."""

    def __init__(self, redis_manager: Optional[RedisConnectionManager] = None):
        """Initialize processing queue.

        Args:
            redis_manager: Redis manager for queue operations
        """
        self.redis_manager = redis_manager or get_redis_manager()
        self.queue_key = "document_processing_queue"
        self.job_prefix = "processing_job:"
        logger.info("ProcessingQueue initialized")

    @property
    def _client(self):
        """Get the underlying redis.Redis client."""
        return self.redis_manager.get_client()

    def enqueue(
        self,
        document_id: str,
        file_key: str,
        bucket: str,
        mime_type: str,
        user_id: str,
        task_id: Optional[str] = None,
    ) -> ProcessingJob:
        """Enqueue document for processing.

        Args:
            document_id: Document identifier
            file_key: MinIO object key
            bucket: MinIO bucket name
            mime_type: File MIME type
            user_id: User ID
            task_id: Optional task ID

        Returns:
            ProcessingJob with job details
        """
        job_id = str(uuid.uuid4())
        job = ProcessingJob(
            job_id=job_id,
            document_id=document_id,
            file_key=file_key,
            bucket=bucket,
            mime_type=mime_type,
            user_id=user_id,
            task_id=task_id,
            status=JobStatus.QUEUED,
            created_at=utcnow().isoformat(),
        )

        # Serialize status enum to string for JSON
        job_dict = asdict(job)
        job_dict["status"] = (
            job_dict["status"].value
            if isinstance(job_dict["status"], JobStatus)
            else job_dict["status"]
        )

        # Store job data
        job_key = f"{self.job_prefix}{job_id}"
        self._client.set(job_key, json.dumps(job_dict))

        # Add to queue
        self._client.lpush(self.queue_key, job_id)

        logger.info(f"Job enqueued: {job_id}", extra={"document_id": document_id})
        return job

    def dequeue(self, timeout: int = 5) -> Optional[ProcessingJob]:
        """Dequeue next job for processing.

        Args:
            timeout: Timeout in seconds for blocking pop

        Returns:
            ProcessingJob or None if queue is empty
        """
        try:
            result = self._client.brpop(self.queue_key, timeout=timeout)
        except RedisTimeoutError:
            # BRPOP timeout is expected when queue is idle.
            return None
        except Exception as e:
            logger.warning(f"Queue dequeue failed: {e}")
            return None
        if not result:
            return None

        _, job_id = result
        # decode_responses=True means job_id is already a string
        if isinstance(job_id, bytes):
            job_id = job_id.decode()
        job_key = f"{self.job_prefix}{job_id}"
        job_data = self._client.get(job_key)

        if not job_data:
            return None

        job_dict = json.loads(job_data)
        job_dict["status"] = JobStatus(job_dict["status"])
        return ProcessingJob(**job_dict)

    def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
    ) -> None:
        """Update job status.

        Args:
            job_id: Job identifier
            status: New status
            error_message: Optional error message
        """
        job_key = f"{self.job_prefix}{job_id}"
        job_data = self._client.get(job_key)

        if not job_data:
            logger.warning(f"Job not found: {job_id}")
            return

        job_dict = json.loads(job_data)
        job_dict["status"] = status.value

        if status == JobStatus.PROCESSING:
            job_dict["started_at"] = utcnow().isoformat()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job_dict["completed_at"] = utcnow().isoformat()

        if error_message:
            job_dict["error_message"] = error_message

        self._client.set(job_key, json.dumps(job_dict))
        logger.info(f"Job status updated: {job_id} -> {status.value}")

    def request_cancel(self, job_id: str, error_message: Optional[str] = None) -> bool:
        """Request cancellation for a queued/processing job.

        Args:
            job_id: Job identifier
            error_message: Optional cancellation message

        Returns:
            True if cancellation was recorded, else False
        """
        job_key = f"{self.job_prefix}{job_id}"
        job_data = self._client.get(job_key)

        if not job_data:
            logger.warning(f"Job not found for cancellation: {job_id}")
            return False

        job_dict = json.loads(job_data)
        current_status = JobStatus(job_dict.get("status", JobStatus.QUEUED.value))
        if current_status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return False

        now_iso = utcnow().isoformat()
        job_dict["cancel_requested"] = True
        job_dict["cancel_requested_at"] = now_iso
        job_dict["status"] = JobStatus.CANCELLED.value
        job_dict["completed_at"] = now_iso
        job_dict["error_message"] = (
            error_message or job_dict.get("error_message") or "Processing cancelled by user."
        )

        # If still queued, remove pending job id from Redis list.
        if current_status == JobStatus.QUEUED:
            self._client.lrem(self.queue_key, 0, job_id)

        self._client.set(job_key, json.dumps(job_dict))
        logger.info(f"Cancellation requested for job: {job_id}")
        return True

    def is_cancel_requested(self, job_id: str) -> bool:
        """Check whether cancellation was requested for a job."""
        job = self.get_job(job_id)
        if not job:
            return False
        return bool(job.cancel_requested or job.status == JobStatus.CANCELLED)

    def get_job(self, job_id: str) -> Optional[ProcessingJob]:
        """Get job by ID.

        Args:
            job_id: Job identifier

        Returns:
            ProcessingJob or None if not found
        """
        job_key = f"{self.job_prefix}{job_id}"
        job_data = self._client.get(job_key)

        if not job_data:
            return None

        job_dict = json.loads(job_data)
        job_dict["status"] = JobStatus(job_dict["status"])
        return ProcessingJob(**job_dict)


# Singleton instance
_processing_queue: Optional[ProcessingQueue] = None


def get_processing_queue() -> ProcessingQueue:
    """Get or create the processing queue singleton.

    Returns:
        ProcessingQueue instance
    """
    global _processing_queue
    if _processing_queue is None:
        _processing_queue = ProcessingQueue()
    return _processing_queue
