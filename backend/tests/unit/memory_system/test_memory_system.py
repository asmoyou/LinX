"""Tests for Memory System implementation.

This module tests the multi-tiered memory system including:
- Memory storage and retrieval (DB-first with Milvus sync)
- Semantic similarity search
- Memory type classification
- Memory sharing
- Memory archival
- Memory count limit enforcement

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 6: Memory System Design
"""

from datetime import datetime, timedelta
from typing import List
from unittest.mock import MagicMock, Mock, patch
from uuid import UUID

import pytest

from memory_system.embedding_service import OllamaEmbeddingService
from memory_system.memory_interface import (
    MemoryItem,
    MemoryType,
    SearchQuery,
)
from memory_system.memory_repository import MemoryRecordData
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


def _make_record_data(
    record_id: int = 1,
    milvus_id: int = None,
    memory_type: MemoryType = MemoryType.AGENT,
    content: str = "test content",
    agent_id: str = None,
    user_id: str = None,
    vector_status: str = "pending",
) -> MemoryRecordData:
    """Build a MemoryRecordData for tests."""
    return MemoryRecordData(
        id=record_id,
        milvus_id=milvus_id,
        memory_type=memory_type,
        content=content,
        user_id=user_id,
        agent_id=agent_id,
        task_id=None,
        metadata={},
        timestamp=datetime.utcnow(),
        vector_status=vector_status,
        vector_error=None,
        vector_updated_at=None,
    )


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
    mock_collection.insert.return_value = Mock(primary_keys=[100])
    mock_collection.search.return_value = [[]]
    mock_collection.query.return_value = []
    mock_collection.delete.return_value = None

    mock_conn.get_collection.return_value = mock_collection
    mock_conn.get_collection_stats.return_value = {"name": "test_collection", "num_entities": 0}

    return mock_conn


@pytest.fixture
def mock_repository():
    """Fixture for mock MemoryRepository."""
    repo = Mock()
    repo.create.return_value = _make_record_data(record_id=42, agent_id="agent123")
    repo.mark_vector_synced.return_value = _make_record_data(
        record_id=42, milvus_id=100, agent_id="agent123", vector_status="synced"
    )
    repo.mark_vector_failed.return_value = _make_record_data(
        record_id=42, agent_id="agent123", vector_status="failed"
    )
    repo.update_record.return_value = _make_record_data(record_id=42, agent_id="agent123")
    repo.find_recent_by_content_hash.return_value = None
    repo.get_by_milvus_id.return_value = None
    repo.clear_milvus_link.return_value = _make_record_data(record_id=42, agent_id="agent123")
    repo.evict_older_than.return_value = []
    repo.count_memories.return_value = 0
    repo.evict_oldest.return_value = []
    repo.evict_low_value.return_value = []
    return repo


@pytest.fixture
def memory_system(mock_embedding_service, mock_milvus_connection, mock_repository):
    """Fixture for Memory System with mocked dependencies."""
    with patch(
        "memory_system.memory_system.get_embedding_service", return_value=mock_embedding_service
    ):
        with patch(
            "memory_system.memory_system.get_milvus_connection",
            return_value=mock_milvus_connection,
        ):
            with patch(
                "memory_system.memory_system.get_memory_repository",
                return_value=mock_repository,
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

    def test_store_agent_memory(self, memory_system, mock_repository):
        """Test storing an agent memory returns DB id."""
        memory = MemoryItem(
            content="Agent learned something new", memory_type=MemoryType.AGENT, agent_id="agent123"
        )

        memory_id = memory_system.store_memory(memory)

        assert memory_id == 42  # DB record id, not Milvus id
        mock_repository.create.assert_called_once()

    def test_store_agent_memory_resolves_missing_user_id(self, memory_system, mock_repository):
        """Agent memory should auto-resolve user_id from owner when omitted."""
        memory = MemoryItem(
            content="Agent learned something new",
            memory_type=MemoryType.AGENT,
            agent_id=str(UUID(int=1)),
        )

        with patch.object(
            memory_system, "_resolve_agent_owner_user_id", return_value="owner-user-1"
        ) as mock_resolve:
            memory_system.store_memory(memory)

        mock_resolve.assert_called_once()
        created_item = mock_repository.create.call_args[0][0]
        assert created_item.user_id == "owner-user-1"
        assert created_item.metadata.get("user_id") == "owner-user-1"

    def test_store_agent_memory_preserves_explicit_user_id(self, memory_system, mock_repository):
        """Explicit user_id should bypass owner-resolution lookup."""
        memory = MemoryItem(
            content="Agent learned something new",
            memory_type=MemoryType.AGENT,
            agent_id="agent123",
            user_id="explicit-user-1",
        )

        with patch.object(memory_system, "_resolve_agent_owner_user_id") as mock_resolve:
            memory_system.store_memory(memory)

        mock_resolve.assert_not_called()
        created_item = mock_repository.create.call_args[0][0]
        assert created_item.user_id == "explicit-user-1"
        assert created_item.metadata.get("user_id") == "explicit-user-1"

    def test_store_memory_writes_db_first_then_milvus(
        self, memory_system, mock_repository, mock_milvus_connection
    ):
        """Test that store_memory writes to DB before Milvus."""
        call_order = []
        mock_repository.create.side_effect = lambda item: (
            call_order.append("db_create"),
            _make_record_data(record_id=42, agent_id="agent123"),
        )[1]

        mock_collection = mock_milvus_connection.get_collection.return_value
        original_insert = mock_collection.insert.return_value

        def milvus_insert_side_effect(data):
            call_order.append("milvus_insert")
            return original_insert

        mock_collection.insert.side_effect = milvus_insert_side_effect

        memory = MemoryItem(
            content="Test content", memory_type=MemoryType.AGENT, agent_id="agent123"
        )
        memory_system.store_memory(memory)

        assert call_order == ["db_create", "milvus_insert"]

    def test_store_memory_returns_db_id(self, memory_system, mock_repository):
        """Test that store_memory returns PostgreSQL record ID."""
        mock_repository.create.return_value = _make_record_data(record_id=99, agent_id="agent123")

        memory = MemoryItem(
            content="Test content", memory_type=MemoryType.AGENT, agent_id="agent123"
        )
        result = memory_system.store_memory(memory)

        assert result == 99

    def test_store_memory_marks_synced_on_success(
        self, memory_system, mock_repository, mock_milvus_connection
    ):
        """Test that successful Milvus sync marks record as synced."""
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.insert.return_value = Mock(primary_keys=[200])

        memory = MemoryItem(
            content="Test content", memory_type=MemoryType.AGENT, agent_id="agent123"
        )
        memory_system.store_memory(memory)

        mock_repository.mark_vector_synced.assert_called_once_with(42, 200)

    def test_store_memory_marks_failed_on_milvus_error(
        self, memory_system, mock_repository, mock_milvus_connection
    ):
        """Test that Milvus failure marks record as failed but DB record is preserved."""
        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.insert.side_effect = Exception("Milvus down")

        memory = MemoryItem(
            content="Test content", memory_type=MemoryType.AGENT, agent_id="agent123"
        )
        memory_id = memory_system.store_memory(memory)

        # Should still return DB id
        assert memory_id == 42
        mock_repository.create.assert_called_once()
        mock_repository.mark_vector_failed.assert_called_once()
        assert "Milvus down" in mock_repository.mark_vector_failed.call_args[0][1]

    def test_store_user_context_memory(self, memory_system, mock_repository):
        """Test storing a user context memory."""
        mock_repository.create.return_value = _make_record_data(
            record_id=50, memory_type=MemoryType.USER_CONTEXT, user_id="user123"
        )

        memory = MemoryItem(
            content="User prefers dark mode", memory_type=MemoryType.USER_CONTEXT, user_id="user123"
        )

        memory_id = memory_system.store_memory(memory)

        assert memory_id == 50

    def test_store_company_memory(self, memory_system, mock_repository):
        """Test storing a company memory."""
        mock_repository.create.return_value = _make_record_data(
            record_id=60, memory_type=MemoryType.COMPANY, user_id="user123"
        )

        memory = MemoryItem(
            content="Company policy update", memory_type=MemoryType.COMPANY, user_id="user123"
        )

        memory_id = memory_system.store_memory(memory)

        assert memory_id == 60

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

    def test_store_memory_structures_auto_generated_user_context(
        self, memory_system, mock_repository
    ):
        """Auto-generated user context should be stored as structured fact content."""
        memory = MemoryItem(
            content="User discussed: prefers dark mode\nTopic: dashboard settings",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
            metadata={"auto_generated": True, "source": "conversation"},
        )

        memory_system.store_memory(memory)

        created_item = mock_repository.create.call_args[0][0]
        assert created_item.content
        assert "=" in created_item.content
        assert created_item.metadata.get("fact_version") == "v2"
        assert created_item.metadata.get("content_hash")
        facts = created_item.metadata.get("facts")
        assert isinstance(facts, list)
        assert facts
        assert all("key" in fact and "value" in fact for fact in facts)

    def test_extract_heuristic_facts_avoids_user_profile_from_agent_result(self, memory_system):
        """Agent-result self-intro should not be misclassified as user profile."""
        memory = MemoryItem(
            content=(
                "[Agent: 小新客服]\n"
                "Task: PostgreSQL 索引怎么优化？\n"
                "Result: 您好，我是新航物联网小新，很高兴为您服务。"
            ),
            memory_type=MemoryType.AGENT,
            agent_id="agent123",
            user_id="user123",
        )

        facts = memory_system._extract_heuristic_facts(memory)
        fact_keys = [str(f.get("key") or "") for f in facts]

        assert "agent.identity.name" in fact_keys
        assert "interaction.task.latest" in fact_keys
        assert not any(key.startswith("user.profile.") for key in fact_keys)

    def test_collect_facts_filters_model_facts_by_memory_type(self, memory_system):
        """Agent memories should drop task-domain model facts."""
        memory = MemoryItem(
            content="[Agent: 小新客服]\nTask: PostgreSQL 索引怎么优化？\nResult: 这是优化说明。",
            memory_type=MemoryType.AGENT,
            agent_id="agent123",
            user_id="user123",
        )

        with patch.object(
            memory_system,
            "_extract_model_facts",
            return_value=[
                {
                    "key": "topic.domain",
                    "value": "数据库索引优化",
                    "category": "domain",
                    "importance": 1.0,
                    "confidence": 1.0,
                },
                {
                    "key": "interaction.task.latest",
                    "value": "PostgreSQL 索引怎么优化？",
                    "category": "task",
                    "importance": 0.8,
                    "confidence": 0.9,
                },
                {
                    "key": "agent.name",
                    "value": "小新客服",
                    "category": "agent",
                    "importance": 0.7,
                    "confidence": 0.9,
                },
            ],
        ):
            facts, _ = memory_system._collect_facts(memory)

        fact_keys = [str(f.get("key") or "") for f in facts]
        assert "topic.domain" not in fact_keys
        assert "agent.name" not in fact_keys
        assert all(key.startswith("agent.") or key.startswith("interaction.") for key in fact_keys)

    def test_collect_facts_prefers_model_only_for_user_context_when_model_enabled(
        self, memory_system
    ):
        """When model extraction is enabled, user_context should prefer model facts over heuristics."""
        memory = MemoryItem(
            content="我喜欢黄焖鸡",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
        )
        memory_system._fact_extraction_enabled = True
        memory_system._fact_extraction_model_enabled = True
        memory_system._fact_extraction_provider = "ollama"

        with patch.object(
            memory_system,
            "_extract_heuristic_facts",
            return_value=[
                {
                    "key": "user.topic.latest",
                    "value": "喜欢黄焖鸡",
                    "category": "user_context",
                    "importance": 0.4,
                    "confidence": 0.7,
                    "source": "heuristic",
                }
            ],
        ), patch.object(
            memory_system,
            "_extract_model_facts",
            return_value=[
                {
                    "key": "user.preference.food",
                    "value": "黄焖鸡",
                    "category": "user_preference",
                    "importance": 0.92,
                    "confidence": 0.91,
                    "source": "model",
                }
            ],
        ):
            facts, _ = memory_system._collect_facts(memory)

        fact_keys = [str(f.get("key") or "") for f in facts]
        assert "user.preference.food" in fact_keys
        assert "user.topic.latest" not in fact_keys

    def test_collect_facts_skips_fallback_for_user_context_when_model_mode_empty(self, memory_system):
        """Model-first user_context extraction should not fabricate fallback facts when model returns none."""
        memory = MemoryItem(
            content="这轮只是确认一下",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
        )
        memory_system._fact_extraction_enabled = True
        memory_system._fact_extraction_model_enabled = True
        memory_system._fact_extraction_provider = "ollama"

        with patch.object(memory_system, "_extract_heuristic_facts", return_value=[]), patch.object(
            memory_system,
            "_extract_model_facts",
            return_value=[],
        ):
            facts, _ = memory_system._collect_facts(memory)

        assert facts == []

    def test_collect_facts_skips_secondary_extraction_for_session_pre_extracted(self, memory_system):
        """Session pre-extracted memories should reuse seed facts without secondary extraction."""
        memory = MemoryItem(
            content="user.preference.food_preference_like=黄焖鸡",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
            metadata={
                "signal_type": "user_preference",
                "skip_secondary_fact_extraction": True,
                "facts": [
                    {
                        "key": "user.preference.food_preference_like",
                        "value": "黄焖鸡",
                        "category": "user_preference",
                        "importance": 0.9,
                        "confidence": 0.92,
                        "source": "session_llm",
                    }
                ],
            },
        )

        with patch.object(memory_system, "_extract_heuristic_facts") as heuristic_mock, patch.object(
            memory_system, "_extract_model_facts"
        ) as model_mock:
            facts, _ = memory_system._collect_facts(memory)

        assert len(facts) == 1
        assert facts[0]["key"] == "user.preference.food_preference_like"
        heuristic_mock.assert_not_called()
        model_mock.assert_not_called()

    def test_fact_grounding_rejects_unsupported_user_inference(self, memory_system):
        """Grounding helper should reject inferred values absent from source text."""
        content = "User discussed: 我在学摄影，最近主要拍夜景，想提升构图。"

        assert memory_system._is_fact_value_grounded_in_content(content, "摄影")
        assert not memory_system._is_fact_value_grounded_in_content(
            content,
            "每周参加摄影课程",
        )

    def test_store_memory_merges_exact_duplicate_instead_of_insert(
        self, memory_system, mock_repository
    ):
        """Exact duplicate should refresh existing memory instead of creating a new row."""
        existing = _make_record_data(
            record_id=7,
            milvus_id=101,
            memory_type=MemoryType.AGENT,
            content="interaction.task.latest = summarize q4 report",
            agent_id="agent123",
            user_id="user123",
            vector_status="synced",
        )
        existing.metadata = {
            "content_hash": "same-hash",
            "facts": [
                {
                    "key": "interaction.task.latest",
                    "value": "summarize q4 report",
                    "category": "task",
                    "importance": 0.6,
                    "confidence": 0.8,
                    "source": "heuristic",
                }
            ],
            "fact_keys": ["interaction.task.latest"],
            "importance_score": 0.6,
            "mention_count": 1,
            "memory_tier": "core",
        }
        mock_repository.find_recent_by_content_hash.return_value = existing
        mock_repository.update_record.return_value = existing

        memory = MemoryItem(
            content="Task: Summarize Q4 report\nResult: Completed summary",
            memory_type=MemoryType.AGENT,
            agent_id="agent123",
            user_id="user123",
        )

        result_id = memory_system.store_memory(memory)

        assert result_id == 7
        mock_repository.create.assert_not_called()
        mock_repository.update_record.assert_called()


class TestMemoryLimits:
    """Tests for memory count limit enforcement."""

    def test_store_memory_enforces_agent_limit(self, memory_system, mock_repository):
        """Test that agent memory limit triggers eviction."""
        mock_repository.count_memories.return_value = 10000  # At limit

        evicted_record = _make_record_data(record_id=1, milvus_id=50, agent_id="agent123")
        mock_repository.evict_low_value.return_value = [evicted_record]

        memory = MemoryItem(
            content="New agent memory", memory_type=MemoryType.AGENT, agent_id="agent123"
        )
        memory_system.store_memory(memory)

        mock_repository.evict_low_value.assert_called_once()
        call_kwargs = mock_repository.evict_low_value.call_args.kwargs
        assert call_kwargs["memory_type"] == MemoryType.AGENT
        assert call_kwargs["agent_id"] == "agent123"
        assert call_kwargs["count"] == 1

    def test_store_memory_enforces_user_context_limit(self, memory_system, mock_repository):
        """Test that user context memory limit triggers eviction."""
        mock_repository.count_memories.return_value = 5000  # At limit

        evicted_record = _make_record_data(
            record_id=2, milvus_id=51, memory_type=MemoryType.USER_CONTEXT, user_id="user123"
        )
        mock_repository.evict_low_value.return_value = [evicted_record]
        mock_repository.create.return_value = _make_record_data(
            record_id=60, memory_type=MemoryType.USER_CONTEXT, user_id="user123"
        )

        memory = MemoryItem(
            content="New user context", memory_type=MemoryType.USER_CONTEXT, user_id="user123"
        )
        memory_system.store_memory(memory)

        mock_repository.evict_low_value.assert_called_once()
        call_kwargs = mock_repository.evict_low_value.call_args.kwargs
        assert call_kwargs["memory_type"] == MemoryType.USER_CONTEXT
        assert call_kwargs["user_id"] == "user123"

    def test_no_eviction_below_limit(self, memory_system, mock_repository):
        """Test that no eviction happens when below limit."""
        mock_repository.count_memories.return_value = 100  # Well below limit

        memory = MemoryItem(
            content="New agent memory", memory_type=MemoryType.AGENT, agent_id="agent123"
        )
        memory_system.store_memory(memory)

        mock_repository.evict_low_value.assert_not_called()


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

    def test_rank_results_boosts_core_high_importance(self, memory_system):
        """Core + high-importance memories should rank above archival peers."""
        now = datetime.utcnow()
        low = MemoryItem(
            content="archival memory",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
            timestamp=now,
            metadata={"importance_score": 0.1, "memory_tier": "archival", "mention_count": 1},
            similarity_score=0.7,
        )
        high = MemoryItem(
            content="core memory",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user123",
            timestamp=now,
            metadata={"importance_score": 0.95, "memory_tier": "core", "mention_count": 6},
            similarity_score=0.7,
        )

        ranked = memory_system._rank_results([low, high])
        assert ranked[0].content == "core memory"

    def test_retrieve_memories_respects_explicit_zero_min_similarity(
        self, memory_system, mock_milvus_connection
    ):
        """Explicit `min_similarity=0` should bypass default threshold filtering."""
        mock_hit = Mock()
        mock_hit.id = 1
        mock_hit.distance = 200.0  # Low normalized similarity for L2 metric
        mock_hit.entity = {
            "content": "Low similarity memory",
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
            "metadata": {},
            "agent_id": "agent123",
        }

        mock_collection = mock_milvus_connection.get_collection.return_value
        mock_collection.search.return_value = [[mock_hit]]

        default_results = memory_system.retrieve_memories(
            SearchQuery(query_text="test query", agent_id="agent123")
        )
        zero_threshold_results = memory_system.retrieve_memories(
            SearchQuery(query_text="test query", agent_id="agent123", min_similarity=0.0)
        )

        assert default_results == []
        assert len(zero_threshold_results) == 1


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
