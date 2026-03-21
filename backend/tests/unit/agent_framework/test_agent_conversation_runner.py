from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_framework import agent_conversation_runner


@pytest.mark.asyncio
async def test_initialize_chat_agent_applies_resolved_context_window(monkeypatch) -> None:
    fake_llm = object()

    def fake_build_llm_and_context(_agent_info, **_kwargs):
        return fake_llm, 262144

    async def fake_initialize(self) -> None:
        return None

    monkeypatch.setattr(
        agent_conversation_runner,
        "_build_llm_and_context_for_agent",
        fake_build_llm_and_context,
    )
    monkeypatch.setattr(agent_conversation_runner.BaseAgent, "initialize", fake_initialize)

    agent_info = SimpleNamespace(
        agent_id=uuid4(),
        name="Persistent Agent",
        agent_type="assistant",
        owner_user_id=uuid4(),
        capabilities=["search"],
        access_level="private",
        allowed_knowledge=[],
        llm_model="demo-256k",
        temperature=0.2,
        system_prompt="Be useful.",
    )

    agent = await agent_conversation_runner.initialize_chat_agent(
        agent_info=agent_info,
        owner_user_id=uuid4(),
    )

    assert agent.llm is fake_llm
    assert agent.config.context_window_tokens == 262144


@pytest.mark.asyncio
async def test_initialize_chat_agent_prefers_agent_owner_for_skill_env(monkeypatch) -> None:
    fake_llm = object()

    def fake_build_llm_and_context(_agent_info, **_kwargs):
        return fake_llm, 8192

    async def fake_initialize(self) -> None:
        return None

    monkeypatch.setattr(
        agent_conversation_runner,
        "_build_llm_and_context_for_agent",
        fake_build_llm_and_context,
    )
    monkeypatch.setattr(agent_conversation_runner.BaseAgent, "initialize", fake_initialize)

    agent_owner_id = uuid4()
    execution_user_id = uuid4()
    agent_info = SimpleNamespace(
        agent_id=uuid4(),
        name="Shared Agent",
        agent_type="assistant",
        owner_user_id=agent_owner_id,
        capabilities=["search"],
        access_level="public",
        allowed_knowledge=[],
        llm_model="demo-32k",
        temperature=0.2,
        system_prompt="Be useful.",
    )

    agent = await agent_conversation_runner.initialize_chat_agent(
        agent_info=agent_info,
        owner_user_id=execution_user_id,
    )

    assert agent.config.owner_user_id == execution_user_id
    assert agent.config.skill_env_user_id == agent_owner_id
