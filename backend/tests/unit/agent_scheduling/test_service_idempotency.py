from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from agent_scheduling.service import (
    _is_same_agent_auto_schedule_request,
    _schedule_idempotency_fingerprint,
)


def test_schedule_idempotency_fingerprint_ignores_whitespace() -> None:
    assert _schedule_idempotency_fingerprint("打开 anyrouter 打卡") == _schedule_idempotency_fingerprint(
        "打开anyrouter打卡"
    )


def test_agent_auto_dedupe_matches_same_once_schedule_with_spacing_variants() -> None:
    bound_conversation_id = uuid4()
    run_at_utc = datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc)
    existing = SimpleNamespace(
        bound_conversation_id=bound_conversation_id,
        schedule_type="once",
        timezone="Asia/Shanghai",
        run_at_utc=run_at_utc,
        cron_expression=None,
        name="打开anyrouter打卡",
        prompt_template="提醒我打开anyrouter打卡",
    )

    assert (
        _is_same_agent_auto_schedule_request(
            existing,
            bound_conversation_id=bound_conversation_id,
            name="打开 anyrouter 打卡",
            prompt_template="提醒我打开 anyrouter 打卡",
            schedule_type="once",
            cron_expression=None,
            run_at_utc=run_at_utc,
            timezone_name="Asia/Shanghai",
        )
        is True
    )


def test_agent_auto_dedupe_rejects_different_schedule_time() -> None:
    bound_conversation_id = uuid4()
    existing = SimpleNamespace(
        bound_conversation_id=bound_conversation_id,
        schedule_type="once",
        timezone="Asia/Shanghai",
        run_at_utc=datetime(2026, 3, 20, 0, 0, tzinfo=timezone.utc),
        cron_expression=None,
        name="打开anyrouter打卡",
        prompt_template="提醒我打开anyrouter打卡",
    )

    assert (
        _is_same_agent_auto_schedule_request(
            existing,
            bound_conversation_id=bound_conversation_id,
            name="打开 anyrouter 打卡",
            prompt_template="提醒我打开 anyrouter 打卡",
            schedule_type="once",
            cron_expression=None,
            run_at_utc=datetime(2026, 3, 20, 1, 0, tzinfo=timezone.utc),
            timezone_name="Asia/Shanghai",
        )
        is False
    )
