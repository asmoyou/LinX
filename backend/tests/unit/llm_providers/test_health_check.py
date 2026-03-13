"""
Unit tests for LLM Provider Health Check Service

Verifies that chat, embedding, and rerank models are each tested with the
correct API endpoint and payload.

References:
- Requirements 5: Multi-Provider LLM Support
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_providers.health_check import (
    ApiKeyStatus,
    HealthStatus,
    ModelHealthResult,
    _detect_model_type,
    _has_embedding_data,
    _has_rerank_data,
    _resolve_model_type,
    check_model_with_single_key,
    check_models_health,
)


# ---------------------------------------------------------------------------
# Model type detection
# ---------------------------------------------------------------------------


class TestDetectModelType:
    """Tests for _detect_model_type pattern matching."""

    @pytest.mark.parametrize(
        "model_id,expected",
        [
            # Rerank models
            ("bge-reranker-v2-m3", "rerank"),
            ("jina-reranker-v1", "rerank"),
            ("BAAI/bge-reranker-large", "rerank"),
            ("rerank-english-v3.0", "rerank"),
            ("re-rank-model", "rerank"),
            # Embedding models
            ("bge-m3", "embedding"),
            ("bge-large-zh", "embedding"),
            ("text-embedding-3-small", "embedding"),
            ("text-embedding-ada-002", "embedding"),
            ("nomic-embed-text", "embedding"),
            ("jina-embeddings-v2", "embedding"),
            ("mxbai-embed-large", "embedding"),
            ("gte-base", "embedding"),
            ("e5-large", "embedding"),
            ("voyage-2", "embedding"),
            ("doubao-embedding-v1", "embedding"),
            # Chat models (default)
            ("llama3:8b", "chat"),
            ("qwen2:7b", "chat"),
            ("gpt-4o", "chat"),
            ("deepseek-chat", "chat"),
            ("claude-3-sonnet", "chat"),
        ],
    )
    def test_pattern_detection(self, model_id: str, expected: str):
        assert _detect_model_type(model_id) == expected

    def test_rerank_takes_priority_over_embed(self):
        """Models with both 'rerank' and 'embed' keywords should be rerank."""
        assert _detect_model_type("bge-reranker-embed-v2") == "rerank"


class TestResolveModelType:
    """Tests for _resolve_model_type with metadata override."""

    def test_metadata_embedding_overrides_pattern(self):
        result = _resolve_model_type("custom-model", {"model_type": "embedding"})
        assert result == "embedding"

    def test_metadata_rerank_overrides_pattern(self):
        result = _resolve_model_type("custom-model", {"model_type": "rerank"})
        assert result == "rerank"

    def test_metadata_chat_falls_through_to_pattern(self):
        """A chat metadata doesn't force chat — pattern still runs."""
        result = _resolve_model_type("bge-m3", {"model_type": "chat"})
        assert result == "embedding"

    def test_no_metadata_uses_pattern(self):
        assert _resolve_model_type("bge-reranker-v2-m3") == "rerank"
        assert _resolve_model_type("bge-m3") == "embedding"
        assert _resolve_model_type("llama3") == "chat"


# ---------------------------------------------------------------------------
# Payload introspection helpers
# ---------------------------------------------------------------------------


class TestHasEmbeddingData:
    def test_openai_style(self):
        data = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
        assert _has_embedding_data(data) is True

    def test_ollama_style(self):
        data = {"embedding": [0.1, 0.2, 0.3]}
        assert _has_embedding_data(data) is True

    def test_empty_embedding(self):
        data = {"embedding": []}
        assert _has_embedding_data(data) is False

    def test_no_embedding_key(self):
        data = {"choices": [{"text": "hello"}]}
        assert _has_embedding_data(data) is False

    def test_non_dict(self):
        assert _has_embedding_data("hello") is False


class TestHasRerankData:
    def test_results_key(self):
        data = {"results": [{"index": 0, "relevance_score": 0.9}]}
        assert _has_rerank_data(data) is True

    def test_data_key(self):
        data = {"data": [{"index": 0, "relevance_score": 0.8}]}
        assert _has_rerank_data(data) is True

    def test_empty_results(self):
        data = {"results": []}
        assert _has_rerank_data(data) is False

    def test_no_results_key(self):
        data = {"embedding": [0.1, 0.2]}
        assert _has_rerank_data(data) is False


# ---------------------------------------------------------------------------
# check_model_with_single_key: dispatch to correct test method
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal async context manager for mocking aiohttp responses."""

    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        import json
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeSession:
    """Minimal async context manager wrapping a mock post."""

    def __init__(self, response: _FakeResponse):
        self._response = response
        self.post = MagicMock(return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def _patch_aiohttp(fake_response: _FakeResponse):
    """Patch aiohttp.ClientSession to return a fake session."""
    fake_session = _FakeSession(fake_response)
    return patch("aiohttp.ClientSession", return_value=fake_session)


class TestCheckModelEmbedding:
    """Embedding models should hit the embeddings endpoint, not chat."""

    @pytest.mark.asyncio
    async def test_ollama_embedding_model(self):
        resp = _FakeResponse(200, {"embedding": [0.1, 0.2, 0.3]})
        with _patch_aiohttp(resp) as mock_cls:
            result = await check_model_with_single_key(
                provider_name="ollama-local",
                protocol="ollama",
                base_url="http://localhost:11434",
                model_id="bge-m3",
                timeout=10,
            )

        assert result.status == HealthStatus.SUCCESS
        # Verify it called the embeddings endpoint, not /api/generate
        call_args = mock_cls.return_value.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "/api/embeddings" in url

    @pytest.mark.asyncio
    async def test_openai_compatible_embedding_model(self):
        resp = _FakeResponse(200, {"data": [{"embedding": [0.1, 0.2]}]})
        with _patch_aiohttp(resp) as mock_cls:
            result = await check_model_with_single_key(
                provider_name="xinference",
                protocol="openai_compatible",
                base_url="http://localhost:9997",
                model_id="bge-m3",
                api_key="test-key",
                timeout=10,
            )

        assert result.status == HealthStatus.SUCCESS
        call_args = mock_cls.return_value.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "/embeddings" in url
        assert "/chat/completions" not in url

    @pytest.mark.asyncio
    async def test_embedding_model_via_metadata_override(self):
        """model_metadata with model_type=embedding should route to embedding test."""
        resp = _FakeResponse(200, {"data": [{"embedding": [0.5]}]})
        with _patch_aiohttp(resp):
            result = await check_model_with_single_key(
                provider_name="custom",
                protocol="openai_compatible",
                base_url="http://localhost:8080",
                model_id="my-custom-model",
                timeout=10,
                model_metadata={"model_type": "embedding"},
            )

        assert result.status == HealthStatus.SUCCESS


class TestCheckModelRerank:
    """Rerank models should hit the rerank endpoint."""

    @pytest.mark.asyncio
    async def test_openai_compatible_rerank_model(self):
        resp = _FakeResponse(
            200, {"results": [{"index": 0, "relevance_score": 0.9}]}
        )
        with _patch_aiohttp(resp) as mock_cls:
            result = await check_model_with_single_key(
                provider_name="xinference",
                protocol="openai_compatible",
                base_url="http://localhost:9997",
                model_id="bge-reranker-v2-m3",
                api_key="test-key",
                timeout=10,
            )

        assert result.status == HealthStatus.SUCCESS
        call_args = mock_cls.return_value.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "/rerank" in url

    @pytest.mark.asyncio
    async def test_rerank_model_via_metadata_override(self):
        resp = _FakeResponse(200, {"results": [{"index": 0, "relevance_score": 0.8}]})
        with _patch_aiohttp(resp):
            result = await check_model_with_single_key(
                provider_name="custom",
                protocol="openai_compatible",
                base_url="http://localhost:8080",
                model_id="my-custom-reranker",
                timeout=10,
                model_metadata={"model_type": "rerank"},
            )

        assert result.status == HealthStatus.SUCCESS


class TestCheckModelChat:
    """Chat models should still hit the chat/generate endpoint."""

    @pytest.mark.asyncio
    async def test_ollama_chat_model(self):
        resp = _FakeResponse(200, {"response": "hi"})
        with _patch_aiohttp(resp) as mock_cls:
            result = await check_model_with_single_key(
                provider_name="ollama-local",
                protocol="ollama",
                base_url="http://localhost:11434",
                model_id="llama3:8b",
                timeout=10,
            )

        assert result.status == HealthStatus.SUCCESS
        call_args = mock_cls.return_value.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "/api/generate" in url

    @pytest.mark.asyncio
    async def test_openai_compatible_chat_model(self):
        resp = _FakeResponse(200, {"choices": [{"message": {"content": "hi"}}]})
        with _patch_aiohttp(resp) as mock_cls:
            result = await check_model_with_single_key(
                provider_name="xinference",
                protocol="openai_compatible",
                base_url="http://localhost:9997",
                model_id="qwen2-chat",
                api_key="test-key",
                timeout=10,
            )

        assert result.status == HealthStatus.SUCCESS
        call_args = mock_cls.return_value.post.call_args
        url = call_args.args[0] if call_args.args else call_args.kwargs.get("url", "")
        assert "/chat/completions" in url


class TestCheckModelFailure:
    """Test error paths."""

    @pytest.mark.asyncio
    async def test_embedding_model_http_error(self):
        resp = _FakeResponse(500, {"error": "internal server error"})
        with _patch_aiohttp(resp):
            result = await check_model_with_single_key(
                provider_name="xinference",
                protocol="openai_compatible",
                base_url="http://localhost:9997",
                model_id="bge-m3",
                timeout=10,
            )

        assert result.status == HealthStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_rerank_model_http_error(self):
        resp = _FakeResponse(404, {"error": "not found"})
        with _patch_aiohttp(resp):
            result = await check_model_with_single_key(
                provider_name="xinference",
                protocol="openai_compatible",
                base_url="http://localhost:9997",
                model_id="bge-reranker-v2-m3",
                timeout=10,
            )

        assert result.status == HealthStatus.FAILED


# ---------------------------------------------------------------------------
# check_models_health: batch with mixed model types
# ---------------------------------------------------------------------------


class TestCheckModelsHealthMixed:
    """Batch health check with a mix of chat, embedding, rerank models."""

    @pytest.mark.asyncio
    async def test_mixed_models_use_correct_endpoints(self):
        """All three model types in one batch should each get the right test."""
        call_log = []

        async def mock_check_single(
            provider_name, protocol, base_url, model_id,
            api_key=None, timeout=15, model_metadata=None,
        ):
            model_type = _resolve_model_type(model_id, model_metadata)
            call_log.append((model_id, model_type))
            return ApiKeyStatus(
                key_masked="no-key",
                status=HealthStatus.SUCCESS,
                latency=10.0,
            )

        with patch(
            "llm_providers.health_check.check_model_with_single_key",
            side_effect=mock_check_single,
        ):
            results = await check_models_health(
                provider_name="xinference",
                protocol="openai_compatible",
                base_url="http://localhost:9997",
                models=["qwen2-chat", "bge-m3", "bge-reranker-v2-m3"],
                api_keys=[],
                concurrent=False,
                timeout=10,
            )

        assert len(results) == 3
        assert all(r.status == HealthStatus.SUCCESS for r in results)

        # Verify each model was classified correctly
        types = {mid: mtype for mid, mtype in call_log}
        assert types["qwen2-chat"] == "chat"
        assert types["bge-m3"] == "embedding"
        assert types["bge-reranker-v2-m3"] == "rerank"

    @pytest.mark.asyncio
    async def test_metadata_map_passed_through(self):
        """model_metadata_map should be forwarded to per-model checks."""
        received_metadata = []

        async def mock_check_single(
            provider_name, protocol, base_url, model_id,
            api_key=None, timeout=15, model_metadata=None,
        ):
            received_metadata.append((model_id, model_metadata))
            return ApiKeyStatus(
                key_masked="no-key",
                status=HealthStatus.SUCCESS,
                latency=5.0,
            )

        metadata_map = {
            "custom-embed": {"model_type": "embedding", "dimension": 768},
            "custom-rerank": {"model_type": "rerank"},
        }

        with patch(
            "llm_providers.health_check.check_model_with_single_key",
            side_effect=mock_check_single,
        ):
            await check_models_health(
                provider_name="test",
                protocol="openai_compatible",
                base_url="http://localhost:8080",
                models=["custom-embed", "custom-rerank", "chat-model"],
                api_keys=[],
                concurrent=False,
                timeout=10,
                model_metadata_map=metadata_map,
            )

        meta_by_model = {mid: meta for mid, meta in received_metadata}
        assert meta_by_model["custom-embed"] == {"model_type": "embedding", "dimension": 768}
        assert meta_by_model["custom-rerank"] == {"model_type": "rerank"}
        assert meta_by_model["chat-model"] is None
