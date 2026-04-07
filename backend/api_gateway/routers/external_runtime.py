from __future__ import annotations

import hashlib
import io
import tarfile
import textwrap
import zipfile
from dataclasses import dataclass
from datetime import timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from access_control.agent_access import load_accessible_agent_or_raise
from access_control.permissions import CurrentUser, get_current_user
from api_gateway.feishu_publication_helpers import resolve_public_web_base_url
from database.connection import get_db_session
from database.project_execution_models import ExternalAgentBinding
from project_execution.external_runtime_schemas import (
    ExternalAgentDispatchResponse,
    ExternalAgentProfileResponse,
    ExternalAgentProfileUpdateRequest,
    ExternalDispatchProgressRequest,
    ExternalInstallCommandRequest,
    ExternalInstallCommandResponse,
    ExternalRuntimeArtifactManifestResponse,
    ExternalRuntimeArtifactRecord,
    ExternalRuntimeBootstrapRequest,
    ExternalRuntimeBootstrapResponse,
    ExternalRuntimeHeartbeatRequest,
    ExternalRuntimeHeartbeatResponse,
    ExternalRuntimeOverviewResponse,
    ExternalRuntimeStateResponse,
    ExternalRuntimeUpdateCheckResponse,
    ExternalUpdateCommandRequest,
    ExternalUpdateCommandResponse,
)
from project_execution.external_runtime_service import (
    CURRENT_EXTERNAL_RUNTIME_VERSION,
    EXTERNAL_RUNTIME_OFFLINE_SECONDS,
    EXTERNAL_RUNTIME_TYPES,
    SUPPORTED_EXTERNAL_TARGETS,
    ExternalRuntimeBindingRevokedError,
    ExternalRuntimeConflictError,
    ExternalRuntimeInstallCodeError,
    ExternalRuntimeNoDispatchError,
    ExternalRuntimePlatformError,
    ExternalRuntimeService,
    ExternalRuntimeTokenError,
)
from project_execution.service import parse_uuid

user_router = APIRouter()
host_router = APIRouter()
_machine_security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class ExternalBindingPrincipal:
    binding_id: UUID
    agent_id: UUID
    machine_token: str


def _to_state_response(state) -> ExternalRuntimeStateResponse:
    return ExternalRuntimeStateResponse(
        status=state.status,
        bound=state.bound,
        availableForConversation=state.available_for_conversation,
        availableForExecution=state.available_for_execution,
        hostName=state.host_name,
        hostOs=state.host_os,
        hostArch=state.host_arch,
        currentVersion=state.current_version,
        desiredVersion=state.desired_version,
        lastSeenAt=state.last_seen_at,
        boundAt=state.bound_at,
        lastErrorMessage=state.last_error_message,
        updateAvailable=state.update_available,
    )


async def get_current_external_agent_binding(
    credentials: HTTPAuthorizationCredentials = Depends(_machine_security),
) -> ExternalBindingPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="external_agent_machine_token_invalid")
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        try:
            binding = service.get_binding_by_machine_token(raw_token=credentials.credentials)
        except ExternalRuntimeBindingRevokedError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        except ExternalRuntimeTokenError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        return ExternalBindingPrincipal(
            binding_id=binding.binding_id,
            agent_id=binding.agent_id,
            machine_token=credentials.credentials,
        )


def _resolve_public_base_url_or_400(request: Request | None = None) -> str:
    base_url = resolve_public_web_base_url(request)
    if not base_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LINX_PUBLIC_BASE_URL is required for external runtime installation",
        )
    return base_url.rstrip("/")


def _assert_external_agent_for_user(*, session, agent_id: str, current_user: CurrentUser):
    agent = load_accessible_agent_or_raise(session, agent_id, current_user, access_type="manage")
    if str(getattr(agent, "runtime_preference", "") or "") not in EXTERNAL_RUNTIME_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent is not an external runtime agent")
    return agent


@user_router.get("/agents/{agent_id}/external-runtime", response_model=ExternalRuntimeOverviewResponse)
async def get_external_runtime_overview(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        agent = _assert_external_agent_for_user(session=session, agent_id=agent_id, current_user=current_user)
        service = ExternalRuntimeService(session)
        profile = service.get_or_create_profile(agent_id=agent.agent_id)
        state = service.summarize_state(agent=agent)
        return ExternalRuntimeOverviewResponse(
            state=_to_state_response(state),
            profile=ExternalAgentProfileResponse.model_validate(profile),
        )


@user_router.patch("/agents/{agent_id}/external-runtime/profile", response_model=ExternalRuntimeOverviewResponse)
async def update_external_runtime_profile(
    agent_id: str,
    payload: ExternalAgentProfileUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        agent = _assert_external_agent_for_user(session=session, agent_id=agent_id, current_user=current_user)
        service = ExternalRuntimeService(session)
        profile = service.update_profile(
            agent_id=agent.agent_id,
            path_allowlist=payload.pathAllowlist,
            launch_command_template=payload.launchCommandTemplate,
            install_channel=payload.installChannel,
            desired_version=payload.desiredVersion,
        )
        state = service.summarize_state(agent=agent)
        return ExternalRuntimeOverviewResponse(
            state=_to_state_response(state),
            profile=ExternalAgentProfileResponse.model_validate(profile),
        )


@user_router.post("/agents/{agent_id}/external-runtime/install-command", response_model=ExternalInstallCommandResponse)
async def create_external_runtime_install_command(
    agent_id: str,
    payload: ExternalInstallCommandRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    base_url = _resolve_public_base_url_or_400(request)
    with get_db_session() as session:
        agent = _assert_external_agent_for_user(session=session, agent_id=agent_id, current_user=current_user)
        service = ExternalRuntimeService(session)
        try:
            row, raw_code = service.create_install_token(
                agent_id=agent.agent_id,
                created_by_user_id=parse_uuid(current_user.user_id, "current_user"),
            )
            command = service.build_install_command(
                agent_id=agent.agent_id,
                target_os=payload.target_os,
                code=raw_code,
                base_url=base_url,
            )
        except ExternalRuntimeConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ExternalRuntimePlatformError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return ExternalInstallCommandResponse(command=command, expires_at=row.expires_at)


@user_router.post("/agents/{agent_id}/external-runtime/update-command", response_model=ExternalUpdateCommandResponse)
async def create_external_runtime_update_command(
    agent_id: str,
    payload: ExternalUpdateCommandRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    base_url = _resolve_public_base_url_or_400(request)
    with get_db_session() as session:
        agent = _assert_external_agent_for_user(session=session, agent_id=agent_id, current_user=current_user)
        service = ExternalRuntimeService(session)
        try:
            command = service.build_update_command(agent_id=agent.agent_id, target_os=payload.target_os, base_url=base_url)
        except ExternalRuntimePlatformError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return ExternalUpdateCommandResponse(command=command)


@user_router.post("/agents/{agent_id}/external-runtime/unbind", status_code=status.HTTP_200_OK)
async def unbind_external_runtime(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        agent = _assert_external_agent_for_user(session=session, agent_id=agent_id, current_user=current_user)
        ExternalRuntimeService(session).unbind_agent(agent_id=agent.agent_id)
        return {"success": True, "agent_id": str(agent.agent_id)}


@host_router.post("/external-runtime/bootstrap", response_model=ExternalRuntimeBootstrapResponse)
async def bootstrap_external_runtime(payload: ExternalRuntimeBootstrapRequest):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        agent = service.get_agent(payload.agent_id)
        if not service.is_external_runtime_type(getattr(agent, "runtime_preference", None)):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent is not an external runtime agent")
        try:
            binding, machine_token, profile = service.bootstrap_binding(
                agent_id=payload.agent_id,
                install_code=payload.install_code,
                host_name=payload.host_name,
                host_os=payload.host_os,
                host_arch=payload.host_arch,
                host_fingerprint=payload.host_fingerprint,
                current_version=payload.current_version,
                metadata=payload.metadata,
            )
            binding = service.heartbeat(
                binding=binding,
                host_fingerprint=payload.host_fingerprint,
                host_name=payload.host_name,
                host_os=payload.host_os,
                host_arch=payload.host_arch,
                current_version=payload.current_version,
                status_value="online",
                last_error_message=None,
                metadata=payload.metadata,
            )
            state = service.summarize_state(agent=agent)
        except ExternalRuntimeConflictError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        except ExternalRuntimeInstallCodeError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return ExternalRuntimeBootstrapResponse(
            machine_token=machine_token,
            state=_to_state_response(state),
            profile=ExternalAgentProfileResponse.model_validate(profile),
            desired_version=profile.desired_version,
            heartbeat_interval_seconds=20,
            dispatch_poll_interval_seconds=25,
        )


@host_router.post("/external-runtime/heartbeat", response_model=ExternalRuntimeHeartbeatResponse)
async def heartbeat_external_runtime(
    payload: ExternalRuntimeHeartbeatRequest,
    principal: ExternalBindingPrincipal = Depends(get_current_external_agent_binding),
):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        binding = session.query(ExternalAgentBinding).filter(ExternalAgentBinding.binding_id == principal.binding_id).first()
        if binding is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="external_agent_machine_token_invalid")
        try:
            binding = service.heartbeat(
                binding=binding,
                host_fingerprint=payload.host_fingerprint,
                host_name=payload.host_name,
                host_os=payload.host_os,
                host_arch=payload.host_arch,
                current_version=payload.current_version,
                status_value=payload.status,
                last_error_message=payload.last_error_message,
                metadata=payload.metadata,
            )
        except ExternalRuntimeBindingRevokedError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
        agent = service.get_agent(binding.agent_id)
        state = service.summarize_state(agent=agent)
        return ExternalRuntimeHeartbeatResponse(
            state=_to_state_response(state),
            desired_version=state.desired_version or CURRENT_EXTERNAL_RUNTIME_VERSION,
            update_available=state.update_available,
        )


@host_router.post("/external-runtime/update-check", response_model=ExternalRuntimeUpdateCheckResponse)
async def update_check_external_runtime(
    principal: ExternalBindingPrincipal = Depends(get_current_external_agent_binding),
):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        agent = service.get_agent(principal.agent_id)
        state = service.summarize_state(agent=agent)
        return ExternalRuntimeUpdateCheckResponse(
            desired_version=state.desired_version or CURRENT_EXTERNAL_RUNTIME_VERSION,
            current_version=state.current_version,
            update_available=state.update_available,
        )


@host_router.get("/external-runtime/dispatches/next", response_model=ExternalAgentDispatchResponse)
async def get_next_external_dispatch(
    principal: ExternalBindingPrincipal = Depends(get_current_external_agent_binding),
):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        binding = session.query(ExternalAgentBinding).filter(ExternalAgentBinding.binding_id == principal.binding_id).first()
        if binding is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="external_agent_machine_token_invalid")
        try:
            dispatch = service.get_next_dispatch(binding=binding)
        except ExternalRuntimeNoDispatchError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        return ExternalAgentDispatchResponse.model_validate(dispatch)


@host_router.post("/external-runtime/dispatches/{dispatch_id}/ack", response_model=ExternalAgentDispatchResponse)
async def ack_external_dispatch(
    dispatch_id: str,
    payload: ExternalDispatchProgressRequest,
    principal: ExternalBindingPrincipal = Depends(get_current_external_agent_binding),
):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        binding = session.query(ExternalAgentBinding).filter(ExternalAgentBinding.binding_id == principal.binding_id).first()
        dispatch = service.get_dispatch_for_binding(binding=binding, dispatch_id=parse_uuid(dispatch_id, "dispatch_id"))
        dispatch = service.ack_dispatch(dispatch=dispatch, result_payload=payload.result_payload)
        return ExternalAgentDispatchResponse.model_validate(dispatch)


@host_router.post("/external-runtime/dispatches/{dispatch_id}/progress", response_model=ExternalAgentDispatchResponse)
async def progress_external_dispatch(
    dispatch_id: str,
    payload: ExternalDispatchProgressRequest,
    principal: ExternalBindingPrincipal = Depends(get_current_external_agent_binding),
):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        binding = session.query(ExternalAgentBinding).filter(ExternalAgentBinding.binding_id == principal.binding_id).first()
        dispatch = service.get_dispatch_for_binding(binding=binding, dispatch_id=parse_uuid(dispatch_id, "dispatch_id"))
        dispatch = service.progress_dispatch(
            dispatch=dispatch,
            result_payload=payload.result_payload,
            error_message=payload.error_message,
            status_value=payload.status,
        )
        return ExternalAgentDispatchResponse.model_validate(dispatch)


@host_router.post("/external-runtime/dispatches/{dispatch_id}/complete", response_model=ExternalAgentDispatchResponse)
async def complete_external_dispatch(
    dispatch_id: str,
    payload: ExternalDispatchProgressRequest,
    principal: ExternalBindingPrincipal = Depends(get_current_external_agent_binding),
):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        binding = session.query(ExternalAgentBinding).filter(ExternalAgentBinding.binding_id == principal.binding_id).first()
        dispatch = service.get_dispatch_for_binding(binding=binding, dispatch_id=parse_uuid(dispatch_id, "dispatch_id"))
        dispatch = service.complete_dispatch(dispatch=dispatch, result_payload=payload.result_payload)
        return ExternalAgentDispatchResponse.model_validate(dispatch)


@host_router.post("/external-runtime/dispatches/{dispatch_id}/fail", response_model=ExternalAgentDispatchResponse)
async def fail_external_dispatch(
    dispatch_id: str,
    payload: ExternalDispatchProgressRequest,
    principal: ExternalBindingPrincipal = Depends(get_current_external_agent_binding),
):
    with get_db_session() as session:
        service = ExternalRuntimeService(session)
        binding = session.query(ExternalAgentBinding).filter(ExternalAgentBinding.binding_id == principal.binding_id).first()
        dispatch = service.get_dispatch_for_binding(binding=binding, dispatch_id=parse_uuid(dispatch_id, "dispatch_id"))
        dispatch = service.fail_dispatch(
            dispatch=dispatch,
            result_payload=payload.result_payload,
            error_message=payload.error_message,
        )
        return ExternalAgentDispatchResponse.model_validate(dispatch)


# --- artifact helpers -----------------------------------------------------

def _runtime_payload_text(version: str, target_os: str, arch: str) -> str:
    executable_name = "linx-external-runtime.exe" if target_os == "windows" else "linx-external-runtime"
    return textwrap.dedent(
        f"""
        Placeholder external runtime package
        version={version}
        os={target_os}
        arch={arch}
        executable={executable_name}
        """
    ).strip() + "\n"


def _build_artifact_bytes(version: str, target_os: str, arch: str) -> tuple[bytes, str, str]:
    folder_name = f"linx-external-runtime_{version}_{target_os}_{arch}"
    payload = _runtime_payload_text(version, target_os, arch).encode("utf-8")
    if target_os == "windows":
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{folder_name}/README.txt", payload)
            zf.writestr(f"{folder_name}/linx-external-runtime.exe", b"placeholder-runtime-binary\n")
        return buf.getvalue(), f"{folder_name}.zip", "application/zip"

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        readme_info = tarfile.TarInfo(name=f"{folder_name}/README.txt")
        readme_info.size = len(payload)
        tar.addfile(readme_info, io.BytesIO(payload))
        binary_bytes = b"#!/usr/bin/env bash\necho 'placeholder runtime binary'\n"
        binary_info = tarfile.TarInfo(name=f"{folder_name}/linx-external-runtime")
        binary_info.mode = 0o755
        binary_info.size = len(binary_bytes)
        tar.addfile(binary_info, io.BytesIO(binary_bytes))
    suffix = ".tar.gz"
    return buf.getvalue(), f"{folder_name}{suffix}", "application/gzip"


def _build_manifest(base_url: str) -> ExternalRuntimeArtifactManifestResponse:
    artifacts: list[ExternalRuntimeArtifactRecord] = []
    for target_os, archs in SUPPORTED_EXTERNAL_TARGETS.items():
        for arch in archs:
            payload, filename, _content_type = _build_artifact_bytes(CURRENT_EXTERNAL_RUNTIME_VERSION, target_os, arch)
            digest = hashlib.sha256(payload).hexdigest()
            artifacts.append(
                ExternalRuntimeArtifactRecord(
                    version=CURRENT_EXTERNAL_RUNTIME_VERSION,
                    os=target_os,
                    arch=arch,
                    sha256=digest,
                    download_path=f"{base_url}/api/v1/external-runtime/artifacts/{CURRENT_EXTERNAL_RUNTIME_VERSION}/{target_os}/{arch}/download",
                )
            )
    return ExternalRuntimeArtifactManifestResponse(version=CURRENT_EXTERNAL_RUNTIME_VERSION, artifacts=artifacts)


@host_router.get("/external-runtime/artifacts/manifest", response_model=ExternalRuntimeArtifactManifestResponse)
async def get_external_runtime_artifact_manifest(request: Request):
    base_url = _resolve_public_base_url_or_400(request)
    return _build_manifest(base_url)


@host_router.get("/external-runtime/artifacts/{version}/{target_os}/{arch}/download")
async def download_external_runtime_artifact(version: str, target_os: str, arch: str):
    target_os = str(target_os).strip().lower()
    arch = str(arch).strip().lower()
    if version != CURRENT_EXTERNAL_RUNTIME_VERSION:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact version not found")
    if target_os not in SUPPORTED_EXTERNAL_TARGETS or arch not in SUPPORTED_EXTERNAL_TARGETS[target_os]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artifact target not found")
    payload, filename, content_type = _build_artifact_bytes(version, target_os, arch)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(content=payload, media_type=content_type, headers=headers)


@user_router.get("/agents/{agent_id}/external-runtime/install.sh", response_class=PlainTextResponse)
async def render_external_runtime_install_sh(
    agent_id: str,
    request: Request,
    target: str = Query(...),
    code: str = Query(...),
):
    base_url = _resolve_public_base_url_or_400(request)
    target = str(target or "").strip().lower()
    if target not in {"linux", "darwin"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="external_agent_platform_not_supported")
    return textwrap.dedent(
        f"""
        #!/usr/bin/env bash
        set -euo pipefail
        AGENT_ID="{agent_id}"
        TARGET_OS="{target}"
        INSTALL_CODE="{code}"
        CONTROL_PLANE="{base_url}"
        MANIFEST_URL="$CONTROL_PLANE/api/v1/external-runtime/artifacts/manifest"
        echo "Installing LinX external runtime for $AGENT_ID on $TARGET_OS"
        echo "Fetching manifest from $MANIFEST_URL"
        echo "Bootstrap endpoint: $CONTROL_PLANE/api/v1/external-runtime/bootstrap"
        echo "This installer is managed by the control plane."
        """
    ).strip() + "\n"


@user_router.get("/agents/{agent_id}/external-runtime/update.sh", response_class=PlainTextResponse)
async def render_external_runtime_update_sh(
    agent_id: str,
    request: Request,
    target: str = Query(...),
):
    base_url = _resolve_public_base_url_or_400(request)
    return textwrap.dedent(
        f"""
        #!/usr/bin/env bash
        set -euo pipefail
        AGENT_ID="{agent_id}"
        TARGET_OS="{target}"
        CONTROL_PLANE="{base_url}"
        echo "Updating LinX external runtime for $AGENT_ID on $TARGET_OS"
        echo "Fetch latest artifact manifest from $CONTROL_PLANE/api/v1/external-runtime/artifacts/manifest"
        """
    ).strip() + "\n"


@user_router.get("/agents/{agent_id}/external-runtime/install.ps1", response_class=PlainTextResponse)
async def render_external_runtime_install_ps1(
    agent_id: str,
    request: Request,
    target: str = Query(...),
    code: str = Query(...),
):
    base_url = _resolve_public_base_url_or_400(request)
    return textwrap.dedent(
        f"""
        $AgentId = "{agent_id}"
        $TargetOs = "{target}"
        $InstallCode = "{code}"
        $ControlPlane = "{base_url}"
        Write-Host "Installing LinX external runtime for $AgentId on $TargetOs"
        Write-Host "Bootstrap endpoint: $ControlPlane/api/v1/external-runtime/bootstrap"
        """
    ).strip() + "\n"


@user_router.get("/agents/{agent_id}/external-runtime/update.ps1", response_class=PlainTextResponse)
async def render_external_runtime_update_ps1(
    agent_id: str,
    request: Request,
    target: str = Query(...),
):
    base_url = _resolve_public_base_url_or_400(request)
    return textwrap.dedent(
        f"""
        $AgentId = "{agent_id}"
        $TargetOs = "{target}"
        $ControlPlane = "{base_url}"
        Write-Host "Updating LinX external runtime for $AgentId on $TargetOs"
        Write-Host "Manifest endpoint: $ControlPlane/api/v1/external-runtime/artifacts/manifest"
        """
    ).strip() + "\n"
