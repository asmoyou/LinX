"""Minimal CRUD/workflow routers for the project execution platform skeleton."""

import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError

from access_control.permissions import CurrentUser, get_current_user
from api_gateway.routers import agents as agents_router
from database.connection import get_db_session
from database.models import Agent
from database.project_execution_models import (
    ExecutionNode,
    AgentProvisioningProfile,
    ExternalAgentDispatch,
    Project,
    ProjectAgentBinding,
    ProjectExtensionPackage,
    ProjectPlan,
    ProjectRun,
    ProjectSkillPackage,
    ProjectSpace,
    ProjectTask,
    ProjectTaskChangeBundle,
    ProjectTaskEvidenceBundle,
    ProjectTaskHandoff,
    ProjectTaskReviewIssue,
)
from project_execution.model_planner import ProjectExecutionPlanner
from project_execution.read_models import (
    build_run_node_read_models,
    build_run_runtime_session_read_models,
    build_project_detail_read_model,
    build_task_attempt_read_models,
    build_project_task_detail_read_model,
    build_run_detail_read_model,
)
from project_execution.run_workspace_manager import get_run_workspace_manager
from project_execution.schemas import (
    AgentProvisioningProfileCreate,
    AgentProvisioningProfileResponse,
    AgentProvisioningProfileUpdate,
    ExecutionAttemptNodeReadModel,
    ExecutionAttemptNodeCreateRequest,
    ExecutionAttemptNodeStatusRequest,
    ExecutionAttemptNodeUpdateRequest,
    ExecutionAttemptReadModel,
    ExternalAgentDispatchResponse,
    ExtensionPackageCreate,
    ExtensionPackageResponse,
    ExtensionPackageUpdate,
    PlanStatusRequest,
    ProjectAgentBindingCreate,
    ProjectAgentBindingResponse,
    ProjectAgentBindingUpdate,
    ProjectCreate,
    ProjectDetailReadModel,
    ProjectPlanCreate,
    ProjectPlanResponse,
    ProjectPlanUpdate,
    ProjectResponse,
    ProjectRunCreate,
    ProjectRunResponse,
    ProjectRunUpdate,
    ProjectSpaceResponse,
    ProjectSpaceUpsert,
    ProjectTaskCreate,
    ProjectTaskCreateAndLaunchRequest,
    TaskContractReadModel,
    TaskContractUpsertRequest,
    TaskChangeBundleCreateRequest,
    TaskChangeBundleReadModel,
    TaskDependencyReadModel,
    TaskDependencyReplaceRequest,
    TaskEvidenceBundleCreateRequest,
    TaskEvidenceBundleReadModel,
    TaskHandoffCreateRequest,
    TaskHandoffReadModel,
    ProjectTaskDetailReadModel,
    ProjectTaskLaunchBundleResponse,
    ProjectTaskResponse,
    ProjectTaskUpdate,
    ProjectUpdate,
    RunDetailReadModel,
    RunSchedulingResponse,
    RunTransitionRequest,
    RuntimeSessionReadModel,
    SkillImportRequest,
    SkillPackageResponse,
    SkillPackageTestRequest,
    TaskReviewIssueCreateRequest,
    TaskReviewIssueReadModel,
    TaskReviewIssueUpdateRequest,
    TaskTransitionRequest,
)
from project_execution.delivery_records import (
    create_task_change_bundle,
    create_task_evidence_bundle,
    create_task_handoff,
    create_task_review_issue,
    update_task_review_issue,
)
from project_execution.execution_nodes import create_execution_node
from project_execution.scheduler import schedule_run_after_launch
from project_execution.service import (
    append_audit_event,
    apply_updates,
    create_project_task_and_launch_run,
    ensure_related_records,
    flush_and_refresh,
    get_current_user_uuid,
    get_or_404,
    launch_existing_project_task_run,
    parse_uuid,
    reconcile_project_state,
    reconcile_run_state,
)
from project_execution.task_contracts import (
    create_manual_task_contract,
    ensure_task_contract,
    get_latest_task_contract,
)
from project_execution.task_dependencies import (
    compute_task_readiness,
    DependencyCycleError,
    DependencyValidationError,
    build_dependency_snapshot,
    replace_task_dependencies,
    summarize_task_blockers,
)
from shared.logging import get_logger

logger = get_logger(__name__)

projects_router = APIRouter()
project_tasks_router = APIRouter()
plans_router = APIRouter()
runs_router = APIRouter()
attempts_router = APIRouter()
project_space_router = APIRouter()
extensions_router = APIRouter()
skills_import_router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _handle_integrity_error(exc: IntegrityError, *, duplicate_detail: str) -> None:
    logger.warning("Project execution integrity error: %s", exc)
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=duplicate_detail) from exc


def _load_owned_project_or_404(session, *, project_id: UUID, current_user: CurrentUser) -> Project:
    project = get_or_404(session, Project, Project.project_id, project_id, "Project not found")
    if str(project.created_by_user_id) != str(current_user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _load_owned_run_or_404(session, *, run_id: UUID, current_user: CurrentUser) -> ProjectRun:
    run = get_or_404(session, ProjectRun, ProjectRun.run_id, run_id, "Run not found")
    project = get_or_404(session, Project, Project.project_id, run.project_id, "Project not found")
    if str(project.created_by_user_id) != str(current_user.user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


def _resolve_project_space_root(project_id: UUID, project_space: Optional[ProjectSpace]) -> Path:
    root_path = (
        getattr(project_space, "root_path", None)
        or str(get_run_workspace_manager().get_project_space_root(project_id))
    )
    return Path(root_path)


def _resolve_run_workspace_root(run: ProjectRun) -> Path:
    runtime_context = run.runtime_context if isinstance(run.runtime_context, dict) else {}
    run_workspace = (
        runtime_context.get("run_workspace")
        if isinstance(runtime_context.get("run_workspace"), dict)
        else {}
    )
    root_path = run_workspace.get("root_path") or str(
        get_run_workspace_manager().get_run_workspace_root(run.project_id, run.run_id)
    )
    return Path(str(root_path))


def _build_planner_context(
    session,
    *,
    project_id: UUID,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    project = get_or_404(session, Project, Project.project_id, project_id, "Project not found")
    bindings = (
        session.query(ProjectAgentBinding)
        .filter(ProjectAgentBinding.project_id == project_id)
        .filter(ProjectAgentBinding.status == "active")
        .all()
    )
    binding_agent_ids = [binding.agent_id for binding in bindings]
    agents_by_id = {
        agent.agent_id: agent
        for agent in (
            session.query(Agent)
            .filter(Agent.agent_id.in_(binding_agent_ids))
            .all()
            if binding_agent_ids
            else []
        )
    }
    available_agents: list[dict[str, object]] = []
    for binding in bindings:
        agent = agents_by_id.get(binding.agent_id)
        available_agents.append(
            {
                "id": str(binding.agent_id),
                "name": getattr(agent, "name", str(binding.agent_id)),
                "type": getattr(agent, "agent_type", None),
                "runtime_preference": getattr(agent, "runtime_preference", None),
                "preferred_runtime_types": list(binding.preferred_runtime_types or []),
                "allowed_step_kinds": list(binding.allowed_step_kinds or []),
                "preferred_skills": list(binding.preferred_skills or []),
            }
        )

    return (
        {
            "project_id": str(project.project_id),
            "project_name": project.name,
            "project_description": project.description,
        },
        available_agents,
    )


def _planner_questions_to_response(planner_result) -> list[dict[str, str]]:
    return [question.model_dump() for question in planner_result.clarification_questions]


def _execution_node_to_read_model(node: ExecutionNode) -> ExecutionAttemptNodeReadModel:
    payload = node.node_payload if isinstance(node.node_payload, dict) else {}
    dependency_node_ids = payload.get("dependency_node_ids")
    if not isinstance(dependency_node_ids, list):
        dependency_node_ids = node.dependency_node_ids if isinstance(node.dependency_node_ids, list) else []
    suggested_agent_ids = payload.get("suggested_agent_ids")
    if not isinstance(suggested_agent_ids, list):
        suggested_agent_ids = []
    return ExecutionAttemptNodeReadModel(
        id=str(node.node_id),
        run_id=str(node.run_id),
        task_id=str(node.project_task_id) if node.project_task_id else None,
        name=node.name,
        node_type=node.node_type,
        status=node.status,
        sequence_number=node.sequence_number,
        execution_mode=str(payload.get("execution_mode") or "").strip() or None,
        executor_kind=str(payload.get("executor_kind") or "").strip() or None,
        runtime_type=str(payload.get("runtime_type") or "").strip() or None,
        suggested_agent_ids=[str(item) for item in suggested_agent_ids if str(item).strip()],
        dependency_step_ids=[str(item) for item in dependency_node_ids if str(item).strip()],
        node_payload=payload,
        result_payload=node.result_payload if isinstance(node.result_payload, dict) else {},
        error_message=node.error_message,
        started_at=node.started_at,
        completed_at=node.completed_at,
        created_at=node.created_at,
        updated_at=node.updated_at,
    )


def _create_execution_step_pair(
    session,
    *,
    run: ProjectRun,
    project_task_id: Optional[UUID],
    name: str,
    node_type: str,
    status_value: str,
    sequence_number: int,
    payload: dict[str, Any],
) -> ExecutionNode:
    node = create_execution_node(
        session,
        run=run,
        project_task_id=project_task_id,
        name=name,
        node_type=node_type,
        status=status_value,
        sequence_number=sequence_number,
        node_payload=payload,
    )
    return node


def _update_execution_node_and_sync_step(
    session,
    *,
    node: ExecutionNode,
    request: ExecutionAttemptNodeUpdateRequest,
) -> ExecutionNode:
    if request.project_task_id is not None:
        node.project_task_id = request.project_task_id
    if request.name is not None:
        node.name = request.name
    if request.node_type is not None:
        node.node_type = request.node_type
    if request.status is not None:
        node.status = request.status
    if request.sequence_number is not None:
        node.sequence_number = request.sequence_number
    if request.node_payload is not None:
        node.node_payload = request.node_payload
    if request.result_payload is not None:
        node.result_payload = request.result_payload
    if request.error_message is not None:
        node.error_message = request.error_message
    flush_and_refresh(session, node)
    return node


def _complete_execution_node_and_sync_step(
    session,
    *,
    node: ExecutionNode,
    request: ExecutionAttemptNodeStatusRequest,
) -> ExecutionNode:
    node.status = request.status
    node.result_payload = request.result_payload
    node.error_message = request.error_message
    if node.started_at is None:
        node.started_at = _utc_now()
    node.completed_at = _utc_now()
    flush_and_refresh(session, node)
    return node


def _resolve_execution_reference(
    session,
    *,
    task: ProjectTask,
    run_id: Optional[UUID],
    node_id: Optional[str],
) -> Optional[UUID]:
    parsed_node_id = parse_uuid(node_id, "node_id") if node_id else None

    if parsed_node_id is not None:
        node = get_or_404(session, ExecutionNode, ExecutionNode.node_id, parsed_node_id, "Execution node not found")
        if node.project_task_id and node.project_task_id != task.project_task_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution node not found")
        if run_id is not None and node.run_id != run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution node not found")
    return parsed_node_id


@runs_router.get(
    "/{run_id}/external-dispatches", response_model=list[ExternalAgentDispatchResponse]
)
async def list_run_external_dispatches(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        if str(run.requested_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return (
            session.query(ExternalAgentDispatch)
            .filter(ExternalAgentDispatch.run_id == parsed_run_id)
            .order_by(ExternalAgentDispatch.created_at.asc())
            .all()
        )


@projects_router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        normalized_status = str(request.status or "").strip().lower() or "planning"
        if normalized_status == "draft":
            normalized_status = "planning"
        project = Project(
            name=request.name,
            description=request.description,
            status=normalized_status,
            configuration=request.configuration,
            created_by_user_id=actor_user_id,
        )
        session.add(project)
        try:
            flush_and_refresh(session, project)
        except IntegrityError as exc:
            _handle_integrity_error(exc, duplicate_detail="Project could not be created")

        append_audit_event(
            session,
            action="project.created",
            resource_type="project",
            resource_id=project.project_id,
            project_id=project.project_id,
            current_user=current_user,
            payload={"status": project.status},
        )
        return project


@projects_router.get("", response_model=list[ProjectResponse])
async def list_projects(current_user: CurrentUser = Depends(get_current_user)):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        projects = (
            session.query(Project)
            .filter(Project.created_by_user_id == actor_user_id)
            .order_by(Project.created_at.desc())
            .all()
        )
        for project in projects:
            reconcile_project_state(session, project=project)
        return projects


@projects_router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = _load_owned_project_or_404(
            session, project_id=parsed_project_id, current_user=current_user
        )
        reconcile_project_state(session, project=project)
        return project


@projects_router.get("/{project_id}/detail", response_model=ProjectDetailReadModel)
async def get_project_detail(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = _load_owned_project_or_404(
            session, project_id=parsed_project_id, current_user=current_user
        )
        return build_project_detail_read_model(session, project=project)


@projects_router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    request: ProjectUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = _load_owned_project_or_404(
            session, project_id=parsed_project_id, current_user=current_user
        )

        apply_updates(project, request, ["name", "description", "status", "configuration"])
        flush_and_refresh(session, project)
        reconcile_project_state(session, project=project)
        append_audit_event(
            session,
            action="project.updated",
            resource_type="project",
            resource_id=project.project_id,
            project_id=project.project_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        return project


@projects_router.post("/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = _load_owned_project_or_404(
            session, project_id=parsed_project_id, current_user=current_user
        )

        project.status = "archived"
        flush_and_refresh(session, project)
        append_audit_event(
            session,
            action="project.archived",
            resource_type="project",
            resource_id=project.project_id,
            project_id=project.project_id,
            current_user=current_user,
        )
        return project


@projects_router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = _load_owned_project_or_404(
            session, project_id=parsed_project_id, current_user=current_user
        )

        append_audit_event(
            session,
            action="project.deleted",
            resource_type="project",
            resource_id=project.project_id,
            project_id=project.project_id,
            current_user=current_user,
        )
        session.delete(project)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@projects_router.get(
    "/{project_id}/agent-bindings", response_model=list[ProjectAgentBindingResponse]
)
async def list_project_agent_bindings(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = _load_owned_project_or_404(
            session, project_id=parsed_project_id, current_user=current_user
        )
        return (
            session.query(ProjectAgentBinding)
            .filter(ProjectAgentBinding.project_id == parsed_project_id)
            .order_by(ProjectAgentBinding.priority.desc(), ProjectAgentBinding.created_at.asc())
            .all()
        )


@projects_router.post(
    "/{project_id}/agent-bindings",
    response_model=ProjectAgentBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_agent_binding(
    project_id: str,
    request: ProjectAgentBindingCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = _load_owned_project_or_404(
            session, project_id=parsed_project_id, current_user=current_user
        )
        binding = ProjectAgentBinding(
            project_id=parsed_project_id,
            agent_id=request.agent_id,
            role_hint=request.role_hint,
            priority=request.priority,
            status=request.status,
            allowed_step_kinds=request.allowed_step_kinds,
            preferred_skills=request.preferred_skills,
            preferred_runtime_types=request.preferred_runtime_types,
        )
        session.add(binding)
        try:
            flush_and_refresh(session, binding)
        except IntegrityError as exc:
            _handle_integrity_error(
                exc, duplicate_detail="Project agent binding could not be created"
            )
        append_audit_event(
            session,
            action="project-agent-binding.created",
            resource_type="project_agent_binding",
            resource_id=binding.binding_id,
            project_id=parsed_project_id,
            current_user=current_user,
        )
        return binding


@projects_router.patch(
    "/{project_id}/agent-bindings/{binding_id}", response_model=ProjectAgentBindingResponse
)
async def update_project_agent_binding(
    project_id: str,
    binding_id: str,
    request: ProjectAgentBindingUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_binding_id = parse_uuid(binding_id, "binding_id")
    with get_db_session() as session:
        binding = get_or_404(
            session,
            ProjectAgentBinding,
            ProjectAgentBinding.binding_id,
            parsed_binding_id,
            "Project agent binding not found",
        )
        if str(binding.project_id) != str(parsed_project_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project agent binding not found"
            )
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        apply_updates(
            binding,
            request,
            [
                "role_hint",
                "priority",
                "status",
                "allowed_step_kinds",
                "preferred_skills",
                "preferred_runtime_types",
            ],
        )
        flush_and_refresh(session, binding)
        return binding


@projects_router.delete(
    "/{project_id}/agent-bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_project_agent_binding(
    project_id: str,
    binding_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_binding_id = parse_uuid(binding_id, "binding_id")
    with get_db_session() as session:
        binding = get_or_404(
            session,
            ProjectAgentBinding,
            ProjectAgentBinding.binding_id,
            parsed_binding_id,
            "Project agent binding not found",
        )
        if str(binding.project_id) != str(parsed_project_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project agent binding not found"
            )
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        session.delete(binding)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@projects_router.get(
    "/{project_id}/agent-provisioning-profiles",
    response_model=list[AgentProvisioningProfileResponse],
)
async def list_agent_provisioning_profiles(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return (
            session.query(AgentProvisioningProfile)
            .filter(AgentProvisioningProfile.project_id == parsed_project_id)
            .order_by(AgentProvisioningProfile.step_kind.asc())
            .all()
        )


@projects_router.post(
    "/{project_id}/agent-provisioning-profiles",
    response_model=AgentProvisioningProfileResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_provisioning_profile(
    project_id: str,
    request: AgentProvisioningProfileCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        profile = AgentProvisioningProfile(
            project_id=parsed_project_id,
            step_kind=request.step_kind,
            agent_type=request.agent_type,
            template_id=request.template_id,
            default_skill_ids=request.default_skill_ids,
            default_provider=request.default_provider,
            default_model=request.default_model,
            runtime_type=request.runtime_type,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            sandbox_mode=request.sandbox_mode,
            ephemeral=request.ephemeral,
        )
        session.add(profile)
        try:
            flush_and_refresh(session, profile)
        except IntegrityError as exc:
            _handle_integrity_error(
                exc, duplicate_detail="Agent provisioning profile could not be created"
            )
        append_audit_event(
            session,
            action="agent-provisioning-profile.created",
            resource_type="agent_provisioning_profile",
            resource_id=profile.profile_id,
            project_id=parsed_project_id,
            current_user=current_user,
        )
        return profile


@projects_router.patch(
    "/{project_id}/agent-provisioning-profiles/{profile_id}",
    response_model=AgentProvisioningProfileResponse,
)
async def update_agent_provisioning_profile(
    project_id: str,
    profile_id: str,
    request: AgentProvisioningProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_profile_id = parse_uuid(profile_id, "profile_id")
    with get_db_session() as session:
        profile = get_or_404(
            session,
            AgentProvisioningProfile,
            AgentProvisioningProfile.profile_id,
            parsed_profile_id,
            "Agent provisioning profile not found",
        )
        if str(profile.project_id) != str(parsed_project_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Agent provisioning profile not found"
            )
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        apply_updates(
            profile,
            request,
            [
                "agent_type",
                "template_id",
                "default_skill_ids",
                "default_provider",
                "default_model",
                "runtime_type",
                "temperature",
                "max_tokens",
                "sandbox_mode",
                "ephemeral",
            ],
        )
        flush_and_refresh(session, profile)
        return profile


@projects_router.delete(
    "/{project_id}/agent-provisioning-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_agent_provisioning_profile(
    project_id: str,
    profile_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_profile_id = parse_uuid(profile_id, "profile_id")
    with get_db_session() as session:
        profile = get_or_404(
            session,
            AgentProvisioningProfile,
            AgentProvisioningProfile.profile_id,
            parsed_profile_id,
            "Agent provisioning profile not found",
        )
        if str(profile.project_id) != str(parsed_project_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Agent provisioning profile not found"
            )
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        session.delete(profile)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@project_tasks_router.post(
    "/create-and-launch",
    response_model=ProjectTaskLaunchBundleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task_and_launch(
    request: ProjectTaskCreateAndLaunchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        _ = _load_owned_project_or_404(
            session, project_id=request.project_id, current_user=current_user
        )
        project_context, available_agents = _build_planner_context(
            session, project_id=request.project_id
        )

    planner_result = await ProjectExecutionPlanner().plan(
        title=request.title,
        description=request.description,
        execution_mode=request.execution_mode
        or str((request.input_payload or {}).get("execution_mode") or "auto"),
        project_context=project_context,
        available_agents=available_agents,
    )

    with get_db_session() as session:
        try:
            task, plan, run, node = create_project_task_and_launch_run(
                session,
                project_id=request.project_id,
                title=request.title,
                description=request.description,
                priority=request.priority,
                assignee_agent_id=request.assignee_agent_id,
                input_payload={
                    **(request.input_payload or {}),
                    **({"execution_mode": request.execution_mode} if request.execution_mode else {}),
                },
                planner_result=planner_result,
                current_user=current_user,
            )
            ensure_task_contract(
                session,
                task=task,
                actor_user_id=get_current_user_uuid(current_user),
            )
        except IntegrityError as exc:
            _handle_integrity_error(exc, duplicate_detail="Project task could not be created")
        task_id = task.project_task_id
        plan_id = plan.plan_id if plan is not None else None
        run_id = run.run_id if run is not None else None
        node_id = node.node_id if node is not None else None

    scheduling_result = (
        await schedule_run_after_launch(run_id=run_id, current_user=current_user)
        if run_id is not None
        else {}
    )

    with get_db_session() as session:
        task = get_or_404(
            session, ProjectTask, ProjectTask.project_task_id, task_id, "Project task not found"
        )
        plan = (
            get_or_404(session, ProjectPlan, ProjectPlan.plan_id, plan_id, "Plan not found")
            if plan_id is not None
            else None
        )
        run = (
            get_or_404(session, ProjectRun, ProjectRun.run_id, run_id, "Run not found")
            if run_id is not None
            else None
        )
        node = (
            get_or_404(session, ExecutionNode, ExecutionNode.node_id, node_id, "Execution node not found")
            if node_id is not None
            else None
        )
        return ProjectTaskLaunchBundleResponse(
            task=ProjectTaskResponse.model_validate(task),
            plan=ProjectPlanResponse.model_validate(plan) if plan is not None else None,
            run=ProjectRunResponse.model_validate(run) if run is not None else None,
            node=_execution_node_to_read_model(node) if node is not None else None,
            needs_clarification=planner_result.needs_clarification,
            clarification_questions=_planner_questions_to_response(planner_result),
            agent_assignment=scheduling_result.get("agent_assignment"),
            external_dispatch=scheduling_result.get("external_dispatch"),
            executor_assignment=scheduling_result.get("executor_assignment"),
            run_workspace=scheduling_result.get("run_workspace"),
        )


@project_tasks_router.post(
    "", response_model=ProjectTaskResponse, status_code=status.HTTP_201_CREATED
)
async def create_project_task(
    request: ProjectTaskCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        ensure_related_records(
            session,
            project_id=request.project_id,
            plan_id=request.plan_id,
            run_id=request.run_id,
            agent_id=request.assignee_agent_id,
            require_project=True,
        )
        task = ProjectTask(
            project_id=request.project_id,
            plan_id=request.plan_id,
            run_id=request.run_id,
            assignee_agent_id=request.assignee_agent_id,
            title=request.title,
            description=request.description,
            status=request.status,
            priority=request.priority,
            sort_order=request.sort_order,
            input_payload={
                **(request.input_payload or {}),
                **({"execution_mode": request.execution_mode} if request.execution_mode else {}),
            },
            created_by_user_id=actor_user_id,
        )
        session.add(task)
        flush_and_refresh(session, task)
        ensure_task_contract(session, task=task, actor_user_id=actor_user_id)
        append_audit_event(
            session,
            action="project-task.created",
            resource_type="project_task",
            resource_id=task.project_task_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
        )
        reconcile_project_state(session, project_id=task.project_id)
        return task


@project_tasks_router.post(
    "/{project_task_id}/launch",
    response_model=ProjectTaskLaunchBundleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def launch_existing_project_task(
    project_task_id: str,
    request: ProjectTaskCreateAndLaunchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")

    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        readiness = compute_task_readiness(session, project_task_id=task.project_task_id)
        if not readiness["ready"]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=summarize_task_blockers(readiness) or "Task dependencies are not satisfied",
            )
        project_context, available_agents = _build_planner_context(
            session, project_id=task.project_id
        )

    planner_result = await ProjectExecutionPlanner().plan(
        title=task.title,
        description=task.description,
        execution_mode=request.execution_mode
        or str((task.input_payload or {}).get("execution_mode") or "auto"),
        project_context=project_context,
        available_agents=available_agents,
    )

    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        task, plan, run, node = launch_existing_project_task_run(
            session,
            task=task,
            planner_result=planner_result,
            current_user=current_user,
        )
        ensure_task_contract(
            session,
            task=task,
            actor_user_id=get_current_user_uuid(current_user),
        )
        task_id = task.project_task_id
        plan_id = plan.plan_id if plan is not None else None
        run_id = run.run_id if run is not None else None
        node_id = node.node_id if node is not None else None

    scheduling_result = (
        await schedule_run_after_launch(run_id=run_id, current_user=current_user)
        if run_id is not None
        else {}
    )

    with get_db_session() as session:
        task = get_or_404(
            session, ProjectTask, ProjectTask.project_task_id, task_id, "Project task not found"
        )
        plan = (
            get_or_404(session, ProjectPlan, ProjectPlan.plan_id, plan_id, "Plan not found")
            if plan_id is not None
            else None
        )
        run = (
            get_or_404(session, ProjectRun, ProjectRun.run_id, run_id, "Run not found")
            if run_id is not None
            else None
        )
        node = (
            get_or_404(session, ExecutionNode, ExecutionNode.node_id, node_id, "Execution node not found")
            if node_id is not None
            else None
        )
        return ProjectTaskLaunchBundleResponse(
            task=ProjectTaskResponse.model_validate(task),
            plan=ProjectPlanResponse.model_validate(plan) if plan is not None else None,
            run=ProjectRunResponse.model_validate(run) if run is not None else None,
            node=_execution_node_to_read_model(node) if node is not None else None,
            needs_clarification=planner_result.needs_clarification,
            clarification_questions=_planner_questions_to_response(planner_result),
            agent_assignment=scheduling_result.get("agent_assignment"),
            external_dispatch=scheduling_result.get("external_dispatch"),
            executor_assignment=scheduling_result.get("executor_assignment"),
            run_workspace=scheduling_result.get("run_workspace"),
        )


@project_tasks_router.get("", response_model=list[ProjectTaskResponse])
async def list_project_tasks(
    project_id: Optional[UUID] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        query = session.query(ProjectTask).filter(ProjectTask.created_by_user_id == actor_user_id)
        if project_id:
            query = query.filter(ProjectTask.project_id == project_id)
        return query.order_by(ProjectTask.sort_order.asc(), ProjectTask.created_at.asc()).all()


@project_tasks_router.get("/{project_task_id}", response_model=ProjectTaskResponse)
async def get_project_task(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        return task


@project_tasks_router.get(
    "/{project_task_id}/detail", response_model=ProjectTaskDetailReadModel
)
async def get_project_task_detail(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        if get_latest_task_contract(session, project_task_id=task.project_task_id) is None:
            ensure_task_contract(
                session,
                task=task,
                actor_user_id=get_current_user_uuid(current_user),
            )
        return build_project_task_detail_read_model(session, task=task)


@project_tasks_router.get(
    "/{project_task_id}/attempts", response_model=list[ExecutionAttemptReadModel]
)
async def list_project_task_attempts(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        project = get_or_404(session, Project, Project.project_id, task.project_id, "Project not found")
        return build_task_attempt_read_models(session, task=task, project=project)


@project_tasks_router.get(
    "/{project_task_id}/contract", response_model=TaskContractReadModel
)
async def get_project_task_contract(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        contract = get_latest_task_contract(session, project_task_id=task.project_task_id)
        if contract is None:
            contract = ensure_task_contract(
                session,
                task=task,
                actor_user_id=get_current_user_uuid(current_user),
            )
        return TaskContractReadModel(
            id=str(contract.contract_id),
            task_id=str(contract.project_task_id),
            version=contract.version,
            goal=contract.goal,
            scope=list(contract.scope or []),
            constraints=list(contract.constraints or []),
            deliverables=list(contract.deliverables or []),
            acceptance_criteria=list(contract.acceptance_criteria or []),
            assumptions=list(contract.assumptions or []),
            evidence_required=list(contract.evidence_required or []),
            allowed_surface=contract.allowed_surface or {},
            created_at=contract.created_at,
            updated_at=contract.updated_at,
        )


@project_tasks_router.put(
    "/{project_task_id}/contract", response_model=TaskContractReadModel
)
async def update_project_task_contract(
    project_task_id: str,
    request: TaskContractUpsertRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        contract = create_manual_task_contract(
            session,
            task=task,
            actor_user_id=get_current_user_uuid(current_user),
            payload=request.model_dump(by_alias=False),
        )
        append_audit_event(
            session,
            action="project-task.contract.updated",
            resource_type="project_task_contract",
            resource_id=contract.contract_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
        )
        return TaskContractReadModel(
            id=str(contract.contract_id),
            task_id=str(contract.project_task_id),
            version=contract.version,
            goal=contract.goal,
            scope=list(contract.scope or []),
            constraints=list(contract.constraints or []),
            deliverables=list(contract.deliverables or []),
            acceptance_criteria=list(contract.acceptance_criteria or []),
            assumptions=list(contract.assumptions or []),
            evidence_required=list(contract.evidence_required or []),
            allowed_surface=contract.allowed_surface or {},
            created_at=contract.created_at,
            updated_at=contract.updated_at,
        )


@project_tasks_router.get(
    "/{project_task_id}/dependencies", response_model=list[TaskDependencyReadModel]
)
async def get_project_task_dependencies(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        return [
            TaskDependencyReadModel(**item)
            for item in build_dependency_snapshot(session, project_task_id=task.project_task_id)
        ]


@project_tasks_router.put(
    "/{project_task_id}/dependencies", response_model=list[TaskDependencyReadModel]
)
async def replace_project_task_dependencies(
    project_task_id: str,
    request: TaskDependencyReplaceRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )
        try:
            replace_task_dependencies(
                session,
                task=task,
                dependencies=[item.model_dump(by_alias=False) for item in request.dependencies],
                actor_user_id=get_current_user_uuid(current_user),
            )
        except DependencyValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        except DependencyCycleError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc
        append_audit_event(
            session,
            action="project-task.dependencies.replaced",
            resource_type="project_task",
            resource_id=task.project_task_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
            payload={"dependency_count": len(request.dependencies)},
        )
        return [
            TaskDependencyReadModel(**item)
            for item in build_dependency_snapshot(session, project_task_id=task.project_task_id)
        ]


@project_tasks_router.get(
    "/{project_task_id}/handoffs", response_model=list[TaskHandoffReadModel]
)
async def list_project_task_handoffs(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        rows = (
            session.query(ProjectTaskHandoff)
            .filter(ProjectTaskHandoff.project_task_id == task.project_task_id)
            .order_by(ProjectTaskHandoff.created_at.desc())
            .all()
        )
        return [
            TaskHandoffReadModel(
                id=str(row.handoff_id),
                task_id=str(row.project_task_id),
                run_id=str(row.run_id) if row.run_id else None,
                node_id=str(row.node_id) if row.node_id else None,
                stage=row.stage,
                from_actor=row.from_actor,
                to_actor=row.to_actor,
                status_from=row.status_from,
                status_to=row.status_to,
                title=row.title,
                summary=row.summary,
                payload=row.payload or {},
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


@project_tasks_router.post(
    "/{project_task_id}/handoffs",
    response_model=TaskHandoffReadModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task_handoff(
    project_task_id: str,
    request: TaskHandoffCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        run_id = parse_uuid(request.run_id, "run_id") if request.run_id else None
        ensure_related_records(session, project_id=task.project_id, run_id=run_id)
        node_id = _resolve_execution_reference(
            session,
            task=task,
            run_id=run_id,
            node_id=request.node_id,
        )
        row = create_task_handoff(
            session,
            task=task,
            actor_user_id=get_current_user_uuid(current_user),
            payload={
                **request.model_dump(by_alias=False),
                "run_id": run_id,
                "node_id": node_id,
            },
        )
        append_audit_event(
            session,
            action="project-task.handoff.created",
            resource_type="project_task_handoff",
            resource_id=row.handoff_id,
            project_id=task.project_id,
            run_id=row.run_id,
            current_user=current_user,
            payload={"stage": row.stage, "from_actor": row.from_actor, "to_actor": row.to_actor},
        )
        return TaskHandoffReadModel(
            id=str(row.handoff_id),
            task_id=str(row.project_task_id),
            run_id=str(row.run_id) if row.run_id else None,
            node_id=str(row.node_id) if row.node_id else None,
            stage=row.stage,
            from_actor=row.from_actor,
            to_actor=row.to_actor,
            status_from=row.status_from,
            status_to=row.status_to,
            title=row.title,
            summary=row.summary,
            payload=row.payload or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@project_tasks_router.get(
    "/{project_task_id}/change-bundles", response_model=list[TaskChangeBundleReadModel]
)
async def list_project_task_change_bundles(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        rows = (
            session.query(ProjectTaskChangeBundle)
            .filter(ProjectTaskChangeBundle.project_task_id == task.project_task_id)
            .order_by(ProjectTaskChangeBundle.created_at.desc())
            .all()
        )
        return [
            TaskChangeBundleReadModel(
                id=str(row.change_bundle_id),
                task_id=str(row.project_task_id),
                run_id=str(row.run_id) if row.run_id else None,
                node_id=str(row.node_id) if row.node_id else None,
                bundle_kind=row.bundle_kind,
                status=row.status,
                base_ref=row.base_ref,
                head_ref=row.head_ref,
                summary=row.summary,
                commit_count=row.commit_count,
                changed_files=row.changed_files or [],
                artifact_manifest=row.artifact_manifest or {},
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


@project_tasks_router.post(
    "/{project_task_id}/change-bundles",
    response_model=TaskChangeBundleReadModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task_change_bundle(
    project_task_id: str,
    request: TaskChangeBundleCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        run_id = parse_uuid(request.run_id, "run_id") if request.run_id else None
        ensure_related_records(session, project_id=task.project_id, run_id=run_id)
        node_id = _resolve_execution_reference(
            session,
            task=task,
            run_id=run_id,
            node_id=request.node_id,
        )
        row = create_task_change_bundle(
            session,
            task=task,
            actor_user_id=get_current_user_uuid(current_user),
            payload={
                **request.model_dump(by_alias=False),
                "run_id": run_id,
                "node_id": node_id,
            },
        )
        append_audit_event(
            session,
            action="project-task.change-bundle.created",
            resource_type="project_task_change_bundle",
            resource_id=row.change_bundle_id,
            project_id=task.project_id,
            run_id=row.run_id,
            current_user=current_user,
            payload={"status": row.status, "bundle_kind": row.bundle_kind},
        )
        return TaskChangeBundleReadModel(
            id=str(row.change_bundle_id),
            task_id=str(row.project_task_id),
            run_id=str(row.run_id) if row.run_id else None,
            node_id=str(row.node_id) if row.node_id else None,
            bundle_kind=row.bundle_kind,
            status=row.status,
            base_ref=row.base_ref,
            head_ref=row.head_ref,
            summary=row.summary,
            commit_count=row.commit_count,
            changed_files=row.changed_files or [],
            artifact_manifest=row.artifact_manifest or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@project_tasks_router.get(
    "/{project_task_id}/evidence-bundles", response_model=list[TaskEvidenceBundleReadModel]
)
async def list_project_task_evidence_bundles(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        rows = (
            session.query(ProjectTaskEvidenceBundle)
            .filter(ProjectTaskEvidenceBundle.project_task_id == task.project_task_id)
            .order_by(ProjectTaskEvidenceBundle.created_at.desc())
            .all()
        )
        return [
            TaskEvidenceBundleReadModel(
                id=str(row.evidence_bundle_id),
                task_id=str(row.project_task_id),
                run_id=str(row.run_id) if row.run_id else None,
                node_id=str(row.node_id) if row.node_id else None,
                summary=row.summary,
                status=row.status,
                bundle=row.bundle or {},
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


@project_tasks_router.post(
    "/{project_task_id}/evidence-bundles",
    response_model=TaskEvidenceBundleReadModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task_evidence_bundle(
    project_task_id: str,
    request: TaskEvidenceBundleCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        run_id = parse_uuid(request.run_id, "run_id") if request.run_id else None
        ensure_related_records(session, project_id=task.project_id, run_id=run_id)
        node_id = _resolve_execution_reference(
            session,
            task=task,
            run_id=run_id,
            node_id=request.node_id,
        )
        row = create_task_evidence_bundle(
            session,
            task=task,
            actor_user_id=get_current_user_uuid(current_user),
            payload={
                **request.model_dump(by_alias=False),
                "run_id": run_id,
                "node_id": node_id,
            },
        )
        append_audit_event(
            session,
            action="project-task.evidence-bundle.created",
            resource_type="project_task_evidence_bundle",
            resource_id=row.evidence_bundle_id,
            project_id=task.project_id,
            run_id=row.run_id,
            current_user=current_user,
            payload={"status": row.status},
        )
        return TaskEvidenceBundleReadModel(
            id=str(row.evidence_bundle_id),
            task_id=str(row.project_task_id),
            run_id=str(row.run_id) if row.run_id else None,
            node_id=str(row.node_id) if row.node_id else None,
            summary=row.summary,
            status=row.status,
            bundle=row.bundle or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@project_tasks_router.get(
    "/{project_task_id}/review-issues", response_model=list[TaskReviewIssueReadModel]
)
async def list_project_task_review_issues(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        rows = (
            session.query(ProjectTaskReviewIssue)
            .filter(ProjectTaskReviewIssue.project_task_id == task.project_task_id)
            .order_by(ProjectTaskReviewIssue.created_at.desc())
            .all()
        )
        return [
            TaskReviewIssueReadModel(
                id=str(row.review_issue_id),
                task_id=str(row.project_task_id),
                change_bundle_id=str(row.change_bundle_id) if row.change_bundle_id else None,
                evidence_bundle_id=str(row.evidence_bundle_id) if row.evidence_bundle_id else None,
                handoff_id=str(row.handoff_id) if row.handoff_id else None,
                issue_key=row.issue_key,
                severity=row.severity,
                category=row.category,
                acceptance_ref=row.acceptance_ref,
                summary=row.summary,
                suggestion=row.suggestion,
                status=row.status,
                resolved_at=row.resolved_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]


@project_tasks_router.post(
    "/{project_task_id}/review-issues",
    response_model=TaskReviewIssueReadModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_task_review_issue(
    project_task_id: str,
    request: TaskReviewIssueCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        change_bundle_id = parse_uuid(request.change_bundle_id, "change_bundle_id") if request.change_bundle_id else None
        evidence_bundle_id = parse_uuid(request.evidence_bundle_id, "evidence_bundle_id") if request.evidence_bundle_id else None
        handoff_id = parse_uuid(request.handoff_id, "handoff_id") if request.handoff_id else None
        if change_bundle_id is not None:
            change_bundle = get_or_404(
                session,
                ProjectTaskChangeBundle,
                ProjectTaskChangeBundle.change_bundle_id,
                change_bundle_id,
                "Change bundle not found",
            )
            if change_bundle.project_task_id != task.project_task_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change bundle not found")
        if evidence_bundle_id is not None:
            evidence_bundle = get_or_404(
                session,
                ProjectTaskEvidenceBundle,
                ProjectTaskEvidenceBundle.evidence_bundle_id,
                evidence_bundle_id,
                "Evidence bundle not found",
            )
            if evidence_bundle.project_task_id != task.project_task_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence bundle not found")
        if handoff_id is not None:
            handoff = get_or_404(
                session,
                ProjectTaskHandoff,
                ProjectTaskHandoff.handoff_id,
                handoff_id,
                "Handoff not found",
            )
            if handoff.project_task_id != task.project_task_id:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handoff not found")
        row = create_task_review_issue(
            session,
            task=task,
            actor_user_id=get_current_user_uuid(current_user),
            payload={
                **request.model_dump(by_alias=False),
                "change_bundle_id": change_bundle_id,
                "evidence_bundle_id": evidence_bundle_id,
                "handoff_id": handoff_id,
            },
        )
        append_audit_event(
            session,
            action="project-task.review-issue.created",
            resource_type="project_task_review_issue",
            resource_id=row.review_issue_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
            payload={"severity": row.severity, "category": row.category, "status": row.status},
        )
        return TaskReviewIssueReadModel(
            id=str(row.review_issue_id),
            task_id=str(row.project_task_id),
            change_bundle_id=str(row.change_bundle_id) if row.change_bundle_id else None,
            evidence_bundle_id=str(row.evidence_bundle_id) if row.evidence_bundle_id else None,
            handoff_id=str(row.handoff_id) if row.handoff_id else None,
            issue_key=row.issue_key,
            severity=row.severity,
            category=row.category,
            acceptance_ref=row.acceptance_ref,
            summary=row.summary,
            suggestion=row.suggestion,
            status=row.status,
            resolved_at=row.resolved_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@project_tasks_router.patch(
    "/{project_task_id}/review-issues/{review_issue_id}", response_model=TaskReviewIssueReadModel
)
async def update_project_task_review_issue(
    project_task_id: str,
    review_issue_id: str,
    request: TaskReviewIssueUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    parsed_issue_id = parse_uuid(review_issue_id, "review_issue_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found")
        row = get_or_404(
            session,
            ProjectTaskReviewIssue,
            ProjectTaskReviewIssue.review_issue_id,
            parsed_issue_id,
            "Review issue not found",
        )
        if row.project_task_id != task.project_task_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review issue not found")
        update_task_review_issue(session, issue=row, payload=request.model_dump(by_alias=False, exclude_none=True))
        append_audit_event(
            session,
            action="project-task.review-issue.updated",
            resource_type="project_task_review_issue",
            resource_id=row.review_issue_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
            payload=request.model_dump(by_alias=False, exclude_none=True),
        )
        return TaskReviewIssueReadModel(
            id=str(row.review_issue_id),
            task_id=str(row.project_task_id),
            change_bundle_id=str(row.change_bundle_id) if row.change_bundle_id else None,
            evidence_bundle_id=str(row.evidence_bundle_id) if row.evidence_bundle_id else None,
            handoff_id=str(row.handoff_id) if row.handoff_id else None,
            issue_key=row.issue_key,
            severity=row.severity,
            category=row.category,
            acceptance_ref=row.acceptance_ref,
            summary=row.summary,
            suggestion=row.suggestion,
            status=row.status,
            resolved_at=row.resolved_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


@project_tasks_router.patch("/{project_task_id}", response_model=ProjectTaskResponse)
async def update_project_task(
    project_task_id: str,
    request: ProjectTaskUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )

        previous_run_id = task.run_id
        ensure_related_records(
            session,
            project_id=task.project_id,
            plan_id=request.plan_id,
            run_id=request.run_id,
            agent_id=request.assignee_agent_id,
        )
        apply_updates(
            task,
            request,
            [
                "plan_id",
                "run_id",
                "assignee_agent_id",
                "title",
                "description",
                "status",
                "priority",
                "sort_order",
                "input_payload",
                "output_payload",
                "error_message",
            ],
        )
        flush_and_refresh(session, task)
        if (
            request.title is not None
            or request.description is not None
            or get_latest_task_contract(session, project_task_id=task.project_task_id) is None
        ):
            ensure_task_contract(
                session,
                task=task,
                actor_user_id=get_current_user_uuid(current_user),
            )
        append_audit_event(
            session,
            action="project-task.updated",
            resource_type="project_task",
            resource_id=task.project_task_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        reconcile_run_state(session, run_id=previous_run_id)
        if task.run_id and task.run_id != previous_run_id:
            reconcile_run_state(session, run_id=task.run_id)
        elif task.run_id is None:
            reconcile_project_state(session, project_id=task.project_id)
        return task


@project_tasks_router.post("/{project_task_id}/transition", response_model=ProjectTaskResponse)
async def transition_project_task(
    project_task_id: str,
    request: TaskTransitionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )

        task.status = request.status
        task.output_payload = request.output_payload
        task.error_message = request.error_message
        flush_and_refresh(session, task)
        append_audit_event(
            session,
            action="project-task.transitioned",
            resource_type="project_task",
            resource_id=task.project_task_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        reconcile_run_state(session, run_id=task.run_id)
        if task.run_id is None:
            reconcile_project_state(session, project_id=task.project_id)
        return task


@project_tasks_router.delete("/{project_task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_task(
    project_task_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_task_id = parse_uuid(project_task_id, "project_task_id")
    with get_db_session() as session:
        task = get_or_404(
            session,
            ProjectTask,
            ProjectTask.project_task_id,
            parsed_task_id,
            "Project task not found",
        )
        if str(task.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Project task not found"
            )

        append_audit_event(
            session,
            action="project-task.deleted",
            resource_type="project_task",
            resource_id=task.project_task_id,
            project_id=task.project_id,
            run_id=task.run_id,
            current_user=current_user,
        )
        run_id = task.run_id
        project_id = task.project_id
        session.delete(task)
        session.flush()
        reconcile_run_state(session, run_id=run_id)
        if run_id is None:
            reconcile_project_state(session, project_id=project_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@plans_router.post("", response_model=ProjectPlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: ProjectPlanCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        ensure_related_records(session, project_id=request.project_id, require_project=True)
        plan = ProjectPlan(
            project_id=request.project_id,
            name=request.name,
            goal=request.goal,
            status=request.status,
            version=request.version,
            definition=request.definition,
            created_by_user_id=actor_user_id,
        )
        session.add(plan)
        flush_and_refresh(session, plan)
        append_audit_event(
            session,
            action="plan.created",
            resource_type="project_plan",
            resource_id=plan.plan_id,
            project_id=plan.project_id,
            current_user=current_user,
        )
        return plan


@plans_router.get("", response_model=list[ProjectPlanResponse])
async def list_plans(project_id: Optional[UUID] = None, _: CurrentUser = Depends(get_current_user)):
    with get_db_session() as session:
        query = session.query(ProjectPlan)
        if project_id:
            query = query.filter(ProjectPlan.project_id == project_id)
        return query.order_by(ProjectPlan.created_at.desc()).all()


@plans_router.get("/{plan_id}", response_model=ProjectPlanResponse)
async def get_plan(plan_id: str, _: CurrentUser = Depends(get_current_user)):
    parsed_plan_id = parse_uuid(plan_id, "plan_id")
    with get_db_session() as session:
        return get_or_404(
            session, ProjectPlan, ProjectPlan.plan_id, parsed_plan_id, "Plan not found"
        )


@plans_router.patch("/{plan_id}", response_model=ProjectPlanResponse)
async def update_plan(
    plan_id: str,
    request: ProjectPlanUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_plan_id = parse_uuid(plan_id, "plan_id")
    with get_db_session() as session:
        plan = get_or_404(
            session, ProjectPlan, ProjectPlan.plan_id, parsed_plan_id, "Plan not found"
        )
        apply_updates(plan, request, ["name", "goal", "status", "version", "definition"])
        flush_and_refresh(session, plan)
        append_audit_event(
            session,
            action="plan.updated",
            resource_type="project_plan",
            resource_id=plan.plan_id,
            project_id=plan.project_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        return plan


@plans_router.post("/{plan_id}/activate", response_model=ProjectPlanResponse)
async def activate_plan(
    plan_id: str,
    request: PlanStatusRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_plan_id = parse_uuid(plan_id, "plan_id")
    with get_db_session() as session:
        plan = get_or_404(
            session, ProjectPlan, ProjectPlan.plan_id, parsed_plan_id, "Plan not found"
        )
        plan.status = request.status
        flush_and_refresh(session, plan)
        append_audit_event(
            session,
            action="plan.activated",
            resource_type="project_plan",
            resource_id=plan.plan_id,
            project_id=plan.project_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        return plan


@plans_router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(plan_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_plan_id = parse_uuid(plan_id, "plan_id")
    with get_db_session() as session:
        plan = get_or_404(
            session, ProjectPlan, ProjectPlan.plan_id, parsed_plan_id, "Plan not found"
        )
        append_audit_event(
            session,
            action="plan.deleted",
            resource_type="project_plan",
            resource_id=plan.plan_id,
            project_id=plan.project_id,
            current_user=current_user,
        )
        session.delete(plan)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@runs_router.post("", response_model=ProjectRunResponse, status_code=status.HTTP_201_CREATED)
async def create_run(
    request: ProjectRunCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        ensure_related_records(
            session,
            project_id=request.project_id,
            plan_id=request.plan_id,
            require_project=True,
        )
        run = ProjectRun(
            project_id=request.project_id,
            plan_id=request.plan_id,
            status=request.status,
            trigger_source=request.trigger_source,
            runtime_context=request.runtime_context,
            requested_by_user_id=actor_user_id,
        )
        session.add(run)
        flush_and_refresh(session, run)
        append_audit_event(
            session,
            action="run.created",
            resource_type="project_run",
            resource_id=run.run_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
        )
        return run


@runs_router.get("", response_model=list[ProjectRunResponse])
async def list_runs(project_id: Optional[UUID] = None, _: CurrentUser = Depends(get_current_user)):
    with get_db_session() as session:
        query = session.query(ProjectRun)
        if project_id:
            query = query.filter(ProjectRun.project_id == project_id)
        runs = query.order_by(ProjectRun.created_at.desc()).all()
        for run in runs:
            reconcile_run_state(session, run=run)
        return [ProjectRunResponse.model_validate(run) for run in runs]


@runs_router.get("/{run_id}", response_model=ProjectRunResponse)
async def get_run(run_id: str, _: CurrentUser = Depends(get_current_user)):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        reconcile_run_state(session, run=run)
        return ProjectRunResponse.model_validate(run)


@runs_router.get("/{run_id}/detail", response_model=RunDetailReadModel)
async def get_run_detail(run_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        return build_run_detail_read_model(session, run=run)


@runs_router.get("/{run_id}/nodes", response_model=list[ExecutionAttemptNodeReadModel])
async def list_run_nodes(run_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        return build_run_node_read_models(session, run=run)


@runs_router.get(
    "/{run_id}/runtime-sessions", response_model=list[RuntimeSessionReadModel]
)
async def list_run_runtime_sessions(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        return build_run_runtime_session_read_models(session, run=run)


@attempts_router.post("", response_model=ProjectRunResponse, status_code=status.HTTP_201_CREATED)
async def create_attempt(
    request: ProjectRunCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await create_run(request, current_user)


@attempts_router.get("", response_model=list[ProjectRunResponse])
async def list_attempts(
    project_id: Optional[UUID] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await list_runs(project_id, current_user)


@attempts_router.get("/{attempt_id}", response_model=RunDetailReadModel)
async def get_attempt_detail(
    attempt_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await get_run_detail(attempt_id, current_user)


@attempts_router.post("/{attempt_id}/start", response_model=ProjectRunResponse)
async def start_attempt(
    attempt_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await start_run(attempt_id, current_user)


@attempts_router.post("/{attempt_id}/complete", response_model=ProjectRunResponse)
async def complete_attempt(
    attempt_id: str,
    request: RunTransitionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await complete_run(attempt_id, request, current_user)


@attempts_router.post("/{attempt_id}/cancel", response_model=ProjectRunResponse)
async def cancel_attempt(
    attempt_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await cancel_run(attempt_id, current_user)


@attempts_router.get("/{attempt_id}/nodes", response_model=list[ExecutionAttemptNodeReadModel])
async def list_attempt_nodes(
    attempt_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await list_run_nodes(attempt_id, current_user)


@attempts_router.get("/{attempt_id}/nodes/{node_id}", response_model=ExecutionAttemptNodeReadModel)
async def get_attempt_node(
    attempt_id: str,
    node_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(attempt_id, "attempt_id")
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        node = get_or_404(
            session,
            ExecutionNode,
            ExecutionNode.node_id,
            parsed_node_id,
            "Execution node not found",
        )
        if node.run_id != run.run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution node not found")
        return _execution_node_to_read_model(node)


@attempts_router.post(
    "/{attempt_id}/nodes",
    response_model=ExecutionAttemptNodeReadModel,
    status_code=status.HTTP_201_CREATED,
)
async def create_attempt_node(
    attempt_id: str,
    request: ExecutionAttemptNodeCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(attempt_id, "attempt_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        ensure_related_records(
            session,
            project_id=run.project_id,
            task_id=request.project_task_id,
        )
        node = _create_execution_step_pair(
            session,
            run=run,
            project_task_id=request.project_task_id,
            name=request.name,
            node_type=request.node_type,
            status_value=request.status,
            sequence_number=request.sequence_number,
            payload=request.node_payload,
        )
        append_audit_event(
            session,
            action="execution-node.created",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        return _execution_node_to_read_model(node)


@attempts_router.patch(
    "/{attempt_id}/nodes/{node_id}", response_model=ExecutionAttemptNodeReadModel
)
async def update_attempt_node(
    attempt_id: str,
    node_id: str,
    request: ExecutionAttemptNodeUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(attempt_id, "attempt_id")
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        node = get_or_404(session, ExecutionNode, ExecutionNode.node_id, parsed_node_id, "Execution node not found")
        if node.run_id != run.run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution node not found")
        ensure_related_records(session, project_id=run.project_id, task_id=request.project_task_id)
        node = _update_execution_node_and_sync_step(session, node=node, request=request)
        append_audit_event(
            session,
            action="execution-node.updated",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        reconcile_run_state(session, run=run)
        return _execution_node_to_read_model(node)


@attempts_router.post(
    "/{attempt_id}/nodes/{node_id}/complete", response_model=ExecutionAttemptNodeReadModel
)
async def complete_attempt_node(
    attempt_id: str,
    node_id: str,
    request: ExecutionAttemptNodeStatusRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(attempt_id, "attempt_id")
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        node = get_or_404(session, ExecutionNode, ExecutionNode.node_id, parsed_node_id, "Execution node not found")
        if node.run_id != run.run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution node not found")
        node = _complete_execution_node_and_sync_step(session, node=node, request=request)
        append_audit_event(
            session,
            action="execution-node.completed",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        reconcile_run_state(session, run=run)
        return _execution_node_to_read_model(node)


@attempts_router.get(
    "/{attempt_id}/runtime-sessions", response_model=list[RuntimeSessionReadModel]
)
async def list_attempt_runtime_sessions(
    attempt_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    return await list_run_runtime_sessions(attempt_id, current_user)


@runs_router.patch("/{run_id}", response_model=ProjectRunResponse)
async def update_run(
    run_id: str,
    request: ProjectRunUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        ensure_related_records(session, project_id=run.project_id, plan_id=request.plan_id)
        apply_updates(
            run,
            request,
            ["plan_id", "status", "trigger_source", "runtime_context", "error_message"],
        )
        flush_and_refresh(session, run)
        append_audit_event(
            session,
            action="run.updated",
            resource_type="project_run",
            resource_id=run.run_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        return run


@runs_router.post("/{run_id}/schedule", response_model=RunSchedulingResponse)
async def schedule_run(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        if str(run.requested_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        tasks = (
            session.query(ProjectTask)
            .filter(ProjectTask.run_id == parsed_run_id)
            .order_by(ProjectTask.updated_at.desc())
            .all()
        )
        for task in tasks:
            readiness = compute_task_readiness(session, project_task_id=task.project_task_id)
            if not readiness["ready"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=summarize_task_blockers(readiness)
                    or "Task dependencies are not satisfied",
                )
    scheduling_result = await schedule_run_after_launch(
        run_id=parsed_run_id, current_user=current_user
    )
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        return RunSchedulingResponse(
            run=ProjectRunResponse.model_validate(run),
            agent_assignment=scheduling_result.get("agent_assignment"),
            external_dispatch=scheduling_result.get("external_dispatch"),
            executor_assignment=scheduling_result.get("executor_assignment"),
            run_workspace=scheduling_result.get("run_workspace"),
        )


@runs_router.post("/{run_id}/start", response_model=ProjectRunResponse)
async def start_run(run_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        tasks = (
            session.query(ProjectTask)
            .filter(ProjectTask.run_id == parsed_run_id)
            .order_by(ProjectTask.updated_at.desc())
            .all()
        )
        for task in tasks:
            readiness = compute_task_readiness(session, project_task_id=task.project_task_id)
            if not readiness["ready"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=summarize_task_blockers(readiness)
                    or "Task dependencies are not satisfied",
                )
        run.status = "running"
        run.error_message = None
        run.completed_at = None
        if run.started_at is None:
            run.started_at = _utc_now()
        flush_and_refresh(session, run)
        append_audit_event(
            session,
            action="run.started",
            resource_type="project_run",
            resource_id=run.run_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
        )
        reconcile_project_state(session, project_id=run.project_id)
        return run


@runs_router.post("/{run_id}/complete", response_model=ProjectRunResponse)
async def complete_run(
    run_id: str,
    request: RunTransitionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        run.status = request.status
        run.error_message = request.error_message
        if run.started_at is None:
            run.started_at = _utc_now()
        run.completed_at = _utc_now()
        flush_and_refresh(session, run)
        append_audit_event(
            session,
            action="run.completed",
            resource_type="project_run",
            resource_id=run.run_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        reconcile_project_state(session, project_id=run.project_id)
        return run


@runs_router.post("/{run_id}/cancel", response_model=ProjectRunResponse)
async def cancel_run(run_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        run.status = "cancelled"
        run.completed_at = _utc_now()
        flush_and_refresh(session, run)
        append_audit_event(
            session,
            action="run.cancelled",
            resource_type="project_run",
            resource_id=run.run_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
        )
        reconcile_project_state(session, project_id=run.project_id)
        return run


@runs_router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(run_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        append_audit_event(
            session,
            action="run.deleted",
            resource_type="project_run",
            resource_id=run.run_id,
            project_id=run.project_id,
            run_id=run.run_id,
            current_user=current_user,
        )
        session.delete(run)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@project_space_router.put("/{project_id}", response_model=ProjectSpaceResponse)
async def upsert_project_space(
    project_id: str,
    request: ProjectSpaceUpsert,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        _load_owned_project_or_404(session, project_id=parsed_project_id, current_user=current_user)
        project_space = (
            session.query(ProjectSpace).filter(ProjectSpace.project_id == parsed_project_id).first()
        )
        if project_space is None:
            project_space = ProjectSpace(project_id=parsed_project_id)
            session.add(project_space)

        project_space.storage_uri = request.storage_uri
        project_space.branch_name = request.branch_name
        project_space.status = request.status
        project_space.root_path = request.root_path
        project_space.space_metadata = request.space_metadata
        flush_and_refresh(session, project_space)
        append_audit_event(
            session,
            action="project-space.upserted",
            resource_type="project_space",
            resource_id=project_space.project_space_id,
            project_id=project_space.project_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        return project_space


@project_space_router.get("/{project_id}", response_model=ProjectSpaceResponse)
async def get_project_space(
    project_id: str, current_user: CurrentUser = Depends(get_current_user)
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        _load_owned_project_or_404(session, project_id=parsed_project_id, current_user=current_user)
        return get_or_404(
            session,
            ProjectSpace,
            ProjectSpace.project_id,
            parsed_project_id,
            "Project space not found",
        )


@project_space_router.post("/{project_id}/sync", response_model=ProjectSpaceResponse)
async def sync_project_space(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        _load_owned_project_or_404(session, project_id=parsed_project_id, current_user=current_user)
        project_space = get_or_404(
            session,
            ProjectSpace,
            ProjectSpace.project_id,
            parsed_project_id,
            "Project space not found",
        )
        project_space.status = "synced"
        project_space.last_synced_at = _utc_now()
        flush_and_refresh(session, project_space)
        append_audit_event(
            session,
            action="project-space.synced",
            resource_type="project_space",
            resource_id=project_space.project_space_id,
            project_id=project_space.project_id,
            current_user=current_user,
        )
        return project_space


@project_space_router.get("/{project_id}/files")
async def list_project_space_files(
    project_id: str,
    path: str = "",
    recursive: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        _load_owned_project_or_404(session, project_id=parsed_project_id, current_user=current_user)
        project_space = (
            session.query(ProjectSpace).filter(ProjectSpace.project_id == parsed_project_id).first()
        )
        if project_space is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project space not found")
        workspace_root = _resolve_project_space_root(parsed_project_id, project_space)
    return agents_router._list_session_workspace_entries(workspace_root, path, recursive)


@project_space_router.get("/{project_id}/download")
async def download_project_space_file(
    project_id: str,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        _load_owned_project_or_404(session, project_id=parsed_project_id, current_user=current_user)
        project_space = (
            session.query(ProjectSpace).filter(ProjectSpace.project_id == parsed_project_id).first()
        )
        if project_space is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project space not found")
        workspace_root = _resolve_project_space_root(parsed_project_id, project_space)

    file_path, relative_path = agents_router._resolve_safe_workspace_path(workspace_root, path)
    if agents_router._is_internal_workspace_path(relative_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace file not found")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace file not found")

    filename = file_path.name or (relative_path.rsplit("/", 1)[-1] if relative_path else "download")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {
        "Content-Disposition": agents_router._build_download_content_disposition(
            filename,
            disposition="attachment",
        )
    }
    return FileResponse(path=file_path, media_type=media_type, filename=filename, headers=headers)


@runs_router.get("/{run_id}/workspace/files")
async def list_run_workspace_files(
    run_id: str,
    path: str = "",
    recursive: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        workspace_root = _resolve_run_workspace_root(run)
    return agents_router._list_session_workspace_entries(workspace_root, path, recursive)


@runs_router.get("/{run_id}/workspace/download")
async def download_run_workspace_file(
    run_id: str,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = _load_owned_run_or_404(session, run_id=parsed_run_id, current_user=current_user)
        workspace_root = _resolve_run_workspace_root(run)

    file_path, relative_path = agents_router._resolve_safe_workspace_path(workspace_root, path)
    if agents_router._is_internal_workspace_path(relative_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace file not found")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace file not found")

    filename = file_path.name or (relative_path.rsplit("/", 1)[-1] if relative_path else "download")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {
        "Content-Disposition": agents_router._build_download_content_disposition(
            filename,
            disposition="attachment",
        )
    }
    return FileResponse(path=file_path, media_type=media_type, filename=filename, headers=headers)


@extensions_router.post(
    "", response_model=ExtensionPackageResponse, status_code=status.HTTP_201_CREATED
)
async def create_extension(
    request: ExtensionPackageCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        ensure_related_records(session, project_id=request.project_id, require_project=True)
        extension = ProjectExtensionPackage(
            project_id=request.project_id,
            name=request.name,
            package_type=request.package_type,
            source_uri=request.source_uri,
            status=request.status,
            manifest=request.manifest,
            installed_by_user_id=actor_user_id,
        )
        session.add(extension)
        flush_and_refresh(session, extension)
        append_audit_event(
            session,
            action="extension.created",
            resource_type="project_extension_package",
            resource_id=extension.extension_package_id,
            project_id=extension.project_id,
            current_user=current_user,
        )
        return extension


@extensions_router.get("", response_model=list[ExtensionPackageResponse])
async def list_extensions(
    project_id: Optional[UUID] = None,
    _: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        query = session.query(ProjectExtensionPackage)
        if project_id:
            query = query.filter(ProjectExtensionPackage.project_id == project_id)
        return query.order_by(ProjectExtensionPackage.created_at.desc()).all()


@extensions_router.get("/{extension_package_id}", response_model=ExtensionPackageResponse)
async def get_extension(extension_package_id: str, _: CurrentUser = Depends(get_current_user)):
    parsed_extension_id = parse_uuid(extension_package_id, "extension_package_id")
    with get_db_session() as session:
        return get_or_404(
            session,
            ProjectExtensionPackage,
            ProjectExtensionPackage.extension_package_id,
            parsed_extension_id,
            "Extension package not found",
        )


@extensions_router.patch("/{extension_package_id}", response_model=ExtensionPackageResponse)
async def update_extension(
    extension_package_id: str,
    request: ExtensionPackageUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_extension_id = parse_uuid(extension_package_id, "extension_package_id")
    with get_db_session() as session:
        extension = get_or_404(
            session,
            ProjectExtensionPackage,
            ProjectExtensionPackage.extension_package_id,
            parsed_extension_id,
            "Extension package not found",
        )
        apply_updates(
            extension, request, ["name", "package_type", "source_uri", "status", "manifest"]
        )
        flush_and_refresh(session, extension)
        append_audit_event(
            session,
            action="extension.updated",
            resource_type="project_extension_package",
            resource_id=extension.extension_package_id,
            project_id=extension.project_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        return extension


@extensions_router.post("/{extension_package_id}/enable", response_model=ExtensionPackageResponse)
async def enable_extension(
    extension_package_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_extension_id = parse_uuid(extension_package_id, "extension_package_id")
    with get_db_session() as session:
        extension = get_or_404(
            session,
            ProjectExtensionPackage,
            ProjectExtensionPackage.extension_package_id,
            parsed_extension_id,
            "Extension package not found",
        )
        extension.status = "enabled"
        flush_and_refresh(session, extension)
        append_audit_event(
            session,
            action="extension.enabled",
            resource_type="project_extension_package",
            resource_id=extension.extension_package_id,
            project_id=extension.project_id,
            current_user=current_user,
        )
        return extension


@extensions_router.post("/{extension_package_id}/disable", response_model=ExtensionPackageResponse)
async def disable_extension(
    extension_package_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_extension_id = parse_uuid(extension_package_id, "extension_package_id")
    with get_db_session() as session:
        extension = get_or_404(
            session,
            ProjectExtensionPackage,
            ProjectExtensionPackage.extension_package_id,
            parsed_extension_id,
            "Extension package not found",
        )
        extension.status = "disabled"
        flush_and_refresh(session, extension)
        append_audit_event(
            session,
            action="extension.disabled",
            resource_type="project_extension_package",
            resource_id=extension.extension_package_id,
            project_id=extension.project_id,
            current_user=current_user,
        )
        return extension


@extensions_router.delete("/{extension_package_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_extension(
    extension_package_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_extension_id = parse_uuid(extension_package_id, "extension_package_id")
    with get_db_session() as session:
        extension = get_or_404(
            session,
            ProjectExtensionPackage,
            ProjectExtensionPackage.extension_package_id,
            parsed_extension_id,
            "Extension package not found",
        )
        append_audit_event(
            session,
            action="extension.deleted",
            resource_type="project_extension_package",
            resource_id=extension.extension_package_id,
            project_id=extension.project_id,
            current_user=current_user,
        )
        session.delete(extension)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@skills_import_router.post(
    "/import", response_model=SkillPackageResponse, status_code=status.HTTP_201_CREATED
)
async def import_skill_package(
    request: SkillImportRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        if request.project_id:
            ensure_related_records(session, project_id=request.project_id)
        existing = (
            session.query(ProjectSkillPackage)
            .filter(ProjectSkillPackage.slug == request.slug)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Skill slug already exists"
            )

        skill_package = ProjectSkillPackage(
            project_id=request.project_id,
            name=request.name,
            slug=request.slug,
            source_uri=request.source_uri,
            status="imported",
            manifest=request.manifest,
            imported_by_user_id=actor_user_id,
        )
        session.add(skill_package)
        flush_and_refresh(session, skill_package)
        append_audit_event(
            session,
            action="skill-package.imported",
            resource_type="project_skill_package",
            resource_id=skill_package.skill_package_id,
            project_id=skill_package.project_id,
            current_user=current_user,
            payload={"slug": skill_package.slug},
        )
        return skill_package


@skills_import_router.post(
    "/imports/{skill_package_id}/test",
    response_model=SkillPackageResponse,
)
async def test_imported_skill_package(
    skill_package_id: str,
    request: SkillPackageTestRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_skill_package_id = parse_uuid(skill_package_id, "skill_package_id")
    with get_db_session() as session:
        skill_package = get_or_404(
            session,
            ProjectSkillPackage,
            ProjectSkillPackage.skill_package_id,
            parsed_skill_package_id,
            "Skill package not found",
        )
        skill_package.status = request.status
        skill_package.test_result = request.test_result
        skill_package.last_tested_at = _utc_now()
        flush_and_refresh(session, skill_package)
        append_audit_event(
            session,
            action="skill-package.tested",
            resource_type="project_skill_package",
            resource_id=skill_package.skill_package_id,
            project_id=skill_package.project_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        return skill_package
