"""Execution profile and runtime policy contracts for agent execution."""

from __future__ import annotations

import os
from functools import lru_cache
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from shared.config import get_config


DEFAULT_AGENT_TIMEOUT_SECONDS = 1800
DEFAULT_AGENT_COMPACTION_GRACE_SECONDS = 60
RETRY_ITERATION_CAP_BASE = 24
RETRY_ITERATION_CAP_PER_PROFILE = 8
RETRY_ITERATION_CAP_MIN = 32
RETRY_ITERATION_CAP_MAX = 160


class LoopMode(str, Enum):
    """Execution loop strategy for a run."""

    SINGLE_TURN = "single_turn"
    AUTO_MULTI_TURN = "auto_multi_turn"
    RECOVERY_MULTI_TURN = "recovery_multi_turn"


class FileDeliveryGuardMode(str, Enum):
    """File deliverable guard strictness for autonomous loops."""

    OFF = "off"
    SOFT = "soft"
    STRICT = "strict"


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
    retry_iteration_cap: int = 0
    enable_error_recovery: bool = True
    max_retries: int = 3
    timeout_seconds: int = DEFAULT_AGENT_TIMEOUT_SECONDS
    include_context: bool = True
    include_memory: bool = True
    stream_output: bool = False
    file_delivery_guard_mode: FileDeliveryGuardMode = FileDeliveryGuardMode.SOFT


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


@lru_cache(maxsize=1)
def load_agent_runtime_defaults() -> Dict[str, int]:
    """Load agent runtime defaults from config with safe fallbacks."""

    timeout_seconds = DEFAULT_AGENT_TIMEOUT_SECONDS
    compaction_grace_seconds = DEFAULT_AGENT_COMPACTION_GRACE_SECONDS

    try:
        config = get_config()
        timeout_seconds = int(
            config.get("agents.defaults.timeout_seconds", timeout_seconds) or timeout_seconds
        )
        compaction_grace_seconds = int(
            config.get(
                "agents.defaults.compaction_grace_seconds",
                compaction_grace_seconds,
            )
            or compaction_grace_seconds
        )
    except Exception:
        # Runtime policy must remain usable in isolated tests and fallback environments.
        pass

    return {
        "timeout_seconds": max(30, timeout_seconds),
        "compaction_grace_seconds": max(5, min(compaction_grace_seconds, 300)),
    }


def get_default_agent_timeout_seconds() -> int:
    """Return the default total runtime timeout for agent executions."""

    return int(load_agent_runtime_defaults()["timeout_seconds"])


def get_default_agent_compaction_grace_seconds() -> int:
    """Return the extra grace window used when timeout hits during compaction."""

    return int(load_agent_runtime_defaults()["compaction_grace_seconds"])


def clamp_retry_iteration_cap(value: int) -> int:
    """Clamp retry iteration caps into the supported execution range."""

    return max(RETRY_ITERATION_CAP_MIN, min(RETRY_ITERATION_CAP_MAX, int(value)))


def compute_retry_iteration_cap(profile_count: int) -> int:
    """Compute the outer retry-iteration cap for a run."""

    normalized_profile_count = max(1, int(profile_count or 1))
    return clamp_retry_iteration_cap(
        RETRY_ITERATION_CAP_BASE + RETRY_ITERATION_CAP_PER_PROFILE * normalized_profile_count
    )


class RuntimePolicyRegistry:
    """Profile-to-policy resolver with optional safe overrides."""

    def __init__(self) -> None:
        default_timeout_seconds = get_default_agent_timeout_seconds()
        self._defaults: Dict[ExecutionProfile, RuntimePolicy] = {
            ExecutionProfile.DEBUG_CHAT: RuntimePolicy(
                profile=ExecutionProfile.DEBUG_CHAT,
                loop_mode=LoopMode.RECOVERY_MULTI_TURN,
                max_rounds=20,
                retry_iteration_cap=0,
                enable_error_recovery=True,
                max_retries=3,
                timeout_seconds=default_timeout_seconds,
                include_context=True,
                include_memory=True,
                stream_output=True,
                file_delivery_guard_mode=FileDeliveryGuardMode.SOFT,
            ),
            ExecutionProfile.MISSION_TASK: RuntimePolicy(
                profile=ExecutionProfile.MISSION_TASK,
                loop_mode=LoopMode.RECOVERY_MULTI_TURN,
                max_rounds=20,
                retry_iteration_cap=0,
                enable_error_recovery=True,
                max_retries=3,
                timeout_seconds=default_timeout_seconds,
                include_context=True,
                include_memory=True,
                stream_output=False,
                file_delivery_guard_mode=FileDeliveryGuardMode.STRICT,
            ),
            ExecutionProfile.MISSION_CONTROL: RuntimePolicy(
                profile=ExecutionProfile.MISSION_CONTROL,
                loop_mode=LoopMode.SINGLE_TURN,
                max_rounds=1,
                retry_iteration_cap=1,
                enable_error_recovery=False,
                max_retries=1,
                timeout_seconds=default_timeout_seconds,
                include_context=True,
                include_memory=True,
                stream_output=False,
                file_delivery_guard_mode=FileDeliveryGuardMode.SOFT,
            ),
            ExecutionProfile.LEGACY: RuntimePolicy(
                profile=ExecutionProfile.LEGACY,
                loop_mode=LoopMode.SINGLE_TURN,
                max_rounds=1,
                retry_iteration_cap=1,
                enable_error_recovery=True,
                max_retries=3,
                timeout_seconds=default_timeout_seconds,
                include_context=True,
                include_memory=True,
                stream_output=False,
                file_delivery_guard_mode=FileDeliveryGuardMode.SOFT,
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
            "retry_iteration_cap",
            "enable_error_recovery",
            "max_retries",
            "timeout_seconds",
            "stream_output",
            "file_delivery_guard_mode",
        ):
            if key in overrides:
                safe[key] = overrides[key]

        if "loop_mode" in safe:
            safe["loop_mode"] = LoopMode(str(safe["loop_mode"]))
        if "file_delivery_guard_mode" in safe:
            safe["file_delivery_guard_mode"] = FileDeliveryGuardMode(
                str(safe["file_delivery_guard_mode"]).strip().lower()
            )

        return RuntimePolicy(
            profile=base.profile,
            loop_mode=safe.get("loop_mode", base.loop_mode),
            max_rounds=int(safe.get("max_rounds", base.max_rounds)),
            retry_iteration_cap=int(
                safe.get("retry_iteration_cap", base.retry_iteration_cap)
            ),
            enable_error_recovery=bool(
                safe.get("enable_error_recovery", base.enable_error_recovery)
            ),
            max_retries=int(safe.get("max_retries", base.max_retries)),
            timeout_seconds=int(safe.get("timeout_seconds", base.timeout_seconds)),
            include_context=base.include_context,
            include_memory=base.include_memory,
            stream_output=bool(safe.get("stream_output", base.stream_output)),
            file_delivery_guard_mode=safe.get(
                "file_delivery_guard_mode", base.file_delivery_guard_mode
            ),
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
