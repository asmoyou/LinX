from types import SimpleNamespace
from unittest.mock import Mock, patch

from user_memory.storage_cleanup import (
    UserMemoryVectorCleanupSettings,
    delete_user_memory_entry_vectors,
    load_user_memory_vector_cleanup_settings,
    prepare_user_memory_rows_for_user_deletion,
    run_user_memory_vector_cleanup_once,
)


class _ConfigStub:
    def __init__(self, section):
        self._section = section

    def get(self, key, default=None):
        if key == "user_memory.vector_cleanup":
            return self._section
        return default


class _QueryStub:
    def __init__(self, *, all_result=None, count_value=0, delete_recorder=None, delete_key=None):
        self._all_result = list(all_result or [])
        self._count_value = int(count_value)
        self._delete_recorder = delete_recorder
        self._delete_key = delete_key

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._all_result)

    def count(self):
        return self._count_value

    def delete(self, synchronize_session=False):
        if self._delete_recorder is not None and self._delete_key is not None:
            self._delete_recorder.append((self._delete_key, synchronize_session))
        return self._count_value


class _SessionStub:
    def __init__(self):
        self.deleted_calls = []
        self.flush_called = False

    def query(self, entity):
        class_name = getattr(entity, "__name__", "")
        attr_key = getattr(entity, "key", "")
        owner = getattr(entity, "class_", None)
        owner_name = getattr(owner, "__name__", "")

        if owner_name == "UserMemoryEntry" and attr_key == "id":
            return _QueryStub(all_result=[(101,), (102,)])
        if owner_name == "SessionLedger" and attr_key == "id":
            return _QueryStub(all_result=[(201,), (202,)])
        if class_name == "SessionLedgerEvent":
            return _QueryStub(count_value=5)
        if class_name == "UserMemoryLink":
            return _QueryStub(
                count_value=2,
                delete_recorder=self.deleted_calls,
                delete_key="UserMemoryLink",
            )
        if class_name == "UserMemoryEntry":
            return _QueryStub(
                count_value=2,
                delete_recorder=self.deleted_calls,
                delete_key="UserMemoryEntry",
            )
        if class_name == "UserMemoryView":
            return _QueryStub(
                count_value=3,
                delete_recorder=self.deleted_calls,
                delete_key="UserMemoryView",
            )
        if class_name == "SkillProposal":
            return _QueryStub(
                count_value=4,
                delete_recorder=self.deleted_calls,
                delete_key="SkillProposal",
            )
        if class_name == "SessionLedger":
            return _QueryStub(
                count_value=2,
                delete_recorder=self.deleted_calls,
                delete_key="SessionLedger",
            )
        raise AssertionError(f"Unexpected query entity: {entity!r}")

    def flush(self):
        self.flush_called = True


def test_load_user_memory_vector_cleanup_settings_uses_defaults():
    settings = load_user_memory_vector_cleanup_settings(_ConfigStub({"enabled": True}))

    assert settings.enabled is True
    assert settings.batch_size == 500
    assert settings.compact_on_cycle is True
    assert settings.interval_seconds == 21600


def test_delete_user_memory_entry_vectors_batches_requests():
    fake_collection = Mock()
    fake_connection = Mock()
    fake_connection.collection_exists.return_value = True
    fake_connection.get_collection.return_value = fake_collection

    result = delete_user_memory_entry_vectors(
        ["101", "102", "103"],
        milvus_conn=fake_connection,
        batch_size=2,
    )

    assert result["deleted_entry_ids"] == 3
    assert fake_collection.delete.call_count == 2
    assert fake_collection.delete.call_args_list[0].args[0] == 'entry_id in ["101", "102"]'
    assert fake_collection.delete.call_args_list[1].args[0] == 'entry_id in ["103"]'


def test_prepare_user_memory_rows_for_user_deletion_removes_user_scoped_rows():
    session = _SessionStub()

    result = prepare_user_memory_rows_for_user_deletion(session, user_id="user-1")

    assert result["entry_ids"] == ["101", "102"]
    assert result["session_ids"] == [201, 202]
    assert result["memory_entries"] == 2
    assert result["memory_views"] == 3
    assert result["skill_proposals"] == 4
    assert result["session_events"] == 5
    assert session.flush_called is True
    assert session.deleted_calls == [
        ("UserMemoryLink", False),
        ("UserMemoryEntry", False),
        ("UserMemoryView", False),
        ("SkillProposal", False),
        ("SessionLedger", False),
    ]


@patch("user_memory.storage_cleanup.trigger_user_memory_collection_compaction")
@patch("user_memory.storage_cleanup.cleanup_orphaned_user_memory_vectors")
@patch("user_memory.storage_cleanup._load_live_user_memory_entry_ids")
def test_run_user_memory_vector_cleanup_once_returns_combined_summary(
    mock_load_live_ids,
    mock_cleanup_vectors,
    mock_compaction,
):
    mock_load_live_ids.return_value = {"101", "102"}
    mock_cleanup_vectors.return_value = {
        "scanned_rows": 7,
        "orphaned_entry_ids": 2,
        "deleted_entry_ids": 2,
        "errors": [],
    }
    mock_compaction.return_value = {"attempted": True, "triggered": True, "error": None}

    result = run_user_memory_vector_cleanup_once(
        UserMemoryVectorCleanupSettings(
            enabled=True,
            use_advisory_lock=False,
        ),
        reason="scheduled",
    )

    assert result["status"] == "ok"
    assert result["cleanup"]["live_entry_ids"] == 2
    assert result["cleanup"]["vector_cleanup"]["deleted_entry_ids"] == 2
    assert result["cleanup"]["compaction"]["triggered"] is True
