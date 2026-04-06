from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.project_execution_models import AgentRuntimeBinding
from project_execution.service import flush_and_refresh


def ensure_agent_runtime_binding(
    session: Session,
    *,
    agent_id: UUID,
    runtime_type: str,
    execution_node_id: Optional[UUID] = None,
    workspace_strategy: Optional[str] = None,
    path_allowlist: Optional[list[str]] = None,
    config: Optional[dict] = None,
) -> AgentRuntimeBinding:
    existing = (
        session.query(AgentRuntimeBinding)
        .filter(AgentRuntimeBinding.agent_id == agent_id)
        .filter(AgentRuntimeBinding.runtime_type == runtime_type)
        .filter(AgentRuntimeBinding.status == "active")
        .order_by(AgentRuntimeBinding.updated_at.desc())
        .first()
    )
    if existing is not None:
        existing.execution_node_id = execution_node_id
        existing.workspace_strategy = workspace_strategy or existing.workspace_strategy
        existing.path_allowlist = path_allowlist or existing.path_allowlist or []
        existing.config = {**(existing.config or {}), **(config or {})}
        return flush_and_refresh(session, existing)

    binding = AgentRuntimeBinding(
        agent_id=agent_id,
        runtime_type=runtime_type,
        execution_node_id=execution_node_id,
        workspace_strategy=workspace_strategy,
        path_allowlist=path_allowlist or [],
        status="active",
        config=config or {},
    )
    session.add(binding)
    return flush_and_refresh(session, binding)
