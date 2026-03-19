from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

from access_control.permissions import CurrentUser
from api_gateway.routers.memory_contracts import MemoryConfigUpdateRequest
from api_gateway.routers.memory_pipeline_config import (
    _build_memory_config_payload,
    get_memory_config,
    update_memory_config,
)


def _config_payload(similarity_threshold: float) -> dict:
    return {
        "user_memory": {
            "embedding": {},
            "retrieval": {"similarity_threshold": similarity_threshold},
            "extraction": {},
            "consolidation": {
                "enabled": True,
                "run_on_startup": True,
                "startup_delay_seconds": 180,
                "interval_seconds": 21600,
                "dry_run": False,
                "limit": 5000,
                "use_advisory_lock": True,
            },
            "observability": {},
        },
        "skill_candidates": {
            "extraction": {
                "enabled": True,
                "max_candidates": 6,
            },
        },
        "skill_runtime": {
            "retrieval": {
                "enabled": True,
                "top_k": 5,
                "min_similarity": 0.45,
            },
            "auto_bind_source_agent": True,
        },
        "session_ledger": {},
        "runtime_context": {
            "enable_user_memory": True,
            "enable_skills": True,
            "enable_knowledge_base": True,
        },
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
        "retrieval": {
            "similarity_threshold": 0.55,
            "legacy_fallback_enabled": True,
            "rerank_provider": "legacy-provider",
            "rerank_model": "legacy-model",
        },
        "extraction": {"provider": "openai"},
    }
    skill_candidates_section = {
        "extraction": {"provider": "openai", "max_candidates": 4},
    }
    llm_section = {
        "default_provider": "anthropic",
        "providers": {"openai": {"models": {"chat": "gpt-4.1-mini"}}},
    }

    with (
        patch(
            "memory_system.embedding_service.resolve_embedding_settings",
            return_value={
                "provider": "openai",
                "model": "text-embedding-3-large",
                "dimension": 3072,
                "provider_source": "user_memory.embedding.provider",
                "model_source": "user_memory.embedding.model",
                "dimension_source": "user_memory.embedding.dimension",
            },
        ),
        patch(
            "user_memory.vector_index.get_user_memory_vector_index_state",
            return_value={
                "active_collection": "user_memory_embeddings_v2_deadbeef",
                "active_signature": "sig",
                "build_state": "ready",
            },
        ),
        patch(
            "user_memory.vector_index.user_memory_vector_reindex_required",
            return_value=False,
        ),
    ):
        payload = _build_memory_config_payload(
            user_memory_section,
            skill_candidates_section,
            {},
            {},
            {},
            {},
            llm_section,
        )

    assert payload["user_memory"]["retrieval"]["similarity_threshold"] == 0.55
    assert payload["user_memory"]["retrieval"]["rerank"]["provider"] == "legacy-provider"
    assert payload["user_memory"]["retrieval"]["rerank"]["model"] == "legacy-model"
    assert "legacy_fallback_enabled" not in payload["user_memory"]["retrieval"]
    assert payload["user_memory"]["extraction"]["effective"]["provider"] == "openai"
    assert payload["user_memory"]["extraction"]["effective"]["model"] == "gpt-4.1-mini"
    assert payload["user_memory"]["embedding"]["effective"]["model"] == "text-embedding-3-large"
    assert (
        payload["user_memory"]["indexState"]["activeCollection"]
        == "user_memory_embeddings_v2_deadbeef"
    )
    assert payload["user_memory"]["indexState"]["reindexRequired"] is False
    assert payload["skill_candidates"]["extraction"]["max_candidates"] == 4


@pytest.mark.asyncio
async def test_get_memory_config_uses_reset_sections(admin_user):
    config = SimpleNamespace(
        get_section=lambda name: {
            "user_memory": {"retrieval": {"similarity_threshold": 0.4}},
            "skill_candidates": {},
            "skill_runtime": {},
            "session_ledger": {},
            "runtime_context": {},
            "knowledge_base": {},
            "llm": {},
        }[name]
    )
    payload = _config_payload(0.4)

    with (
        patch("api_gateway.routers.memory_pipeline_config.get_config", return_value=config),
        patch(
            "api_gateway.routers.memory_pipeline_config._build_memory_config_payload",
            return_value=payload,
        ),
    ):
        result = await get_memory_config(current_user=admin_user)

    assert result.user_memory == payload["user_memory"]


@pytest.mark.asyncio
async def test_update_memory_config_rejects_non_admin(regular_user):
    with pytest.raises(Exception) as exc:
        await update_memory_config(
            update_data=MemoryConfigUpdateRequest(
                user_memory={"retrieval": {"similarity_threshold": 0.42}}
            ),
            current_user=regular_user,
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_memory_config_writes_requested_sections(admin_user):
    canonical_payload = _config_payload(0.42)
    canonical_payload["user_memory"]["consolidation"]["enabled"] = False
    canonical_payload["skill_candidates"]["extraction"]["max_candidates"] = 8
    canonical_payload["runtime_context"]["enable_skills"] = False

    update = MemoryConfigUpdateRequest(
        user_memory={
            "retrieval": {"similarity_threshold": 0.42},
            "consolidation": {"enabled": False},
        },
        runtime_context={"enable_skills": False},
        skill_candidates={"extraction": {"max_candidates": 8}},
    )
    reloaded = SimpleNamespace(
        get_section=lambda name: {
            "user_memory": {"retrieval": {"similarity_threshold": 0.42}},
            "skill_candidates": {},
            "skill_runtime": {},
            "session_ledger": {},
            "runtime_context": {},
            "knowledge_base": {},
            "llm": {},
        }[name]
    )
    file_mock = mock_open(read_data="user_memory: {}\n")

    with (
        patch("builtins.open", file_mock),
        patch(
            "yaml.safe_load",
            return_value={
                "user_memory": {},
                "skill_candidates": {},
                "skill_runtime": {},
                "runtime_context": {},
            },
        ),
        patch("yaml.dump") as yaml_dump,
        patch("shared.config.reload_config", return_value=reloaded),
        patch(
            "api_gateway.routers.memory_pipeline_config._build_memory_config_payload",
            return_value=canonical_payload,
        ),
    ):
        result = await update_memory_config(update_data=update, current_user=admin_user)

    dumped_config = yaml_dump.call_args.args[0]
    assert dumped_config["user_memory"]["retrieval"] == {"similarity_threshold": 0.42}
    assert dumped_config["user_memory"]["consolidation"]["enabled"] is False
    assert dumped_config["runtime_context"] == {
        "enable_user_memory": True,
        "enable_skills": False,
        "enable_knowledge_base": True,
    }
    assert dumped_config["runtime_context"]["enable_skills"] is False
    assert dumped_config["skill_candidates"]["extraction"]["max_candidates"] == 8
    assert dumped_config["skill_runtime"]["retrieval"]["top_k"] == 5
    assert result.user_memory["retrieval"] == {"similarity_threshold": 0.42}
