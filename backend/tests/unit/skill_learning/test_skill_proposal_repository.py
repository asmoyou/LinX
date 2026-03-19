"""Tests for skill-candidate repository."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from skill_learning.repository import SkillCandidateRepository


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *_args, **_kwargs):
        return self

    def one_or_none(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row
        self.refresh = MagicMock()

    def query(self, _model):
        return _FakeQuery(self._row)

    def flush(self):
        return None


class _FakeSessionContext:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, exc_type, exc, tb):
        return False


def test_update_candidate_refreshes_row_before_return() -> None:
    row = SimpleNamespace(
        id=7,
        title="before",
        goal="before",
        why_it_worked=None,
        review_status="pending",
        review_note=None,
        promoted_skill_id=None,
        candidate_payload={},
    )
    session = _FakeSession(row)
    repository = SkillCandidateRepository(repository=MagicMock())

    with patch(
        "skill_learning.repository.get_db_session",
        return_value=_FakeSessionContext(session),
    ):
        updated = repository.update_candidate(
            candidate_id=7,
            summary="updated summary",
            review_status="published",
            payload={"goal": "after"},
        )

    assert updated is row
    session.refresh.assert_called_once_with(row)
    assert row.why_it_worked == "updated summary"
    assert row.review_status == "published"
    assert row.candidate_payload == {"goal": "after"}
