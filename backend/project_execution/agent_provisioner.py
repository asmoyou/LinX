from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence
from uuid import UUID

from access_control.agent_access import list_accessible_agents
from access_control.permissions import CurrentUser
from agent_framework.agent_registry import get_agent_registry
from database.connection import get_db_session
from database.models import Agent
from database.project_execution_models import AgentProvisioningProfile, Project, ProjectAgentBinding
from project_execution.capability_mapper import CapabilityMapper
from project_execution.external_runtime_service import ExternalRuntimeService
from project_execution.load_balancer import LoadBalancer
from shared.logging import get_logger

logger = get_logger(__name__)

INTERNAL_RUNTIME_TYPES = {"project_sandbox"}
EXTERNAL_RUNTIME_TYPES = {"external_same_dir", "external_worktree", "remote_session"}


class ProjectExternalRuntimeUnavailableError(RuntimeError):
    """Raised when a host-action step needs external runtime capacity that is not configured."""

    pass


@dataclass
class AgentSelectionResult:
    agent_id: UUID
    agent_name: str
    score: float
    selection_reason: str
    provisioned_agent: bool = False
    step_kind: str = "implementation"
    required_capabilities: list[str] | None = None
    runtime_type: str = "project_sandbox"


DEFAULT_STEP_SKILLS: dict[str, list[str]] = {
    "research": ["research", "knowledge_retrieval", "planning"],
    "writing": ["writing", "documentation", "planning"],
    "implementation": ["implementation", "code_execution", "planning"],
    "review": ["review", "qa", "planning"],
    "qa": ["qa", "verification", "planning"],
    "ops": ["ops", "shell", "planning"],
    "host_action": ["ops", "shell", "host_execution"],
}

DEFAULT_AGENT_TYPE: dict[str, str] = {
    "research": "project_research_agent",
    "writing": "project_writing_agent",
    "implementation": "project_implementation_agent",
    "review": "project_review_agent",
    "qa": "project_qa_agent",
    "ops": "project_ops_agent",
    "host_action": "project_external_ops_agent",
}

DEFAULT_RUNTIME_TYPE: dict[str, str] = {
    "host_action": "external_worktree",
}


class ProjectAgentProvisioner:
    def __init__(self) -> None:
        self._capability_mapper = CapabilityMapper()
        self._load_balancer = LoadBalancer(max_tasks_per_agent=3)

    @staticmethod
    def _requires_external_runtime(desired_runtime_types: Sequence[str]) -> bool:
        return any(runtime_type in EXTERNAL_RUNTIME_TYPES for runtime_type in desired_runtime_types)

    def select_or_provision_agent(
        self,
        *,
        project_id: UUID,
        step_kind: str,
        required_capabilities: Sequence[str],
        current_user: CurrentUser,
        run_id: UUID,
        required_runtime_types: Optional[Sequence[str]] = None,
        suggested_agent_ids: Optional[Sequence[str]] = None,
    ) -> AgentSelectionResult:
        desired_runtime_types = list(required_runtime_types or self._default_runtime_types_for_step(step_kind))
        selected = self._select_bound_agent(
            project_id=project_id,
            step_kind=step_kind,
            required_capabilities=list(required_capabilities),
            current_user=current_user,
            desired_runtime_types=desired_runtime_types,
            suggested_agent_ids=suggested_agent_ids,
        )
        if selected is not None:
            return selected
        return self._provision_ephemeral_agent(
            project_id=project_id,
            step_kind=step_kind,
            required_capabilities=list(required_capabilities),
            current_user=current_user,
            run_id=run_id,
            desired_runtime_types=desired_runtime_types,
        )

    def _default_runtime_types_for_step(self, step_kind: str) -> list[str]:
        if step_kind == "host_action":
            return ["external_worktree", "external_same_dir", "remote_session"]
        return ["project_sandbox"]

    def _is_runtime_compatible(self, agent: Agent, desired_runtime_types: list[str]) -> bool:
        runtime_preference = str(getattr(agent, "runtime_preference", "") or "project_sandbox").strip()
        if not runtime_preference:
            runtime_preference = "project_sandbox"
        if runtime_preference in desired_runtime_types:
            return True
        if runtime_preference == "project_sandbox" and any(rt in INTERNAL_RUNTIME_TYPES for rt in desired_runtime_types):
            return True
        return False

    def _select_bound_agent(
        self,
        *,
        project_id: UUID,
        step_kind: str,
        required_capabilities: list[str],
        current_user: CurrentUser,
        desired_runtime_types: list[str],
        suggested_agent_ids: Optional[Sequence[str]] = None,
    ) -> Optional[AgentSelectionResult]:
        with get_db_session() as session:
            runtime_service = ExternalRuntimeService(session)
            bindings = (
                session.query(ProjectAgentBinding)
                .filter(ProjectAgentBinding.project_id == project_id)
                .filter(ProjectAgentBinding.status == "active")
                .all()
            )
            if not bindings:
                return None
            binding_map = {row.agent_id: row for row in bindings}
            bound_runtime_candidates = [
                agent
                for agent in list_accessible_agents(
                    session,
                    current_user,
                    access_type="execute",
                    statuses=["idle", "active", "working", "busy"],
                )
                if agent.agent_id in binding_map
                and self._is_runtime_compatible(agent, desired_runtime_types)
            ]
            candidates = [
                agent
                for agent in bound_runtime_candidates
                if (
                    not self._requires_external_runtime(desired_runtime_types)
                    or bool(
                        (
                            runtime_state := runtime_service.summarize_state(agent=agent)
                        )
                        and runtime_state.available_for_execution
                    )
                )
            ]
            if not candidates:
                if self._requires_external_runtime(desired_runtime_types) and bound_runtime_candidates:
                    runtime_states = [
                        runtime_service.summarize_state(agent=agent)
                        for agent in bound_runtime_candidates
                    ]
                    if any(
                        state is not None and not state.runtime_compatible
                        for state in runtime_states
                    ):
                        raise ProjectExternalRuntimeUnavailableError(
                            "External Runtime Host must be upgraded before this host-action step can run."
                        )
                    if any(
                        state is not None and state.status in {"offline", "error", "uninstalled"}
                        for state in runtime_states
                    ):
                        raise ProjectExternalRuntimeUnavailableError(
                            "External Runtime Host is bound for this host-action step but is not currently available."
                        )
                return None
            normalized_suggested_agent_ids = {
                str(agent_id).strip()
                for agent_id in (suggested_agent_ids or [])
                if str(agent_id).strip()
            }
            if normalized_suggested_agent_ids:
                preferred_candidates = [
                    agent
                    for agent in candidates
                    if str(agent.agent_id) in normalized_suggested_agent_ids
                ]
                if preferred_candidates:
                    candidates = preferred_candidates
            scored: list[tuple[float, Agent]] = []
            for agent in candidates:
                capabilities = list(agent.capabilities or []) if isinstance(agent.capabilities, list) else []
                binding = binding_map[agent.agent_id]
                skill_score = self._capability_mapper.calculate_capability_match_score(
                    required=required_capabilities,
                    available=capabilities,
                )
                type_bonus = 1.0 if step_kind in str(agent.agent_type or "") else 0.0
                history_success = 0.5
                runtime_bonus = 1.0 if str(getattr(agent, "runtime_preference", "") or "project_sandbox") in desired_runtime_types else 0.5
                binding_bonus = 1.0 if (not binding.allowed_step_kinds or step_kind in (binding.allowed_step_kinds or [])) else 0.2
                try:
                    load_pick = self._load_balancer.select_agent([agent.agent_id], UUID(str(current_user.user_id)))
                    load_bonus = 1.0 if load_pick == agent.agent_id else 0.4
                except Exception:
                    load_bonus = 0.6
                total_score = (skill_score * 35) + (type_bonus * 20) + (history_success * 15) + (load_bonus * 10) + (runtime_bonus * 10) + (binding_bonus * 10)
                scored.append((total_score, agent))
            scored.sort(key=lambda item: item[0], reverse=True)
            best_score, best_agent = scored[0]
            runtime_type = str(getattr(best_agent, "runtime_preference", "") or desired_runtime_types[0])
            return AgentSelectionResult(
                agent_id=best_agent.agent_id,
                agent_name=best_agent.name,
                score=best_score,
                selection_reason=f"Selected from project binding pool for {step_kind} with score {best_score:.1f}",
                provisioned_agent=False,
                step_kind=step_kind,
                required_capabilities=required_capabilities,
                runtime_type=runtime_type,
            )

    def _provision_ephemeral_agent(
        self,
        *,
        project_id: UUID,
        step_kind: str,
        required_capabilities: list[str],
        current_user: CurrentUser,
        run_id: UUID,
        desired_runtime_types: list[str],
    ) -> AgentSelectionResult:
        with get_db_session() as session:
            project = session.query(Project).filter(Project.project_id == project_id).first()
            profile = (
                session.query(AgentProvisioningProfile)
                .filter(AgentProvisioningProfile.project_id == project_id)
                .filter(AgentProvisioningProfile.step_kind == step_kind)
                .order_by(AgentProvisioningProfile.created_at.desc())
                .first()
            )
        registry = get_agent_registry()
        runtime_type = (
            profile.runtime_type
            if profile and getattr(profile, "runtime_type", None)
            else DEFAULT_RUNTIME_TYPE.get(step_kind, desired_runtime_types[0])
        )
        if runtime_type in EXTERNAL_RUNTIME_TYPES:
            raise ProjectExternalRuntimeUnavailableError(
                "No external runtime is configured for this host-action step. "
                "Bind an external agent in the Project Agent Pool and install a Runtime Host."
            )
        capabilities = list(profile.default_skill_ids or []) if profile and profile.default_skill_ids else list(required_capabilities)
        scope_label = "external" if runtime_type in EXTERNAL_RUNTIME_TYPES else "internal"
        agent_name = f"{(project.name if project else 'Project')} · {step_kind} · temp · {scope_label} · {str(run_id)[:8]}"
        system_prompt = (
            f"You are a temporary {step_kind} agent for the LinX project execution platform. "
            f"Your runtime type is {runtime_type}. "
            "Complete the assigned step and leave concrete outputs and summaries."
        )
        agent_info = registry.register_agent(
            name=agent_name,
            agent_type=(profile.agent_type if profile and profile.agent_type else DEFAULT_AGENT_TYPE.get(step_kind, 'project_temp_agent')),
            owner_user_id=UUID(str(current_user.user_id)),
            capabilities=capabilities,
            llm_provider=(profile.default_provider if profile else None),
            llm_model=(profile.default_model if profile else None),
            system_prompt=system_prompt,
            temperature=(profile.temperature if profile and profile.temperature is not None else 0.2),
            max_tokens=(profile.max_tokens if profile and profile.max_tokens is not None else 4000),
            access_level="private",
            department_id=None,
            is_ephemeral=True,
            lifecycle_scope="current_run",
            runtime_preference=runtime_type,
            project_scope_id=project_id,
        )
        registry.update_agent(agent_id=agent_info.agent_id, status="idle")
        logger.info(
            "Provisioned ephemeral project execution agent",
            extra={
                "project_id": str(project_id),
                "agent_id": str(agent_info.agent_id),
                "step_kind": step_kind,
                "runtime_type": runtime_type,
            },
        )
        return AgentSelectionResult(
            agent_id=agent_info.agent_id,
            agent_name=agent_name,
            score=100.0,
            selection_reason=f"Provisioned temporary {scope_label} {step_kind} agent for this run",
            provisioned_agent=True,
            step_kind=step_kind,
            required_capabilities=required_capabilities,
            runtime_type=runtime_type,
        )


def default_required_capabilities(step_kind: str) -> list[str]:
    return list(DEFAULT_STEP_SKILLS.get(step_kind, DEFAULT_STEP_SKILLS["implementation"]))
