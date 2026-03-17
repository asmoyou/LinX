"""Shared access-control and response helpers for reset-era memory routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import HTTPException, status

from access_control.permissions import CurrentUser


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(raw_value: Optional[str]) -> Optional[UUID]:
    if not raw_value:
        return None
    try:
        return UUID(str(raw_value))
    except Exception:
        return None


def _is_admin_or_manager(current_user: CurrentUser) -> bool:
    return str(current_user.role).strip().lower() in {"admin", "manager"}


def _list_owned_agent_ids_sync(user_id: Optional[str]) -> List[str]:
    """Resolve all agent ids owned by a user."""

    if not user_id:
        return []
    try:
        parsed_user_id = UUID(str(user_id))
    except (TypeError, ValueError):
        return []

    from agent_framework.agent_registry import get_agent_registry

    try:
        agents = get_agent_registry().list_agents(owner_user_id=parsed_user_id)
    except Exception:
        return []
    return [str(agent.agent_id) for agent in agents if getattr(agent, "agent_id", None)]


def _lookup_agent_name(session, agent_id: Optional[str]) -> Optional[str]:
    """Look up agent name by ID."""
    if not agent_id:
        return None

    from database.models import Agent

    agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
    return agent.name if agent else None


def _lookup_user_name(session, user_id: Optional[str]) -> Optional[str]:
    """Look up user display name by ID."""
    if not user_id:
        return None

    from database.models import User

    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return None
    attrs = user.attributes or {}
    return attrs.get("display_name") or user.username


def _normalize_visibility(memory_type: str, metadata: Dict[str, Any]) -> str:
    configured = str(metadata.get("visibility") or "").strip().lower()
    if configured:
        return configured
    if memory_type == "user_memory":
        return "private"
    if memory_type == "skill_proposal":
        return "private"
    return "private"


def _normalized_summary(
    *,
    summary: Optional[str],
    content: str,
) -> Optional[str]:
    summary_text = str(summary or "").strip()
    if not summary_text:
        return None
    content_text = str(content or "").strip()
    if summary_text == content_text:
        return None
    return summary_text


def _memory_item_to_response(
    item: Any,
    agent_name: Optional[str] = None,
    user_name: Optional[str] = None,
    shared_with_names: Optional[List[str]] = None,
) -> dict:
    """Convert a retrieved memory item to an API response dict."""

    metadata = dict(getattr(item, "metadata", None) or {})
    tags = metadata.pop("tags", [])
    summary = getattr(item, "summary", None) or metadata.pop("summary", None)
    shared_with = metadata.get("shared_with", [])
    stored_shared_names = metadata.get("shared_with_names", [])
    shared_from = metadata.get("shared_from", None)
    index_status = metadata.pop("vector_status", None)
    index_error = metadata.pop("vector_error", None)
    memory_type = str(getattr(item, "memory_type", None) or metadata.get("memory_type") or "")
    memory_type = memory_type.strip() or "user_memory"

    if not isinstance(shared_with, list):
        shared_with = []
    if shared_with_names is not None:
        final_shared_names = shared_with_names
    elif isinstance(stored_shared_names, list):
        final_shared_names = stored_shared_names
    else:
        final_shared_names = []

    visibility = _normalize_visibility(memory_type, metadata)
    metadata["visibility"] = visibility
    metadata.setdefault("record_type", str(metadata.get("record_type") or memory_type))
    metadata.setdefault("memory_type", memory_type)
    metadata = {key: value for key, value in metadata.items() if not str(key).startswith("_")}

    shared_with_user_ids = metadata.get("shared_with_user_ids", [])
    if not isinstance(shared_with_user_ids, list):
        shared_with_user_ids = []

    timestamp = getattr(item, "timestamp", None)
    created_at = (
        timestamp.isoformat() if isinstance(timestamp, datetime) else _utc_now().isoformat()
    )

    return {
        "id": str(getattr(item, "id", "") or ""),
        "type": memory_type,
        "content": str(getattr(item, "content", "") or ""),
        "summary": _normalized_summary(
            summary=summary,
            content=str(getattr(item, "content", "") or ""),
        ),
        "agentId": getattr(item, "agent_id", None),
        "agentName": agent_name,
        "userId": getattr(item, "user_id", None),
        "userName": user_name,
        "createdAt": created_at,
        "tags": tags if isinstance(tags, list) else [],
        "relevanceScore": getattr(item, "similarity_score", None),
        "metadata": metadata if metadata else None,
        "isShared": bool(shared_from) or bool(shared_with) or bool(shared_with_user_ids),
        "sharedWith": shared_with,
        "sharedWithNames": final_shared_names,
        "indexStatus": index_status,
        "indexError": index_error,
    }


def _agent_owned_by_user_sync(agent_id: Optional[str], user_id: str) -> bool:
    from database.connection import get_db_session
    from database.models import Agent

    parsed_agent_id = _parse_uuid(agent_id)
    if parsed_agent_id is None:
        return False

    with get_db_session() as session:
        row = session.query(Agent.owner_user_id).filter(Agent.agent_id == parsed_agent_id).first()
    return bool(row and str(row[0]) == str(user_id))


def _require_user_memory_read_access_sync(user_id: str, current_user: CurrentUser) -> None:
    """Ensure current user can inspect the requested user-memory scope."""

    if str(user_id) == str(current_user.user_id):
        return
    if _is_admin_or_manager(current_user):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to access this user memory",
    )


def _require_agent_read_access_sync(agent_id: str, current_user: CurrentUser) -> None:
    """Ensure current user can read this agent's skill-learning surface."""

    from access_control.memory_filter import can_access_skill_learning
    from access_control.rbac import Action
    from database.connection import get_db_session
    from database.models import Agent

    try:
        parsed_agent_id = UUID(str(agent_id))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent_id: {agent_id}",
        ) from exc

    with get_db_session() as session:
        agent = session.query(Agent).filter(Agent.agent_id == parsed_agent_id).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    allowed = can_access_skill_learning(
        current_user=current_user,
        agent_id=str(agent.agent_id),
        agent_owner_id=str(agent.owner_user_id),
        action=Action.READ,
    )
    if allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to access this agent's skill learning data",
    )
