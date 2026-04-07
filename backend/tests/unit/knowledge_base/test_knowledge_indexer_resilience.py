"""Unit tests for Milvus resilience behaviors in KnowledgeIndexer."""

from unittest.mock import Mock, call, patch

import pytest
from pymilvus import MilvusException

from knowledge_base.knowledge_indexer import KnowledgeIndexer


def _build_indexer() -> KnowledgeIndexer:
    """Create a lightweight KnowledgeIndexer instance with mocked dependencies."""
    indexer = KnowledgeIndexer.__new__(KnowledgeIndexer)
    indexer.embedding_service = Mock()
    indexer.milvus_conn = Mock()
    indexer.collection_name = "knowledge_embeddings"
    indexer._milvus_flush_timeout_seconds = 3.0
    indexer._milvus_retry_backoff_seconds = 0.0
    indexer._milvus_max_retries = 2
    indexer._milvus_allow_flush_degrade = True
    indexer._store_chunks_in_postgres = Mock()
    return indexer


def test_index_chunks_retries_flush_when_channel_not_found():
    """Channel-not-found errors should reconnect and retry without duplicate inserts."""
    indexer = _build_indexer()
    indexer.embedding_service.generate_embeddings_batch.return_value = [[0.1, 0.2, 0.3]]

    first_collection = Mock()
    second_collection = Mock()
    first_collection.flush.side_effect = MilvusException(code=500, message="channel not found")
    indexer.milvus_conn.get_collection.side_effect = [first_collection, second_collection]

    with patch("knowledge_base.knowledge_indexer.time.sleep", return_value=None):
        result = KnowledgeIndexer.index_chunks(
            indexer,
            document_id="1fdb519c-9ac8-4c9a-a945-812b82213ae7",
            chunks=["test chunk"],
            chunk_metadata=[{"chunk_index": 0}],
            user_id="user-1",
        )

    assert result.chunks_indexed == 1
    assert result.embeddings_generated == 1
    assert indexer.milvus_conn.get_collection.call_args_list == [
        call("knowledge_embeddings", force_refresh=False),
        call("knowledge_embeddings", force_refresh=True),
    ]
    first_collection.insert.assert_called_once()
    second_collection.insert.assert_not_called()
    second_collection.flush.assert_called_once_with(timeout=3.0)
    indexer.milvus_conn.reconnect.assert_called_once()
    indexer._store_chunks_in_postgres.assert_called_once()


def test_index_chunks_does_not_retry_non_retryable_milvus_error():
    """Non-transient Milvus errors should fail fast and skip PostgreSQL writes."""
    indexer = _build_indexer()
    indexer.embedding_service.generate_embeddings_batch.return_value = [[0.1, 0.2, 0.3]]

    collection = Mock()
    collection.insert.side_effect = MilvusException(code=500, message="field schema mismatch")
    indexer.milvus_conn.get_collection.return_value = collection

    with pytest.raises(MilvusException):
        KnowledgeIndexer.index_chunks(
            indexer,
            document_id="1fdb519c-9ac8-4c9a-a945-812b82213ae7",
            chunks=["test chunk"],
            chunk_metadata=[{"chunk_index": 0}],
            user_id="user-1",
        )

    indexer.milvus_conn.get_collection.assert_called_once_with(
        "knowledge_embeddings",
        force_refresh=False,
    )
    indexer.milvus_conn.reconnect.assert_not_called()
    collection.flush.assert_not_called()
    indexer._store_chunks_in_postgres.assert_not_called()


def test_index_chunks_degrades_when_flush_keeps_failing_after_retries():
    """When insert succeeds but flush keeps failing, indexing should continue in degrade mode."""
    indexer = _build_indexer()
    indexer.embedding_service.generate_embeddings_batch.return_value = [[0.1, 0.2, 0.3]]

    first_collection = Mock()
    second_collection = Mock()
    third_collection = Mock()
    flush_error = MilvusException(code=500, message="channel not found")
    first_collection.flush.side_effect = flush_error
    second_collection.flush.side_effect = flush_error
    third_collection.flush.side_effect = flush_error
    indexer.milvus_conn.get_collection.side_effect = [
        first_collection,
        second_collection,
        third_collection,
    ]

    with patch("knowledge_base.knowledge_indexer.time.sleep", return_value=None):
        result = KnowledgeIndexer.index_chunks(
            indexer,
            document_id="1fdb519c-9ac8-4c9a-a945-812b82213ae7",
            chunks=["test chunk"],
            chunk_metadata=[{"chunk_index": 0}],
            user_id="user-1",
        )

    assert result.chunks_indexed == 1
    assert indexer.milvus_conn.get_collection.call_args_list == [
        call("knowledge_embeddings", force_refresh=False),
        call("knowledge_embeddings", force_refresh=True),
        call("knowledge_embeddings", force_refresh=True),
    ]
    first_collection.insert.assert_called_once()
    second_collection.insert.assert_not_called()
    third_collection.insert.assert_not_called()
    indexer.milvus_conn.reconnect.assert_called()
    assert indexer.milvus_conn.reconnect.call_count == 2
    indexer._store_chunks_in_postgres.assert_called_once()


def test_index_chunks_normalizes_multimodal_text_before_embedding_and_storage():
    """Indexing should sanitize noisy multimodal chunk text before persistence."""
    indexer = _build_indexer()
    indexer.embedding_service.generate_embeddings_batch.return_value = [[0.1, 0.2, 0.3]]

    collection = Mock()
    indexer.milvus_conn.get_collection.return_value = collection

    raw_chunk = (
        "Audio Transcript:\n<|nospeech|>欢迎来到卡丁车赛道。\n\n"
        "Visual Analysis:\nVideo Summary:\n### 摘要\n"
        "**1) 整体剧情** 卡丁车高速过弯。\n"
    )

    KnowledgeIndexer.index_chunks(
        indexer,
        document_id="1fdb519c-9ac8-4c9a-a945-812b82213ae7",
        chunks=[raw_chunk],
        chunk_metadata=[{"chunk_index": 0, "summary": "### 摘要\n**卡丁车高速过弯。**"}],
        user_id="user-1",
    )

    embedding_input = indexer.embedding_service.generate_embeddings_batch.call_args.args[0][0]
    assert "<|" not in embedding_input
    assert "Audio Transcript:" not in embedding_input
    assert "卡丁车赛道" in embedding_input

    stored_chunks = indexer._store_chunks_in_postgres.call_args.kwargs["chunks"]
    assert "<|" not in stored_chunks[0]
    assert "Visual Analysis:" not in stored_chunks[0]

    stored_meta = indexer._store_chunks_in_postgres.call_args.kwargs["chunk_metadata"][0]
    assert stored_meta["summary"] == "摘要\n卡丁车高速过弯。"


def test_index_chunks_bootstraps_collection_when_missing():
    """Missing knowledge collection should be created before indexing."""
    indexer = _build_indexer()
    indexer.embedding_service.generate_embeddings_batch.return_value = [[0.1, 0.2, 0.3]]
    indexer.milvus_conn.collection_exists.return_value = False

    collection = Mock()
    indexer.milvus_conn.get_collection.return_value = collection

    with patch(
        "knowledge_base.knowledge_indexer.ensure_knowledge_embeddings_collection",
        return_value=collection,
    ) as ensure_collection:
        result = KnowledgeIndexer.index_chunks(
            indexer,
            document_id="1fdb519c-9ac8-4c9a-a945-812b82213ae7",
            chunks=["test chunk"],
            chunk_metadata=[{"chunk_index": 0}],
            user_id="user-1",
        )

    assert result.chunks_indexed == 1
    ensure_collection.assert_called_once_with()
    indexer.milvus_conn.get_collection.assert_called_once_with(
        "knowledge_embeddings",
        force_refresh=False,
    )
    collection.insert.assert_called_once()
    collection.flush.assert_called_once_with(timeout=3.0)
