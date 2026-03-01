"""Unit tests for code_execution tool language support metadata."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_framework.tools.code_execution_tool import CodeExecutionInput, CodeExecutionTool


def test_code_execution_input_language_description_mentions_js_ts() -> None:
    field_info = CodeExecutionInput.model_fields["language"]
    description = str(field_info.description or "")

    assert "javascript" in description
    assert "typescript" in description
    assert "bash" not in description


def test_code_execution_tool_description_mentions_supported_languages() -> None:
    description = str(CodeExecutionTool.model_fields["description"].default or "").lower()

    assert "python/javascript/typescript" in description
    assert "for shell commands, use the dedicated `bash` tool" in description
    assert "node.js" in description
    assert "ts-node" in description


@pytest.mark.asyncio
async def test_code_execution_tool_normalizes_node_alias_before_sandbox_call(monkeypatch) -> None:
    captured = {}

    class _FakeSandbox:
        async def execute_code(self, *, code, language, context):
            captured["code"] = code
            captured["language"] = language
            captured["context"] = context
            return SimpleNamespace(success=True, output="ok", error="")

    monkeypatch.setattr(
        "skill_library.skill_env_manager.get_skill_env_manager",
        lambda: SimpleNamespace(get_env_for_user=lambda _user_id: {}),
    )
    monkeypatch.setattr(
        "agent_framework.tools.file_tools.get_workspace_root",
        lambda: None,
    )

    tool = CodeExecutionTool(agent_id=uuid4(), user_id=uuid4())
    object.__setattr__(tool, "_sandbox", _FakeSandbox())

    output = await tool._execute_code("console.log('ok')", "node")

    assert captured["language"] == "javascript"
    assert "Code executed successfully" in output


@pytest.mark.asyncio
async def test_code_execution_tool_rejects_shell_language() -> None:
    tool = CodeExecutionTool(agent_id=uuid4(), user_id=uuid4())

    output = await tool._execute_code("echo hello", "bash")

    assert "Unsupported language for code_execution" in output
    assert "use the bash tool" in output
