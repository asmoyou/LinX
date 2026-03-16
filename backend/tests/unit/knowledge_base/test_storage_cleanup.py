from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from knowledge_base.storage_cleanup import (
    KnowledgeStorageCleanupSettings,
    cleanup_knowledge_item_storage,
    load_knowledge_storage_cleanup_settings,
    run_knowledge_storage_cleanup_once,
)


class _ConfigStub:
    def __init__(self, section):
        self._section = section

    def get(self, key, default=None):
        if key == "knowledge_base.cleanup":
            return self._section
        return default


def test_load_knowledge_storage_cleanup_settings_uses_defaults():
    settings = load_knowledge_storage_cleanup_settings(_ConfigStub({"enabled": True}))

    assert settings.enabled is True
    assert settings.batch_size == 500
    assert settings.compact_on_cycle is True
    assert settings.purge_minio_versions is True


@patch("knowledge_base.storage_cleanup.request_document_cancellation")
@patch("knowledge_base.processing_queue.get_processing_queue")
@patch("memory_system.milvus_connection.get_milvus_connection")
@patch("object_storage.minio_client.get_minio_client")
def test_cleanup_knowledge_item_storage_removes_vectors_and_all_object_refs(
    mock_get_minio_client,
    mock_get_milvus_connection,
    mock_get_processing_queue,
    mock_request_document_cancellation,
):
    fake_minio = Mock()
    fake_minio.parse_object_reference.side_effect = lambda ref: tuple(ref.split(":", 2)[1:])
    fake_minio.delete_file_versions.side_effect = [2, 1]
    mock_get_minio_client.return_value = fake_minio

    fake_collection = Mock()
    fake_milvus = Mock()
    fake_milvus.collection_exists.return_value = True
    fake_milvus.get_collection.return_value = fake_collection
    mock_get_milvus_connection.return_value = fake_milvus

    fake_queue = Mock()
    fake_queue.request_cancel.return_value = True
    mock_get_processing_queue.return_value = fake_queue

    item = SimpleNamespace(
        knowledge_id="kid-1",
        file_reference="minio:documents:user-1/doc.txt",
        item_metadata={
            "thumbnail_reference": "minio:images:user-1/doc_thumb.jpg",
            "job_id": "job-1",
        },
    )

    result = cleanup_knowledge_item_storage(item)

    mock_request_document_cancellation.assert_called_once_with("kid-1")
    fake_queue.request_cancel.assert_called_once_with(
        "job-1", error_message="Processing cancelled by user."
    )
    fake_collection.delete.assert_called_once_with('knowledge_id == "kid-1"')
    assert fake_minio.delete_file_versions.call_args_list == [
        call("documents", "user-1/doc.txt"),
        call("images", "user-1/doc_thumb.jpg"),
    ]
    assert result["minio"]["deleted_objects"] == 2
    assert result["minio"]["deleted_versions"] == 3
    assert result["vectors"]["deleted"] is True


@patch("knowledge_base.storage_cleanup.trigger_knowledge_collection_compaction")
@patch("knowledge_base.storage_cleanup.cleanup_orphaned_knowledge_objects")
@patch("knowledge_base.storage_cleanup.cleanup_orphaned_knowledge_vectors")
@patch("knowledge_base.storage_cleanup._load_live_knowledge_ids")
def test_run_knowledge_storage_cleanup_once_returns_combined_summary(
    mock_load_live_ids,
    mock_cleanup_vectors,
    mock_cleanup_objects,
    mock_compaction,
):
    mock_load_live_ids.return_value = {"kid-1"}
    mock_cleanup_vectors.return_value = {
        "scanned_rows": 10,
        "orphaned_knowledge_ids": 2,
        "deleted_knowledge_ids": 2,
        "errors": [],
    }
    mock_cleanup_objects.return_value = {
        "scanned_tagged_versions": 8,
        "orphaned_objects": 1,
        "deleted_objects": 1,
        "deleted_versions": 3,
        "errors": [],
    }
    mock_compaction.return_value = {"attempted": True, "triggered": True, "error": None}

    result = run_knowledge_storage_cleanup_once(
        KnowledgeStorageCleanupSettings(
            enabled=True,
            use_advisory_lock=False,
        ),
        reason="scheduled",
    )

    assert result["status"] == "ok"
    assert result["cleanup"]["live_knowledge_ids"] == 1
    assert result["cleanup"]["vector_cleanup"]["deleted_knowledge_ids"] == 2
    assert result["cleanup"]["object_cleanup"]["deleted_objects"] == 1
    assert result["cleanup"]["compaction"]["triggered"] is True
