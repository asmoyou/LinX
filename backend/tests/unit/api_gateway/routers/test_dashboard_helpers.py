"""Tests for dashboard helper behavior."""

from datetime import datetime, timezone

from api_gateway.routers.dashboard import (
    _build_event_message,
    _classify_event_type,
    _format_utc_iso,
)


def test_classify_event_type_maps_failed_to_error() -> None:
    assert _classify_event_type("MISSION_FAILED") == "error"


def test_classify_event_type_maps_completed_to_success() -> None:
    assert _classify_event_type("TASK_COMPLETED") == "success"


def test_classify_event_type_defaults_to_info() -> None:
    assert _classify_event_type("PHASE_STARTED") == "info"


def test_build_event_message_prefers_explicit_message() -> None:
    assert (
        _build_event_message(
            event_type="TASK_COMPLETED",
            message="Task finished successfully",
            mission_title="Quarterly report",
        )
        == "Task finished successfully"
    )


def test_build_event_message_falls_back_to_mission_and_event_label() -> None:
    assert (
        _build_event_message(
            event_type="MISSION_COMPLETED",
            message=None,
            mission_title="Quarterly report",
        )
        == "Quarterly report: Mission completed"
    )


def test_format_utc_iso_normalizes_timezone() -> None:
    value = datetime(2026, 2, 23, 9, 30, tzinfo=timezone.utc)
    assert _format_utc_iso(value) == "2026-02-23T09:30:00Z"
