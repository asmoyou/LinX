"""Tests for mission deliverable helper behavior."""

from datetime import datetime, timedelta
from types import SimpleNamespace

from api_gateway.routers.missions import (
    _build_content_disposition,
    _compute_clarification_state,
    _derive_initial_mission_title,
    _normalize_deliverable_item,
)
from shared.datetime_utils import utcnow


def test_build_content_disposition_encodes_unicode_filename() -> None:
    header = _build_content_disposition("output/福州古诗.docx", disposition="attachment")

    assert header.startswith("attachment;")
    assert "filename*=UTF-8''" in header
    # Header bytes must remain ASCII-safe for HTTP transport.
    assert all(ord(ch) < 128 for ch in header)


def test_normalize_deliverable_item_demotes_runtime_script() -> None:
    item = {
        "filename": "code_ab12cd34.py",
        "path": "artifacts/demo/code_ab12cd34.py",
        "is_target": True,
        "source_scope": "output",
        "artifact_kind": "final",
    }

    normalized = _normalize_deliverable_item(item)

    assert normalized is not None
    assert normalized["is_target"] is False
    assert normalized["artifact_kind"] == "intermediate"
    assert normalized["source_scope"] == "shared"


def test_normalize_deliverable_item_keeps_real_output_as_final() -> None:
    item = {
        "filename": "output/final_report.docx",
        "path": "artifacts/demo/final_report.docx",
        "is_target": True,
        "source_scope": "output",
        "artifact_kind": "final",
    }

    normalized = _normalize_deliverable_item(item)

    assert normalized is not None
    assert normalized["is_target"] is True
    assert normalized["artifact_kind"] == "final"
    assert normalized["source_scope"] == "output"


def test_compute_clarification_state_marks_pending_when_request_unanswered() -> None:
    now = utcnow()
    events = [
        SimpleNamespace(
            event_type="USER_CLARIFICATION_REQUESTED",
            created_at=now,
            event_data={"questions": "请确认目标人群"},
            message="Leader requests clarification",
        )
    ]

    state = _compute_clarification_state(events, boundary_ts=None)

    assert state["needs_clarification"] is True
    assert state["pending_clarification_count"] == 1
    assert "目标人群" in (state["latest_clarification_request"] or "")


def test_compute_clarification_state_ignores_events_before_boundary() -> None:
    now = utcnow()
    events = [
        SimpleNamespace(
            event_type="USER_CLARIFICATION_REQUESTED",
            created_at=now - timedelta(minutes=10),
            event_data={"questions": "old question"},
            message="old question",
        ),
        SimpleNamespace(
            event_type="USER_CLARIFICATION_REQUESTED",
            created_at=now - timedelta(minutes=1),
            event_data={"questions": "new question"},
            message="new question",
        ),
    ]

    state = _compute_clarification_state(events, boundary_ts=now - timedelta(minutes=5))

    assert state["needs_clarification"] is True
    assert state["pending_clarification_count"] == 1
    assert state["latest_clarification_request"] == "new question"


def test_derive_initial_mission_title_trims_leading_request_prefix_for_chinese() -> None:
    title = _derive_initial_mission_title(
        "请帮我设计一个覆盖采购、库存、发货链路的自动化运营看板，并输出执行方案。"
    )

    assert not title.startswith("请帮我")
    assert len(title) <= 24


def test_derive_initial_mission_title_caps_english_title_length() -> None:
    title = _derive_initial_mission_title(
        "Build a multi-tenant observability dashboard with per-team alert routing, "
        "SLO burn-rate analysis, and audit-ready incident timelines."
    )

    assert len(title) <= 70
