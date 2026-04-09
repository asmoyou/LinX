from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from database.models import Agent
from database.project_execution_models import (
    ExternalAgentBinding,
    ExternalAgentDispatch,
    ExternalAgentDispatchEvent,
    ExternalAgentInstallToken,
    ExternalAgentProfile,
    ProjectRun,
    ProjectRunStep,
    ProjectTask,
)
from project_execution.execution_nodes import create_or_update_execution_node_from_step
from project_execution.service import flush_and_refresh, reconcile_run_state, retire_ephemeral_run_agents
from shared.secret_crypto import sha256_text

CURRENT_EXTERNAL_RUNTIME_VERSION = "0.2.0"
EXTERNAL_RUNTIME_OFFLINE_SECONDS = 90
EXTERNAL_INSTALL_CODE_TTL_MINUTES = 15
EXTERNAL_DISPATCH_ACK_TIMEOUT_SECONDS = 60
SUPPORTED_EXTERNAL_TARGETS = {
    "linux": ["amd64", "arm64"],
    "darwin": ["amd64", "arm64"],
    "windows": ["amd64"],
}
EXTERNAL_RUNTIME_TYPES = {"external_worktree", "external_same_dir", "remote_session"}


@dataclass(frozen=True)
class ExternalRuntimeState:
    status: str
    bound: bool
    available_for_conversation: bool
    available_for_execution: bool
    host_name: Optional[str]
    host_os: Optional[str]
    host_arch: Optional[str]
    current_version: Optional[str]
    desired_version: Optional[str]
    runtime_compatible: bool
    compatibility_message: Optional[str]
    last_seen_at: Optional[datetime]
    bound_at: Optional[datetime]
    last_error_message: Optional[str]
    update_available: bool
    local_status_url: Optional[str]
    local_status_port: Optional[int]
    last_dispatch_action: Optional[str]
    last_dispatch_status: Optional[str]
    last_dispatch_error_message: Optional[str]


class ExternalRuntimeUnavailableError(RuntimeError):
    pass


class ExternalRuntimeBindingRevokedError(RuntimeError):
    pass


class ExternalRuntimeTokenError(RuntimeError):
    pass


class ExternalRuntimeInstallCodeError(RuntimeError):
    pass


class ExternalRuntimeConflictError(RuntimeError):
    pass


class ExternalRuntimePlatformError(RuntimeError):
    pass


class ExternalRuntimeNoDispatchError(RuntimeError):
    pass


class ExternalRuntimeService:
    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _parse_version(value: Optional[str]) -> tuple[int, ...]:
        raw = str(value or "").strip()
        if not raw:
            return ()
        parts: list[int] = []
        for chunk in raw.split("."):
            try:
                parts.append(int(chunk))
            except ValueError:
                break
        return tuple(parts)

    @classmethod
    def _is_version_less(cls, value: Optional[str], baseline: str) -> bool:
        parsed_value = cls._parse_version(value)
        parsed_baseline = cls._parse_version(baseline)
        if not parsed_value:
            return True
        return parsed_value < parsed_baseline

    @staticmethod
    def is_external_runtime_type(runtime_type: Optional[str]) -> bool:
        return str(runtime_type or "").strip() in EXTERNAL_RUNTIME_TYPES

    @staticmethod
    def validate_target_os(target_os: str) -> str:
        normalized = str(target_os or "").strip().lower()
        if normalized not in SUPPORTED_EXTERNAL_TARGETS:
            raise ExternalRuntimePlatformError("external_agent_platform_not_supported")
        return normalized

    def get_agent(self, agent_id: UUID) -> Agent:
        agent = self.session.query(Agent).filter(Agent.agent_id == agent_id).first()
        if agent is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
        return agent

    def get_or_create_profile(self, *, agent_id: UUID) -> ExternalAgentProfile:
        profile = (
            self.session.query(ExternalAgentProfile)
            .filter(ExternalAgentProfile.agent_id == agent_id)
            .first()
        )
        if profile is not None:
            if self._is_version_less(profile.desired_version, CURRENT_EXTERNAL_RUNTIME_VERSION):
                profile.desired_version = CURRENT_EXTERNAL_RUNTIME_VERSION
                return flush_and_refresh(self.session, profile)
            return profile
        profile = ExternalAgentProfile(agent_id=agent_id, desired_version=CURRENT_EXTERNAL_RUNTIME_VERSION)
        self.session.add(profile)
        return flush_and_refresh(self.session, profile)

    @staticmethod
    def is_runtime_compatible(*, current_version: Optional[str]) -> bool:
        return str(current_version or "").strip() == CURRENT_EXTERNAL_RUNTIME_VERSION

    def build_compatibility_message(self, *, current_version: Optional[str]) -> Optional[str]:
        if self.is_runtime_compatible(current_version=current_version):
            return None
        if not str(current_version or "").strip():
            return "Runtime Host must be reinstalled to enable native remote execution."
        return (
            "Runtime Host upgrade required for native remote execution "
            f"(current: {current_version}, required: {CURRENT_EXTERNAL_RUNTIME_VERSION})."
        )

    def get_profile(self, *, agent_id: UUID) -> Optional[ExternalAgentProfile]:
        return (
            self.session.query(ExternalAgentProfile)
            .filter(ExternalAgentProfile.agent_id == agent_id)
            .first()
        )

    def update_profile(
        self,
        *,
        agent_id: UUID,
        path_allowlist: Optional[list[str]] = None,
        install_channel: Optional[str] = None,
        desired_version: Optional[str] = None,
    ) -> ExternalAgentProfile:
        profile = self.get_or_create_profile(agent_id=agent_id)
        if path_allowlist is not None:
            profile.path_allowlist = path_allowlist
        if install_channel is not None:
            profile.install_channel = install_channel or "stable"
        if desired_version is not None:
            profile.desired_version = desired_version or CURRENT_EXTERNAL_RUNTIME_VERSION
        return flush_and_refresh(self.session, profile)

    def get_active_binding(self, *, agent_id: UUID) -> Optional[ExternalAgentBinding]:
        return (
            self.session.query(ExternalAgentBinding)
            .filter(ExternalAgentBinding.agent_id == agent_id)
            .filter(ExternalAgentBinding.revoked_at.is_(None))
            .order_by(ExternalAgentBinding.bound_at.desc())
            .first()
        )

    def get_latest_binding(self, *, agent_id: UUID) -> Optional[ExternalAgentBinding]:
        return (
            self.session.query(ExternalAgentBinding)
            .filter(ExternalAgentBinding.agent_id == agent_id)
            .order_by(ExternalAgentBinding.bound_at.desc())
            .first()
        )

    def get_binding_by_machine_token(self, *, raw_token: str) -> ExternalAgentBinding:
        token_hash = sha256_text(raw_token)
        binding = (
            self.session.query(ExternalAgentBinding)
            .filter(ExternalAgentBinding.machine_token_hash == token_hash)
            .order_by(ExternalAgentBinding.bound_at.desc())
            .first()
        )
        if binding is None:
            raise ExternalRuntimeTokenError("external_agent_machine_token_invalid")
        if binding.revoked_at is not None:
            raise ExternalRuntimeBindingRevokedError("external_agent_binding_revoked")
        return binding

    def summarize_state(self, *, agent: Agent) -> ExternalRuntimeState | None:
        if not self.is_external_runtime_type(getattr(agent, "runtime_preference", None)):
            return None
        profile = self.get_profile(agent_id=agent.agent_id)
        binding = self.get_active_binding(agent_id=agent.agent_id)
        if binding is None:
            desired_version = profile.desired_version if profile else CURRENT_EXTERNAL_RUNTIME_VERSION
            return ExternalRuntimeState(
                status="uninstalled",
                bound=False,
                available_for_conversation=False,
                available_for_execution=False,
                host_name=None,
                host_os=None,
                host_arch=None,
                current_version=None,
                desired_version=desired_version,
                runtime_compatible=False,
                compatibility_message=(
                    "Install Runtime Host to enable native remote execution."
                ),
                last_seen_at=None,
                bound_at=None,
                last_error_message=None,
                update_available=False,
                local_status_url=None,
                local_status_port=None,
                last_dispatch_action=None,
                last_dispatch_status=None,
                last_dispatch_error_message=None,
            )
        desired_version = profile.desired_version if profile else CURRENT_EXTERNAL_RUNTIME_VERSION
        now = self.utc_now()
        effective_status = str(binding.status or "offline").strip().lower() or "offline"
        if effective_status != "error":
            if binding.last_seen_at is None:
                effective_status = "offline"
            elif (now - binding.last_seen_at).total_seconds() > EXTERNAL_RUNTIME_OFFLINE_SECONDS:
                effective_status = "offline"
            else:
                effective_status = "online"
        runtime_compatible = self.is_runtime_compatible(current_version=binding.current_version)
        compatibility_message = self.build_compatibility_message(current_version=binding.current_version)
        if effective_status == "online" and not runtime_compatible:
            effective_status = "upgrade_required"
        last_error_message = binding.last_error_message
        if effective_status == "upgrade_required":
            last_error_message = last_error_message or compatibility_message
        update_available = (
            bool(binding.current_version and desired_version)
            and self._is_version_less(binding.current_version, desired_version)
        )
        local_status_url = None
        local_status_port = None
        binding_metadata = dict(binding.binding_metadata or {})
        raw_local_status_url = binding_metadata.get("local_status_url")
        if raw_local_status_url is not None:
            local_status_url = str(raw_local_status_url).strip() or None
        raw_local_status_port = binding_metadata.get("local_status_port")
        if raw_local_status_port is not None:
            try:
                local_status_port = int(raw_local_status_port)
            except (TypeError, ValueError):
                local_status_port = None
        last_dispatch_action = str(binding_metadata.get("last_dispatch_action") or "").strip() or None
        last_dispatch_status = str(binding_metadata.get("last_dispatch_status") or "").strip() or None
        last_dispatch_error_message = (
            str(binding_metadata.get("last_dispatch_error_message") or "").strip() or None
        )
        return ExternalRuntimeState(
            status=effective_status,
            bound=True,
            available_for_conversation=effective_status == "online" and runtime_compatible,
            available_for_execution=effective_status == "online" and runtime_compatible,
            host_name=binding.host_name,
            host_os=binding.host_os,
            host_arch=binding.host_arch,
            current_version=binding.current_version,
            desired_version=desired_version,
            runtime_compatible=runtime_compatible,
            compatibility_message=compatibility_message,
            last_seen_at=binding.last_seen_at,
            bound_at=binding.bound_at,
            last_error_message=last_error_message,
            update_available=update_available,
            local_status_url=local_status_url,
            local_status_port=local_status_port,
            last_dispatch_action=last_dispatch_action,
            last_dispatch_status=last_dispatch_status,
            last_dispatch_error_message=last_dispatch_error_message,
        )

    def assert_agent_online(self, *, agent: Agent, error_detail: str = "external_agent_not_online") -> ExternalRuntimeState | None:
        state = self.summarize_state(agent=agent)
        if state is None:
            return None
        if not state.available_for_execution:
            if not state.runtime_compatible:
                raise ExternalRuntimeUnavailableError("external_agent_upgrade_required")
            raise ExternalRuntimeUnavailableError(error_detail)
        return state

    def invalidate_install_tokens(self, *, agent_id: UUID) -> None:
        rows = (
            self.session.query(ExternalAgentInstallToken)
            .filter(ExternalAgentInstallToken.agent_id == agent_id)
            .filter(ExternalAgentInstallToken.status == "active")
            .all()
        )
        for row in rows:
            row.status = "revoked"

    def create_install_token(self, *, agent_id: UUID, created_by_user_id: UUID) -> tuple[ExternalAgentInstallToken, str]:
        if self.get_active_binding(agent_id=agent_id) is not None:
            raise ExternalRuntimeConflictError("external_agent_already_bound")
        self.invalidate_install_tokens(agent_id=agent_id)
        raw_token = f"lxei_{secrets.token_urlsafe(24)}"
        row = ExternalAgentInstallToken(
            agent_id=agent_id,
            token_hash=sha256_text(raw_token),
            token_prefix=raw_token[:16],
            status="active",
            expires_at=self.utc_now() + timedelta(minutes=EXTERNAL_INSTALL_CODE_TTL_MINUTES),
            created_by_user_id=created_by_user_id,
        )
        self.session.add(row)
        return flush_and_refresh(self.session, row), raw_token

    def consume_install_token(self, *, agent_id: UUID, raw_token: str) -> ExternalAgentInstallToken:
        row = (
            self.session.query(ExternalAgentInstallToken)
            .filter(ExternalAgentInstallToken.agent_id == agent_id)
            .filter(ExternalAgentInstallToken.token_hash == sha256_text(raw_token))
            .order_by(ExternalAgentInstallToken.created_at.desc())
            .first()
        )
        if row is None:
            raise ExternalRuntimeInstallCodeError("external_agent_install_code_invalid")
        if row.status != "active":
            raise ExternalRuntimeInstallCodeError("external_agent_install_code_invalid")
        if row.expires_at <= self.utc_now():
            row.status = "expired"
            flush_and_refresh(self.session, row)
            raise ExternalRuntimeInstallCodeError("external_agent_install_code_expired")
        row.status = "used"
        row.used_at = self.utc_now()
        return flush_and_refresh(self.session, row)

    def build_install_command(self, *, agent_id: UUID, target_os: str, code: str, base_url: str) -> str:
        target_os = self.validate_target_os(target_os)
        if target_os == "windows":
            return (
                "powershell -NoProfile -ExecutionPolicy Bypass -Command "
                f"\"iwr '{base_url}/api/v1/agents/{agent_id}/external-runtime/install.ps1?target=windows&code={code}' "
                "-UseBasicParsing | iex\""
            )
        return (
            f"curl -fsSL '{base_url}/api/v1/agents/{agent_id}/external-runtime/install.sh?target={target_os}&code={code}' | bash"
        )

    def build_update_command(self, *, agent_id: UUID, target_os: str, base_url: str) -> str:
        target_os = self.validate_target_os(target_os)
        if target_os == "windows":
            return (
                "powershell -NoProfile -ExecutionPolicy Bypass -Command "
                f"\"iwr '{base_url}/api/v1/agents/{agent_id}/external-runtime/update.ps1?target=windows' -UseBasicParsing | iex\""
            )
        return f"curl -fsSL '{base_url}/api/v1/agents/{agent_id}/external-runtime/update.sh?target={target_os}' | bash"

    def build_uninstall_command(self, *, agent_id: UUID, target_os: str, base_url: str) -> str:
        target_os = self.validate_target_os(target_os)
        if target_os == "windows":
            return (
                "powershell -NoProfile -ExecutionPolicy Bypass -Command "
                f"\"iwr '{base_url}/api/v1/agents/{agent_id}/external-runtime/uninstall.ps1?target=windows' -UseBasicParsing | iex\""
            )
        return f"curl -fsSL '{base_url}/api/v1/agents/{agent_id}/external-runtime/uninstall.sh?target={target_os}' | bash"

    def bootstrap_binding(
        self,
        *,
        agent_id: UUID,
        install_code: str,
        host_name: str,
        host_os: str,
        host_arch: str,
        host_fingerprint: str,
        current_version: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
    ) -> tuple[ExternalAgentBinding, str, ExternalAgentProfile]:
        if self.get_active_binding(agent_id=agent_id) is not None:
            raise ExternalRuntimeConflictError("external_agent_already_bound")
        self.consume_install_token(agent_id=agent_id, raw_token=install_code)
        raw_machine_token = f"lxem_{secrets.token_urlsafe(32)}"
        binding = self.get_latest_binding(agent_id=agent_id)
        if binding is None:
            binding = ExternalAgentBinding(agent_id=agent_id)
            self.session.add(binding)
        binding.host_name = str(host_name or "").strip() or None
        binding.host_os = str(host_os or "").strip().lower() or None
        binding.host_arch = str(host_arch or "").strip() or None
        binding.host_fingerprint = str(host_fingerprint or "").strip() or None
        binding.machine_token_hash = sha256_text(raw_machine_token)
        binding.machine_token_prefix = raw_machine_token[:16]
        binding.status = "offline"
        binding.current_version = current_version or CURRENT_EXTERNAL_RUNTIME_VERSION
        binding.last_seen_at = None
        binding.bound_at = self.utc_now()
        binding.revoked_at = None
        binding.last_error_message = None
        binding.binding_metadata = metadata or {}
        binding = flush_and_refresh(self.session, binding)
        profile = self.get_or_create_profile(agent_id=agent_id)
        return binding, raw_machine_token, profile

    def revoke_binding(
        self,
        *,
        binding: ExternalAgentBinding,
        reason: str = "Binding revoked",
    ) -> ExternalAgentBinding:
        binding.status = "revoked"
        binding.revoked_at = self.utc_now()
        binding.last_error_message = reason
        return flush_and_refresh(self.session, binding)

    def unbind_agent(self, *, agent_id: UUID) -> None:
        binding = self.get_active_binding(agent_id=agent_id)
        if binding is None:
            return
        self.revoke_binding(binding=binding)

    def heartbeat(
        self,
        *,
        binding: ExternalAgentBinding,
        host_fingerprint: str,
        host_name: Optional[str],
        host_os: Optional[str],
        host_arch: Optional[str],
        current_version: Optional[str],
        status_value: Optional[str],
        last_error_message: Optional[str],
        metadata: Optional[dict[str, Any]] = None,
    ) -> ExternalAgentBinding:
        normalized_fingerprint = str(host_fingerprint or "").strip()
        if binding.host_fingerprint and normalized_fingerprint and binding.host_fingerprint != normalized_fingerprint:
            binding.status = "error"
            binding.last_error_message = "Host fingerprint mismatch"
            flush_and_refresh(self.session, binding)
            raise ExternalRuntimeBindingRevokedError("external_agent_binding_revoked")
        if normalized_fingerprint and not binding.host_fingerprint:
            binding.host_fingerprint = normalized_fingerprint
        binding.host_name = str(host_name or binding.host_name or "").strip() or binding.host_name
        binding.host_os = str(host_os or binding.host_os or "").strip().lower() or binding.host_os
        binding.host_arch = str(host_arch or binding.host_arch or "").strip() or binding.host_arch
        binding.current_version = current_version or binding.current_version
        binding.last_seen_at = self.utc_now()
        normalized_status = str(status_value or "online").strip().lower()
        binding.status = "error" if normalized_status == "error" else "online"
        binding.last_error_message = last_error_message if binding.status == "error" else None
        binding.binding_metadata = {**(binding.binding_metadata or {}), **(metadata or {})}
        return flush_and_refresh(self.session, binding)

    def create_dispatch(
        self,
        *,
        agent_id: UUID,
        source_type: str,
        source_id: str,
        runtime_type: str,
        request_payload: dict[str, Any],
        project_id: Optional[UUID] = None,
        run_id: Optional[UUID] = None,
        run_step_id: Optional[UUID] = None,
    ) -> ExternalAgentDispatch:
        binding = self.get_active_binding(agent_id=agent_id)
        if binding is None:
            raise ExternalRuntimeUnavailableError("external_agent_not_online")
        state = self.summarize_state(agent=self.get_agent(agent_id))
        if state is None or not state.available_for_execution:
            if state is not None and not state.runtime_compatible:
                raise ExternalRuntimeUnavailableError("external_agent_upgrade_required")
            raise ExternalRuntimeUnavailableError("external_agent_not_online")
        dispatch = ExternalAgentDispatch(
            agent_id=agent_id,
            binding_id=binding.binding_id,
            project_id=project_id,
            run_id=run_id,
            run_step_id=run_step_id,
            source_type=source_type,
            source_id=source_id,
            runtime_type=runtime_type,
            request_payload=request_payload or {},
            status="pending",
            expires_at=self.utc_now() + timedelta(seconds=EXTERNAL_DISPATCH_ACK_TIMEOUT_SECONDS),
        )
        self.session.add(dispatch)
        return flush_and_refresh(self.session, dispatch)

    def create_maintenance_dispatch(
        self,
        *,
        agent_id: UUID,
        action: str,
        request_payload: Optional[dict[str, Any]] = None,
    ) -> ExternalAgentDispatch:
        binding = self.get_active_binding(agent_id=agent_id)
        if binding is None:
            raise ExternalRuntimeUnavailableError("external_agent_not_online")
        agent = self.get_agent(agent_id)
        state = self.summarize_state(agent=agent)
        if state is None or state.status not in {"online", "upgrade_required"}:
            if state is not None and not state.runtime_compatible:
                if state.status != "upgrade_required":
                    raise ExternalRuntimeUnavailableError("external_agent_upgrade_required")
            raise ExternalRuntimeUnavailableError("external_agent_not_online")
        dispatch = ExternalAgentDispatch(
            agent_id=agent_id,
            binding_id=binding.binding_id,
            source_type="maintenance",
            source_id=action,
            runtime_type=str(getattr(agent, "runtime_preference", None) or "external_worktree"),
            request_payload={
                "control_action": action,
                **(request_payload or {}),
            },
            status="pending",
            expires_at=self.utc_now() + timedelta(seconds=EXTERNAL_DISPATCH_ACK_TIMEOUT_SECONDS),
        )
        self.session.add(dispatch)
        return flush_and_refresh(self.session, dispatch)

    def get_next_dispatch(self, *, binding: ExternalAgentBinding) -> ExternalAgentDispatch:
        dispatch = (
            self.session.query(ExternalAgentDispatch)
            .filter(ExternalAgentDispatch.binding_id == binding.binding_id)
            .filter(ExternalAgentDispatch.status == "pending")
            .order_by(ExternalAgentDispatch.created_at.asc())
            .first()
        )
        if dispatch is None:
            raise ExternalRuntimeNoDispatchError("external_agent_no_dispatch_available")
        return dispatch

    def get_dispatch_for_binding(self, *, binding: ExternalAgentBinding, dispatch_id: UUID) -> ExternalAgentDispatch:
        dispatch = (
            self.session.query(ExternalAgentDispatch)
            .filter(ExternalAgentDispatch.dispatch_id == dispatch_id)
            .filter(ExternalAgentDispatch.binding_id == binding.binding_id)
            .first()
        )
        if dispatch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dispatch not found")
        return dispatch

    def append_dispatch_event(
        self,
        *,
        dispatch: ExternalAgentDispatch,
        event_type: str,
        payload: Optional[dict[str, Any]] = None,
    ) -> ExternalAgentDispatchEvent:
        next_sequence = (
            self.session.query(ExternalAgentDispatchEvent)
            .filter(ExternalAgentDispatchEvent.dispatch_id == dispatch.dispatch_id)
            .count()
            + 1
        )
        event = ExternalAgentDispatchEvent(
            dispatch_id=dispatch.dispatch_id,
            sequence_number=next_sequence,
            event_type=str(event_type or "info").strip() or "info",
            payload=payload or {},
        )
        self.session.add(event)
        return flush_and_refresh(self.session, event)

    def list_dispatch_events(
        self,
        *,
        dispatch_id: UUID,
        after_sequence: int = 0,
    ) -> list[ExternalAgentDispatchEvent]:
        return (
            self.session.query(ExternalAgentDispatchEvent)
            .filter(ExternalAgentDispatchEvent.dispatch_id == dispatch_id)
            .filter(ExternalAgentDispatchEvent.sequence_number > max(int(after_sequence or 0), 0))
            .order_by(ExternalAgentDispatchEvent.sequence_number.asc())
            .all()
        )

    def _sync_dispatch_targets(self, *, dispatch: ExternalAgentDispatch) -> tuple[Optional[ProjectRunStep], Optional[ProjectTask], Optional[ProjectRun]]:
        step = None
        task = None
        run = None
        if dispatch.run_step_id:
            step = self.session.query(ProjectRunStep).filter(ProjectRunStep.run_step_id == dispatch.run_step_id).first()
        if step and step.project_task_id:
            task = self.session.query(ProjectTask).filter(ProjectTask.project_task_id == step.project_task_id).first()
        if dispatch.run_id:
            run = self.session.query(ProjectRun).filter(ProjectRun.run_id == dispatch.run_id).first()
        return step, task, run

    def ack_dispatch(self, *, dispatch: ExternalAgentDispatch, result_payload: Optional[dict[str, Any]] = None) -> ExternalAgentDispatch:
        dispatch.status = "acked"
        dispatch.acked_at = self.utc_now()
        dispatch.result_payload = {**(dispatch.result_payload or {}), **(result_payload or {})}
        step, task, run = self._sync_dispatch_targets(dispatch=dispatch)
        if step is not None:
            step.status = "assigned"
            step.output_payload = {**(step.output_payload or {}), **(result_payload or {})}
            flush_and_refresh(self.session, step)
            if run is not None:
                create_or_update_execution_node_from_step(self.session, run=run, step=step)
        if task is not None:
            task.status = "assigned"
            task.error_message = None
            flush_and_refresh(self.session, task)
        if run is not None and str(run.status or "") not in {"running", "completed", "failed", "blocked"}:
            run.status = "scheduled"
            run.error_message = None
            run.completed_at = None
            flush_and_refresh(self.session, run)
        return flush_and_refresh(self.session, dispatch)

    def progress_dispatch(self, *, dispatch: ExternalAgentDispatch, result_payload: Optional[dict[str, Any]] = None, error_message: Optional[str] = None, status_value: str = "running") -> ExternalAgentDispatch:
        normalized_status = str(status_value or "running").strip().lower() or "running"
        dispatch.status = normalized_status
        if dispatch.started_at is None:
            dispatch.started_at = self.utc_now()
        dispatch.result_payload = {**(dispatch.result_payload or {}), **(result_payload or {})}
        dispatch.error_message = error_message
        step, task, run = self._sync_dispatch_targets(dispatch=dispatch)
        if step is not None:
            step.status = normalized_status
            step.output_payload = {**(step.output_payload or {}), **(result_payload or {})}
            step.error_message = error_message
            if step.started_at is None:
                step.started_at = self.utc_now()
            flush_and_refresh(self.session, step)
            if run is not None:
                create_or_update_execution_node_from_step(self.session, run=run, step=step)
        if task is not None:
            task.status = normalized_status
            task.error_message = error_message
            flush_and_refresh(self.session, task)
        if run is not None and normalized_status == "running":
            run.status = "running"
            run.error_message = None
            run.completed_at = None
            flush_and_refresh(self.session, run)
        return flush_and_refresh(self.session, dispatch)

    def complete_dispatch(self, *, dispatch: ExternalAgentDispatch, result_payload: Optional[dict[str, Any]] = None) -> ExternalAgentDispatch:
        now = self.utc_now()
        dispatch.status = "completed"
        dispatch.completed_at = now
        if dispatch.started_at is None:
            dispatch.started_at = now
        dispatch.result_payload = {**(dispatch.result_payload or {}), **(result_payload or {})}
        step, task, run = self._sync_dispatch_targets(dispatch=dispatch)
        if step is not None:
            step.status = "completed"
            step.completed_at = now
            if step.started_at is None:
                step.started_at = dispatch.started_at
            step.output_payload = {**(step.output_payload or {}), **(result_payload or {})}
            flush_and_refresh(self.session, step)
            if run is not None:
                create_or_update_execution_node_from_step(self.session, run=run, step=step)
        if task is not None:
            task.output_payload = {**(task.output_payload or {}), **(result_payload or {})}
            flush_and_refresh(self.session, task)
        if run is not None:
            run.error_message = None
            flush_and_refresh(self.session, run)
            reconcile_run_state(self.session, run=run)
        return flush_and_refresh(self.session, dispatch)

    def fail_dispatch(self, *, dispatch: ExternalAgentDispatch, result_payload: Optional[dict[str, Any]] = None, error_message: Optional[str] = None) -> ExternalAgentDispatch:
        now = self.utc_now()
        dispatch.status = "failed"
        dispatch.completed_at = now
        dispatch.error_message = error_message or dispatch.error_message or "External runtime reported failure"
        dispatch.result_payload = {**(dispatch.result_payload or {}), **(result_payload or {})}
        step, task, run = self._sync_dispatch_targets(dispatch=dispatch)
        if step is not None:
            step.status = "failed"
            step.completed_at = now
            step.error_message = dispatch.error_message
            step.output_payload = {**(step.output_payload or {}), **(result_payload or {})}
            flush_and_refresh(self.session, step)
            if run is not None:
                create_or_update_execution_node_from_step(self.session, run=run, step=step)
        if task is not None:
            task.status = "failed"
            task.error_message = dispatch.error_message
            task.output_payload = {**(task.output_payload or {}), **(result_payload or {})}
            flush_and_refresh(self.session, task)
        if run is not None:
            run.status = "failed"
            run.completed_at = now
            run.error_message = dispatch.error_message
            flush_and_refresh(self.session, run)
            reconcile_run_state(self.session, run=run)
        return flush_and_refresh(self.session, dispatch)


__all__ = [
    "CURRENT_EXTERNAL_RUNTIME_VERSION",
    "EXTERNAL_RUNTIME_OFFLINE_SECONDS",
    "EXTERNAL_RUNTIME_TYPES",
    "EXTERNAL_DISPATCH_ACK_TIMEOUT_SECONDS",
    "EXTERNAL_INSTALL_CODE_TTL_MINUTES",
    "SUPPORTED_EXTERNAL_TARGETS",
    "ExternalRuntimeConflictError",
    "ExternalRuntimeInstallCodeError",
    "ExternalRuntimeNoDispatchError",
    "ExternalRuntimePlatformError",
    "ExternalRuntimeService",
    "ExternalRuntimeState",
    "ExternalRuntimeTokenError",
    "ExternalRuntimeUnavailableError",
    "ExternalRuntimeBindingRevokedError",
]
