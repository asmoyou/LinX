"""Repository wrapper for reset-era skill candidates."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import SkillCandidate
from user_memory.session_ledger_repository import (
    SessionLedgerRepository,
    get_session_ledger_repository,
)


class SkillCandidateRepository:
    """Read and write reviewed skill candidates."""

    def __init__(self, repository: Optional[SessionLedgerRepository] = None):
        self._repository = repository or get_session_ledger_repository()

    def list_candidates(
        self,
        *,
        agent_ids: List[str],
        review_status: str,
        limit: int,
    ) -> List[SkillCandidate]:
        normalized_review_status = str(review_status or "pending").strip().lower()
        rows: List[SkillCandidate] = []
        per_agent_limit = max(int(limit), 1) if len(agent_ids) == 1 else max(int(limit), 50)
        for agent_id in agent_ids:
            rows.extend(
                self._repository.list_skill_candidates(
                    agent_id=str(agent_id),
                    review_status=normalized_review_status,
                    limit=per_agent_limit,
                )
            )
        rows.sort(
            key=lambda row: (
                getattr(row, "updated_at", None) or getattr(row, "created_at", None),
                int(getattr(row, "id", 0) or 0),
            ),
            reverse=True,
        )
        deduped: List[SkillCandidate] = []
        seen = set()
        for row in rows:
            row_id = int(getattr(row, "id", 0) or 0)
            if row_id in seen:
                continue
            seen.add(row_id)
            deduped.append(row)
            if len(deduped) >= max(int(limit), 1):
                break
        return deduped

    def get_candidate(self, candidate_id: int) -> Optional[SkillCandidate]:
        return self._repository.get_skill_candidate(candidate_id)

    def update_candidate(
        self,
        *,
        candidate_id: int,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        details: Optional[str] = None,
        review_status: Optional[str] = None,
        review_note: Optional[str] = None,
        payload: Optional[dict] = None,
        promoted_skill_id: Optional[str] = None,
    ) -> Optional[SkillCandidate]:
        with get_db_session() as db:
            row = db.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            if row is None:
                return None
            if title is not None:
                row.title = str(title)
                row.goal = str(title)
            if summary is not None:
                row.why_it_worked = str(summary) if summary else None
            if details is not None:
                row.details = details
            if review_status is not None:
                row.review_status = str(review_status)
            if review_note is not None:
                row.review_note = str(review_note) if review_note else None
            if payload is not None:
                row.candidate_payload = dict(payload)
            if promoted_skill_id is not None:
                row.promoted_skill_id = (
                    UUID(str(promoted_skill_id)) if promoted_skill_id else None
                )
            db.flush()
            db.refresh(row)
            return row

    def delete_candidate(self, candidate_id: int) -> bool:
        with get_db_session() as db:
            row = db.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            if row is None:
                return False
            db.delete(row)
            db.flush()
            return True

    def count_candidates_for_promoted_skill(
        self,
        *,
        promoted_skill_id: str,
        exclude_candidate_id: Optional[int] = None,
    ) -> int:
        with get_db_session() as db:
            query = db.query(SkillCandidate).filter(
                SkillCandidate.promoted_skill_id == UUID(str(promoted_skill_id))
            )
            if exclude_candidate_id is not None:
                query = query.filter(SkillCandidate.id != int(exclude_candidate_id))
            return int(query.count())


_skill_candidate_repository: Optional[SkillCandidateRepository] = None


def get_skill_candidate_repository() -> SkillCandidateRepository:
    """Return the shared skill-candidate repository."""

    global _skill_candidate_repository
    if _skill_candidate_repository is None:
        _skill_candidate_repository = SkillCandidateRepository()
    return _skill_candidate_repository
