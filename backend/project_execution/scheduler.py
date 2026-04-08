from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from access_control.permissions import CurrentUser
from agent_framework.agent_registry import get_agent_registry
from agent_framework.conversation_execution import build_conversation_execution_principal
from agent_framework.persistent_conversations import (
    build_default_conversation_title,
    get_persistent_conversation_runtime_service,
)
from api_gateway.routers.agent_conversations import execute_persistent_conversation_turn
from database.connection import get_db_session
from database.models import AgentConversation
from database.project_execution_models import ExternalAgentDispatch, Project, ProjectPlan, ProjectRun, ProjectRunStep, ProjectSpace, ProjectTask
from project_execution.agent_provisioner import (
    ProjectAgentProvisioner,
    ProjectExternalRuntimeUnavailableError,
    default_required_capabilities,
)
from project_execution.external_runtime_service import EXTERNAL_RUNTIME_TYPES, ExternalRuntimeService, ExternalRuntimeUnavailableError
from project_execution.planning import infer_step_kind, normalize_execution_mode
from project_execution.run_workspace_manager import RunWorkspaceDescriptor, get_run_workspace_manager
from project_execution.service import (
    append_audit_event,
    flush_and_refresh,
    reconcile_run_state,
    retire_ephemeral_run_agents,
)
from shared.logging import get_logger

logger = get_logger(__name__)
_TERMINAL_STEP_STATUSES = {"completed", "failed", "cancelled", "blocked"}


def _auto_execute_enabled() -> bool:
    override = os.environ.get("LINX_DISABLE_PROJECT_EXECUTION_AUTO_EXECUTION")
    if override is not None:
        return str(override).strip().lower() not in {"1", "true", "yes", "on"}
    return os.environ.get("PYTEST_CURRENT_TEST") is None





def _block_pending_step(
    session,
    *,
    pending_step: ProjectRunStep,
    task: ProjectTask,
    run: ProjectRun,
    current_user: CurrentUser,
    reason: str,
    selection: Optional[Any] = None,
) -> dict[str, Any]:
    if selection is not None:
        if getattr(selection, "agent_id", None) is not None:
            task.assignee_agent_id = selection.agent_id
        task.input_payload = {
            **(task.input_payload or {}),
            "assigned_agent_id": str(selection.agent_id),
            "assigned_agent_name": selection.agent_name,
            "selection_reason": selection.selection_reason,
            "runtime_type": selection.runtime_type,
        }
        pending_step.input_payload = {
            **(pending_step.input_payload or {}),
            "assigned_agent_id": str(selection.agent_id),
            "assigned_agent_name": selection.agent_name,
            "selection_reason": selection.selection_reason,
            "runtime_type": selection.runtime_type,
        }
        run.runtime_context = {
            **(run.runtime_context or {}),
            "agent_assignment": {
                "executor_kind": "agent",
                "agent_id": str(selection.agent_id),
                "selection_reason": selection.selection_reason,
                "provisioned_agent": bool(selection.provisioned_agent),
                "runtime_type": selection.runtime_type,
            },
        }
    pending_step.status = "blocked"
    pending_step.error_message = reason
    task.status = "blocked"
    task.error_message = reason
    run.status = "blocked"
    run.error_message = reason
    flush_and_refresh(session, pending_step)
    flush_and_refresh(session, task)
    flush_and_refresh(session, run)
    retire_ephemeral_run_agents(session, run=run, tasks=[task])
    append_audit_event(
        session,
        action="run-step.blocked",
        resource_type="project_run_step",
        resource_id=pending_step.run_step_id,
        project_id=run.project_id,
        run_id=run.run_id,
        current_user=current_user,
        payload={"reason": reason},
    )
    reconcile_run_state(session, run=run)
    return {
        "executor_kind": "agent",
        "agent_id": getattr(selection, "agent_id", None),
        "dispatch_id": None,
        "selection_reason": getattr(selection, "selection_reason", reason),
        "provisioned_agent": bool(getattr(selection, "provisioned_agent", False)),
        "runtime_type": getattr(selection, "runtime_type", None),
        "external_dispatch": None,
    }


def _queue_external_agent_dispatch(
    session,
    *,
    selection,
    run: ProjectRun,
    pending_step: ProjectRunStep,
    task: ProjectTask,
    project: Optional[Project],
    current_user: CurrentUser,
    descriptor: Optional[RunWorkspaceDescriptor],
    step_kind: str,
) -> dict[str, Any]:
    runtime_service = ExternalRuntimeService(session)
    try:
        dispatch = runtime_service.create_dispatch(
            agent_id=selection.agent_id,
            source_type="project_run_step",
            source_id=str(pending_step.run_step_id),
            runtime_type=selection.runtime_type,
            project_id=run.project_id,
            run_id=run.run_id,
            run_step_id=pending_step.run_step_id,
            request_payload={
                "selection_reason": selection.selection_reason,
                "project_id": str(run.project_id),
                "run_id": str(run.run_id),
                "run_step_id": str(pending_step.run_step_id),
                "task_id": str(task.project_task_id),
                "task_title": task.title,
                "task_description": task.description,
                "step_name": pending_step.name,
                "step_kind": step_kind,
                "runtime_type": selection.runtime_type,
                "run_workspace_root": str(
                    descriptor.run_workspace_root
                    if descriptor
                    else get_run_workspace_manager().get_run_workspace_root(run.project_id, run.run_id)
                ),
                "project_title": project.name if project else "Project",
                "execution_prompt": build_external_agent_prompt(
                    project_title=project.name if project else "Project",
                    task_title=task.title,
                    task_description=task.description,
                    step_name=pending_step.name,
                    step_kind=step_kind,
                    selection_reason=selection.selection_reason,
                    runtime_type=selection.runtime_type,
                    run_workspace_root=str(
                        descriptor.run_workspace_root
                        if descriptor
                        else get_run_workspace_manager().get_run_workspace_root(run.project_id, run.run_id)
                    ),
                ),
            },
        )
    except ExternalRuntimeUnavailableError as exc:
        detail = str(exc)
        return _block_pending_step(
            session,
            pending_step=pending_step,
            task=task,
            run=run,
            current_user=current_user,
            reason=(
                "External agent launch command is not configured"
                if detail == "external_agent_launch_command_not_configured"
                else "External agent is not online"
            ),
            selection=selection,
        )

    task.assignee_agent_id = selection.agent_id
    task.status = "assigned"
    task.error_message = None
    pending_step.status = "queued"
    pending_step.error_message = None
    run.status = "scheduled"
    run.error_message = None
    run.completed_at = None
    run.runtime_context = {
        **(run.runtime_context or {}),
        "agent_assignment": {
            "executor_kind": "agent",
            "agent_id": str(selection.agent_id),
            "dispatch_id": str(dispatch.dispatch_id),
            "selection_reason": selection.selection_reason,
            "provisioned_agent": selection.provisioned_agent,
            "runtime_type": selection.runtime_type,
        },
        "external_dispatch": {
            "dispatch_id": str(dispatch.dispatch_id),
            "binding_id": str(dispatch.binding_id),
            "status": dispatch.status,
            "runtime_type": dispatch.runtime_type,
        },
    }
    task.input_payload = {
        **(task.input_payload or {}),
        "assigned_agent_id": str(selection.agent_id),
        "assigned_agent_name": selection.agent_name,
        "selection_reason": selection.selection_reason,
        "runtime_type": selection.runtime_type,
        "dispatch_id": str(dispatch.dispatch_id),
    }
    pending_step.input_payload = {
        **(pending_step.input_payload or {}),
        "selection_reason": selection.selection_reason,
        "assigned_agent_id": str(selection.agent_id),
        "assigned_agent_name": selection.agent_name,
        "runtime_type": selection.runtime_type,
        "dispatch_id": str(dispatch.dispatch_id),
    }
    flush_and_refresh(session, task)
    flush_and_refresh(session, pending_step)
    flush_and_refresh(session, run)
    append_audit_event(
        session,
        action="external-agent-dispatch.created",
        resource_type="external_agent_dispatch",
        resource_id=dispatch.dispatch_id,
        project_id=run.project_id,
        run_id=run.run_id,
        current_user=current_user,
        payload={"agent_id": str(selection.agent_id)},
    )
    return {
        "executor_kind": "agent",
        "agent_id": selection.agent_id,
        "dispatch_id": dispatch.dispatch_id,
        "selection_reason": selection.selection_reason,
        "provisioned_agent": selection.provisioned_agent,
        "runtime_type": selection.runtime_type,
        "external_dispatch": {
            "dispatch_id": dispatch.dispatch_id,
            "agent_id": dispatch.agent_id,
            "binding_id": dispatch.binding_id,
            "project_id": dispatch.project_id,
            "run_id": dispatch.run_id,
            "run_step_id": dispatch.run_step_id,
            "source_type": dispatch.source_type,
            "source_id": dispatch.source_id,
            "runtime_type": dispatch.runtime_type,
            "request_payload": dispatch.request_payload,
            "result_payload": dispatch.result_payload,
            "status": dispatch.status,
            "error_message": dispatch.error_message,
            "acked_at": dispatch.acked_at,
            "started_at": dispatch.started_at,
            "completed_at": dispatch.completed_at,
            "expires_at": dispatch.expires_at,
            "created_at": dispatch.created_at,
            "updated_at": dispatch.updated_at,
        },
    }


def _dependency_step_ids(step: ProjectRunStep) -> list[str]:
    payload = step.input_payload if isinstance(step.input_payload, dict) else {}
    raw = payload.get("dependency_step_ids")
    if not isinstance(raw, list):
        return []
    return [str(value).strip() for value in raw if str(value).strip()]


def _step_is_ready(step: ProjectRunStep, completed_step_ids: set[str]) -> bool:
    dependency_ids = _dependency_step_ids(step)
    return all(dependency_id in completed_step_ids for dependency_id in dependency_ids)


def _schedule_ready_step(
    session,
    *,
    run: ProjectRun,
    pending_step: ProjectRunStep,
    current_user: CurrentUser,
    descriptor: Optional[RunWorkspaceDescriptor],
) -> tuple[dict[str, Any], Optional[UUID]]:
    task = (
        session.query(ProjectTask)
        .filter(ProjectTask.project_task_id == pending_step.project_task_id)
        .first()
    )
    if task is None:
        return {"executor_kind": "agent", "selection_reason": "Task not found"}, None
    project = session.query(Project).filter(Project.project_id == run.project_id).first()

    step_payload = dict(pending_step.input_payload or {})
    task_payload = dict(task.input_payload or {})
    execution_mode = normalize_execution_mode(
        str(step_payload.get("execution_mode") or task_payload.get("execution_mode") or "auto")
    )
    step_kind = str(
        step_payload.get("step_kind")
        or infer_step_kind(task.title, task.description, execution_mode=execution_mode)
    )
    executor_kind = str(step_payload.get("executor_kind") or "agent")
    required_capabilities = list(
        step_payload.get("required_capabilities") or default_required_capabilities(step_kind)
    )
    suggested_agent_ids = [
        str(agent_id).strip()
        for agent_id in list(step_payload.get("suggested_agent_ids") or [])
        if str(agent_id).strip()
    ]

    step_payload.update(
        {
            "step_kind": step_kind,
            "executor_kind": executor_kind,
            "execution_mode": execution_mode,
            "required_capabilities": required_capabilities,
            "suggested_agent_ids": suggested_agent_ids,
        }
    )
    pending_step.input_payload = step_payload
    task.input_payload = {
        **(task.input_payload or {}),
        "step_kind": step_kind,
        "execution_mode": execution_mode,
        "required_capabilities": required_capabilities,
        "suggested_agent_ids": suggested_agent_ids,
        "assignment_source": "project_execution_scheduler",
    }

    if step_kind == "host_action":
        try:
            selection = ProjectAgentProvisioner().select_or_provision_agent(
                project_id=run.project_id,
                step_kind=step_kind,
                required_capabilities=required_capabilities,
                current_user=current_user,
                run_id=run.run_id,
                required_runtime_types=["external_worktree", "external_same_dir", "remote_session"],
                suggested_agent_ids=suggested_agent_ids,
            )
        except ProjectExternalRuntimeUnavailableError as exc:
            return (
                _block_pending_step(
                    session,
                    pending_step=pending_step,
                    task=task,
                    run=run,
                    current_user=current_user,
                    reason=str(exc),
                ),
                None,
            )
        return (
            _queue_external_agent_dispatch(
                session,
                selection=selection,
                run=run,
                pending_step=pending_step,
                task=task,
                project=project,
                current_user=current_user,
                descriptor=descriptor,
                step_kind=step_kind,
            ),
            None,
        )

    selection = ProjectAgentProvisioner().select_or_provision_agent(
        project_id=run.project_id,
        step_kind=step_kind,
        required_capabilities=required_capabilities,
        current_user=current_user,
        run_id=run.run_id,
        suggested_agent_ids=suggested_agent_ids,
    )
    if selection.runtime_type in EXTERNAL_RUNTIME_TYPES:
        return (
            _queue_external_agent_dispatch(
                session,
                selection=selection,
                run=run,
                pending_step=pending_step,
                task=task,
                project=project,
                current_user=current_user,
                descriptor=descriptor,
                step_kind=step_kind,
            ),
            None,
        )

    task.assignee_agent_id = selection.agent_id
    task.status = "assigned"
    task.error_message = None
    pending_step.status = "assigned"
    pending_step.error_message = None
    run.status = "scheduled"
    run.error_message = None
    run.completed_at = None
    run.runtime_context = {
        **(run.runtime_context or {}),
        "agent_assignment": {
            "executor_kind": "agent",
            "agent_id": str(selection.agent_id),
            "selection_reason": selection.selection_reason,
            "provisioned_agent": selection.provisioned_agent,
            "runtime_type": selection.runtime_type,
        },
    }
    task.input_payload = {
        **(task.input_payload or {}),
        "assigned_agent_id": str(selection.agent_id),
        "assigned_agent_name": selection.agent_name,
        "selection_reason": selection.selection_reason,
        "runtime_type": selection.runtime_type,
    }
    pending_step.input_payload = {
        **pending_step.input_payload,
        "assigned_agent_id": str(selection.agent_id),
        "assigned_agent_name": selection.agent_name,
        "selection_reason": selection.selection_reason,
    }
    flush_and_refresh(session, task)
    flush_and_refresh(session, pending_step)
    flush_and_refresh(session, run)
    append_audit_event(
        session,
        action="run-step.assigned",
        resource_type="project_run_step",
        resource_id=pending_step.run_step_id,
        project_id=run.project_id,
        run_id=run.run_id,
        current_user=current_user,
        payload={
            "agent_id": str(selection.agent_id),
            "selection_reason": selection.selection_reason,
            "provisioned_agent": selection.provisioned_agent,
        },
    )

    return (
        {
            "executor_kind": "agent",
            "agent_id": selection.agent_id,
            "dispatch_id": None,
            "selection_reason": selection.selection_reason,
            "provisioned_agent": selection.provisioned_agent,
            "runtime_type": selection.runtime_type,
            "external_dispatch": None,
        },
        pending_step.run_step_id,
    )

async def schedule_run_after_launch(*, run_id: UUID, current_user: CurrentUser) -> dict[str, Any]:
    descriptor = _ensure_run_workspace(run_id=run_id)
    assignment = await _schedule_next_pending_step(
        run_id=run_id,
        current_user=current_user,
        auto_execute=_auto_execute_enabled(),
        descriptor=descriptor,
    )
    return {
        "agent_assignment": assignment,
        "executor_assignment": assignment,
        "external_dispatch": assignment.get("external_dispatch") if isinstance(assignment, dict) else None,
        "run_workspace": {
            "workspace_id": str(run_id),
            "root_path": str(descriptor.run_workspace_root),
            "sandbox_mode": descriptor.sandbox_mode,
        },
    }


def _ensure_run_workspace(*, run_id: UUID) -> RunWorkspaceDescriptor:
    workspace_manager = get_run_workspace_manager()
    with get_db_session() as session:
        run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()
        if run is None:
            raise RuntimeError(f"Run {run_id} not found")
        descriptor = workspace_manager.create_run_workspace(run.project_id, run.run_id)
        project_space = (
            session.query(ProjectSpace)
            .filter(ProjectSpace.project_id == run.project_id)
            .first()
        )
        if project_space is None:
            project_space = ProjectSpace(
                project_id=run.project_id,
                status="active",
                root_path=str(descriptor.project_space_root),
                space_metadata={"sandbox_mode": descriptor.sandbox_mode},
            )
            session.add(project_space)
        else:
            project_space.root_path = str(descriptor.project_space_root)
            project_space.status = "active"
            project_space.space_metadata = {
                **(project_space.space_metadata or {}),
                "sandbox_mode": descriptor.sandbox_mode,
            }
        run.runtime_context = {
            **(run.runtime_context or {}),
            "run_workspace": {
                "workspace_id": str(run.run_id),
                "root_path": str(descriptor.run_workspace_root),
                "sandbox_mode": descriptor.sandbox_mode,
            },
        }
        flush_and_refresh(session, run)
        flush_and_refresh(session, project_space)
        return descriptor


async def _schedule_next_pending_step(
    *,
    run_id: UUID,
    current_user: CurrentUser,
    auto_execute: bool,
    descriptor: Optional[RunWorkspaceDescriptor] = None,
) -> Optional[dict[str, Any]]:
    with get_db_session() as session:
        run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()
        if run is None:
            return None
        pending_steps = (
            session.query(ProjectRunStep)
            .filter(ProjectRunStep.run_id == run_id)
            .filter(ProjectRunStep.status.in_(["pending", "queued"]))
            .order_by(ProjectRunStep.sequence_number.asc(), ProjectRunStep.created_at.asc())
            .all()
        )
        if not pending_steps:
            if run.status not in {"completed", "failed", "cancelled", "blocked"}:
                run.status = "completed"
                run.completed_at = datetime.now(timezone.utc)
                flush_and_refresh(session, run)
                retire_ephemeral_run_agents(session, run=run)
                append_audit_event(
                    session,
                    action="run.completed",
                    resource_type="project_run",
                    resource_id=run.run_id,
                    project_id=run.project_id,
                    run_id=run.run_id,
                    current_user=current_user,
                )
                reconcile_run_state(session, run=run)
            return None
        all_steps = (
            session.query(ProjectRunStep)
            .filter(ProjectRunStep.run_id == run_id)
            .order_by(ProjectRunStep.sequence_number.asc(), ProjectRunStep.created_at.asc())
            .all()
        )
        completed_step_ids = {
            str(step.run_step_id)
            for step in all_steps
            if str(step.status or "").strip().lower() in _TERMINAL_STEP_STATUSES
        }
        ready_steps = [
            step for step in pending_steps if _step_is_ready(step, completed_step_ids)
        ]
        if not ready_steps:
            return None
        first_assignment: Optional[dict[str, Any]] = None
        auto_execute_step_ids: list[UUID] = []
        for pending_step in ready_steps:
            assignment, execute_step_id = _schedule_ready_step(
                session,
                run=run,
                pending_step=pending_step,
                current_user=current_user,
                descriptor=descriptor,
            )
            if first_assignment is None:
                first_assignment = assignment
            if execute_step_id is not None:
                auto_execute_step_ids.append(execute_step_id)

    if auto_execute:
        for step_id in auto_execute_step_ids:
            asyncio.create_task(
                execute_assigned_step(
                    step_id=step_id,
                    current_user=current_user,
                    descriptor=descriptor,
                )
            )

    return first_assignment


async def execute_assigned_step(
    *,
    step_id: UUID,
    current_user: CurrentUser,
    descriptor: Optional[RunWorkspaceDescriptor] = None,
) -> None:
    registry = get_agent_registry()
    with get_db_session() as session:
        step = session.query(ProjectRunStep).filter(ProjectRunStep.run_step_id == step_id).first()
        if step is None:
            return
        run = session.query(ProjectRun).filter(ProjectRun.run_id == step.run_id).first()
        task = (
            session.query(ProjectTask).filter(ProjectTask.project_task_id == step.project_task_id).first()
            if step.project_task_id
            else None
        )
        if run is None or task is None or task.assignee_agent_id is None:
            return
        project = session.query(Project).filter(Project.project_id == run.project_id).first()
        if descriptor is None:
            descriptor = _ensure_run_workspace(run_id=run.run_id)
        step_payload = dict(step.input_payload or {})
        selection_reason = str(step_payload.get("selection_reason") or "")
        step_kind = str(step_payload.get("step_kind") or "implementation")
        agent_id = task.assignee_agent_id
        conversation = AgentConversation(
            agent_id=agent_id,
            owner_user_id=UUID(str(current_user.user_id)),
            title=build_default_conversation_title(),
            status="active",
            source="project_execution",
        )
        session.add(conversation)
        session.flush()
        run.runtime_context = {
            **(run.runtime_context or {}),
            "conversation_id": str(conversation.conversation_id),
            "run_workspace": {
                "workspace_id": str(run.run_id),
                "root_path": str(descriptor.run_workspace_root),
                "sandbox_mode": descriptor.sandbox_mode,
            },
        }
        step.input_payload = {
            **step_payload,
            "conversation_id": str(conversation.conversation_id),
            "run_workspace_root": str(descriptor.run_workspace_root),
        }
        step.status = "running"
        step.started_at = datetime.now(timezone.utc)
        task.status = "running"
        run.status = "running"
        if run.started_at is None:
            run.started_at = datetime.now(timezone.utc)
        flush_and_refresh(session, conversation)
        flush_and_refresh(session, run)
        flush_and_refresh(session, task)
        flush_and_refresh(session, step)
        append_audit_event(
            session,
            action="run-step.started",
            resource_type="project_run_step",
            resource_id=step.run_step_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload={"agent_id": str(agent_id)},
        )
        principal = build_conversation_execution_principal(
            user_id=current_user.user_id,
            role=current_user.role,
            username=current_user.username,
        )
        title = task.title
        description = task.description
        conversation_id = conversation.conversation_id
        project_id = run.project_id
        run_id = run.run_id
        project_title = project.name if project else "Project"
    try:
        runtime_service = get_persistent_conversation_runtime_service()
        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                raise RuntimeError("Conversation not found for project execution")
        runtime, _ = await runtime_service.get_or_create_runtime(conversation=conversation)
        workspace_manager = get_run_workspace_manager()
        await asyncio.to_thread(
            workspace_manager.materialize_to_runtime,
            descriptor.run_workspace_root,
            runtime.workdir,
        )
        registry.update_agent(agent_id=agent_id, status="working")
        result = await execute_persistent_conversation_turn(
            conversation=conversation,
            principal=principal,
            message=build_project_execution_prompt(
                project_title=project_title,
                task_title=title,
                task_description=description,
                step_name=title,
                step_kind=step_kind,
                selection_reason=selection_reason,
                run_workspace_root=str(descriptor.run_workspace_root),
            ),
            files=[],
            source="project_execution",
            chunk_callback=None,
            persist_input_message=True,
            input_message_role="system",
            input_message_text=f"Project execution step: {title}",
            execution_intent_text=f"Complete project task step: {title}",
            title_seed_text=title,
            context_origin_surface="project_execution",
            extra_execution_context={
                "project_execution": True,
                "project_id": str(project_id),
                "run_id": str(run_id),
                "step_id": str(step_id),
                "run_workspace_root": str(descriptor.run_workspace_root),
            },
        )
        await asyncio.to_thread(
            workspace_manager.capture_runtime,
            runtime.workdir,
            descriptor.run_workspace_root,
        )
        await asyncio.to_thread(
            workspace_manager.promote_run_workspace,
            descriptor.run_workspace_root,
            descriptor.project_space_root,
        )
        with get_db_session() as session:
            step = session.query(ProjectRunStep).filter(ProjectRunStep.run_step_id == step_id).first()
            run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()
            task = (
                session.query(ProjectTask).filter(ProjectTask.project_task_id == step.project_task_id).first()
                if step and step.project_task_id
                else None
            )
            if step is None or run is None or task is None:
                return
            step.status = "completed"
            step.completed_at = datetime.now(timezone.utc)
            step.output_payload = {
                **(step.output_payload or {}),
                "conversation_id": str(conversation_id),
                "output": result.get("output"),
                "artifacts": result.get("artifact_delta") or result.get("artifacts") or [],
            }
            task.output_payload = {
                **(task.output_payload or {}),
                "last_output": result.get("output"),
                "conversation_id": str(conversation_id),
                "run_workspace_root": str(descriptor.run_workspace_root),
            }
            flush_and_refresh(session, step)
            reconcile_run_state(session, run=run)
            append_audit_event(
                session,
                action="run-step.completed",
                resource_type="project_run_step",
                resource_id=step.run_step_id,
                project_id=run.project_id,
                run_id=run.run_id,
                current_user=current_user,
                payload={"conversation_id": str(conversation_id)},
            )
        registry.update_agent(agent_id=agent_id, status="idle")
        await _schedule_next_pending_step(
            run_id=run_id,
            current_user=current_user,
            auto_execute=True,
            descriptor=descriptor,
        )
    except Exception as exc:  # noqa: BLE001
        registry.update_agent(agent_id=agent_id, status="idle")
        with get_db_session() as session:
            step = session.query(ProjectRunStep).filter(ProjectRunStep.run_step_id == step_id).first()
            run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()
            task = (
                session.query(ProjectTask).filter(ProjectTask.project_task_id == step.project_task_id).first()
                if step and step.project_task_id
                else None
            )
            if step is not None:
                step.status = "failed"
                step.error_message = str(exc)
                step.completed_at = datetime.now(timezone.utc)
                flush_and_refresh(session, step)
            if task is not None:
                task.status = "failed"
                task.error_message = str(exc)
                flush_and_refresh(session, task)
            if run is not None:
                run.status = "failed"
                run.error_message = str(exc)
                run.completed_at = datetime.now(timezone.utc)
                flush_and_refresh(session, run)
                reconcile_run_state(session, run=run)
                append_audit_event(
                    session,
                    action="run-step.failed",
                    resource_type="project_run_step",
                    resource_id=step.run_step_id if step else None,
                    project_id=run.project_id,
                    run_id=run.run_id,
                    current_user=current_user,
                    payload={"error": str(exc)},
                )
        logger.error("Project execution step failed: %s", exc, exc_info=True)


def build_external_agent_prompt(
    *,
    project_title: str,
    task_title: str,
    task_description: Optional[str],
    step_name: str,
    step_kind: str,
    selection_reason: str,
    runtime_type: str,
    run_workspace_root: str,
) -> str:
    return (
        f"Project: {project_title}\n"
        f"Task: {task_title}\n"
        f"Task description: {task_description or 'N/A'}\n"
        f"Current step: {step_name}\n"
        f"Step kind: {step_kind}\n"
        f"Runtime type: {runtime_type}\n"
        f"Selection reason: {selection_reason}\n\n"
        "You are an external LinX agent running on a host-backed runtime.\n"
        f"Use the working directory provided by the host node. Expected workspace root: {run_workspace_root}\n"
        "Prefer making deterministic, host-safe changes and report exact artifacts/diffs.\n"
        "If you need to use shell, git, browser, or host tools, do so inside the assigned runtime working directory and summarize the outcome clearly."
    )




def build_project_execution_prompt(
    *,
    project_title: str,
    task_title: str,
    task_description: Optional[str],
    step_name: str,
    step_kind: str,
    selection_reason: str,
    run_workspace_root: str,
) -> str:
    return (
        f"Project: {project_title}\n"
        f"Task: {task_title}\n"
        f"Task description: {task_description or 'N/A'}\n"
        f"Current step: {step_name}\n"
        f"Step kind: {step_kind}\n"
        f"Selection reason: {selection_reason}\n\n"
        "You are executing a project task step inside the LinX run sandbox.\n"
        "Work only inside /workspace, which is the current run workspace.\n"
        "Use these shared directories when appropriate:\n"
        "- /workspace/.linx/shared\n"
        "- /workspace/.linx/scratchpad\n"
        "- /workspace/.linx/artifacts\n\n"
        f"The underlying run workspace root on the host is: {run_workspace_root}\n"
        "Deliver concrete files and a concise final summary. If you create artifacts, place them under /workspace or /workspace/.linx/artifacts."
    )
