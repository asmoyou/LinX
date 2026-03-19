"""Service layer for canonical skill candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import or_

from database.connection import get_db_session
from database.models import SkillCandidate
from skill_library.canonical_service import get_canonical_skill_service


def _build_playbook_instruction(candidate: SkillCandidate) -> str:
    steps = [
        str(step).strip()
        for step in ((candidate.candidate_payload or {}).get("successful_path") or [])
        if str(step).strip()
    ]
    lines = [f"# {candidate.title}", "", "## Goal", str(candidate.goal or candidate.title or "").strip()]
    if steps:
        lines.extend(["", "## Key Steps"])
        lines.extend(f"- {step}" for step in steps)
    if candidate.why_it_worked:
        lines.extend(["", "## Why It Worked", str(candidate.why_it_worked).strip()])
    if candidate.applicability:
        lines.extend(["", "## When To Use", str(candidate.applicability).strip()])
    if candidate.avoid:
        lines.extend(["", "## Avoid", str(candidate.avoid).strip()])
    return "\n".join(lines)


@dataclass(frozen=True)
class SkillCandidateInfo:
    candidate_id: int
    source_agent_id: str
    user_id: str
    cluster_key: str
    title: str
    goal: str
    successful_path: List[str]
    why_it_worked: Optional[str]
    applicability: Optional[str]
    avoid: Optional[str]
    confidence: float
    status: str
    review_status: str
    review_note: Optional[str]
    promoted_skill_id: Optional[str]
    promoted_revision_id: Optional[str]
    created_at: Any
    updated_at: Any
    payload: Dict[str, Any]


class SkillCandidateService:
    """Manage learned skill candidates and promotion into canonical skills."""

    @staticmethod
    def _to_info(row: SkillCandidate) -> SkillCandidateInfo:
        payload = dict(row.candidate_payload or {})
        return SkillCandidateInfo(
            candidate_id=int(row.id),
            source_agent_id=str(row.agent_id or ""),
            user_id=str(row.user_id or ""),
            cluster_key=str(row.cluster_key or ""),
            title=str(row.title or ""),
            goal=str(row.goal or ""),
            successful_path=[str(step).strip() for step in (row.successful_path or []) if str(step).strip()],
            why_it_worked=row.why_it_worked,
            applicability=row.applicability,
            avoid=row.avoid,
            confidence=float(row.confidence or 0.0),
            status=str(row.candidate_status or "new"),
            review_status=str(row.review_status or "pending"),
            review_note=row.review_note,
            promoted_skill_id=str(row.promoted_skill_id) if row.promoted_skill_id else None,
            promoted_revision_id=str(row.promoted_revision_id) if row.promoted_revision_id else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
            payload=payload,
        )

    def list_candidates(
        self,
        *,
        agent_ids: List[str],
        status: Optional[str],
        limit: int,
        query_text: Optional[str] = None,
    ) -> List[SkillCandidateInfo]:
        with get_db_session() as session:
            query = session.query(SkillCandidate)
            if agent_ids:
                query = query.filter(SkillCandidate.agent_id.in_([str(item) for item in agent_ids]))
            if status and status != "all":
                normalized_status = str(status).strip().lower()
                if normalized_status == "published":
                    query = query.filter(
                        or_(
                            SkillCandidate.review_status == "published",
                            SkillCandidate.candidate_status.in_(["promoted", "merged"]),
                        )
                    )
                elif normalized_status == "pending":
                    query = query.filter(
                        or_(
                            SkillCandidate.review_status == "pending",
                            SkillCandidate.candidate_status == "new",
                        )
                    )
                elif normalized_status == "revise":
                    query = query.filter(SkillCandidate.review_status == "revise")
                else:
                    query = query.filter(
                        or_(
                            SkillCandidate.candidate_status == normalized_status,
                            SkillCandidate.review_status == normalized_status,
                        )
                    )
            normalized_query = str(query_text or "").strip()
            if normalized_query:
                search_pattern = f"%{normalized_query}%"
                query = query.filter(
                    or_(
                        SkillCandidate.title.ilike(search_pattern),
                        SkillCandidate.goal.ilike(search_pattern),
                        SkillCandidate.why_it_worked.ilike(search_pattern),
                        SkillCandidate.applicability.ilike(search_pattern),
                        SkillCandidate.avoid.ilike(search_pattern),
                    )
                )
            rows = (
                query.order_by(SkillCandidate.updated_at.desc(), SkillCandidate.id.desc())
                .limit(max(int(limit), 1))
                .all()
            )
            return [self._to_info(row) for row in rows]

    def get_candidate(self, candidate_id: int) -> Optional[SkillCandidateInfo]:
        with get_db_session() as session:
            row = session.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            return self._to_info(row) if row else None

    def reject_candidate(self, *, candidate_id: int, review_note: Optional[str]) -> Optional[SkillCandidateInfo]:
        with get_db_session() as session:
            row = session.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            if row is None:
                return None
            row.candidate_status = "rejected"
            row.review_status = "rejected"
            row.review_note = str(review_note) if review_note else None
            session.flush()
            session.refresh(row)
            return self._to_info(row)

    def revise_candidate(self, *, candidate_id: int, review_note: Optional[str]) -> Optional[SkillCandidateInfo]:
        with get_db_session() as session:
            row = session.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            if row is None:
                return None
            row.review_status = "revise"
            row.review_note = str(review_note) if review_note else None
            session.flush()
            session.refresh(row)
            return self._to_info(row)

    def promote_candidate(
        self,
        *,
        candidate_id: int,
        reviewer_user_id: str,
        target_skill_id: Optional[str] = None,
        auto_bind_source_agent: bool = True,
    ) -> Optional[SkillCandidateInfo]:
        service = get_canonical_skill_service()
        with get_db_session() as session:
            row = session.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            if row is None:
                return None
            payload = dict(row.candidate_payload or {})
            config_payload = {
                "successful_path": list(row.successful_path or []),
                "why_it_worked": row.why_it_worked,
                "applicability": row.applicability,
                "avoid": row.avoid,
                "candidate_id": int(row.id),
            }
            revision_payload = {
                "version": "1.0.0",
                "review_state": "approved",
                "instruction_md": _build_playbook_instruction(row),
                "tool_code": None,
                "interface_definition": {
                    "inputs": {"goal": "string", "task_context": "string"},
                    "outputs": {"recommended_path": "string"},
                    "required_inputs": ["goal"],
                },
                "artifact_storage_kind": "inline",
                "artifact_ref": None,
                "manifest": {"artifact_kind": "playbook", "runtime_mode": "retrieval"},
                "config": config_payload,
                "change_note": "Promoted from skill candidate",
            }
            if target_skill_id:
                skill_id = UUID(str(target_skill_id))
                revision = service.create_revision(
                    skill_id=skill_id,
                    owner_user_id=reviewer_user_id,
                    revision_payload=revision_payload,
                )
                service.review_revision(
                    skill_id=skill_id,
                    revision_id=revision.revision_id,
                    review_state="approved",
                )
                skill = service.activate_revision(
                    skill_id=skill_id,
                    revision_id=revision.revision_id,
                    actor_user_id=reviewer_user_id,
                )
                row.candidate_status = "merged"
            else:
                slug = (
                    f"learned_{str(row.agent_id or 'agent').replace('-', '_')}_"
                    f"{str(row.cluster_key or row.id)}"
                )
                skill = service.create_skill(
                    slug=slug[:255],
                    display_name=str(row.title or row.goal or slug),
                    description=str(row.why_it_worked or row.goal or "Learned playbook"),
                    source_kind="candidate",
                    artifact_kind="playbook",
                    runtime_mode="retrieval",
                    visibility="private",
                    owner_user_id=reviewer_user_id,
                    department_id=None,
                    revision_payload=revision_payload,
                    lifecycle_state="active",
                )
                row.candidate_status = "promoted"
            row.review_status = "published"
            row.promoted_skill_id = UUID(str(skill.skill_id))
            row.promoted_revision_id = UUID(str(skill.active_revision_id)) if skill.active_revision_id else None
            row.review_note = payload.get("review_note") or row.review_note
            if auto_bind_source_agent and row.agent_id and skill.skill_id:
                service.ensure_binding(
                    agent_id=UUID(str(row.agent_id)),
                    skill_id=skill.skill_id,
                    binding_mode="retrieval",
                    source="auto_learned",
                )
            session.flush()
            session.refresh(row)
            return self._to_info(row)

    def delete_candidate(self, *, candidate_id: int) -> bool:
        with get_db_session() as session:
            row = session.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            if row is None:
                return False
            session.delete(row)
            session.flush()
            return True


_skill_candidate_service: Optional[SkillCandidateService] = None


def get_skill_candidate_service() -> SkillCandidateService:
    global _skill_candidate_service
    if _skill_candidate_service is None:
        _skill_candidate_service = SkillCandidateService()
    return _skill_candidate_service
