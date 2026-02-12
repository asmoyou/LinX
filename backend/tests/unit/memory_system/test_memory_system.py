"""Tests for Memory System implementation.

This module tests the multi-tiered memory system including:
- Memory storage and retrieval
- Semantic similarity search
- Memory type classification
- Memory sharing
- Memory archival

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 6: Memory System Design
"""

from datetime import datetime, timedelta
from typing import List
from unittest.mock import MagicMock, Mock, patch

import pytest

from memory_system.embedding_service import OllamaEmbeddingService
from memory_system.memory_interface import (
    MemoryItem,
    MemoryType,
    SearchQuery,
)
from memory_system.memory_system import MemorySystem


class MockEmbeddingService:
    """Mock embedding service for testing."""

    def __init__(self, dimension: int = 768):
        self._dimension = dimension

    def generate_embedding(self, text: str) -> List[float]:
        """Generate a mock embedding based on text hash."""
        # Simple deterministic embedding based on text
        hash_val = hash(text)
        return [(hash_val % 1000) / 1000.0] * self._dimension

    def generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings for batch."""
        return [self.generate_embedding(text) for text in texts]

    def get_embedding_dimension(self) -> int:
        """Get embedding dimension."""
        return self._dimension


@pytest.fixture
def mock_embedding_service():
    """Fixture for mock embedding service."""
    return MockEmbeddingService()


@pytest.fixture
def mock_milvus_connection():
    """Fixture for mock Milvus connection."""
    mock_conn = Mock()
    mock_collection = Mock()

    # Mock collection methods
    mock_collection.insert.return_value = Mock(primary_keys=[1])
    mock_collection.search.return_value = [[]]
    mock_collection.query.return_value = []
    mock_collection.delete.return_value = None

    mock_conn.get_collection.return_value = mock_collection
    mock_conn.get_collection_stats.return_value = {"name": "test_collection", "num_entities": 0}

    return mock_conn


@pytest.fixture
def memory_system(mock_embedding_service, mock_milvus_connection):
    """Fixture for Memory System with mocked dependencies."""
    with patch(
        "memory_system.memory_system.get_embedding_service", return_value=mock_embedding_service
    ):
        with patch(
            "memory_system.memory_system.get_milvus_connection", return_value=mock_milvus_connection
        ):
            system = MemorySystem()
            return system


class TestMemoryItem:
    """Tests for MemoryItem data class."""

    def test_memory_item_creation(self):
        """Test creating a memory item."""
        memory = MemoryItem(
            content="Test memory content",
            memory_type=MemoryType.AGENT,
            agent_id="agent123",
            user_id="user123",
        )

        assert memory.content == "Test memory content"
        assert memory.memory_type == MemoryType.AGENT
        assert memory.agent_id == "agent123"
        assert memory.user_id == "user123"

    def test_memory_item_to_dict(self):
        """Test converting memory item to dictionary."""
        timestamp = datetime.utcnow()
        memory = MemoryItem(
            content="Test content",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
            timestamp=timestamp,
            metadata={"key": "value"},
        )

        data = memory.to_dict()

        assert data["content"] == "Test content"
        assert data["memory_type"] == "user_context"
        assert data["user_id"] == "user123"
        assert data["timestamp"] == timestamp.isoformat()
        assert data["metadata"] == {"key": "value"}

    def test_memory_item_from_dict(self):
        """Test creating memory item from dictionary."""
        data = {
            "id": 1,
            "content": "Test content",
            "memory_type": "company",
            "user_id": "user123",
            "timestamp": "2024-01-01T12:00:00",
            "metadata": {"key": "value"},
            "similarity_score": 0.95,
        }

        memory = MemoryItem.from_dict(data)

        assert memory.id == 1
        assert memory.content == "Test content"
        assert memory.memory_type == MemoryType.COMPANY
        assert memory.user_id == "user123"
        assert isinstance(memory.timestamp, datetime)
        assert memory.metadata == {"key": "value"}
        assert memory.similarity_score == 0.95


class TestMemoryStorage:
    """Tests for memory storage operations."""

    def test_store_agent_memory(self, memory_system):
        """Test storing an agent memory."""
        memory = MemoryItem(
            content="Agent learned something new", memory_type=MemoryType.AGENT, agent_id="agent123"
        )

        memory_id = memory_system.store_memory(memory)

        assert memory_id == 1
        assert memory.embedding is not None
        assert len(memory.embedding) == 768

    def test_store_user_context_memory(self, memory_system):
        """Test storing a user context memory."""
        memory = MemoryItem(
            content="User prefers dark mode", memory_type=MemoryType.USER_CONTEXT, user_id="user123"
        )

        memory_id = memory_system.store_memory(memory)

        assert memory_id == 1
        assert memory.embedding is not None

    def test_store_company_memory(self, memory_system):
        """Test storing a company memory."""
        memory = MemoryItem(
            content="Company policy update", memory_type=MemoryType.COMPANY, user_id="user123"
        )

        memory_id = memory_system.store_memory(memory)

        assert memory_id == 1

    def test_store_memory_without_content_fails(self, memory_system):
        """Test that storing memory without content fails."""
        memory = MemoryItem(content="", memory_type=MemoryType.AGENT, agent_id="agent123")

        with pytest.raises(ValueError, match="content cannot be empty"):
            memory_system.store_memory(memory)

    def test_store_agent_memory_without_agent_id_fails(self, memory_system):
        """Test that storing agent memory without agent_id fails."""
        memory = MemoryItem(content="Test content", memory_type=MemoryType.AGENT)

        with pytest.raises(ValueError, match="agent_id required"):
            memory_system.store_memory(memory)

    def test_store_company_memory_without_user_id_fails(self, memory_system):
        """Test that storing company memory without user_id fails."""
        memory = MemoryItem(content="Test content", memory_type=MemoryType.COMPANY)

        with pytest.raises(ValueError, match="user_id required"):
            memory_system.store_memory(memory)

    def test_store_memory_sets_timestamp(self, memory_system):
        """Test that storing memory sets timestamp if not provided."""
        memory = MemoryItem(
            content="Test content", memory_type=MemoryType.AGENT, agent_id="agent123"
        )

        assert memory.timestamp is None

        memory_system.store_memory(memory)

        assert memory.timestamp is not None
        assert isinstance(memory.timestamp, datetime)


class TestMemoryRetrieval:
    """Tests for memory retrieval operations."""

    def test_retrieve_memories_basic(self, memory_system, mock_milvus_connection):
        """Test basic memory retrieval."""
        # Mock search results
        mock_hit = Mock()
        mock_hit.id = 1
        mock_hit.distance = 0.1
        mock_hit.entity = {
            "content": "Test memory",
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "metadata": {},
            "agent_id": "agent123",
        }

        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.search.return_value = [[mock_hit]]

        query = SearchQuery(query_text="test query", agent_id="agent123", top_k=5)

        results = memory_system.retrieve_memories(query)

        assert len(results) == 1
        assert results[0].content == "Test memory"
        assert results[0].agent_id == "agent123"

    def test_retrieve_memories_with_filters(self, memory_system):
        """Test memory retrieval with filters."""
        query = SearchQuery(
            query_text="user preferences",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
            top_k=10,
        )

        results = memory_system.retrieve_memories(query)

        # Should not fail even with no results
        assert isinstance(results, list)

    def test_retrieve_memories_empty_query_fails(self, memory_system):
        """Test that empty query fails."""
        query = SearchQuery(query_text="")

        with pytest.raises(ValueError, match="Query text cannot be empty"):
            memory_system.retrieve_memories(query)

    def test_retrieve_memories_ranking(self, memory_system, mock_milvus_connection):
        """Test that memories are ranked by relevance."""
        # Mock multiple search results with different timestamps
        now = datetime.utcnow()
        old_time = now - timedelta(days=30)

        mock_hit1 = Mock()
        mock_hit1.id = 1
        mock_hit1.distance = 0.2
        mock_hit1.entity = {
            "content": "Recent memory",
            "timestamp": int(now.timestamp() * 1000),
            "metadata": {},
            "agent_id": "agent123",
        }

        mock_hit2 = Mock()
        mock_hit2.id = 2
        mock_hit2.distance = 0.1
        mock_hit2.entity = {
            "content": "Old memory",
            "timestamp": int(old_time.timestamp() * 1000),
            "metadata": {},
            "agent_id": "agent123",
        }

        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.search.return_value = [[mock_hit1, mock_hit2]]

        query = SearchQuery(query_text="test query", agent_id="agent123")

        results = memory_system.retrieve_memories(query)

        assert len(results) == 2
        # Results should be ranked (recent + similar should rank higher)
        assert all(hasattr(r, "similarity_score") for r in results)


class TestMemoryClassification:
    """Tests for memory type classification."""

    def test_classify_user_context(self, memory_system):
        """Test classification of user context memories."""
        content = "I prefer dark mode and always use vim"
        memory_type = memory_system.classify_memory_type(content)

        assert memory_type == MemoryType.USER_CONTEXT

    def test_classify_task_context(self, memory_system):
        """Test classification of task context memories."""
        content = "Task completed successfully with output file generated"
        memory_type = memory_system.classify_memory_type(content)

        assert memory_type == MemoryType.TASK_CONTEXT

    def test_classify_with_explicit_context(self, memory_system):
        """Test classification with explicit context hints."""
        content = "Some generic content"
        context = {"is_user_preference": True}

        memory_type = memory_system.classify_memory_type(content, context)

        assert memory_type == MemoryType.USER_CONTEXT

    def test_classify_default_to_company(self, memory_system):
        """Test that ambiguous content defaults to company memory."""
        content = "Generic information about the project"
        memory_type = memory_system.classify_memory_type(content)

        assert memory_type == MemoryType.COMPANY


class TestMemoryDeletion:
    """Tests for memory deletion operations."""

    def test_delete_memory(self, memory_system, mock_milvus_connection):
        """Test deleting a memory."""
        result = memory_system.delete_memory(1, MemoryType.AGENT)

        assert result is True

        # Verify delete was called
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.delete.assert_called_once()

    def test_delete_memory_handles_errors(self, memory_system, mock_milvus_connection):
        """Test that delete handles errors gracefully."""
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.delete.side_effect = Exception("Delete failed")

        result = memory_system.delete_memory(1, MemoryType.AGENT)

        assert result is False


class TestMemoryArchival:
    """Tests for memory archival operations."""

    def test_archive_agent_memories(self, memory_system, mock_milvus_connection):
        """Test archiving agent memories."""
        # Mock query results
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.query.return_value = [
            {
                "id": 1,
                "agent_id": "agent123",
                "content": "Memory 1",
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
                "metadata": {},
            },
            {
                "id": 2,
                "agent_id": "agent123",
                "content": "Memory 2",
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
                "metadata": {},
            },
        ]

        result = memory_system.archive_agent_memories("agent123")

        assert result["agent_id"] == "agent123"
        assert result["count"] == 2
        assert "timestamp" in result
        assert "location" in result

    def test_archive_no_memories(self, memory_system, mock_milvus_connection):
        """Test archiving when agent has no memories."""
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.query.return_value = []

        result = memory_system.archive_agent_memories("agent123")

        assert result["count"] == 0


class TestMemorySharing:
    """Tests for memory sharing operations."""

    def test_share_memory(self, memory_system, mock_milvus_connection):
        """Test sharing a memory with users."""
        # Mock query result
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.query.return_value = [
            {
                "content": "Shared memory content",
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
                "metadata": {},
            }
        ]

        result = memory_system.share_memory(
            memory_id=1, source_type=MemoryType.AGENT, target_user_ids=["user1", "user2"]
        )

        assert result is True

    def test_share_nonexistent_memory(self, memory_system, mock_milvus_connection):
        """Test sharing a memory that doesn't exist."""
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.query.return_value = []

        result = memory_system.share_memory(
            memory_id=999, source_type=MemoryType.AGENT, target_user_ids=["user1"]
        )

        assert result is False


class TestMemoryStats:
    """Tests for memory statistics."""

    def test_get_memory_stats(self, memory_system, mock_milvus_connection):
        """Test getting memory statistics."""
        stats = memory_system.get_memory_stats()

        assert isinstance(stats, dict)
        assert "agent_memories" in stats or "company_memories" in stats


class TestEmbeddingService:
    """Tests for embedding service."""

    def test_ollama_embedding_service_initialization(self):
        """Test Ollama embedding service initialization."""
        with patch("memory_system.embedding_service.resolve_embedding_settings") as mock_settings:
            with patch("llm_providers.provider_resolver.resolve_provider") as mock_resolve_provider:
                mock_settings.return_value = {
                    "provider": "ollama",
                    "model": "nomic-embed-text",
                    "dimension": 768,
                }
                mock_resolve_provider.return_value = {
                    "base_url": "http://localhost:11434",
                    "api_key": None,
                    "timeout": 30,
                }

                service = OllamaEmbeddingService()

                assert service._base_url == "http://localhost:11434"
                assert service._model == "nomic-embed-text"
                assert service.get_embedding_dimension() == 768

    def test_generate_embedding_empty_text_fails(self):
        """Test that generating embedding for empty text fails."""
        # Mock service should handle this, but real service should fail
        with patch("memory_system.embedding_service.resolve_embedding_settings") as mock_settings:
            with patch("llm_providers.provider_resolver.resolve_provider") as mock_resolve_provider:
                mock_settings.return_value = {
                    "provider": "ollama",
                    "model": "nomic-embed-text",
                    "dimension": 768,
                }
                mock_resolve_provider.return_value = {
                    "base_url": "http://localhost:11434",
                    "api_key": None,
                    "timeout": 30,
                }

                service = OllamaEmbeddingService()

                with pytest.raises(ValueError, match="Text cannot be empty"):
                    service.generate_embedding("")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
