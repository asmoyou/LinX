# Memory System Reset - Requirements

## Overview

This spec replaces the current multi-type memory product model with a simpler and stricter target:

- `User Memory` is the only long-term memory product.
- `Agent Memory` is removed as a memory product and replaced by `Skill Learning`.
- `Company Memory` is removed as a memory product and replaced by the existing `Knowledge Base`.
- `Task Context` is removed from long-term memory and kept in task/session runtime state only.
- `Session Ledger` remains, but only as an internal provenance layer with retention cleanup.

This is a one-shot cutover spec. The product is not launched, so legacy memory data, compatibility APIs,
dual-write paths, and backward-compatibility tests are out of scope and should be deleted rather than carried.

## Problem Statement

The current architecture mixes three different concepts into one system:

1. Long-term personal memory
2. Reusable execution know-how
3. Shared organizational knowledge

That produces the wrong product boundaries:

- `agent` memory is really learned skill/procedure, not memory
- `company` memory duplicates knowledge-base responsibilities
- `task_context` pollutes long-term storage with runtime-only state
- `user_context` is the only category that truly belongs in a memory system

The result is avoidable complexity:

- `MemoryType` drives product behavior, storage layout, runtime retrieval, and UI filters
- runtime context assembly is split into `agent / company / user_context / task_context`
- APIs, config, tests, vector collections, and partitions all encode the wrong taxonomy
- SimpleMem-style factual recall is weakened because the system still thinks in type buckets instead of atomic facts

## Product Decision

### Keep

1. `User Memory`
2. `Knowledge Base`
3. `Skills`
4. `Session Ledger` as internal provenance only

### Remove

1. `Agent Memory` as a user-facing or runtime-facing memory product
2. `Company Memory` as a memory product
3. `Task Context` as a long-term memory product
4. generic multi-type `MemoryType` as the primary product model

## Goals

1. Build a SimpleMem-style factual `User Memory` system centered on atomic facts and events.
2. Move learned successful paths into a proper `Skill Learning` pipeline instead of storing them as agent memory.
3. Route all shared organizational information to the `Knowledge Base`, not the memory system.
4. Remove legacy memory types, compatibility layers, and old tests in one cut.
5. Simplify runtime context assembly to only three sources:
   - user memory
   - skills
   - knowledge references
6. Reset the database and vector storage so the final architecture is clean from day one.

## Non-Goals

1. Backfilling or preserving old memory data
2. Maintaining compatibility with old `/memories` semantics
3. Keeping `memory_records`-based storage alive behind a facade
4. Preserving old frontend filters for memory type selection
5. Supporting mixed legacy/new execution paths during rollout

## User Stories

### US-1: Personal factual memory

As a user, I want the system to remember factual information about me, so that future interactions can reuse it accurately.

Acceptance Criteria:
- [ ] The system stores relationship, experience, skill, preference, goal, constraint, identity, and event facts.
- [ ] Facts are stored as self-contained statements instead of UI-shaped key/value fragments only.
- [ ] Queries like "用户什么时候搬到杭州" or "用户和王敏是什么关系" resolve from user memory.

### US-2: Learned execution know-how

As a platform owner, I want agent successful paths to become skill proposals, so that reusable know-how is managed like skills instead of memory.

Acceptance Criteria:
- [ ] Session learning can generate `skill proposals` from successful executions.
- [ ] Skill proposals have review and publish semantics.
- [ ] Published learned skills flow into the existing skill system, not the memory system.

### US-3: Shared knowledge stays in KB

As an operator, I want organization-wide knowledge to live in the knowledge base, so that there is only one product for shared documents and facts.

Acceptance Criteria:
- [ ] There is no new company memory write path.
- [ ] Runtime uses KB retrieval for shared organizational knowledge.
- [ ] Memory UI no longer exposes a company memory category.

### US-4: Runtime simplicity

As an agent runtime maintainer, I want context retrieval to assemble only from user memory, skills, and KB, so that behavior is explainable and consistent.

Acceptance Criteria:
- [ ] Runtime context no longer retrieves `company`, `task_context`, or `agent` memory scopes.
- [ ] Agent context assembly uses a unified source contract.
- [ ] Config surfaces align to the new three-source model.

### US-5: Clean reset

As a maintainer, I want a destructive reset path, so that the repository no longer carries dead memory architecture and misleading tests.

Acceptance Criteria:
- [ ] Old memory tables and vector collections are dropped or recreated.
- [ ] Old multi-type memory APIs are removed.
- [ ] Obsolete tests are deleted or rewritten before merge.

## Functional Requirements

### FR-1: Single long-term memory product

The system MUST keep only one long-term memory product: `User Memory`.

`User Memory` MUST support:
- atomic fact entries
- profile projections
- episodic/timed event recall
- semantic retrieval over user facts

### FR-2: User memory fact model

Each durable user memory entry MUST support the following fields where applicable:

- `fact_kind`
- `canonical_text`
- `predicate`
- `object`
- `event_time`
- `location`
- `persons`
- `entities`
- `topic`
- `confidence`
- provenance to session ledger

### FR-3: User memory projections

The system MUST maintain at least two read models:

1. `user_profile_view`
   - stable profile facts
   - no noisy session-by-session event spam

2. `user_episode_view`
   - important timed events
   - relocations, life milestones, dated changes

### FR-4: Skill learning replaces agent memory

The system MUST replace agent memory extraction with a `Skill Learning` pipeline.

The pipeline MUST:
- detect successful paths from session ledger
- create `skill proposals`
- support review/publish/reject
- publish accepted proposals into the skill system

The pipeline MUST NOT store successful paths as a separate long-term memory product.

### FR-5: Company knowledge stays in KB

The system MUST route organization-wide facts, documents, playbooks, and references to the knowledge base.

The memory system MUST NOT expose a `company` memory type.

### FR-6: Task state is not long-term memory

The system MUST keep task-specific state in task/session state only.

The memory system MUST NOT expose a `task_context` long-term memory type.

### FR-7: Session ledger is internal only

The system MUST keep session ledger as an internal provenance substrate.

The ledger MUST:
- capture ordered session events
- support user memory and skill learning extraction
- be cleaned up by retention policy

The ledger MUST NOT be presented as a first-class end-user memory product.

### FR-8: Destructive schema reset

The implementation MUST support a one-shot destructive reset.

The reset MUST:
- drop old memory tables or replace them entirely
- clear old Milvus memory collections/partitions
- recreate only the final target schema

No backfill is required.

### FR-9: API reset

The implementation MUST remove old generic memory CRUD and type-driven APIs.

Replacement API groups MUST be:

1. `user memory`
2. `skill proposals / learned skills`
3. existing `knowledge base`

### FR-10: Frontend reset

The frontend MUST remove old memory type filters and views.

The final UI model MUST be:

1. `User Memory`
2. `Skill Learning`
3. `Knowledge Base`

### FR-11: Config reset

The final config MUST not be organized around old memory types.

Config MUST be split into:

1. `user_memory`
2. `skill_learning`
3. `knowledge_base`
4. internal `session_ledger`

### FR-12: Test-suite reset

Tests that encode old multi-type memory semantics MUST be deleted or rewritten before merge.

The final suite MUST validate:

1. user fact extraction and consolidation
2. user profile and episodic retrieval
3. skill proposal learning and publish flow
4. runtime context assembly from user memory + skills + KB
5. session-ledger retention cleanup

## Non-Functional Requirements

### NFR-1: Simplicity

The target architecture SHOULD reduce the number of product-facing memory categories from four to one.

### NFR-2: Explainability

Runtime context assembly SHOULD be explainable in terms of:
- personal facts
- learned skills
- knowledge references

### NFR-3: Operational safety

The reset SHOULD be reproducible from an empty database and empty vector store without requiring historical migration jobs.

### NFR-4: Performance

User memory retrieval SHOULD remain within the current interactive budget for chat context injection.

Skill proposal extraction MAY run asynchronously if needed, but its write path must not block core chat completion.

## Success Metrics

1. There is no remaining product-facing `company` or `agent` memory category.
2. Runtime context debug output shows only:
   - user memory
   - skills
   - knowledge references
3. User memory can answer relationship and timed-event questions in integration tests.
4. Learned successful paths publish into the skill system without using generic memory tables.
5. Obsolete legacy memory tests are removed from the main test suite.

## Merge Gates

1. Old `MemoryType`-driven runtime retrieval is removed.
2. Old generic `/memories` product semantics are removed or fully repurposed.
3. User-memory tests and skill-learning tests pass.
4. Obsolete memory tests are deleted or rewritten.
5. Database reset and fresh-start bootstrap work from zero state.
