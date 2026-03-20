"""Tests for the agent-driven manage_schedule tool."""

from uuid import uuid4

import agent_framework.tools.manage_schedule_tool as manage_schedule_module
from agent_framework.tools.manage_schedule_tool import (
    ScheduleToolContext,
    clear_schedule_tool_context,
    create_manage_schedule_tool,
    set_schedule_tool_context,
)


def _set_default_context() -> None:
    set_schedule_tool_context(
        ScheduleToolContext(
            owner_user_id=str(uuid4()),
            owner_role="admin",
            agent_id=str(uuid4()),
            origin_surface="persistent_chat",
            bound_conversation_id=str(uuid4()),
        )
    )


def test_manage_schedule_tool_uses_structured_args_for_create(monkeypatch) -> None:
    captured: dict = {}

    def _fake_create_schedule(**kwargs):
        captured.update(kwargs)
        return {
            "id": "schedule-1",
            "agentId": kwargs["agent_id"],
            "boundConversationId": kwargs["bound_conversation_id"],
            "name": kwargs["name"],
            "status": "active",
            "nextRunAt": "2026-03-20T00:00:00+00:00",
            "timezone": kwargs["timezone"] or "UTC",
            "createdVia": kwargs["created_via"],
            "boundConversationTitle": "提醒对话",
            "originSurface": kwargs["origin_surface"],
        }

    monkeypatch.setattr(manage_schedule_module, "create_schedule", _fake_create_schedule)

    tool = create_manage_schedule_tool(uuid4(), uuid4())
    _set_default_context()
    try:
        result = tool.invoke(
            {
                "name": "日报提醒",
                "prompt_template": "提醒我写日报",
                "schedule_type": "once",
                "run_at": "2026-03-20T08:00:00+08:00",
                "timezone": "Asia/Shanghai",
            }
        )
    finally:
        clear_schedule_tool_context()

    assert "Schedule created successfully" in result
    assert captured["created_via"] == "agent_auto"
    assert captured["origin_surface"] == "persistent_chat"
    assert captured["schedule_type"] == "once"
    assert captured["name"] == "日报提醒"


def test_manage_schedule_tool_defaults_action_to_create(monkeypatch) -> None:
    monkeypatch.setattr(
        manage_schedule_module,
        "create_schedule",
        lambda **kwargs: {
            "id": "schedule-2",
            "agentId": kwargs["agent_id"],
            "boundConversationId": kwargs["bound_conversation_id"],
            "name": kwargs["name"],
            "status": "active",
            "nextRunAt": "2026-03-20T00:00:00+00:00",
            "timezone": kwargs["timezone"] or "UTC",
            "createdVia": kwargs["created_via"],
            "boundConversationTitle": "提醒对话",
            "originSurface": kwargs["origin_surface"],
        },
    )

    tool = create_manage_schedule_tool(uuid4(), uuid4())
    _set_default_context()
    try:
        result = tool.invoke(
            {
                "action": "",
                "name": "日报提醒",
                "prompt_template": "提醒我写日报",
                "schedule_type": "once",
                "run_at": "2026-03-20T08:00:00+08:00",
                "timezone": "Asia/Shanghai",
            }
        )
    finally:
        clear_schedule_tool_context()

    assert "Schedule created successfully" in result


def test_manage_schedule_tool_updates_schedule_by_id(monkeypatch) -> None:
    captured: dict = {}

    monkeypatch.setattr(
        manage_schedule_module,
        "get_schedule_detail",
        lambda **kwargs: {
            "id": kwargs["schedule_id"],
            "name": "日报提醒",
            "status": "active",
            "scheduleType": "recurring",
            "timezone": "Asia/Shanghai",
            "nextRunAt": "2026-03-20T01:00:00+00:00",
            "runAtUtc": None,
            "promptTemplate": "提醒我写日报",
            "boundConversationTitle": "提醒对话",
        },
    )

    def _fake_update_schedule(**kwargs):
        captured.update(kwargs)
        return {
            "id": kwargs["schedule_id"],
            "name": kwargs["name"],
            "status": "active",
            "scheduleType": "once",
            "timezone": kwargs["timezone"] or "Asia/Shanghai",
            "nextRunAt": "2026-03-21T00:00:00+00:00",
            "runAtUtc": "2026-03-21T00:00:00+00:00",
        }

    monkeypatch.setattr(manage_schedule_module, "update_schedule", _fake_update_schedule)

    tool = create_manage_schedule_tool(uuid4(), uuid4())
    _set_default_context()
    try:
        result = tool.invoke(
            {
                "action": "update",
                "schedule_id": "schedule-3",
                "name": "新的提醒",
                "schedule_type": "once",
                "run_at": "2026-03-21T08:00:00+08:00",
                "timezone": "Asia/Shanghai",
            }
        )
    finally:
        clear_schedule_tool_context()

    assert "Schedule updated successfully" in result
    assert captured["schedule_id"] == "schedule-3"
    assert captured["name"] == "新的提醒"
    assert captured["schedule_type"] == "once"


def test_manage_schedule_tool_deletes_resolved_schedule_by_name(monkeypatch) -> None:
    deleted: dict = {}

    monkeypatch.setattr(
        manage_schedule_module,
        "list_schedules",
        lambda **kwargs: (
            [
                {
                    "id": "schedule-9",
                    "name": "打开anyrouter打卡",
                    "status": "active",
                    "scheduleType": "once",
                    "timezone": "Asia/Shanghai",
                    "nextRunAt": "2026-03-20T00:00:00+00:00",
                    "runAtUtc": "2026-03-20T00:00:00+00:00",
                    "promptTemplate": "提醒我打开anyrouter打卡",
                    "boundConversationId": kwargs["agent_id"],
                    "boundConversationTitle": "提醒对话",
                }
            ],
            1,
        ),
    )

    monkeypatch.setattr(
        manage_schedule_module,
        "delete_schedule",
        lambda **kwargs: deleted.update(kwargs),
    )

    tool = create_manage_schedule_tool(uuid4(), uuid4())
    context = ScheduleToolContext(
        owner_user_id=str(uuid4()),
        owner_role="admin",
        agent_id=str(uuid4()),
        origin_surface="persistent_chat",
        bound_conversation_id=None,
    )
    set_schedule_tool_context(context)
    try:
        result = tool.invoke(
            {
                "action": "delete",
                "target_name": "打开 anyrouter 打卡",
            }
        )
    finally:
        clear_schedule_tool_context()

    assert "Schedule deleted successfully" in result
    assert deleted["schedule_id"] == "schedule-9"
    assert deleted["viewer_user_id"] == context.owner_user_id


def test_manage_schedule_tool_lists_schedules_for_current_agent(monkeypatch) -> None:
    captured: dict = {}

    def _fake_list_schedules(**kwargs):
        captured.update(kwargs)
        return (
            [
                {
                    "id": "schedule-11",
                    "name": "日报提醒",
                    "status": "active",
                    "scheduleType": "recurring",
                    "timezone": "Asia/Shanghai",
                    "nextRunAt": "2026-03-20T01:00:00+00:00",
                    "runAtUtc": None,
                    "promptTemplate": "提醒我写日报",
                    "boundConversationId": "conversation-1",
                    "boundConversationTitle": "提醒对话",
                }
            ],
            1,
        )

    monkeypatch.setattr(manage_schedule_module, "list_schedules", _fake_list_schedules)

    tool = create_manage_schedule_tool(uuid4(), uuid4())
    context = ScheduleToolContext(
        owner_user_id=str(uuid4()),
        owner_role="admin",
        agent_id=str(uuid4()),
        origin_surface="persistent_chat",
        bound_conversation_id=None,
    )
    set_schedule_tool_context(context)
    try:
        result = tool.invoke({"action": "list", "limit": 5})
    finally:
        clear_schedule_tool_context()

    assert "Found 1 schedule(s)" in result
    assert "日报提醒" in result
    assert captured["agent_id"] == context.agent_id
    assert captured["viewer_user_id"] == context.owner_user_id
