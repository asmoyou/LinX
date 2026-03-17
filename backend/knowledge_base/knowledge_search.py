"""Hybrid knowledge search with Milvus vector + PostgreSQL BM25.

Combines semantic vector search (Milvus) with full-text BM25 search (PostgreSQL)
using Reciprocal Rank Fusion (RRF) for result merging.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import json
import logging
import re
import threading
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple, Union
from uuid import UUID

from knowledge_base.config_utils import load_knowledge_base_config
from knowledge_base.text_normalizer import normalize_knowledge_text
from llm_providers.openai_compatible import build_api_url_candidates, normalize_rerank_scores
from memory_system.embedding_service import get_embedding_service
from memory_system.milvus_connection import get_milvus_connection
from llm_providers.provider_resolver import resolve_provider
from shared.config import get_config

logger = logging.getLogger(__name__)
_CJK_TOKEN_PATTERN = re.compile(r"^[\u3400-\u4dbf\u4e00-\u9fff]+$")


class AwaitableSearchResults(list):
    """List wrapper that can also be awaited in compatibility paths."""

    def __await__(self):
        async def _resolve():
            return self

        return _resolve().__await__()


@dataclass
class SearchFilter:
    """Filter for knowledge search."""

    user_id: str
    user_role: str = "user"
    user_attributes: Optional[dict] = None
    access_levels: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    department_ids: Optional[List[str]] = None
    top_k: int = 10
    min_relevance_score: Optional[float] = None


@dataclass
class SearchResult:
    """Result of knowledge search."""

    chunk_id: str
    document_id: str
    content: str
    similarity_score: float
    chunk_index: int
    metadata: dict
    keywords: Optional[List[str]] = None
    summary: Optional[str] = None
    search_method: str = "hybrid"


class KnowledgeSearch:
    """Hybrid search combining vector similarity and BM25 full-text search."""

    _cross_language_state_lock = threading.Lock()
    _cross_language_fail_until_by_key: Dict[str, float] = {}
    _cross_language_failures_by_key: Dict[str, int] = {}

    def __init__(self):
        """Initialize knowledge search."""
        self.embedding_service = get_embedding_service(scope="knowledge_base")
        self.milvus_conn = get_milvus_connection()
        self.collection_name = "knowledge_embeddings"

        # Load search config
        config = get_config()
        kb_config = load_knowledge_base_config(config)
        search_cfg = kb_config.get("search", {})
        llm_cfg = config.get_section("llm") if config else {}

        self.enable_semantic = search_cfg.get("enable_semantic", True)
        self.enable_fulltext = search_cfg.get("enable_fulltext", True)
        self.semantic_weight = search_cfg.get("semantic_weight", 0.7)
        self.fulltext_weight = search_cfg.get("fulltext_weight", 0.3)
        self.fusion_method = search_cfg.get("fusion_method", "rrf")
        self.rrf_k = search_cfg.get("rrf_k", 60)
        self.semantic_timeout_seconds = search_cfg.get("semantic_timeout_seconds", 8)
        self.embedding_failure_backoff_seconds = float(
            search_cfg.get("embedding_failure_backoff_seconds", 30)
        )
        self.min_relevance_score = float(search_cfg.get("min_relevance_score", 0.3))
        self.hybrid_score_scale = float(search_cfg.get("hybrid_score_scale", 0.02))
        self.keyword_min_rank = float(search_cfg.get("keyword_min_rank", 4.0))
        self.keyword_max_terms = int(search_cfg.get("keyword_max_terms", 16))
        self.rerank_enabled = bool(search_cfg.get("rerank_enabled", True))
        self.rerank_provider = str(search_cfg.get("rerank_provider", "") or "").strip()
        self.rerank_model = str(search_cfg.get("rerank_model", "") or "").strip()
        self.rerank_top_k = int(search_cfg.get("rerank_top_k", 30))
        self.rerank_timeout_seconds = float(search_cfg.get("rerank_timeout_seconds", 10))
        self.rerank_failure_backoff_seconds = float(
            search_cfg.get("rerank_failure_backoff_seconds", 60)
        )
        self.rerank_weight = float(search_cfg.get("rerank_weight", 0.85))
        self.rerank_doc_max_chars = int(search_cfg.get("rerank_doc_max_chars", 1600))

        # Cross-language query expansion for lexical retrieval (RAGFlow-style optional feature).
        self.cross_language_expansion_enabled = bool(
            search_cfg.get("cross_language_expansion_enabled", True)
        )
        raw_languages = search_cfg.get("cross_language_languages", ["en", "zh-CN"])
        if not isinstance(raw_languages, list):
            raw_languages = [raw_languages]
        self.cross_language_languages = [
            str(lang).strip() for lang in raw_languages if str(lang).strip()
        ]
        default_provider = str(llm_cfg.get("default_provider", "ollama") or "ollama").strip()
        self.cross_language_provider = str(
            search_cfg.get("cross_language_provider", default_provider) or default_provider
        ).strip()
        self.cross_language_model = str(search_cfg.get("cross_language_model", "") or "").strip()
        self.cross_language_timeout_seconds = float(
            search_cfg.get("cross_language_timeout_seconds", 4)
        )
        self.cross_language_failure_backoff_seconds = float(
            search_cfg.get("cross_language_failure_backoff_seconds", 60)
        )
        self.cross_language_max_expansions = int(search_cfg.get("cross_language_max_expansions", 2))
        self.cross_language_max_queries = int(search_cfg.get("cross_language_max_queries", 3))
        languages_key = ",".join(self.cross_language_languages) or "-"
        self._cross_language_state_key = f"{self.cross_language_provider}|{self.cross_language_model or '<auto>'}|{languages_key}"

        # Failure backoff timestamps to avoid repeated slow timeouts when upstream is unhealthy.
        self._embedding_fail_until = 0.0
        self._rerank_fail_until = 0.0
        self._cross_language_fail_until = 0.0
        self._cross_language_cache: Dict[str, List[str]] = {}

        logger.info(
            "KnowledgeSearch initialized (hybrid)",
            extra={
                "semantic": self.enable_semantic,
                "fulltext": self.enable_fulltext,
                "fusion": self.fusion_method,
                "semantic_timeout_seconds": self.semantic_timeout_seconds,
                "embedding_failure_backoff_seconds": self.embedding_failure_backoff_seconds,
                "min_relevance_score": self.min_relevance_score,
                "hybrid_score_scale": self.hybrid_score_scale,
                "keyword_min_rank": self.keyword_min_rank,
                "rerank_enabled": self.rerank_enabled,
                "rerank_provider": self.rerank_provider,
                "rerank_model": self.rerank_model,
                "rerank_failure_backoff_seconds": self.rerank_failure_backoff_seconds,
                "cross_language_expansion_enabled": self.cross_language_expansion_enabled,
                "cross_language_languages": self.cross_language_languages,
                "cross_language_provider": self.cross_language_provider,
                "cross_language_model": self.cross_language_model,
            },
        )

    def search(
        self,
        query: str,
        search_filter: Optional[SearchFilter] = None,
        user_id: Optional[UUID] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Search knowledge base using hybrid vector + BM25 search.

        Args:
            query: Search query text
            search_filter: Filter criteria

        Returns:
            List of SearchResult ordered by relevance
        """
        if search_filter is None:
            raw_results = self.milvus_conn.search(query=query, limit=limit)
            return AwaitableSearchResults(
                [
                    {
                        "knowledge_id": hit["entity"]["knowledge_id"],
                        "chunk_text": hit["entity"]["chunk_text"],
                        "relevance_score": max(0.0, 1.0 - float(hit.get("distance", 1.0))),
                    }
                    for hit in raw_results
                ]
            )

        total_start = time.perf_counter()
        stage_ms: Dict[str, float] = {}

        def _stage_elapsed_ms(start_time: float) -> float:
            return round((time.perf_counter() - start_time) * 1000.0, 2)

        try:
            expand_start = time.perf_counter()
            retrieval_queries = self._build_retrieval_queries(query)
            stage_ms["query_expand"] = _stage_elapsed_ms(expand_start)
            vector_query = "\n".join(retrieval_queries) if len(retrieval_queries) > 1 else query
            lexical_query = " ".join(retrieval_queries)
            query_terms = self._extract_query_terms(lexical_query)
            vector_results = []
            bm25_results = []

            # Vector search via Milvus
            if self.enable_semantic:
                vector_start = time.perf_counter()
                vector_results = self._vector_search(vector_query, search_filter)
                stage_ms["vector"] = _stage_elapsed_ms(vector_start)
            else:
                stage_ms["vector"] = 0.0

            # BM25 search via PostgreSQL
            if self.enable_fulltext:
                bm25_start = time.perf_counter()
                bm25_results = self._bm25_search(retrieval_queries, search_filter, query_terms)
                stage_ms["bm25"] = _stage_elapsed_ms(bm25_start)
            else:
                stage_ms["bm25"] = 0.0

            # Merge results
            merge_start = time.perf_counter()
            if vector_results and bm25_results:
                merged = self._rrf_merge(vector_results, bm25_results)
            elif vector_results:
                merged = vector_results
            elif bm25_results:
                merged = bm25_results
            else:
                merged = []
            stage_ms["merge"] = _stage_elapsed_ms(merge_start)

            # Apply permission filtering via access_control module
            permission_start = time.perf_counter()
            filtered_results = self._apply_permission_filter(merged, search_filter)
            stage_ms["permission"] = _stage_elapsed_ms(permission_start)

            rerank_start = time.perf_counter()
            filtered_results, model_rerank_applied = self._rerank_with_model(
                query=query,
                results=filtered_results,
                top_k=search_filter.top_k,
            )
            stage_ms["rerank"] = _stage_elapsed_ms(rerank_start)

            if not model_rerank_applied:
                heuristic_rerank_start = time.perf_counter()
                filtered_results = self._rerank_by_query_overlap(filtered_results, query_terms)
                stage_ms["heuristic_rerank"] = _stage_elapsed_ms(heuristic_rerank_start)
            else:
                stage_ms["heuristic_rerank"] = 0.0

            filtered_results = self._apply_short_query_precision_guard(
                query=query,
                query_terms=query_terms,
                bm25_results=bm25_results,
                results=filtered_results,
            )

            # Apply configurable relevance gate (similar to RAGFlow similarity_threshold).
            relevance_gate_start = time.perf_counter()
            effective_min_score = self._resolve_effective_min_relevance_score(
                search_filter.min_relevance_score,
                model_rerank_applied=model_rerank_applied,
            )
            filtered_results = [
                result
                for result in filtered_results
                if float(result.similarity_score or 0.0) >= effective_min_score
            ]
            stage_ms["relevance_gate"] = _stage_elapsed_ms(relevance_gate_start)

            # Limit to top_k
            topk_slice_start = time.perf_counter()
            filtered_results = filtered_results[: search_filter.top_k]
            stage_ms["topk_slice"] = _stage_elapsed_ms(topk_slice_start)
            stage_ms["total"] = _stage_elapsed_ms(total_start)

            logger.info(
                "Hybrid knowledge search completed",
                extra={
                    "query_length": len(query),
                    "query_variants": len(retrieval_queries),
                    "query_terms": len(query_terms),
                    "vector_hits": len(vector_results),
                    "bm25_hits": len(bm25_results),
                    "min_relevance_score": effective_min_score,
                    "model_rerank_applied": model_rerank_applied,
                    "merged_results": len(filtered_results),
                    "stage_latency_ms": stage_ms,
                },
            )

            return filtered_results

        except Exception as e:
            logger.error(f"Knowledge search failed: {e}", exc_info=True)
            raise

    @staticmethod
    def _normalize_query_key(text: str) -> str:
        """Normalize text into a stable dedup/cache key."""
        return unicodedata.normalize("NFKC", (text or "")).strip().lower()

    def _build_retrieval_queries(self, query: str) -> List[str]:
        """Build query variants for hybrid retrieval."""
        base_query = (query or "").strip()
        if not base_query:
            return []

        variants = [base_query]
        if (
            self.cross_language_expansion_enabled
            and self.cross_language_languages
            and self._should_expand_cross_language(base_query)
        ):
            variants.extend(self._expand_query_cross_language(base_query))

        deduped: List[str] = []
        seen: Set[str] = set()
        for candidate in variants:
            clean = (candidate or "").strip()
            if not clean:
                continue
            if clean != base_query and not self._is_meaningful_query_variant(clean):
                continue
            key = self._normalize_query_key(clean)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(clean)
            if len(deduped) >= max(int(self.cross_language_max_queries), 1):
                break
        return deduped or [base_query]

    @staticmethod
    def _is_meaningful_query_variant(candidate: str) -> bool:
        normalized = unicodedata.normalize("NFKC", (candidate or "")).strip()
        if len(normalized) < 2:
            return False
        if normalized in {"...", "…", "……"}:
            return False
        return bool(re.search(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]", normalized))

    def _should_expand_cross_language(self, query: str) -> bool:
        normalized = unicodedata.normalize("NFKC", (query or "")).strip()
        if len(normalized) < 4:
            return False
        if len(self._extract_query_terms(normalized)) < 2 and not re.search(
            r"[A-Za-z]{3,}", normalized
        ):
            return False
        return True

    def _expand_query_cross_language(self, query: str) -> List[str]:
        """Expand user query into additional languages for lexical retrieval."""
        if max(int(self.cross_language_max_expansions), 0) <= 0:
            return []

        now = time.monotonic()
        with self._cross_language_state_lock:
            shared_fail_until = self._cross_language_fail_until_by_key.get(
                self._cross_language_state_key, 0.0
            )
        effective_fail_until = max(self._cross_language_fail_until, shared_fail_until)
        if now < effective_fail_until:
            logger.debug(
                "Cross-language expansion in backoff window",
                extra={
                    "backoff_remaining_seconds": round(effective_fail_until - now, 2),
                    "provider": self.cross_language_provider,
                },
            )
            return []

        cache_key = self._normalize_query_key(query)
        cached = self._cross_language_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        try:
            provider_cfg = resolve_provider(self.cross_language_provider)
            if not provider_cfg:
                raise ValueError(
                    f"Cross-language provider '{self.cross_language_provider}' is not resolvable"
                )

            protocol = provider_cfg.get(
                "protocol",
                "ollama" if self.cross_language_provider == "ollama" else "openai_compatible",
            )
            model_name = self._resolve_cross_language_model(provider_cfg)
            if not model_name:
                raise ValueError(
                    "Cross-language expansion model is not configured and cannot be auto-resolved"
                )

            prompt = (
                "You are a multilingual retrieval query expander.\n"
                "Rewrite the input query into the target languages while preserving intent.\n"
                'Return JSON only: {"queries": ["..."]}.\n'
                "No explanations, no markdown.\n\n"
                f"Input query: {query}\n"
                f"Target languages: {', '.join(self.cross_language_languages)}\n"
            )
            raw_response = self._call_cross_language_model(
                protocol=str(protocol),
                base_url=str(provider_cfg.get("base_url", "")).strip(),
                api_key=provider_cfg.get("api_key"),
                model_name=model_name,
                prompt=prompt,
            )

            parsed = self._parse_cross_language_queries(raw_response)
            expansions: List[str] = []
            base_key = self._normalize_query_key(query)
            seen: Set[str] = {base_key}
            for candidate in parsed:
                clean = candidate.strip()
                if not clean:
                    continue
                key = self._normalize_query_key(clean)
                if key in seen:
                    continue
                seen.add(key)
                expansions.append(clean)
                if len(expansions) >= max(int(self.cross_language_max_expansions), 1):
                    break

            self._cross_language_fail_until = 0.0
            with self._cross_language_state_lock:
                self._cross_language_fail_until_by_key[self._cross_language_state_key] = 0.0
                self._cross_language_failures_by_key[self._cross_language_state_key] = 0
            self._cross_language_cache[cache_key] = expansions
            # Keep cache bounded.
            if len(self._cross_language_cache) > 256:
                oldest_key = next(iter(self._cross_language_cache))
                self._cross_language_cache.pop(oldest_key, None)

            return expansions
        except Exception as e:
            base_backoff_seconds = max(float(self.cross_language_failure_backoff_seconds), 1.0)
            error_text = str(e).lower()
            timeout_like = "timed out" in error_text or "timeout" in error_text
            with self._cross_language_state_lock:
                failure_count = (
                    self._cross_language_failures_by_key.get(self._cross_language_state_key, 0) + 1
                )
                self._cross_language_failures_by_key[self._cross_language_state_key] = failure_count

            if timeout_like:
                # Repeated timeout means the cross-language model is unhealthy or too slow.
                # Apply a longer shared backoff to avoid blocking each fresh session.
                timeout_multiplier = min(2 ** (failure_count - 1), 8)
                effective_backoff_seconds = max(base_backoff_seconds * timeout_multiplier, 300.0)
            else:
                effective_backoff_seconds = base_backoff_seconds

            fail_until = now + effective_backoff_seconds
            self._cross_language_fail_until = fail_until
            with self._cross_language_state_lock:
                self._cross_language_fail_until_by_key[self._cross_language_state_key] = fail_until
            logger.warning(
                "Cross-language query expansion failed; fallback to original query",
                extra={
                    "error": str(e),
                    "provider": self.cross_language_provider,
                    "model": self.cross_language_model,
                    "backoff_seconds": effective_backoff_seconds,
                    "failure_count": failure_count,
                    "timeout_like": timeout_like,
                },
            )
            return []

    def _resolve_cross_language_model(self, provider_cfg: dict) -> str:
        """Resolve model name for cross-language expansion."""
        provider_models = provider_cfg.get("models") or []
        if isinstance(provider_models, dict):
            provider_models = list(provider_models.values())
        if isinstance(provider_models, str):
            provider_models = [provider_models]

        candidates = [str(m).strip() for m in provider_models if str(m).strip()]

        configured_model = str(self.cross_language_model or "").strip()
        if configured_model:
            if not candidates:
                return configured_model

            if configured_model in candidates:
                return configured_model

            normalized_configured = self._normalize_model_name_for_match(configured_model)
            for candidate in candidates:
                if self._normalize_model_name_for_match(candidate) == normalized_configured:
                    return candidate

            fallback_model = self._select_cross_language_fallback_model(candidates)
            if fallback_model:
                logger.warning(
                    "Configured cross-language model not found in provider model list; "
                    "fallback to provider available model",
                    extra={
                        "provider": self.cross_language_provider,
                        "configured_model": configured_model,
                        "fallback_model": fallback_model,
                    },
                )
                return fallback_model

            return configured_model

        if not candidates:
            return ""

        return self._select_cross_language_fallback_model(candidates)

    @staticmethod
    def _normalize_model_name_for_match(model_name: str) -> str:
        """Normalize model identifier for loose comparison."""
        normalized = (model_name or "").strip().lower()
        if normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized

    @staticmethod
    def _select_cross_language_fallback_model(candidates: List[str]) -> str:
        """Select a likely chat-capable model from provider candidates."""
        if not candidates:
            return ""

        non_chat_hints = ("embed", "embedding", "rerank")
        for candidate in candidates:
            lowered = candidate.lower()
            if any(hint in lowered for hint in non_chat_hints):
                continue
            return candidate
        return candidates[0]

    @staticmethod
    def _normalize_model_response(content: object) -> str:
        """Normalize model response payload to plain text."""
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text_parts.append(part.get("text", ""))
            return "".join(text_parts).strip()
        return (str(content) if content is not None else "").strip()

    def _call_cross_language_model(
        self,
        protocol: str,
        base_url: str,
        api_key: Optional[str],
        model_name: str,
        prompt: str,
    ) -> str:
        """Call provider to generate cross-language query variants."""
        timeout_seconds = max(float(self.cross_language_timeout_seconds), 1.0)

        if protocol == "ollama":
            import requests

            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            payload = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.0, "num_predict": 256},
            }
            response = requests.post(
                f"{base_url.rstrip('/')}/api/generate",
                json=payload,
                headers=headers,
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            return str(body.get("response") or body.get("thinking") or "")

        from langchain_core.messages import HumanMessage

        from llm_providers.custom_openai_provider import CustomOpenAIChat

        llm = CustomOpenAIChat(
            base_url=base_url,
            model=model_name,
            api_key=api_key,
            temperature=0.0,
            max_tokens=384,
            timeout=max(2, min(int(timeout_seconds), 30)),
            streaming=False,
        )
        result = llm.invoke([HumanMessage(content=prompt)])
        return self._normalize_model_response(getattr(result, "content", ""))

    @staticmethod
    def _parse_cross_language_queries(response_text: str) -> List[str]:
        """Parse model output into query list."""
        text = (response_text or "").strip()
        if not text:
            return []

        # Remove markdown fences when model does not strictly follow instructions.
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text, flags=re.IGNORECASE)

        def _extract_from_obj(obj: object) -> List[str]:
            if isinstance(obj, dict):
                for key in ("queries", "translations", "results", "items"):
                    value = obj.get(key)
                    if isinstance(value, list):
                        return [str(item).strip() for item in value if str(item).strip()]
                return []
            if isinstance(obj, list):
                return [str(item).strip() for item in obj if str(item).strip()]
            return []

        json_candidates = [text]
        if "{" in text and "}" in text:
            json_candidates.append(text[text.find("{") : text.rfind("}") + 1])
        if "[" in text and "]" in text:
            json_candidates.append(text[text.find("[") : text.rfind("]") + 1])

        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            extracted = _extract_from_obj(parsed)
            meaningful = [
                item for item in extracted if KnowledgeSearch._is_meaningful_query_variant(item)
            ]
            if meaningful:
                return meaningful

        # Fallback to delimiter-based parsing.
        items = re.split(r"(?:\n+|###|===|；|;)", text)
        cleaned: List[str] = []
        for item in items:
            candidate = item.strip().strip("-").strip()
            if not candidate:
                continue
            lowered = candidate.lower()
            if lowered.startswith("output"):
                continue
            if KnowledgeSearch._is_meaningful_query_variant(candidate):
                cleaned.append(candidate)
        return cleaned

    def _generate_query_embedding(self, query: str) -> Optional[List[float]]:
        """Generate embedding with a strict timeout for search latency control."""
        now = time.monotonic()
        start = time.perf_counter()
        if now < self._embedding_fail_until:
            logger.warning(
                "Embedding provider in backoff window, skipping vector retrieval",
                extra={
                    "backoff_remaining_seconds": round(self._embedding_fail_until - now, 2),
                    "provider": type(self.embedding_service).__name__,
                },
            )
            return None

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self.embedding_service.generate_embedding, query)

        try:
            timeout = max(float(self.semantic_timeout_seconds), 1.0)
            embedding = future.result(timeout=timeout)
            self._embedding_fail_until = 0.0
            logger.info(
                "Embedding generated for retrieval query",
                extra={
                    "provider": type(self.embedding_service).__name__,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000.0, 2),
                    "query_length": len(query or ""),
                },
            )
            return embedding
        except FuturesTimeoutError:
            future.cancel()
            self._embedding_fail_until = now + max(self.embedding_failure_backoff_seconds, 1.0)
            logger.warning(
                "Embedding generation timed out, falling back to non-vector retrieval",
                extra={
                    "timeout_seconds": self.semantic_timeout_seconds,
                    "backoff_seconds": self.embedding_failure_backoff_seconds,
                    "elapsed_ms": round((time.perf_counter() - start) * 1000.0, 2),
                },
            )
            return None
        except Exception as e:
            self._embedding_fail_until = now + max(self.embedding_failure_backoff_seconds, 1.0)
            logger.warning(
                "Embedding generation failed, skipping vector search",
                extra={
                    "error": str(e),
                    "elapsed_ms": round((time.perf_counter() - start) * 1000.0, 2),
                    "provider": type(self.embedding_service).__name__,
                },
            )
            return None
        finally:
            # Do not block current request on a stuck worker thread.
            executor.shutdown(wait=False, cancel_futures=True)

    def _vector_search(
        self,
        query: str,
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Perform vector similarity search via Milvus.

        Args:
            query: Search query
            search_filter: Filter criteria

        Returns:
            List of SearchResult from vector search
        """
        try:
            # Generate query embedding
            query_embedding = self._generate_query_embedding(query)
            if query_embedding is None:
                return []

            # Build Milvus search expression with RBAC-aware scope.
            from access_control.knowledge_filter import build_milvus_filter_expr
            from access_control.permissions import CurrentUser
            from access_control.rbac import Action

            current_user = CurrentUser(
                user_id=search_filter.user_id,
                username="knowledge_search_user",
                role=search_filter.user_role or "user",
            )
            additional_filters = []
            if search_filter.document_ids:
                doc_ids_str = '", "'.join(search_filter.document_ids)
                additional_filters.append(f'knowledge_id in ["{doc_ids_str}"]')

            expr = build_milvus_filter_expr(
                current_user=current_user,
                action=Action.READ,
                user_attributes=search_filter.user_attributes,
                additional_filters=" and ".join(additional_filters) if additional_filters else None,
            )
            # Empty expression means unrestricted for privileged roles.
            expr = expr or None

            # Search in Milvus
            from pymilvus import Collection

            collection = Collection(self.collection_name)

            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=search_filter.top_k * 2,  # Fetch more for fusion
                expr=expr,
                output_fields=[
                    "knowledge_id",
                    "content",
                    "chunk_index",
                    "owner_user_id",
                    "access_level",
                ],
                timeout=max(float(self.semantic_timeout_seconds), 1.0),
            )

            # Convert to SearchResult objects
            search_results = []
            for hits in results:
                for hit in hits:
                    content, summary = self._normalize_result_texts(
                        content=hit.entity.get("content"),
                        summary=None,
                    )
                    search_results.append(
                        SearchResult(
                            chunk_id=str(hit.id),
                            document_id=hit.entity.get("knowledge_id"),
                            content=content,
                            similarity_score=1.0
                            / (1.0 + hit.distance),  # Convert distance to similarity
                            chunk_index=hit.entity.get("chunk_index", 0),
                            metadata={
                                "owner_user_id": hit.entity.get("owner_user_id"),
                                "access_level": hit.entity.get("access_level", "private"),
                            },
                            summary=summary,
                            search_method="vector",
                        )
                    )

            return search_results

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []

    def _bm25_search(
        self,
        query: Union[str, List[str]],
        search_filter: SearchFilter,
        query_terms: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """Perform BM25 full-text search via PostgreSQL tsvector.

        Args:
            query: Search query or query variants
            search_filter: Filter criteria

        Returns:
            List of SearchResult from BM25 search
        """
        queries = [query] if isinstance(query, str) else list(query or [])
        queries = [q.strip() for q in queries if isinstance(q, str) and q.strip()]
        if not queries:
            return []
        queries = queries[: max(int(self.cross_language_max_queries), 1)]

        merged: Dict[str, SearchResult] = {}
        for q in queries:
            for row in self._bm25_search_single(q, search_filter):
                existing = merged.get(row.chunk_id)
                if existing is None or float(row.similarity_score) > float(
                    existing.similarity_score
                ):
                    row.metadata = dict(row.metadata or {})
                    if len(queries) > 1:
                        row.metadata["matched_query"] = q
                    merged[row.chunk_id] = row

        search_results = sorted(
            merged.values(),
            key=lambda item: float(item.similarity_score or 0.0),
            reverse=True,
        )

        # If BM25 under-retrieves (especially for cross-language phrase mismatch),
        # supplement with lightweight keyword fallback over all query variants.
        target_hits = search_filter.top_k * 2
        if len(search_results) < target_hits:
            fallback_results = self._keyword_fallback_search_multi(
                queries=queries,
                query_terms=query_terms,
                search_filter=search_filter,
                exclude_chunk_ids={r.chunk_id for r in search_results},
                limit=target_hits - len(search_results),
            )
            for row in fallback_results:
                existing = merged.get(row.chunk_id)
                if existing is None or float(row.similarity_score) > float(
                    existing.similarity_score
                ):
                    merged[row.chunk_id] = row
            search_results = sorted(
                merged.values(),
                key=lambda item: float(item.similarity_score or 0.0),
                reverse=True,
            )

        return search_results[:target_hits]

    def _bm25_search_single(
        self,
        query: str,
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Execute one BM25 query and return ranked chunk matches."""
        try:
            from sqlalchemy import func, text

            from access_control.knowledge_filter import filter_knowledge_query
            from access_control.permissions import CurrentUser
            from access_control.rbac import Action
            from database.connection import get_db_session
            from database.models import KnowledgeChunk, KnowledgeItem

            with get_db_session() as session:
                # Build ts_query from search terms
                ts_query = func.plainto_tsquery("pg_catalog.simple", query)

                # Build query with join to knowledge_items for access filtering
                q = (
                    session.query(
                        KnowledgeChunk.chunk_id,
                        KnowledgeChunk.knowledge_id,
                        KnowledgeChunk.content,
                        KnowledgeChunk.chunk_index,
                        KnowledgeChunk.keywords,
                        KnowledgeChunk.summary,
                        KnowledgeChunk.chunk_metadata,
                        KnowledgeItem.owner_user_id,
                        KnowledgeItem.access_level,
                        func.ts_rank(KnowledgeChunk.search_vector, ts_query).label("rank"),
                    )
                    .join(
                        KnowledgeItem,
                        KnowledgeItem.knowledge_id == KnowledgeChunk.knowledge_id,
                    )
                    .filter(KnowledgeChunk.search_vector.op("@@")(ts_query))
                )
                current_user = CurrentUser(
                    user_id=search_filter.user_id,
                    username="knowledge_search_user",
                    role=search_filter.user_role or "user",
                )
                q = filter_knowledge_query(
                    q,
                    current_user=current_user,
                    action=Action.READ,
                    user_attributes=search_filter.user_attributes,
                )

                # Apply document filter
                if search_filter.document_ids:
                    doc_uuids = []
                    for doc_id in search_filter.document_ids:
                        try:
                            doc_uuids.append(UUID(doc_id))
                        except ValueError:
                            continue

                    if not doc_uuids:
                        return []

                    q = q.filter(KnowledgeChunk.knowledge_id.in_(doc_uuids))

                # Apply department filter
                if search_filter.department_ids:
                    dept_uuids = []
                    for department_id in search_filter.department_ids:
                        try:
                            dept_uuids.append(UUID(department_id))
                        except ValueError:
                            continue

                    if dept_uuids:
                        q = q.filter(KnowledgeItem.department_id.in_(dept_uuids))

                # Order by BM25 rank
                q = q.order_by(text("rank DESC")).limit(search_filter.top_k * 2)
                rows = q.all()

            # Convert to SearchResult
            search_results = []
            for row in rows:
                row_metadata = dict(row.chunk_metadata or {})
                row_metadata.setdefault("owner_user_id", str(row.owner_user_id))
                row_metadata.setdefault("access_level", row.access_level or "private")
                content, summary = self._normalize_result_texts(
                    content=row.content,
                    summary=row.summary,
                )
                search_results.append(
                    SearchResult(
                        chunk_id=str(row.chunk_id),
                        document_id=str(row.knowledge_id),
                        content=content,
                        similarity_score=float(row.rank),
                        chunk_index=row.chunk_index,
                        metadata=row_metadata,
                        keywords=row.keywords,
                        summary=summary,
                        search_method="bm25",
                    )
                )
            return search_results

        except Exception as e:
            logger.error(f"BM25 search failed for query '{query}': {e}", exc_info=True)
            return []

    def _keyword_fallback_search_multi(
        self,
        queries: List[str],
        query_terms: Optional[List[str]],
        search_filter: SearchFilter,
        exclude_chunk_ids: Optional[Set[str]] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Run keyword fallback over multiple query variants and merge top results."""
        if limit <= 0:
            return []

        merged: Dict[str, SearchResult] = {}
        excluded = set(exclude_chunk_ids or set())

        base_terms = [t for t in (query_terms or []) if t]
        for q in queries:
            per_query_terms = self._extract_query_terms(q)
            terms = list(dict.fromkeys(base_terms + per_query_terms))[
                : max(self.keyword_max_terms, 1)
            ]
            rows = self._keyword_fallback_search(
                query=q,
                query_terms=terms,
                search_filter=search_filter,
                exclude_chunk_ids=excluded.union(set(merged.keys())),
                limit=limit,
            )
            for row in rows:
                existing = merged.get(row.chunk_id)
                if existing is None or float(row.similarity_score) > float(
                    existing.similarity_score
                ):
                    merged[row.chunk_id] = row
                if len(merged) >= limit:
                    break
            if len(merged) >= limit:
                break

        return sorted(
            merged.values(),
            key=lambda item: float(item.similarity_score or 0.0),
            reverse=True,
        )[:limit]

    def _extract_query_terms(self, query: str) -> List[str]:
        """Extract normalized query terms for lexical matching and reranking."""
        normalized_query = unicodedata.normalize("NFKC", (query or "")).strip().lower()
        if len(normalized_query) < 2:
            return []

        stop_terms = {
            "如何",
            "怎么",
            "怎样",
            "请问",
            "一下",
            "一下子",
            "可以",
            "是否",
            "这个",
            "那个",
            "what",
            "how",
            "why",
            "who",
            "where",
            "when",
            "the",
            "and",
            "for",
            "with",
            "from",
            "that",
            "this",
            "are",
            "is",
            "to",
            "of",
            "in",
            "on",
        }
        cjk_question_terms = {"如何", "怎么", "怎样", "请问"}
        cjk_question_chars = {"如", "何", "怎", "样", "请", "问"}

        raw_terms: Set[str] = set()

        def _is_meaningful_term(term: str) -> bool:
            return bool(re.search(r"[A-Za-z0-9\u3400-\u4dbf\u4e00-\u9fff]", term))

        split_terms = re.split(
            r"[\s,，。！？!?;；:：/\\|()\[\]{}【】\"'“”‘’]+",
            normalized_query,
        )
        for term in split_terms:
            term = term.strip()
            if len(term) >= 2 and term not in stop_terms and _is_meaningful_term(term):
                raw_terms.add(term)

        # Preserve contiguous Chinese fragments and generate short n-grams for phrase recall.
        cjk_fragments = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", normalized_query)
        for fragment in cjk_fragments:
            if len(fragment) >= 2 and fragment not in stop_terms and _is_meaningful_term(fragment):
                raw_terms.add(fragment)
            for n in (2, 3):
                if len(fragment) < n:
                    continue
                for idx in range(len(fragment) - n + 1):
                    gram = fragment[idx : idx + n]
                    if any(question_term in gram for question_term in cjk_question_terms):
                        continue
                    if gram and gram[0] in cjk_question_chars:
                        continue
                    if len(gram) >= 2 and gram not in stop_terms and _is_meaningful_term(gram):
                        raw_terms.add(gram)

        if (
            normalized_query not in stop_terms
            and len(normalized_query) >= 2
            and _is_meaningful_term(normalized_query)
        ):
            raw_terms.add(normalized_query)

        # Longer phrases first to favor specific matches.
        return sorted(raw_terms, key=lambda item: (-len(item), item))[:24]

    def _keyword_fallback_search(
        self,
        query: str,
        query_terms: List[str],
        search_filter: SearchFilter,
        exclude_chunk_ids: Optional[Set[str]] = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        """Fallback lexical retrieval for cases where BM25 under-retrieves."""
        if limit <= 0:
            return []

        try:
            from sqlalchemy import case, func, literal, or_, text

            from access_control.knowledge_filter import filter_knowledge_query
            from access_control.permissions import CurrentUser
            from access_control.rbac import Action
            from database.connection import get_db_session
            from database.models import KnowledgeChunk, KnowledgeItem

            terms = [t.strip() for t in query_terms if len(t.strip()) >= 2][
                : max(self.keyword_max_terms, 1)
            ]
            full_query = unicodedata.normalize("NFKC", (query or "")).strip().lower()
            if len(full_query) >= 2 and full_query not in terms:
                terms.insert(0, full_query)

            if not terms:
                return []

            # Parse optional filters.
            doc_uuids = []
            if search_filter.document_ids:
                for doc_id in search_filter.document_ids:
                    try:
                        doc_uuids.append(UUID(doc_id))
                    except ValueError:
                        continue
                if not doc_uuids:
                    return []

            dept_uuids = []
            if search_filter.department_ids:
                for department_id in search_filter.department_ids:
                    try:
                        dept_uuids.append(UUID(department_id))
                    except ValueError:
                        continue

            exclude_uuids = []
            if exclude_chunk_ids:
                for chunk_id in exclude_chunk_ids:
                    try:
                        exclude_uuids.append(UUID(chunk_id))
                    except ValueError:
                        continue

            summary_expr = func.coalesce(KnowledgeChunk.summary, "")
            keyword_expr = func.coalesce(func.array_to_string(KnowledgeChunk.keywords, " "), "")
            title_expr = func.coalesce(KnowledgeItem.title, "")

            score_expr = literal(0.0)
            match_conditions = []
            term_hits_expr = literal(0)
            used_terms = set()
            for term in terms:
                term = term.strip()
                if len(term) < 2 or term in used_terms:
                    continue
                used_terms.add(term)
                pattern = f"%{term}%"
                is_full_query = term == full_query

                # Phrase match gets higher weight than short token matches.
                content_weight = 6.0 if is_full_query else 2.0
                summary_weight = 4.0 if is_full_query else 1.5
                keyword_weight = 5.0 if is_full_query else 2.5
                title_weight = 4.0 if is_full_query else 2.0

                term_match_expr = or_(
                    KnowledgeChunk.content.ilike(pattern),
                    summary_expr.ilike(pattern),
                    keyword_expr.ilike(pattern),
                    title_expr.ilike(pattern),
                )
                match_conditions.append(term_match_expr)
                term_hits_expr = term_hits_expr + case((term_match_expr, 1), else_=0)
                score_expr = (
                    score_expr
                    + case((KnowledgeChunk.content.ilike(pattern), content_weight), else_=0.0)
                    + case((summary_expr.ilike(pattern), summary_weight), else_=0.0)
                    + case((keyword_expr.ilike(pattern), keyword_weight), else_=0.0)
                    + case((title_expr.ilike(pattern), title_weight), else_=0.0)
                )

            rank_expr = score_expr.label("rank")
            term_hits_label = term_hits_expr.label("term_hits")
            min_term_hits = 1 if len(terms) <= 2 else 2

            with get_db_session() as session:
                q = session.query(
                    KnowledgeChunk.chunk_id,
                    KnowledgeChunk.knowledge_id,
                    KnowledgeChunk.content,
                    KnowledgeChunk.chunk_index,
                    KnowledgeChunk.keywords,
                    KnowledgeChunk.summary,
                    KnowledgeChunk.chunk_metadata,
                    KnowledgeItem.owner_user_id,
                    KnowledgeItem.access_level,
                    rank_expr,
                    term_hits_label,
                ).join(
                    KnowledgeItem,
                    KnowledgeItem.knowledge_id == KnowledgeChunk.knowledge_id,
                )
                current_user = CurrentUser(
                    user_id=search_filter.user_id,
                    username="knowledge_search_user",
                    role=search_filter.user_role or "user",
                )
                q = filter_knowledge_query(
                    q,
                    current_user=current_user,
                    action=Action.READ,
                    user_attributes=search_filter.user_attributes,
                )

                if doc_uuids:
                    q = q.filter(KnowledgeChunk.knowledge_id.in_(doc_uuids))

                if dept_uuids:
                    q = q.filter(KnowledgeItem.department_id.in_(dept_uuids))

                if exclude_uuids:
                    q = q.filter(~KnowledgeChunk.chunk_id.in_(exclude_uuids))

                if match_conditions:
                    q = q.filter(or_(*match_conditions))

                rows = (
                    q.order_by(text("rank DESC"), KnowledgeChunk.chunk_index.asc())
                    .limit(limit * 2)
                    .all()
                )

            fallback_results = []
            for row in rows:
                rank = float(row.rank or 0.0)
                term_hits = int(row.term_hits or 0)
                if rank < self.keyword_min_rank or term_hits < min_term_hits:
                    continue
                row_metadata = dict(row.chunk_metadata or {})
                row_metadata.setdefault("owner_user_id", str(row.owner_user_id))
                row_metadata.setdefault("access_level", row.access_level or "private")
                row_metadata["keyword_rank"] = rank
                row_metadata["keyword_term_hits"] = term_hits
                content, summary = self._normalize_result_texts(
                    content=row.content,
                    summary=row.summary,
                )
                fallback_results.append(
                    SearchResult(
                        chunk_id=str(row.chunk_id),
                        document_id=str(row.knowledge_id),
                        content=content,
                        similarity_score=rank,
                        chunk_index=row.chunk_index,
                        metadata=row_metadata,
                        keywords=row.keywords,
                        summary=summary,
                        search_method="keyword",
                    )
                )
                if len(fallback_results) >= limit:
                    break

            return fallback_results

        except Exception as e:
            logger.warning(f"Keyword fallback search failed: {e}")
            return []

    def _normalize_result_score_for_blend(self, result: SearchResult) -> float:
        """Normalize result score into [0, 1] before blending with rerank."""
        raw_score = max(float(result.similarity_score or 0.0), 0.0)
        method = (result.search_method or "").lower()
        if method == "vector":
            return min(raw_score, 1.0)
        if method == "bm25":
            return raw_score / (1.0 + raw_score)
        if method == "keyword":
            keyword_scale = max(self.keyword_min_rank * 2.0, 1.0)
            return min(raw_score / keyword_scale, 1.0)
        if method == "hybrid":
            hybrid_scale = max(self.hybrid_score_scale, 1e-6)
            return min(raw_score / hybrid_scale, 1.0)
        return raw_score / (1.0 + raw_score)

    def _resolve_effective_min_relevance_score(
        self,
        requested_min_score: Optional[float],
        *,
        model_rerank_applied: bool,
    ) -> float:
        """Resolve the final relevance floor for one search request."""
        effective = self.min_relevance_score
        if requested_min_score is not None:
            try:
                effective = float(requested_min_score)
            except (TypeError, ValueError):
                effective = self.min_relevance_score
        if not model_rerank_applied:
            effective = max(effective, self.min_relevance_score)
        return max(0.0, min(effective, 1.0))

    def _rerank_with_model(
        self,
        query: str,
        results: List[SearchResult],
        top_k: int,
    ) -> Tuple[List[SearchResult], bool]:
        """Apply model-based rerank when configured, otherwise return original order."""
        if (
            not self.rerank_enabled
            or not self.rerank_provider
            or not self.rerank_model
            or len(results) <= 1
        ):
            return results, False

        provider_cfg = resolve_provider(self.rerank_provider)
        base_url = str(provider_cfg.get("base_url") or "").strip()
        if not base_url:
            logger.warning(
                "Rerank provider not resolvable, fallback to heuristic rerank",
                extra={"rerank_provider": self.rerank_provider},
            )
            return results, False

        candidate_limit = min(
            len(results),
            max(int(self.rerank_top_k), int(top_k), 10),
        )
        candidates = results[:candidate_limit]
        doc_char_limit = self._effective_rerank_doc_max_chars(candidate_limit)
        documents = [
            self._build_rerank_document(candidate)[:doc_char_limit] for candidate in candidates
        ]
        rerank_items = self._call_rerank_api(
            base_url=base_url,
            api_key=provider_cfg.get("api_key"),
            query=query,
            documents=documents,
        )
        if not rerank_items:
            return results, False

        rerank_weight = min(max(self.rerank_weight, 0.0), 1.0)
        base_weight = 1.0 - rerank_weight

        reranked_candidates: List[SearchResult] = []
        for candidate_rank, (doc_index, rerank_score) in enumerate(rerank_items):
            if doc_index < 0 or doc_index >= len(candidates):
                continue

            candidate = candidates[doc_index]
            candidate.metadata = dict(candidate.metadata or {})
            candidate.metadata["rerank_score"] = round(float(rerank_score), 4)
            candidate.metadata["rerank_model"] = self.rerank_model
            candidate.metadata["rerank_provider"] = self.rerank_provider
            base_score = self._normalize_result_score_for_blend(candidate)
            candidate.metadata["base_score"] = round(float(base_score), 4)
            candidate.similarity_score = (
                rerank_weight * float(rerank_score) + base_weight * base_score
            )
            reranked_candidates.append(candidate)

        if not reranked_candidates:
            return results, False

        # Keep any candidate missing rerank output at the tail in original order.
        reranked_ids = {item.chunk_id for item in reranked_candidates}
        reranked_candidates.extend(
            [item for item in candidates if item.chunk_id not in reranked_ids]
        )
        reranked_candidates.extend(results[candidate_limit:])
        return reranked_candidates, True

    @staticmethod
    def _sanitize_rerank_text(text: str) -> str:
        """Remove obvious transcription/analysis scaffolding before rerank."""
        raw = normalize_knowledge_text(text)
        if not raw:
            return ""

        dropped_prefixes = (
            "okay, let's see",
            "let's see",
            "the user wants me to",
            "so in markdown",
            "let's format",
            "text starts with",
            "would be in chinese as well",
        )
        lines: List[str] = []
        for line in raw.splitlines():
            normalized_line = line.strip().lower()
            if normalized_line.startswith(dropped_prefixes):
                continue
            lines.append(line)

        return "\n".join(lines).strip()

    @staticmethod
    def _normalize_result_texts(
        *,
        content: Optional[str],
        summary: Optional[str],
    ) -> Tuple[str, Optional[str]]:
        normalized_content = normalize_knowledge_text(content)
        normalized_summary = normalize_knowledge_text(summary)
        if normalized_summary and normalized_summary == normalized_content:
            normalized_summary = None
        return normalized_content or str(content or ""), normalized_summary or None

    def _build_rerank_document(self, result: SearchResult) -> str:
        """Build compact rerank input text from chunk content and enrichment fields."""
        parts = [self._sanitize_rerank_text(result.content or "")]
        if result.summary:
            parts.append(f"Summary: {self._sanitize_rerank_text(result.summary)}")
        if result.keywords:
            parts.append("Keywords: " + ", ".join(result.keywords))

        text = "\n".join(part.strip() for part in parts if part and part.strip())
        max_chars = max(int(self.rerank_doc_max_chars), 256)
        return text[:max_chars]

    def _effective_rerank_doc_max_chars(self, candidate_limit: int) -> int:
        """Return configured rerank document size without implicit extra truncation."""
        del candidate_limit
        return max(int(self.rerank_doc_max_chars), 256)

    def _call_rerank_api(
        self,
        base_url: str,
        api_key: Optional[str],
        query: str,
        documents: List[str],
    ) -> List[Tuple[int, float]]:
        """Call OpenAI-compatible rerank API and return ordered (doc_index, score)."""
        if not documents:
            return []

        now = time.monotonic()
        if now < self._rerank_fail_until:
            logger.warning(
                "Rerank provider in backoff window, skipping model rerank",
                extra={
                    "backoff_remaining_seconds": round(self._rerank_fail_until - now, 2),
                    "rerank_provider": self.rerank_provider,
                },
            )
            return []

        try:
            import requests

            total_timeout = max(float(self.rerank_timeout_seconds), 1.0)
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            payload = {
                "model": self.rerank_model,
                "query": query,
                "documents": documents,
                "top_n": len(documents),
            }
            urls_to_try = build_api_url_candidates(base_url, "/rerank")

            last_error = None
            for attempt_index, url in enumerate(urls_to_try):
                attempt_start = time.perf_counter()
                attempt_timeout = (
                    total_timeout
                    if attempt_index == 0
                    else min(
                        max(total_timeout / 3.0, 1.0),
                        3.0,
                    )
                )
                try:
                    response = requests.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=attempt_timeout,
                    )
                    if response.status_code != 200:
                        last_error = f"{url} -> HTTP {response.status_code}: {response.text[:200]}"
                        continue
                    data = response.json()
                    parsed = self._parse_rerank_response(data, len(documents))
                    if parsed:
                        self._rerank_fail_until = 0.0
                        logger.info(
                            "Rerank API call succeeded",
                            extra={
                                "url": url,
                                "elapsed_ms": round(
                                    (time.perf_counter() - attempt_start) * 1000.0, 2
                                ),
                                "rerank_provider": self.rerank_provider,
                                "result_count": len(parsed),
                            },
                        )
                        return parsed
                    last_error = f"{url} -> empty/invalid rerank response"
                except Exception as call_err:
                    last_error = f"{url} -> {call_err}"

            if last_error:
                self._rerank_fail_until = now + max(self.rerank_failure_backoff_seconds, 1.0)
                logger.warning(
                    "Rerank API failed, fallback to heuristic rerank",
                    extra={
                        "error": last_error,
                        "total_timeout_seconds": total_timeout,
                        "per_attempt_timeout_seconds": total_timeout,
                        "backoff_seconds": self.rerank_failure_backoff_seconds,
                    },
                )
            return []

        except Exception as e:
            self._rerank_fail_until = now + max(self.rerank_failure_backoff_seconds, 1.0)
            logger.warning(f"Unexpected rerank invocation failure: {e}")
            return []

    def _parse_rerank_response(
        self,
        response_data: object,
        doc_count: int,
    ) -> List[Tuple[int, float]]:
        """Parse rerank API response into ordered (index, score) pairs."""
        if isinstance(response_data, str):
            try:
                response_data = json.loads(response_data)
            except Exception:
                return []

        if not isinstance(response_data, dict):
            return []

        raw_results = response_data.get("results")
        if not isinstance(raw_results, list):
            raw_results = response_data.get("data")
        if not isinstance(raw_results, list):
            raw_results = response_data.get("output")
            if isinstance(raw_results, str):
                try:
                    wrapped_output = json.loads(raw_results)
                except Exception:
                    wrapped_output = None
                if isinstance(wrapped_output, dict):
                    raw_results = wrapped_output.get("results") or wrapped_output.get("data")
        if not isinstance(raw_results, list):
            return []

        parsed: List[Tuple[int, float]] = []
        for idx, item in enumerate(raw_results):
            if isinstance(item, dict):
                raw_index = (
                    item.get("index")
                    if item.get("index") is not None
                    else item.get("document_index")
                )
                if raw_index is None and isinstance(item.get("document"), dict):
                    raw_index = item.get("document", {}).get("index")
                try:
                    doc_index = int(raw_index if raw_index is not None else idx)
                except (TypeError, ValueError):
                    continue

                raw_score = (
                    item.get("relevance_score")
                    if item.get("relevance_score") is not None
                    else item.get("score")
                )
                if raw_score is None:
                    raw_score = item.get("similarity", 0.0)
            else:
                doc_index = idx
                raw_score = item

            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue

            if doc_index < 0 or doc_index >= doc_count:
                continue
            parsed.append((doc_index, score))

        return normalize_rerank_scores(parsed)

    def _rerank_by_query_overlap(
        self,
        results: List[SearchResult],
        query_terms: List[str],
    ) -> List[SearchResult]:
        """Blend base score with query-term coverage to improve semantic intent matching."""
        if not results or not query_terms:
            return results

        terms = [t.lower() for t in query_terms if len(t) >= 2][:16]
        if not terms:
            return results

        def _method_score(result: SearchResult) -> float:
            raw_score = max(float(result.similarity_score or 0.0), 0.0)
            method = (result.search_method or "").lower()
            if method == "vector":
                return min(raw_score, 1.0)
            if method == "bm25":
                return raw_score / (1.0 + raw_score)
            if method == "keyword":
                keyword_scale = max(self.keyword_min_rank * 2.0, 1.0)
                return min(raw_score / keyword_scale, 1.0)
            if method == "hybrid":
                hybrid_scale = max(self.hybrid_score_scale, 1e-6)
                return min(raw_score / hybrid_scale, 1.0)
            return raw_score / (1.0 + raw_score)

        reranked = []
        total_results = len(results)
        for rank_index, result in enumerate(results):
            lexical_text = " ".join(
                [
                    result.content or "",
                    result.summary or "",
                    " ".join(result.keywords or []),
                ]
            ).lower()
            matched_terms = sum(1 for term in terms if term in lexical_text)
            overlap_score = matched_terms / len(terms)
            method_score = _method_score(result)
            rank_prior = 1.0 - (rank_index / max(total_results, 1)) * 0.35
            method = (result.search_method or "").lower()
            semantic_floor_applied = False

            # Preserve semantic-only hits for cross-lingual multi-term queries where lexical overlap is zero.
            if method == "vector" and overlap_score == 0.0 and len(terms) >= 2:
                semantic_floor = 0.88 * method_score + 0.12 * rank_prior
                final_score = max(semantic_floor, method_score * 0.90)
                semantic_floor_applied = True
            else:
                final_score = 0.55 * overlap_score + 0.35 * method_score + 0.10 * rank_prior

            result.similarity_score = float(final_score)
            result.metadata = dict(result.metadata or {})
            result.metadata["query_overlap"] = round(overlap_score, 4)
            result.metadata["method_score"] = round(method_score, 4)
            result.metadata["semantic_floor_applied"] = semantic_floor_applied
            reranked.append(result)

        reranked.sort(key=lambda item: item.similarity_score, reverse=True)
        return reranked

    @staticmethod
    def _contains_literal_query_term(result: SearchResult, term: str) -> bool:
        normalized_term = unicodedata.normalize("NFKC", (term or "")).strip().lower()
        if len(normalized_term) < 2:
            return False
        haystack = " ".join(
            [
                str(result.content or ""),
                str(result.summary or ""),
                " ".join(result.keywords or []),
            ]
        ).lower()
        return normalized_term in haystack

    def _apply_short_query_precision_guard(
        self,
        *,
        query: str,
        query_terms: List[str],
        bm25_results: List[SearchResult],
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """Drop weak semantic-only hits for literal short queries with no lexical support."""
        if not results or bm25_results:
            return results

        normalized_query = unicodedata.normalize("NFKC", (query or "")).strip().lower()
        if len(normalized_query) < 2:
            return results

        is_short_cjk_query = (
            bool(_CJK_TOKEN_PATTERN.match(normalized_query)) and len(normalized_query) <= 4
        )
        is_short_single_token = " " not in normalized_query and len(normalized_query) <= 4
        if not (is_short_cjk_query or is_short_single_token):
            return results

        literal_terms: List[str] = []
        for candidate in [normalized_query, *query_terms]:
            term = unicodedata.normalize("NFKC", str(candidate or "")).strip().lower()
            if len(term) < 2 or term in literal_terms:
                continue
            literal_terms.append(term)

        top_rerank_score = max(
            float(dict(result.metadata or {}).get("rerank_score") or 0.0) for result in results
        )
        if top_rerank_score >= 0.03:
            supported: List[SearchResult] = []
            rerank_support_floor = max(top_rerank_score * 0.5, 0.02)
            for result in results:
                if any(self._contains_literal_query_term(result, term) for term in literal_terms):
                    supported.append(result)
                    continue

                metadata = dict(result.metadata or {})
                rerank_score = float(metadata.get("rerank_score") or 0.0)
                if rerank_score < rerank_support_floor:
                    continue

                base_score = float(
                    metadata.get("base_score")
                    or self._normalize_result_score_for_blend(result)
                    or 0.0
                )
                if base_score < 0.42:
                    continue

                result.similarity_score = max(
                    float(result.similarity_score or 0.0), base_score * 0.9
                )
                supported.append(result)

            if supported:
                return supported

        scored_by_base = [
            (
                result,
                float(
                    dict(result.metadata or {}).get("base_score")
                    or self._normalize_result_score_for_blend(result)
                    or 0.0
                ),
            )
            for result in results
        ]
        scored_by_base.sort(key=lambda item: item[1], reverse=True)
        if scored_by_base:
            leader, leader_base = scored_by_base[0]
            runner_up_base = scored_by_base[1][1] if len(scored_by_base) > 1 else 0.0
            if leader_base >= 0.5 and (leader_base - runner_up_base) >= 0.03:
                leader.similarity_score = max(
                    float(leader.similarity_score or 0.0), leader_base * 0.9
                )
                return [leader]

        guarded: List[SearchResult] = []
        for result in results:
            if any(self._contains_literal_query_term(result, term) for term in literal_terms):
                guarded.append(result)
                continue

            metadata = dict(result.metadata or {})
            rerank_score = float(metadata.get("rerank_score") or 0.0)
            base_score = self._normalize_result_score_for_blend(result)
            if max(rerank_score, base_score) >= 0.75:
                guarded.append(result)

        return guarded

    def _apply_permission_filter(
        self,
        results: List[SearchResult],
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Apply permission filtering to search results.

        Both Milvus and BM25 queries already filter by owner user_id.
        This provides additional access-level filtering for team/public items.

        Args:
            results: Search results to filter
            search_filter: Filter with user context

        Returns:
            Filtered list of SearchResult
        """
        try:
            from access_control.knowledge_filter import filter_knowledge_results
            from access_control.permissions import CurrentUser

            # Convert SearchResults to dicts for the filter function
            result_dicts = []
            for r in results:
                result_dicts.append(
                    {
                        "chunk_id": r.chunk_id,
                        "document_id": r.document_id,
                        "owner_user_id": r.metadata.get("owner_user_id", search_filter.user_id),
                        "access_level": r.metadata.get("access_level", "private"),
                        "content": r.content,
                        "similarity_score": r.similarity_score,
                        "chunk_index": r.chunk_index,
                        "metadata": r.metadata,
                        "keywords": r.keywords,
                        "summary": r.summary,
                        "search_method": r.search_method,
                    }
                )

            current_user = CurrentUser(
                user_id=search_filter.user_id,
                username="knowledge_search_user",
                role=search_filter.user_role or "user",
            )

            filtered_dicts = filter_knowledge_results(
                results=result_dicts,
                current_user=current_user,
                user_attributes=search_filter.user_attributes,
            )

            # Convert back to SearchResult objects
            filtered_ids = {d["chunk_id"] for d in filtered_dicts}
            return [r for r in results if r.chunk_id in filtered_ids]

        except ImportError:
            logger.warning("access_control.knowledge_filter not available, skipping filter")
            return results
        except Exception as e:
            logger.warning(f"Permission filtering failed, returning unfiltered: {e}")
            return results

    def _rrf_merge(
        self,
        vector_results: List[SearchResult],
        bm25_results: List[SearchResult],
    ) -> List[SearchResult]:
        """Merge results using Reciprocal Rank Fusion.

        RRF score(d) = Σ weight / (k + rank) for each result list.

        Args:
            vector_results: Results from vector search
            bm25_results: Results from BM25 search

        Returns:
            Merged and re-ranked results
        """
        scores: Dict[str, float] = {}
        result_map: Dict[str, SearchResult] = {}

        # Score vector results
        for rank, result in enumerate(vector_results):
            key = result.chunk_id
            rrf_score = self.semantic_weight / (self.rrf_k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            if key not in result_map:
                result_map[key] = result

        # Score BM25 results
        for rank, result in enumerate(bm25_results):
            key = result.chunk_id
            rrf_score = self.fulltext_weight / (self.rrf_k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            if key not in result_map:
                result_map[key] = result
            else:
                # Merge metadata: prefer BM25 keywords/summary
                existing = result_map[key]
                if result.keywords and not existing.keywords:
                    existing.keywords = result.keywords
                if result.summary and not existing.summary:
                    existing.summary = result.summary

        # Sort by RRF score
        sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)

        merged = []
        for key in sorted_keys:
            result = result_map[key]
            result.similarity_score = scores[key]
            result.search_method = "hybrid"
            merged.append(result)

        return merged


# Singleton instance
_knowledge_search: Optional[KnowledgeSearch] = None
_knowledge_search_signature: Optional[str] = None


def _build_search_signature() -> str:
    """Build signature to refresh singleton when KB config changes."""
    try:
        config = get_config()
        kb_config = load_knowledge_base_config(config)
        payload = {
            "search": kb_config.get("search", {}),
            "embedding": kb_config.get("embedding", {}),
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=True)
    except Exception:
        return ""


def get_knowledge_search() -> KnowledgeSearch:
    """Get or create the knowledge search singleton.

    Returns:
        KnowledgeSearch instance
    """
    global _knowledge_search, _knowledge_search_signature
    signature = _build_search_signature()
    if _knowledge_search is None or signature != _knowledge_search_signature:
        _knowledge_search = KnowledgeSearch()
        _knowledge_search_signature = signature
    return _knowledge_search
