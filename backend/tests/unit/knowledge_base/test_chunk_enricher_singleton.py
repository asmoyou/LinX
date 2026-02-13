"""Tests for chunk enricher singleton refresh behavior."""

from typing import Any

import knowledge_base.chunk_enricher as chunk_enricher_module


class _FakeConfig:
    """Minimal config object exposing get_section used by the enricher."""

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get_section(self, section: str) -> dict[str, Any]:
        return self._data.get(section, {})


def _mock_resolve_provider(provider_name: str) -> dict[str, Any]:
    return {
        "base_url": f"http://{provider_name}.local",
        "api_key": None,
        "protocol": "openai_compatible",
        "timeout": 30,
    }


def _mock_resolve_provider_with_metadata(provider_name: str) -> dict[str, Any]:
    return {
        "base_url": f"http://{provider_name}.local",
        "api_key": None,
        "protocol": "openai_compatible",
        "timeout": 30,
        "model_metadata": {
            "model-a": {
                "max_output_tokens": 3072,
            }
        },
    }


def test_get_chunk_enricher_reuses_singleton_when_signature_is_unchanged(monkeypatch) -> None:
    """Repeated access should keep one singleton when config signature is identical."""
    config_data = {
        "knowledge_base": {
            "enrichment": {
                "provider": "provider-a",
                "model": "model-a",
                "keywords_topn": 5,
                "questions_topn": 3,
                "generate_summary": True,
                "temperature": 0.2,
                "batch_size": 5,
            }
        }
    }
    fake_config = _FakeConfig(config_data)

    monkeypatch.setattr(chunk_enricher_module, "get_config", lambda: fake_config)
    monkeypatch.setattr(
        "llm_providers.provider_resolver.resolve_provider",
        _mock_resolve_provider,
    )

    chunk_enricher_module.reset_chunk_enricher()
    first = chunk_enricher_module.get_chunk_enricher()
    second = chunk_enricher_module.get_chunk_enricher()

    assert first is second

    chunk_enricher_module.reset_chunk_enricher()


def test_get_chunk_enricher_rebuilds_when_config_signature_changes(monkeypatch) -> None:
    """Config/provider changes should invalidate cached singleton automatically."""
    config_data = {
        "knowledge_base": {
            "enrichment": {
                "provider": "provider-a",
                "model": "model-a",
                "keywords_topn": 5,
                "questions_topn": 3,
                "generate_summary": True,
                "temperature": 0.2,
                "batch_size": 5,
            }
        }
    }
    fake_config = _FakeConfig(config_data)

    monkeypatch.setattr(chunk_enricher_module, "get_config", lambda: fake_config)
    monkeypatch.setattr(
        "llm_providers.provider_resolver.resolve_provider",
        _mock_resolve_provider,
    )

    chunk_enricher_module.reset_chunk_enricher()
    first = chunk_enricher_module.get_chunk_enricher()
    assert first.provider_name == "provider-a"
    assert first.base_url == "http://provider-a.local"

    config_data["knowledge_base"]["enrichment"]["provider"] = "provider-b"
    config_data["knowledge_base"]["enrichment"]["model"] = "model-b"

    second = chunk_enricher_module.get_chunk_enricher()
    assert second is not first
    assert second.provider_name == "provider-b"
    assert second.model_name == "model-b"
    assert second.base_url == "http://provider-b.local"

    chunk_enricher_module.reset_chunk_enricher()


def test_get_chunk_enricher_rebuilds_when_max_tokens_changes(monkeypatch) -> None:
    """Changing enrichment max_tokens should refresh singleton with new runtime cap."""
    config_data = {
        "knowledge_base": {
            "enrichment": {
                "provider": "provider-a",
                "model": "model-a",
                "max_tokens": 1024,
            }
        }
    }
    fake_config = _FakeConfig(config_data)

    monkeypatch.setattr(chunk_enricher_module, "get_config", lambda: fake_config)
    monkeypatch.setattr(
        "llm_providers.provider_resolver.resolve_provider",
        _mock_resolve_provider,
    )

    chunk_enricher_module.reset_chunk_enricher()
    first = chunk_enricher_module.get_chunk_enricher()
    assert first.max_tokens == 1024

    config_data["knowledge_base"]["enrichment"]["max_tokens"] = 2048

    second = chunk_enricher_module.get_chunk_enricher()
    assert second is not first
    assert second.max_tokens == 2048

    chunk_enricher_module.reset_chunk_enricher()


def test_get_chunk_enricher_uses_model_metadata_max_output_tokens(monkeypatch) -> None:
    """When enrichment max_tokens is absent/0, use provider model metadata fallback."""
    config_data = {
        "knowledge_base": {
            "enrichment": {
                "provider": "provider-a",
                "model": "model-a",
                "max_tokens": 0,
            }
        }
    }
    fake_config = _FakeConfig(config_data)

    monkeypatch.setattr(chunk_enricher_module, "get_config", lambda: fake_config)
    monkeypatch.setattr(
        "llm_providers.provider_resolver.resolve_provider",
        _mock_resolve_provider_with_metadata,
    )

    chunk_enricher_module.reset_chunk_enricher()
    enricher = chunk_enricher_module.get_chunk_enricher()
    assert enricher.max_tokens == 3072

    chunk_enricher_module.reset_chunk_enricher()
