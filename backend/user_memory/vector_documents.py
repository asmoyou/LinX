"""Shared document assembly helpers for user-memory hybrid retrieval."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

_DATE_PATTERNS = (
    re.compile(r"^\s*(?P<year>\d{4})[-/](?P<month>\d{1,2})[-/](?P<day>\d{1,2})\s*$"),
    re.compile(r"^\s*(?P<year>\d{4})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日?\s*$"),
)
_MONTH_PATTERNS = (
    re.compile(r"^\s*(?P<year>\d{4})[-/](?P<month>\d{1,2})\s*$"),
    re.compile(r"^\s*(?P<year>\d{4})年(?P<month>\d{1,2})月\s*$"),
)
_YEAR_PATTERNS = (
    re.compile(r"^\s*(?P<year>\d{4})\s*$"),
    re.compile(r"^\s*(?P<year>\d{4})年\s*$"),
)
_WHITESPACE_PATTERN = re.compile(r"\s+")


def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _last_day(year: int, month: int) -> int:
    return int(calendar.monthrange(year, month)[1])


def _normalize_text(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def _flatten_payload(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, dict):
        flattened: list[str] = []
        for item in value.values():
            flattened.extend(_flatten_payload(item))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened: list[str] = []
        for item in value:
            flattened.extend(_flatten_payload(item))
        return flattened
    text = str(value).strip()
    return [text] if text else []


def _build_search_document(*parts: object, payload: Any = None) -> str:
    document_parts = [str(part).strip() for part in parts if str(part or "").strip()]
    if payload is not None:
        document_parts.extend(_flatten_payload(payload))
    return _normalize_text(" ".join(document_parts))


def parse_event_time_range(raw_value: object) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Parse coarse YYYY / YYYY-MM / YYYY-MM-DD memory event timestamps."""

    value = str(raw_value or "").strip()
    if not value:
        return None, None

    for pattern in _DATE_PATTERNS:
        match = pattern.match(value)
        if match:
            year = int(match.group("year"))
            month = int(match.group("month"))
            day = int(match.group("day"))
            start = _utc(year, month, day)
            return start, start

    for pattern in _MONTH_PATTERNS:
        match = pattern.match(value)
        if match:
            year = int(match.group("year"))
            month = int(match.group("month"))
            start = _utc(year, month, 1)
            end = _utc(year, month, _last_day(year, month))
            return start, end

    for pattern in _YEAR_PATTERNS:
        match = pattern.match(value)
        if match:
            year = int(match.group("year"))
            return _utc(year, 1, 1), _utc(year, 12, 31)

    return None, None


def build_entry_vector_content(row: Any) -> str:
    payload = row.entry_data if isinstance(row.entry_data, dict) else {}
    return _build_search_document(
        row.entry_key,
        row.canonical_text,
        row.summary,
        getattr(row, "details", None),
        row.predicate,
        row.object_text,
        row.event_time,
        row.location,
        row.topic,
        row.persons,
        row.entities,
        payload=payload,
    )


def build_view_vector_content(row: Any) -> str:
    payload = row.view_data if isinstance(row.view_data, dict) else {}
    return _build_search_document(
        row.view_key,
        row.title,
        row.content,
        getattr(row, "details", None),
        payload=payload,
    )


def build_entry_vector_metadata(row: Any) -> Dict[str, Any]:
    payload = row.entry_data if isinstance(row.entry_data, dict) else {}
    return {
        "entry_key": getattr(row, "entry_key", None),
        "fact_kind": getattr(row, "fact_kind", None),
        "predicate": getattr(row, "predicate", None),
        "object_text": getattr(row, "object_text", None),
        "event_time": getattr(row, "event_time", None),
        "location": getattr(row, "location", None),
        "topic": getattr(row, "topic", None),
        "persons": list(getattr(row, "persons", None) or []),
        "entities": list(getattr(row, "entities", None) or []),
        "source_session_ledger_id": getattr(row, "source_session_ledger_id", None),
        "payload": payload,
    }


def build_view_vector_metadata(row: Any) -> Dict[str, Any]:
    payload = row.view_data if isinstance(row.view_data, dict) else {}
    return {
        "view_key": getattr(row, "view_key", None),
        "view_type": getattr(row, "view_type", None),
        "title": getattr(row, "title", None),
        "payload": payload,
    }


def compute_vector_document_hash(parts: Mapping[str, Any]) -> str:
    """Build a stable document hash for sync/reconcile bookkeeping."""

    encoded = json.dumps(dict(parts or {}), sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def datetime_to_epoch_seconds(value: Optional[datetime]) -> int:
    if not isinstance(value, datetime):
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp())


def normalize_people_terms(values: Optional[Sequence[Any]]) -> list[str]:
    return [str(value).strip() for value in list(values or []) if str(value).strip()]


__all__ = [
    "build_entry_vector_content",
    "build_entry_vector_metadata",
    "build_view_vector_content",
    "build_view_vector_metadata",
    "compute_vector_document_hash",
    "datetime_to_epoch_seconds",
    "normalize_people_terms",
    "parse_event_time_range",
]
