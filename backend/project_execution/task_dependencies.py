from __future__ import annotations

from collections import defaultdict, deque
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from database.project_execution_models import ProjectTask, ProjectTaskDependency

ALLOWED_DEPENDENCY_REQUIRED_STATES = {"ready_to_start", "approved", "completed", "accepted"}
ALLOWED_DEPENDENCY_TYPES = {"hard", "soft", "artifact", "review"}
_COMPLETED_STATUSES = {"completed", "done", "success", "succeeded"}
_APPROVED_STATUSES = _COMPLETED_STATUSES | {"approved", "pending_acceptance"}
_READY_TO_START_STATUSES = _APPROVED_STATUSES | {"running", "reviewing", "assigned", "queued", "scheduled"}


class DependencyValidationError(ValueError):
    """Raised when dependency payload is invalid."""


class DependencyCycleError(RuntimeError):
    """Raised when dependency change would introduce a cycle."""


def _normalize_required_state(value: Any) -> str:
    normalized = str(value or "approved").strip().lower() or "approved"
    if normalized not in ALLOWED_DEPENDENCY_REQUIRED_STATES:
        raise DependencyValidationError(f"Unsupported required_state: {normalized}")
    return normalized


def _normalize_dependency_type(value: Any) -> str:
    normalized = str(value or "hard").strip().lower() or "hard"
    if normalized not in ALLOWED_DEPENDENCY_TYPES:
        raise DependencyValidationError(f"Unsupported dependency_type: {normalized}")
    return normalized


def is_dependency_satisfied(*, dependency_task_status: str, required_state: str) -> bool:
    normalized_status = str(dependency_task_status or "").strip().lower()
    normalized_required_state = _normalize_required_state(required_state)

    if normalized_required_state == "completed":
        return normalized_status in _COMPLETED_STATUSES
    if normalized_required_state == "approved":
        return normalized_status in _APPROVED_STATUSES
    if normalized_required_state == "accepted":
        return normalized_status in _COMPLETED_STATUSES
    if normalized_required_state == "ready_to_start":
        return normalized_status in _READY_TO_START_STATUSES
    return False


def list_task_dependencies(
    session: Session,
    *,
    project_task_id: UUID,
) -> list[ProjectTaskDependency]:
    return (
        session.query(ProjectTaskDependency)
        .filter(ProjectTaskDependency.project_task_id == project_task_id)
        .order_by(ProjectTaskDependency.created_at.asc())
        .all()
    )


def build_dependency_snapshot(
    session: Session,
    *,
    project_task_id: UUID,
) -> list[dict[str, Any]]:
    rows = list_task_dependencies(session, project_task_id=project_task_id)
    if not rows:
        return []

    dependency_task_ids = [row.depends_on_project_task_id for row in rows]
    dependency_tasks = (
        session.query(ProjectTask)
        .filter(ProjectTask.project_task_id.in_(dependency_task_ids))
        .all()
    )
    task_lookup = {task.project_task_id: task for task in dependency_tasks}

    result: list[dict[str, Any]] = []
    for row in rows:
        dependency_task = task_lookup.get(row.depends_on_project_task_id)
        status = str(dependency_task.status or "") if dependency_task is not None else ""
        result.append(
            {
                "id": str(row.dependency_id),
                "project_task_id": str(row.project_task_id),
                "depends_on_task_id": str(row.depends_on_project_task_id),
                "depends_on_task_title": dependency_task.title if dependency_task is not None else None,
                "depends_on_task_status": status or None,
                "required_state": row.required_state,
                "dependency_type": row.dependency_type,
                "artifact_selector": row.artifact_selector or {},
                "satisfied": (
                    is_dependency_satisfied(
                        dependency_task_status=status,
                        required_state=row.required_state,
                    )
                    if dependency_task is not None
                    else False
                ),
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }
        )
    return result


def compute_task_readiness(
    session: Session,
    *,
    project_task_id: UUID,
) -> dict[str, Any]:
    snapshots = build_dependency_snapshot(session, project_task_id=project_task_id)
    blocking = [item for item in snapshots if not item["satisfied"] and item["dependency_type"] == "hard"]
    return {
        "ready": len(blocking) == 0,
        "blocking_dependency_count": len(blocking),
        "dependencies": snapshots,
    }


def summarize_task_blockers(readiness: dict[str, Any]) -> Optional[str]:
    blocking_count = int(readiness.get("blocking_dependency_count") or 0)
    if blocking_count <= 0:
        return None
    return (
        f"Waiting on {blocking_count} upstream dependenc{'y' if blocking_count == 1 else 'ies'}."
    )


def _build_adjacency(
    rows: list[tuple[UUID, UUID]],
) -> dict[UUID, set[UUID]]:
    adjacency: dict[UUID, set[UUID]] = defaultdict(set)
    for source, target in rows:
        adjacency[source].add(target)
    return adjacency


def _detect_cycle(
    adjacency: dict[UUID, set[UUID]],
    *,
    start_task_id: UUID,
) -> bool:
    visited: set[UUID] = set()
    stack: deque[UUID] = deque([start_task_id])

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency.get(current, set()):
            if neighbor == start_task_id:
                return True
            if neighbor not in visited:
                stack.append(neighbor)
    return False


def replace_task_dependencies(
    session: Session,
    *,
    task: ProjectTask,
    dependencies: list[dict[str, Any]],
    actor_user_id: Optional[UUID],
) -> list[ProjectTaskDependency]:
    normalized_dependencies: list[dict[str, Any]] = []
    for item in dependencies:
        raw_task_id = str(
            item.get("depends_on_task_id") or item.get("dependsOnTaskId") or ""
        ).strip()
        if not raw_task_id:
            raise DependencyValidationError("depends_on_task_id is required")
        try:
            depends_on_task_id = UUID(raw_task_id)
        except ValueError as exc:
            raise DependencyValidationError(f"Invalid depends_on_task_id: {raw_task_id}") from exc
        if depends_on_task_id == task.project_task_id:
            raise DependencyValidationError("Task cannot depend on itself")
        normalized_dependencies.append(
            {
                "depends_on_project_task_id": depends_on_task_id,
                "required_state": _normalize_required_state(
                    item.get("required_state") or item.get("requiredState")
                ),
                "dependency_type": _normalize_dependency_type(
                    item.get("dependency_type") or item.get("dependencyType")
                ),
                "artifact_selector": item.get("artifact_selector")
                or item.get("artifactSelector")
                or {},
            }
        )

    dependency_task_ids = [item["depends_on_project_task_id"] for item in normalized_dependencies]
    if dependency_task_ids:
        dependency_tasks = (
            session.query(ProjectTask)
            .filter(ProjectTask.project_task_id.in_(dependency_task_ids))
            .all()
        )
        task_lookup = {dependency_task.project_task_id: dependency_task for dependency_task in dependency_tasks}
        for dependency_task_id in dependency_task_ids:
            dependency_task = task_lookup.get(dependency_task_id)
            if dependency_task is None:
                raise DependencyValidationError(f"Dependency task not found: {dependency_task_id}")
            if dependency_task.project_id != task.project_id:
                raise DependencyValidationError("Dependency task must belong to the same project")

    existing_edges = (
        session.query(
            ProjectTaskDependency.project_task_id,
            ProjectTaskDependency.depends_on_project_task_id,
        )
        .filter(ProjectTaskDependency.project_task_id != task.project_task_id)
        .all()
    )
    next_edges = existing_edges + [
        (task.project_task_id, item["depends_on_project_task_id"]) for item in normalized_dependencies
    ]
    adjacency = _build_adjacency(next_edges)
    if _detect_cycle(adjacency, start_task_id=task.project_task_id):
        raise DependencyCycleError("Dependency change would introduce a cycle")

    (
        session.query(ProjectTaskDependency)
        .filter(ProjectTaskDependency.project_task_id == task.project_task_id)
        .delete(synchronize_session=False)
    )
    session.flush()

    created_rows: list[ProjectTaskDependency] = []
    for item in normalized_dependencies:
        row = ProjectTaskDependency(
            project_task_id=task.project_task_id,
            depends_on_project_task_id=item["depends_on_project_task_id"],
            required_state=item["required_state"],
            dependency_type=item["dependency_type"],
            artifact_selector=item["artifact_selector"],
            created_by_user_id=actor_user_id,
        )
        session.add(row)
        created_rows.append(row)

    existing_input_payload = task.input_payload if isinstance(task.input_payload, dict) else {}
    task.input_payload = {
        **existing_input_payload,
        "dependency_ids": [str(item["depends_on_project_task_id"]) for item in normalized_dependencies],
    }
    session.flush()

    return list_task_dependencies(session, project_task_id=task.project_task_id)
