"""Tests for the shared memory retrieval gateway."""

from datetime import datetime
from unittest.mock import Mock, patch

from memory_system.memory_interface import MemoryItem, MemoryType, SearchQuery
from memory_system.memory_repository import MemoryRecordData
from memory_system.retrieval_gateway import MemoryRetrievalGateway


def test_retrieval_gateway_maps_semantic_hits_to_db_records():
    gateway = MemoryRetrievalGateway()
    user_id = "test-user-id"

    semantic_item = MemoryItem(
        id=101,
        content="legacy vector content",
        memory_type=MemoryType.COMPANY,
        user_id=user_id,
        similarity_score=0.83,
        metadata={"_rerank_score": 0.91, "plain": "ignored"},
    )
    mapped_item = MemoryItem(
        id=7,
        content="mapped db content",
        memory_type=MemoryType.COMPANY,
        user_id=user_id,
        metadata={"source": "db"},
    )
    mapped_row = Mock()
    mapped_row.user_id = user_id
    mapped_row.to_memory_item.return_value = mapped_item

    memory_system = Mock()
    memory_system.retrieve_memories.return_value = [semantic_item]
    memory_system._default_similarity_threshold = 0.3

    repository = Mock()
    repository.get_by_milvus_ids.return_value = {101: mapped_row}

    results = gateway.retrieve_memories(
        search_query=SearchQuery(
            query_text="mapped db content",
            memory_type=MemoryType.COMPANY,
            user_id=user_id,
            top_k=5,
        ),
        memory_system=memory_system,
        repository=repository,
        strict_keyword_fallback=True,
        log_label="Test memory",
    )

    assert len(results) == 1
    assert results[0].content == "mapped db content"
    assert results[0].metadata["source"] == "db"
    assert results[0].metadata["_rerank_score"] == 0.91
    assert "plain" not in results[0].metadata
    repository.search_keywords.assert_not_called()


def test_retrieval_gateway_keyword_fallback_respects_similarity_threshold():
    gateway = MemoryRetrievalGateway()

    memory_system = Mock()
    memory_system.retrieve_memories.return_value = []
    memory_system._default_similarity_threshold = 0.4

    repository = Mock()
    repository.get_by_milvus_ids.return_value = {}
    repository.search_keywords.return_value = [
        (
            MemoryRecordData(
                id=9,
                milvus_id=9001,
                memory_type=MemoryType.COMPANY,
                content="LinX是小白客开发的",
                user_id="test-user-id",
                agent_id=None,
                task_id=None,
                owner_user_id="test-user-id",
                owner_agent_id=None,
                department_id=None,
                visibility="department_tree",
                sensitivity="internal",
                source_memory_id=None,
                expires_at=None,
                metadata={},
                timestamp=datetime(2026, 1, 15, 12, 0, 0),
                vector_status="synced",
                vector_error=None,
                vector_updated_at=None,
            ),
            2.6,
            2,
        )
    ]

    results = gateway.retrieve_memories(
        search_query=SearchQuery(
            query_text="LinX是谁开发的",
            memory_type=MemoryType.COMPANY,
            top_k=5,
            min_similarity=None,
        ),
        memory_system=memory_system,
        repository=repository,
        strict_keyword_fallback=True,
        cjk_ngram_sizes=(2, 3),
        log_label="Test memory",
    )

    assert results == []
    assert repository.search_keywords.call_args.kwargs["strict_semantics"] is True


def test_retrieval_gateway_materializations_are_marked_read_only():
    gateway = MemoryRetrievalGateway()
    materialized_item = MemoryItem(
        id=301,
        content="user.preference.response_style=concise",
        memory_type=MemoryType.USER_CONTEXT,
        user_id="test-user-id",
        similarity_score=0.84,
        metadata={"materialization_type": "user_profile"},
    )
    service = Mock()
    service.retrieve_user_profile.return_value = [materialized_item]

    with patch(
        "memory_system.retrieval_gateway.get_materialization_retrieval_service",
        return_value=service,
    ):
        results = gateway.retrieve_materializations(
            materialization_type="user_profile",
            owner_id="test-user-id",
            query_text="answer concisely",
            top_k=5,
        )

    assert len(results) == 1
    assert results[0].metadata["read_only"] is True
    assert results[0].metadata["source_table"] == "memory_materializations"
    service.retrieve_user_profile.assert_called_once()


def test_retrieval_gateway_entries_are_marked_read_only():
    gateway = MemoryRetrievalGateway()
    entry_item = MemoryItem(
        id=302,
        content="user.preference.response_style=concise",
        memory_type=MemoryType.USER_CONTEXT,
        user_id="test-user-id",
        similarity_score=0.83,
        metadata={"entry_type": "user_fact", "entry_key": "response_style"},
    )
    service = Mock()
    service.retrieve_user_facts.return_value = [entry_item]

    with patch(
        "memory_system.retrieval_gateway.get_memory_entry_retrieval_service",
        return_value=service,
    ):
        results = gateway.retrieve_entries(
            entry_type="user_fact",
            owner_id="test-user-id",
            query_text="answer concisely",
            top_k=5,
        )

    assert len(results) == 1
    assert results[0].metadata["read_only"] is True
    assert results[0].metadata["source_table"] == "memory_entries"
    service.retrieve_user_facts.assert_called_once()


def test_retrieval_gateway_agent_scope_merges_legacy_and_materialized_results():
    gateway = MemoryRetrievalGateway()
    memory_system = Mock()
    memory_system.retrieve_memories.return_value = []
    memory_system._default_similarity_threshold = 0.3

    repository = Mock()
    repository.get_by_milvus_ids.return_value = {}
    repository.search_keywords.return_value = []

    materialization_service = Mock()
    materialization_service.retrieve_agent_experience.return_value = [
        MemoryItem(
            id=401,
            content="agent.experience.goal=Stable PDF delivery path",
            memory_type=MemoryType.AGENT,
            agent_id="agent-123",
            similarity_score=0.88,
            metadata={
                "materialization_type": "agent_experience",
                "materialization_key": "pdf_delivery",
            },
        )
    ]
    entry_service = Mock()
    entry_service.retrieve_agent_skill_candidates.return_value = [
        MemoryItem(
            id=402,
            content="agent.experience.goal=Stable PDF delivery path",
            memory_type=MemoryType.AGENT,
            agent_id="agent-123",
            similarity_score=0.84,
            metadata={
                "entry_type": "agent_skill_candidate",
                "entry_key": "pdf_delivery",
            },
        )
    ]

    with patch(
        "memory_system.retrieval_gateway.get_materialization_retrieval_service",
        return_value=materialization_service,
    ):
        with patch(
            "memory_system.retrieval_gateway.get_memory_entry_retrieval_service",
            return_value=entry_service,
        ):
            results = gateway.retrieve_agent_scope(
                memory_system=memory_system,
                repository=repository,
                agent_id="agent-123",
                user_id="user-123",
                query_text="reliable pdf delivery",
                top_k=3,
                min_similarity=0.5,
            )

    assert len(results) == 1
    assert results[0].metadata["entry_type"] == "agent_skill_candidate"
    called_query = memory_system.retrieve_memories.call_args.args[0]
    assert called_query.user_id == "user-123"
    assert called_query.agent_id == "agent-123"


def test_retrieval_gateway_user_scope_merges_materializations_and_entries():
    gateway = MemoryRetrievalGateway()
    memory_system = Mock()
    memory_system.retrieve_memories.return_value = []
    memory_system._default_similarity_threshold = 0.3

    repository = Mock()
    repository.get_by_milvus_ids.return_value = {}
    repository.search_keywords.return_value = []

    materialization_service = Mock()
    materialization_service.retrieve_user_profile.return_value = [
        MemoryItem(
            id=501,
            content="user.preference.response_style=concise",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user-123",
            similarity_score=0.88,
            metadata={
                "materialization_type": "user_profile",
                "materialization_key": "response_style",
            },
        )
    ]
    entry_service = Mock()
    entry_service.retrieve_user_facts.return_value = [
        MemoryItem(
            id=502,
            content="user.preference.response_style=concise",
            memory_type=MemoryType.USER_CONTEXT,
            user_id="user-123",
            similarity_score=0.83,
            metadata={"entry_type": "user_fact", "entry_key": "response_style"},
        )
    ]

    with patch(
        "memory_system.retrieval_gateway.get_materialization_retrieval_service",
        return_value=materialization_service,
    ):
        with patch(
            "memory_system.retrieval_gateway.get_memory_entry_retrieval_service",
            return_value=entry_service,
        ):
            results = gateway.retrieve_user_context_scope(
                memory_system=memory_system,
                repository=repository,
                user_id="user-123",
                query_text="answer concisely",
                top_k=5,
                min_similarity=0.5,
            )

    assert len(results) == 1
    assert results[0].metadata["entry_type"] == "user_fact"


def test_retrieval_gateway_owned_agent_scope_merges_entries_before_materializations():
    gateway = MemoryRetrievalGateway()
    memory_system = Mock()
    memory_system.retrieve_memories.return_value = []
    memory_system._default_similarity_threshold = 0.3

    repository = Mock()
    repository.get_by_milvus_ids.return_value = {}
    repository.search_keywords.return_value = []

    materialization_service = Mock()
    materialization_service.retrieve_agent_experience.side_effect = [
        [
            MemoryItem(
                id=601,
                content="agent.experience.goal=Stable PDF delivery path",
                memory_type=MemoryType.AGENT,
                agent_id="agent-1",
                similarity_score=0.88,
                metadata={
                    "materialization_type": "agent_experience",
                    "materialization_key": "pdf_delivery",
                },
            )
        ],
        [],
    ]
    entry_service = Mock()
    entry_service.retrieve_agent_skill_candidates.side_effect = [
        [
            MemoryItem(
                id=602,
                content="agent.experience.goal=Stable PDF delivery path",
                memory_type=MemoryType.AGENT,
                agent_id="agent-1",
                similarity_score=0.84,
                metadata={
                    "entry_type": "agent_skill_candidate",
                    "entry_key": "pdf_delivery",
                },
            )
        ],
        [],
    ]

    with patch(
        "memory_system.retrieval_gateway.get_materialization_retrieval_service",
        return_value=materialization_service,
    ):
        with patch(
            "memory_system.retrieval_gateway.get_memory_entry_retrieval_service",
            return_value=entry_service,
        ):
            results = gateway.retrieve_owned_agent_scope(
                memory_system=memory_system,
                repository=repository,
                owner_ids=["agent-1", "agent-2"],
                user_id="user-123",
                query_text="reliable pdf delivery",
                top_k=3,
                min_similarity=0.5,
            )

    assert len(results) == 1
    assert results[0].metadata["entry_type"] == "agent_skill_candidate"
    called_query = memory_system.retrieve_memories.call_args.args[0]
    assert called_query.user_id == "user-123"
    assert called_query.agent_id is None


def test_retrieval_gateway_list_scope_memories_merges_owned_agent_materializations():
    gateway = MemoryRetrievalGateway()
    legacy_row = MemoryRecordData(
        id=10,
        milvus_id=1010,
        memory_type=MemoryType.AGENT,
        content="legacy agent memory",
        user_id="user-123",
        agent_id="agent-1",
        task_id=None,
        owner_user_id="user-123",
        owner_agent_id="agent-1",
        department_id=None,
        visibility="private",
        sensitivity="internal",
        source_memory_id=None,
        expires_at=None,
        metadata={"signal_type": "agent_memory_candidate"},
        timestamp=datetime(2026, 3, 10, 12, 0, 0),
        vector_status="synced",
        vector_error=None,
        vector_updated_at=None,
    )
    repository = Mock()
    repository.list_memories.return_value = [legacy_row]

    agent_one_materialized = MemoryItem(
        id=501,
        content="agent.experience.goal=Stable PDF delivery path",
        memory_type=MemoryType.AGENT,
        agent_id="agent-1",
        similarity_score=0.85,
        metadata={
            "materialization_type": "agent_experience",
            "materialization_key": "pdf_delivery",
        },
    )
    agent_two_materialized = MemoryItem(
        id=502,
        content="agent.experience.goal=Calendar booking path",
        memory_type=MemoryType.AGENT,
        agent_id="agent-2",
        similarity_score=0.82,
        metadata={
            "materialization_type": "agent_experience",
            "materialization_key": "calendar_booking",
        },
    )
    agent_two_entry = MemoryItem(
        id=503,
        content="agent.experience.goal=Calendar booking path",
        memory_type=MemoryType.AGENT,
        agent_id="agent-2",
        similarity_score=0.8,
        metadata={
            "entry_type": "agent_skill_candidate",
            "entry_key": "calendar_booking",
        },
    )

    with patch.object(
        gateway,
        "retrieve_materializations",
        side_effect=[[agent_one_materialized], [agent_two_materialized]],
    ) as mock_materializations:
        with patch.object(
            gateway,
            "retrieve_entries",
            side_effect=[[], [agent_two_entry]],
        ) as mock_entries:
            results = gateway.list_scope_memories(
                search_query=SearchQuery(
                    query_text="*",
                    memory_type=MemoryType.AGENT,
                    user_id="user-123",
                    top_k=None,
                ),
                repository=repository,
                agent_materialization_owner_ids=["agent-1", "agent-2"],
            )

    assert len(results) == 3
    assert {item.content for item in results} == {
        "legacy agent memory",
        "agent.experience.goal=Stable PDF delivery path",
        "agent.experience.goal=Calendar booking path",
    }
    calendar_item = next(
        item for item in results if item.content == "agent.experience.goal=Calendar booking path"
    )
    assert calendar_item.metadata["entry_type"] == "agent_skill_candidate"
    assert mock_materializations.call_count == 2
    assert mock_entries.call_count == 2
    first_call = mock_materializations.call_args_list[0].kwargs
    second_call = mock_materializations.call_args_list[1].kwargs
    assert first_call["owner_id"] == "agent-1"
    assert second_call["owner_id"] == "agent-2"
