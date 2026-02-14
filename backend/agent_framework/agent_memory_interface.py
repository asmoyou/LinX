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
from memory_system.memory_system import MemorySystem, get_memory_system

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

    def _retrieve_memories_with_db_alignment(self, search_query: SearchQuery) -> List[MemoryItem]:
        """Retrieve memories aligned with API semantics (DB mapping + text fallback)."""
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
                        {
                            k: v
                            for k, v in semantic_item.metadata.items()
                            if str(k).startswith("_")
                        }
                    )
                items.append(db_item)
            else:
                # Keep API behavior: with user scope, fail-closed for unmapped legacy vectors.
                if search_query.user_id:
                    continue
                items.append(semantic_item)

        if items:
            return items

        fallback_rows = repo.search_text(
            search_query.query_text,
            memory_type=search_query.memory_type,
            agent_id=search_query.agent_id,
            user_id=search_query.user_id,
            task_id=search_query.task_id,
            limit=search_query.top_k or 10,
        )
        return [row.to_memory_item() for row in fallback_rows]

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
        memory_item = MemoryItem(
            content=content,
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            user_id=str(user_id) if user_id else None,
            metadata=metadata or {},
        )

        memory_id = self.memory_system.store_memory(memory_item)
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
        meta = metadata or {}
        meta["auto_generated"] = True
        meta["source"] = "conversation"

        memory_item = MemoryItem(
            content=content,
            memory_type=MemoryType.USER_CONTEXT,
            agent_id=str(agent_id),
            user_id=str(user_id),
            metadata=meta,
        )

        memory_id = self.memory_system.store_memory(memory_item)
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
