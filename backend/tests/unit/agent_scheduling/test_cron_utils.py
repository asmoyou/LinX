from datetime import datetime, timezone

import pytest

from agent_scheduling.cron_utils import (
    ScheduleValidationError,
    compute_next_run_at,
    normalize_cron_expression,
    parse_run_at,
    preview_schedule,
)


def test_parse_run_at_uses_timezone_for_naive_datetime() -> None:
    parsed = parse_run_at("2025-01-10T09:30", "Asia/Shanghai")

    assert parsed.isoformat() == "2025-01-10T01:30:00+00:00"


def test_preview_schedule_recurring_returns_summary_and_occurrences() -> None:
    preview = preview_schedule(
        schedule_type="recurring",
        timezone_name="UTC",
        cron_expression="0 9 * * 1-5",
        now=datetime(2025, 1, 1, 8, 0, tzinfo=timezone.utc),
    )

    assert preview.is_valid is True
    assert preview.normalized_cron == "0 9 * * 1-5"
    assert preview.human_summary == "Every weekday at 09:00 (UTC)"
    assert preview.next_occurrences[0] == "2025-01-01T09:00:00+00:00"


def test_compute_next_run_at_for_once_returns_supplied_time() -> None:
    run_at = datetime(2025, 3, 2, 12, 30, tzinfo=timezone.utc)

    result = compute_next_run_at(
        schedule_type="once",
        timezone_name="UTC",
        run_at_utc=run_at,
    )

    assert result == run_at


def test_normalize_cron_expression_rejects_invalid_field_count() -> None:
    with pytest.raises(ScheduleValidationError, match="exactly 5 fields"):
        normalize_cron_expression("0 9 * *")
