from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api_gateway.routers.agents import (
    CreateAgentRequest,
    UpdateAgentRequest,
    _resolve_model_max_output_tokens,
    _validate_agent_max_tokens,
)


def test_create_agent_request_allows_large_max_tokens() -> None:
    request = CreateAgentRequest(
        name="Large Token Agent",
        type="assistant",
        provider="openai",
        model="qwen-plus",
        maxTokens=81920,
    )

    assert request.maxTokens == 81920


def test_update_agent_request_allows_large_max_tokens() -> None:
    request = UpdateAgentRequest(maxTokens=81920)

    assert request.maxTokens == 81920


def test_resolve_model_max_output_tokens_prefers_provider_metadata() -> None:
    provider = SimpleNamespace(
        model_metadata={
            "qwen-plus": {
                "max_output_tokens": 81920,
            }
        }
    )

    resolved = _resolve_model_max_output_tokens(provider, "openai", "qwen-plus")

    assert resolved == 81920


def test_validate_agent_max_tokens_rejects_values_above_model_limit(monkeypatch) -> None:
    class _FakeSessionContext:
        def __enter__(self):
            return object()

        def __exit__(self, exc_type, exc, tb):
            return False

    provider = SimpleNamespace(
        model_metadata={"qwen-plus": {"max_output_tokens": 81920}},
    )

    class _FakeProviderDBManager:
        def __init__(self, db):
            self.db = db

        def get_provider(self, provider_name):
            assert provider_name == "openai"
            return provider

    monkeypatch.setattr("api_gateway.routers.agents.get_db_session", lambda: _FakeSessionContext())
    monkeypatch.setattr(
        "llm_providers.db_manager.ProviderDBManager",
        _FakeProviderDBManager,
    )

    with pytest.raises(HTTPException) as exc_info:
        _validate_agent_max_tokens(
            provider_name="openai",
            model_name="qwen-plus",
            max_tokens=90000,
        )

    assert exc_info.value.status_code == 422
    assert "81920" in str(exc_info.value.detail)
