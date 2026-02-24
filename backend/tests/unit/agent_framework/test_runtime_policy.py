"""Unit tests for runtime profile and policy resolution."""

from agent_framework.runtime_policy import (
    ExecutionProfile,
    LoopMode,
    RuntimePolicyRegistry,
    parse_execution_profile,
)


def test_parse_execution_profile_fallback_to_legacy():
    assert parse_execution_profile(None) == ExecutionProfile.LEGACY
    assert parse_execution_profile("unknown_profile") == ExecutionProfile.LEGACY


def test_registry_resolves_debug_chat_to_recovery_mode():
    registry = RuntimePolicyRegistry()
    policy = registry.resolve(ExecutionProfile.DEBUG_CHAT)

    assert policy.profile == ExecutionProfile.DEBUG_CHAT
    assert policy.loop_mode == LoopMode.RECOVERY_MULTI_TURN
    assert policy.stream_output is True


def test_registry_applies_safe_override_fields():
    registry = RuntimePolicyRegistry()
    policy = registry.resolve(
        ExecutionProfile.MISSION_TASK,
        overrides={"loop_mode": "single_turn", "max_rounds": 1, "unsupported": "ignored"},
    )

    assert policy.profile == ExecutionProfile.MISSION_TASK
    assert policy.loop_mode == LoopMode.SINGLE_TURN
    assert policy.max_rounds == 1
