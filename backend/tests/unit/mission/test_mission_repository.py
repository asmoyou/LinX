"""Unit tests for mission repository settings fallbacks."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy.exc import SQLAlchemyError

from mission_system import mission_repository


@contextmanager
def _broken_db_session():
    raise SQLAlchemyError("db unavailable")
    yield


def test_get_mission_settings_falls_back_to_defaults(monkeypatch):
    monkeypatch.setattr(mission_repository, "get_db_session", _broken_db_session)

    result = mission_repository.get_mission_settings(uuid4())

    assert result["leader_config"]["llm_provider"] == "ollama"
    assert result["supervisor_config"]["llm_provider"] == "ollama"
    assert result["qa_config"]["llm_provider"] == "ollama"
    assert result["temporary_worker_config"]["llm_provider"] == "ollama"
    assert result["execution_config"]["max_retries"] == 3


def test_upsert_mission_settings_raises_on_db_error(monkeypatch):
    monkeypatch.setattr(mission_repository, "get_db_session", _broken_db_session)

    with pytest.raises(SQLAlchemyError):
        mission_repository.upsert_mission_settings(
            uuid4(),
            {
                "leader_config": {"temperature": 0.9},
                "execution_config": {"max_concurrent_tasks": 8},
            },
        )


def test_delete_mission_returns_false_when_not_found(monkeypatch):
    class _FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return None

    class _FakeSession:
        def query(self, *args, **kwargs):
            return _FakeQuery()

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)

    assert mission_repository.delete_mission(uuid4()) is False


def test_delete_mission_deletes_existing_row(monkeypatch):
    deleted = {"count": 0}

    class _FakeQuery:
        def __init__(self, mission):
            self._mission = mission

        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return self._mission

    class _FakeSession:
        def __init__(self):
            self._mission = object()

        def query(self, *args, **kwargs):
            return _FakeQuery(self._mission)

        def delete(self, _row):
            deleted["count"] += 1

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)

    assert mission_repository.delete_mission(uuid4()) is True
    assert deleted["count"] == 1


def test_reset_failed_mission_for_retry_rejects_non_retryable_status(monkeypatch):
    mission = type("MissionStub", (), {"status": "completed"})()

    class _MissionQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return mission

    class _FakeSession:
        def query(self, *args, **kwargs):
            return _MissionQuery()

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)

    with pytest.raises(ValueError, match="Only failed or cancelled missions can be retried"):
        mission_repository.reset_failed_mission_for_retry(uuid4())


def test_reset_failed_mission_for_retry_clears_runtime_state(monkeypatch):
    delete_calls = {"tasks": 0, "agents": 0}
    mission = type(
        "MissionStub",
        (),
        {
            "mission_id": uuid4(),
            "status": "failed",
            "error_message": "timeout",
            "result": {"deliverables": [{"path": "x"}]},
            "requirements_doc": "old requirements",
            "total_tasks": 9,
            "completed_tasks": 2,
            "failed_tasks": 7,
            "started_at": object(),
            "completed_at": object(),
            "container_id": "container-1",
            "workspace_bucket": "bucket-1",
            "mission_config": {"qa_cycle_count": 3, "execution_config": {"max_retries": 2}},
        },
    )()

    class _MissionQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return mission

    class _DeleteQuery:
        def __init__(self, key):
            self._key = key

        def filter(self, *args, **kwargs):
            return self

        def delete(self, synchronize_session=False):
            assert synchronize_session is False
            delete_calls[self._key] += 1
            return 1

    class _FakeSession:
        def query(self, model, *args, **kwargs):
            model_name = getattr(model, "__name__", str(model))
            if model_name == "Mission":
                return _MissionQuery()
            if model_name == "Task":
                return _DeleteQuery("tasks")
            if model_name == "MissionAgent":
                return _DeleteQuery("agents")
            raise AssertionError(f"Unexpected model query: {model_name}")

        def flush(self):
            return None

        def refresh(self, _obj):
            return None

        def expunge(self, _obj):
            return None

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)

    reset = mission_repository.reset_failed_mission_for_retry(mission.mission_id)

    assert reset.status == "draft"
    assert reset.error_message is None
    assert reset.result is None
    assert reset.requirements_doc is None
    assert reset.total_tasks == 0
    assert reset.completed_tasks == 0
    assert reset.failed_tasks == 0
    assert reset.started_at is None
    assert reset.completed_at is None
    assert reset.container_id is None
    assert reset.workspace_bucket is None
    assert "qa_cycle_count" not in (reset.mission_config or {})
    assert delete_calls["tasks"] == 1
    assert delete_calls["agents"] == 1


def test_reset_failed_mission_for_retry_accepts_cancelled(monkeypatch):
    mission = type(
        "MissionStub",
        (),
        {
            "mission_id": uuid4(),
            "status": "cancelled",
            "error_message": "cancelled by user",
            "result": {"deliverables": []},
            "requirements_doc": "old requirements",
            "total_tasks": 4,
            "completed_tasks": 1,
            "failed_tasks": 1,
            "started_at": object(),
            "completed_at": object(),
            "container_id": "container-1",
            "workspace_bucket": "bucket-1",
            "mission_config": {"qa_cycle_count": 2},
        },
    )()

    class _MissionQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return mission

    class _DeleteQuery:
        def filter(self, *args, **kwargs):
            return self

        def delete(self, synchronize_session=False):
            assert synchronize_session is False
            return 1

    class _FakeSession:
        def query(self, model, *args, **kwargs):
            model_name = getattr(model, "__name__", str(model))
            if model_name == "Mission":
                return _MissionQuery()
            if model_name in {"Task", "MissionAgent"}:
                return _DeleteQuery()
            raise AssertionError(f"Unexpected model query: {model_name}")

        def flush(self):
            return None

        def refresh(self, _obj):
            return None

        def expunge(self, _obj):
            return None

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)

    reset = mission_repository.reset_failed_mission_for_retry(mission.mission_id)
    assert reset.status == "draft"
    assert reset.error_message is None
