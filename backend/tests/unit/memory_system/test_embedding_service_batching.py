"""Tests for adaptive batch splitting in OpenAI-compatible embedding service."""

from unittest.mock import patch

import requests

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


def _build_service() -> VLLMEmbeddingService:
    with patch("memory_system.embedding_service.resolve_embedding_settings") as mock_settings:
        with patch("llm_providers.provider_resolver.resolve_provider") as mock_resolve_provider:
            mock_settings.return_value = {
                "provider": "llm-pool",
                "model": "BAAI/bge-m3",
                "dimension": 1024,
            }
            mock_resolve_provider.return_value = {
                "base_url": "http://localhost:8000",
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
    assert [vector[0] for vector in embeddings] == [0.0, 1.0, 2.0, 3.0]
