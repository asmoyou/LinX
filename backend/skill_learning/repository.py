"""Repository wrapper for reset-era skill proposals."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import SkillProposal
from user_memory.session_ledger_repository import (
    SessionLedgerRepository,
    get_session_ledger_repository,
)


class SkillProposalRepository:
    """Read and write reviewed skill proposals."""

    def __init__(self, repository: Optional[SessionLedgerRepository] = None):
        self._repository = repository or get_session_ledger_repository()

    def list_proposals(
        self,
        *,
        agent_ids: List[str],
        review_status: str,
        limit: int,
    ) -> List[SkillProposal]:
        normalized_review_status = str(review_status or "pending").strip().lower()
        rows: List[SkillProposal] = []
        per_agent_limit = max(int(limit), 1) if len(agent_ids) == 1 else max(int(limit), 50)
        for agent_id in agent_ids:
            rows.extend(
                self._repository.list_skill_proposals(
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
        deduped: List[SkillProposal] = []
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

    def get_proposal(self, proposal_id: int) -> Optional[SkillProposal]:
        return self._repository.get_skill_proposal(proposal_id)

    def update_proposal(
        self,
        *,
        proposal_id: int,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        details: Optional[str] = None,
        review_status: Optional[str] = None,
        review_note: Optional[str] = None,
        payload: Optional[dict] = None,
        published_skill_id: Optional[str] = None,
    ) -> Optional[SkillProposal]:
        with get_db_session() as db:
            row = db.query(SkillProposal).filter(SkillProposal.id == int(proposal_id)).one_or_none()
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
                row.proposal_payload = dict(payload)
            if published_skill_id is not None:
                row.published_skill_id = (
                    UUID(str(published_skill_id)) if published_skill_id else None
                )
            db.flush()
            db.refresh(row)
            return row


_skill_proposal_repository: Optional[SkillProposalRepository] = None


def get_skill_proposal_repository() -> SkillProposalRepository:
    """Return the shared skill-proposal repository."""

    global _skill_proposal_repository
    if _skill_proposal_repository is None:
        _skill_proposal_repository = SkillProposalRepository()
    return _skill_proposal_repository
