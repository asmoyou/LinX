"""Tests for user-memory vector document helpers."""

from datetime import datetime, timezone
from types import SimpleNamespace

from user_memory.vector_documents import (
    build_entry_vector_content,
    build_view_vector_content,
    parse_event_time_range,
)


def test_parse_event_time_range_supports_year_month_day_formats() -> None:
    start, end = parse_event_time_range("2024年8月")
    assert start == datetime(2024, 8, 1, tzinfo=timezone.utc)
    assert end == datetime(2024, 8, 31, tzinfo=timezone.utc)

    day_start, day_end = parse_event_time_range("2024-08-15")
    assert day_start == datetime(2024, 8, 15, tzinfo=timezone.utc)
    assert day_end == datetime(2024, 8, 15, tzinfo=timezone.utc)


def test_build_entry_vector_content_flattens_payload_fields() -> None:
    row = SimpleNamespace(
        entry_key="relationship_spouse",
        canonical_text="用户的配偶是王敏",
        summary="配偶信息",
        details="来自明确陈述",
        predicate="spouse",
        object_text="王敏",
        event_time=None,
        location=None,
        topic="relationship",
        persons=["王敏"],
        entities=[],
        entry_data={"canonical_statement": "用户的配偶是王敏", "facts": ["配偶", "王敏"]},
    )

    content = build_entry_vector_content(row)

    assert "relationship_spouse" in content
    assert "用户的配偶是王敏" in content
    assert "王敏" in content


def test_build_view_vector_content_includes_view_payload() -> None:
    row = SimpleNamespace(
        view_key="profile:response_style",
        title="沟通偏好",
        content="偏好简洁回答",
        details="显式偏好",
        view_data={"key": "response_style", "value": "concise"},
    )

    content = build_view_vector_content(row)

    assert "沟通偏好" in content
    assert "偏好简洁回答" in content
    assert "response_style" in content
