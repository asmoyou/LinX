"""Agent memory access interface.

References:
- Requirements 3: Multi-Tiered Memory System
- Design Section 6: Memory System Architecture
"""

import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional
from uuid import UUID

from memory_system.memory_interface import MemoryItem, MemoryType, SearchQuery
from memory_system.memory_repository import get_memory_repository
from memory_system.memory_system import MemoryQualitySkipError, MemorySystem, get_memory_system
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


def _format_agent_memory_content(
    task: str,
    result: str,
    agent_name: str = "",
    max_result_length: int = 240,
) -> str:
    """Format agent memory content with structured layout and truncation.

    Args:
        task: Task description or user message
        result: Agent response or execution output
        agent_name: Name of the agent
        max_result_length: Maximum characters for the result field

    Returns:
        Structured memory content string
    """
    task_trimmed = (task or "").strip()[:300]
    result_trimmed = (result or "").strip()
    if len(result_trimmed) > max_result_length:
        result_trimmed = result_trimmed[:max_result_length] + "..."

    parts = []
    if agent_name:
        parts.append(f"[Agent: {agent_name}]")
    parts.append(f"Task: {task_trimmed}")
    parts.append(f"Result: {result_trimmed}")
    return "\n".join(parts)


def _format_user_context_content(
    user_message: str,
    agent_name: str = "",
    response_summary: str = "",
    max_message_length: int = 300,
) -> str:
    """Format user context memory with structured layout and truncation.

    Args:
        user_message: The user's message/query
        agent_name: Name of the responding agent
        response_summary: Brief summary of the response topic
        max_message_length: Maximum characters for user message

    Returns:
        Structured user context string
    """
    msg_trimmed = (user_message or "").strip()
    if len(msg_trimmed) > max_message_length:
        msg_trimmed = msg_trimmed[:max_message_length] + "..."

    parts = [f"User discussed: {msg_trimmed}"]
    if agent_name:
        parts.append(f"Agent: {agent_name}")
    if response_summary:
        summary_trimmed = (response_summary or "").strip()[:200]
        parts.append(f"Topic: {summary_trimmed}")
    return "\n".join(parts)


class AgentMemoryInterface:
    """Interface for agents to access memory systems."""

    def __init__(self, memory_system: Optional[MemorySystem] = None):
        """Initialize agent memory interface.

        Args:
            memory_system: MemorySystem instance
        """
        self.memory_system = memory_system or get_memory_system()
        logger.info("AgentMemoryInterface initialized")

    @staticmethod
    def _extract_query_terms(query_text: str, *, max_terms: int = 16) -> List[str]:
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

            for n in (3, 4):
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
    def _keyword_min_term_hits(query_terms: List[str]) -> int:
        term_count = len([term for term in query_terms if len(str(term).strip()) >= 2])
        if term_count <= 1:
            return 1
        if term_count <= 4:
            return 2
        return 3

    @staticmethod
    def _keyword_rank_to_similarity(rank: float) -> float:
        safe_rank = max(float(rank or 0.0), 0.0)
        return min(max(safe_rank / (safe_rank + _KEYWORD_FALLBACK_SCORE_DENOMINATOR), 0.0), 1.0)

    @staticmethod
    def _is_strict_keyword_fallback_enabled() -> bool:
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

    def _retrieve_memories_with_db_alignment(self, search_query: SearchQuery) -> List[MemoryItem]:
        """Retrieve memories with DB mapping and strict keyword fallback when semantic misses."""
        repo = get_memory_repository()
        semantic_items = self.memory_system.retrieve_memories(search_query)

        milvus_ids: List[int] = []
        for semantic_item in semantic_items:
            if semantic_item.id is None:
                continue
            try:
                milvus_ids.append(int(semantic_item.id))
            except (TypeError, ValueError):
                continue

        mapped_by_milvus = repo.get_by_milvus_ids(milvus_ids)
        items: List[MemoryItem] = []

        for semantic_item in semantic_items:
            mapped = None
            try:
                mapped = mapped_by_milvus.get(int(semantic_item.id))
            except (TypeError, ValueError):
                mapped = None

            if mapped:
                if search_query.user_id and str(mapped.user_id or "") != str(search_query.user_id):
                    continue
                db_item = mapped.to_memory_item(similarity_score=semantic_item.similarity_score)
                if semantic_item.metadata:
                    db_item.metadata = db_item.metadata or {}
                    db_item.metadata.update(
                        {k: v for k, v in semantic_item.metadata.items() if str(k).startswith("_")}
                    )
                items.append(db_item)
            else:
                # Keep API behavior: with user scope, fail-closed for unmapped legacy vectors.
                if search_query.user_id:
                    continue
                items.append(semantic_item)

        if items:
            return items

        query_terms = self._extract_query_terms(search_query.query_text)
        strict_keyword_fallback = self._is_strict_keyword_fallback_enabled()
        keyword_rows = repo.search_keywords(
            search_query.query_text,
            query_terms=query_terms,
            memory_type=search_query.memory_type,
            agent_id=search_query.agent_id,
            user_id=search_query.user_id,
            task_id=search_query.task_id,
            min_term_hits=self._keyword_min_term_hits(query_terms),
            min_rank=_KEYWORD_FALLBACK_MIN_RANK,
            limit=search_query.top_k or 10,
            strict_semantics=strict_keyword_fallback,
        )

        effective_min_similarity = (
            max(float(search_query.min_similarity), 0.0)
            if search_query.min_similarity is not None
            else max(float(getattr(self.memory_system, "_default_similarity_threshold", 0.0)), 0.0)
        )
        fallback_items: List[MemoryItem] = []
        for row, rank, term_hits in keyword_rows:
            score = self._keyword_rank_to_similarity(rank)
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
                "Agent memory keyword fallback matched results",
                extra={
                    "query_preview": (search_query.query_text or "")[:120],
                    "hit_count": len(fallback_items),
                    "min_similarity": effective_min_similarity,
                },
            )

        return fallback_items

    def store_agent_memory(
        self,
        agent_id: UUID,
        content: str,
        user_id: Optional[UUID | str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store memory in Agent Memory (private).

        Args:
            agent_id: Agent UUID
            content: Memory content
            user_id: Optional user UUID (owner/initiator). If omitted, storage layer attempts
                owner resolution by agent_id.
            metadata: Optional metadata

        Returns:
            Memory ID
        """
        meta = dict(metadata or {})
        if bool(meta.get("auto_generated")):
            meta.setdefault("fail_closed_extraction", True)

        memory_item = MemoryItem(
            content=content,
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            user_id=str(user_id) if user_id else None,
            metadata=meta,
        )

        try:
            memory_id = self.memory_system.store_memory(memory_item)
        except MemoryQualitySkipError as exc:
            logger.info("Agent memory skipped by quality gate: %s", exc)
            return ""
        logger.info(f"Agent memory stored: {memory_id}")
        return str(memory_id)

    def store_company_memory(
        self,
        agent_id: UUID,
        user_id: UUID,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store memory in Company Memory (shared).

        Args:
            agent_id: Agent UUID
            user_id: User UUID
            content: Memory content
            metadata: Optional metadata

        Returns:
            Memory ID
        """
        memory_item = MemoryItem(
            content=content,
            memory_type=MemoryType.COMPANY,
            agent_id=str(agent_id),
            user_id=str(user_id),
            metadata=metadata or {},
        )

        memory_id = self.memory_system.store_memory(memory_item)
        logger.info(f"Company memory stored: {memory_id}")
        return str(memory_id)

    def retrieve_agent_memory(
        self,
        agent_id: UUID,
        user_id: UUID | str,
        query: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
    ) -> List[MemoryItem]:
        """Retrieve relevant memories from Agent Memory.

        Args:
            agent_id: Agent UUID
            user_id: User UUID (strict agent-memory scope)
            query: Search query
            top_k: Number of results

        Returns:
            List of MemoryItem objects
        """
        search_query = SearchQuery(
            query_text=query,
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            user_id=str(user_id),
            top_k=top_k,
            min_similarity=min_similarity,
        )

        results = self._retrieve_memories_with_db_alignment(search_query)
        logger.info(
            "Retrieved agent memories",
            extra={
                "agent_id": str(agent_id),
                "user_id": str(user_id),
                "top_k": top_k,
                "min_similarity": min_similarity,
                "hit_count": len(results),
                "query_preview": (query or "")[:120],
            },
        )
        return results

    def retrieve_company_memory(
        self,
        user_id: UUID,
        query: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
    ) -> List[MemoryItem]:
        """Retrieve relevant memories from Company Memory.

        Args:
            user_id: User UUID
            query: Search query
            top_k: Number of results

        Returns:
            List of MemoryItem objects
        """
        search_query = SearchQuery(
            query_text=query,
            memory_type=MemoryType.COMPANY,
            user_id=str(user_id),
            top_k=top_k,
            min_similarity=min_similarity,
        )

        results = self._retrieve_memories_with_db_alignment(search_query)
        logger.info(
            "Retrieved company memories",
            extra={
                "user_id": str(user_id),
                "top_k": top_k,
                "min_similarity": min_similarity,
                "hit_count": len(results),
                "query_preview": (query or "")[:120],
            },
        )
        return results

    def store_user_context(
        self,
        user_id: UUID,
        agent_id: UUID,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store user context memory (auto-generated from conversations).

        Captures user preferences, communication style, and interaction patterns.

        Args:
            user_id: User UUID
            agent_id: Agent UUID that interacted with user
            content: User context content
            metadata: Optional metadata

        Returns:
            Memory ID
        """
        meta = dict(metadata or {})
        meta.setdefault("auto_generated", True)
        meta.setdefault("source", "conversation")
        meta.setdefault("fail_closed_extraction", True)

        memory_item = MemoryItem(
            content=content,
            memory_type=MemoryType.USER_CONTEXT,
            agent_id=str(agent_id),
            user_id=str(user_id),
            metadata=meta,
        )

        try:
            memory_id = self.memory_system.store_memory(memory_item)
        except MemoryQualitySkipError as exc:
            logger.info("User context memory skipped by quality gate: %s", exc)
            return ""
        logger.info(f"User context stored: {memory_id}")
        return str(memory_id)


# Singleton instance
_agent_memory_interface: Optional[AgentMemoryInterface] = None


def get_agent_memory_interface() -> AgentMemoryInterface:
    """Get or create the agent memory interface singleton.

    Returns:
        AgentMemoryInterface instance
    """
    global _agent_memory_interface
    if _agent_memory_interface is None:
        _agent_memory_interface = AgentMemoryInterface()
    return _agent_memory_interface
