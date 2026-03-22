from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from skill_learning.candidate_service import SkillCandidateService


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


def _build_candidate_row():
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=6,
        agent_id=str(uuid4()),
        user_id=str(uuid4()),
        cluster_key="cluster-1",
        title="Playbook title",
        goal="Playbook goal",
        successful_path=["step one", "step two"],
        why_it_worked="Because it works",
        applicability="When this scenario appears",
        avoid="Avoid doing the wrong thing",
        confidence=0.81,
        candidate_status="new",
        review_status="pending",
        review_note=None,
        promoted_skill_id=None,
        promoted_revision_id=None,
        candidate_payload={"tags": ["alpha"]},
        created_at=now,
        updated_at=now,
    )


def test_promote_candidate_uses_inline_storage_for_new_playbook_skill() -> None:
    row = _build_candidate_row()
    session = _FakeSession(row)
    canonical_service = MagicMock()
    created_skill_id = uuid4()
    created_revision_id = uuid4()
    canonical_service.create_skill.return_value = SimpleNamespace(
        skill_id=created_skill_id,
        active_revision_id=created_revision_id,
    )

    with patch(
        "skill_learning.candidate_service.get_db_session",
        return_value=_FakeSessionContext(session),
    ), patch(
        "skill_learning.candidate_service.get_canonical_skill_service",
        return_value=canonical_service,
    ):
        promoted = SkillCandidateService().promote_candidate(
            candidate_id=6,
            reviewer_user_id=str(uuid4()),
        )

    revision_payload = canonical_service.create_skill.call_args.kwargs["revision_payload"]

    assert revision_payload["artifact_storage_kind"] == "inline"
    assert promoted is not None
    assert promoted.review_status == "published"
    assert promoted.status == "promoted"
    session.refresh.assert_called_once_with(row)
    canonical_service.ensure_binding.assert_called_once()


def test_merge_candidate_uses_inline_storage_for_new_revision() -> None:
    row = _build_candidate_row()
    session = _FakeSession(row)
    canonical_service = MagicMock()
    target_skill_id = uuid4()
    revision_id = uuid4()
    canonical_service.create_revision.return_value = SimpleNamespace(revision_id=revision_id)
    canonical_service.activate_revision.return_value = SimpleNamespace(
        skill_id=target_skill_id,
        active_revision_id=revision_id,
    )

    with patch(
        "skill_learning.candidate_service.get_db_session",
        return_value=_FakeSessionContext(session),
    ), patch(
        "skill_learning.candidate_service.get_canonical_skill_service",
        return_value=canonical_service,
    ):
        merged = SkillCandidateService().promote_candidate(
            candidate_id=6,
            reviewer_user_id=str(uuid4()),
            target_skill_id=str(target_skill_id),
        )

    revision_payload = canonical_service.create_revision.call_args.kwargs["revision_payload"]

    assert revision_payload["artifact_storage_kind"] == "inline"
    assert merged is not None
    assert merged.status == "merged"
    canonical_service.ensure_binding.assert_called_once()
