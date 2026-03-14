"""Dedicated skill-proposal endpoints for the reset architecture."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from access_control.permissions import CurrentUser, get_current_user
from skill_learning.service import get_skill_proposal_service

from .memory_access import (
    _agent_owned_by_user_sync,
    _is_admin_or_manager,
    _list_owned_agent_ids_sync,
    _lookup_agent_name,
    _memory_item_to_response,
    _require_agent_read_access_sync,
)
from .memory_contracts import AgentCandidateReviewRequest, MemoryItemResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def _proposal_review_status(row_status: str, payload: Dict[str, Any]) -> str:
    normalized = str(payload.get("review_status") or "").strip().lower()
    if normalized in {"pending", "published", "rejected"}:
        return normalized
    if row_status == "active":
        return "published"
    if row_status == "rejected":
        return "rejected"
    return "pending"


def _build_skill_proposal_content(row: Any) -> str:
    payload = row.proposal_payload if isinstance(row.proposal_payload, dict) else {}
    goal = str(payload.get("goal") or row.title or "").strip()
    steps = [
        str(step).strip() for step in payload.get("successful_path") or [] if str(step).strip()
    ]
    why_it_worked = str(payload.get("why_it_worked") or row.summary or "").strip()
    applicability = str(payload.get("applicability") or "").strip()
    avoid = str(payload.get("avoid") or "").strip()

    if not goal:
        return ""

    lines = [f"skill.proposal.goal={goal}"]
    if steps:
        lines.append(f"skill.proposal.successful_path={' | '.join(steps)}")
    if why_it_worked:
        lines.append(f"skill.proposal.why_it_worked={why_it_worked}")
    if applicability:
        lines.append(f"skill.proposal.applicability={applicability}")
    if avoid:
        lines.append(f"skill.proposal.avoid={avoid}")
    return "\n".join(lines)


def _skill_proposal_row_to_response(row: Any) -> Dict[str, Any]:
    from database.connection import get_db_session

    payload = dict(row.proposal_payload or {}) if isinstance(row.proposal_payload, dict) else {}
    agent_id = str(row.owner_id) if str(row.owner_type or "") == "agent" else None
    review_status = _proposal_review_status(str(row.status or ""), payload)
    content = _build_skill_proposal_content(row) or str(row.summary or row.title or "").strip()
    created_at = row.updated_at or row.created_at or datetime.now(timezone.utc)
    metadata = {
        **payload,
        "signal_type": "skill_proposal",
        "proposal_id": int(row.id),
        "proposal_key": str(getattr(row, "proposal_key", None) or ""),
        "review_status": review_status,
        "status": str(row.status or ""),
        "agent_id": agent_id,
        "published_skill_id": str(getattr(row, "published_skill_id", None) or "") or None,
    }

    agent_name = None
    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, agent_id)

    return {
        "id": str(row.id),
        "type": "skill_proposal",
        "content": content,
        "summary": str(row.summary or "") or None,
        "agentId": agent_id,
        "agentName": agent_name,
        "userId": None,
        "userName": None,
        "createdAt": created_at.isoformat(),
        "tags": [],
        "relevanceScore": None,
        "metadata": metadata,
        "isShared": False,
        "sharedWith": [],
        "sharedWithNames": [],
        "indexStatus": None,
        "indexError": None,
    }


def _load_skill_proposal_rows(
    *,
    current_user: CurrentUser,
    agent_id: Optional[str],
    review_status: str,
    limit: int,
) -> List[Any]:
    normalized_review_status = str(review_status or "pending").strip().lower()
    if agent_id:
        _require_agent_read_access_sync(agent_id, current_user)
        agent_ids = [str(agent_id)]
    else:
        agent_ids = _list_owned_agent_ids_sync(current_user.user_id)

    if not agent_ids:
        return []
    return get_skill_proposal_service().list_proposals(
        agent_ids=agent_ids,
        review_status=normalized_review_status,
        limit=limit,
    )


def _require_skill_proposal_manage_access(agent_id: str, current_user: CurrentUser) -> None:
    _require_agent_read_access_sync(agent_id, current_user)
    if _is_admin_or_manager(current_user):
        return
    if _agent_owned_by_user_sync(agent_id, current_user.user_id):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to modify this skill proposal",
    )


def _merge_review_payload(
    payload: Dict[str, Any], request: AgentCandidateReviewRequest
) -> Dict[str, Any]:
    updated = dict(payload)
    if request.note is not None:
        updated["review_note"] = request.note
    if request.summary is not None:
        updated["why_it_worked"] = request.summary
    if request.content is not None:
        updated["review_content"] = request.content
    if request.metadata and isinstance(request.metadata, dict):
        updated.update(request.metadata)
    return updated


@router.get("", response_model=List[MemoryItemResponse])
async def list_skill_proposals(
    agent_id: Optional[str] = Query(None),
    review_status: str = Query("pending", pattern=r"^(pending|published|rejected|all)$"),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List skill proposals generated from successful agent execution paths."""
    try:
        results = await asyncio.to_thread(
            _load_skill_proposal_rows,
            current_user=current_user,
            agent_id=agent_id,
            review_status=review_status,
            limit=limit,
        )
    except Exception as exc:
        logger.error("Failed to list skill proposals: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list skill proposals: {exc}",
        ) from exc

    return [MemoryItemResponse(**_skill_proposal_row_to_response(item)) for item in results]


@router.post("/{memory_id}/review", response_model=MemoryItemResponse)
async def review_skill_proposal(
    memory_id: int,
    request: AgentCandidateReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Approve or reject a learned skill proposal."""
    service = get_skill_proposal_service()
    existing = await asyncio.to_thread(service.get_proposal, memory_id)
    if existing is None or not str(getattr(existing, "agent_id", "") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill proposal not found",
        )
    agent_id = str(existing.owner_id or "").strip()
    await asyncio.to_thread(_require_skill_proposal_manage_access, agent_id, current_user)

    try:
        payload = _merge_review_payload(
            (
                dict(existing.proposal_payload or {})
                if isinstance(existing.proposal_payload, dict)
                else {}
            ),
            request,
        )
        updated = await asyncio.to_thread(
            service.review_proposal,
            proposal_id=int(existing.id),
            action=str(request.action or ""),
            reviewer_user_id=str(current_user.user_id),
            summary=request.summary if request.summary is not None else None,
            details=request.content if request.content is not None else None,
            payload_updates=payload,
        )
    except Exception as exc:
        logger.error("Failed to review skill proposal: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to review skill proposal: {exc}",
        ) from exc

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Skill proposal not found",
        )

    return MemoryItemResponse(**_skill_proposal_row_to_response(updated))


@router.post("/{memory_id}/publish", response_model=MemoryItemResponse)
async def publish_skill_proposal(
    memory_id: int,
    request: AgentCandidateReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Publish a reviewed skill proposal into the skill registry."""
    request.action = "publish"
    return await review_skill_proposal(
        memory_id=memory_id,
        request=request,
        current_user=current_user,
    )
