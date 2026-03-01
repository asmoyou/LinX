"""Unit tests for code block executor sandbox fallback policy."""

from pathlib import Path

import pytest

from agent_framework.code_block_executor import CodeBlock, CodeBlockExecutor


@pytest.mark.asyncio
async def test_execute_rejects_host_mode_when_fallback_disabled(tmp_path: Path):
    executor = CodeBlockExecutor(base_workdir=str(tmp_path), allow_host_fallback=False)
    block = CodeBlock(language="python", code="print('hello')", filename="a.py")

    result = await executor.execute(block, workdir=tmp_path, container_id=None)

    assert result.success is False
    assert "disabled" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_container_exec_rejects_subprocess_fallback_when_disabled(tmp_path: Path):
    executor = CodeBlockExecutor(base_workdir=str(tmp_path), allow_host_fallback=False)
    script_path = tmp_path / "script.py"
    script_path.write_text("print('x')", encoding="utf-8")

    class FakeContainerManager:
        docker_available = False

    executor._container_manager = FakeContainerManager()

    result = await executor._execute_in_container(
        container_id="sandbox-1",
        language="python",
        script_path=script_path,
        env=None,
        timeout=5,
        workdir=tmp_path,
    )

    assert result.success is False
    assert "disabled" in (result.error or "").lower()
