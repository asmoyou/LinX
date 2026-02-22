from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_framework.base_agent import AgentConfig
from mission_system.agent_factory import create_mission_agent


@pytest.mark.asyncio
async def test_create_mission_agent_ollama_uses_provider_timeout_and_retries(monkeypatch):
    captured_llm_kwargs = {}

    class _FakeAgent:
        def __init__(self, config):
            self.config = config
            self.llm = None
            self.initialized = False

        async def initialize(self):
            self.initialized = True

    class _FakeLLM:
        def __init__(self, **kwargs):
            captured_llm_kwargs.update(kwargs)

    class _FakeSessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    provider = SimpleNamespace(
        enabled=True,
        protocol="ollama",
        base_url="http://localhost:11434",
        timeout=180,
        max_retries=5,
        model_metadata={"qwen2.5:14b": {"context_window": 32768}},
    )

    class _FakeProviderDBManager:
        def __init__(self, db):
            self.db = db

        def get_provider(self, provider_name):
            assert provider_name == "ollama"
            return provider

    monkeypatch.setattr("mission_system.agent_factory.BaseAgent", _FakeAgent)
    monkeypatch.setattr("mission_system.agent_factory.CustomOpenAIChat", _FakeLLM)
    monkeypatch.setattr("database.connection.get_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(
        "llm_providers.db_manager.ProviderDBManager",
        _FakeProviderDBManager,
    )

    cfg = AgentConfig(
        agent_id=uuid4(),
        name="test-agent",
        agent_type="test",
        owner_user_id=uuid4(),
        capabilities=[],
    )

    agent = await create_mission_agent(
        agent_config=cfg,
        llm_provider="ollama",
        llm_model="qwen2.5:14b",
        temperature=0.2,
        max_tokens=1024,
    )

    assert captured_llm_kwargs["timeout"] == 180
    assert captured_llm_kwargs["max_retries"] == 5
    assert captured_llm_kwargs["base_url"] == "http://localhost:11434"
    assert captured_llm_kwargs["model"] == "qwen2.5:14b"
    assert agent.initialized is True
    assert agent.config.context_window_tokens == 32768
