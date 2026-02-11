"""Embedding generation service using local LLM providers.

This module provides embedding generation using local LLM providers (Ollama/vLLM)
for semantic similarity search in the memory system.

References:
- Requirements 3.2, 5: Vector Database and LLM Integration
- Design Section 6.3: Embedding Strategy
- Design Section 9: LLM Integration Design
"""

import json
import logging
from typing import List, Optional

import requests

from memory_system.memory_interface import EmbeddingServiceInterface
from shared.config import get_config

logger = logging.getLogger(__name__)


def _normalize_embedding_vector(raw_vector: object) -> Optional[List[float]]:
    """Normalize one embedding candidate into a float vector."""
    if not isinstance(raw_vector, list) or not raw_vector:
        return None

    try:
        return [float(value) for value in raw_vector]
    except (TypeError, ValueError):
        return None


def _extract_embedding_vectors(response_data: object) -> List[List[float]]:
    """Parse embedding vectors from OpenAI-compatible and provider-specific responses."""
    vectors: List[List[float]] = []

    def _append_candidate(candidate: object) -> None:
        vector = _normalize_embedding_vector(candidate)
        if vector:
            vectors.append(vector)

    def _walk(payload: object) -> None:
        if payload is None:
            return

        # Some gateways wrap the real response as JSON string in "output".
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except Exception:
                return
            _walk(parsed)
            return

        # Direct vector payload.
        if isinstance(payload, list):
            _append_candidate(payload)
            for item in payload:
                if isinstance(item, (dict, list, str)):
                    _walk(item)
            return

        if not isinstance(payload, dict):
            return

        # OpenAI-compatible: {"data": [{"embedding": [...]}, ...]}
        raw_data = payload.get("data")
        if isinstance(raw_data, list):
            for item in raw_data:
                if isinstance(item, dict):
                    _append_candidate(item.get("embedding"))
                else:
                    _append_candidate(item)

        # Common alternatives used by gateways/proxies.
        for key in ("embeddings", "results"):
            alt_payload = payload.get(key)
            if isinstance(alt_payload, list):
                for item in alt_payload:
                    if isinstance(item, dict):
                        _append_candidate(item.get("embedding"))
                    else:
                        _append_candidate(item)

        # Some providers return {"output": "...json..."} or {"output": {...}}
        _walk(payload.get("output"))

        _append_candidate(payload.get("embedding"))

    _walk(response_data)
    return vectors


class OllamaEmbeddingService(EmbeddingServiceInterface):
    """
    Embedding service using Ollama local LLM provider.

    This service generates embeddings using Ollama's embedding models
    (e.g., nomic-embed-text, mxbai-embed-large).

    Example:
        >>> service = OllamaEmbeddingService()
        >>> embedding = service.generate_embedding("Hello world")
        >>> len(embedding)
        768
    """

    def __init__(
        self, base_url: Optional[str] = None, model: Optional[str] = None, timeout: int = 30
    ):
        """
        Initialize the Ollama embedding service.

        Args:
            base_url: Ollama API base URL (default from config)
            model: Embedding model name (default from config)
            timeout: Request timeout in seconds
        """
        self._config = get_config()

        # Read knowledge_base.embedding config first
        kb_config = self._config.get_section("knowledge_base") if self._config else {}
        kb_embedding = kb_config.get("embedding", {})

        # Resolve provider config from DB (primary) or config.yaml (fallback)
        embedding_provider = kb_embedding.get("provider", "ollama")
        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(embedding_provider)

        self._base_url = base_url or provider_cfg.get("base_url", "http://localhost:11434")
        self._api_key = provider_cfg.get("api_key")

        # Model priority: explicit param > kb.embedding.model > provider default
        self._model = (
            model
            or kb_embedding.get("model")
            or "nomic-embed-text"
        )

        self._timeout = provider_cfg.get("timeout", timeout)
        # Dimension priority: kb.embedding.dimension > provider config > auto-detect
        default_dim = 1024 if "bge" in self._model else 768
        self._embedding_dim = (
            kb_embedding.get("dimension")
            or provider_cfg.get("embedding_dimension")
            or default_dim
        )

        logger.info(
            f"Initialized Ollama embedding service: "
            f"url={self._base_url}, model={self._model}, dim={self._embedding_dim}"
        )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using Ollama.

        Args:
            text: Input text

        Returns:
            List[float]: Embedding vector

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            # Call Ollama embeddings API
            url = f"{self._base_url}/api/embeddings"
            payload = {"model": self._model, "prompt": text}
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            response = requests.post(url, json=payload, headers=headers, timeout=self._timeout)

            response.raise_for_status()

            # Extract embedding from response
            result = response.json()
            vectors = _extract_embedding_vectors(result)
            if not vectors:
                raise RuntimeError("No embedding returned from Ollama")
            embedding = vectors[0]

            logger.debug(f"Generated embedding for text (length={len(text)})")
            return embedding

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate embedding via Ollama: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Note: Ollama doesn't have a native batch API, so this calls
        the single embedding endpoint multiple times. For better performance,
        consider using vLLM for batch operations.

        Args:
            texts: List of input texts

        Returns:
            List[List[float]]: List of embedding vectors

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not texts:
            return []

        embeddings = []
        for i, text in enumerate(texts):
            try:
                embedding = self.generate_embedding(text)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to generate embedding for text {i}: {e}")
                # Continue with other texts, append None for failed ones
                embeddings.append(None)

        # Check if any embeddings failed
        failed_count = sum(1 for e in embeddings if e is None)
        if failed_count > 0:
            logger.warning(f"Failed to generate {failed_count}/{len(texts)} embeddings")

        return embeddings

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this service.

        Returns:
            int: Embedding dimension
        """
        return self._embedding_dim


class VLLMEmbeddingService(EmbeddingServiceInterface):
    """
    Embedding service using vLLM local LLM provider.

    This service generates embeddings using vLLM's high-performance
    embedding models for production-scale deployments.

    Example:
        >>> service = VLLMEmbeddingService()
        >>> embeddings = service.generate_embeddings_batch(["text1", "text2"])
        >>> len(embeddings)
        2
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 30,
        provider_name: Optional[str] = None,
    ):
        """
        Initialize the vLLM embedding service.

        Args:
            base_url: vLLM API base URL (default from config)
            model: Embedding model name (default from config)
            timeout: Request timeout in seconds
            provider_name: Provider identifier (e.g. vllm, llm-pool)
        """
        self._config = get_config()

        # Resolve provider config from DB (primary) or config.yaml (fallback)
        from llm_providers.provider_resolver import resolve_provider

        kb_config = self._config.get_section("knowledge_base") if self._config else {}
        kb_embedding = kb_config.get("embedding", {})
        resolved_provider = provider_name or kb_embedding.get("provider") or "vllm"
        provider_cfg = resolve_provider(resolved_provider)

        provider_models = provider_cfg.get("models", [])
        if isinstance(provider_models, dict):
            provider_models = list(provider_models.values())
        if not isinstance(provider_models, list):
            provider_models = []

        provider_embedding_model = ""
        embedding_hints = ("embed", "embedding", "bge", "e5", "mxbai", "gte", "jina")
        for candidate in provider_models:
            candidate_str = str(candidate)
            if any(hint in candidate_str.lower() for hint in embedding_hints):
                provider_embedding_model = candidate_str
                break
        if not provider_embedding_model and provider_models:
            provider_embedding_model = str(provider_models[0])

        self._base_url = base_url or provider_cfg.get("base_url", "http://localhost:8000")
        self._api_key = provider_cfg.get("api_key")
        self._model = (
            model
            or kb_embedding.get("model")
            or provider_embedding_model
            or "BAAI/bge-m3"
        )

        resolved_timeout = provider_cfg.get("timeout", timeout)
        try:
            self._timeout = max(int(resolved_timeout), 1)
        except (TypeError, ValueError):
            self._timeout = timeout

        default_dim = 1024 if "bge" in self._model.lower() else 768
        provider_dim = provider_cfg.get("embedding_dimension")
        try:
            provider_dim = int(provider_dim) if provider_dim is not None else None
        except (TypeError, ValueError):
            provider_dim = None
        self._embedding_dim = kb_embedding.get("dimension") or provider_dim or default_dim

        logger.info(
            f"Initialized vLLM embedding service: "
            f"provider={resolved_provider}, "
            f"url={self._base_url}, model={self._model}, dim={self._embedding_dim}"
        )

    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text using vLLM.

        Args:
            text: Input text

        Returns:
            List[float]: Embedding vector

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            # Call vLLM embeddings API (OpenAI-compatible)
            url = f"{self._base_url}/v1/embeddings"
            payload = {"model": self._model, "input": text}
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            response = requests.post(url, json=payload, headers=headers, timeout=self._timeout)

            response.raise_for_status()

            # Extract embedding from response
            result = response.json()
            vectors = _extract_embedding_vectors(result)
            if not vectors:
                raise RuntimeError(
                    f"No embedding returned from provider response (keys={list(result.keys())})"
                )
            embedding = vectors[0]

            logger.debug(f"Generated embedding for text (length={len(text)})")
            return embedding

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate embedding via vLLM: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch using vLLM.

        vLLM supports batch embedding generation for better performance.

        Args:
            texts: List of input texts

        Returns:
            List[List[float]]: List of embedding vectors

        Raises:
            RuntimeError: If embedding generation fails
        """
        if not texts:
            return []

        try:
            # Call vLLM embeddings API with batch input
            url = f"{self._base_url}/v1/embeddings"
            payload = {"model": self._model, "input": texts}
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self._timeout * 2,  # Longer timeout for batch
            )

            response.raise_for_status()

            # Extract embeddings from response
            result = response.json()
            embeddings = _extract_embedding_vectors(result)
            if not embeddings:
                raise RuntimeError(
                    f"No embeddings returned from provider response (keys={list(result.keys())})"
                )

            logger.debug(f"Generated {len(embeddings)} embeddings in batch")
            return embeddings

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate batch embeddings via vLLM: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating batch embeddings: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}")

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this service.

        Returns:
            int: Embedding dimension
        """
        return self._embedding_dim


# Global embedding service instance
_embedding_service: Optional[EmbeddingServiceInterface] = None
_embedding_service_signature: Optional[str] = None


def _build_embedding_service_signature() -> str:
    """Build signature to refresh singleton when embedding/provider config changes."""
    try:
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}
        kb_embedding = kb_config.get("embedding", {})
        provider = str(kb_embedding.get("provider", "") or "").lower()
        if not provider and config:
            llm_config = config.get_section("llm")
            provider = str(llm_config.get("embedding_provider", "ollama") or "").lower()

        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(provider)
        signature_payload = {
            "provider": provider,
            "model": kb_embedding.get("model"),
            "dimension": kb_embedding.get("dimension"),
            "base_url": provider_cfg.get("base_url"),
            "protocol": provider_cfg.get("protocol"),
            "timeout": provider_cfg.get("timeout"),
            # avoid leaking key into logs; only use presence bit for signature.
            "has_api_key": bool(provider_cfg.get("api_key")),
        }
        return json.dumps(signature_payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return ""


def get_embedding_service() -> EmbeddingServiceInterface:
    """
    Get the global embedding service instance.

    This function returns the singleton embedding service instance.
    The service type (Ollama/vLLM) is determined by knowledge_base.embedding.provider
    in config, falling back to llm.embedding_provider.

    Returns:
        EmbeddingServiceInterface: Global embedding service instance
    """
    global _embedding_service, _embedding_service_signature
    signature = _build_embedding_service_signature()

    if _embedding_service is None or signature != _embedding_service_signature:
        config = get_config()

        # Prefer knowledge_base.embedding.provider, fallback to llm.embedding_provider
        kb_config = config.get_section("knowledge_base") if config else {}
        kb_embedding = kb_config.get("embedding", {})
        provider = kb_embedding.get("provider", "").lower()

        if not provider:
            llm_config = config.get_section("llm") if config else {}
            provider = llm_config.get("embedding_provider", "ollama").lower()

        # Determine which service to use based on provider protocol
        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(provider)
        protocol = provider_cfg.get(
            "protocol",
            "ollama" if provider == "ollama" else "openai_compatible",
        )

        if protocol == "ollama":
            _embedding_service = OllamaEmbeddingService()
        else:
            # openai_compatible (vLLM, llm-pool, etc.) uses /v1/embeddings
            _embedding_service = VLLMEmbeddingService(
                provider_name=provider,
                model=kb_embedding.get("model"),
            )

        _embedding_service_signature = signature
        logger.info(f"Initialized embedding service: {provider}")

    return _embedding_service


def set_embedding_service(service: EmbeddingServiceInterface) -> None:
    """
    Set a custom embedding service instance.

    This is useful for testing or using custom embedding providers.

    Args:
        service: Embedding service instance
    """
    global _embedding_service, _embedding_service_signature
    _embedding_service = service
    _embedding_service_signature = ""
    logger.info(f"Set custom embedding service: {type(service).__name__}")
