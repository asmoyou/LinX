# Agent Test Chat Runtime Strategy - Requirements

## 1. Overview

This spec defines a production-grade runtime strategy so that:

1. Agent test chat (`/agents/{id}/test`) and mission execution use the same core execution semantics.
2. Frontend debug results are representative of mission behavior.
3. Entry-point differences remain explicit through adapter layers, instead of hidden logic forks.

The immediate multi-turn context bug in test chat has been fixed at implementation level. This document addresses the deeper architectural consistency and long-term maintainability.

## 2. Problem Statement

Current runtime behavior has diverged across execution paths:

1. Agent test chat and mission execution do not always share the same strategy selection logic.
2. Multi-round behavior is coupled to `stream_callback` in parts of the code path, which mixes transport and reasoning policy.
3. Context/memory and tool-skill policy are not defined by a single contract that both paths must follow.

This causes debugging mismatch: a prompt that works in test chat may behave differently in mission, and vice versa.

## 3. Goals

1. Define one core execution contract for all agent runs.
2. Separate execution policy from transport concerns (streaming vs non-streaming).
3. Preserve mission-specific orchestration features without duplicating agent runtime logic.
4. Provide phased migration and rollback strategy suitable for production.

## 4. User Stories

### 4.1 Platform Engineer
As a platform engineer, I want both test chat and mission to call the same runtime core so I can debug once and trust behavior parity.

Acceptance criteria:
- A single runtime service handles message assembly, loop policy, and tool/skill invocation.
- Entry-point code only maps request context to runtime profile and output transport.

### 4.2 Agent Developer
As an agent developer, I want a deterministic execution profile so I know whether a run is single-turn, auto multi-turn, or recovery-enabled.

Acceptance criteria:
- Runtime profile is explicit and logged per execution.
- Profile controls loop strategy, timeout, and retry policy.

### 4.3 Mission Operator
As a mission operator, I want mission tasks to keep required context and memory consistently across retries/replans.

Acceptance criteria:
- Mission task execution context is passed via runtime contract, not ad-hoc fields.
- Retry/recovery does not silently drop context.

### 4.4 SRE/On-call
As on-call engineer, I want observability that quickly explains behavior differences.

Acceptance criteria:
- Traces/logs include `execution_profile`, `loop_mode`, `context_source`, and `history_count`.
- Dashboards can compare test-chat and mission success metrics with same tags.

## 5. Functional Requirements

### FR-1: Unified Runtime Service
1. Introduce a shared runtime service that owns:
   - message assembly (task + system + history + context),
   - loop execution policy (single-turn / auto multi-turn / recovery),
   - tool/skill invocation orchestration boundary.
2. Both test chat and mission paths must call this service.

### FR-2: Execution Profile Contract
1. Define `ExecutionProfile` as first-class runtime input (for example: `debug_chat`, `mission_task`, `mission_control`).
2. Profile must configure:
   - loop mode,
   - retry budget,
   - timeout budget,
   - memory/context inclusion policy,
   - streaming output policy.

### FR-3: Context & History Contract
1. Define canonical message/history schema accepted by runtime service.
2. Runtime must normalize history content shape and enforce role validity.
3. Mission execution context must be passed in structured form; no hidden side-channel mutation.

### FR-4: Transport Decoupling
1. `stream_callback` (or equivalent transport hooks) must only control output delivery.
2. Multi-round strategy cannot be gated solely by callback existence.

### FR-5: Tool/Skill Policy Consistency
1. Skill and tool availability must derive from agent initialization + runtime profile policy.
2. Test chat and mission task with same profile policy must expose consistent tool/skill set.

### FR-6: Backward-Compatible Adapters
1. Existing API response contracts for test chat and mission events must remain backward compatible.
2. Any changed field semantics must be versioned or feature-flagged.

### FR-7: Fail-Safe Rollout
1. Introduce feature flags to switch per entry point:
   - legacy runtime path,
   - unified runtime path.
2. Support quick rollback without schema rollback.

## 6. Non-Functional Requirements

1. Reliability:
   - No increase in mission task failure rate attributable to runtime migration.
2. Performance:
   - P95 latency regression per run <= 10% under comparable load.
3. Observability:
   - Structured logs and traces must identify runtime path and profile.
4. Testability:
   - Unit + integration + e2e parity tests required before full rollout.
5. Security:
   - No profile may escalate tool permissions beyond current policy defaults.

## 7. Constraints

1. Do not force immediate hard merge of all orchestration code.
2. Keep mission state-machine concerns in mission layer.
3. Keep API gateway concerns in router layer.
4. Runtime unification is about execution core semantics and contracts.

## 8. Success Metrics

1. Debug-to-production parity:
   - Reproducible behavior match rate between test chat and mission task >= 90% for parity test suite.
2. Context retention:
   - Multi-turn context loss defect rate reduced to near zero in tracked scenarios.
3. Stability:
   - No Sev-1/Sev-2 incidents caused by runtime unification rollout.

## 9. Out of Scope

1. Full redesign of mission orchestration state machine.
2. New knowledge base retrieval architecture.
3. Frontend UX redesign unrelated to runtime contract.

## 10. Dependencies

1. Existing mission-system specification (`.kiro/specs/mission-system`).
2. Existing agent error recovery design (`.kiro/specs/agent-error-recovery`).
3. Agent framework, API gateway, and mission orchestrator modules.

## 11. Risks and Mitigations

1. Risk: Hidden path dependencies in legacy mission flow.
   - Mitigation: Dual-path flag + shadow execution comparison in staging.
2. Risk: Streaming protocol coupling regression.
   - Mitigation: Contract tests for event ordering and chunk semantics.
3. Risk: Latency increase from generalized runtime pipeline.
   - Mitigation: Profile-specific fast path + benchmark gates.

## 12. Validation Requirements

1. Unit tests for profile resolution, history normalization, and loop policy selection.
2. Integration tests covering:
   - agent test chat multi-turn continuity,
   - mission task context retention across retry.
3. E2E tests validating parity between test chat and mission for representative skills/tools.
4. Canary rollout with metric comparison before default switch.

## 13. Documentation Deliverables

1. Runtime profile matrix (entry point x profile x behavior).
2. Migration runbook (enable flag, monitor, rollback).
3. Troubleshooting guide for context-loss and loop-policy mismatches.
