from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

import agent_scheduling.service as schedule_service
from agent_scheduling.cron_utils import ScheduleValidationError


class _SessionStub:
    def flush(self) -> None:
        return None

    def refresh(self, _obj) -> None:
        return None


def _build_once_schedule(*, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        schedule_id=uuid4(),
        owner_user_id=uuid4(),
        schedule_type="once",
        status=status,
        run_at_utc=datetime(2026, 3, 20, 1, 0, tzinfo=timezone.utc),
        next_run_at=None,
        name="金价提醒",
        prompt_template="提醒我查询国际金价",
    )


def test_pause_schedule_rejects_terminal_once_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    schedule = _build_once_schedule(status="completed")
    session = _SessionStub()

    @contextmanager
    def _fake_session():
        yield session

    monkeypatch.setattr(schedule_service, "get_db_session", _fake_session)
    monkeypatch.setattr(schedule_service, "_load_schedule_for_viewer", lambda *_args, **_kwargs: schedule)

    with pytest.raises(ScheduleValidationError, match="cannot be paused"):
        schedule_service.pause_schedule(
            schedule_id=str(schedule.schedule_id),
            viewer_user_id=str(schedule.owner_user_id),
            viewer_role="user",
        )


def test_resume_schedule_rejects_terminal_once_schedule(monkeypatch: pytest.MonkeyPatch) -> None:
    schedule = _build_once_schedule(status="completed")
    session = _SessionStub()

    @contextmanager
    def _fake_session():
        yield session

    monkeypatch.setattr(schedule_service, "get_db_session", _fake_session)
    monkeypatch.setattr(schedule_service, "_load_schedule_for_viewer", lambda *_args, **_kwargs: schedule)

    with pytest.raises(ScheduleValidationError, match="cannot be resumed"):
        schedule_service.resume_schedule(
            schedule_id=str(schedule.schedule_id),
            viewer_user_id=str(schedule.owner_user_id),
            viewer_role="user",
        )


def test_cleanup_terminal_one_time_schedules_deletes_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        SimpleNamespace(schedule_id=uuid4()),
        SimpleNamespace(schedule_id=uuid4()),
    ]

    class _QueryStub:
        def __init__(self, candidates):
            self._candidates = candidates
            self._limit = None

        def filter(self, *_args, **_kwargs):
            return self

        def order_by(self, *_args, **_kwargs):
            return self

        def limit(self, value: int):
            self._limit = value
            return self

        def all(self):
            if self._limit is None:
                return list(self._candidates)
            return list(self._candidates[: self._limit])

    class _CleanupSessionStub:
        def __init__(self, candidates):
            self.deleted = []
            self._query = _QueryStub(candidates)

        def query(self, _model):
            return self._query

        def delete(self, obj) -> None:
            self.deleted.append(obj)

    cleanup_session = _CleanupSessionStub(rows)

    @contextmanager
    def _fake_session():
        yield cleanup_session

    monkeypatch.setattr(schedule_service, "get_db_session", _fake_session)
    monkeypatch.setattr(
        schedule_service,
        "_utcnow",
        lambda: datetime(2026, 4, 20, tzinfo=timezone.utc),
    )

    deleted = schedule_service.cleanup_terminal_one_time_schedules(
        retention_days=30,
        limit=10,
    )

    assert deleted == 2
    assert cleanup_session.deleted == rows
