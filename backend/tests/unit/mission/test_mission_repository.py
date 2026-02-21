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
