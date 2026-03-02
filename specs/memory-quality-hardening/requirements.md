# Memory Quality Hardening - Requirements

## Overview

This spec hardens the memory pipeline to improve precision and reduce irrelevant hits, while preserving useful long-term memory behavior.

The primary issue is not absence of extraction, but lack of an explicit write-action decision layer and loose retrieval gates in several paths.

## Problem Statement

Current behavior has three risk categories:

1. Write quality drift:
- Some paths can still persist low-quality or fallback-derived memory content when model extraction is weak.
- Write semantics are merge-centric, not explicit `ADD/UPDATE/DELETE/NONE`.

2. Retrieval precision drift:
- Similarity and keyword fallback thresholds are too permissive in several execution paths.
- Context relevance gating can pass weakly related memories.

3. Path inconsistency:
- There are write bypasses that do not follow the same extraction and dedup policy.

## Goals

1. Enforce high-quality memory writes with fail-closed extraction for user/agent long-term memories.
2. Introduce explicit action planning semantics (`ADD/UPDATE/DELETE/NONE`) before write execution.
3. Reduce irrelevant retrieval hits in agent runtime context assembly.
4. Unify write paths so all persistence follows a single quality policy.
5. Improve observability of memory decision quality and retrieval relevance.

## Non-Goals

1. Replacing the existing memory system with mem0 wholesale.
2. Rebuilding the entire storage stack (Postgres/Milvus) in this project.
3. Large schema redesign outside fields needed for action audit and safe rollout.

## User Stories

### US-1: High-quality write guarantee
As a product owner, I want low-confidence/empty extraction to produce no write, so that memory quality is not degraded by fallback text.

Acceptance Criteria:
- [ ] For `USER_CONTEXT` and `AGENT`, empty model extraction yields `NONE` (no write).
- [ ] Heuristic fallback is disabled by default for those types in online chat paths.
- [ ] Existing successful extraction paths keep working.

### US-2: Explicit action semantics
As an engineer, I want every write to be planned as `ADD/UPDATE/DELETE/NONE`, so that behavior is deterministic and auditable.

Acceptance Criteria:
- [ ] Planner output is produced before persistence.
- [ ] Executor applies only planner-approved actions.
- [ ] `NONE` never writes a new memory record.
- [ ] `DELETE` follows defined soft-delete semantics.

### US-3: Retrieval relevance hardening
As an end user, I want returned memories to be relevant to the current request, so that the agent does not use unrelated context.

Acceptance Criteria:
- [ ] Semantic threshold usage is consistent across runtime entry points.
- [ ] Keyword fallback thresholds are stricter than semantic floor.
- [ ] Context gate requires stronger overlap for keyword-derived memories.
- [ ] Relevance pass rate improves on evaluation set.

### US-4: Unified write policy
As a maintainer, I want all write paths to share one policy, so that quality behavior is predictable.

Acceptance Criteria:
- [ ] Bypass writes are routed through the same policy service or explicitly exempted with documented reason.
- [ ] Share/promote path no longer bypasses quality controls without explicit flag and audit.

### US-5: Observable quality
As an operator, I want measurable quality telemetry, so that regressions are caught quickly.

Acceptance Criteria:
- [ ] Action distribution (`ADD/UPDATE/DELETE/NONE`) is recorded.
- [ ] Low-quality write attempts and blocked writes are counted.
- [ ] Retrieval relevance metrics are tracked by source (`semantic`/`keyword`).

## Functional Requirements

### FR-1: Two-stage write pipeline

The system MUST apply:
1. Stage A: extract candidate facts.
2. Stage B: decide actions (`ADD/UPDATE/DELETE/NONE`) against existing memory.
3. Stage C: execute actions atomically per memory item.

### FR-2: Fail-closed extraction policy

For online conversation write paths:
- `USER_CONTEXT`, `AGENT` memory types MUST default to fail-closed.
- If extraction result is empty or parsing fails, result MUST be `NONE`.
- Fallback-to-raw or fallback-to-heuristic write MUST be off by default.

### FR-3: Retrieval hard gates

- Runtime context retrieval MUST apply configured semantic threshold consistently.
- Keyword fallback MUST require stricter rank/score and overlap than semantic retrieval.
- Context relevance gate MUST treat keyword retrieval as lower-trust source.

### FR-4: Write path normalization

All write entry points MUST go through one policy-enforced write service unless explicitly tagged as import/admin operation.

### FR-5: Action audit

Each decision SHOULD preserve minimal audit metadata:
- decision source
- chosen action
- confidence (when available)
- reason code (optional)

## Non-Functional Requirements

### NFR-1: Latency
- P0 changes should not increase p95 retrieval latency by more than 10%.
- Planner in P1 should stay within acceptable write latency budget for interactive chats.

### NFR-2: Safety
- No destructive migration required for P0/P1 rollout.
- Feature flags required for staged enablement.

### NFR-3: Backward compatibility
- Existing memory read APIs remain compatible.
- Existing memory records remain valid.

## Success Metrics

1. Low-quality write rate:
- Empty-extraction write rate for `USER_CONTEXT`/`AGENT` = 0%.

2. Retrieval relevance:
- Top-3 irrelevant hit rate reduced by at least 50% on evaluation set.

3. Duplication quality:
- 7-day duplicate memory rate reduced by at least 40%.

4. Decision observability:
- At least 95% of writes include action decision metadata.

## Rollout Gates

1. P0 gate:
- Retrieval precision and empty-write guard tests pass.

2. P1 gate:
- Planner action tests pass across add/update/delete/none scenarios.

3. P2 gate:
- Production telemetry confirms no regression in latency and write success.

