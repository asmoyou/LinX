"""Unit tests for Milvus orphan vector cleanup utilities."""

from unittest.mock import Mock, patch

from memory_system.orphan_vector_cleanup import (
    OrphanCleanupSettings,
    load_orphan_cleanup_settings,
    run_orphan_cleanup_once,
    scan_orphan_vectors,
)


class _ConfigStub:
    def __init__(self, cleanup_section):
        self._cleanup_section = cleanup_section

    def get(self, key, default=None):
        if key == "memory.cleanup_orphans":
            return self._cleanup_section
        return default


def test_load_orphan_cleanup_settings_uses_defaults_for_missing_fields():
    settings = load_orphan_cleanup_settings(_ConfigStub({"enabled": True}))

    assert settings.enabled is True
    assert settings.run_on_startup is True
    assert settings.interval_seconds == 21600
    assert settings.batch_size == 1000
    assert settings.collections == ["agent_memories", "company_memories"]


@patch("memory_system.orphan_vector_cleanup.get_milvus_connection")
@patch("memory_system.orphan_vector_cleanup.get_memory_repository")
def test_scan_orphan_vectors_dry_run_reports_orphans_without_delete(mock_get_repo, mock_get_milvus):
    iterator = Mock()
    iterator.next.side_effect = [[{"id": 1}, {"id": 2}, {"id": 3}], []]

    collection = Mock()
    collection.query_iterator.return_value = iterator

    mock_get_milvus.return_value.get_collection.return_value = collection
    mock_get_repo.return_value.get_by_milvus_ids.return_value = {1: Mock(), 3: Mock()}

    result = scan_orphan_vectors("company_memories", batch_size=1000, dry_run=True)

    assert result["orphan_count"] == 1
    assert result["deleted"] == 0
    assert result["orphan_ids"] == [2]
    collection.delete.assert_not_called()
    iterator.close.assert_called_once()


@patch("memory_system.orphan_vector_cleanup.get_milvus_connection")
@patch("memory_system.orphan_vector_cleanup.get_memory_repository")
def test_scan_orphan_vectors_enforces_delete_cap(mock_get_repo, mock_get_milvus):
    iterator = Mock()
    iterator.next.side_effect = [[{"id": 10}, {"id": 11}, {"id": 12}, {"id": 13}], []]

    collection = Mock()
    collection.query_iterator.return_value = iterator

    mock_get_milvus.return_value.get_collection.return_value = collection
    mock_get_repo.return_value.get_by_milvus_ids.return_value = {10: Mock()}

    result = scan_orphan_vectors(
        "agent_memories",
        batch_size=1000,
        dry_run=False,
        max_delete=2,
    )

    assert result["orphan_count"] == 3
    assert result["deleted"] == 2
    assert result["delete_capped"] is True
    collection.delete.assert_called_once_with(expr="id in [11, 12]")


@patch("memory_system.orphan_vector_cleanup.scan_orphan_vectors")
@patch("memory_system.orphan_vector_cleanup._acquire_advisory_lock")
def test_run_orphan_cleanup_once_skips_when_lock_unavailable(mock_acquire, mock_scan):
    mock_acquire.return_value = None
    settings = OrphanCleanupSettings(enabled=True).with_defaults()

    result = run_orphan_cleanup_once(settings, reason="scheduled")

    assert result["status"] == "skipped"
    assert result["skip_reason"] == "lock_not_acquired"
    mock_scan.assert_not_called()

