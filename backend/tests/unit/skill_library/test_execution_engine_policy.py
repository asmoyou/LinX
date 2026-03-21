"""Tests for execution-engine host dependency installation policy."""

from __future__ import annotations

import builtins
import subprocess
from uuid import uuid4

import pytest

from skill_library.execution_engine import SkillExecutionEngine


def _patch_import_to_fail_for(monkeypatch: pytest.MonkeyPatch, missing_module: str) -> None:
    """Force ImportError for a specific module while delegating all other imports."""
    original_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == missing_module:
            raise ImportError(f"No module named {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)


def test_dependency_import_name_uses_override_for_tavily_python() -> None:
    engine = SkillExecutionEngine()

    assert engine._dependency_import_name("tavily-python") == "tavily"
    assert engine._dependency_import_name("python-dotenv") == "dotenv"
    assert engine._dependency_import_name("plain-package") == "plain_package"


def test_dependency_import_candidates_can_infer_from_code_imports() -> None:
    engine = SkillExecutionEngine()
    code = """
from tavily import TavilyClient
from langchain_core.tools import tool
"""

    candidates = engine._dependency_import_candidates("tavily-python", code=code)

    assert candidates[0] == "tavily"
    assert "tavily" in candidates


def test_host_dependency_install_blocked_when_fallback_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LINX_ENFORCE_SANDBOX_ISOLATION", "1")
    monkeypatch.setenv("LINX_ALLOW_HOST_EXECUTION_FALLBACK", "0")

    missing_dep = "definitely_missing_pkg_for_policy_test"
    _patch_import_to_fail_for(monkeypatch, missing_dep)

    engine = SkillExecutionEngine()

    with pytest.raises(ValueError, match="disabled by sandbox isolation policy"):
        engine._ensure_dependencies_installed([missing_dep])


def test_host_dependency_install_allowed_when_fallback_enabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LINX_ENFORCE_SANDBOX_ISOLATION", "1")
    monkeypatch.setenv("LINX_ALLOW_HOST_EXECUTION_FALLBACK", "1")

    missing_dep = "definitely_missing_pkg_for_policy_test"
    _patch_import_to_fail_for(monkeypatch, missing_dep)

    calls: list[tuple[list[str], object, object]] = []

    def _fake_check_call(cmd, stdout=None, stderr=None):
        calls.append((cmd, stdout, stderr))
        return 0

    monkeypatch.setattr(subprocess, "check_call", _fake_check_call)

    engine = SkillExecutionEngine()
    engine._ensure_dependencies_installed([missing_dep])

    assert len(calls) == 1
    cmd, stdout_target, stderr_target = calls[0]
    assert cmd[1:4] == ["-m", "pip", "install"]
    assert "python" in cmd[0]
    assert cmd[4] == missing_dep
    assert stdout_target is subprocess.DEVNULL
    assert stderr_target is subprocess.PIPE


def test_create_tool_from_code_prefers_primary_env_and_backfills_from_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    engine = SkillExecutionEngine()
    primary_user_id = uuid4()
    fallback_user_id = uuid4()
    code = """
import os
from langchain_core.tools import tool

PRIMARY_ONLY = os.getenv("PRIMARY_ONLY", "")
FALLBACK_ONLY = os.getenv("FALLBACK_ONLY", "")
SHARED = os.getenv("SHARED", "")

@tool
def show_env() -> str:
    \"\"\"Return selected environment variables for verification.\"\"\"
    return "|".join([
        PRIMARY_ONLY,
        FALLBACK_ONLY,
        SHARED,
    ])
"""

    class _FakeEnvManager:
        def get_env_for_user_with_fallback(self, *, user_id, fallback_user_id=None):
            assert user_id == primary_user_id
            assert fallback_user_id == fallback_user_id_ref
            return {
                "PRIMARY_ONLY": "user-key",
                "FALLBACK_ONLY": "owner-key",
                "SHARED": "user-wins",
            }

    fallback_user_id_ref = fallback_user_id
    monkeypatch.setattr(
        "skill_library.skill_env_manager.get_skill_env_manager",
        lambda: _FakeEnvManager(),
    )

    tool = engine._create_tool_from_code(
        code=code,
        skill_name="show_env",
        user_id=primary_user_id,
        fallback_user_id=fallback_user_id,
    )

    assert tool.invoke({}) == "user-key|owner-key|user-wins"
