from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ExternalRuntimeStateResponse(BaseModel):
    status: str
    bound: bool
    availableForConversation: bool
    availableForExecution: bool
    hostName: Optional[str] = None
    hostOs: Optional[str] = None
    hostArch: Optional[str] = None
    currentVersion: Optional[str] = None
    desiredVersion: Optional[str] = None
    lastSeenAt: Optional[datetime] = None
    boundAt: Optional[datetime] = None
    lastErrorMessage: Optional[str] = None
    updateAvailable: bool = False
    runtimeCompatible: bool = True
    compatibilityMessage: Optional[str] = None
    localStatusUrl: Optional[str] = None
    localStatusPort: Optional[int] = None
    lastDispatchAction: Optional[str] = None
    lastDispatchStatus: Optional[str] = None
    lastDispatchErrorMessage: Optional[str] = None


class ExternalAgentProfileUpdateRequest(BaseModel):
    pathAllowlist: Optional[list[str]] = None
    installChannel: Optional[str] = None
    desiredVersion: Optional[str] = None


class ExternalAgentProfileResponse(ORMModel):
    profile_id: UUID
    agent_id: UUID
    path_allowlist: list[str]
    install_channel: str
    desired_version: str
    created_at: datetime
    updated_at: datetime


class ExternalInstallCommandRequest(BaseModel):
    target_os: str = Field(..., min_length=1, max_length=32)


class ExternalInstallCommandResponse(BaseModel):
    command: str
    expires_at: datetime


class ExternalUpdateCommandRequest(BaseModel):
    target_os: str = Field(..., min_length=1, max_length=32)


class ExternalUpdateCommandResponse(BaseModel):
    command: str


class ExternalUninstallCommandRequest(BaseModel):
    target_os: str = Field(..., min_length=1, max_length=32)


class ExternalUninstallCommandResponse(BaseModel):
    command: str


class ExternalRuntimeOverviewResponse(BaseModel):
    state: ExternalRuntimeStateResponse
    profile: ExternalAgentProfileResponse


class ExternalRuntimeBootstrapRequest(BaseModel):
    agent_id: UUID
    install_code: str = Field(..., min_length=1, max_length=255)
    host_name: str = Field(..., min_length=1, max_length=255)
    host_os: str = Field(..., min_length=1, max_length=32)
    host_arch: str = Field(..., min_length=1, max_length=64)
    host_fingerprint: str = Field(..., min_length=1, max_length=255)
    current_version: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalRuntimeBootstrapResponse(BaseModel):
    machine_token: str
    state: ExternalRuntimeStateResponse
    profile: ExternalAgentProfileResponse
    desired_version: str
    heartbeat_interval_seconds: int
    dispatch_poll_interval_seconds: int


class ExternalRuntimeHeartbeatRequest(BaseModel):
    host_name: Optional[str] = None
    host_os: Optional[str] = None
    host_arch: Optional[str] = None
    host_fingerprint: str = Field(..., min_length=1, max_length=255)
    current_version: Optional[str] = None
    status: str = Field(default="online", min_length=1, max_length=32)
    last_error_message: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalRuntimeHeartbeatResponse(BaseModel):
    state: ExternalRuntimeStateResponse
    desired_version: str
    update_available: bool


class ExternalRuntimeUpdateCheckResponse(BaseModel):
    desired_version: str
    current_version: Optional[str] = None
    update_available: bool


class ExternalRuntimeArtifactRecord(BaseModel):
    version: str
    os: str
    arch: str
    sha256: str
    download_path: str
    min_server_version: str = "0.0.0"


class ExternalRuntimeArtifactManifestResponse(BaseModel):
    version: str
    artifacts: list[ExternalRuntimeArtifactRecord]


class ExternalDispatchProgressRequest(BaseModel):
    status: str = Field(default="running", min_length=1, max_length=32)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None


class ExternalDispatchEventCreateRequest(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExternalDispatchEventResponse(ORMModel):
    event_id: UUID
    dispatch_id: UUID
    sequence_number: int
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class ExternalRuntimeLlmMessage(BaseModel):
    role: str = Field(..., min_length=1, max_length=32)
    content: Any
    tool_call_id: Optional[str] = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class ExternalRuntimeLlmChatRequest(BaseModel):
    messages: list[ExternalRuntimeLlmMessage] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ExternalRuntimeLlmChatResponse(BaseModel):
    content: str = ""
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)
    finish_reason: Optional[str] = None


class ExternalConversationWorkspaceDownloadResponse(BaseModel):
    archive_base64: str
    checksum: Optional[str] = None
    generation: int = 0
    size_bytes: int = 0


class ExternalConversationWorkspaceUploadRequest(BaseModel):
    archive_base64: str = Field(..., min_length=1)
    workspace_bytes_estimate: int = Field(default=0, ge=0)
    workspace_file_count_estimate: int = Field(default=0, ge=0)
    snapshot_status: str = Field(default="ready", min_length=1, max_length=32)


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
