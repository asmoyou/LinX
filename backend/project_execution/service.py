"""Shared helpers for the project execution backend skeleton."""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from access_control.permissions import CurrentUser
from database.project_execution_models import (
    ProjectAuditEvent,
    ProjectPlan,
    ProjectRun,
    ProjectRunStep,
    ProjectTask,
)
from project_execution.planning import build_step_definitions

_COMPLETED_STATUSES = {"completed", "done", "success", "succeeded", "approved"}
_FAILED_STATUSES = {"failed", "error", "cancelled", "canceled"}
_TERMINAL_RUN_STATUSES = _COMPLETED_STATUSES | _FAILED_STATUSES


def parse_uuid(value: Any, field_name: str) -> uuid.UUID:
    """Parse a UUID value or raise a 400 error."""
    if isinstance(value, uuid.UUID):
        return value

    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field_name}",
        ) from exc


def get_current_user_uuid(current_user: CurrentUser) -> uuid.UUID:
    """Return the authenticated user's UUID."""
    return parse_uuid(current_user.user_id, "current user ID")


def get_or_404(session: Session, model: Any, column: Any, value: Any, detail: str) -> Any:
    """Load one record or raise 404."""
    entity = session.query(model).filter(column == value).first()
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    return entity


def ensure_related_records(
    session: Session,
    *,
    project_id: Optional[uuid.UUID] = None,
    plan_id: Optional[uuid.UUID] = None,
    run_id: Optional[uuid.UUID] = None,
    task_id: Optional[uuid.UUID] = None,
    agent_id: Optional[uuid.UUID] = None,
    require_project: bool = False,
) -> None:
    """Validate referenced records for common project execution entities."""
    from database.models import Agent
    from database.project_execution_models import (
        Project,
        ProjectPlan,
        ProjectRun,
        ProjectTask,
    )

    if require_project and not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="project_id is required"
        )
    if project_id:
        get_or_404(session, Project, Project.project_id, project_id, "Project not found")
    if plan_id:
        get_or_404(session, ProjectPlan, ProjectPlan.plan_id, plan_id, "Plan not found")
    if run_id:
        get_or_404(session, ProjectRun, ProjectRun.run_id, run_id, "Run not found")
    if task_id:
        get_or_404(
            session, ProjectTask, ProjectTask.project_task_id, task_id, "Project task not found"
        )
    if agent_id:
        get_or_404(session, Agent, Agent.agent_id, agent_id, "Agent not found")


def apply_updates(entity: Any, payload: Any, allowed_fields: Iterable[str]) -> Any:
    """Apply partial updates using allowed field names only."""
    for field_name in allowed_fields:
        if hasattr(payload, field_name):
            value = getattr(payload, field_name)
            if value is not None:
                setattr(entity, field_name, value)
    return entity


def flush_and_refresh(session: Session, entity: Any) -> Any:
    """Persist ORM changes eagerly within the current transaction."""
    session.flush()
    session.refresh(entity)
    return entity


def _json_safe(value: Any) -> Any:
    """Recursively coerce common Python values into JSON-serializable structures."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def append_audit_event(
    session: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: Optional[uuid.UUID],
    current_user: Optional[CurrentUser],
    project_id: Optional[uuid.UUID] = None,
    run_id: Optional[uuid.UUID] = None,
    payload: Optional[dict[str, Any]] = None,
) -> ProjectAuditEvent:
    """Create a project execution audit row in the current transaction."""
    actor_user_id = get_current_user_uuid(current_user) if current_user else None
    event = ProjectAuditEvent(
        project_id=project_id,
        run_id=run_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        actor_user_id=actor_user_id,
        payload=_json_safe(payload or {}),
    )
    session.add(event)
    return event


def _normalize_status(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_completed_status(status: Any) -> bool:
    return _normalize_status(status) in _COMPLETED_STATUSES


def _is_failed_status(status: Any) -> bool:
    normalized = _normalize_status(status)
    return normalized in _FAILED_STATUSES or "fail" in normalized


def _is_terminal_task_status(status: Any) -> bool:
    return _is_completed_status(status) or _is_failed_status(status)


def _latest_timestamp(values: Iterable[Optional[datetime]]) -> Optional[datetime]:
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def reconcile_run_state(
    session: Session,
    *,
    run: Optional[ProjectRun] = None,
    run_id: Optional[uuid.UUID] = None,
) -> Optional[ProjectRun]:
    """Normalize stale run state based on the tasks and steps currently attached to it."""
    target_run = run
    if target_run is None and run_id is not None:
        target_run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()

    if target_run is None:
        return None

    tasks = session.query(ProjectTask).filter(ProjectTask.run_id == target_run.run_id).all()
    steps = session.query(ProjectRunStep).filter(ProjectRunStep.run_id == target_run.run_id).all()

    normalized_status = _normalize_status(target_run.status)
    completion_timestamp = _latest_timestamp(
        [
            target_run.completed_at,
            target_run.updated_at,
            target_run.started_at,
            *(task.updated_at for task in tasks),
            *(step.completed_at for step in steps),
            *(step.updated_at for step in steps),
        ]
    )
    failed_steps = any(_is_failed_status(step.status) for step in steps)
    failed_tasks = any(_is_failed_status(task.status) for task in tasks)
    has_active_tasks = any(not _is_terminal_task_status(task.status) for task in tasks)
    changed = False

    if normalized_status in _TERMINAL_RUN_STATUSES:
        if target_run.completed_at is None and completion_timestamp is not None:
            target_run.completed_at = completion_timestamp
            changed = True
    elif not tasks:
        if target_run.started_at is not None:
            next_status = "failed" if failed_steps else "completed"
            if target_run.status != next_status:
                target_run.status = next_status
                changed = True
            resolved_completed_at = completion_timestamp or datetime.now(timezone.utc)
            if target_run.completed_at != resolved_completed_at:
                target_run.completed_at = resolved_completed_at
                changed = True
        elif target_run.completed_at is not None:
            target_run.completed_at = None
            changed = True
    elif not has_active_tasks:
        next_status = "failed" if failed_tasks or failed_steps else "completed"
        if target_run.status != next_status:
            target_run.status = next_status
            changed = True
        resolved_completed_at = completion_timestamp or datetime.now(timezone.utc)
        if target_run.completed_at != resolved_completed_at:
            target_run.completed_at = resolved_completed_at
            changed = True
    elif target_run.completed_at is not None:
        target_run.completed_at = None
        changed = True

    if changed:
        session.flush()
        session.refresh(target_run)

    return target_run


def create_project_task_and_launch_run(
    session: Session,
    *,
    project_id: uuid.UUID,
    title: str,
    description: Optional[str],
    priority: str,
    assignee_agent_id: Optional[uuid.UUID],
    input_payload: Optional[dict[str, Any]],
    current_user: CurrentUser,
) -> tuple[ProjectTask, ProjectPlan, ProjectRun, ProjectRunStep]:
    """Create a task, plan, run, and initial pending run step bundle in one transaction."""
    actor_user_id = get_current_user_uuid(current_user)
    ensure_related_records(
        session,
        project_id=project_id,
        agent_id=assignee_agent_id,
        require_project=True,
    )

    next_sort_order = (
        session.query(ProjectTask).filter(ProjectTask.project_id == project_id).count()
    )
    next_plan_version = (
        session.query(ProjectPlan).filter(ProjectPlan.project_id == project_id).count() + 1
    )
    step_definitions = build_step_definitions(title, description)

    task = ProjectTask(
        project_id=project_id,
        assignee_agent_id=assignee_agent_id,
        title=title,
        description=description,
        status="queued",
        priority=priority,
        sort_order=next_sort_order,
        input_payload={**(input_payload or {}), "step_count": len(step_definitions)},
        created_by_user_id=actor_user_id,
    )
    session.add(task)
    flush_and_refresh(session, task)
    append_audit_event(
        session,
        action="project-task.created",
        resource_type="project_task",
        resource_id=task.project_task_id,
        project_id=task.project_id,
        current_user=current_user,
        payload={"status": task.status},
    )

    plan = ProjectPlan(
        project_id=project_id,
        name=f"{title} Plan",
        goal=description or title,
        status="active",
        version=next_plan_version,
        definition={
            "project_task_id": str(task.project_task_id),
            "task_title": title,
            "nodes": step_definitions,
        },
        created_by_user_id=actor_user_id,
    )
    session.add(plan)
    flush_and_refresh(session, plan)
    append_audit_event(
        session,
        action="plan.created",
        resource_type="project_plan",
        resource_id=plan.plan_id,
        project_id=project_id,
        current_user=current_user,
    )
    append_audit_event(
        session,
        action="plan.activated",
        resource_type="project_plan",
        resource_id=plan.plan_id,
        project_id=project_id,
        current_user=current_user,
        payload={"status": "active"},
    )

    run = ProjectRun(
        project_id=project_id,
        plan_id=plan.plan_id,
        status="queued",
        trigger_source="manual",
        runtime_context={
            "project_task_id": str(task.project_task_id),
            "task_title": title,
            "step_count": len(step_definitions),
        },
        requested_by_user_id=actor_user_id,
    )
    session.add(run)
    flush_and_refresh(session, run)
    append_audit_event(
        session,
        action="run.created",
        resource_type="project_run",
        resource_id=run.run_id,
        project_id=project_id,
        run_id=run.run_id,
        current_user=current_user,
        payload={"status": run.status},
    )

    created_steps: list[ProjectRunStep] = []
    for step_definition in step_definitions:
        step = ProjectRunStep(
            run_id=run.run_id,
            project_task_id=task.project_task_id,
            name=str(step_definition.get("name") or title),
            step_type="task",
            status="pending",
            sequence_number=int(step_definition.get("sequence") or 0),
            input_payload={
                "project_task_id": str(task.project_task_id),
                "step_kind": str(step_definition.get("step_kind") or "implementation"),
                "executor_kind": str(step_definition.get("executor_kind") or "agent"),
            },
        )
        session.add(step)
        flush_and_refresh(session, step)
        created_steps.append(step)
        append_audit_event(
            session,
            action="run-step.created",
            resource_type="project_run_step",
            resource_id=step.run_step_id,
            project_id=project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload={"sequence": step.sequence_number, "status": step.status},
        )

    task.plan_id = plan.plan_id
    task.run_id = run.run_id
    task.status = "queued"
    flush_and_refresh(session, task)
    append_audit_event(
        session,
        action="project-task.updated",
        resource_type="project_task",
        resource_id=task.project_task_id,
        project_id=project_id,
        run_id=run.run_id,
        current_user=current_user,
        payload={
            "plan_id": str(plan.plan_id),
            "run_id": str(run.run_id),
            "status": "queued",
        },
    )

    return task, plan, run, created_steps[0]
