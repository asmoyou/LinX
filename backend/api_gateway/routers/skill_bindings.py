"""Skill binding endpoints mounted under /skills/bindings."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from access_control.permissions import CurrentUser, get_current_user
from access_control.skill_access import build_skill_access_context
from agent_framework.agent_registry import get_agent_registry
from database.connection import get_db_session
from database.models import Agent, AgentSkillBinding, Department, Skill
from skill_library.canonical_service import get_canonical_skill_service
from skill_library.skill_registry import get_skill_registry

router = APIRouter(tags=["skill-bindings"])


def _owned_agent_or_403(agent_id: str, current_user: CurrentUser):
    try:
        agent_uuid = UUID(str(agent_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent id: {agent_id}",
        ) from exc

    agent = get_agent_registry().get_agent(agent_uuid)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if str(agent.owner_user_id) != str(current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this agent",
        )
    return agent, agent_uuid


def _skill_summary_payload(skill: Any) -> Dict[str, Any]:
    return {
        "skill_id": str(skill.skill_id),
        "skill_slug": str(skill.skill_slug or ""),
        "display_name": str(skill.display_name or ""),
        "description": str(skill.description or ""),
        "skill_type": str(skill.skill_type or ""),
        "artifact_kind": str(getattr(skill, "artifact_kind", "") or "") or None,
        "runtime_mode": str(getattr(skill, "runtime_mode", "") or "") or None,
        "active_revision_id": (
            str(getattr(skill, "active_revision_id", None))
            if getattr(skill, "active_revision_id", None)
            else None
        ),
        "version": str(skill.version or "1.0.0"),
        "access_level": str(getattr(skill, "access_level", "private") or "private"),
        "department_id": (
            str(getattr(skill, "department_id", None)) if getattr(skill, "department_id", None) else None
        ),
        "department_name": getattr(skill, "department_name", None),
    }


class SkillBindingResponse(BaseModel):
    binding_id: str
    owner_id: str
    owner_name: str
    owner_type: str = "agent"
    skill_id: str
    skill_slug: str
    display_name: str
    skill_type: Optional[str] = None
    artifact_kind: Optional[str] = None
    runtime_mode: Optional[str] = None
    binding_mode: Optional[str] = None
    enabled: bool = True
    priority: int = 0
    source: Optional[str] = None
    auto_update_policy: Optional[str] = None
    revision_pin_id: Optional[str] = None
    access_level: Optional[str] = None
    department_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class AgentSkillBindingPayload(BaseModel):
    skill_id: str
    binding_mode: str = Field(default="doc")
    enabled: bool = True
    priority: int = 0
    source: str = "manual"
    auto_update_policy: str = "follow_active"
    revision_pin_id: Optional[str] = None


class AgentSkillBindingsResponse(BaseModel):
    owner_id: str
    owner_type: str = "agent"
    bindings: List[AgentSkillBindingPayload] = Field(default_factory=list)
    available_skills: List[Dict[str, Any]] = Field(default_factory=list)


class UpdateAgentSkillBindingsRequest(BaseModel):
    bindings: List[AgentSkillBindingPayload] = Field(default_factory=list)


@router.get("", response_model=List[SkillBindingResponse])
async def list_skill_bindings(
    owner_type: str = Query("agent"),
    owner_id: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
):
    if owner_type != "agent":
        return []

    with get_db_session() as session:
        query = (
            session.query(AgentSkillBinding, Agent, Skill, Department)
            .join(Agent, Agent.agent_id == AgentSkillBinding.agent_id)
            .join(Skill, Skill.skill_id == AgentSkillBinding.skill_id)
            .outerjoin(Department, Department.department_id == Skill.department_id)
            .filter(Agent.owner_user_id == UUID(str(current_user.user_id)))
            .filter(AgentSkillBinding.enabled.is_(True))
            .order_by(Agent.name.asc(), AgentSkillBinding.priority.asc(), Skill.display_name.asc())
        )
        if owner_id:
            try:
                owner_uuid = UUID(str(owner_id))
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid owner_id: {owner_id}",
                ) from exc
            query = query.filter(AgentSkillBinding.agent_id == owner_uuid)
        rows = query.limit(limit).all()

    return [
        SkillBindingResponse(
            binding_id=str(binding.binding_id),
            owner_id=str(agent.agent_id),
            owner_name=str(agent.name or "Unknown owner"),
            owner_type="agent",
            skill_id=str(skill.skill_id),
            skill_slug=str(skill.skill_slug or ""),
            display_name=str(skill.display_name or ""),
            skill_type=str(skill.skill_type or "") or None,
            artifact_kind=str(skill.artifact_kind or "") or None,
            runtime_mode=str(skill.runtime_mode or "") or None,
            binding_mode=str(binding.binding_mode or "doc"),
            enabled=bool(binding.enabled),
            priority=int(binding.priority or 0),
            source=str(binding.source or "manual"),
            auto_update_policy=str(binding.auto_update_policy or "follow_active"),
            revision_pin_id=str(binding.revision_pin_id) if binding.revision_pin_id else None,
            access_level=str(skill.access_level or "private") if skill.access_level else None,
            department_name=getattr(department, "name", None),
            created_at=(
                binding.created_at.isoformat() if getattr(binding.created_at, "isoformat", None) else None
            ),
            updated_at=(
                binding.updated_at.isoformat() if getattr(binding.updated_at, "isoformat", None) else None
            ),
        )
        for binding, agent, skill, department in rows
    ]


@router.get("/agents/{agent_id}", response_model=AgentSkillBindingsResponse)
async def get_agent_skill_bindings(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    agent, agent_uuid = _owned_agent_or_403(agent_id, current_user)
    access_context = build_skill_access_context(current_user)
    available_skills = get_skill_registry().list_visible_skills(
        access_context=access_context,
        limit=1000,
        offset=0,
    )
    configured_bindings = [
        AgentSkillBindingPayload(
            skill_id=str(binding.skill_id),
            binding_mode=str(binding.binding_mode or "doc"),
            enabled=bool(binding.enabled),
            priority=int(binding.priority or 0),
            source=str(binding.source or "manual"),
            auto_update_policy=str(binding.auto_update_policy or "follow_active"),
            revision_pin_id=(
                str(binding.revision_pin_id) if getattr(binding, "revision_pin_id", None) else None
            ),
        )
        for binding in get_canonical_skill_service().list_bindings(agent_id=agent_uuid)
    ]
    return AgentSkillBindingsResponse(
        owner_id=str(agent.agent_id),
        owner_type="agent",
        bindings=configured_bindings,
        available_skills=[_skill_summary_payload(skill) for skill in available_skills if skill.is_active],
    )


@router.put("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_agent_skill_bindings(
    agent_id: str,
    payload: UpdateAgentSkillBindingsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    _, agent_uuid = _owned_agent_or_403(agent_id, current_user)
    access_context = build_skill_access_context(current_user)
    get_canonical_skill_service().replace_bindings(
        agent_id=agent_uuid,
        bindings=[
            {
                "skill_id": binding.skill_id,
                "binding_mode": binding.binding_mode,
                "enabled": binding.enabled,
                "priority": binding.priority,
                "source": binding.source,
                "auto_update_policy": binding.auto_update_policy,
                "revision_pin_id": binding.revision_pin_id,
            }
            for binding in payload.bindings
        ],
        access_context=access_context,
    )
    from .agents import invalidate_agent_cache

    invalidate_agent_cache(agent_id)
    return None
