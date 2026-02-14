"""Memory System interface and base classes.

This module defines the interface for the multi-tiered memory system including:
- Agent Memory (private to each agent)
- Company Memory (shared across agents)
- User Context (user-specific information accessible to all user's agents)

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 6: Memory System Design
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """Enum for memory types."""

    AGENT = "agent"  # Private agent memory
    COMPANY = "company"  # Shared company memory
    USER_CONTEXT = "user_context"  # User-specific context
    TASK_CONTEXT = "task_context"  # Task-specific context


@dataclass
class MemoryItem:
    """
    Represents a single memory item.

    Attributes:
        id: Unique identifier (assigned by Milvus)
        content: Text content of the memory
        embedding: Vector embedding (optional, generated on storage)
        memory_type: Type of memory (agent, company, user_context, task_context)
        agent_id: Agent identifier (for agent memories)
        user_id: User identifier (for user context and filtering)
        task_id: Task identifier (for task context)
        timestamp: Creation timestamp
        metadata: Additional metadata
        similarity_score: Similarity score (for search results)
    """

    content: str
    memory_type: MemoryType
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    task_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[Dict[str, Any]] = None
    id: Optional[int] = None
    embedding: Optional[List[float]] = None
    similarity_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert memory item to dictionary."""
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": (
                self.memory_type.value
                if isinstance(self.memory_type, MemoryType)
                else self.memory_type
            ),
            "agent_id": self.agent_id,
            "user_id": self.user_id,
            "task_id": self.task_id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metadata": self.metadata,
            "similarity_score": self.similarity_score,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryItem":
        """Create memory item from dictionary."""
        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        memory_type = data.get("memory_type")
        if isinstance(memory_type, str):
            memory_type = MemoryType(memory_type)

        return cls(
            id=data.get("id"),
            content=data["content"],
            memory_type=memory_type,
            agent_id=data.get("agent_id"),
            user_id=data.get("user_id"),
            task_id=data.get("task_id"),
            timestamp=timestamp,
            metadata=data.get("metadata"),
            embedding=data.get("embedding"),
            similarity_score=data.get("similarity_score"),
        )


@dataclass
class SearchQuery:
    """
    Represents a memory search query.

    Attributes:
        query_text: Text query for semantic search
        memory_type: Type of memory to search (optional, searches all if None)
        agent_id: Filter by agent ID (for agent memories)
        user_id: Filter by user ID (for user context)
        task_id: Filter by task ID (for task context)
        top_k: Number of results to return
        min_similarity: Optional minimum similarity threshold. None means use system default.
        include_metadata: Whether to include metadata in results
    """

    query_text: str
    memory_type: Optional[MemoryType] = None
    agent_id: Optional[str] = None
    user_id: Optional[str] = None
    task_id: Optional[str] = None
    top_k: int = 10
    min_similarity: Optional[float] = None
    include_metadata: bool = True


class MemorySystemInterface(ABC):
    """
    Abstract interface for the Memory System.

    This interface defines the contract for memory storage and retrieval
    operations across all memory tiers (Agent, Company, User Context).
    """

    @abstractmethod
    def store_memory(self, memory: MemoryItem) -> int:
        """
        Store a memory item.

        Args:
            memory: Memory item to store

        Returns:
            int: ID of the stored memory

        Raises:
            ValueError: If memory data is invalid
            RuntimeError: If storage fails
        """
        pass

    @abstractmethod
    def retrieve_memories(self, query: SearchQuery) -> List[MemoryItem]:
        """
        Retrieve memories based on semantic similarity search.

        Args:
            query: Search query with filters

        Returns:
            List[MemoryItem]: List of matching memories ranked by relevance

        Raises:
            ValueError: If query is invalid
            RuntimeError: If retrieval fails
        """
        pass

    @abstractmethod
    def delete_memory(self, memory_id: int, memory_type: MemoryType) -> bool:
        """
        Delete a specific memory by ID.

        Args:
            memory_id: ID of the memory to delete
            memory_type: Type of memory (determines collection)

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        pass

    @abstractmethod
    def archive_agent_memories(self, agent_id: str) -> Dict[str, Any]:
        """
        Archive all memories for an agent to cold storage.

        This is called when an agent is terminated.

        Args:
            agent_id: Agent identifier

        Returns:
            dict: Archive metadata (location, count, timestamp)
        """
        pass

    @abstractmethod
    def classify_memory_type(
        self, content: str, context: Optional[Dict[str, Any]] = None
    ) -> MemoryType:
        """
        Classify whether memory should be user-specific or task-specific.

        Args:
            content: Memory content text
            context: Additional context for classification

        Returns:
            MemoryType: Classified memory type
        """
        pass

    @abstractmethod
    def share_memory(
        self, memory_id: int, source_type: MemoryType, target_user_ids: List[str]
    ) -> bool:
        """
        Share a memory with specific users.

        Args:
            memory_id: ID of the memory to share
            source_type: Source memory type
            target_user_ids: List of user IDs to share with

        Returns:
            bool: True if shared successfully
        """
        pass

    @abstractmethod
    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about memory usage.

        Returns:
            dict: Statistics including counts, sizes, etc.
        """
        pass


class EmbeddingServiceInterface(ABC):
    """
    Abstract interface for embedding generation service.

    This interface defines the contract for generating embeddings
    from text using local LLM providers.
    """

    @abstractmethod
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding vector for text.

        Args:
            text: Input text

        Returns:
            List[float]: Embedding vector

        Raises:
            RuntimeError: If embedding generation fails
        """
        pass

    @abstractmethod
    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batch.

        Args:
            texts: List of input texts

        Returns:
            List[List[float]]: List of embedding vectors

        Raises:
            RuntimeError: If embedding generation fails
        """
        pass

    @abstractmethod
    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this service.

        Returns:
            int: Embedding dimension
        """
        pass
