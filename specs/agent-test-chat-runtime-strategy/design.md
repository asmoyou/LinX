# Agent Test Chat Runtime Strategy - Design

## 1. Overview

This design introduces a unified agent execution runtime while preserving current entry-point boundaries:

1. API gateway test chat remains an adapter layer.
2. Mission orchestrator remains an orchestration/state-machine layer.
3. Shared runtime service becomes the single execution semantics owner.

The target is behavioral parity and predictable debugging, not forced structural merge of unrelated modules.

## 2. Design Principles

1. One execution semantics, multiple adapters.
2. Transport is not strategy: streaming and reasoning policy are decoupled.
3. Profile-driven behavior: every run declares explicit runtime profile.
4. Safe migration: dual path, flags, observability, rollback.

## 3. Current Gaps (As-Is)

1. Context/history was previously dropped in test-chat path (already fixed in code).
2. Some loop/recovery behavior is still selected based on `stream_callback` presence.
3. Mission and test-chat paths may diverge in context/tool policy selection under edge cases.
4. Observability does not always expose strategy-selection reasons.

## 4. Target Architecture (To-Be)

### 4.1 Components

1. `ExecutionAdapter` (existing entry points):
   - `AgentTestChatAdapter` (API router).
   - `MissionTaskAdapter` (mission orchestrator).
2. `UnifiedAgentRuntimeService` (new core):
   - input normalization,
   - profile resolution,
   - loop policy execution,
   - model invocation boundary,
   - tool/skill lifecycle integration.
3. `RuntimePolicyRegistry` (new):
   - maps profile -> loop mode, retry budget, timeout, context policy, stream policy.
4. `RuntimeTelemetry` (new/shared):
   - structured trace/log emission.

### 4.2 Responsibility Boundaries

1. Adapter layer:
   - parse request/event payload,
   - choose profile and pass execution context,
   - map runtime output to transport format.
2. Runtime service:
   - everything required to produce answer/tool actions consistently.
3. Orchestrator layer:
   - mission lifecycle, dependency graph, retry/replan at task-state level.

## 5. Runtime Contract

### 5.1 Core Input Model

`RuntimeExecutionRequest`:

1. `agent_id: str`
2. `task: str`
3. `profile: ExecutionProfile`
4. `conversation_history: list[Message] | None`
5. `execution_context: dict[str, Any] | None`
6. `transport: TransportConfig`
7. `metadata: RuntimeMetadata`

`Message`:

1. `role: system | user | assistant | tool`
2. `content: str | list[ContentPart]`
3. `name: str | None`
4. `timestamp: str | None`

### 5.2 Profile Model

`ExecutionProfile` (initial set):

1. `debug_chat`:
   - multi-turn enabled,
   - debug-friendly telemetry,
   - moderate retry budget.
2. `mission_task`:
   - task objective strictness,
   - deterministic retries bound by mission-level policy.
3. `mission_control`:
   - planner/control style execution,
   - usually short loop with strong guardrails.

Profiles can be extended but must be versioned in registry.

### 5.3 Policy Resolution

`RuntimePolicy` fields:

1. `loop_mode: single_turn | auto_multi_turn | recovery_multi_turn`
2. `max_rounds: int`
3. `enable_error_recovery: bool`
4. `max_retries: int`
5. `timeout_seconds: int`
6. `context_policy: ContextPolicy`
7. `tool_policy: ToolPolicy`

Policy resolution order:

1. profile defaults,
2. agent-level overrides (validated allowlist),
3. request-level safe overrides (limited fields).

## 6. Execution Pipeline

### 6.1 Request Normalization

1. Validate profile and agent availability.
2. Normalize history messages:
   - drop invalid roles,
   - normalize content shape to canonical text/parts,
   - preserve ordering.
3. Normalize execution context:
   - enforce size and schema bounds,
   - scrub disallowed keys.

### 6.2 Message Assembly

1. System directives (agent + runtime safety).
2. Profile-specific preamble (if configured).
3. Normalized history messages.
4. Current user task.
5. Optional context summary prompt.

This assembly pipeline is centralized and shared across adapters.

### 6.3 Loop Execution

1. Loop mode chosen by `RuntimePolicy.loop_mode`.
2. Transport callback only emits intermediate/final outputs.
3. Recovery logic depends on policy flags and error classification.
4. Round state captured for telemetry and postmortem.

### 6.4 Tool/Skill Invocation

1. Tools/skills loaded from agent initialization.
2. Runtime policy gates what is callable for this profile.
3. Invocation traces include tool id, latency, and error category.

## 7. Streaming & Transport Decoupling

### 7.1 Problem

`stream_callback` historically influenced strategy branching.

### 7.2 New Rule

1. Strategy selection uses profile/policy only.
2. Transport mode controls output channel only:
   - no-stream (single payload),
   - stream (chunk/event emission).

### 7.3 Compatibility

Existing callback APIs remain; adapters provide wrapper translators where needed.

## 8. Adapter Integration Plan

### 8.1 Agent Test Chat Adapter

1. Parse `message` + `conversation_history`.
2. Map to `profile=debug_chat`.
3. Call unified runtime service.
4. Return stream or non-stream response using existing endpoint format.

### 8.2 Mission Task Adapter

1. Build `execution_context` from task/mission state.
2. Map to `profile=mission_task` (or `mission_control` by phase).
3. Call unified runtime service.
4. Feed result back to mission state machine and retry planner.

## 9. Data and Persistence Considerations

1. Conversation history persistence remains owned by current storage modules.
2. Runtime service consumes history; it does not own long-term storage.
3. Mission retry snapshots must reference normalized runtime input/output for auditability.

## 10. Observability

Required tags/fields:

1. `runtime_profile`
2. `runtime_loop_mode`
3. `runtime_path` (`legacy` or `unified`)
4. `history_count`
5. `context_keys`
6. `tool_calls_count`
7. `retry_count`
8. `final_status`

Required dashboards:

1. success rate by profile and runtime path,
2. latency p50/p95 by profile,
3. context-loss error trend.

## 11. Migration Strategy

### Phase 0: Baseline & Contract Tests

1. Freeze expected behavior with parity tests on current production path.
2. Define golden cases for debug-chat and mission-task parity.

### Phase 1: Introduce Unified Runtime Behind Flags

1. Add runtime service and adapters without default switch.
2. Keep legacy behavior as fallback.

### Phase 2: Shadow Validation

1. In staging, run unified path in shadow mode for selected requests.
2. Compare output category and key metrics.

### Phase 3: Gradual Enablement

1. Enable unified path for debug chat first.
2. Enable mission task for low-risk agent groups.
3. Expand by percentage rollout gates.

### Phase 4: Default Switch and Legacy Decommission

1. Switch defaults when SLO and parity targets are met.
2. Remove dead branches after stability window.

## 12. Rollback Strategy

1. Feature flag immediate fallback to legacy runtime per entry point.
2. Keep adapter contracts unchanged to avoid client rollback dependency.
3. Preserve telemetry tag to diagnose rollback trigger.

## 13. Testing Strategy

1. Unit:
   - profile registry,
   - policy resolution,
   - message normalization.
2. Integration:
   - adapter -> runtime wiring for both entry points.
   - multi-turn continuity and context retention tests.
3. E2E:
   - same prompt/history under debug-chat and mission-task should produce parity-class results.
4. Regression:
   - stream event ordering and final output consistency.

## 14. Security and Guardrails

1. Profile-level tool permissions must be least privilege.
2. Context sanitization before model input.
3. Explicit max size limits for history/context payloads.
4. Audit logs for privileged tool invocation.

## 15. Open Questions

1. Should mission control phases use separate profile or profile extension fields?
2. Which parity definition is acceptable: semantic equivalence or exact text match for key scenarios?
3. How long should legacy runtime remain as hot standby after default switch?
