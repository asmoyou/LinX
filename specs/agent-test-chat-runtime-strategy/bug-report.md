# Agent Runtime Context Bug Report

## 1. Summary

Multi-turn context was not consistently preserved in agent test chat and mission execution paths.

## 2. Root Cause

1. In agent test chat, parsed `conversation_history` was sanitized and prepared but not always passed into the final execution invocation path.
2. Runtime strategy selection depended on `stream_callback` presence in parts of `BaseAgent.execute_task`, so non-streaming mission paths could skip multi-round recovery behavior.
3. Entry-point adapters had diverging invocation semantics, making debug-chat behavior different from mission behavior.

## 3. Impact

1. Test chat appeared to lose previous turns ("no memory") in user-visible flows.
2. Mission task runs were at risk of reduced context continuity and weaker recovery behavior.
3. Debug-to-production behavior parity was reduced.

## 4. Fixes Applied

1. Added runtime contract:
   - `ExecutionProfile`
   - `RuntimePolicy`
   - `RuntimePolicyRegistry`
   - `RuntimeExecutionRequest`
2. Added unified runtime bridge:
   - `UnifiedAgentRuntimeService`
3. Updated `BaseAgent.execute_task`:
   - strategy is policy/profile-driven, not callback-driven
   - recovery path can run without stream callback
4. Updated adapters:
   - `/agents/{id}/test` passes `ExecutionProfile.DEBUG_CHAT`
   - mission orchestration passes `ExecutionProfile.EXECUTION_TASK` / `EXECUTION_CONTROL`
5. Added feature flags:
   - `AGENT_TEST_CHAT_UNIFIED_RUNTIME_ENABLED`
   - `EXECUTION_TASK_UNIFIED_RUNTIME_ENABLED` (legacy env alias still accepted)
6. Added/updated unit and integration tests for context/history/profile propagation.

## 5. Verification

Validated with targeted backend unit + integration tests covering:

1. base agent history + profile behavior,
2. mission orchestrator adapter behavior,
3. agent executor context wiring,
4. memory/knowledge integration and agent router helper regressions.
