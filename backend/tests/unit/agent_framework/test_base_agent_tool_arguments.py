"""Regression tests for BaseAgent tool argument normalization."""

import json
from uuid import uuid4

from agent_framework.base_agent import BaseAgent
from agent_framework.tools.manage_schedule_tool import create_manage_schedule_tool


def test_normalize_tool_arguments_decodes_structured_positional_payload() -> None:
    agent = BaseAgent.__new__(BaseAgent)
    tool = create_manage_schedule_tool(uuid4(), uuid4())
    payload = {
        "name": "日报提醒",
        "prompt_template": "提醒我写日报",
        "schedule_type": "once",
        "run_at": "2026-03-20T08:00:00+08:00",
        "timezone": "Asia/Shanghai",
    }

    normalized = agent._normalize_tool_arguments_for_execution(
        "manage_schedule",
        tool,
        {"__arg1": json.dumps(payload, ensure_ascii=False)},
    )

    assert normalized == payload
