# Unified Runtime Rollout Runbook

## 1. Feature Flags

1. `AGENT_TEST_CHAT_UNIFIED_RUNTIME_ENABLED` (default: `true`)
2. `EXECUTION_TASK_UNIFIED_RUNTIME_ENABLED` (default: `true`, legacy alias still accepted)

## 2. Rollout Steps

1. Staging:
   - Enable both flags.
   - Run unit + integration regression suites.
   - Validate multi-turn continuity on test chat and mission tasks.
2. Production canary:
   - Enable test chat first.
   - Observe runtime logs: `runtime_profile`, `runtime_loop_mode`, `has_stream_callback`.
3. Production expansion:
   - Enable mission task flag for broader traffic after stability checks.

## 3. Rollback Steps

1. Disable test chat unified runtime:
   - set `AGENT_TEST_CHAT_UNIFIED_RUNTIME_ENABLED=false`
2. Disable mission unified runtime:
   - set `EXECUTION_TASK_UNIFIED_RUNTIME_ENABLED=false`
3. Verify rollback:
   - confirm adapter paths continue operating with legacy fallback behavior.

## 4. Post-Deploy Checks

1. Agent test chat remembers previous turn context.
2. Mission task retries still receive execution context.
3. No error spike in mission/task completion paths.
