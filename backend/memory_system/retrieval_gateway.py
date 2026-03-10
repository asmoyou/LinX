"""Shared retrieval gateway for legacy memory records."""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Optional, Sequence

from memory_system.materialization_retrieval_service import get_materialization_retrieval_service
from memory_system.memory_entry_retrieval_service import get_memory_entry_retrieval_service
from memory_system.memory_interface import MemoryItem, MemoryType, SearchQuery
from shared.config import get_config

logger = logging.getLogger(__name__)


_MEMORY_QUERY_STOP_TERMS = {
    "如何",
    "怎么",
    "怎样",
    "请问",
    "一下",
    "可以",
    "是否",
    "这个",
    "那个",
    "是谁",
    "什么",
    "what",
    "how",
    "who",
    "where",
    "when",
    "is",
    "are",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "to",
    "of",
    "in",
    "on",
}
_MEMORY_CJK_QUESTION_TERMS = {"如何", "怎么", "怎样", "请问", "是谁", "什么"}
_MEMORY_CJK_QUESTION_CHARS = {"如", "何", "怎", "样", "请", "问", "谁", "什", "么"}
_KEYWORD_FALLBACK_MIN_RANK = 4.0
_KEYWORD_FALLBACK_SCORE_DENOMINATOR = 6.0


class MemoryRetrievalGateway:
    """Shared retrieval path for semantic search, DB alignment, and keyword fallback."""

    @staticmethod
    def _source_priority(item: MemoryItem) -> int:
        metadata = dict(item.metadata or {})
        source_table = str(metadata.get("source_table") or "").strip().lower()
        memory_source = str(metadata.get("memory_source") or "").strip().lower()
        if (
            source_table == "memory_entries"
            or memory_source == "entry"
            or metadata.get("entry_type")
        ):
            return 3
        if (
            source_table == "memory_materializations"
            or memory_source == "materialization"
            or metadata.get("materialization_type")
        ):
            return 2
        return 1

    @staticmethod
    def merge_results(*result_sets: List[MemoryItem], top_k: int) -> List[MemoryItem]:
        """Merge multiple result sets, dedupe stable items, and keep strongest hits."""

        combined_by_key = {}
        for result_set in result_sets:
            for item in result_set or []:
                metadata = dict(item.metadata or {})
                content_key = str(item.content or "").strip()
                dedupe_key = (
                    str(
                        item.memory_type.value
                        if getattr(item.memory_type, "value", None)
                        else item.memory_type
                    ),
                    content_key
                    or str(
                        metadata.get("materialization_type") or metadata.get("entry_type") or ""
                    ),
                    str(metadata.get("materialization_key") or metadata.get("entry_key") or ""),
                )
                existing = combined_by_key.get(dedupe_key)
                if existing is None:
                    combined_by_key[dedupe_key] = item
                    continue
                existing_rank = (
                    MemoryRetrievalGateway._source_priority(existing),
                    float(existing.similarity_score or 0.0),
                    existing.timestamp.isoformat() if existing.timestamp else "",
                )
                candidate_rank = (
                    MemoryRetrievalGateway._source_priority(item),
                    float(item.similarity_score or 0.0),
                    item.timestamp.isoformat() if item.timestamp else "",
                )
                if candidate_rank > existing_rank:
                    combined_by_key[dedupe_key] = item

        combined = list(combined_by_key.values())

        combined.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                MemoryRetrievalGateway._source_priority(item),
                item.timestamp.isoformat() if item.timestamp else "",
            ),
            reverse=True,
        )
        return combined[: max(int(top_k or 1), 1)]

    @staticmethod
    def is_strict_keyword_fallback_enabled() -> bool:
        try:
            memory_cfg = get_config().get_section("memory")
        except Exception:
            return True
        if not isinstance(memory_cfg, dict):
            return True
        retrieval_cfg = memory_cfg.get("retrieval", {})
        if not isinstance(retrieval_cfg, dict):
            return True
        return bool(retrieval_cfg.get("strict_keyword_fallback", True))

    @staticmethod
    def extract_query_terms(
        query_text: str,
        *,
        max_terms: int = 16,
        cjk_ngram_sizes: Sequence[int] = (3, 4),
    ) -> List[str]:
        normalized = unicodedata.normalize("NFKC", str(query_text or "")).strip().lower()
        if len(normalized) < 2:
            return []

        terms = set()
        for token in re.findall(r"[a-z0-9][a-z0-9._-]{1,}", normalized):
            if token not in _MEMORY_QUERY_STOP_TERMS:
                terms.add(token)

        split_terms = re.split(
            r"[\s,，。！？!?;；:：/\\|()\[\]{}【】\"'“”‘’]+",
            normalized,
        )
        for token in split_terms:
            token = token.strip()
            if len(token) >= 2 and token not in _MEMORY_QUERY_STOP_TERMS:
                terms.add(token)

        cjk_fragments = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", normalized)
        for fragment in cjk_fragments:
            if len(fragment) >= 2 and fragment not in _MEMORY_QUERY_STOP_TERMS:
                terms.add(fragment)

            for n in cjk_ngram_sizes:
                if len(fragment) < n:
                    continue
                for idx in range(len(fragment) - n + 1):
                    gram = fragment[idx : idx + n]
                    if not gram or gram in _MEMORY_QUERY_STOP_TERMS:
                        continue
                    if any(question in gram for question in _MEMORY_CJK_QUESTION_TERMS):
                        continue
                    if gram[0] in _MEMORY_CJK_QUESTION_CHARS:
                        continue
                    terms.add(gram)

        if normalized not in _MEMORY_QUERY_STOP_TERMS and len(normalized) >= 2:
            terms.add(normalized)

        return sorted(terms, key=lambda item: (-len(item), item))[: max(int(max_terms), 1)]

    @staticmethod
    def keyword_min_term_hits(query_terms: List[str]) -> int:
        term_count = len([term for term in query_terms if len(str(term).strip()) >= 2])
        if term_count <= 1:
            return 1
        if term_count <= 4:
            return 2
        return 3

    @staticmethod
    def keyword_rank_to_similarity(rank: float) -> float:
        safe_rank = max(float(rank or 0.0), 0.0)
        return min(max(safe_rank / (safe_rank + _KEYWORD_FALLBACK_SCORE_DENOMINATOR), 0.0), 1.0)

    def retrieve_memories(
        self,
        *,
        search_query: SearchQuery,
        memory_system,
        repository,
        strict_keyword_fallback: bool,
        cjk_ngram_sizes: Sequence[int] = (3, 4),
        log_label: str = "Memory",
    ) -> List[MemoryItem]:
        """Retrieve memories with semantic alignment first and keyword fallback second."""

        items: List[MemoryItem] = []
        try:
            semantic_items = memory_system.retrieve_memories(search_query)

            milvus_ids: List[int] = []
            for semantic_item in semantic_items:
                if semantic_item.id is None:
                    continue
                try:
                    milvus_ids.append(int(semantic_item.id))
                except (TypeError, ValueError):
                    continue

            mapped_by_milvus = repository.get_by_milvus_ids(milvus_ids)
            for semantic_item in semantic_items:
                mapped = None
                try:
                    mapped = mapped_by_milvus.get(int(semantic_item.id))
                except (TypeError, ValueError):
                    mapped = None

                if mapped:
                    if search_query.user_id and str(mapped.user_id or "") != str(
                        search_query.user_id
                    ):
                        continue
                    db_item = mapped.to_memory_item(similarity_score=semantic_item.similarity_score)
                    if semantic_item.metadata:
                        db_item.metadata = db_item.metadata or {}
                        db_item.metadata.update(
                            {
                                key: value
                                for key, value in semantic_item.metadata.items()
                                if str(key).startswith("_")
                            }
                        )
                    items.append(db_item)
                else:
                    if search_query.user_id:
                        continue
                    items.append(semantic_item)
        except Exception as exc:
            logger.warning(
                "%s semantic search failed, attempting keyword fallback: %s", log_label, exc
            )

        if items:
            return items

        query_terms = self.extract_query_terms(
            search_query.query_text,
            cjk_ngram_sizes=cjk_ngram_sizes,
        )
        keyword_rows = repository.search_keywords(
            search_query.query_text,
            query_terms=query_terms,
            memory_type=search_query.memory_type,
            agent_id=search_query.agent_id,
            user_id=search_query.user_id,
            task_id=search_query.task_id,
            min_term_hits=self.keyword_min_term_hits(query_terms),
            min_rank=_KEYWORD_FALLBACK_MIN_RANK,
            limit=search_query.top_k or 10,
            strict_semantics=bool(strict_keyword_fallback),
        )

        effective_min_similarity = (
            max(float(search_query.min_similarity), 0.0)
            if search_query.min_similarity is not None
            else max(float(getattr(memory_system, "_default_similarity_threshold", 0.0)), 0.0)
        )
        fallback_items: List[MemoryItem] = []
        for row, rank, term_hits in keyword_rows:
            score = self.keyword_rank_to_similarity(rank)
            if score < effective_min_similarity:
                continue

            item = row.to_memory_item(similarity_score=score)
            item.metadata = dict(item.metadata or {})
            item.metadata["search_method"] = "keyword"
            item.metadata["keyword_mode"] = "strict" if strict_keyword_fallback else "legacy"
            item.metadata["keyword_rank"] = round(float(rank), 4)
            item.metadata["keyword_term_hits"] = int(term_hits)
            fallback_items.append(item)

        if fallback_items:
            logger.info(
                "%s keyword fallback matched results",
                log_label,
                extra={
                    "query_preview": (search_query.query_text or "")[:120],
                    "hit_count": len(fallback_items),
                    "min_similarity": effective_min_similarity,
                },
            )

        return fallback_items

    def retrieve_materializations(
        self,
        *,
        materialization_type: str,
        owner_id: str,
        query_text: str,
        top_k: Optional[int],
        min_similarity: Optional[float] = None,
    ) -> List[MemoryItem]:
        """Retrieve read-only materialized projections through one shared path."""

        service = get_materialization_retrieval_service()
        if materialization_type == "user_profile":
            items = service.retrieve_user_profile(
                user_id=str(owner_id),
                query_text=str(query_text or "*"),
                top_k=(max(int(top_k), 1) if top_k is not None else None),
            )
        elif materialization_type == "agent_experience":
            items = service.retrieve_agent_experience(
                agent_id=str(owner_id),
                query_text=str(query_text or "*"),
                top_k=(max(int(top_k), 1) if top_k is not None else None),
            )
        else:
            raise ValueError(f"Unsupported materialization_type: {materialization_type}")

        if min_similarity is not None:
            threshold = max(float(min_similarity), 0.0)
            items = [item for item in items if float(item.similarity_score or 0.0) >= threshold]

        for item in items:
            item.metadata = dict(item.metadata or {})
            item.metadata["read_only"] = True
            item.metadata["source_table"] = "memory_materializations"

        return items

    def retrieve_entries(
        self,
        *,
        entry_type: str,
        owner_id: str,
        query_text: str,
        top_k: Optional[int],
        min_similarity: Optional[float] = None,
        status: Optional[str] = "active",
    ) -> List[MemoryItem]:
        """Retrieve read-only atomic memory entries through one shared path."""

        service = get_memory_entry_retrieval_service()
        if entry_type == "user_fact":
            items = service.retrieve_user_facts(
                user_id=str(owner_id),
                query_text=str(query_text or "*"),
                top_k=(max(int(top_k), 1) if top_k is not None else None),
                status=status,
            )
        elif entry_type == "agent_skill_candidate":
            items = service.retrieve_agent_skill_candidates(
                agent_id=str(owner_id),
                query_text=str(query_text or "*"),
                top_k=(max(int(top_k), 1) if top_k is not None else None),
                status=status,
            )
        else:
            raise ValueError(f"Unsupported entry_type: {entry_type}")

        if min_similarity is not None:
            threshold = max(float(min_similarity), 0.0)
            items = [item for item in items if float(item.similarity_score or 0.0) >= threshold]

        for item in items:
            item.metadata = dict(item.metadata or {})
            item.metadata["read_only"] = True
            item.metadata["source_table"] = "memory_entries"

        return items

    def list_scope_memories(
        self,
        *,
        search_query: SearchQuery,
        repository,
        agent_materialization_owner_ids: Optional[Sequence[str]] = None,
    ) -> List[MemoryItem]:
        """List wildcard scope memories from DB records plus active materializations."""

        rows = repository.list_memories(
            memory_type=search_query.memory_type,
            agent_id=search_query.agent_id,
            user_id=search_query.user_id,
            task_id=search_query.task_id,
            limit=search_query.top_k,
        )
        legacy_items = [row.to_memory_item() for row in rows]
        materialized_items: List[MemoryItem] = []
        entry_items: List[MemoryItem] = []

        if search_query.memory_type == MemoryType.USER_CONTEXT and search_query.user_id:
            materialized_items = self.retrieve_materializations(
                materialization_type="user_profile",
                owner_id=str(search_query.user_id),
                query_text="*",
                top_k=search_query.top_k,
            )
            entry_items = self.retrieve_entries(
                entry_type="user_fact",
                owner_id=str(search_query.user_id),
                query_text="*",
                top_k=search_query.top_k,
                status="active",
            )
        elif search_query.memory_type == MemoryType.AGENT:
            owner_ids: List[str] = []
            if search_query.agent_id:
                owner_ids.append(str(search_query.agent_id))
            elif agent_materialization_owner_ids:
                owner_ids.extend(
                    str(owner_id).strip()
                    for owner_id in agent_materialization_owner_ids
                    if str(owner_id).strip()
                )
            seen_owner_ids = set()
            for owner_id in owner_ids:
                if owner_id in seen_owner_ids:
                    continue
                seen_owner_ids.add(owner_id)
                materialized_items.extend(
                    self.retrieve_materializations(
                        materialization_type="agent_experience",
                        owner_id=owner_id,
                        query_text="*",
                        top_k=search_query.top_k,
                    )
                )
                entry_items.extend(
                    self.retrieve_entries(
                        entry_type="agent_skill_candidate",
                        owner_id=owner_id,
                        query_text="*",
                        top_k=search_query.top_k,
                        status="active",
                    )
                )

        effective_top_k = search_query.top_k or max(
            len(legacy_items) + len(materialized_items) + len(entry_items), 1
        )
        return self.merge_results(
            entry_items,
            materialized_items,
            legacy_items,
            top_k=effective_top_k,
        )

    def retrieve_agent_scope(
        self,
        *,
        memory_system,
        repository,
        agent_id: str,
        user_id: str,
        query_text: str,
        top_k: int,
        min_similarity: Optional[float] = None,
        strict_keyword_fallback: Optional[bool] = None,
        cjk_ngram_sizes: Sequence[int] = (3, 4),
    ) -> List[MemoryItem]:
        """Retrieve agent scope from legacy records plus agent experience materializations."""

        if strict_keyword_fallback is None:
            strict_keyword_fallback = self.is_strict_keyword_fallback_enabled()

        search_query = SearchQuery(
            query_text=query_text,
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            user_id=str(user_id),
            top_k=top_k,
            min_similarity=min_similarity,
        )
        legacy_items = self.retrieve_memories(
            search_query=search_query,
            memory_system=memory_system,
            repository=repository,
            strict_keyword_fallback=bool(strict_keyword_fallback),
            cjk_ngram_sizes=cjk_ngram_sizes,
            log_label="Agent memory",
        )
        materialized_items = self.retrieve_materializations(
            materialization_type="agent_experience",
            owner_id=str(agent_id),
            query_text=query_text,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        entry_items = self.retrieve_entries(
            entry_type="agent_skill_candidate",
            owner_id=str(agent_id),
            query_text=query_text,
            top_k=top_k,
            min_similarity=min_similarity,
            status="active",
        )
        return self.merge_results(entry_items, materialized_items, legacy_items, top_k=top_k)

    def retrieve_owned_agent_scope(
        self,
        *,
        memory_system,
        repository,
        owner_ids: Sequence[str],
        user_id: Optional[str],
        query_text: str,
        top_k: int,
        min_similarity: Optional[float] = None,
        strict_keyword_fallback: Optional[bool] = None,
        cjk_ngram_sizes: Sequence[int] = (3, 4),
    ) -> List[MemoryItem]:
        """Retrieve owned-agent scope across multiple agent owners for one user."""

        if strict_keyword_fallback is None:
            strict_keyword_fallback = self.is_strict_keyword_fallback_enabled()

        search_query = SearchQuery(
            query_text=query_text,
            memory_type=MemoryType.AGENT,
            user_id=str(user_id) if user_id else None,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        legacy_items = self.retrieve_memories(
            search_query=search_query,
            memory_system=memory_system,
            repository=repository,
            strict_keyword_fallback=bool(strict_keyword_fallback),
            cjk_ngram_sizes=cjk_ngram_sizes,
            log_label="Agent memory",
        )

        materialized_items: List[MemoryItem] = []
        entry_items: List[MemoryItem] = []
        seen_owner_ids = set()
        for owner_id in owner_ids or []:
            normalized_owner_id = str(owner_id or "").strip()
            if not normalized_owner_id or normalized_owner_id in seen_owner_ids:
                continue
            seen_owner_ids.add(normalized_owner_id)
            materialized_items.extend(
                self.retrieve_materializations(
                    materialization_type="agent_experience",
                    owner_id=normalized_owner_id,
                    query_text=query_text,
                    top_k=top_k,
                    min_similarity=min_similarity,
                )
            )
            entry_items.extend(
                self.retrieve_entries(
                    entry_type="agent_skill_candidate",
                    owner_id=normalized_owner_id,
                    query_text=query_text,
                    top_k=top_k,
                    min_similarity=min_similarity,
                    status="active",
                )
            )

        return self.merge_results(entry_items, materialized_items, legacy_items, top_k=top_k)

    def retrieve_user_context_scope(
        self,
        *,
        memory_system,
        repository,
        user_id: str,
        query_text: str,
        top_k: int,
        min_similarity: Optional[float] = None,
        strict_keyword_fallback: Optional[bool] = None,
        cjk_ngram_sizes: Sequence[int] = (3, 4),
    ) -> List[MemoryItem]:
        """Retrieve user context from legacy records plus materialized user profile."""

        if strict_keyword_fallback is None:
            strict_keyword_fallback = self.is_strict_keyword_fallback_enabled()

        search_query = SearchQuery(
            query_text=query_text,
            memory_type=MemoryType.USER_CONTEXT,
            user_id=str(user_id),
            top_k=top_k,
            min_similarity=min_similarity,
        )
        legacy_items = self.retrieve_memories(
            search_query=search_query,
            memory_system=memory_system,
            repository=repository,
            strict_keyword_fallback=bool(strict_keyword_fallback),
            cjk_ngram_sizes=cjk_ngram_sizes,
            log_label="User-context memory",
        )
        materialized_items = self.retrieve_materializations(
            materialization_type="user_profile",
            owner_id=str(user_id),
            query_text=query_text,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        entry_items = self.retrieve_entries(
            entry_type="user_fact",
            owner_id=str(user_id),
            query_text=query_text,
            top_k=top_k,
            min_similarity=min_similarity,
            status="active",
        )
        return self.merge_results(entry_items, materialized_items, legacy_items, top_k=top_k)


_memory_retrieval_gateway: Optional[MemoryRetrievalGateway] = None


def get_memory_retrieval_gateway() -> MemoryRetrievalGateway:
    """Return a process-wide retrieval gateway singleton."""

    global _memory_retrieval_gateway
    if _memory_retrieval_gateway is None:
        _memory_retrieval_gateway = MemoryRetrievalGateway()
    return _memory_retrieval_gateway
