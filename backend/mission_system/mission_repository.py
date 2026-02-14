"""Mission Repository.

CRUD operations for Mission and related models (MissionAttachment,
MissionAgent, MissionEvent) using the shared ``get_db_session()`` pattern.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import desc
from sqlalchemy.orm import joinedload

from database.connection import get_db_session
from database.mission_models import (
    Mission,
    MissionAgent,
    MissionAttachment,
    MissionEvent,
    MissionSettings,
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Mission CRUD
# ------------------------------------------------------------------


def create_mission(
    title: str,
    instructions: str,
    created_by_user_id: UUID,
    department_id: Optional[UUID] = None,
    requirements_doc: Optional[str] = None,
    mission_config: Optional[Dict[str, Any]] = None,
) -> Mission:
    """Create a new mission in draft status."""
    with get_db_session() as session:
        mission = Mission(
            mission_id=uuid4(),
            title=title,
            instructions=instructions,
            created_by_user_id=created_by_user_id,
            department_id=department_id,
            requirements_doc=requirements_doc,
            mission_config=mission_config or {},
            status="draft",
        )
        session.add(mission)
        session.flush()
        session.refresh(mission)
        # Detach so caller can use outside the session
        session.expunge(mission)
        return mission


def get_mission(mission_id: UUID) -> Optional[Mission]:
    """Fetch a mission by ID, eager-loading relationships."""
    with get_db_session() as session:
        mission = (
            session.query(Mission)
            .options(
                joinedload(Mission.attachments),
                joinedload(Mission.agents),
            )
            .filter(Mission.mission_id == mission_id)
            .first()
        )
        if mission:
            session.expunge(mission)
        return mission


def update_mission_status(
    mission_id: UUID,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    """Update a mission's lifecycle status."""
    with get_db_session() as session:
        mission = session.query(Mission).filter(Mission.mission_id == mission_id).first()
        if mission is None:
            raise ValueError(f"Mission {mission_id} not found")
        mission.status = status
        if error_message is not None:
            mission.error_message = error_message
        if status == "executing" and mission.started_at is None:
            mission.started_at = datetime.utcnow()
        if status in ("completed", "failed", "cancelled"):
            mission.completed_at = datetime.utcnow()


def update_mission_fields(mission_id: UUID, **fields: Any) -> None:
    """Update arbitrary columns on a mission."""
    with get_db_session() as session:
        mission = session.query(Mission).filter(Mission.mission_id == mission_id).first()
        if mission is None:
            raise ValueError(f"Mission {mission_id} not found")
        for key, value in fields.items():
            setattr(mission, key, value)


def list_missions(
    user_id: Optional[UUID] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Mission]:
    """List missions with optional filters."""
    with get_db_session() as session:
        query = session.query(Mission)
        if user_id is not None:
            query = query.filter(Mission.created_by_user_id == user_id)
        if status is not None:
            query = query.filter(Mission.status == status)
        missions = (
            query.order_by(desc(Mission.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
        for m in missions:
            session.expunge(m)
        return missions


def count_missions(
    user_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> int:
    """Count missions with optional filters."""
    with get_db_session() as session:
        query = session.query(Mission)
        if user_id is not None:
            query = query.filter(Mission.created_by_user_id == user_id)
        if status is not None:
            query = query.filter(Mission.status == status)
        return query.count()


# ------------------------------------------------------------------
# Attachment helpers
# ------------------------------------------------------------------


def add_attachment(
    mission_id: UUID,
    filename: str,
    file_reference: str,
    content_type: Optional[str] = None,
    file_size: Optional[int] = None,
) -> MissionAttachment:
    """Add a file attachment to a mission."""
    with get_db_session() as session:
        att = MissionAttachment(
            attachment_id=uuid4(),
            mission_id=mission_id,
            filename=filename,
            file_reference=file_reference,
            content_type=content_type,
            file_size=file_size,
        )
        session.add(att)
        session.flush()
        session.expunge(att)
        return att


def list_attachments(mission_id: UUID) -> List[MissionAttachment]:
    """List all attachments for a mission."""
    with get_db_session() as session:
        atts = (
            session.query(MissionAttachment)
            .filter(MissionAttachment.mission_id == mission_id)
            .all()
        )
        for a in atts:
            session.expunge(a)
        return atts


# ------------------------------------------------------------------
# Agent assignment helpers
# ------------------------------------------------------------------


def assign_agent(
    mission_id: UUID,
    agent_id: UUID,
    role: str,
    is_temporary: bool = False,
) -> MissionAgent:
    """Assign an agent to a mission with a given role."""
    with get_db_session() as session:
        ma = MissionAgent(
            id=uuid4(),
            mission_id=mission_id,
            agent_id=agent_id,
            role=role,
            is_temporary=is_temporary,
        )
        session.add(ma)
        session.flush()
        session.expunge(ma)
        return ma


def update_agent_status(
    mission_id: UUID,
    agent_id: UUID,
    status: str,
) -> None:
    """Update the status of an assigned agent."""
    with get_db_session() as session:
        ma = (
            session.query(MissionAgent)
            .filter(
                MissionAgent.mission_id == mission_id,
                MissionAgent.agent_id == agent_id,
            )
            .first()
        )
        if ma:
            ma.status = status


def list_mission_agents(mission_id: UUID) -> List[MissionAgent]:
    """List all agents assigned to a mission."""
    with get_db_session() as session:
        agents = (
            session.query(MissionAgent)
            .filter(MissionAgent.mission_id == mission_id)
            .all()
        )
        for a in agents:
            session.expunge(a)
        return agents


# ------------------------------------------------------------------
# Event helpers
# ------------------------------------------------------------------


def list_events(
    mission_id: UUID,
    event_type: Optional[str] = None,
    limit: int = 100,
) -> List[MissionEvent]:
    """List events for a mission, newest first."""
    with get_db_session() as session:
        query = (
            session.query(MissionEvent)
            .filter(MissionEvent.mission_id == mission_id)
        )
        if event_type:
            query = query.filter(MissionEvent.event_type == event_type)
        events = (
            query.order_by(desc(MissionEvent.created_at))
            .limit(limit)
            .all()
        )
        for e in events:
            session.expunge(e)
        return events


# ------------------------------------------------------------------
# Mission Settings helpers
# ------------------------------------------------------------------

DEFAULT_LEADER_CONFIG = {
    "llm_provider": "ollama",
    "llm_model": "qwen2.5:14b",
    "temperature": 0.3,
    "max_tokens": 4096,
}

DEFAULT_SUPERVISOR_CONFIG = {
    "llm_provider": "ollama",
    "llm_model": "qwen2.5:14b",
    "temperature": 0.2,
    "max_tokens": 4096,
}

DEFAULT_QA_CONFIG = {
    "llm_provider": "ollama",
    "llm_model": "qwen2.5:14b",
    "temperature": 0.1,
    "max_tokens": 4096,
}

DEFAULT_EXECUTION_CONFIG = {
    "max_retries": 3,
    "task_timeout_s": 600,
    "max_rework_cycles": 2,
    "network_access": False,
    "max_concurrent_tasks": 3,
}


def get_mission_settings(user_id: UUID) -> Optional[Dict[str, Any]]:
    """Get mission settings for a user, returning defaults if not found."""
    with get_db_session() as session:
        settings = (
            session.query(MissionSettings)
            .filter(MissionSettings.user_id == user_id)
            .first()
        )
        if settings:
            result = {
                "leader_config": {**DEFAULT_LEADER_CONFIG, **(settings.leader_config or {})},
                "supervisor_config": {
                    **DEFAULT_SUPERVISOR_CONFIG,
                    **(settings.supervisor_config or {}),
                },
                "qa_config": {**DEFAULT_QA_CONFIG, **(settings.qa_config or {})},
                "execution_config": {
                    **DEFAULT_EXECUTION_CONFIG,
                    **(settings.execution_config or {}),
                },
            }
            return result
    return {
        "leader_config": DEFAULT_LEADER_CONFIG.copy(),
        "supervisor_config": DEFAULT_SUPERVISOR_CONFIG.copy(),
        "qa_config": DEFAULT_QA_CONFIG.copy(),
        "execution_config": DEFAULT_EXECUTION_CONFIG.copy(),
    }


def upsert_mission_settings(user_id: UUID, data: Dict[str, Any]) -> Dict[str, Any]:
    """Create or update mission settings for a user."""
    with get_db_session() as session:
        settings = (
            session.query(MissionSettings)
            .filter(MissionSettings.user_id == user_id)
            .first()
        )
        if settings is None:
            settings = MissionSettings(
                id=uuid4(),
                user_id=user_id,
            )
            session.add(settings)

        if "leader_config" in data:
            settings.leader_config = data["leader_config"]
        if "supervisor_config" in data:
            settings.supervisor_config = data["supervisor_config"]
        if "qa_config" in data:
            settings.qa_config = data["qa_config"]
        if "execution_config" in data:
            settings.execution_config = data["execution_config"]

        session.flush()

    return get_mission_settings(user_id)
