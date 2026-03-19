"""Skill candidate review endpoints mounted under /skills/candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from database.connection import get_db_session
from database.models import Skill
from skill_learning.candidate_service import SkillCandidateInfo, get_skill_candidate_service

from .memory_access import (
    _agent_owned_by_user_sync,
    _is_admin_or_manager,
    _list_owned_agent_ids_sync,
    _lookup_agent_name,
    _require_agent_read_access_sync,
)

router = APIRouter(tags=["skill-candidates"])


def _require_candidate_manage_access(agent_id: str, current_user: CurrentUser) -> None:
    _require_agent_read_access_sync(agent_id, current_user)
    if _is_admin_or_manager(current_user):
        return
    if _agent_owned_by_user_sync(agent_id, current_user.user_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to modify this skill candidate",
    )


def _present_candidate_status(info: SkillCandidateInfo) -> str:
    review_status = str(info.review_status or "").strip().lower()
    if review_status in {"published", "rejected", "revise"}:
        return review_status
    if str(info.status or "").strip().lower() in {"promoted", "merged"}:
        return "published"
    if str(info.status or "").strip().lower() == "rejected":
        return "rejected"
    return "pending"


def _build_candidate_content(info: SkillCandidateInfo) -> str:
    steps = [str(step).strip() for step in info.successful_path if str(step).strip()]
    lines: List[str] = []
    goal = str(info.goal or info.title or "").strip()
    if goal:
        lines.append(f"goal={goal}")
    if steps:
        lines.append("successful_path=" + " | ".join(steps))
    if info.why_it_worked:
        lines.append(f"why_it_worked={str(info.why_it_worked).strip()}")
    if info.applicability:
        lines.append(f"applicability={str(info.applicability).strip()}")
    if info.avoid:
        lines.append(f"avoid={str(info.avoid).strip()}")
    return "\n".join(lines)


def _lookup_skill_summary(skill_id: Optional[str]) -> Dict[str, Optional[str]]:
    if not skill_id:
        return {"skill_slug": None, "skill_type": None}
    try:
        normalized_skill_id = UUID(str(skill_id))
    except ValueError:
        return {"skill_slug": None, "skill_type": None}
    with get_db_session() as session:
        row = session.query(Skill).filter(Skill.skill_id == normalized_skill_id).one_or_none()
        if row is None:
            return {"skill_slug": None, "skill_type": None}
        return {
            "skill_slug": str(row.skill_slug or "") or None,
            "skill_type": str(row.skill_type or "") or None,
        }


class SkillCandidateResponse(BaseModel):
    candidate_id: str
    title: str
    summary: str
    content: str
    status: str
    tags: List[str] = Field(default_factory=list)
    skill_id: Optional[str] = None
    skill_slug: Optional[str] = None
    skill_type: Optional[str] = None
    source_memory_id: Optional[str] = None
    source_agent_id: Optional[str] = None
    source_agent_name: Optional[str] = None
    review_note: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_info(cls, info: SkillCandidateInfo) -> "SkillCandidateResponse":
        payload = dict(info.payload or {})
        skill_summary = _lookup_skill_summary(info.promoted_skill_id)
        with get_db_session() as session:
            source_agent_name = _lookup_agent_name(session, info.source_agent_id)
        tags = payload.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        summary = str(info.why_it_worked or info.goal or info.title or "").strip()
        content = _build_candidate_content(info) or summary
        metadata = {
            **payload,
            "review_status": info.review_status,
            "candidate_status": info.status,
            "promoted_revision_id": info.promoted_revision_id,
            "confidence": info.confidence,
            "successful_path": list(info.successful_path),
            "applicability": info.applicability,
            "avoid": info.avoid,
        }
        source_memory_id = payload.get("source_memory_id") or payload.get("memory_id")
        return cls(
            candidate_id=str(info.candidate_id),
            title=str(info.title or info.goal or "Untitled candidate"),
            summary=summary or "Untitled candidate",
            content=content or summary or "Untitled candidate",
            status=_present_candidate_status(info),
            tags=[str(tag).strip() for tag in tags if str(tag).strip()],
            skill_id=info.promoted_skill_id,
            skill_slug=skill_summary["skill_slug"],
            skill_type=skill_summary["skill_type"],
            source_memory_id=str(source_memory_id) if source_memory_id else None,
            source_agent_id=info.source_agent_id or None,
            source_agent_name=source_agent_name,
            review_note=info.review_note,
            created_at=info.created_at.isoformat() if getattr(info.created_at, "isoformat", None) else "",
            updated_at=(
                info.updated_at.isoformat() if getattr(info.updated_at, "isoformat", None) else None
            ),
            metadata=metadata,
        )


class PromoteSkillCandidateRequest(BaseModel):
    auto_bind_source_agent: bool = True


class MergeSkillCandidateRequest(BaseModel):
    target_skill_id: str = Field(alias="targetSkillId")
    auto_bind_source_agent: bool = True

    model_config = {"populate_by_name": True}


class RejectSkillCandidateRequest(BaseModel):
    note: Optional[str] = None


@router.get("", response_model=List[SkillCandidateResponse])
async def list_skill_candidates(
    status_filter: str = Query("all", alias="status"),
    query: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    agent_id: Optional[str] = Query(None, alias="agent_id"),
    current_user: CurrentUser = Depends(get_current_user),
):
    if agent_id:
        _require_agent_read_access_sync(agent_id, current_user)
        agent_ids = [str(agent_id)]
    else:
        agent_ids = _list_owned_agent_ids_sync(current_user.user_id)
    rows = get_skill_candidate_service().list_candidates(
        agent_ids=agent_ids,
        status=status_filter,
        limit=limit,
        query_text=query,
    )
    return [SkillCandidateResponse.from_info(row) for row in rows]


@router.get("/{candidate_id}", response_model=SkillCandidateResponse)
async def get_skill_candidate(
    candidate_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    row = get_skill_candidate_service().get_candidate(candidate_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    _require_agent_read_access_sync(row.source_agent_id, current_user)
    return SkillCandidateResponse.from_info(row)


@router.post("/{candidate_id}/promote", response_model=SkillCandidateResponse)
async def promote_skill_candidate(
    candidate_id: int,
    payload: PromoteSkillCandidateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    existing = get_skill_candidate_service().get_candidate(candidate_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    _require_candidate_manage_access(existing.source_agent_id, current_user)
    try:
        row = get_skill_candidate_service().promote_candidate(
            candidate_id=candidate_id,
            reviewer_user_id=str(current_user.user_id),
            auto_bind_source_agent=payload.auto_bind_source_agent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    return SkillCandidateResponse.from_info(row)


@router.post("/{candidate_id}/merge", response_model=SkillCandidateResponse)
async def merge_skill_candidate(
    candidate_id: int,
    payload: MergeSkillCandidateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    existing = get_skill_candidate_service().get_candidate(candidate_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    _require_candidate_manage_access(existing.source_agent_id, current_user)

    try:
        row = get_skill_candidate_service().promote_candidate(
            candidate_id=candidate_id,
            reviewer_user_id=str(current_user.user_id),
            target_skill_id=payload.target_skill_id,
            auto_bind_source_agent=payload.auto_bind_source_agent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    return SkillCandidateResponse.from_info(row)


@router.post("/{candidate_id}/reject", response_model=SkillCandidateResponse)
async def reject_skill_candidate(
    candidate_id: int,
    payload: RejectSkillCandidateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    existing = get_skill_candidate_service().get_candidate(candidate_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    _require_candidate_manage_access(existing.source_agent_id, current_user)

    row = get_skill_candidate_service().reject_candidate(
        candidate_id=candidate_id,
        review_note=payload.note,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    return SkillCandidateResponse.from_info(row)


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill_candidate(
    candidate_id: int,
    current_user: CurrentUser = Depends(get_current_user),
):
    existing = get_skill_candidate_service().get_candidate(candidate_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill candidate not found")
    _require_candidate_manage_access(existing.source_agent_id, current_user)
    get_skill_candidate_service().delete_candidate(candidate_id=candidate_id)
    return None
