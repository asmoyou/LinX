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
    deleted = {"mission_count": 0, "task_count": 0}

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

        def query(self, model, *args, **kwargs):
            model_name = getattr(model, "__name__", str(model))
            if model_name == "Mission":
                return _FakeQuery(self._mission)

            if model_name == "Task":
                class _DeleteQuery:
                    def filter(self, *args, **kwargs):
                        return self

                    def delete(self, synchronize_session=False):
                        assert synchronize_session is False
                        deleted["task_count"] += 1
                        return 1

                return _DeleteQuery()

            raise AssertionError(f"Unexpected model query: {model_name}")

        def delete(self, _row):
            deleted["mission_count"] += 1

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)

    assert mission_repository.delete_mission(uuid4()) is True
    assert deleted["task_count"] == 1
    assert deleted["mission_count"] == 1


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
    assert "qa_cycle_count" not in (reset.mission_config or {})


def test_prepare_partial_retry_for_failed_tasks_rejects_non_retryable_status(monkeypatch):
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

    with pytest.raises(ValueError, match="Only failed or cancelled missions can retry failed parts"):
        mission_repository.prepare_partial_retry_for_failed_tasks(uuid4())


def test_prepare_partial_retry_for_failed_tasks_resets_unfinished_tasks(monkeypatch):
    mission = type(
        "MissionStub",
        (),
        {
            "mission_id": uuid4(),
            "status": "failed",
            "error_message": "qa fail",
            "completed_at": object(),
            "failed_tasks": 2,
            "completed_tasks": 1,
            "total_tasks": 3,
            "mission_config": {"qa_cycle_count": 2, "execution_config": {"max_retries": 2}},
        },
    )()
    completed_task = type(
        "TaskStub",
        (),
        {
            "status": "completed",
            "completed_at": object(),
            "task_metadata": {"title": "done", "review_status": "approved"},
        },
    )()
    failed_task = type(
        "TaskStub",
        (),
        {
            "status": "failed",
            "completed_at": object(),
            "task_metadata": {
                "title": "failed",
                "review_status": "rework_required",
                "review_cycle_count": 3,
            },
        },
    )()
    in_progress_task = type(
        "TaskStub",
        (),
        {
            "status": "in_progress",
            "completed_at": object(),
            "task_metadata": {
                "title": "running",
                "review_status": "approved",
            },
        },
    )()
    tasks = [completed_task, failed_task, in_progress_task]

    class _MissionQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return mission

    class _TaskQuery:
        def filter(self, *args, **kwargs):
            return self

        def all(self):
            return tasks

    class _FakeSession:
        def query(self, model, *args, **kwargs):
            model_name = getattr(model, "__name__", str(model))
            if model_name == "Mission":
                return _MissionQuery()
            if model_name == "Task":
                return _TaskQuery()
            raise AssertionError(f"Unexpected model query: {model_name}")

        def flush(self):
            return None

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)

    summary = mission_repository.prepare_partial_retry_for_failed_tasks(mission.mission_id)

    assert summary == {
        "total_tasks": 3,
        "completed_tasks": 1,
        "retried_tasks": 2,
        "failed_tasks_before": 1,
    }
    assert mission.error_message is None
    assert mission.completed_at is None
    assert mission.failed_tasks == 0
    assert mission.completed_tasks == 1
    assert mission.total_tasks == 3
    assert "qa_cycle_count" not in (mission.mission_config or {})

    assert completed_task.status == "completed"
    assert failed_task.status == "pending"
    assert failed_task.completed_at is None
    assert failed_task.task_metadata["review_status"] == "rework_required"
    assert failed_task.task_metadata["review_cycle_count"] == 0

    assert in_progress_task.status == "pending"
    assert in_progress_task.completed_at is None
    assert in_progress_task.task_metadata["review_status"] == "pending"


def test_sync_mission_settings_snapshot_refreshes_llm_settings(monkeypatch):
    mission = type(
        "MissionStub",
        (),
        {
            "mission_id": uuid4(),
            "status": "draft",
            "created_by_user_id": uuid4(),
            "mission_config": {
                "leader_config": {"llm_provider": "ollama", "llm_model": "qwen2.5:14b"},
                "supervisor_config": {"llm_provider": "ollama", "llm_model": "qwen2.5:14b"},
                "qa_config": {"llm_provider": "ollama", "llm_model": "qwen2.5:14b"},
                "temporary_worker_config": {
                    "llm_provider": "ollama",
                    "llm_model": "qwen2.5:14b",
                },
                "execution_config": {
                    "max_retries": 3,
                    "network_access": False,
                    "max_concurrent_tasks": 2,
                },
                "network_access": True,
                "max_retries": 9,
                "base_image": "custom-image:latest",
            },
        },
    )()

    latest_settings = {
        "leader_config": {
            "llm_provider": "vllm",
            "llm_model": "Qwen3.5-27B-FP8",
            "temperature": 0.3,
            "max_tokens": 8192,
        },
        "supervisor_config": {
            "llm_provider": "vllm",
            "llm_model": "Qwen3.5-27B-FP8",
            "temperature": 0.2,
            "max_tokens": 2048,
        },
        "qa_config": {
            "llm_provider": "vllm",
            "llm_model": "Qwen3.5-27B-FP8",
            "temperature": 0.1,
            "max_tokens": 4096,
        },
        "temporary_worker_config": {
            "llm_provider": "vllm",
            "llm_model": "Qwen3.5-27B-FP8",
            "temperature": 0.3,
            "max_tokens": 8192,
        },
        "execution_config": {
            "max_retries": 3,
            "network_access": False,
            "max_concurrent_tasks": 6,
            "allow_temporary_workers": True,
        },
    }

    class _MissionQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return mission

    class _FakeSession:
        def query(self, model, *args, **kwargs):
            model_name = getattr(model, "__name__", str(model))
            if model_name == "Mission":
                return _MissionQuery()
            raise AssertionError(f"Unexpected model query: {model_name}")

        def flush(self):
            return None

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)
    monkeypatch.setattr(mission_repository, "get_mission_settings", lambda _user_id: latest_settings)

    refreshed = mission_repository.sync_mission_settings_snapshot(mission.mission_id)

    assert refreshed["leader_config"]["llm_provider"] == "vllm"
    assert refreshed["leader_config"]["llm_model"] == "Qwen3.5-27B-FP8"
    assert refreshed["temporary_worker_config"]["llm_provider"] == "vllm"
    assert refreshed["execution_config"]["max_concurrent_tasks"] == 6
    assert refreshed["execution_config"]["max_retries"] == 9
    assert refreshed["execution_config"]["network_access"] is True
    assert refreshed["max_retries"] == 9
    assert refreshed["network_access"] is True
    assert refreshed["base_image"] == "custom-image:latest"
    assert mission.mission_config == refreshed


def test_sync_mission_settings_snapshot_uses_network_enabled_legacy_override(monkeypatch):
    mission = type(
        "MissionStub",
        (),
        {
            "mission_id": uuid4(),
            "status": "failed",
            "created_by_user_id": uuid4(),
            "mission_config": {
                "network_enabled": True,
                "execution_config": {"network_access": False},
            },
        },
    )()

    latest_settings = {
        "leader_config": {"llm_provider": "vllm", "llm_model": "Qwen3.5-27B-FP8"},
        "supervisor_config": {"llm_provider": "vllm", "llm_model": "Qwen3.5-27B-FP8"},
        "qa_config": {"llm_provider": "vllm", "llm_model": "Qwen3.5-27B-FP8"},
        "temporary_worker_config": {
            "llm_provider": "vllm",
            "llm_model": "Qwen3.5-27B-FP8",
        },
        "execution_config": {"network_access": False},
    }

    class _MissionQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return mission

    class _FakeSession:
        def query(self, model, *args, **kwargs):
            model_name = getattr(model, "__name__", str(model))
            if model_name == "Mission":
                return _MissionQuery()
            raise AssertionError(f"Unexpected model query: {model_name}")

        def flush(self):
            return None

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(mission_repository, "get_db_session", _fake_db_session)
    monkeypatch.setattr(mission_repository, "get_mission_settings", lambda _user_id: latest_settings)

    refreshed = mission_repository.sync_mission_settings_snapshot(mission.mission_id)

    assert refreshed["execution_config"]["network_access"] is True
    assert refreshed["network_access"] is True
    assert "network_enabled" not in refreshed
