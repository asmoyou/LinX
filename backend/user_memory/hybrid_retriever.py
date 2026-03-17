"""Hybrid retrieval for user-memory entries and views."""

from __future__ import annotations

import json
import logging
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import requests

from database.connection import get_db_session
from database.models import UserMemoryEntry, UserMemoryView
from llm_providers.openai_compatible import build_api_url_candidates, normalize_rerank_scores
from llm_providers.provider_resolver import resolve_provider
from shared.config import get_config
from shared.metrics import (
    user_memory_retrieval_fallback_total,
    user_memory_retrieval_hits_total,
    user_memory_retrieval_reflection_total,
    user_memory_retrieval_stage_latency_seconds,
)
from user_memory.items import RetrievedMemoryItem
from user_memory.lexical_search import (
    build_query_variants,
    extract_query_terms,
    get_user_memory_lexical_search_service,
    is_wildcard_query,
    normalize_text,
    simplify_query_text,
)
from user_memory.query_planner import QueryPlan, get_user_memory_query_planner
from user_memory.structured_search import (
    StructuredQueryFilters,
    get_user_memory_structured_search_service,
)
from user_memory.vector_documents import parse_event_time_range
from user_memory.vector_index import search_user_memory_vectors

logger = logging.getLogger(__name__)


class UserMemoryHybridRetriever:
    """Shared hybrid retrieval pipeline for runtime and APIs."""

    def __init__(self) -> None:
        self._rerank_fail_until = 0.0

    @staticmethod
    def _candidate_key(item: RetrievedMemoryItem) -> Tuple[str, int]:
        metadata = dict(item.metadata or {})
        if metadata.get("relation_id") is not None:
            return ("relation", int(metadata["relation_id"]))
        if metadata.get("entry_id") is not None:
            return ("entry", int(metadata["entry_id"]))
        if metadata.get("view_id") is not None:
            return ("view", int(metadata["view_id"]))
        return (str(metadata.get("memory_source") or "unknown"), int(item.id or 0))

    @staticmethod
    def _normalize_identity_text(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
        if not text:
            return ""
        text = text.replace("将和", "将与").replace("和小", "与小")
        text = text.replace("一起和", "一起与")
        text = "".join(ch for ch in text if not ch.isspace())
        return text

    @classmethod
    def _semantic_identity_key(cls, item: RetrievedMemoryItem) -> Optional[Tuple[str, ...]]:
        metadata = dict(item.metadata or {})
        identity_signature = str(metadata.get("identity_signature") or "").strip()
        if identity_signature:
            return ("identity", identity_signature)
        semantic_key = str(metadata.get("semantic_key") or "").strip()
        event_time = str(metadata.get("event_time") or "").strip()
        fact_kind = str(metadata.get("fact_kind") or "").strip()
        source_entry_key = str(metadata.get("source_entry_key") or "").strip()
        entry_key = str(metadata.get("entry_key") or "").strip()
        view_key = str(metadata.get("view_key") or "").strip()
        canonical_statement = str(metadata.get("canonical_statement") or "").strip()
        view_type = str(metadata.get("view_type") or "").strip()
        normalized_statement = cls._normalize_identity_text(
            canonical_statement or item.content or item.summary or ""
        )

        if view_type == "episode" or fact_kind == "event":
            stable_key = normalized_statement or cls._normalize_identity_text(
                source_entry_key or semantic_key or entry_key or view_key
            )
            if stable_key:
                return ("event", stable_key, event_time)
        if fact_kind in {"preference", "identity", "constraint", "habit"} or (
            view_type == "user_profile" and normalized_statement
        ):
            if normalized_statement:
                return ("profile", normalized_statement)
        if semantic_key:
            return ("semantic", semantic_key)
        stable_key = entry_key or view_key or normalized_statement
        if stable_key:
            return ("fact", stable_key)
        return None

    @staticmethod
    def _surface_priority(item: RetrievedMemoryItem) -> int:
        metadata = dict(item.metadata or {})
        if metadata.get("relation_id") is not None:
            return 4
        view_type = str(metadata.get("view_type") or "").strip().lower()
        if view_type == "user_profile":
            return 3
        if view_type == "episode":
            return 2
        if metadata.get("view_id") is not None:
            return 1
        return 0

    @staticmethod
    def _merge_duplicate_item_metadata(
        chosen: RetrievedMemoryItem,
        duplicate: RetrievedMemoryItem,
    ) -> RetrievedMemoryItem:
        chosen.metadata = dict(chosen.metadata or {})
        duplicate_meta = dict(duplicate.metadata or {})
        chosen_methods = list(chosen.metadata.get("search_methods") or [])
        duplicate_methods = list(duplicate_meta.get("search_methods") or [])
        if duplicate_meta.get("search_method"):
            duplicate_methods.append(str(duplicate_meta.get("search_method")))
        chosen.metadata["search_methods"] = list(
            dict.fromkeys([*chosen_methods, *duplicate_methods])
        )
        chosen.metadata["search_method"] = "hybrid"
        chosen.similarity_score = max(
            float(chosen.similarity_score or 0.0),
            float(duplicate.similarity_score or 0.0),
        )
        for key, value in duplicate_meta.items():
            if key not in chosen.metadata:
                chosen.metadata[key] = value
        return chosen

    @staticmethod
    def _metadata_score(metadata: Mapping[str, Any], key: str) -> float:
        try:
            return float(metadata.get(key) or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _candidate_base_score(cls, item: RetrievedMemoryItem) -> float:
        metadata = dict(item.metadata or {})
        candidate_scores = [
            float(item.similarity_score or 0.0),
            cls._metadata_score(metadata, "_semantic_score"),
            cls._metadata_score(metadata, "_lexical_score"),
            cls._metadata_score(metadata, "_structured_score"),
        ]
        return min(max(max(candidate_scores), 0.0), 1.0)

    @staticmethod
    def _candidate_lexical_text(item: RetrievedMemoryItem) -> str:
        return " ".join(
            [
                str(item.content or ""),
                str(item.summary or ""),
                json.dumps(item.metadata or {}, ensure_ascii=False),
            ]
        ).lower()

    @classmethod
    def _query_overlap_metrics(
        cls,
        *,
        query_terms: Sequence[str],
        item: RetrievedMemoryItem,
    ) -> tuple[float, int, bool]:
        terms = []
        seen = set()
        for term in query_terms:
            normalized = str(term or "").strip().lower()
            if len(normalized) < 2 or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(normalized)
        if not terms:
            return 0.0, 0, False

        lexical_text = cls._candidate_lexical_text(item)
        matched_terms = [term for term in terms if term in lexical_text]
        total_weight = sum(max(len(term), 2) for term in terms)
        matched_weight = sum(max(len(term), 2) for term in matched_terms)
        weighted_overlap = matched_weight / max(total_weight, 1)
        specific_match = any(len(term) >= 3 for term in matched_terms)
        return weighted_overlap, len(matched_terms), specific_match

    @staticmethod
    def _ranges_overlap(
        *,
        query_start: datetime,
        query_end: datetime,
        item_start: datetime,
        item_end: datetime,
    ) -> bool:
        return item_start <= query_end and item_end >= query_start

    @classmethod
    def _apply_temporal_filters(
        cls,
        *,
        plan: QueryPlan,
        results: Sequence[RetrievedMemoryItem],
    ) -> List[RetrievedMemoryItem]:
        query_start = plan.structured_filters.time_range.start
        query_end = plan.structured_filters.time_range.end or query_start
        if query_start is None or query_end is None:
            return list(results)

        filtered: List[RetrievedMemoryItem] = []
        for item in results:
            metadata = dict(item.metadata or {})
            fact_kind = str(metadata.get("fact_kind") or "").strip().lower()
            view_type = str(metadata.get("view_type") or "").strip().lower()
            event_time = str(metadata.get("event_time") or "").strip()
            is_temporal_candidate = bool(event_time) or fact_kind == "event" or view_type == "episode"
            if not is_temporal_candidate:
                filtered.append(item)
                continue
            item_start, item_end = parse_event_time_range(event_time)
            if item_start is None or item_end is None:
                continue
            if cls._ranges_overlap(
                query_start=query_start,
                query_end=query_end,
                item_start=item_start,
                item_end=item_end,
            ):
                filtered.append(item)
        return filtered

    @staticmethod
    def _allow_structured_floor(
        structured_filters: Optional[StructuredQueryFilters],
    ) -> bool:
        if structured_filters is None:
            return True
        if structured_filters.persons or structured_filters.entities:
            return True
        if structured_filters.locations or structured_filters.predicates:
            return True
        if structured_filters.time_range.start or structured_filters.time_range.end:
            return True
        if any(
            str(kind or "").strip().lower() in {"relationship", "event"}
            for kind in structured_filters.fact_kinds
        ):
            return True
        if any(
            str(view_type or "").strip().lower() == "episode"
            for view_type in structured_filters.view_types
        ):
            return True
        return False

    def _collapse_duplicate_memories(
        self,
        items: Sequence[RetrievedMemoryItem],
    ) -> List[RetrievedMemoryItem]:
        deduped: Dict[Tuple[str, ...], RetrievedMemoryItem] = {}
        ordered: List[Tuple[str, ...]] = []
        for item in items:
            identity = self._semantic_identity_key(item)
            if identity is None:
                identity = ("candidate", *self._candidate_key(item))
            existing = deduped.get(identity)
            if existing is None:
                deduped[identity] = item
                ordered.append(identity)
                continue

            existing_priority = self._surface_priority(existing)
            candidate_priority = self._surface_priority(item)
            existing_score = float(existing.similarity_score or 0.0)
            candidate_score = float(item.similarity_score or 0.0)
            should_replace = candidate_priority > existing_priority or (
                candidate_priority == existing_priority and candidate_score > existing_score
            )
            if should_replace:
                deduped[identity] = self._merge_duplicate_item_metadata(item, existing)
            else:
                deduped[identity] = self._merge_duplicate_item_metadata(existing, item)

        results = [deduped[key] for key in ordered]
        results.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                (
                    item.timestamp
                    if isinstance(item.timestamp, datetime)
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
            reverse=True,
        )
        return results

    @staticmethod
    def _cfg() -> Dict[str, Any]:
        return get_config().get("user_memory.retrieval", {}) or {}

    def _rerank_cfg(self) -> Dict[str, Any]:
        return self._cfg().get("rerank", {}) or {}

    def _reflection_cfg(self) -> Dict[str, Any]:
        return self._cfg().get("reflection", {}) or {}

    def _similarity_threshold(self) -> float:
        try:
            return float(self._cfg().get("similarity_threshold", 0.3) or 0.3)
        except (TypeError, ValueError):
            return 0.3

    def _normalize_semantic_score(self, raw_distance: float) -> float:
        metric = str(self._cfg().get("vector", {}).get("metric_type", "IP") or "IP").upper()
        if metric == "IP":
            return max(min((float(raw_distance) + 1.0) / 2.0, 1.0), 0.0)
        return 1.0 / (1.0 + max(float(raw_distance), 0.0))

    def _entry_to_item(
        self,
        row: Any,
        *,
        score: float,
        method: str,
    ) -> RetrievedMemoryItem:
        payload = row.entry_data if isinstance(row.entry_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": method,
            "search_methods": [method],
            "memory_source": "entry",
            "record_type": "user_fact",
            "entry_id": row.id,
            "entry_key": row.entry_key,
            "fact_kind": row.fact_kind,
            "status": row.status,
            "_semantic_score": round(float(score), 4) if method == "semantic" else None,
            "vector_status": getattr(row, "vector_sync_state", None),
            "vector_error": getattr(row, "vector_error", None),
        }
        metadata.update(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "fact_kind",
                    "semantic_key",
                    "identity_signature",
                    "canonical_statement",
                    "event_time",
                    "location",
                    "topic",
                    "persons",
                    "entities",
                }
            }
        )
        metadata = {key: value for key, value in metadata.items() if value is not None}
        return RetrievedMemoryItem(
            id=int(row.id),
            content=str(row.canonical_text or "").strip(),
            summary=str(row.summary or "").strip() or None,
            memory_type="user_memory",
            user_id=str(row.user_id),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    def _view_to_item(
        self,
        row: Any,
        *,
        score: float,
        method: str,
    ) -> RetrievedMemoryItem:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": method,
            "search_methods": [method],
            "memory_source": "user_memory_view",
            "record_type": str(row.view_type or "view"),
            "view_id": row.id,
            "view_key": row.view_key,
            "view_type": row.view_type,
            "status": row.status,
            "_semantic_score": round(float(score), 4) if method == "semantic" else None,
            "vector_status": getattr(row, "vector_sync_state", None),
            "vector_error": getattr(row, "vector_error", None),
        }
        metadata.update(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "fact_kind",
                    "semantic_key",
                    "identity_signature",
                    "canonical_statement",
                    "event_time",
                    "location",
                    "topic",
                }
            }
        )
        metadata = {key: value for key, value in metadata.items() if value is not None}
        return RetrievedMemoryItem(
            id=int(row.id),
            content=str(row.content or row.title or "").strip(),
            summary=str(row.content or "").strip() or None,
            memory_type="user_memory",
            user_id=str(row.user_id),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    def _load_rows_for_vector_hits(
        self,
        *,
        user_id: str,
        vector_hits: Sequence[Any],
    ) -> List[RetrievedMemoryItem]:
        entry_hit_map = {
            int(hit.source_id): hit
            for hit in vector_hits
            if str(hit.source_kind) == "entry" and hit.source_id is not None
        }
        view_hit_map = {
            int(hit.source_id): hit
            for hit in vector_hits
            if str(hit.source_kind) == "view" and hit.source_id is not None
        }

        items: List[RetrievedMemoryItem] = []
        with get_db_session() as session:
            if entry_hit_map:
                rows = (
                    session.query(UserMemoryEntry)
                    .filter(
                        UserMemoryEntry.user_id == str(user_id),
                        UserMemoryEntry.id.in_(list(entry_hit_map.keys())),
                    )
                    .all()
                )
                for row in rows:
                    hit = entry_hit_map.get(int(row.id))
                    if hit is None:
                        continue
                    items.append(
                        self._entry_to_item(
                            row,
                            score=self._normalize_semantic_score(hit.distance),
                            method="semantic",
                        )
                    )

            if view_hit_map:
                rows = (
                    session.query(UserMemoryView)
                    .filter(
                        UserMemoryView.user_id == str(user_id),
                        UserMemoryView.id.in_(list(view_hit_map.keys())),
                    )
                    .all()
                )
                for row in rows:
                    hit = view_hit_map.get(int(row.id))
                    if hit is None:
                        continue
                    items.append(
                        self._view_to_item(
                            row,
                            score=self._normalize_semantic_score(hit.distance),
                            method="semantic",
                        )
                    )
        return items

    def _semantic_candidates(
        self,
        *,
        user_id: str,
        plan: QueryPlan,
        source_kinds: Optional[Sequence[str]],
        fact_kinds: Optional[Sequence[str]],
        view_types: Optional[Sequence[str]],
    ) -> List[RetrievedMemoryItem]:
        statuses = ["active", "superseded"] if plan.structured_filters.allow_history else ["active"]
        deduped_hits = {}
        for query_variant in plan.query_variants:
            hits = search_user_memory_vectors(
                user_id=str(user_id),
                query=query_variant,
                top_k=plan.vector_top_k,
                statuses=statuses,
                source_kinds=source_kinds,
                fact_kinds=fact_kinds or plan.structured_filters.fact_kinds,
                view_types=view_types or plan.structured_filters.view_types,
            )
            for hit in hits:
                key = (str(hit.source_kind), int(hit.source_id))
                previous = deduped_hits.get(key)
                if previous is None or float(hit.distance) > float(previous.distance):
                    deduped_hits[key] = hit
        items = self._load_rows_for_vector_hits(
            user_id=user_id, vector_hits=list(deduped_hits.values())
        )
        items.sort(key=lambda item: float(item.similarity_score or 0.0), reverse=True)
        return items[: plan.vector_top_k]

    def _merge_candidates(
        self,
        *,
        plan: QueryPlan,
        groups: Mapping[str, Sequence[RetrievedMemoryItem]],
    ) -> List[RetrievedMemoryItem]:
        rrf_k = int(self._cfg().get("fusion", {}).get("rrf_k", 60) or 60)
        merged: Dict[Tuple[str, int], RetrievedMemoryItem] = {}
        scores: Dict[Tuple[str, int], float] = {}
        methods: Dict[Tuple[str, int], List[str]] = {}

        for source_name, items in groups.items():
            for rank, item in enumerate(items):
                key = self._candidate_key(item)
                score = 1.0 / float(rrf_k + rank + 1)
                scores[key] = scores.get(key, 0.0) + score
                methods.setdefault(key, []).append(source_name)
                existing = merged.get(key)
                if existing is None or float(item.similarity_score or 0.0) > float(
                    existing.similarity_score or 0.0
                ):
                    merged[key] = item
                metadata = merged[key].metadata
                metadata[f"_{source_name}_rank"] = rank + 1
                if source_name == "semantic":
                    metadata["_semantic_score"] = round(float(item.similarity_score or 0.0), 4)
                elif source_name == "lexical":
                    metadata["_lexical_score"] = round(float(item.similarity_score or 0.0), 4)
                elif source_name == "structured":
                    metadata["_structured_score"] = round(float(item.similarity_score or 0.0), 4)

        results: List[RetrievedMemoryItem] = []
        for key, item in merged.items():
            item.metadata = dict(item.metadata or {})
            search_methods = list(dict.fromkeys(methods.get(key, [])))
            raw_fusion_score = float(scores.get(key, 0.0))
            blended_fusion_score = min(raw_fusion_score * float(max(rrf_k, 1)) * 0.75, 0.99)
            item.metadata["search_method"] = "hybrid"
            item.metadata["search_methods"] = search_methods
            item.metadata["_fusion_score"] = round(raw_fusion_score, 6)
            item.metadata["_planner_mode"] = plan.planner_mode
            item.similarity_score = blended_fusion_score
            results.append(item)

        results.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                (
                    item.timestamp
                    if isinstance(item.timestamp, datetime)
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
            reverse=True,
        )
        return results

    def _build_rerank_document(self, item: RetrievedMemoryItem) -> str:
        parts = [str(item.content or "")]
        if item.summary:
            parts.append(f"Summary: {item.summary}")
        metadata = dict(item.metadata or {})
        for key in ("fact_kind", "view_type", "event_time", "location", "topic"):
            value = str(metadata.get(key) or "").strip()
            if value:
                parts.append(f"{key}: {value}")
        max_chars = max(int(self._rerank_cfg().get("doc_max_chars", 1200) or 1200), 256)
        return "\n".join(part for part in parts if part)[:max_chars]

    def _parse_rerank_response(
        self, response_data: object, doc_count: int
    ) -> List[Tuple[int, float]]:
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
            return []

        parsed: List[Tuple[int, float]] = []
        for idx, item in enumerate(raw_results):
            if isinstance(item, dict):
                raw_index = item.get("index", item.get("document_index", idx))
                raw_score = item.get(
                    "relevance_score", item.get("score", item.get("similarity", 0.0))
                )
            else:
                raw_index = idx
                raw_score = item
            try:
                doc_index = int(raw_index)
                score = float(raw_score)
            except (TypeError, ValueError):
                continue
            if 0 <= doc_index < doc_count:
                parsed.append((doc_index, score))
        return normalize_rerank_scores(parsed)

    def _call_rerank_api(self, *, query: str, documents: List[str]) -> List[Tuple[int, float]]:
        cfg = self._rerank_cfg()
        provider_name = str(cfg.get("provider") or "").strip()
        model = str(cfg.get("model") or "").strip()
        if not provider_name or not model or not documents:
            return []

        now = time.monotonic()
        if now < self._rerank_fail_until:
            return []

        provider_cfg = resolve_provider(provider_name)
        base_url = str(provider_cfg.get("base_url") or "").strip()
        if not base_url:
            return []

        timeout = max(float(cfg.get("timeout_seconds") or 8), 1.0)
        headers = {"Content-Type": "application/json"}
        if provider_cfg.get("api_key"):
            headers["Authorization"] = f"Bearer {provider_cfg['api_key']}"

        payload = {
            "model": model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
        }
        urls = build_api_url_candidates(base_url, "/rerank")
        for attempt_index, url in enumerate(urls):
            attempt_timeout = (
                timeout
                if attempt_index == 0
                else min(
                    max(timeout / 3.0, 1.0),
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
                    continue
                parsed = self._parse_rerank_response(response.json(), len(documents))
                if parsed:
                    self._rerank_fail_until = 0.0
                    return parsed
            except Exception as exc:
                logger.debug("User-memory rerank request failed: %s", exc)
                continue

        self._rerank_fail_until = now + max(
            float(cfg.get("failure_backoff_seconds") or 30),
            1.0,
        )
        return []

    def _heuristic_rerank(
        self,
        *,
        query_terms: Sequence[str],
        results: List[RetrievedMemoryItem],
        structured_filters: Optional[StructuredQueryFilters] = None,
    ) -> List[RetrievedMemoryItem]:
        terms = [term.lower() for term in query_terms if len(term) >= 2][:16]
        if not terms:
            return results

        total_results = len(results)
        structured_floor_allowed = self._allow_structured_floor(structured_filters)
        reranked: List[RetrievedMemoryItem] = []
        for index, item in enumerate(results):
            overlap_score, matched_terms, specific_match = self._query_overlap_metrics(
                query_terms=terms,
                item=item,
            )
            metadata = dict(item.metadata or {})
            method_score = self._candidate_base_score(item)
            rank_prior = 1.0 - (index / max(total_results, 1)) * 0.35
            search_methods = [
                str(value).lower() for value in list(metadata.get("search_methods") or [])
            ]
            semantic_floor_applied = False
            structured_floor_applied = False
            if "semantic" in search_methods and overlap_score == 0.0:
                semantic_floor = 0.88 * method_score + 0.12 * rank_prior
                final_score = max(semantic_floor, method_score * 0.90)
                semantic_floor_applied = True
            else:
                specificity_bonus = 0.06 if specific_match else 0.0
                final_score = (
                    0.62 * overlap_score
                    + 0.22 * method_score
                    + 0.10 * rank_prior
                    + specificity_bonus
                )
            structured_score = self._metadata_score(metadata, "_structured_score")
            if (
                structured_floor_allowed
                and "structured" in search_methods
                and overlap_score == 0.0
                and structured_score > 0.0
            ):
                structured_floor = min(0.72 * structured_score + 0.28 * rank_prior, 0.99)
                final_score = max(final_score, structured_floor)
                structured_floor_applied = True

            item.metadata = metadata
            item.metadata["query_overlap"] = round(overlap_score, 4)
            item.metadata["semantic_floor_applied"] = semantic_floor_applied
            item.metadata["structured_floor_applied"] = structured_floor_applied
            item.similarity_score = float(final_score)
            reranked.append(item)

        reranked.sort(key=lambda item: float(item.similarity_score or 0.0), reverse=True)
        return reranked

    def _apply_rerank(
        self,
        *,
        query_text: str,
        query_terms: Sequence[str],
        results: List[RetrievedMemoryItem],
        top_k: int,
        structured_filters: Optional[StructuredQueryFilters] = None,
    ) -> Tuple[List[RetrievedMemoryItem], bool]:
        cfg = self._rerank_cfg()
        enabled = bool(cfg.get("enabled", True))
        if not enabled or len(results) <= 1:
            return results, False

        candidate_limit = min(
            len(results),
            max(
                int(cfg.get("top_k") or 30),
                int(top_k) * 3,
                int(top_k),
            ),
        )
        candidates = list(results[:candidate_limit])
        documents = [self._build_rerank_document(item) for item in candidates]
        rerank_items = self._call_rerank_api(query=query_text, documents=documents)
        if not rerank_items:
            return (
                self._heuristic_rerank(
                    query_terms=query_terms,
                    results=results,
                    structured_filters=structured_filters,
                ),
                False,
            )

        rerank_weight = min(max(float(cfg.get("weight") or 0.75), 0.0), 1.0)
        base_weight = 1.0 - rerank_weight
        structured_floor_allowed = self._allow_structured_floor(structured_filters)
        reordered: List[RetrievedMemoryItem] = []
        seen = set()
        for candidate_rank, (doc_index, rerank_score) in enumerate(rerank_items):
            if doc_index < 0 or doc_index >= len(candidates):
                continue
            item = candidates[doc_index]
            item.metadata = dict(item.metadata or {})
            item.metadata["_rerank_score"] = round(float(rerank_score), 4)
            item.metadata["_rerank_provider"] = str(cfg.get("provider") or "")
            item.metadata["_rerank_model"] = str(cfg.get("model") or "")
            base_score = self._candidate_base_score(item)
            item.metadata["_base_score"] = round(float(base_score), 4)
            blended = rerank_weight * float(rerank_score) + base_weight * base_score
            overlap_score, _matched_terms, specific_match = self._query_overlap_metrics(
                query_terms=query_terms,
                item=item,
            )
            blended += 0.08 * overlap_score
            if specific_match:
                blended += 0.03
            structured_score = self._metadata_score(item.metadata, "_structured_score")
            if (
                structured_floor_allowed
                and structured_score > 0.0
                and float(rerank_score) < 0.25
            ):
                structured_floor = min(0.58 * structured_score + 0.42 * base_score, 0.99)
                item.metadata["_structured_floor"] = round(float(structured_floor), 4)
                blended = max(blended, structured_floor)
            blended = min(max(float(blended), 0.0), 0.99)
            item.metadata["_rerank_blended_score"] = round(float(blended), 4)
            item.similarity_score = float(blended)
            reordered.append(item)
            seen.add(self._candidate_key(item))

        reordered.extend(item for item in candidates if self._candidate_key(item) not in seen)
        reordered.extend(results[candidate_limit:])
        return reordered, True

    def _apply_min_score(
        self,
        items: Sequence[RetrievedMemoryItem],
        *,
        min_score: Optional[float],
        limit: int,
    ) -> List[RetrievedMemoryItem]:
        threshold = self._similarity_threshold() if min_score is None else float(min_score)
        accepted = [
            item for item in items if float(item.similarity_score or 0.0) >= float(threshold)
        ]
        return accepted[: max(int(limit), 1)]

    @staticmethod
    def _preferred_query_text(
        *,
        original_query: str,
        query_variants: Sequence[str],
    ) -> str:
        simplified = simplify_query_text(original_query)
        if simplified:
            return simplified
        original_normalized = normalize_text(original_query)
        for candidate in query_variants:
            normalized = normalize_text(candidate)
            if normalized and normalized != original_normalized:
                return str(candidate)
        return original_query

    def _recent_search(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int,
        min_score: Optional[float],
        scope: str,
    ) -> List[RetrievedMemoryItem]:
        safe_limit = max(int(limit), 1)
        with get_db_session() as session:
            results: List[RetrievedMemoryItem] = []
            if scope == "profile":
                rows = (
                    session.query(UserMemoryView)
                    .filter(
                        UserMemoryView.user_id == str(user_id),
                        UserMemoryView.status == "active",
                        UserMemoryView.view_type == "user_profile",
                    )
                    .order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
                    .limit(safe_limit)
                    .all()
                )
                results = [self._view_to_item(row, score=0.35, method="recent") for row in rows]
            elif scope == "episodes":
                view_rows = (
                    session.query(UserMemoryView)
                    .filter(
                        UserMemoryView.user_id == str(user_id),
                        UserMemoryView.status == "active",
                        UserMemoryView.view_type == "episode",
                    )
                    .order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
                    .limit(safe_limit)
                    .all()
                )
                results = [
                    self._view_to_item(row, score=0.35, method="recent") for row in view_rows
                ]
                if len(results) < safe_limit:
                    remaining = safe_limit - len(results)
                    event_rows = (
                        session.query(UserMemoryEntry)
                        .filter(
                            UserMemoryEntry.user_id == str(user_id),
                            UserMemoryEntry.status == "active",
                            UserMemoryEntry.fact_kind == "event",
                        )
                        .order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
                        .limit(remaining)
                        .all()
                    )
                    results.extend(
                        [
                            self._entry_to_item(row, score=0.33, method="recent")
                            for row in event_rows
                        ]
                    )
            else:
                view_rows = (
                    session.query(UserMemoryView)
                    .filter(
                        UserMemoryView.user_id == str(user_id),
                        UserMemoryView.status == "active",
                    )
                    .order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
                    .limit(safe_limit)
                    .all()
                )
                entry_rows = (
                    session.query(UserMemoryEntry)
                    .filter(
                        UserMemoryEntry.user_id == str(user_id),
                        UserMemoryEntry.status == "active",
                    )
                    .order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
                    .limit(safe_limit)
                    .all()
                )
                results = [
                    *[self._view_to_item(row, score=0.35, method="recent") for row in view_rows],
                    *[self._entry_to_item(row, score=0.33, method="recent") for row in entry_rows],
                ]

        deduped = self._collapse_duplicate_memories(results)
        return self._apply_min_score(deduped, min_score=min_score, limit=limit)

    def _search_hybrid(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int,
        min_score: Optional[float],
        planner_mode: str,
        allow_reflection: bool,
        scope: str,
        source_kinds: Optional[Sequence[str]] = None,
        fact_kinds: Optional[Sequence[str]] = None,
        view_types: Optional[Sequence[str]] = None,
    ) -> List[RetrievedMemoryItem]:
        if is_wildcard_query(query_text):
            user_memory_retrieval_fallback_total.labels(reason="wildcard_recent").inc()
            return self._recent_search(
                user_id=user_id,
                query_text=query_text,
                limit=limit,
                min_score=min_score,
                scope=scope,
            )

        scope_view_types = view_types if scope in {"profile", "episodes"} else None
        plan = get_user_memory_query_planner().plan(
            query_text=query_text,
            planner_mode=planner_mode,
            scope_view_types=scope_view_types,
        )
        query_variants = build_query_variants(query_text, extra_queries=plan.query_variants)
        retrieval_query = self._preferred_query_text(
            original_query=query_text,
            query_variants=query_variants,
        )

        semantic_started = time.perf_counter()
        semantic_items = self._semantic_candidates(
            user_id=user_id,
            plan=plan,
            source_kinds=source_kinds,
            fact_kinds=fact_kinds,
            view_types=view_types,
        )
        user_memory_retrieval_stage_latency_seconds.labels(stage="semantic").observe(
            time.perf_counter() - semantic_started
        )
        user_memory_retrieval_hits_total.labels(source="semantic").inc(len(semantic_items))
        lexical_service = get_user_memory_lexical_search_service()
        lexical_items: List[RetrievedMemoryItem] = []
        structured_items: List[RetrievedMemoryItem] = []

        lexical_started = time.perf_counter()
        if source_kinds is None or "entry" in source_kinds:
            lexical_items.extend(
                lexical_service.search_entries(
                    user_id=user_id,
                    query_text=retrieval_query,
                    top_k=plan.lexical_top_k,
                    statuses=(
                        ["active", "superseded"]
                        if plan.structured_filters.allow_history
                        else ["active"]
                    ),
                    fact_kinds=fact_kinds or plan.structured_filters.fact_kinds or None,
                    query_variants=query_variants,
                )
            )
        if source_kinds is None or "view" in source_kinds:
            lexical_items.extend(
                lexical_service.search_views(
                    user_id=user_id,
                    query_text=retrieval_query,
                    top_k=plan.lexical_top_k,
                    statuses=(
                        ["active", "superseded"]
                        if plan.structured_filters.allow_history
                        else ["active"]
                    ),
                    view_types=view_types or plan.structured_filters.view_types or None,
                    query_variants=query_variants,
                )
            )
        user_memory_retrieval_stage_latency_seconds.labels(stage="lexical").observe(
            time.perf_counter() - lexical_started
        )
        user_memory_retrieval_hits_total.labels(source="lexical").inc(len(lexical_items))

        structured_started = time.perf_counter()
        if source_kinds is None or "entry" in source_kinds:
            structured_items.extend(
                get_user_memory_structured_search_service().search_entries(
                    user_id=user_id,
                    filters=StructuredQueryFilters(
                        persons=list(plan.structured_filters.persons),
                        entities=list(plan.structured_filters.entities),
                        locations=list(plan.structured_filters.locations),
                        predicates=list(plan.structured_filters.predicates),
                        fact_kinds=list(fact_kinds or plan.structured_filters.fact_kinds),
                        view_types=[],
                        time_range=plan.structured_filters.time_range,
                        allow_history=plan.structured_filters.allow_history,
                    ),
                    top_k=plan.structured_top_k,
                )
            )
        if source_kinds is None or "relation" in source_kinds:
            structured_items.extend(
                get_user_memory_structured_search_service().search_relations(
                    user_id=user_id,
                    filters=StructuredQueryFilters(
                        persons=list(plan.structured_filters.persons),
                        entities=list(plan.structured_filters.entities),
                        locations=list(plan.structured_filters.locations),
                        predicates=list(plan.structured_filters.predicates),
                        fact_kinds=list(fact_kinds or plan.structured_filters.fact_kinds),
                        view_types=[],
                        time_range=plan.structured_filters.time_range,
                        allow_history=plan.structured_filters.allow_history,
                    ),
                    top_k=plan.structured_top_k,
                )
            )
        if source_kinds is None or "view" in source_kinds:
            structured_items.extend(
                get_user_memory_structured_search_service().search_views(
                    user_id=user_id,
                    filters=StructuredQueryFilters(
                        persons=[],
                        entities=[],
                        locations=list(plan.structured_filters.locations),
                        predicates=[],
                        fact_kinds=list(fact_kinds or plan.structured_filters.fact_kinds),
                        view_types=list(view_types or plan.structured_filters.view_types),
                        time_range=plan.structured_filters.time_range,
                        allow_history=plan.structured_filters.allow_history,
                    ),
                    top_k=plan.structured_top_k,
                )
            )
        user_memory_retrieval_stage_latency_seconds.labels(stage="structured").observe(
            time.perf_counter() - structured_started
        )
        user_memory_retrieval_hits_total.labels(source="structured").inc(len(structured_items))

        merge_started = time.perf_counter()
        merged = self._merge_candidates(
            plan=plan,
            groups={
                "semantic": semantic_items,
                "lexical": lexical_items,
                "structured": structured_items,
            },
        )
        merged = self._apply_temporal_filters(plan=plan, results=merged)
        user_memory_retrieval_stage_latency_seconds.labels(stage="merge").observe(
            time.perf_counter() - merge_started
        )

        rerank_started = time.perf_counter()
        reranked, model_applied = self._apply_rerank(
            query_text=retrieval_query,
            query_terms=plan.keyword_terms,
            results=merged,
            top_k=plan.rerank_top_k,
            structured_filters=plan.structured_filters,
        )
        user_memory_retrieval_stage_latency_seconds.labels(stage="rerank").observe(
            time.perf_counter() - rerank_started
        )

        reflection_cfg = self._reflection_cfg()
        if (
            planner_mode == "api_full"
            and allow_reflection
            and bool(reflection_cfg.get("enabled_api", True))
            and plan.reflection_worthwhile
        ):
            min_results = int(reflection_cfg.get("min_results", 3) or 3)
            min_reflection_score = float(reflection_cfg.get("min_score", 0.45) or 0.45)
            if (
                len(reranked) < min_results
                or float(reranked[0].similarity_score or 0.0) < min_reflection_score
            ):
                user_memory_retrieval_reflection_total.labels(outcome="triggered").inc()
                reflection_started = time.perf_counter()
                extra_queries = get_user_memory_query_planner().build_reflection_queries(
                    query_text=retrieval_query,
                    plan=plan,
                    top_result_content=(reranked[0].content if reranked else None),
                )
                if extra_queries:
                    reflection_plan = QueryPlan(
                        planner_mode=plan.planner_mode,
                        query_variants=build_query_variants(
                            query_text, extra_queries=extra_queries
                        ),
                        keyword_terms=plan.keyword_terms,
                        structured_filters=StructuredQueryFilters(
                            persons=list(plan.structured_filters.persons),
                            entities=list(plan.structured_filters.entities),
                            locations=[],
                            predicates=list(plan.structured_filters.predicates),
                            fact_kinds=list(plan.structured_filters.fact_kinds),
                            view_types=list(plan.structured_filters.view_types),
                            time_range=plan.structured_filters.time_range,
                            allow_history=plan.structured_filters.allow_history,
                        ),
                        reflection_worthwhile=False,
                        vector_top_k=plan.vector_top_k,
                        lexical_top_k=plan.lexical_top_k,
                        structured_top_k=0,
                        rerank_top_k=plan.rerank_top_k,
                    )
                    reflection_semantic = self._semantic_candidates(
                        user_id=user_id,
                        plan=reflection_plan,
                        source_kinds=source_kinds,
                        fact_kinds=fact_kinds,
                        view_types=view_types,
                    )
                    reflection_lexical = list(lexical_items)
                    combined = self._merge_candidates(
                        plan=reflection_plan,
                        groups={
                            "semantic": [*semantic_items, *reflection_semantic],
                            "lexical": reflection_lexical,
                            "structured": structured_items,
                        },
                    )
                    combined = self._apply_temporal_filters(plan=reflection_plan, results=combined)
                    reranked, model_applied = self._apply_rerank(
                        query_text=retrieval_query,
                        query_terms=plan.keyword_terms,
                        results=combined,
                        top_k=plan.rerank_top_k,
                        structured_filters=reflection_plan.structured_filters,
                    )
                user_memory_retrieval_stage_latency_seconds.labels(stage="reflection").observe(
                    time.perf_counter() - reflection_started
                )
            else:
                user_memory_retrieval_reflection_total.labels(outcome="skipped").inc()

        results = self._collapse_duplicate_memories(reranked)
        results = self._apply_min_score(results, min_score=min_score, limit=limit)
        for item in results:
            item.metadata = dict(item.metadata or {})
            item.metadata["_planner_mode"] = plan.planner_mode
            item.metadata["model_rerank_applied"] = model_applied
        logger.info(
            "User-memory hybrid retrieval complete",
            extra={
                "user_id": str(user_id),
                "planner_mode": plan.planner_mode,
                "query_preview": (query_text or "")[:120],
                "semantic_hits": len(semantic_items),
                "lexical_hits": len(lexical_items),
                "structured_hits": len(structured_items),
                "merged_hits": len(merged),
                "returned_hits": len(results),
                "model_rerank_applied": model_applied,
                "reflection_enabled": bool(planner_mode == "api_full" and allow_reflection),
            },
        )
        return results

    def search_user_memory(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
        planner_mode: str = "runtime_light",
        allow_reflection: bool = False,
    ) -> List[RetrievedMemoryItem]:
        return self._search_hybrid(
            user_id=str(user_id),
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode=planner_mode,
            allow_reflection=allow_reflection,
            scope="all",
        )

    def list_profile(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
        planner_mode: str = "api_full",
        allow_reflection: bool = False,
    ) -> List[RetrievedMemoryItem]:
        return self._search_hybrid(
            user_id=str(user_id),
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode=planner_mode,
            allow_reflection=allow_reflection,
            scope="profile",
            source_kinds=["view"],
            view_types=["user_profile"],
        )

    def list_episodes(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
        planner_mode: str = "api_full",
        allow_reflection: bool = False,
    ) -> List[RetrievedMemoryItem]:
        episode_views = self._search_hybrid(
            user_id=str(user_id),
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode=planner_mode,
            allow_reflection=allow_reflection,
            scope="episodes",
            source_kinds=["view"],
            view_types=["episode"],
        )
        if len(episode_views) >= max(int(limit), 1):
            return episode_views[: max(int(limit), 1)]

        remaining = max(int(limit), 1) - len(episode_views)
        event_facts = self._search_hybrid(
            user_id=str(user_id),
            query_text=query_text,
            limit=max(remaining, 1),
            min_score=min_score,
            planner_mode=planner_mode,
            allow_reflection=False,
            scope="episodes",
            source_kinds=["entry"],
            fact_kinds=["event"],
        )
        seen = {self._candidate_key(item) for item in episode_views}
        combined = list(episode_views)
        for item in event_facts:
            key = self._candidate_key(item)
            if key in seen:
                continue
            seen.add(key)
            combined.append(item)
        combined = self._collapse_duplicate_memories(combined)
        return combined[: max(int(limit), 1)]


_hybrid_retriever: Optional[UserMemoryHybridRetriever] = None


def get_user_memory_hybrid_retriever() -> UserMemoryHybridRetriever:
    """Return the shared hybrid retriever."""

    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = UserMemoryHybridRetriever()
    return _hybrid_retriever


__all__ = ["UserMemoryHybridRetriever", "get_user_memory_hybrid_retriever"]
