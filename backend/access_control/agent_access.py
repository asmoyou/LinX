"""Agent visibility and execution access helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Optional, Sequence
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Query, joinedload

from access_control.permissions import CurrentUser
from database.connection import get_db_session
from database.models import Agent, Department, User

AGENT_ACCESS_PRIVATE = "private"
AGENT_ACCESS_DEPARTMENT = "department"
AGENT_ACCESS_PUBLIC = "public"
AGENT_ACCESS_LEGACY_TEAM = "team"

AgentAccessType = Literal["read", "execute", "manage"]


def _normalize_uuid_str(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        return None


def normalize_agent_access_level(raw_value: object) -> str:
    normalized = str(raw_value or AGENT_ACCESS_PRIVATE).strip().lower()
    if normalized == AGENT_ACCESS_LEGACY_TEAM:
        return AGENT_ACCESS_DEPARTMENT
    if normalized in {AGENT_ACCESS_PRIVATE, AGENT_ACCESS_DEPARTMENT, AGENT_ACCESS_PUBLIC}:
        return normalized
    return AGENT_ACCESS_PRIVATE


def get_department_ancestor_ids(session, department_id: object) -> list[str]:
    """Return one department id plus all ancestors up to the root."""
    current_id = _normalize_uuid_str(department_id)
    if not current_id:
        return []

    ancestor_ids: list[str] = []
    seen: set[str] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        ancestor_ids.append(current_id)
        row = (
            session.query(Department.parent_id)
            .filter(Department.department_id == UUID(current_id))
            .first()
        )
        current_id = _normalize_uuid_str(row[0]) if row else None
    return ancestor_ids


@dataclass(frozen=True)
class AgentAccessContext:
    """Resolved Agent access context for one user."""

    user_id: str
    role: str
    department_id: Optional[str]
    department_ancestor_ids: tuple[str, ...]

    @property
    def is_admin(self) -> bool:
        return str(self.role).strip().lower() == "admin"


def build_agent_access_context_for_user_id(
    session,
    *,
    user_id: str,
    role: str,
) -> AgentAccessContext:
    normalized_user_id = _normalize_uuid_str(user_id)
    user = None
    if normalized_user_id:
        user = session.query(User).filter(User.user_id == UUID(normalized_user_id)).first()

    department_id = _normalize_uuid_str(getattr(user, "department_id", None))
    ancestor_ids = tuple(get_department_ancestor_ids(session, department_id))
    return AgentAccessContext(
        user_id=str(user_id),
        role=str(role or ""),
        department_id=department_id,
        department_ancestor_ids=ancestor_ids,
    )


def build_agent_access_context(current_user: CurrentUser) -> AgentAccessContext:
    with get_db_session() as session:
        return build_agent_access_context_for_user_id(
            session,
            user_id=str(current_user.user_id),
            role=str(current_user.role),
        )


def resolve_agent_owner_department_id(session, owner_user_id: object) -> Optional[str]:
    normalized_owner_id = _normalize_uuid_str(owner_user_id)
    if not normalized_owner_id:
        return None

    row = (
        session.query(User.department_id)
        .filter(User.user_id == UUID(normalized_owner_id))
        .first()
    )
    return _normalize_uuid_str(row[0]) if row else None


def _agent_owner_id(agent: object) -> Optional[str]:
    return _normalize_uuid_str(getattr(agent, "owner_user_id", None))


def _agent_department_id(agent: object) -> Optional[str]:
    return _normalize_uuid_str(getattr(agent, "department_id", None))


def can_read_agent(agent: object, context: AgentAccessContext) -> bool:
    if agent is None:
        return False
    if context.is_admin:
        return True
    if _agent_owner_id(agent) == context.user_id:
        return True

    access_level = normalize_agent_access_level(getattr(agent, "access_level", None))
    if access_level == AGENT_ACCESS_PUBLIC:
        return True
    if access_level == AGENT_ACCESS_DEPARTMENT:
        department_id = _agent_department_id(agent)
        return bool(department_id and department_id in context.department_ancestor_ids)
    return False


def can_execute_agent(agent: object, context: AgentAccessContext) -> bool:
    return can_read_agent(agent, context)


def can_manage_agent(agent: object, context: AgentAccessContext) -> bool:
    if agent is None:
        return False
    return context.is_admin or _agent_owner_id(agent) == context.user_id


def _query_for_agent_access(
    query: Query,
    *,
    context: AgentAccessContext,
    access_type: AgentAccessType = "read",
) -> Query:
    if context.is_admin:
        return query

    try:
        user_uuid = UUID(context.user_id)
    except (TypeError, ValueError):
        return query.filter(false())

    conditions = [Agent.owner_user_id == user_uuid]

    if access_type in {"read", "execute"}:
        conditions.append(Agent.access_level == AGENT_ACCESS_PUBLIC)
        if context.department_ancestor_ids:
            conditions.append(
                and_(
                    Agent.access_level.in_(
                        [AGENT_ACCESS_DEPARTMENT, AGENT_ACCESS_LEGACY_TEAM]
                    ),
                    Agent.department_id.in_([UUID(value) for value in context.department_ancestor_ids]),
                )
            )

    if not conditions:
        return query.filter(false())
    return query.filter(or_(*conditions))


def filter_agent_query(
    query: Query,
    current_user: CurrentUser,
    *,
    access_type: AgentAccessType = "read",
) -> Query:
    with get_db_session() as session:
        context = build_agent_access_context_for_user_id(
            session,
            user_id=str(current_user.user_id),
            role=str(current_user.role),
        )
    return _query_for_agent_access(query, context=context, access_type=access_type)


def list_accessible_agents(
    session,
    current_user: CurrentUser,
    *,
    access_type: AgentAccessType = "read",
    statuses: Optional[Sequence[str]] = None,
    exclude_agent_ids: Optional[Iterable[UUID]] = None,
) -> list[Agent]:
    context = build_agent_access_context_for_user_id(
        session,
        user_id=str(current_user.user_id),
        role=str(current_user.role),
    )
    query = session.query(Agent).options(joinedload(Agent.owner), joinedload(Agent.department))
    query = _query_for_agent_access(query, context=context, access_type=access_type)

    if statuses:
        query = query.filter(Agent.status.in_(list(statuses)))
    if exclude_agent_ids:
        query = query.filter(~Agent.agent_id.in_(list(exclude_agent_ids)))

    return query.order_by(Agent.name.asc(), Agent.created_at.asc()).all()


def load_accessible_agent_or_raise(
    session,
    agent_id: str,
    current_user: CurrentUser,
    *,
    access_type: AgentAccessType = "read",
) -> Agent:
    try:
        agent_uuid = UUID(str(agent_id))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent id: {agent_id}",
        ) from exc

    agent = (
        session.query(Agent)
        .options(joinedload(Agent.owner), joinedload(Agent.department))
        .filter(Agent.agent_id == agent_uuid)
        .first()
    )
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    context = build_agent_access_context_for_user_id(
        session,
        user_id=str(current_user.user_id),
        role=str(current_user.role),
    )
    allowed = (
        can_manage_agent(agent, context)
        if access_type == "manage"
        else can_execute_agent(agent, context)
        if access_type == "execute"
        else can_read_agent(agent, context)
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this agent",
        )

    return agent
