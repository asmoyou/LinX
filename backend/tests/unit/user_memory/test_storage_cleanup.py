from unittest.mock import Mock

from user_memory.storage_cleanup import (
    drop_legacy_user_memory_vector_collection,
    prepare_user_memory_rows_for_user_deletion,
)


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
        if class_name == "UserMemoryRelation":
            return _QueryStub(
                count_value=1,
                delete_recorder=self.deleted_calls,
                delete_key="UserMemoryRelation",
            )
        if class_name == "UserMemoryView":
            return _QueryStub(
                count_value=3,
                delete_recorder=self.deleted_calls,
                delete_key="UserMemoryView",
            )
        if class_name == "SkillCandidate":
            return _QueryStub(
                count_value=4,
                delete_recorder=self.deleted_calls,
                delete_key="SkillCandidate",
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


def test_prepare_user_memory_rows_for_user_deletion_removes_user_scoped_rows():
    session = _SessionStub()

    result = prepare_user_memory_rows_for_user_deletion(session, user_id="user-1")

    assert result["entry_ids"] == ["101", "102"]
    assert result["session_ids"] == [201, 202]
    assert result["memory_entries"] == 2
    assert result["memory_relations"] == 1
    assert result["memory_views"] == 3
    assert result["skill_candidates"] == 4
    assert result["session_events"] == 5
    assert session.flush_called is True
    assert session.deleted_calls == [
        ("UserMemoryLink", False),
        ("UserMemoryRelation", False),
        ("UserMemoryEntry", False),
        ("UserMemoryView", False),
        ("SkillCandidate", False),
        ("SessionLedger", False),
    ]


def test_drop_legacy_user_memory_vector_collection_removes_collection_when_present():
    fake_connection = Mock()
    fake_connection.collection_exists.return_value = True

    result = drop_legacy_user_memory_vector_collection(milvus_conn=fake_connection)

    assert result["exists"] is True
    assert result["dropped"] is True
    fake_connection.drop_collection.assert_called_once_with("user_memory_entries")


def test_drop_legacy_user_memory_vector_collection_returns_absent_when_missing():
    fake_connection = Mock()
    fake_connection.collection_exists.return_value = False

    result = drop_legacy_user_memory_vector_collection(milvus_conn=fake_connection)

    assert result["exists"] is False
    assert result["dropped"] is False
    fake_connection.drop_collection.assert_not_called()
