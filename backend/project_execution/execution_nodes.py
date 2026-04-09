from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.project_execution_models import ExecutionNode, ProjectRun

_TERMINAL_NODE_STATUSES = {"completed", "failed", "cancelled", "blocked"}
_PENDING_NODE_STATUSES = {"pending", "queued"}


def _as_payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _as_payload_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def create_execution_node(
    session: Session,
    *,
    run: ProjectRun,
    project_task_id: Optional[UUID],
    name: str,
    node_type: str,
    status: str,
    sequence_number: int,
    node_payload: Optional[dict[str, Any]] = None,
    result_payload: Optional[dict[str, Any]] = None,
    error_message: Optional[str] = None,
    started_at=None,
    completed_at=None,
) -> ExecutionNode:
    payload = _as_payload_dict(node_payload)
    dependency_node_ids = _as_payload_list(payload.get("dependency_node_ids"))
    node = ExecutionNode(
        project_id=run.project_id,
        run_id=run.run_id,
        project_task_id=project_task_id,
        name=name,
        node_type=node_type,
        status=status,
        sequence_number=sequence_number,
        dependency_node_ids=dependency_node_ids,
        node_payload=payload,
        result_payload=_as_payload_dict(result_payload),
        error_message=error_message,
        started_at=started_at,
        completed_at=completed_at,
    )
    session.add(node)
    session.flush()
    return node


def list_execution_nodes_for_run(
    session: Session,
    *,
    run_id: UUID,
) -> list[ExecutionNode]:
    return (
        session.query(ExecutionNode)
        .filter(ExecutionNode.run_id == run_id)
        .order_by(ExecutionNode.sequence_number.asc(), ExecutionNode.created_at.asc())
        .all()
    )


def ensure_execution_nodes_for_run(
    session: Session,
    *,
    run: ProjectRun,
) -> list[ExecutionNode]:
    return list_execution_nodes_for_run(session, run_id=run.run_id)


def node_is_ready(
    node: ExecutionNode,
    *,
    completed_node_ids: set[str],
) -> bool:
    dependency_ids = _as_payload_list(node.dependency_node_ids)
    return all(dependency_id in completed_node_ids for dependency_id in dependency_ids)


def get_ready_execution_nodes_for_run(
    session: Session,
    *,
    run_id: UUID,
) -> list[ExecutionNode]:
    nodes = list_execution_nodes_for_run(session, run_id=run_id)
    completed_node_ids = {
        str(node.node_id)
        for node in nodes
        if str(node.status or "").strip().lower() in _TERMINAL_NODE_STATUSES
    }
    return [
        node
        for node in nodes
        if str(node.status or "").strip().lower() in _PENDING_NODE_STATUSES
        and node_is_ready(node, completed_node_ids=completed_node_ids)
    ]
