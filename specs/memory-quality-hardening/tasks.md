# Memory Quality Hardening - Tasks

## Phase P0: Precision Guardrails

- [x] P0.1 Enforce fail-closed extraction for online `USER_CONTEXT` and `AGENT` writes
- [x] P0.2 Remove/disable low-quality fallback write path for strict memory types
- [x] P0.3 Ensure runtime retrieval uses configured semantic threshold consistently across agent entry points
- [x] P0.4 Raise keyword fallback minimum rank/score gate
- [x] P0.5 Tighten context overlap checks for keyword-sourced memories
- [x] P0.6 Revisit `user_preference` relevance gate (no unconditional pass)
- [x] P0.7 Add/adjust unit tests for empty extraction no-write and stricter retrieval gates
- [x] P0.8 Validate targeted regression test suite

## Phase P1: Action Planner and Executor

- [x] P1.1 Introduce `MemoryActionPlanner` abstraction and interface
- [x] P1.2 Implement planner output schema: `ADD/UPDATE/DELETE/NONE`
- [x] P1.3 Integrate planner into write path before persistence
- [x] P1.4 Implement `MemoryActionExecutor` with explicit `NONE` no-op behavior
- [x] P1.5 Implement soft-delete semantics for planner-driven `DELETE`
- [x] P1.6 Preserve/update dedup merge behavior under `UPDATE`
- [x] P1.7 Add action decision metadata to memory metadata payload
- [x] P1.8 Add unit tests for planner action matrix (add/update/delete/none)
- [x] P1.9 Add integration tests for session flush with planner decisions

## Phase P2: Path Unification and Observability

- [x] P2.1 Route bypass write paths (including promote/share flow) through policy write service or explicit controlled mode
- [x] P2.2 Separate semantic relevance score from business score in context gate decisions
- [x] P2.3 Improve keyword retrieval implementation toward stronger text search semantics
- [x] P2.4 Add telemetry counters for blocked writes, planner actions, and retrieval source quality
- [x] P2.5 Build evaluation script/report for Top-K relevance tracking
- [x] P2.6 Add rollout feature flags and config docs

## Acceptance and Release Checklist

- [ ] A1 Empty-extraction write rate for strict memory types is 0%
- [ ] A2 Top-3 irrelevant retrieval hit rate reduced by >= 50% on evaluation set
- [ ] A3 7-day duplicate memory rate reduced by >= 40%
- [ ] A4 p95 retrieval latency regression <= 10%
- [ ] A5 Action decision metadata present for >= 95% writes in rollout scope
- [ ] A6 Rollback switches validated in staging
