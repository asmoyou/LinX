"""Tests for adaptive batch splitting in OpenAI-compatible embedding service."""

from unittest.mock import patch

import requests
import pytest

from memory_system.embedding_service import VLLMEmbeddingService


class _FakeResponse:
    """Simple fake HTTP response for embedding API tests."""

    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self._payload = payload or {}
        self._error = error

    def raise_for_status(self) -> None:
        if self._error:
            raise self._error

    def json(self) -> dict:
        return self._payload


def _build_service(base_url: str = "http://localhost:8000") -> VLLMEmbeddingService:
    with patch("memory_system.embedding_service.resolve_embedding_settings") as mock_settings:
        with patch("llm_providers.provider_resolver.resolve_provider") as mock_resolve_provider:
            mock_settings.return_value = {
                "provider": "llm-pool",
                "model": "BAAI/bge-m3",
                "dimension": 1024,
            }
            mock_resolve_provider.return_value = {
                "base_url": base_url,
                "api_key": None,
                "timeout": 30,
                "protocol": "openai_compatible",
            }
            return VLLMEmbeddingService(scope="knowledge_base")


def test_vllm_batch_splits_when_payload_too_large() -> None:
    """A 413 batch failure should trigger adaptive split and preserve output order."""
    service = _build_service()
    texts = [f"chunk-{idx}" for idx in range(4)]
    call_sizes: list[int] = []

    def _mock_post(_url, json, headers, timeout):  # noqa: ANN001
        _ = headers
        _ = timeout
        batch_inputs = json["input"]
        if isinstance(batch_inputs, str):
            batch_inputs = [batch_inputs]

        call_sizes.append(len(batch_inputs))
        if len(batch_inputs) == 4:
            return _FakeResponse(
                error=requests.exceptions.HTTPError(
                    "413 Client Error: Request Entity Too Large for url: /v1/embeddings"
                )
            )

        payload = {
            "data": [{"embedding": [float(item.split("-")[-1]), 1.0]} for item in batch_inputs]
        }
        return _FakeResponse(payload=payload)

    with patch("memory_system.embedding_service.requests.post", side_effect=_mock_post):
        embeddings = service.generate_embeddings_batch(texts)

    assert call_sizes == [4, 2, 2]
    assert len(embeddings) == 4
    for idx, vector in enumerate(embeddings):
        expected_norm = (float(idx) ** 2 + 1.0) ** 0.5
        assert vector[0] == pytest.approx(float(idx) / expected_norm)
        assert vector[1] == pytest.approx(1.0 / expected_norm)
        assert (vector[0] ** 2 + vector[1] ** 2) ** 0.5 == pytest.approx(1.0)


def test_vllm_embedding_url_does_not_duplicate_v1_suffix() -> None:
    """Providers that already expose `/v1` should not receive `/v1/v1/embeddings`."""
    service = _build_service(base_url="http://localhost:9997/v1")

    def _mock_post(url, json, headers, timeout):  # noqa: ANN001
        _ = json
        _ = headers
        _ = timeout
        assert url == "http://localhost:9997/v1/embeddings"
        return _FakeResponse(payload={"data": [{"embedding": [1.0, 0.0]}]})

    with patch("memory_system.embedding_service.requests.post", side_effect=_mock_post):
        embedding = service.generate_embedding("hello")

    assert embedding == [1.0, 0.0]
