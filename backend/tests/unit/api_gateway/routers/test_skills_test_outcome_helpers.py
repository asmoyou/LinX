"""Tests for agent-skill test outcome normalization helpers."""

from api_gateway.routers.skills import (
    _extract_tool_call_status,
    _normalize_agent_skill_test_outcome,
    _serialize_tool_calls_for_response,
)


class _ToolCallObject:
    def __init__(self, status: str):
        self.status = status


def test_extract_tool_call_status_supports_dict_and_object() -> None:
    assert _extract_tool_call_status({"status": "success"}) == "success"
    assert _extract_tool_call_status(_ToolCallObject("error")) == "error"


def test_normalize_outcome_marks_semantic_failure_without_successful_tool_calls() -> None:
    result = {
        "success": True,
        "output": (
            "看起来当前环境无法访问 .skills/weather-check/scripts/ 路径，"
            "由于无法定位或执行该技能脚本，我无法完成请求。"
        ),
        "tool_calls": [],
    }

    normalized = _normalize_agent_skill_test_outcome(result)

    assert normalized["effective_success"] is False
    assert normalized["semantic_failure"] is True
    assert "无法" in (normalized["effective_error"] or "")


def test_normalize_outcome_keeps_success_when_tool_execution_succeeds() -> None:
    result = {
        "success": True,
        "output": "Tianjin weather: 3°C, clear.",
        "tool_calls": [{"status": "success"}],
    }

    normalized = _normalize_agent_skill_test_outcome(result)

    assert normalized["effective_success"] is True
    assert normalized["semantic_failure"] is False
    assert normalized["effective_error"] is None


def test_serialize_tool_calls_for_response_contains_key_fields() -> None:
    tool_calls = [
        {
            "tool_name": "read_skill",
            "status": "success",
            "round_number": 1,
            "arguments": {"skill_name": "weather-check"},
            "result": {"ok": True},
        },
        _ToolCallObject("execution_error"),
    ]

    serialized = _serialize_tool_calls_for_response(tool_calls)

    assert len(serialized) == 2
    assert serialized[0]["tool_name"] == "read_skill"
    assert serialized[0]["status"] == "success"
    assert serialized[0]["round_number"] == 1
    assert "ok" in serialized[0]["result_preview"]
    assert serialized[1]["status"] == "execution_error"
