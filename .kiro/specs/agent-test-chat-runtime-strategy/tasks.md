# Agent Test Chat Runtime Strategy - Tasks

## Status Legend

- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed
- `[!]` Blocked

## 1. Phase 0 - Baseline Stabilization

### 1.1 Context Continuity Hotfix
- `[x]` Wire `conversation_history` into agent test execution path.
- `[x]` Ensure executor path can pass conversation history end-to-end.
- `[x]` Add unit tests for history propagation in streaming/non-streaming paths.

### 1.2 Mission Context Pass-through
- `[x]` Pass mission execution context explicitly into agent execution call.
- `[x]` Add unit tests for mission orchestrator context forwarding.

### 1.3 Baseline Validation
- `[x]` Run targeted backend unit tests for agent framework and mission orchestrator.
- `[x]` Add/update bug report entry with root cause and fix references.

## 2. Phase 1 - Runtime Contract Foundation

### 2.1 Define Core Models
- `[x]` Introduce `ExecutionProfile` enum and policy schema.
- `[x]` Define canonical `RuntimeExecutionRequest` and normalized `Message` schema.
- `[x]` Add validation for history/content role and shape.

### 2.2 Policy Registry
- `[x]` Implement `RuntimePolicyRegistry` with defaults for `debug_chat`, `mission_task`, `mission_control`.
- `[x]` Add safe override rules (agent-level and request-level).
- `[x]` Add unit tests for policy resolution precedence.

### 2.3 Telemetry Contract
- `[x]` Standardize runtime telemetry fields (`runtime_profile`, `runtime_loop_mode`, `runtime_path`, etc.).
- `[x]` Add structured logging helpers shared across adapters.

## 3. Phase 2 - Unified Runtime Service

### 3.1 Service Extraction
- `[x]` Implement `UnifiedAgentRuntimeService` for message assembly and loop orchestration.
- `[x]` Move strategy selection from callback-dependent branches to policy-driven flow.
- `[x]` Keep transport emission pluggable (stream/no-stream).

### 3.2 Adapter Wiring
- `[x]` Refactor agent test chat router to call unified runtime adapter.
- `[x]` Refactor mission task execution adapter to call unified runtime adapter.
- `[x]` Preserve existing API/websocket contracts.

### 3.3 Tool/Skill Consistency
- `[x]` Ensure profile-based tool/skill gating is enforced in both entry points.
- `[ ]` Add regression tests for tool availability parity.

## 4. Phase 3 - Testing and Parity Gates

### 4.1 Unit and Integration Coverage
- `[ ]` Add unit tests for history normalization edge cases.
- `[ ]` Add integration tests for debug-chat and mission-task parity flows.
- `[ ]` Add tests for retry/recovery with retained context.

### 4.2 E2E Parity Suite
- `[ ]` Build parity scenarios: arithmetic, translation, tool call, retry recovery.
- `[ ]` Define pass criteria (semantic parity and failure classification parity).

### 4.3 Performance and Reliability Gates
- `[ ]` Add benchmark checks for p95 regression threshold.
- `[ ]` Validate failure-rate impact in staging.

## 5. Phase 4 - Rollout and Rollback

### 5.1 Feature Flags
- `[x]` Add flags per entry point (`agent_test_chat_unified_runtime`, `mission_task_unified_runtime`).
- `[ ]` Support percentage rollout for mission tasks.

### 5.2 Shadow Mode and Canary
- `[ ]` Implement optional shadow execution in staging with diff logging.
- `[ ]` Build dashboards for parity, latency, and context-loss metrics.

### 5.3 Production Cutover
- `[x]` Enable unified runtime for test chat by default.
- `[ ]` Gradually enable mission task path with guardrails.
- `[ ]` Remove legacy path only after stability window.

## 6. Phase 5 - Documentation and Operations

### 6.1 Developer Docs
- `[x]` Publish runtime profile matrix and adapter responsibilities.
- `[x]` Add implementation guide for adding new runtime profiles.

### 6.2 Runbooks
- `[x]` Create rollout/rollback runbook.
- `[x]` Create troubleshooting guide for context-loss and strategy mismatch incidents.

### 6.3 Handover Checklist
- `[x]` Confirm spec/design/tasks stay updated with implementation PRs.
- `[x]` Add links from related specs (`mission-system`, `agent-error-recovery`) to this spec.
