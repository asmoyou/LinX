"""Execution profile and runtime policy contracts for agent execution."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class LoopMode(str, Enum):
    """Execution loop strategy for a run."""

    SINGLE_TURN = "single_turn"
    AUTO_MULTI_TURN = "auto_multi_turn"
    RECOVERY_MULTI_TURN = "recovery_multi_turn"


class ExecutionProfile(str, Enum):
    """High-level runtime profile for agent execution."""

    DEBUG_CHAT = "debug_chat"
    MISSION_TASK = "mission_task"
    MISSION_CONTROL = "mission_control"
    LEGACY = "legacy"


@dataclass(frozen=True)
class RuntimePolicy:
    """Resolved runtime behavior for one execution."""

    profile: ExecutionProfile
    loop_mode: LoopMode
    max_rounds: int = 20
    enable_error_recovery: bool = True
    max_retries: int = 3
    timeout_seconds: int = 120
    include_context: bool = True
    include_memory: bool = True
    stream_output: bool = False


@dataclass(frozen=True)
class RuntimeExecutionRequest:
    """Canonical runtime request model shared by adapters."""

    task_description: str
    profile: ExecutionProfile
    context: Optional[Dict[str, Any]] = None
    conversation_history: Optional[List[Dict[str, Any]]] = None
    execution_context: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def _get_env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


class RuntimePolicyRegistry:
    """Profile-to-policy resolver with optional safe overrides."""

    def __init__(self) -> None:
        self._defaults: Dict[ExecutionProfile, RuntimePolicy] = {
            ExecutionProfile.DEBUG_CHAT: RuntimePolicy(
                profile=ExecutionProfile.DEBUG_CHAT,
                loop_mode=LoopMode.RECOVERY_MULTI_TURN,
                max_rounds=20,
                enable_error_recovery=True,
                max_retries=3,
                timeout_seconds=180,
                include_context=True,
                include_memory=True,
                stream_output=True,
            ),
            ExecutionProfile.MISSION_TASK: RuntimePolicy(
                profile=ExecutionProfile.MISSION_TASK,
                loop_mode=LoopMode.RECOVERY_MULTI_TURN,
                max_rounds=20,
                enable_error_recovery=True,
                max_retries=3,
                timeout_seconds=180,
                include_context=True,
                include_memory=True,
                stream_output=False,
            ),
            ExecutionProfile.MISSION_CONTROL: RuntimePolicy(
                profile=ExecutionProfile.MISSION_CONTROL,
                loop_mode=LoopMode.SINGLE_TURN,
                max_rounds=1,
                enable_error_recovery=False,
                max_retries=1,
                timeout_seconds=120,
                include_context=True,
                include_memory=True,
                stream_output=False,
            ),
            ExecutionProfile.LEGACY: RuntimePolicy(
                profile=ExecutionProfile.LEGACY,
                loop_mode=LoopMode.SINGLE_TURN,
                max_rounds=1,
                enable_error_recovery=True,
                max_retries=3,
                timeout_seconds=120,
                include_context=True,
                include_memory=True,
                stream_output=False,
            ),
        }

    def resolve(
        self,
        profile: ExecutionProfile | str | None,
        *,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> RuntimePolicy:
        """Resolve a profile into a runtime policy."""
        resolved_profile = parse_execution_profile(profile)
        base = self._defaults.get(resolved_profile, self._defaults[ExecutionProfile.LEGACY])

        if not overrides:
            return base

        safe = {}
        for key in (
            "loop_mode",
            "max_rounds",
            "enable_error_recovery",
            "max_retries",
            "timeout_seconds",
            "stream_output",
        ):
            if key in overrides:
                safe[key] = overrides[key]

        if "loop_mode" in safe:
            safe["loop_mode"] = LoopMode(str(safe["loop_mode"]))

        return RuntimePolicy(
            profile=base.profile,
            loop_mode=safe.get("loop_mode", base.loop_mode),
            max_rounds=int(safe.get("max_rounds", base.max_rounds)),
            enable_error_recovery=bool(
                safe.get("enable_error_recovery", base.enable_error_recovery)
            ),
            max_retries=int(safe.get("max_retries", base.max_retries)),
            timeout_seconds=int(safe.get("timeout_seconds", base.timeout_seconds)),
            include_context=base.include_context,
            include_memory=base.include_memory,
            stream_output=bool(safe.get("stream_output", base.stream_output)),
        )


_runtime_policy_registry: Optional[RuntimePolicyRegistry] = None


def get_runtime_policy_registry() -> RuntimePolicyRegistry:
    """Get singleton runtime policy registry."""
    global _runtime_policy_registry
    if _runtime_policy_registry is None:
        _runtime_policy_registry = RuntimePolicyRegistry()
    return _runtime_policy_registry


def parse_execution_profile(profile: ExecutionProfile | str | None) -> ExecutionProfile:
    """Parse profile input into enum with safe fallback."""
    if isinstance(profile, ExecutionProfile):
        return profile
    if isinstance(profile, str) and profile.strip():
        value = profile.strip().lower()
        for item in ExecutionProfile:
            if item.value == value:
                return item
    return ExecutionProfile.LEGACY


def is_agent_test_chat_unified_runtime_enabled() -> bool:
    """Feature flag: enable unified runtime in agent test chat endpoint."""
    return _get_env_bool("AGENT_TEST_CHAT_UNIFIED_RUNTIME_ENABLED", True)


def is_mission_task_unified_runtime_enabled() -> bool:
    """Feature flag: enable unified runtime in mission task execution."""
    return _get_env_bool("MISSION_TASK_UNIFIED_RUNTIME_ENABLED", True)
