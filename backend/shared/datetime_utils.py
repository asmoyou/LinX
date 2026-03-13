"""UTC datetime helpers that avoid deprecated stdlib constructors."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return a naive UTC datetime compatible with legacy call sites."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcfromtimestamp(timestamp: float) -> datetime:
    """Return a naive UTC datetime for a POSIX timestamp."""
    return datetime.fromtimestamp(timestamp, timezone.utc).replace(tzinfo=None)
