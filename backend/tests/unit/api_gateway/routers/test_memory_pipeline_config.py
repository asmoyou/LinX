from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

from access_control.permissions import CurrentUser
from api_gateway.routers.memory_contracts import MemoryConfigUpdateRequest
from api_gateway.routers.memory_pipeline_config import (
    _build_memory_config_payload,
    get_memory_config,
    maintain_materializations,
    update_memory_config,
)


def _config_payload(top_k: int) -> dict:
    return {
        "user_memory": {
            "embedding": {},
            "retrieval": {"top_k": top_k},
            "extraction": {},
            "consolidation": {},
            "observability": {},
            "retention": {},
        },
        "skill_learning": {
            "extraction": {},
            "proposal_review": {},
            "publish_policy": {},
            "retention": {},
        },
        "session_ledger": {},
        "runtime_context": {},
        "recommended": {},
    }


@pytest.fixture
def admin_user():
    return CurrentUser(
        user_id="admin-user-id",
        username="admin",
        role="admin",
        token_jti="token-jti",
    )


@pytest.fixture
def regular_user():
    return CurrentUser(
        user_id="user-id",
        username="user",
        role="user",
        token_jti="token-jti",
    )


def test_build_memory_config_payload_resolves_effective_sources():
    user_memory_section = {
        "retrieval": {"top_k": 7},
        "extraction": {"provider": "openai"},
    }
    skill_learning_section = {
        "extraction": {"provider": "openai", "max_proposals": 4},
    }
    kb_section = {"search": {"rerank_provider": "cohere", "rerank_model": "rerank-v3"}}
    llm_section = {
        "default_provider": "anthropic",
        "providers": {"openai": {"models": {"chat": "gpt-4.1-mini"}}},
    }

    with patch(
        "memory_system.embedding_service.resolve_embedding_settings",
        return_value={
            "provider": "openai",
            "model": "text-embedding-3-large",
            "dimension": 3072,
            "provider_source": "user_memory.embedding.provider",
            "model_source": "user_memory.embedding.model",
            "dimension_source": "user_memory.embedding.dimension",
        },
    ):
        payload = _build_memory_config_payload(
            user_memory_section,
            skill_learning_section,
            {},
            {},
            kb_section,
            llm_section,
        )

    assert payload["user_memory"]["retrieval"]["top_k"] == 7
    assert payload["user_memory"]["retrieval"]["rerank_provider"] == "cohere"
    assert payload["user_memory"]["extraction"]["effective"]["provider"] == "openai"
    assert payload["user_memory"]["extraction"]["effective"]["model"] == "gpt-4.1-mini"
    assert payload["user_memory"]["embedding"]["effective"]["model"] == "text-embedding-3-large"
    assert payload["skill_learning"]["extraction"]["max_proposals"] == 4


@pytest.mark.asyncio
async def test_get_memory_config_uses_reset_sections(admin_user):
    config = SimpleNamespace(
        get_section=lambda name: {
            "user_memory": {"retrieval": {"top_k": 4}},
            "skill_learning": {},
            "session_ledger": {},
            "runtime_context": {},
            "knowledge_base": {},
            "llm": {},
        }[name]
    )
    payload = _config_payload(4)

    with (
        patch("api_gateway.routers.memory_pipeline_config.get_config", return_value=config),
        patch(
            "api_gateway.routers.memory_pipeline_config._build_memory_config_payload",
            return_value=payload,
        ),
    ):
        result = await get_memory_config(current_user=admin_user)

    assert result.user_memory == {"embedding": {}, "retrieval": {"top_k": 4}, "extraction": {}, "consolidation": {}, "observability": {}, "retention": {}}


@pytest.mark.asyncio
async def test_update_memory_config_rejects_non_admin(regular_user):
    with pytest.raises(Exception) as exc:
        await update_memory_config(
            update_data=MemoryConfigUpdateRequest(user_memory={"retrieval": {"top_k": 12}}),
            current_user=regular_user,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_memory_config_writes_requested_sections(admin_user):
    update = MemoryConfigUpdateRequest(
        user_memory={
            "retrieval": {"top_k": 12},
            "consolidation": {"enabled": False},
        },
        runtime_context={"search_timeout_seconds": 5.5, "enable_skills": False},
        skill_learning={"publish_policy": {"enabled": False}},
    )
    reloaded = SimpleNamespace(
        get_section=lambda name: {
            "user_memory": {"retrieval": {"top_k": 12}},
            "skill_learning": {},
            "session_ledger": {},
            "runtime_context": {},
            "knowledge_base": {},
            "llm": {},
        }[name]
    )
    file_mock = mock_open(read_data="user_memory: {}\n")

    with (
        patch("builtins.open", file_mock),
        patch("yaml.safe_load", return_value={"user_memory": {}, "skill_learning": {}, "runtime_context": {}}),
        patch("yaml.dump") as yaml_dump,
        patch("shared.config.reload_config", return_value=reloaded),
        patch(
            "api_gateway.routers.memory_pipeline_config._build_memory_config_payload",
            return_value=_config_payload(12),
        ),
    ):
        result = await update_memory_config(update_data=update, current_user=admin_user)

    dumped_config = yaml_dump.call_args.args[0]
    assert dumped_config["user_memory"]["retrieval"]["top_k"] == 12
    assert dumped_config["user_memory"]["consolidation"]["enabled"] is False
    assert dumped_config["runtime_context"]["search_timeout_seconds"] == 5.5
    assert dumped_config["runtime_context"]["enable_skills"] is False
    assert dumped_config["skill_learning"]["publish_policy"]["enabled"] is False
    assert result.user_memory["retrieval"] == {"top_k": 12}


@pytest.mark.asyncio
async def test_maintain_materializations_rejects_non_admin(regular_user):
    with pytest.raises(Exception) as exc:
        await maintain_materializations(
            dry_run=True,
            user_id=None,
            agent_id=None,
            limit=None,
            current_user=regular_user,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_maintain_materializations_delegates_to_service(admin_user):
    service = MagicMock()
    service.run_maintenance.return_value = SimpleNamespace()
    service.to_dict.return_value = {
        "consolidation": {"dry_run": True},
    }

    with patch(
        "user_memory.materialization_maintenance_service.get_materialization_maintenance_service",
        return_value=service,
    ):
        result = await maintain_materializations(
            dry_run=True,
            user_id="user-1",
            agent_id="agent-1",
            limit=50,
            current_user=admin_user,
        )

    assert service.run_maintenance.call_args.kwargs == {
        "dry_run": True,
        "user_id": "user-1",
        "agent_id": "agent-1",
        "limit": 50,
    }
    assert result.requested_by == {
        "user_id": str(admin_user.user_id),
        "role": str(admin_user.role),
    }
