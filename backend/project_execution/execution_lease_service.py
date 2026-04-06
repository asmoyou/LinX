from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence
from uuid import UUID

from database.project_execution_models import ExecutionLease, ExecutionNode, ProjectRun, ProjectRunStep
from shared.platform_settings import get_project_execution_settings
from project_execution.run_workspace_manager import get_run_workspace_manager
from shared.logging import get_logger

logger = get_logger(__name__)


DEFAULT_LEASE_MINUTES = 30


def select_execution_node(*, session, project_id: UUID, required_capabilities: Sequence[str]) -> Optional[ExecutionNode]:
    candidates = (
            session.query(ExecutionNode)
            .filter(ExecutionNode.project_id == project_id)
            .filter(ExecutionNode.status.in_(["online", "available", "idle", "working"]))
            .order_by(ExecutionNode.last_seen_at.desc().nullslast(), ExecutionNode.created_at.asc())
            .all()
        )
    if not candidates:
        return None
    required = set(required_capabilities or [])
    if not required:
        return candidates[0]
    best = None
    best_score = -1
    for node in candidates:
        score = len(required & set(node.capabilities or []))
        if score > best_score:
            best = node
            best_score = score
    return best or candidates[0]


def create_execution_lease(*, session, project_id: UUID, node_id: UUID, run_id: UUID, run_step_id: UUID, extra_payload: Optional[dict] = None) -> ExecutionLease:
    workspace_manager = get_run_workspace_manager()
    run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()
    step = session.query(ProjectRunStep).filter(ProjectRunStep.run_step_id == run_step_id).first()
    if run is None or step is None:
        raise RuntimeError("Run or step not found for execution lease")
    descriptor = workspace_manager.create_run_workspace(project_id, run_id)
    lease = ExecutionLease(
            project_id=project_id,
            node_id=node_id,
            run_id=run_id,
            run_step_id=run_step_id,
            status="pending",
            lease_payload={
                "project_id": str(project_id),
                "run_id": str(run_id),
                "run_step_id": str(run_step_id),
                "workspace_root": str(descriptor.run_workspace_root),
                "project_space_root": str(descriptor.project_space_root),
                "sandbox_mode": descriptor.sandbox_mode,
                "external_agent_command_template": resolve_external_agent_command_template(session=session, project_id=project_id, node=session.query(ExecutionNode).filter(ExecutionNode.node_id == node_id).first()),
                "step": {
                    "name": step.name,
                    "input_payload": step.input_payload or {},
                },
                **(extra_payload or {}),
            },
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_LEASE_MINUTES),
        )
    session.add(lease)
    session.flush()
    session.refresh(lease)
    logger.info(
        "Created execution lease",
        extra={"lease_id": str(lease.lease_id), "node_id": str(node_id), "run_step_id": str(run_step_id)},
    )
    return lease



def resolve_external_agent_command_template(*, session, project_id: UUID, node: Optional[ExecutionNode]) -> str:
    node_config = dict(node.config or {}) if node is not None and isinstance(node.config, dict) else {}
    if str(node_config.get("external_agent_command_template") or "").strip():
        return str(node_config.get("external_agent_command_template")).strip()

    run_project = session.query(ProjectRun).filter(ProjectRun.project_id == project_id).first()
    del run_project
    # project-level override lives in projects.configuration
    from database.project_execution_models import Project

    project = session.query(Project).filter(Project.project_id == project_id).first()
    project_config = dict(project.configuration or {}) if project and isinstance(project.configuration, dict) else {}
    if str(project_config.get("external_agent_command_template") or "").strip():
        return str(project_config.get("external_agent_command_template")).strip()

    platform_settings = get_project_execution_settings(session)
    if str(platform_settings.get("external_agent_command_template") or "").strip():
        return str(platform_settings.get("external_agent_command_template")).strip()

    return str(__import__("os").environ.get("LINX_EXTERNAL_AGENT_COMMAND", "")).strip()
