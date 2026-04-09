from __future__ import annotations

"""Pydantic schemas for the project execution backend skeleton."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Base schema configured for SQLAlchemy object responses."""

    model_config = ConfigDict(from_attributes=True)


def _to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class FrontendReadModel(BaseModel):
    """Read models shaped for the project execution frontend."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class FrontendRequestModel(BaseModel):
    """Request models shaped for the project execution frontend."""

    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = Field(default="planning", min_length=1, max_length=50)
    configuration: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, min_length=1, max_length=50)
    configuration: Optional[dict[str, Any]] = None


class ProjectResponse(ORMModel):
    project_id: UUID
    name: str
    description: Optional[str]
    status: str
    configuration: dict[str, Any]
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectAgentBindingCreate(BaseModel):
    agent_id: UUID
    role_hint: Optional[str] = None
    priority: int = Field(default=0, ge=0)
    status: str = Field(default="active", min_length=1, max_length=32)
    allowed_step_kinds: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    preferred_runtime_types: list[str] = Field(default_factory=list)


class ProjectAgentBindingUpdate(BaseModel):
    role_hint: Optional[str] = None
    priority: Optional[int] = Field(default=None, ge=0)
    status: Optional[str] = Field(default=None, min_length=1, max_length=32)
    allowed_step_kinds: Optional[list[str]] = None
    preferred_skills: Optional[list[str]] = None
    preferred_runtime_types: Optional[list[str]] = None


class ProjectAgentBindingResponse(ORMModel):
    binding_id: UUID
    project_id: UUID
    agent_id: UUID
    role_hint: Optional[str]
    priority: int
    status: str
    allowed_step_kinds: list[str]
    preferred_skills: list[str]
    preferred_runtime_types: list[str]
    created_at: datetime
    updated_at: datetime


class ExternalAgentDispatchResponse(ORMModel):
    dispatch_id: UUID
    agent_id: UUID
    binding_id: UUID
    project_id: Optional[UUID]
    run_id: Optional[UUID]
    node_id: Optional[UUID]
    source_type: str
    source_id: str
    runtime_type: str
    request_payload: dict[str, Any]
    result_payload: dict[str, Any]
    status: str
    error_message: Optional[str]
    acked_at: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    expires_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class AgentProvisioningProfileCreate(BaseModel):
    step_kind: str = Field(..., min_length=1, max_length=50)
    agent_type: str = Field(..., min_length=1, max_length=100)
    template_id: Optional[str] = None
    default_skill_ids: list[str] = Field(default_factory=list)
    default_provider: Optional[str] = None
    default_model: Optional[str] = None
    runtime_type: str = Field(default="project_sandbox", min_length=1, max_length=50)
    temperature: Optional[float] = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=4000, ge=1)
    sandbox_mode: str = Field(default="run_shared", min_length=1, max_length=50)
    ephemeral: bool = True


class AgentProvisioningProfileUpdate(BaseModel):
    agent_type: Optional[str] = Field(default=None, min_length=1, max_length=100)
    template_id: Optional[str] = None
    default_skill_ids: Optional[list[str]] = None
    default_provider: Optional[str] = None
    default_model: Optional[str] = None
    runtime_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    sandbox_mode: Optional[str] = Field(default=None, min_length=1, max_length=50)
    ephemeral: Optional[bool] = None


class AgentProvisioningProfileResponse(ORMModel):
    profile_id: UUID
    project_id: UUID
    step_kind: str
    agent_type: str
    template_id: Optional[str]
    default_skill_ids: list[str]
    default_provider: Optional[str]
    default_model: Optional[str]
    runtime_type: str
    temperature: Optional[float]
    max_tokens: Optional[int]
    sandbox_mode: str
    ephemeral: bool
    created_at: datetime
    updated_at: datetime


class StepExecutorAssignmentResponse(BaseModel):
    executor_kind: str
    agent_id: Optional[UUID] = None
    node_id: Optional[UUID] = None
    dispatch_id: Optional[UUID] = None
    selection_reason: Optional[str] = None
    provisioned_agent: bool = False
    runtime_type: Optional[str] = None


class RunWorkspaceDescriptorResponse(BaseModel):
    workspace_id: str
    root_path: str
    sandbox_mode: str


class RunSchedulingResponse(BaseModel):
    run: ProjectRunResponse
    agent_assignment: Optional[StepExecutorAssignmentResponse] = None
    external_dispatch: Optional[ExternalAgentDispatchResponse] = None
    executor_assignment: Optional[StepExecutorAssignmentResponse] = None
    run_workspace: Optional[RunWorkspaceDescriptorResponse] = None


class ProjectTaskCreate(BaseModel):
    project_id: UUID
    plan_id: Optional[UUID] = None
    run_id: Optional[UUID] = None
    assignee_agent_id: Optional[UUID] = None
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = Field(default="pending", min_length=1, max_length=50)
    priority: str = Field(default="normal", min_length=1, max_length=50)
    sort_order: int = Field(default=0, ge=0)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Optional[str] = Field(default=None, min_length=1, max_length=50)


class ProjectTaskUpdate(BaseModel):
    plan_id: Optional[UUID] = None
    run_id: Optional[UUID] = None
    assignee_agent_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = Field(default=None, min_length=1, max_length=50)
    priority: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sort_order: Optional[int] = Field(default=None, ge=0)
    input_payload: Optional[dict[str, Any]] = None
    output_payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class TaskTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class ProjectTaskResponse(ORMModel):
    project_task_id: UUID
    project_id: UUID
    plan_id: Optional[UUID]
    run_id: Optional[UUID]
    assignee_agent_id: Optional[UUID]
    title: str
    description: Optional[str]
    status: str
    priority: str
    sort_order: int
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    error_message: Optional[str]
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectTaskCreateAndLaunchRequest(BaseModel):
    project_id: UUID
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    priority: str = Field(default="normal", min_length=1, max_length=50)
    assignee_agent_id: Optional[UUID] = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    execution_mode: Optional[str] = Field(default=None, min_length=1, max_length=50)


class ProjectTaskLaunchBundleResponse(BaseModel):
    task: ProjectTaskResponse
    plan: Optional[ProjectPlanResponse] = None
    run: Optional[ProjectRunResponse] = None
    node: Optional["ExecutionAttemptNodeReadModel"] = None
    needs_clarification: bool = False
    clarification_questions: list[dict[str, Any]] = Field(default_factory=list)
    agent_assignment: Optional[StepExecutorAssignmentResponse] = None
    external_dispatch: Optional[ExternalAgentDispatchResponse] = None
    executor_assignment: Optional[StepExecutorAssignmentResponse] = None
    run_workspace: Optional[RunWorkspaceDescriptorResponse] = None


class ProjectPlanCreate(BaseModel):
    project_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    goal: Optional[str] = None
    status: str = Field(default="draft", min_length=1, max_length=50)
    version: int = Field(default=1, ge=1)
    definition: dict[str, Any] = Field(default_factory=dict)


class ProjectPlanUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    goal: Optional[str] = None
    status: Optional[str] = Field(default=None, min_length=1, max_length=50)
    version: Optional[int] = Field(default=None, ge=1)
    definition: Optional[dict[str, Any]] = None


class PlanStatusRequest(BaseModel):
    status: str = Field(default="active", min_length=1, max_length=50)


class ProjectPlanResponse(ORMModel):
    plan_id: UUID
    project_id: UUID
    name: str
    goal: Optional[str]
    status: str
    version: int
    definition: dict[str, Any]
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectRunCreate(BaseModel):
    project_id: UUID
    plan_id: Optional[UUID] = None
    status: str = Field(default="queued", min_length=1, max_length=50)
    trigger_source: str = Field(default="manual", min_length=1, max_length=50)
    runtime_context: dict[str, Any] = Field(default_factory=dict)


class ProjectRunUpdate(BaseModel):
    plan_id: Optional[UUID] = None
    status: Optional[str] = Field(default=None, min_length=1, max_length=50)
    trigger_source: Optional[str] = Field(default=None, min_length=1, max_length=50)
    runtime_context: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class RunTransitionRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)
    error_message: Optional[str] = None


class ProjectRunResponse(ORMModel):
    run_id: UUID
    project_id: UUID
    plan_id: Optional[UUID]
    status: str
    trigger_source: str
    runtime_context: dict[str, Any]
    error_message: Optional[str]
    requested_by_user_id: UUID
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ExecutionAttemptNodeUpdateRequest(BaseModel):
    project_task_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    node_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    status: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sequence_number: Optional[int] = Field(default=None, ge=0)
    node_payload: Optional[dict[str, Any]] = None
    result_payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class ExecutionAttemptNodeStatusRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class ExecutionAttemptNodeCreateRequest(BaseModel):
    project_task_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    node_type: str = Field(default="task", min_length=1, max_length=50)
    status: str = Field(default="pending", min_length=1, max_length=50)
    sequence_number: int = Field(default=0, ge=0)
    node_payload: dict[str, Any] = Field(default_factory=dict)


class ProjectSpaceUpsert(BaseModel):
    storage_uri: Optional[str] = Field(default=None, max_length=500)
    branch_name: Optional[str] = Field(default=None, max_length=255)
    status: str = Field(default="active", min_length=1, max_length=50)
    root_path: Optional[str] = Field(default=None, max_length=500)
    space_metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectSpaceResponse(ORMModel):
    project_space_id: UUID
    project_id: UUID
    storage_uri: Optional[str]
    branch_name: Optional[str]
    status: str
    root_path: Optional[str]
    space_metadata: dict[str, Any]
    last_synced_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime




class ExtensionPackageCreate(BaseModel):
    project_id: UUID
    name: str = Field(..., min_length=1, max_length=255)
    package_type: str = Field(default="tooling", min_length=1, max_length=50)
    source_uri: Optional[str] = Field(default=None, max_length=500)
    status: str = Field(default="installed", min_length=1, max_length=50)
    manifest: dict[str, Any] = Field(default_factory=dict)


class ExtensionPackageUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    package_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    source_uri: Optional[str] = Field(default=None, max_length=500)
    status: Optional[str] = Field(default=None, min_length=1, max_length=50)
    manifest: Optional[dict[str, Any]] = None


class ExtensionPackageResponse(ORMModel):
    extension_package_id: UUID
    project_id: UUID
    name: str
    package_type: str
    source_uri: Optional[str]
    status: str
    manifest: dict[str, Any]
    installed_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class SkillImportRequest(BaseModel):
    project_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=255)
    source_uri: Optional[str] = Field(default=None, max_length=500)
    manifest: dict[str, Any] = Field(default_factory=dict)


class SkillPackageTestRequest(BaseModel):
    status: str = Field(default="verified", min_length=1, max_length=50)
    test_result: dict[str, Any] = Field(default_factory=dict)


class SkillPackageResponse(ORMModel):
    skill_package_id: UUID
    project_id: Optional[UUID]
    name: str
    slug: str
    source_uri: Optional[str]
    status: str
    manifest: dict[str, Any]
    test_result: dict[str, Any]
    imported_by_user_id: UUID
    last_tested_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class ProjectActivityItemResponse(FrontendReadModel):
    id: str
    title: str
    description: str
    timestamp: datetime
    level: str
    actor: Optional[str] = None
    task_id: Optional[str] = None


class PlannerClarificationQuestionResponse(FrontendReadModel):
    question: str
    importance: Optional[str] = None


class ProjectTaskMetadataItemResponse(FrontendReadModel):
    label: str
    value: str


class ProjectDeliverableResponse(FrontendReadModel):
    filename: str
    path: str
    size: int
    download_url: Optional[str] = None
    is_target: bool
    source_scope: Optional[str] = None


class ProjectTaskSummaryReadModel(FrontendReadModel):
    id: str
    title: str
    status: str
    priority: int
    updated_at: datetime
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    dependency_ids: list[str] = Field(default_factory=list)
    review_status: Optional[str] = None
    ready: bool = True
    blocking_dependency_count: int = 0
    open_issue_count: int = 0
    latest_change_bundle_status: Optional[str] = None
    next_action: Optional[str] = None
    blocker_reason: Optional[str] = None


class TaskContractReadModel(FrontendReadModel):
    id: str
    task_id: str
    version: int
    goal: Optional[str] = None
    scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    allowed_surface: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TaskDependencyReadModel(FrontendReadModel):
    id: str
    project_task_id: str
    depends_on_task_id: str
    depends_on_task_title: Optional[str] = None
    depends_on_task_status: Optional[str] = None
    required_state: str
    dependency_type: str
    artifact_selector: dict[str, Any] = Field(default_factory=dict)
    satisfied: bool
    created_at: datetime
    updated_at: datetime


class TaskHandoffReadModel(FrontendReadModel):
    id: str
    task_id: str
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    stage: str
    from_actor: str
    to_actor: Optional[str] = None
    status_from: Optional[str] = None
    status_to: Optional[str] = None
    title: Optional[str] = None
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TaskChangeBundleReadModel(FrontendReadModel):
    id: str
    task_id: str
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    bundle_kind: str
    status: str
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    summary: Optional[str] = None
    commit_count: int = 0
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    artifact_manifest: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TaskEvidenceBundleReadModel(FrontendReadModel):
    id: str
    task_id: str
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    summary: str
    status: str
    bundle: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class TaskReviewIssueReadModel(FrontendReadModel):
    id: str
    task_id: str
    change_bundle_id: Optional[str] = None
    evidence_bundle_id: Optional[str] = None
    handoff_id: Optional[str] = None
    issue_key: Optional[str] = None
    severity: str
    category: str
    acceptance_ref: Optional[str] = None
    summary: str
    suggestion: Optional[str] = None
    status: str
    resolved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ExecutionAttemptReadModel(FrontendReadModel):
    id: str
    task_id: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    trigger_source: str
    execution_mode: Optional[str] = None
    current_step_title: Optional[str] = None
    failure_reason: Optional[str] = None
    total_nodes: int = 0
    completed_nodes: int = 0
    active_runtime_sessions: int = 0


class ExecutionAttemptNodeReadModel(FrontendReadModel):
    id: str
    run_id: str
    task_id: Optional[str] = None
    name: str
    node_type: str
    status: str
    sequence_number: int
    execution_mode: Optional[str] = None
    executor_kind: Optional[str] = None
    runtime_type: Optional[str] = None
    suggested_agent_ids: list[str] = Field(default_factory=list)
    dependency_step_ids: list[str] = Field(default_factory=list)
    node_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RuntimeSessionReadModel(FrontendReadModel):
    id: str
    run_id: str
    node_id: Optional[str] = None
    session_type: str
    status: str
    runtime_type: Optional[str] = None
    agent_id: Optional[str] = None
    binding_id: Optional[str] = None
    workspace_root: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TaskContractUpsertRequest(FrontendRequestModel):
    goal: Optional[str] = None
    scope: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    allowed_surface: dict[str, Any] = Field(default_factory=dict)


class TaskDependencyReplaceItem(FrontendRequestModel):
    depends_on_task_id: str = Field(..., min_length=1)
    required_state: str = Field(default="approved", min_length=1, max_length=32)
    dependency_type: str = Field(default="hard", min_length=1, max_length=32)
    artifact_selector: dict[str, Any] = Field(default_factory=dict)


class TaskDependencyReplaceRequest(FrontendRequestModel):
    dependencies: list[TaskDependencyReplaceItem] = Field(default_factory=list)


class TaskHandoffCreateRequest(FrontendRequestModel):
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    stage: str = Field(..., min_length=1, max_length=64)
    from_actor: str = Field(..., min_length=1, max_length=128)
    to_actor: Optional[str] = Field(default=None, max_length=128)
    status_from: Optional[str] = Field(default=None, max_length=50)
    status_to: Optional[str] = Field(default=None, max_length=50)
    title: Optional[str] = Field(default=None, max_length=255)
    summary: str = Field(..., min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskChangeBundleCreateRequest(FrontendRequestModel):
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    bundle_kind: str = Field(default="patchset", min_length=1, max_length=32)
    status: str = Field(default="draft", min_length=1, max_length=32)
    base_ref: Optional[str] = Field(default=None, max_length=255)
    head_ref: Optional[str] = Field(default=None, max_length=255)
    summary: Optional[str] = None
    commit_count: int = Field(default=0, ge=0)
    changed_files: list[dict[str, Any]] = Field(default_factory=list)
    artifact_manifest: dict[str, Any] = Field(default_factory=dict)


class TaskEvidenceBundleCreateRequest(FrontendRequestModel):
    run_id: Optional[str] = None
    node_id: Optional[str] = None
    summary: str = Field(..., min_length=1)
    status: str = Field(default="collected", min_length=1, max_length=32)
    bundle: dict[str, Any] = Field(default_factory=dict)


class TaskReviewIssueCreateRequest(FrontendRequestModel):
    change_bundle_id: Optional[str] = None
    evidence_bundle_id: Optional[str] = None
    handoff_id: Optional[str] = None
    issue_key: Optional[str] = Field(default=None, max_length=128)
    severity: str = Field(default="medium", min_length=1, max_length=32)
    category: str = Field(default="other", min_length=1, max_length=32)
    acceptance_ref: Optional[str] = Field(default=None, max_length=128)
    summary: str = Field(..., min_length=1)
    suggestion: Optional[str] = None
    status: str = Field(default="open", min_length=1, max_length=32)


class TaskReviewIssueUpdateRequest(FrontendRequestModel):
    severity: Optional[str] = Field(default=None, min_length=1, max_length=32)
    category: Optional[str] = Field(default=None, min_length=1, max_length=32)
    acceptance_ref: Optional[str] = Field(default=None, max_length=128)
    summary: Optional[str] = None
    suggestion: Optional[str] = None
    status: Optional[str] = Field(default=None, min_length=1, max_length=32)


class ProjectAgentSummaryReadModel(FrontendReadModel):
    id: str
    name: str
    role: str
    status: str
    is_temporary: bool
    avatar: Optional[str] = None
    assigned_at: Optional[datetime] = None


class ProjectAgentBindingReadModel(FrontendReadModel):
    id: str
    project_id: str
    agent_id: str
    agent_name: str
    agent_type: Optional[str] = None
    role_hint: Optional[str] = None
    priority: int
    status: str
    allowed_step_kinds: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    preferred_runtime_types: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AgentProvisioningProfileReadModel(FrontendReadModel):
    id: str
    project_id: str
    step_kind: str
    agent_type: str
    template_id: Optional[str] = None
    default_skill_ids: list[str] = Field(default_factory=list)
    default_provider: Optional[str] = None
    default_model: Optional[str] = None
    runtime_type: str
    sandbox_mode: str
    ephemeral: bool
    created_at: datetime
    updated_at: datetime


class RunExecutorAssignmentReadModel(FrontendReadModel):
    executor_kind: Optional[str] = None
    agent_id: Optional[str] = None
    node_id: Optional[str] = None
    selection_reason: Optional[str] = None
    provisioned_agent: bool = False
    runtime_type: Optional[str] = None


class ExternalAgentDispatchReadModel(FrontendReadModel):
    id: str
    agent_id: str
    binding_id: str
    project_id: str
    run_id: str
    node_id: str
    source_type: str
    source_id: str
    runtime_type: str
    status: str
    error_message: Optional[str] = None
    request_payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    acked_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class RunSummaryReadModel(FrontendReadModel):
    id: str
    project_id: str
    project_title: str
    status: str
    created_at: datetime
    trigger_source: str
    execution_mode: Optional[str] = None
    planner_source: Optional[str] = None
    planner_summary: Optional[str] = None
    step_total: int = 0
    completed_step_count: int = 0
    active_step_count: int = 0
    parallel_group_count: int = 0
    current_step_title: Optional[str] = None
    suggested_agent_ids: list[str] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_questions: list[PlannerClarificationQuestionResponse] = Field(
        default_factory=list
    )
    task_id: Optional[str] = None
    task_title: Optional[str] = None
    failure_reason: Optional[str] = None
    handled_at: Optional[str] = None
    handled_signature: Optional[str] = None
    alert_signature: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    external_agent_count: int = 0
    latest_signal: Optional[str] = None


class ProjectSummaryReadModel(FrontendReadModel):
    id: str
    title: str
    summary: str
    status: str
    progress: int
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    active_node_count: int = 0
    needs_clarification: bool = False
    latest_signal: Optional[str] = None


class ProjectDetailReadModel(ProjectSummaryReadModel):
    instructions: str
    department_id: Optional[str] = None
    workspace_bucket: Optional[str] = None
    project_workspace_root: Optional[str] = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    tasks: list[ProjectTaskSummaryReadModel] = Field(default_factory=list)
    runs: list[RunSummaryReadModel] = Field(default_factory=list)
    agents: list[ProjectAgentSummaryReadModel] = Field(default_factory=list)
    deliverables: list[ProjectDeliverableResponse] = Field(default_factory=list)
    recent_activity: list[ProjectActivityItemResponse] = Field(default_factory=list)
    agent_bindings: list[ProjectAgentBindingReadModel] = Field(default_factory=list)
    provisioning_profiles: list[AgentProvisioningProfileReadModel] = Field(
        default_factory=list
    )


class ProjectTaskDetailReadModel(ProjectTaskSummaryReadModel):
    project_id: str
    project_title: str
    project_status: str
    description: str
    execution_mode: Optional[str] = None
    planner_source: Optional[str] = None
    planner_summary: Optional[str] = None
    step_total: int = 0
    completed_step_count: int = 0
    active_step_count: int = 0
    parallel_group_count: int = 0
    current_step_title: Optional[str] = None
    suggested_agent_ids: list[str] = Field(default_factory=list)
    clarification_questions: list[PlannerClarificationQuestionResponse] = Field(
        default_factory=list
    )
    acceptance_criteria: Optional[str] = None
    assigned_skill_names: list[str] = Field(default_factory=list)
    latest_result: Optional[str] = None
    contract: Optional[TaskContractReadModel] = None
    dependencies: list[TaskDependencyReadModel] = Field(default_factory=list)
    handoffs: list[TaskHandoffReadModel] = Field(default_factory=list)
    latest_change_bundle: Optional[TaskChangeBundleReadModel] = None
    latest_evidence_bundle: Optional[TaskEvidenceBundleReadModel] = None
    review_issues: list[TaskReviewIssueReadModel] = Field(default_factory=list)
    open_issue_count: int = 0
    attempts: list[ExecutionAttemptReadModel] = Field(default_factory=list)
    metadata: list[ProjectTaskMetadataItemResponse] = Field(default_factory=list)
    events: list[ProjectActivityItemResponse] = Field(default_factory=list)


class RunDetailReadModel(RunSummaryReadModel):
    project_summary: str
    timeline: list[ProjectActivityItemResponse] = Field(default_factory=list)
    deliverables: list[ProjectDeliverableResponse] = Field(default_factory=list)
    run_workspace_root: Optional[str] = None
    executor_assignment: Optional[RunExecutorAssignmentReadModel] = None
    external_dispatches: list[ExternalAgentDispatchReadModel] = Field(default_factory=list)
    nodes: list[ExecutionAttemptNodeReadModel] = Field(default_factory=list)
    runtime_sessions: list[RuntimeSessionReadModel] = Field(default_factory=list)
