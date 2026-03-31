"""Unit tests for runtime profile and policy resolution."""

from agent_framework.runtime_policy import (
    ExecutionProfile,
    FileDeliveryGuardMode,
    LoopMode,
    RuntimePolicyRegistry,
    compute_retry_iteration_cap,
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
    assert policy.timeout_seconds == 1800
    assert policy.stream_output is True
    assert policy.file_delivery_guard_mode == FileDeliveryGuardMode.SOFT


def test_registry_resolves_mission_task_to_strict_file_guard():
    registry = RuntimePolicyRegistry()
    policy = registry.resolve(ExecutionProfile.MISSION_TASK)

    assert policy.profile == ExecutionProfile.MISSION_TASK
    assert policy.file_delivery_guard_mode == FileDeliveryGuardMode.STRICT


def test_registry_applies_safe_override_fields():
    registry = RuntimePolicyRegistry()
    policy = registry.resolve(
        ExecutionProfile.MISSION_TASK,
        overrides={
            "loop_mode": "single_turn",
            "max_rounds": 1,
            "retry_iteration_cap": 9,
            "file_delivery_guard_mode": "strict",
            "unsupported": "ignored",
        },
    )

    assert policy.profile == ExecutionProfile.MISSION_TASK
    assert policy.loop_mode == LoopMode.SINGLE_TURN
    assert policy.max_rounds == 1
    assert policy.retry_iteration_cap == 9
    assert policy.file_delivery_guard_mode == FileDeliveryGuardMode.STRICT


def test_compute_retry_iteration_cap_clamps_to_supported_range():
    assert compute_retry_iteration_cap(1) == 32
    assert compute_retry_iteration_cap(3) == 48
    assert compute_retry_iteration_cap(99) == 160
