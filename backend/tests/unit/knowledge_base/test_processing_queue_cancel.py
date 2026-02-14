"""Unit tests for processing queue cancellation behavior."""

from unittest.mock import Mock

from knowledge_base.processing_queue import ProcessingQueue


def _build_job_json(status: str) -> str:
    return (
        '{"job_id": "job123", "status": "'
        + status
        + '", "document_id": "doc123", "file_key": "key", "bucket": "bucket", '
        '"mime_type": "application/pdf", "user_id": "user", "task_id": null, '
        '"created_at": "2024-01-01T00:00:00"}'
    )


def test_request_cancel_queued_job_marks_cancelled_and_removes_queue_id() -> None:
    """Queued jobs should be marked cancelled and removed from Redis list."""
    redis_client = Mock()
    redis_client.get.return_value = _build_job_json("queued")

    queue = ProcessingQueue(redis_manager=Mock(get_client=Mock(return_value=redis_client)))
    cancelled = queue.request_cancel("job123")

    assert cancelled is True
    redis_client.lrem.assert_called_once_with(queue.queue_key, 0, "job123")
    assert redis_client.set.called


def test_request_cancel_completed_job_returns_false() -> None:
    """Completed jobs should ignore cancellation requests."""
    redis_client = Mock()
    redis_client.get.return_value = _build_job_json("completed")

    queue = ProcessingQueue(redis_manager=Mock(get_client=Mock(return_value=redis_client)))
    cancelled = queue.request_cancel("job123")

    assert cancelled is False
    redis_client.lrem.assert_not_called()
