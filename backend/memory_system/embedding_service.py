"""Embedding generation services and scoped config resolution.

This module provides embedding generation using local/remote providers
(Ollama or OpenAI-compatible endpoints) and allows different pipelines
(e.g. memory and knowledge base) to resolve embedding configuration
independently with explicit fallback rules.
"""

import json
import logging
from typing import Dict, List, Optional

import requests

from memory_system.memory_interface import EmbeddingServiceInterface
from shared.config import get_config

logger = logging.getLogger(__name__)

EMBEDDING_SCOPE_MEMORY = "memory"
EMBEDDING_SCOPE_KNOWLEDGE_BASE = "knowledge_base"
_ALLOWED_EMBEDDING_SCOPES = {EMBEDDING_SCOPE_MEMORY, EMBEDDING_SCOPE_KNOWLEDGE_BASE}


def _normalize_scope(scope: Optional[str]) -> str:
    normalized = str(scope or EMBEDDING_SCOPE_MEMORY).strip().lower()
    if normalized not in _ALLOWED_EMBEDDING_SCOPES:
        return EMBEDDING_SCOPE_MEMORY
    return normalized


def _safe_get_section(config, section: str) -> Dict[str, object]:
    if not config:
        return {}
    try:
        section_data = config.get_section(section)
    except Exception:
        return {}
    return section_data if isinstance(section_data, dict) else {}


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _coerce_int(value: object) -> Optional[int]:
    try:
        coerced = int(value)
        return coerced if coerced > 0 else None
    except (TypeError, ValueError):
        return None


def _normalize_provider_models(provider_cfg: dict) -> List[str]:
    provider_models = provider_cfg.get("models", []) if isinstance(provider_cfg, dict) else []
    if isinstance(provider_models, dict):
        provider_models = list(provider_models.values())
    elif isinstance(provider_models, str):
        provider_models = [provider_models]
    elif not isinstance(provider_models, list):
        provider_models = []

    models: List[str] = []
    for model in provider_models:
        model_str = _normalize_text(model)
        if model_str:
            models.append(model_str)
    return models


def _infer_embedding_model_from_provider(provider_cfg: dict) -> str:
    models = _normalize_provider_models(provider_cfg)
    embedding_hints = ("embed", "embedding", "bge", "e5", "mxbai", "gte", "jina")
    for candidate in models:
        lowered = candidate.lower()
        if any(hint in lowered for hint in embedding_hints):
            return candidate
    return models[0] if models else ""


def _default_model_for_provider(provider: str) -> str:
    return "nomic-embed-text" if provider == "ollama" else "BAAI/bge-m3"


def resolve_embedding_settings(scope: str = EMBEDDING_SCOPE_MEMORY) -> Dict[str, object]:
    """Resolve effective embedding settings for a pipeline scope.

    Resolution order:
    1. scope-specific config section (memory.embedding or knowledge_base.embedding)
    2. optional cross-scope fallback (configurable per scope)
    3. llm.embedding_provider / llm.default_provider
    4. provider model hints / hardcoded defaults
    """
    normalized_scope = _normalize_scope(scope)
    config = get_config()

    memory_cfg = _safe_get_section(config, "memory")
    kb_cfg = _safe_get_section(config, "knowledge_base")
    llm_cfg = _safe_get_section(config, "llm")

    memory_embedding = memory_cfg.get("embedding", {}) if isinstance(memory_cfg, dict) else {}
    if not isinstance(memory_embedding, dict):
        memory_embedding = {}

    kb_embedding = kb_cfg.get("embedding", {}) if isinstance(kb_cfg, dict) else {}
    if not isinstance(kb_embedding, dict):
        kb_embedding = {}

    if normalized_scope == EMBEDDING_SCOPE_KNOWLEDGE_BASE:
        primary_name = "knowledge_base.embedding"
        fallback_name = "memory.embedding"
        primary_cfg = kb_embedding
        fallback_cfg = memory_embedding
        allow_cross_scope_fallback = bool(primary_cfg.get("inherit_from_memory", False))
    else:
        primary_name = "memory.embedding"
        fallback_name = "knowledge_base.embedding"
        primary_cfg = memory_embedding
        fallback_cfg = kb_embedding
        allow_cross_scope_fallback = bool(primary_cfg.get("inherit_from_knowledge_base", True))

    provider = _normalize_text(primary_cfg.get("provider"))
    provider_source = f"{primary_name}.provider" if provider else ""

    if not provider and allow_cross_scope_fallback:
        provider = _normalize_text(fallback_cfg.get("provider"))
        if provider:
            provider_source = f"{fallback_name}.provider"

    if not provider:
        provider = _normalize_text(llm_cfg.get("embedding_provider"))
        if provider:
            provider_source = "llm.embedding_provider"

    if not provider:
        provider = _normalize_text(llm_cfg.get("default_provider"))
        if provider:
            provider_source = "llm.default_provider"

    provider = provider.lower() or "ollama"
    if not provider_source:
        provider_source = "hardcoded.default"

    from llm_providers.provider_resolver import resolve_provider

    provider_cfg = resolve_provider(provider)

    model = _normalize_text(primary_cfg.get("model"))
    model_source = f"{primary_name}.model" if model else ""

    if not model and allow_cross_scope_fallback:
        model = _normalize_text(fallback_cfg.get("model"))
        if model:
            model_source = f"{fallback_name}.model"

    if not model:
        model = _infer_embedding_model_from_provider(provider_cfg)
        if model:
            model_source = "provider.models"

    if not model:
        model = _default_model_for_provider(provider)
        model_source = "hardcoded.default"

    dimension = _coerce_int(primary_cfg.get("dimension"))
    dimension_source = f"{primary_name}.dimension" if dimension else ""

    if dimension is None and allow_cross_scope_fallback:
        dimension = _coerce_int(fallback_cfg.get("dimension"))
        if dimension is not None:
            dimension_source = f"{fallback_name}.dimension"

    provider_dimension = _coerce_int(provider_cfg.get("embedding_dimension"))
    if dimension is None and provider_dimension is not None:
        dimension = provider_dimension
        dimension_source = "provider.embedding_dimension"

    if dimension is None:
        dimension = 1024 if "bge" in model.lower() else 768
        dimension_source = "heuristic.default"

    return {
        "scope": normalized_scope,
        "provider": provider,
        "provider_source": provider_source,
        "model": model,
        "model_source": model_source,
        "dimension": dimension,
        "dimension_source": dimension_source,
        "allow_cross_scope_fallback": allow_cross_scope_fallback,
    }


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


def _is_payload_too_large_error(error: Exception) -> bool:
    """Return True when provider rejected request due to payload size."""
    if isinstance(error, requests.exceptions.HTTPError):
        response = getattr(error, "response", None)
        if response is not None and getattr(response, "status_code", None) == 413:
            return True

    message = str(error).lower()
    if "413" in message and (
        "request entity too large" in message
        or "payload too large" in message
        or "request too large" in message
    ):
        return True
    return False


class OllamaEmbeddingService(EmbeddingServiceInterface):
    """Embedding service using Ollama protocol (/api/embeddings)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 30,
        provider_name: Optional[str] = None,
        scope: str = EMBEDDING_SCOPE_MEMORY,
        embedding_settings: Optional[Dict[str, object]] = None,
    ):
        self._config = get_config()
        self._scope = _normalize_scope(scope)
        settings = embedding_settings or resolve_embedding_settings(scope=self._scope)

        from llm_providers.provider_resolver import resolve_provider

        resolved_provider = _normalize_text(
            provider_name or settings.get("provider") or "ollama"
        ).lower()
        provider_cfg = resolve_provider(resolved_provider)

        self._base_url = base_url or provider_cfg.get("base_url", "http://localhost:11434")
        self._api_key = provider_cfg.get("api_key")

        self._model = _normalize_text(
            model or settings.get("model")
        ) or _default_model_for_provider(resolved_provider)

        self._timeout = provider_cfg.get("timeout", timeout)
        default_dim = 1024 if "bge" in self._model.lower() else 768
        self._embedding_dim = (
            _coerce_int(settings.get("dimension"))
            or _coerce_int(provider_cfg.get("embedding_dimension"))
            or default_dim
        )

        logger.info(
            "Initialized Ollama embedding service",
            extra={
                "scope": self._scope,
                "provider": resolved_provider,
                "url": self._base_url,
                "model": self._model,
                "dimension": self._embedding_dim,
            },
        )

    def generate_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            url = f"{self._base_url}/api/embeddings"
            payload = {"model": self._model, "prompt": text}
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            response = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
            response.raise_for_status()

            result = response.json()
            vectors = _extract_embedding_vectors(result)
            if not vectors:
                raise RuntimeError("No embedding returned from Ollama")

            return vectors[0]

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate embedding via Ollama: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        embeddings = []
        for i, text in enumerate(texts):
            try:
                embedding = self.generate_embedding(text)
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"Failed to generate embedding for text {i}: {e}")
                embeddings.append(None)

        failed_count = sum(1 for e in embeddings if e is None)
        if failed_count > 0:
            logger.warning(f"Failed to generate {failed_count}/{len(texts)} embeddings")

        return embeddings

    def get_embedding_dimension(self) -> int:
        return self._embedding_dim


class VLLMEmbeddingService(EmbeddingServiceInterface):
    """Embedding service using OpenAI-compatible protocol (/v1/embeddings)."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 30,
        provider_name: Optional[str] = None,
        scope: str = EMBEDDING_SCOPE_MEMORY,
        embedding_settings: Optional[Dict[str, object]] = None,
    ):
        self._config = get_config()
        self._scope = _normalize_scope(scope)
        settings = embedding_settings or resolve_embedding_settings(scope=self._scope)

        from llm_providers.provider_resolver import resolve_provider

        resolved_provider = _normalize_text(
            provider_name or settings.get("provider") or "vllm"
        ).lower()
        provider_cfg = resolve_provider(resolved_provider)

        provider_embedding_model = _infer_embedding_model_from_provider(provider_cfg)

        self._base_url = base_url or provider_cfg.get("base_url", "http://localhost:8000")
        self._api_key = provider_cfg.get("api_key")
        self._model = (
            _normalize_text(model)
            or _normalize_text(settings.get("model"))
            or provider_embedding_model
            or _default_model_for_provider(resolved_provider)
        )

        resolved_timeout = provider_cfg.get("timeout", timeout)
        try:
            self._timeout = max(int(resolved_timeout), 1)
        except (TypeError, ValueError):
            self._timeout = timeout

        default_dim = 1024 if "bge" in self._model.lower() else 768
        self._embedding_dim = (
            _coerce_int(settings.get("dimension"))
            or _coerce_int(provider_cfg.get("embedding_dimension"))
            or default_dim
        )

        scope_section_name = (
            "knowledge_base" if self._scope == EMBEDDING_SCOPE_KNOWLEDGE_BASE else "memory"
        )
        scope_embedding_cfg: Dict[str, object] = {}
        try:
            scope_section = self._config.get_section(scope_section_name) if self._config else {}
            if isinstance(scope_section, dict):
                embedding_cfg = scope_section.get("embedding", {})
                if isinstance(embedding_cfg, dict):
                    scope_embedding_cfg = embedding_cfg
        except Exception:
            scope_embedding_cfg = {}

        self._max_batch_size = (
            _coerce_int(settings.get("batch_size"))
            or _coerce_int(scope_embedding_cfg.get("batch_size"))
            or 32
        )
        self._max_batch_chars = (
            _coerce_int(settings.get("batch_char_limit"))
            or _coerce_int(scope_embedding_cfg.get("batch_char_limit"))
            or 120_000
        )
        self._single_input_max_chars = (
            _coerce_int(settings.get("single_input_char_limit"))
            or _coerce_int(scope_embedding_cfg.get("single_input_char_limit"))
            or 60_000
        )

        logger.info(
            "Initialized OpenAI-compatible embedding service",
            extra={
                "scope": self._scope,
                "provider": resolved_provider,
                "url": self._base_url,
                "model": self._model,
                "dimension": self._embedding_dim,
                "batch_size": self._max_batch_size,
                "batch_char_limit": self._max_batch_chars,
            },
        )

    def generate_embedding(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        try:
            url = f"{self._base_url}/v1/embeddings"
            payload = {"model": self._model, "input": text}
            headers = {"Content-Type": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"

            response = requests.post(url, json=payload, headers=headers, timeout=self._timeout)
            response.raise_for_status()

            result = response.json()
            vectors = _extract_embedding_vectors(result)
            if not vectors:
                raise RuntimeError(
                    f"No embedding returned from provider response (keys={list(result.keys())})"
                )

            return vectors[0]

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate embedding via vLLM: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}")

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        normalized_texts = [str(text or "") for text in texts]
        embeddings: List[Optional[List[float]]] = [None] * len(normalized_texts)

        try:
            for start, end in self._build_batch_ranges(normalized_texts):
                self._embed_range_with_adaptive_split(
                    texts=normalized_texts,
                    start=start,
                    end=end,
                    output=embeddings,
                )

            missing_indices = [idx for idx, vector in enumerate(embeddings) if vector is None]
            if missing_indices:
                raise RuntimeError(
                    "Batch embedding generation produced missing vectors at indices "
                    f"{missing_indices[:5]}"
                )

            finalized_embeddings: List[List[float]] = []
            for vector in embeddings:
                if vector is None:
                    raise RuntimeError("Missing embedding vector after batch generation")
                finalized_embeddings.append(vector)

            return finalized_embeddings

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to generate batch embeddings via vLLM: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}")
        except Exception as e:
            logger.error(f"Unexpected error generating batch embeddings: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}")

    def _build_batch_ranges(self, texts: List[str]) -> List[tuple[int, int]]:
        """Build initial batches by item count and approximate payload size."""
        ranges: List[tuple[int, int]] = []
        start = 0
        char_count = 0

        for idx, text in enumerate(texts):
            text_length = len(text)
            exceeds_items = (idx - start) >= self._max_batch_size
            exceeds_chars = idx > start and (char_count + text_length) > self._max_batch_chars

            if exceeds_items or exceeds_chars:
                ranges.append((start, idx))
                start = idx
                char_count = 0

            char_count += text_length

        if start < len(texts):
            ranges.append((start, len(texts)))

        return ranges

    def _embed_range_with_adaptive_split(
        self,
        texts: List[str],
        start: int,
        end: int,
        output: List[Optional[List[float]]],
    ) -> None:
        """Embed one range and split recursively when payload is too large."""
        batch = texts[start:end]

        try:
            vectors = self._request_embeddings_batch(batch)
            if len(vectors) != len(batch):
                raise RuntimeError(
                    "Embedding count mismatch: "
                    f"expected={len(batch)}, received={len(vectors)}, range=({start}, {end})"
                )

            for offset, vector in enumerate(vectors):
                output[start + offset] = vector
            return

        except Exception as error:
            if not _is_payload_too_large_error(error):
                raise

            batch_len = end - start
            if batch_len > 1:
                mid = start + (batch_len // 2)
                logger.warning(
                    "Embedding payload too large, splitting batch",
                    extra={
                        "scope": self._scope,
                        "start": start,
                        "end": end,
                        "batch_len": batch_len,
                    },
                )
                self._embed_range_with_adaptive_split(texts, start, mid, output)
                self._embed_range_with_adaptive_split(texts, mid, end, output)
                return

            single_text = batch[0]
            if len(single_text) > self._single_input_max_chars:
                logger.warning(
                    "Single embedding input exceeded payload limit, truncating",
                    extra={
                        "scope": self._scope,
                        "index": start,
                        "original_chars": len(single_text),
                        "truncated_chars": self._single_input_max_chars,
                    },
                )
                single_text = single_text[: self._single_input_max_chars]

            output[start] = self.generate_embedding(single_text)

    def _request_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Submit one embedding batch request and parse vectors."""
        url = f"{self._base_url}/v1/embeddings"
        payload = {"model": self._model, "input": texts}
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=self._timeout * 2,
        )
        response.raise_for_status()

        result = response.json()
        embeddings = _extract_embedding_vectors(result)
        if not embeddings:
            raise RuntimeError(
                f"No embeddings returned from provider response (keys={list(result)})"
            )

        if len(embeddings) != len(texts):
            raise RuntimeError(
                "Provider returned unexpected number of embeddings: "
                f"expected={len(texts)}, got={len(embeddings)}"
            )

        return embeddings

    def get_embedding_dimension(self) -> int:
        return self._embedding_dim


# Scope-keyed embedding service instances.
_embedding_services: Dict[str, EmbeddingServiceInterface] = {}
_embedding_service_signatures: Dict[str, str] = {}


def _build_embedding_service_signature(scope: str) -> str:
    """Build signature to refresh singleton when scoped config changes."""
    normalized_scope = _normalize_scope(scope)
    try:
        settings = resolve_embedding_settings(scope=normalized_scope)

        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(str(settings.get("provider", "")))
        signature_payload = {
            "scope": normalized_scope,
            "provider": settings.get("provider"),
            "model": settings.get("model"),
            "dimension": settings.get("dimension"),
            "provider_source": settings.get("provider_source"),
            "model_source": settings.get("model_source"),
            "dimension_source": settings.get("dimension_source"),
            "base_url": provider_cfg.get("base_url"),
            "protocol": provider_cfg.get("protocol"),
            "timeout": provider_cfg.get("timeout"),
            "has_api_key": bool(provider_cfg.get("api_key")),
        }
        return json.dumps(signature_payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return ""


def get_embedding_service(scope: str = EMBEDDING_SCOPE_MEMORY) -> EmbeddingServiceInterface:
    """Get or build scoped embedding service singleton."""
    normalized_scope = _normalize_scope(scope)
    signature = _build_embedding_service_signature(normalized_scope)
    current_service = _embedding_services.get(normalized_scope)
    current_signature = _embedding_service_signatures.get(normalized_scope)

    if current_service is None or signature != current_signature:
        settings = resolve_embedding_settings(scope=normalized_scope)
        provider = _normalize_text(settings.get("provider")).lower() or "ollama"

        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(provider)
        protocol = provider_cfg.get(
            "protocol",
            "ollama" if provider == "ollama" else "openai_compatible",
        )

        if protocol == "ollama":
            service = OllamaEmbeddingService(
                scope=normalized_scope,
                provider_name=provider,
                model=_normalize_text(settings.get("model")),
                embedding_settings=settings,
            )
        else:
            service = VLLMEmbeddingService(
                scope=normalized_scope,
                provider_name=provider,
                model=_normalize_text(settings.get("model")),
                embedding_settings=settings,
            )

        _embedding_services[normalized_scope] = service
        _embedding_service_signatures[normalized_scope] = signature
        logger.info(
            "Initialized embedding service",
            extra={
                "scope": normalized_scope,
                "provider": provider,
                "model": settings.get("model"),
            },
        )

    return _embedding_services[normalized_scope]


def set_embedding_service(
    service: EmbeddingServiceInterface,
    scope: str = EMBEDDING_SCOPE_MEMORY,
) -> None:
    """Set custom scoped embedding service instance (mainly for tests or overrides)."""
    normalized_scope = _normalize_scope(scope)
    _embedding_services[normalized_scope] = service
    _embedding_service_signatures[normalized_scope] = ""
    logger.info(
        "Set custom embedding service",
        extra={"scope": normalized_scope, "service": type(service).__name__},
    )
