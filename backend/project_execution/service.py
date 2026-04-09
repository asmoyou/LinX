"""Shared helpers for the project execution backend skeleton."""

import uuid
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from access_control.permissions import CurrentUser
from database.models import Agent
from database.project_execution_models import (
    ExecutionNode,
    Project,
    ProjectAuditEvent,
    ProjectPlan,
    ProjectRun,
    ProjectTask,
)
from project_execution.execution_nodes import create_execution_node
from project_execution.model_planner import PlannerResult, build_plan_definition

_COMPLETED_STATUSES = {"completed", "done", "success", "succeeded", "approved"}
_FAILED_STATUSES = {"failed", "error", "cancelled", "canceled"}
_TERMINAL_RUN_STATUSES = _COMPLETED_STATUSES | _FAILED_STATUSES
_EPHEMERAL_AGENT_CLEANUP_RUN_STATUSES = _TERMINAL_RUN_STATUSES | {"blocked"}
_TASK_ACTIVE_STEP_STATUSES = {"running", "acked", "leased"}
_TASK_ASSIGNED_STEP_STATUSES = {"assigned"}
_TASK_PENDING_STEP_STATUSES = {"pending", "queued"}
_RUN_ACTIVE_STATUSES = {"running", "executing", "in_progress"}
_RUN_BLOCKED_STATUSES = {"blocked"}
_RUN_QUEUED_STATUSES = {"queued", "assigned", "scheduled", "pending"}


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


def _is_blocked_status(status: Any) -> bool:
    return _normalize_status(status) == "blocked"


def _latest_timestamp(values: Iterable[Optional[datetime]]) -> Optional[datetime]:
    filtered = [value for value in values if value is not None]
    return max(filtered) if filtered else None


def _resolve_task_status(current_status: Any, execution_records: Iterable[Any]) -> str:
    record_statuses = [_normalize_status(record.status) for record in execution_records]
    if not record_statuses:
        return str(current_status or "")

    if any(_is_failed_status(status) for status in record_statuses):
        return "failed"
    if any(status in _TASK_ACTIVE_STEP_STATUSES for status in record_statuses):
        return "running"
    if any(status in _TASK_ASSIGNED_STEP_STATUSES for status in record_statuses):
        return "assigned"
    if any(status in _TASK_PENDING_STEP_STATUSES for status in record_statuses):
        return "queued"
    if all(_is_completed_status(status) for status in record_statuses):
        return "completed"
    if any(_is_blocked_status(status) for status in record_statuses):
        return "blocked"
    return str(current_status or "")


def reconcile_task_state(
    session: Session,
    *,
    task: Optional[ProjectTask] = None,
    task_id: Optional[uuid.UUID] = None,
) -> Optional[ProjectTask]:
    target_task = task
    if target_task is None and task_id is not None:
        target_task = (
            session.query(ProjectTask).filter(ProjectTask.project_task_id == task_id).first()
        )

    if target_task is None:
        return None

    execution_nodes = (
        session.query(ExecutionNode)
        .filter(ExecutionNode.project_task_id == target_task.project_task_id)
        .order_by(ExecutionNode.sequence_number.asc(), ExecutionNode.created_at.asc())
        .all()
    )
    execution_records: list[Any] = list(execution_nodes)
    next_status = _resolve_task_status(target_task.status, execution_records)
    if next_status and target_task.status != next_status:
        target_task.status = next_status
        session.flush()
    return target_task


def _resolve_project_status(
    current_status: Any,
    tasks: Iterable[ProjectTask],
    runs: Iterable[ProjectRun],
) -> str:
    task_list = list(tasks)
    run_list = list(runs)
    task_statuses = [_normalize_status(task.status) for task in task_list]
    run_statuses = [_normalize_status(run.status) for run in run_list]

    if not task_statuses and not run_statuses:
        return str(current_status or "")

    if any(status in _RUN_ACTIVE_STATUSES for status in (*task_statuses, *run_statuses)):
        return "running"

    if any(status in _RUN_QUEUED_STATUSES for status in (*task_statuses, *run_statuses)):
        return "queued"

    if run_list:
        latest_run = max(
            run_list,
            key=lambda run: _latest_timestamp(
                [run.updated_at, run.completed_at, run.started_at, run.created_at]
            )
            or datetime.min.replace(tzinfo=timezone.utc),
        )
        latest_run_status = _normalize_status(latest_run.status)
        if latest_run_status in _RUN_BLOCKED_STATUSES:
            return "blocked"
        if _is_failed_status(latest_run_status):
            return "failed"
        if latest_run_status in _TERMINAL_RUN_STATUSES:
            return "completed"

    if task_list:
        latest_task = max(
            task_list,
            key=lambda task: _latest_timestamp([task.updated_at, task.created_at])
            or datetime.min.replace(tzinfo=timezone.utc),
        )
        latest_task_status = _normalize_status(latest_task.status)
        if latest_task_status in _RUN_BLOCKED_STATUSES:
            return "blocked"
        if _is_failed_status(latest_task_status):
            return "failed"
        if _is_completed_status(latest_task_status):
            return "completed"

    return str(current_status or "")


def reconcile_project_state(
    session: Session,
    *,
    project: Optional[Project] = None,
    project_id: Optional[uuid.UUID] = None,
) -> Optional[Project]:
    target_project = project
    if target_project is None and project_id is not None:
        target_project = session.query(Project).filter(Project.project_id == project_id).first()

    if target_project is None:
        return None

    tasks = session.query(ProjectTask).filter(ProjectTask.project_id == target_project.project_id).all()
    runs = session.query(ProjectRun).filter(ProjectRun.project_id == target_project.project_id).all()
    next_status = _resolve_project_status(target_project.status, tasks, runs)
    if next_status and target_project.status != next_status:
        target_project.status = next_status
        session.flush()
    return target_project


def retire_ephemeral_run_agents(
    session: Session,
    *,
    run: ProjectRun,
    tasks: Optional[list[ProjectTask]] = None,
) -> list[uuid.UUID]:
    """Retire run-scoped ephemeral agents once a run is no longer actively executing."""
    normalized_status = _normalize_status(run.status)
    if normalized_status not in _EPHEMERAL_AGENT_CLEANUP_RUN_STATUSES:
        return []

    target_agent_ids: set[uuid.UUID] = {
        task.assignee_agent_id
        for task in (tasks or [])
        if getattr(task, "assignee_agent_id", None) is not None
    }

    runtime_context = run.runtime_context or {}
    if isinstance(runtime_context, dict):
        assignment = runtime_context.get("agent_assignment") or runtime_context.get("executor_assignment")
        if isinstance(assignment, dict):
            raw_agent_id = assignment.get("agent_id")
            try:
                if raw_agent_id:
                    target_agent_ids.add(uuid.UUID(str(raw_agent_id)))
            except (TypeError, ValueError):
                pass

    if not target_agent_ids:
        return []

    now = datetime.now(timezone.utc)
    agents = (
        session.query(Agent)
        .filter(Agent.agent_id.in_(list(target_agent_ids)))
        .filter(Agent.is_ephemeral.is_(True))
        .filter(Agent.lifecycle_scope == "current_run")
        .filter(Agent.retired_at.is_(None))
        .all()
    )
    if not agents:
        return []

    retired_ids: list[uuid.UUID] = []
    for agent in agents:
        agent.status = "offline"
        agent.retired_at = now
        retired_ids.append(agent.agent_id)

    session.flush()
    return retired_ids


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
    execution_nodes = (
        session.query(ExecutionNode)
        .filter(ExecutionNode.run_id == target_run.run_id)
        .order_by(ExecutionNode.sequence_number.asc(), ExecutionNode.created_at.asc())
        .all()
    )
    execution_records: list[Any] = list(execution_nodes)
    records_by_task: dict[uuid.UUID, list[Any]] = {}
    for record in execution_records:
        if record.project_task_id is None:
            continue
        records_by_task.setdefault(record.project_task_id, []).append(record)

    task_state_changed = False
    for task in tasks:
        next_task_status = _resolve_task_status(
            task.status, records_by_task.get(task.project_task_id, [])
        )
        if next_task_status and task.status != next_task_status:
            task.status = next_task_status
            task_state_changed = True

    if task_state_changed:
        session.flush()

    normalized_status = _normalize_status(target_run.status)
    completion_timestamp = _latest_timestamp(
        [
            target_run.completed_at,
            target_run.updated_at,
            target_run.started_at,
            *(task.updated_at for task in tasks),
            *(record.completed_at for record in execution_records),
            *(record.updated_at for record in execution_records),
        ]
    )
    failed_execution_records = any(_is_failed_status(record.status) for record in execution_records)
    failed_tasks = any(_is_failed_status(task.status) for task in tasks)
    has_active_tasks = any(not _is_terminal_task_status(task.status) for task in tasks)
    changed = False

    if normalized_status in _TERMINAL_RUN_STATUSES:
        if target_run.completed_at is None and completion_timestamp is not None:
            target_run.completed_at = completion_timestamp
            changed = True
    elif not tasks:
        if target_run.started_at is not None:
            next_status = "failed" if failed_execution_records else "completed"
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
        next_status = "failed" if failed_tasks or failed_execution_records else "completed"
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

    retire_ephemeral_run_agents(session, run=target_run, tasks=tasks)
    reconcile_project_state(session, project_id=target_run.project_id)

    return target_run


def _planner_parallel_group_count(planner_result: PlannerResult) -> int:
    return len(
        {
            str(step.parallel_group).strip()
            for step in planner_result.steps
            if str(step.parallel_group or "").strip()
        }
    )


def _planner_clarification_payload(planner_result: PlannerResult) -> list[dict[str, Any]]:
    return [question.model_dump() for question in planner_result.clarification_questions]


def _planner_step_count(planner_result: PlannerResult) -> int:
    return len(planner_result.steps)


def _planner_task_input_payload(
    *,
    input_payload: Optional[dict[str, Any]],
    planner_result: PlannerResult,
    execution_mode: str,
) -> dict[str, Any]:
    return {
        **(input_payload or {}),
        "execution_mode": execution_mode,
        "planner_summary": planner_result.summary,
        "planner_source": planner_result.planner_source,
        "planner_provider": planner_result.planner_provider,
        "planner_model": planner_result.planner_model,
        "step_count": _planner_step_count(planner_result),
        "parallel_group_count": _planner_parallel_group_count(planner_result),
        "planner_clarification_questions": _planner_clarification_payload(planner_result),
    }


def create_project_task_and_launch_run(
    session: Session,
    *,
    project_id: uuid.UUID,
    title: str,
    description: Optional[str],
    priority: str,
    assignee_agent_id: Optional[uuid.UUID],
    input_payload: Optional[dict[str, Any]],
    planner_result: PlannerResult,
    current_user: CurrentUser,
) -> tuple[ProjectTask, Optional[ProjectPlan], Optional[ProjectRun], Optional[ExecutionNode]]:
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
    execution_mode = str((input_payload or {}).get("execution_mode") or "auto")
    planner_task_payload = _planner_task_input_payload(
        input_payload=input_payload,
        planner_result=planner_result,
        execution_mode=execution_mode,
    )

    task = ProjectTask(
        project_id=project_id,
        assignee_agent_id=assignee_agent_id,
        title=title,
        description=description,
        status="needs_clarification" if planner_result.needs_clarification else "queued",
        priority=priority,
        sort_order=next_sort_order,
        input_payload=planner_task_payload,
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

    if planner_result.needs_clarification:
        reconcile_project_state(session, project_id=project_id)
        return task, None, None, None

    plan = ProjectPlan(
        project_id=project_id,
        name=f"{title} Plan",
        goal=description or title,
        status="active",
        version=next_plan_version,
        definition={
            "project_task_id": str(task.project_task_id),
            "task_title": title,
            "execution_mode": execution_mode,
            **build_plan_definition(planner_result),
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
            "execution_mode": execution_mode,
            "step_count": _planner_step_count(planner_result),
            "parallel_group_count": _planner_parallel_group_count(planner_result),
            "planner_summary": planner_result.summary,
            "planner_source": planner_result.planner_source,
            "planner_provider": planner_result.planner_provider,
            "planner_model": planner_result.planner_model,
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

    created_nodes: list[tuple[ExecutionNode, Any]] = []
    planner_step_to_node_id: dict[str, str] = {}
    for index, planner_step in enumerate(planner_result.steps):
        node = create_execution_node(
            session,
            run=run,
            project_task_id=task.project_task_id,
            name=planner_step.name,
            node_type="task",
            status="pending",
            sequence_number=index,
            node_payload={
                "project_task_id": str(task.project_task_id),
                "planner_step_id": planner_step.id,
                "step_kind": planner_step.step_kind,
                "executor_kind": planner_step.executor_kind,
                "execution_mode": planner_step.execution_mode,
                "required_capabilities": list(planner_step.required_capabilities or []),
                "suggested_agent_ids": list(planner_step.suggested_agent_ids or []),
                "acceptance": planner_step.acceptance,
                "parallel_group": planner_step.parallel_group,
            },
        )
        planner_step_to_node_id[planner_step.id] = str(node.node_id)
        created_nodes.append((node, planner_step))
        append_audit_event(
            session,
            action="execution-node.created",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload={"sequence": node.sequence_number, "status": node.status},
        )

    for node, planner_step in created_nodes:
        node.dependency_node_ids = [
            planner_step_to_node_id[dependency_id]
            for dependency_id in planner_step.depends_on
            if dependency_id in planner_step_to_node_id
        ]
        node.node_payload = {
            **(node.node_payload or {}),
            "dependency_node_ids": list(node.dependency_node_ids or []),
            "dependency_step_ids": [],
        }
        flush_and_refresh(session, node)

    task.plan_id = plan.plan_id
    task.run_id = run.run_id
    task.status = "queued"
    task.input_payload = {
        **(task.input_payload or {}),
        "plan_id": str(plan.plan_id),
        "run_id": str(run.run_id),
    }
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

    reconcile_project_state(session, project_id=project_id)
    first_node = created_nodes[0][0] if created_nodes else None
    return task, plan, run, first_node


def _update_planned_execution_nodes_for_run(
    session: Session,
    *,
    run: ProjectRun,
    task: ProjectTask,
    planner_result: PlannerResult,
) -> list[ExecutionNode]:
    created_nodes: list[tuple[ExecutionNode, Any]] = []
    planner_step_to_node_id: dict[str, str] = {}
    for index, planner_step in enumerate(planner_result.steps):
        node = create_execution_node(
            session,
            run=run,
            project_task_id=task.project_task_id,
            name=planner_step.name,
            node_type="task",
            status="pending",
            sequence_number=index,
            node_payload={
                "project_task_id": str(task.project_task_id),
                "planner_step_id": planner_step.id,
                "step_kind": planner_step.step_kind,
                "executor_kind": planner_step.executor_kind,
                "execution_mode": planner_step.execution_mode,
                "required_capabilities": list(planner_step.required_capabilities or []),
                "suggested_agent_ids": list(planner_step.suggested_agent_ids or []),
                "acceptance": planner_step.acceptance,
                "parallel_group": planner_step.parallel_group,
            },
        )
        planner_step_to_node_id[planner_step.id] = str(node.node_id)
        created_nodes.append((node, planner_step))

    for node, planner_step in created_nodes:
        node.dependency_node_ids = [
            planner_step_to_node_id[dependency_id]
            for dependency_id in planner_step.depends_on
            if dependency_id in planner_step_to_node_id
        ]
        node.node_payload = {
            **(node.node_payload or {}),
            "dependency_node_ids": list(node.dependency_node_ids or []),
            "dependency_step_ids": [],
        }
        flush_and_refresh(session, node)

    return [node for node, _ in created_nodes]


def launch_existing_project_task_run(
    session: Session,
    *,
    task: ProjectTask,
    planner_result: PlannerResult,
    current_user: CurrentUser,
) -> tuple[ProjectTask, Optional[ProjectPlan], Optional[ProjectRun], Optional[ExecutionNode]]:
    if task.project_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task is not attached to a project",
        )
    actor_user_id = get_current_user_uuid(current_user)
    next_plan_version = (
        session.query(ProjectPlan).filter(ProjectPlan.project_id == task.project_id).count() + 1
    )
    execution_mode = str((task.input_payload or {}).get("execution_mode") or "auto")
    parallel_group_count = _planner_parallel_group_count(planner_result)

    task.input_payload = _planner_task_input_payload(
        input_payload={**(task.input_payload or {})},
        planner_result=planner_result,
        execution_mode=execution_mode,
    )
    task.status = "needs_clarification" if planner_result.needs_clarification else "queued"
    task.output_payload = {}
    task.error_message = None
    flush_and_refresh(session, task)

    if planner_result.needs_clarification:
        return task, None, None, None

    plan = ProjectPlan(
        project_id=task.project_id,
        name=f"{task.title} Plan",
        goal=task.description or task.title,
        status="active",
        version=next_plan_version,
        definition={
            "project_task_id": str(task.project_task_id),
            "task_title": task.title,
            "execution_mode": execution_mode,
            **build_plan_definition(planner_result),
        },
        created_by_user_id=actor_user_id,
    )
    session.add(plan)
    flush_and_refresh(session, plan)

    run = ProjectRun(
        project_id=task.project_id,
        plan_id=plan.plan_id,
        status="queued",
        trigger_source="manual",
        runtime_context={
            "project_task_id": str(task.project_task_id),
            "task_title": task.title,
            "execution_mode": execution_mode,
            "step_count": _planner_step_count(planner_result),
            "parallel_group_count": parallel_group_count,
            "planner_summary": planner_result.summary,
            "planner_source": planner_result.planner_source,
            "planner_provider": planner_result.planner_provider,
            "planner_model": planner_result.planner_model,
        },
        requested_by_user_id=actor_user_id,
    )
    session.add(run)
    flush_and_refresh(session, run)

    created_nodes = _update_planned_execution_nodes_for_run(
        session,
        run=run,
        task=task,
        planner_result=planner_result,
    )

    task.plan_id = plan.plan_id
    task.run_id = run.run_id
    task.status = "queued"
    task.input_payload = {
        **(task.input_payload or {}),
        "plan_id": str(plan.plan_id),
        "run_id": str(run.run_id),
    }
    flush_and_refresh(session, task)

    first_node = created_nodes[0] if created_nodes else None
    return task, plan, run, first_node
