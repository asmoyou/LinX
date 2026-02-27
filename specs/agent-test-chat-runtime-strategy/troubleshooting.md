# Troubleshooting Guide

## 1. Symptom: Agent “forgets” previous turns in test chat

Checks:

1. Ensure history payload contains valid `role/content` pairs.
2. Confirm `AGENT_TEST_CHAT_UNIFIED_RUNTIME_ENABLED=true`.
3. Inspect runtime logs for:
   - `runtime_profile=debug_chat`
   - `runtime_loop_mode=recovery_multi_turn`

## 2. Symptom: Mission tasks look single-turn only

Checks:

1. Ensure `MISSION_TASK_UNIFIED_RUNTIME_ENABLED=true`.
2. Confirm mission task path passes `execution_profile=mission_task`.
3. Check logs for resolved loop mode and context presence.

## 3. Symptom: Behavior mismatch between test chat and mission

Checks:

1. Compare profile selection (`debug_chat` vs `mission_task`).
2. Verify both paths are running unified runtime (flags enabled).
3. Validate both paths include context/history in invocation payload.

## 4. Symptom: Unexpected fallback behavior

Checks:

1. Confirm no environment overrides disabled unified runtime.
2. Check whether caller omits profile and enters `legacy` fallback.
3. Review adapter invocation path for missing execution profile wiring.
