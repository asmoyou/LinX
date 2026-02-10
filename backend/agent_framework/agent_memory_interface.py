"""Agent memory access interface.

References:
- Requirements 3: Multi-Tiered Memory System
- Design Section 6: Memory System Architecture
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from memory_system.memory_interface import MemoryItem, MemoryType, SearchQuery
from memory_system.memory_system import MemorySystem, get_memory_system

logger = logging.getLogger(__name__)


class AgentMemoryInterface:
    """Interface for agents to access memory systems."""

    def __init__(self, memory_system: Optional[MemorySystem] = None):
        """Initialize agent memory interface.

        Args:
            memory_system: MemorySystem instance
        """
        self.memory_system = memory_system or get_memory_system()
        logger.info("AgentMemoryInterface initialized")

    def store_agent_memory(
        self,
        agent_id: UUID,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Store memory in Agent Memory (private).

        Args:
            agent_id: Agent UUID
            content: Memory content
            metadata: Optional metadata

        Returns:
            Memory ID
        """
        memory_item = MemoryItem(
            content=content,
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            metadata=metadata or {},
        )

        memory_id = self.memory_system.store_memory(memory_item)
        logger.info(f"Agent memory stored: {memory_id}")
        return memory_id

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
        return memory_id

    def retrieve_agent_memory(
        self,
        agent_id: UUID,
        query: str,
        top_k: int = 5,
    ) -> List[MemoryItem]:
        """Retrieve relevant memories from Agent Memory.

        Args:
            agent_id: Agent UUID
            query: Search query
            top_k: Number of results

        Returns:
            List of MemoryItem objects
        """
        search_query = SearchQuery(
            query_text=query,
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            top_k=top_k,
        )

        results = self.memory_system.retrieve_memories(search_query)
        logger.info(f"Retrieved {len(results)} agent memories")
        return results

    def retrieve_company_memory(
        self,
        user_id: UUID,
        query: str,
        top_k: int = 5,
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
        )

        results = self.memory_system.retrieve_memories(search_query)
        logger.info(f"Retrieved {len(results)} company memories")
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
        return memory_id


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
