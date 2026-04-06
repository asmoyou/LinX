from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.project_execution_models import ExternalAgentSession
from project_execution.service import flush_and_refresh


def create_external_agent_session(
    session: Session,
    *,
    agent_id: UUID,
    execution_node_id: UUID,
    project_id: UUID,
    run_id: UUID,
    run_step_id: UUID,
    runtime_type: str,
    workdir: Optional[str],
    lease_id: Optional[UUID] = None,
    session_metadata: Optional[dict] = None,
) -> ExternalAgentSession:
    external_session = ExternalAgentSession(
        agent_id=agent_id,
        execution_node_id=execution_node_id,
        project_id=project_id,
        run_id=run_id,
        run_step_id=run_step_id,
        runtime_type=runtime_type,
        workdir=workdir,
        status="pending",
        lease_id=lease_id,
        session_metadata=session_metadata or {},
    )
    session.add(external_session)
    return flush_and_refresh(session, external_session)
