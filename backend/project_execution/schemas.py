from __future__ import annotations

"""Pydantic schemas for the project execution backend skeleton."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    """Base schema configured for SQLAlchemy object responses."""

    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = Field(default="draft", min_length=1, max_length=50)
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
    run_step_id: Optional[UUID]
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
    preferred_node_selector: Optional[str] = None
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
    preferred_node_selector: Optional[str] = None
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
    preferred_node_selector: Optional[str]
    temperature: Optional[float]
    max_tokens: Optional[int]
    sandbox_mode: str
    ephemeral: bool
    created_at: datetime
    updated_at: datetime


class StepExecutorAssignmentResponse(BaseModel):
    executor_kind: str
    agent_id: Optional[UUID] = None
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


class ProjectTaskLaunchBundleResponse(BaseModel):
    task: ProjectTaskResponse
    plan: ProjectPlanResponse
    run: ProjectRunResponse
    step: ProjectRunStepResponse
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


class ProjectRunStepCreate(BaseModel):
    run_id: UUID
    project_task_id: Optional[UUID] = None
    name: str = Field(..., min_length=1, max_length=255)
    step_type: str = Field(default="task", min_length=1, max_length=50)
    status: str = Field(default="pending", min_length=1, max_length=50)
    sequence_number: int = Field(default=0, ge=0)
    input_payload: dict[str, Any] = Field(default_factory=dict)


class ProjectRunStepUpdate(BaseModel):
    project_task_id: Optional[UUID] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    step_type: Optional[str] = Field(default=None, min_length=1, max_length=50)
    status: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sequence_number: Optional[int] = Field(default=None, ge=0)
    input_payload: Optional[dict[str, Any]] = None
    output_payload: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class RunStepStatusRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class ProjectRunStepResponse(ORMModel):
    run_step_id: UUID
    run_id: UUID
    project_task_id: Optional[UUID]
    name: str
    step_type: str
    status: str
    sequence_number: int
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    error_message: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


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
