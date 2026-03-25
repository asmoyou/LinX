from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_framework.base_agent import AgentConfig
from mission_system.agent_factory import create_mission_agent, create_registered_mission_agent


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


@pytest.mark.asyncio
async def test_create_registered_mission_agent_uses_actor_execution_access(monkeypatch):
    actor_user_id = uuid4()
    shared_agent_id = uuid4()
    captured = {}

    class _FakeQuery:
        def __init__(self, first_result):
            self._first_result = first_result

        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return self._first_result

    class _FakeSession:
        def __init__(self, user):
            self._user = user

        def query(self, _model):
            return _FakeQuery(self._user)

    class _FakeSessionContext:
        def __enter__(self):
            return _FakeSession(
                SimpleNamespace(
                    user_id=actor_user_id,
                    username="mission-owner",
                    role="user",
                )
            )

        def __exit__(self, exc_type, exc, tb):
            return False

    async def _fake_create_mission_agent(**kwargs):
        captured["agent_config"] = kwargs["agent_config"]
        captured["llm_provider"] = kwargs["llm_provider"]
        captured["llm_model"] = kwargs["llm_model"]
        captured["max_tokens"] = kwargs["max_tokens"]
        return SimpleNamespace(config=kwargs["agent_config"])

    def _fake_load_accessible_agent_or_raise(session, agent_id, current_user, *, access_type):
        captured["session"] = session
        captured["agent_id"] = agent_id
        captured["current_user"] = current_user
        captured["access_type"] = access_type
        return SimpleNamespace(
            agent_id=shared_agent_id,
            name="shared-agent",
            agent_type="research",
            capabilities=["analysis"],
            access_level="department",
            allowed_knowledge=["kb-1"],
            llm_provider="ollama",
            llm_model="qwen2.5:14b",
            temperature=0.3,
            max_tokens=2048,
            system_prompt="Be precise.",
        )

    monkeypatch.setattr(
        "mission_system.agent_factory.get_db_session", lambda: _FakeSessionContext()
    )
    monkeypatch.setattr(
        "mission_system.agent_factory.load_accessible_agent_or_raise",
        _fake_load_accessible_agent_or_raise,
    )
    monkeypatch.setattr(
        "mission_system.agent_factory.create_mission_agent",
        _fake_create_mission_agent,
    )

    agent = await create_registered_mission_agent(
        shared_agent_id,
        actor_user_id,
        max_iterations=9,
    )

    assert agent is not None
    assert captured["agent_id"] == str(shared_agent_id)
    assert captured["current_user"].user_id == str(actor_user_id)
    assert captured["access_type"] == "execute"
    assert captured["agent_config"].owner_user_id == actor_user_id
    assert captured["agent_config"].access_level == "department"
    assert captured["agent_config"].allowed_knowledge == ["kb-1"]
    assert captured["agent_config"].max_iterations == 9
    assert captured["max_tokens"] == 2048
