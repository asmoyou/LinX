"""Process-local cancellation markers for knowledge processing jobs."""

from __future__ import annotations

import threading
import time
from typing import Dict

_CANCELLATION_TTL_SECONDS = 24 * 60 * 60
_cancelled_documents: Dict[str, float] = {}
_registry_lock = threading.Lock()


def _prune_expired(now: float) -> None:
    expired = [
        document_id
        for document_id, requested_at in _cancelled_documents.items()
        if (now - requested_at) >= _CANCELLATION_TTL_SECONDS
    ]
    for document_id in expired:
        _cancelled_documents.pop(document_id, None)


def request_document_cancellation(document_id: str) -> None:
    """Register a best-effort cancellation marker for one knowledge item."""
    document_key = str(document_id or "").strip()
    if not document_key:
        return

    now = time.monotonic()
    with _registry_lock:
        _prune_expired(now)
        _cancelled_documents[document_key] = now


def clear_document_cancellation(document_id: str) -> None:
    """Clear a previously registered cancellation marker."""
    document_key = str(document_id or "").strip()
    if not document_key:
        return

    with _registry_lock:
        _cancelled_documents.pop(document_key, None)


def is_document_cancel_requested(document_id: str) -> bool:
    """Return ``True`` when a cancellation marker is currently registered."""
    document_key = str(document_id or "").strip()
    if not document_key:
        return False

    now = time.monotonic()
    with _registry_lock:
        _prune_expired(now)
        return document_key in _cancelled_documents
