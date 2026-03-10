"""Agent memory access interface.

References:
- Requirements 3: Multi-Tiered Memory System
- Design Section 6: Memory System Architecture
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from memory_system.memory_interface import MemoryItem, MemoryType, SearchQuery
from memory_system.memory_repository import get_memory_repository
from memory_system.memory_system import MemoryQualitySkipError, MemorySystem, get_memory_system
from memory_system.retrieval_gateway import get_memory_retrieval_gateway

logger = logging.getLogger(__name__)


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
    def _merge_memory_results(*result_sets: List[MemoryItem], top_k: int) -> List[MemoryItem]:
        """Merge memory candidates from multiple sources and keep the strongest items."""

        combined: List[MemoryItem] = []
        seen_keys = set()
        for result_set in result_sets:
            for item in result_set or []:
                metadata = dict(item.metadata or {})
                dedupe_key = (
                    str(metadata.get("materialization_type") or ""),
                    str(metadata.get("materialization_key") or ""),
                    str(item.content or "").strip(),
                )
                if dedupe_key in seen_keys:
                    continue
                seen_keys.add(dedupe_key)
                combined.append(item)

        combined.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                item.timestamp.isoformat() if item.timestamp else "",
            ),
            reverse=True,
        )
        return combined[: max(int(top_k or 1), 1)]

    def _retrieve_memories_with_db_alignment(self, search_query: SearchQuery) -> List[MemoryItem]:
        """Retrieve memories with DB mapping and strict keyword fallback when semantic misses."""
        gateway = get_memory_retrieval_gateway()
        return gateway.retrieve_memories(
            search_query=search_query,
            memory_system=self.memory_system,
            repository=get_memory_repository(),
            strict_keyword_fallback=gateway.is_strict_keyword_fallback_enabled(),
            cjk_ngram_sizes=(3, 4),
            log_label="Agent memory",
        )

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
        gateway = get_memory_retrieval_gateway()
        results = gateway.retrieve_agent_scope(
            memory_system=self.memory_system,
            repository=get_memory_repository(),
            agent_id=str(agent_id),
            user_id=str(user_id),
            query_text=query,
            top_k=top_k,
            min_similarity=min_similarity,
            strict_keyword_fallback=gateway.is_strict_keyword_fallback_enabled(),
            cjk_ngram_sizes=(3, 4),
        )
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

    def retrieve_user_context_memory(
        self,
        *,
        user_id: UUID | str,
        query: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
    ) -> List[MemoryItem]:
        """Retrieve user-context memories plus materialized user profile."""
        gateway = get_memory_retrieval_gateway()
        results = gateway.retrieve_user_context_scope(
            memory_system=self.memory_system,
            repository=get_memory_repository(),
            user_id=str(user_id),
            query_text=query,
            top_k=top_k,
            min_similarity=min_similarity,
            strict_keyword_fallback=gateway.is_strict_keyword_fallback_enabled(),
            cjk_ngram_sizes=(3, 4),
        )
        logger.info(
            "Retrieved user-context memories",
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
