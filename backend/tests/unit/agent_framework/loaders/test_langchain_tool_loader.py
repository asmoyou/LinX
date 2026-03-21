from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.tools import Tool

from agent_framework.loaders.langchain_tool_loader import LangChainToolLoader


@pytest.mark.asyncio
async def test_inline_loader_uses_execution_user_with_owner_fallback(monkeypatch) -> None:
    execution_user_id = uuid4()
    skill_env_user_id = uuid4()
    skill_info = SimpleNamespace(
        skill_id=uuid4(),
        name="web-search",
    )
    captured: dict[str, object] = {}
    fake_skill_row = SimpleNamespace(skill_id=skill_info.skill_id)

    class _FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return fake_skill_row

    class _FakeSession:
        def query(self, *_args, **_kwargs):
            return _FakeQuery()

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    class _FakeExecutionEngine:
        def _get_or_create_tool(self, *, skill, user_id, fallback_user_id=None):
            captured["skill"] = skill
            captured["user_id"] = user_id
            captured["fallback_user_id"] = fallback_user_id
            return Tool(name="web_search", description="search", func=lambda _input="": "ok")

    monkeypatch.setattr("database.connection.get_db_session", _fake_db_session)
    monkeypatch.setattr(
        "skill_library.execution_engine.get_execution_engine",
        lambda: _FakeExecutionEngine(),
    )

    loader = LangChainToolLoader(
        agent_id=uuid4(),
        user_id=execution_user_id,
        skill_env_user_id=skill_env_user_id,
    )

    tool = await loader._load_from_inline_code(skill_info)

    assert tool is not None
    assert captured["skill"] is fake_skill_row
    assert captured["user_id"] == execution_user_id
    assert captured["fallback_user_id"] == skill_env_user_id
