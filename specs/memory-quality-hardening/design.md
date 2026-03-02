# Memory Quality Hardening - Design

## Architecture Intent

Adopt mem0-style decision semantics without replacing the current system:

1. Extract candidate facts.
2. Plan explicit actions (`ADD/UPDATE/DELETE/NONE`) against existing memories.
3. Execute actions through one policy-enforced write path.
4. Harden retrieval thresholds and context gating.

## Current vs Target

### Current (simplified)

`extract/normalize -> dedup/merge -> write`

Risks:
- No explicit action planner.
- Empty extraction can still degrade into fallback behavior in some paths.
- Retrieval gates vary by caller.

### Target (simplified)

`extract facts -> action planner -> action executor -> storage`

Properties:
- `NONE` is explicit and write-free.
- `DELETE` and `UPDATE` are first-class operations.
- Read-time relevance gates are consistent.

## Scope by Phase

## P0: Precision Guardrails (fast stabilization)

Objective: stop low-quality writes and reduce irrelevant hits with minimal structural change.

Changes:
1. Fail-closed extraction for online `USER_CONTEXT`/`AGENT` writes.
2. Enforce runtime semantic threshold consistently.
3. Tighten keyword fallback threshold and overlap gate.
4. Tighten context relevance checks for keyword-sourced memories.

Primary code touchpoints:
- `backend/memory_system/memory_system.py`
- `backend/agent_framework/agent_memory_interface.py`
- `backend/agent_framework/agent_executor.py`
- `backend/api_gateway/routers/memory.py`

Feature flags:
- `memory.write.fail_closed_user_agent` (default: on for online paths)
- `memory.retrieval.strict_keyword_fallback` (default: on)

## P1: Action Planner (core parity with mem0 semantics)

Objective: introduce explicit action decision layer before write.

New components:
1. `MemoryActionPlanner`
- Input: extracted facts + candidate existing memories + metadata.
- Output: action list of `ADD/UPDATE/DELETE/NONE` with optional reason.

2. `MemoryActionExecutor`
- Applies planner output.
- Ensures `NONE` does not write.
- Applies soft-delete for `DELETE`.

Behavioral rules:
- `ADD`: create new memory record.
- `UPDATE`: update existing record content/metadata.
- `DELETE`: soft-delete existing record (`is_active=false`, audit reason).
- `NONE`: no DB insert/update of content.

Primary code touchpoints:
- `backend/memory_system/memory_system.py`
- `backend/memory_system/memory_repository.py`
- optional helper module under `backend/memory_system/`

## P2: Path Unification + Quality Observability

Objective: remove bypasses and instrument quality.

Changes:
1. Route bypass write paths (including promote/share paths) through policy write service.
2. Separate semantic score and business score in relevance decisions.
3. Add telemetry for action outcomes and blocked writes.
4. Upgrade keyword retrieval strategy (towards full-text/trigram where feasible).

Primary code touchpoints:
- `backend/api_gateway/routers/memory.py`
- `backend/memory_system/memory_repository.py`
- `backend/agent_framework/agent_executor.py`

## Data and Metadata Design

No mandatory destructive schema change for P0.

P1/P2 optional additive fields:
1. `decision_action` (enum-like text)
2. `decision_source` (planner/manual/import)
3. `decision_confidence` (float, nullable)
4. `decision_reason` (text, nullable)
5. `superseded_by` (uuid, nullable for soft-delete chains)

If schema change is delayed, store these under metadata JSON first.

## Retrieval Gate Design

Policy:
1. Apply semantic threshold before context injection.
2. Keyword fallback only when semantic retrieval is insufficient.
3. Keyword result must meet stricter overlap and source-aware gate.
4. Context relevance should primarily use semantic relevance, not blended recency/importance.

## Failure Handling

1. Extraction failure/empty for strict types:
- return `NONE`, no write.

2. Planner failure:
- fail-safe to `NONE` in strict mode.

3. Vector sync failure:
- keep DB source of truth and mark sync failure for retry.

## Testing Strategy

## Unit tests

1. Extraction empty -> `NONE` and no write.
2. Planner emits correct action under add/update/delete/none scenarios.
3. Keyword fallback gates reject weak matches.
4. Context gate rejects low-overlap keyword items.

## Integration tests

1. End-to-end chat session flush:
- meaningful memory is written
- empty/noisy extraction writes nothing

2. Retrieval precision scenario:
- unrelated content is excluded from Top-K context.

## Regression tests

1. Existing memory CRUD/read APIs remain compatible.
2. Existing structured memory rendering is unchanged.

## Rollout and Rollback

Rollout:
1. Enable P0 flags in staging.
2. Validate precision and write-rate metrics.
3. Gradually enable in production.

Rollback:
1. Disable strict flags to previous behavior.
2. Keep additive metadata fields intact.
3. No data backfill required for rollback.

## Risks and Mitigations

1. Risk: recall drops too much after stricter gates.
- Mitigation: controlled threshold tuning via config and evaluation set.

2. Risk: planner adds write latency.
- Mitigation: bounded planner context, timeout, and fallback-to-`NONE`.

3. Risk: path unification breaks edge workflows.
- Mitigation: phased routing and endpoint-level feature flag.

