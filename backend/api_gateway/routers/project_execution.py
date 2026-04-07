"""Minimal CRUD/workflow routers for the project execution platform skeleton."""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import IntegrityError

from access_control.permissions import CurrentUser, get_current_user
from database.connection import get_db_session
from database.project_execution_models import (
    AgentProvisioningProfile,
    AgentRuntimeBinding,
    ExecutionLease,
    ExecutionNode,
    ExternalAgentSession,
    Project,
    ProjectAgentBinding,
    ProjectExtensionPackage,
    ProjectPlan,
    ProjectRun,
    ProjectRunStep,
    ProjectSkillPackage,
    ProjectSpace,
    ProjectTask,
)
from project_execution.schemas import (
    AgentProvisioningProfileCreate,
    AgentProvisioningProfileResponse,
    AgentProvisioningProfileUpdate,
    AgentRuntimeBindingCreate,
    AgentRuntimeBindingResponse,
    AgentRuntimeBindingUpdate,
    ExecutionLeaseProgress,
    ExecutionLeaseResponse,
    ExternalAgentSessionResponse,
    ExecutionNodeCreate,
    ExecutionNodeHeartbeat,
    ExecutionNodeRegister,
    ExecutionNodeResponse,
    ExecutionNodeUpdate,
    ExtensionPackageCreate,
    ExtensionPackageResponse,
    ExtensionPackageUpdate,
    PlanStatusRequest,
    ProjectAgentBindingCreate,
    ProjectAgentBindingResponse,
    ProjectAgentBindingUpdate,
    ProjectCreate,
    ProjectPlanCreate,
    ProjectPlanResponse,
    ProjectPlanUpdate,
    ProjectResponse,
    ProjectRunCreate,
    ProjectRunResponse,
    ProjectRunStepCreate,
    ProjectRunStepResponse,
    ProjectRunStepUpdate,
    ProjectRunUpdate,
    ProjectSpaceResponse,
    ProjectSpaceUpsert,
    ProjectTaskCreate,
    ProjectTaskCreateAndLaunchRequest,
    ProjectTaskLaunchBundleResponse,
    ProjectTaskResponse,
    ProjectTaskUpdate,
    ProjectUpdate,
    RunSchedulingResponse,
    RunStepStatusRequest,
    RunTransitionRequest,
    SkillImportRequest,
    SkillPackageResponse,
    SkillPackageTestRequest,
    TaskTransitionRequest,
)
from project_execution.scheduler import schedule_run_after_launch
from project_execution.service import (
    append_audit_event,
    apply_updates,
    create_project_task_and_launch_run,
    ensure_related_records,
    flush_and_refresh,
    get_current_user_uuid,
    get_or_404,
    reconcile_run_state,
    parse_uuid,
)
from shared.logging import get_logger

logger = get_logger(__name__)

projects_router = APIRouter()
project_tasks_router = APIRouter()
plans_router = APIRouter()
runs_router = APIRouter()
run_steps_router = APIRouter()
project_space_router = APIRouter()
execution_nodes_router = APIRouter()
extensions_router = APIRouter()
skills_import_router = APIRouter()
agent_runtime_bindings_router = APIRouter()
external_agent_sessions_router = APIRouter()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _handle_integrity_error(exc: IntegrityError, *, duplicate_detail: str) -> None:
    logger.warning("Project execution integrity error: %s", exc)
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=duplicate_detail) from exc




def _sync_external_session_for_lease(session, lease: ExecutionLease, *, status: str, result_payload: Optional[dict] = None, error_message: Optional[str] = None) -> None:
    external_session = (
        session.query(ExternalAgentSession)
        .filter(ExternalAgentSession.lease_id == lease.lease_id)
        .first()
    )
    if external_session is None:
        return
    external_session.status = status
    external_session.error_message = error_message
    external_session.session_metadata = {
        **(external_session.session_metadata or {}),
        **(result_payload or {}),
    }
    if status in {"spawning", "connected", "running"} and external_session.started_at is None:
        external_session.started_at = _utc_now()
    if status in {"completed", "failed", "terminated"}:
        external_session.completed_at = _utc_now()
    flush_and_refresh(session, external_session)


@agent_runtime_bindings_router.get("/{agent_id}/runtime-bindings", response_model=list[AgentRuntimeBindingResponse])
async def list_agent_runtime_bindings(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_agent_id = parse_uuid(agent_id, "agent_id")
    with get_db_session() as session:
        bindings = session.query(AgentRuntimeBinding).filter(AgentRuntimeBinding.agent_id == parsed_agent_id).order_by(AgentRuntimeBinding.created_at.asc()).all()
        return bindings


@agent_runtime_bindings_router.post("/{agent_id}/runtime-bindings", response_model=AgentRuntimeBindingResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_runtime_binding(
    agent_id: str,
    request: AgentRuntimeBindingCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_agent_id = parse_uuid(agent_id, "agent_id")
    with get_db_session() as session:
        binding = AgentRuntimeBinding(
            agent_id=parsed_agent_id,
            runtime_type=request.runtime_type,
            execution_node_id=request.execution_node_id,
            workspace_strategy=request.workspace_strategy,
            path_allowlist=request.path_allowlist,
            status=request.status,
            config=request.config,
        )
        session.add(binding)
        flush_and_refresh(session, binding)
        return binding


@agent_runtime_bindings_router.patch("/{agent_id}/runtime-bindings/{binding_id}", response_model=AgentRuntimeBindingResponse)
async def update_agent_runtime_binding(
    agent_id: str,
    binding_id: str,
    request: AgentRuntimeBindingUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_agent_id = parse_uuid(agent_id, "agent_id")
    parsed_binding_id = parse_uuid(binding_id, "binding_id")
    with get_db_session() as session:
        binding = get_or_404(session, AgentRuntimeBinding, AgentRuntimeBinding.runtime_binding_id, parsed_binding_id, "Agent runtime binding not found")
        if binding.agent_id != parsed_agent_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent runtime binding not found")
        apply_updates(binding, request, ["runtime_type", "execution_node_id", "workspace_strategy", "path_allowlist", "status", "config"])
        flush_and_refresh(session, binding)
        return binding


@agent_runtime_bindings_router.delete("/{agent_id}/runtime-bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_runtime_binding(
    agent_id: str,
    binding_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_agent_id = parse_uuid(agent_id, "agent_id")
    parsed_binding_id = parse_uuid(binding_id, "binding_id")
    with get_db_session() as session:
        binding = get_or_404(session, AgentRuntimeBinding, AgentRuntimeBinding.runtime_binding_id, parsed_binding_id, "Agent runtime binding not found")
        if binding.agent_id != parsed_agent_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent runtime binding not found")
        session.delete(binding)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@external_agent_sessions_router.get("/{session_id}", response_model=ExternalAgentSessionResponse)
async def get_external_agent_session(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_session_id = parse_uuid(session_id, "session_id")
    with get_db_session() as session:
        return get_or_404(session, ExternalAgentSession, ExternalAgentSession.session_id, parsed_session_id, "External agent session not found")


@runs_router.get("/{run_id}/external-sessions", response_model=list[ExternalAgentSessionResponse])
async def list_run_external_sessions(
    run_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        return session.query(ExternalAgentSession).filter(ExternalAgentSession.run_id == parsed_run_id).order_by(ExternalAgentSession.created_at.asc()).all()


@projects_router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        actor_user_id = get_current_user_uuid(current_user)
        project = Project(
            name=request.name,
            description=request.description,
            status=request.status,
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
        return (
            session.query(Project)
            .filter(Project.created_by_user_id == actor_user_id)
            .order_by(Project.created_at.desc())
            .all()
        )


@projects_router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(project_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return project


@projects_router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    request: ProjectUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

        apply_updates(project, request, ["name", "description", "status", "configuration"])
        flush_and_refresh(session, project)
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
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

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
        project = get_or_404(
            session, Project, Project.project_id, parsed_project_id, "Project not found"
        )
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

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




@projects_router.get("/{project_id}/agent-bindings", response_model=list[ProjectAgentBindingResponse])
async def list_project_agent_bindings(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return (
            session.query(ProjectAgentBinding)
            .filter(ProjectAgentBinding.project_id == parsed_project_id)
            .order_by(ProjectAgentBinding.priority.desc(), ProjectAgentBinding.created_at.asc())
            .all()
        )


@projects_router.post("/{project_id}/agent-bindings", response_model=ProjectAgentBindingResponse, status_code=status.HTTP_201_CREATED)
async def create_project_agent_binding(
    project_id: str,
    request: ProjectAgentBindingCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
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
            _handle_integrity_error(exc, duplicate_detail="Project agent binding could not be created")
        append_audit_event(
            session,
            action="project-agent-binding.created",
            resource_type="project_agent_binding",
            resource_id=binding.binding_id,
            project_id=parsed_project_id,
            current_user=current_user,
        )
        return binding


@projects_router.patch("/{project_id}/agent-bindings/{binding_id}", response_model=ProjectAgentBindingResponse)
async def update_project_agent_binding(
    project_id: str,
    binding_id: str,
    request: ProjectAgentBindingUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_binding_id = parse_uuid(binding_id, "binding_id")
    with get_db_session() as session:
        binding = get_or_404(session, ProjectAgentBinding, ProjectAgentBinding.binding_id, parsed_binding_id, "Project agent binding not found")
        if str(binding.project_id) != str(parsed_project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project agent binding not found")
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        apply_updates(binding, request, ["role_hint", "priority", "status", "allowed_step_kinds", "preferred_skills", "preferred_runtime_types"])
        flush_and_refresh(session, binding)
        return binding


@projects_router.delete("/{project_id}/agent-bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project_agent_binding(
    project_id: str,
    binding_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_binding_id = parse_uuid(binding_id, "binding_id")
    with get_db_session() as session:
        binding = get_or_404(session, ProjectAgentBinding, ProjectAgentBinding.binding_id, parsed_binding_id, "Project agent binding not found")
        if str(binding.project_id) != str(parsed_project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project agent binding not found")
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        session.delete(binding)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@projects_router.get("/{project_id}/agent-provisioning-profiles", response_model=list[AgentProvisioningProfileResponse])
async def list_agent_provisioning_profiles(
    project_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        return (
            session.query(AgentProvisioningProfile)
            .filter(AgentProvisioningProfile.project_id == parsed_project_id)
            .order_by(AgentProvisioningProfile.step_kind.asc())
            .all()
        )


@projects_router.post("/{project_id}/agent-provisioning-profiles", response_model=AgentProvisioningProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_provisioning_profile(
    project_id: str,
    request: AgentProvisioningProfileCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
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
            preferred_node_selector=request.preferred_node_selector,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            sandbox_mode=request.sandbox_mode,
            ephemeral=request.ephemeral,
        )
        session.add(profile)
        try:
            flush_and_refresh(session, profile)
        except IntegrityError as exc:
            _handle_integrity_error(exc, duplicate_detail="Agent provisioning profile could not be created")
        append_audit_event(
            session,
            action="agent-provisioning-profile.created",
            resource_type="agent_provisioning_profile",
            resource_id=profile.profile_id,
            project_id=parsed_project_id,
            current_user=current_user,
        )
        return profile


@projects_router.patch("/{project_id}/agent-provisioning-profiles/{profile_id}", response_model=AgentProvisioningProfileResponse)
async def update_agent_provisioning_profile(
    project_id: str,
    profile_id: str,
    request: AgentProvisioningProfileUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_profile_id = parse_uuid(profile_id, "profile_id")
    with get_db_session() as session:
        profile = get_or_404(session, AgentProvisioningProfile, AgentProvisioningProfile.profile_id, parsed_profile_id, "Agent provisioning profile not found")
        if str(profile.project_id) != str(parsed_project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent provisioning profile not found")
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        apply_updates(profile, request, ["agent_type", "template_id", "default_skill_ids", "default_provider", "default_model", "runtime_type", "preferred_node_selector", "temperature", "max_tokens", "sandbox_mode", "ephemeral"])
        flush_and_refresh(session, profile)
        return profile


@projects_router.delete("/{project_id}/agent-provisioning-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent_provisioning_profile(
    project_id: str,
    profile_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    parsed_profile_id = parse_uuid(profile_id, "profile_id")
    with get_db_session() as session:
        profile = get_or_404(session, AgentProvisioningProfile, AgentProvisioningProfile.profile_id, parsed_profile_id, "Agent provisioning profile not found")
        if str(profile.project_id) != str(parsed_project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent provisioning profile not found")
        project = get_or_404(session, Project, Project.project_id, parsed_project_id, "Project not found")
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
        try:
            task, plan, run, step = create_project_task_and_launch_run(
                session,
                project_id=request.project_id,
                title=request.title,
                description=request.description,
                priority=request.priority,
                assignee_agent_id=request.assignee_agent_id,
                input_payload=request.input_payload,
                current_user=current_user,
            )
        except IntegrityError as exc:
            _handle_integrity_error(exc, duplicate_detail="Project task could not be created")
        task_id = task.project_task_id
        plan_id = plan.plan_id
        run_id = run.run_id
        step_id = step.run_step_id

    scheduling_result = await schedule_run_after_launch(run_id=run_id, current_user=current_user)

    with get_db_session() as session:
        task = get_or_404(session, ProjectTask, ProjectTask.project_task_id, task_id, "Project task not found")
        plan = get_or_404(session, ProjectPlan, ProjectPlan.plan_id, plan_id, "Plan not found")
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, run_id, "Run not found")
        step = get_or_404(session, ProjectRunStep, ProjectRunStep.run_step_id, step_id, "Run step not found")
        return ProjectTaskLaunchBundleResponse(
            task=ProjectTaskResponse.model_validate(task),
            plan=ProjectPlanResponse.model_validate(plan),
            run=ProjectRunResponse.model_validate(run),
            step=ProjectRunStepResponse.model_validate(step),
            agent_assignment=scheduling_result.get("agent_assignment"),
            runtime_binding=scheduling_result.get("runtime_binding"),
            external_session=scheduling_result.get("external_session"),
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
            input_payload=request.input_payload,
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
            run_id=task.run_id,
            current_user=current_user,
        )
        return task


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
        session.delete(task)
        session.flush()
        reconcile_run_state(session, run_id=run_id)
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
    scheduling_result = await schedule_run_after_launch(run_id=parsed_run_id, current_user=current_user)
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        return RunSchedulingResponse(
            run=ProjectRunResponse.model_validate(run),
            agent_assignment=scheduling_result.get("agent_assignment"),
            runtime_binding=scheduling_result.get("runtime_binding"),
            external_session=scheduling_result.get("external_session"),
            executor_assignment=scheduling_result.get("executor_assignment"),
            run_workspace=scheduling_result.get("run_workspace"),
        )


@runs_router.post("/{run_id}/start", response_model=ProjectRunResponse)
async def start_run(run_id: str, current_user: CurrentUser = Depends(get_current_user)):
    parsed_run_id = parse_uuid(run_id, "run_id")
    with get_db_session() as session:
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, parsed_run_id, "Run not found")
        run.status = "running"
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


@run_steps_router.post(
    "", response_model=ProjectRunStepResponse, status_code=status.HTTP_201_CREATED
)
async def create_run_step(
    request: ProjectRunStepCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        ensure_related_records(
            session,
            run_id=request.run_id,
            task_id=request.project_task_id,
            node_id=request.node_id,
        )
        step = ProjectRunStep(
            run_id=request.run_id,
            project_task_id=request.project_task_id,
            node_id=request.node_id,
            name=request.name,
            step_type=request.step_type,
            status=request.status,
            sequence_number=request.sequence_number,
            input_payload=request.input_payload,
        )
        session.add(step)
        flush_and_refresh(session, step)
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, step.run_id, "Run not found")
        append_audit_event(
            session,
            action="run-step.created",
            resource_type="project_run_step",
            resource_id=step.run_step_id,
            project_id=run.project_id,
            run_id=step.run_id,
            current_user=current_user,
        )
        return step


@run_steps_router.get("", response_model=list[ProjectRunStepResponse])
async def list_run_steps(run_id: Optional[UUID] = None, _: CurrentUser = Depends(get_current_user)):
    with get_db_session() as session:
        query = session.query(ProjectRunStep)
        if run_id:
            query = query.filter(ProjectRunStep.run_id == run_id)
        return query.order_by(ProjectRunStep.sequence_number.asc()).all()


@run_steps_router.get("/{run_step_id}", response_model=ProjectRunStepResponse)
async def get_run_step(run_step_id: str, _: CurrentUser = Depends(get_current_user)):
    parsed_step_id = parse_uuid(run_step_id, "run_step_id")
    with get_db_session() as session:
        return get_or_404(
            session,
            ProjectRunStep,
            ProjectRunStep.run_step_id,
            parsed_step_id,
            "Run step not found",
        )


@run_steps_router.patch("/{run_step_id}", response_model=ProjectRunStepResponse)
async def update_run_step(
    run_step_id: str,
    request: ProjectRunStepUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_step_id = parse_uuid(run_step_id, "run_step_id")
    with get_db_session() as session:
        step = get_or_404(
            session,
            ProjectRunStep,
            ProjectRunStep.run_step_id,
            parsed_step_id,
            "Run step not found",
        )
        ensure_related_records(
            session,
            run_id=step.run_id,
            task_id=request.project_task_id,
            node_id=request.node_id,
        )
        apply_updates(
            step,
            request,
            [
                "project_task_id",
                "node_id",
                "name",
                "step_type",
                "status",
                "sequence_number",
                "input_payload",
                "output_payload",
                "error_message",
            ],
        )
        flush_and_refresh(session, step)
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, step.run_id, "Run not found")
        append_audit_event(
            session,
            action="run-step.updated",
            resource_type="project_run_step",
            resource_id=step.run_step_id,
            project_id=run.project_id,
            run_id=step.run_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        reconcile_run_state(session, run_id=step.run_id)
        return step


@run_steps_router.post("/{run_step_id}/complete", response_model=ProjectRunStepResponse)
async def complete_run_step(
    run_step_id: str,
    request: RunStepStatusRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_step_id = parse_uuid(run_step_id, "run_step_id")
    with get_db_session() as session:
        step = get_or_404(
            session,
            ProjectRunStep,
            ProjectRunStep.run_step_id,
            parsed_step_id,
            "Run step not found",
        )
        if step.started_at is None:
            step.started_at = _utc_now()
        step.completed_at = _utc_now()
        step.status = request.status
        step.output_payload = request.output_payload
        step.error_message = request.error_message
        flush_and_refresh(session, step)
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, step.run_id, "Run not found")
        append_audit_event(
            session,
            action="run-step.completed",
            resource_type="project_run_step",
            resource_id=step.run_step_id,
            project_id=run.project_id,
            run_id=step.run_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        reconcile_run_state(session, run_id=step.run_id)
        return step


@run_steps_router.delete("/{run_step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run_step(
    run_step_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_step_id = parse_uuid(run_step_id, "run_step_id")
    with get_db_session() as session:
        step = get_or_404(
            session,
            ProjectRunStep,
            ProjectRunStep.run_step_id,
            parsed_step_id,
            "Run step not found",
        )
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, step.run_id, "Run not found")
        append_audit_event(
            session,
            action="run-step.deleted",
            resource_type="project_run_step",
            resource_id=step.run_step_id,
            project_id=run.project_id,
            run_id=step.run_id,
            current_user=current_user,
        )
        run_id = step.run_id
        session.delete(step)
        session.flush()
        reconcile_run_state(session, run_id=run_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@project_space_router.put("/{project_id}", response_model=ProjectSpaceResponse)
async def upsert_project_space(
    project_id: str,
    request: ProjectSpaceUpsert,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
        ensure_related_records(session, project_id=parsed_project_id, require_project=True)
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
async def get_project_space(project_id: str, _: CurrentUser = Depends(get_current_user)):
    parsed_project_id = parse_uuid(project_id, "project_id")
    with get_db_session() as session:
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


@execution_nodes_router.post("/register", response_model=ExecutionNodeResponse, status_code=status.HTTP_201_CREATED)
async def register_execution_node(
    request: ExecutionNodeRegister,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        ensure_related_records(session, project_id=request.project_id, require_project=True)
        node = ExecutionNode(
            project_id=request.project_id,
            name=request.name,
            node_type=request.node_type,
            status="online",
            capabilities=request.capabilities,
            config=request.config,
            last_seen_at=_utc_now(),
        )
        session.add(node)
        flush_and_refresh(session, node)
        append_audit_event(
            session,
            action="execution-node.registered",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=node.project_id,
            current_user=current_user,
        )
        return node


@execution_nodes_router.post(
    "", response_model=ExecutionNodeResponse, status_code=status.HTTP_201_CREATED
)
async def create_execution_node(
    request: ExecutionNodeCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        ensure_related_records(
            session,
            project_id=request.project_id,
            plan_id=request.plan_id,
            require_project=True,
        )
        node = ExecutionNode(
            project_id=request.project_id,
            plan_id=request.plan_id,
            name=request.name,
            node_type=request.node_type,
            status=request.status,
            capabilities=request.capabilities,
            config=request.config,
        )
        session.add(node)
        flush_and_refresh(session, node)
        append_audit_event(
            session,
            action="execution-node.created",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=node.project_id,
            current_user=current_user,
        )
        return node


@execution_nodes_router.get("", response_model=list[ExecutionNodeResponse])
async def list_execution_nodes(
    project_id: Optional[UUID] = None,
    _: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        query = session.query(ExecutionNode)
        if project_id:
            query = query.filter(ExecutionNode.project_id == project_id)
        return query.order_by(ExecutionNode.created_at.desc()).all()


@execution_nodes_router.get("/{node_id}", response_model=ExecutionNodeResponse)
async def get_execution_node(node_id: str, _: CurrentUser = Depends(get_current_user)):
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        return get_or_404(
            session,
            ExecutionNode,
            ExecutionNode.node_id,
            parsed_node_id,
            "Execution node not found",
        )


@execution_nodes_router.patch("/{node_id}", response_model=ExecutionNodeResponse)
async def update_execution_node(
    node_id: str,
    request: ExecutionNodeUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        node = get_or_404(
            session,
            ExecutionNode,
            ExecutionNode.node_id,
            parsed_node_id,
            "Execution node not found",
        )
        ensure_related_records(session, project_id=node.project_id, plan_id=request.plan_id)
        apply_updates(
            node, request, ["plan_id", "name", "node_type", "status", "capabilities", "config"]
        )
        flush_and_refresh(session, node)
        append_audit_event(
            session,
            action="execution-node.updated",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=node.project_id,
            current_user=current_user,
            payload=request.model_dump(exclude_none=True),
        )
        return node


@execution_nodes_router.post("/{node_id}/heartbeat", response_model=ExecutionNodeResponse)
async def heartbeat_execution_node(
    node_id: str,
    request: ExecutionNodeHeartbeat,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        node = get_or_404(
            session,
            ExecutionNode,
            ExecutionNode.node_id,
            parsed_node_id,
            "Execution node not found",
        )
        node.status = request.status
        node.config = request.config
        node.last_seen_at = _utc_now()
        flush_and_refresh(session, node)
        append_audit_event(
            session,
            action="execution-node.heartbeat",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=node.project_id,
            current_user=current_user,
            payload=request.model_dump(),
        )
        return node


@execution_nodes_router.get("/{node_id}/leases", response_model=list[ExecutionLeaseResponse])
async def list_execution_node_leases(
    node_id: str,
    status: Optional[str] = None,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        node = get_or_404(session, ExecutionNode, ExecutionNode.node_id, parsed_node_id, "Execution node not found")
        project = get_or_404(session, Project, Project.project_id, node.project_id, "Project not found")
        if str(project.created_by_user_id) != str(current_user.user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution node not found")
        query = session.query(ExecutionLease).filter(ExecutionLease.node_id == parsed_node_id)
        if status:
            query = query.filter(ExecutionLease.status == status)
        else:
            query = query.filter(ExecutionLease.status.in_(["pending", "acked", "running"]))
        return query.order_by(ExecutionLease.created_at.asc()).all()


@execution_nodes_router.post("/{node_id}/leases/{lease_id}/ack", response_model=ExecutionLeaseResponse)
async def ack_execution_lease(
    node_id: str,
    lease_id: str,
    request: ExecutionLeaseProgress,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    parsed_lease_id = parse_uuid(lease_id, "lease_id")
    with get_db_session() as session:
        lease = get_or_404(session, ExecutionLease, ExecutionLease.lease_id, parsed_lease_id, "Execution lease not found")
        if lease.node_id != parsed_node_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution lease not found")
        lease.status = "acked"
        lease.acked_at = _utc_now()
        lease.result_payload = {**(lease.result_payload or {}), **request.result_payload}
        flush_and_refresh(session, lease)
        _sync_external_session_for_lease(session, lease, status="connected", result_payload=request.result_payload)
        step = get_or_404(session, ProjectRunStep, ProjectRunStep.run_step_id, lease.run_step_id, "Run step not found")
        step.status = "leased"
        flush_and_refresh(session, step)
        return lease


@execution_nodes_router.post("/{node_id}/leases/{lease_id}/progress", response_model=ExecutionLeaseResponse)
async def update_execution_lease_progress(
    node_id: str,
    lease_id: str,
    request: ExecutionLeaseProgress,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    parsed_lease_id = parse_uuid(lease_id, "lease_id")
    with get_db_session() as session:
        lease = get_or_404(session, ExecutionLease, ExecutionLease.lease_id, parsed_lease_id, "Execution lease not found")
        if lease.node_id != parsed_node_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution lease not found")
        lease.status = request.status
        if lease.started_at is None:
            lease.started_at = _utc_now()
        lease.result_payload = {**(lease.result_payload or {}), **request.result_payload}
        lease.error_message = request.error_message
        flush_and_refresh(session, lease)
        _sync_external_session_for_lease(session, lease, status=request.status, result_payload=request.result_payload, error_message=request.error_message)
        step = get_or_404(session, ProjectRunStep, ProjectRunStep.run_step_id, lease.run_step_id, "Run step not found")
        step.status = request.status
        step.output_payload = {**(step.output_payload or {}), **request.result_payload}
        step.error_message = request.error_message
        if step.started_at is None:
            step.started_at = _utc_now()
        flush_and_refresh(session, step)
        return lease


@execution_nodes_router.post("/{node_id}/leases/{lease_id}/complete", response_model=ExecutionLeaseResponse)
async def complete_execution_lease(
    node_id: str,
    lease_id: str,
    request: ExecutionLeaseProgress,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    parsed_lease_id = parse_uuid(lease_id, "lease_id")
    with get_db_session() as session:
        lease = get_or_404(session, ExecutionLease, ExecutionLease.lease_id, parsed_lease_id, "Execution lease not found")
        if lease.node_id != parsed_node_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution lease not found")
        lease.status = "completed"
        lease.completed_at = _utc_now()
        if lease.started_at is None:
            lease.started_at = lease.completed_at
        lease.result_payload = {**(lease.result_payload or {}), **request.result_payload}
        flush_and_refresh(session, lease)
        _sync_external_session_for_lease(session, lease, status="completed", result_payload=request.result_payload)
        step = get_or_404(session, ProjectRunStep, ProjectRunStep.run_step_id, lease.run_step_id, "Run step not found")
        step.status = "completed"
        step.completed_at = lease.completed_at
        if step.started_at is None:
            step.started_at = lease.started_at
        step.output_payload = {**(step.output_payload or {}), **request.result_payload}
        flush_and_refresh(session, step)
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, lease.run_id, "Run not found")
        remaining = session.query(ProjectRunStep).filter(ProjectRunStep.run_id == lease.run_id).filter(ProjectRunStep.status.in_(["pending", "queued", "assigned", "leased", "running"])).count()
        if remaining == 0:
            run.status = "completed"
            run.completed_at = _utc_now()
            flush_and_refresh(session, run)
        return lease


@execution_nodes_router.post("/{node_id}/leases/{lease_id}/fail", response_model=ExecutionLeaseResponse)
async def fail_execution_lease(
    node_id: str,
    lease_id: str,
    request: ExecutionLeaseProgress,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    parsed_lease_id = parse_uuid(lease_id, "lease_id")
    with get_db_session() as session:
        lease = get_or_404(session, ExecutionLease, ExecutionLease.lease_id, parsed_lease_id, "Execution lease not found")
        if lease.node_id != parsed_node_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution lease not found")
        lease.status = "failed"
        lease.completed_at = _utc_now()
        lease.error_message = request.error_message or "Execution node reported failure"
        lease.result_payload = {**(lease.result_payload or {}), **request.result_payload}
        flush_and_refresh(session, lease)
        _sync_external_session_for_lease(session, lease, status="failed", result_payload=request.result_payload, error_message=lease.error_message)
        step = get_or_404(session, ProjectRunStep, ProjectRunStep.run_step_id, lease.run_step_id, "Run step not found")
        step.status = "failed"
        step.completed_at = lease.completed_at
        step.error_message = lease.error_message
        step.output_payload = {**(step.output_payload or {}), **request.result_payload}
        flush_and_refresh(session, step)
        run = get_or_404(session, ProjectRun, ProjectRun.run_id, lease.run_id, "Run not found")
        run.status = "failed"
        run.completed_at = _utc_now()
        run.error_message = lease.error_message
        flush_and_refresh(session, run)
        return lease


@execution_nodes_router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_execution_node(
    node_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    parsed_node_id = parse_uuid(node_id, "node_id")
    with get_db_session() as session:
        node = get_or_404(
            session,
            ExecutionNode,
            ExecutionNode.node_id,
            parsed_node_id,
            "Execution node not found",
        )
        append_audit_event(
            session,
            action="execution-node.deleted",
            resource_type="execution_node",
            resource_id=node.node_id,
            project_id=node.project_id,
            current_user=current_user,
        )
        session.delete(node)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


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
