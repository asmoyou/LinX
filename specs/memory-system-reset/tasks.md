# Memory System Reset - Tasks

## Audit Note

This checklist was partially stale.

Status rule after the 2026-03-12 audit:
- checked: implemented in the repository
- unchecked: still genuinely unfinished relative to the reset spec

Current state:
- all reset workstreams in this checklist are implemented
- remaining red tests in the wider backend suite are outside the reset scope
- bootstrap verification now succeeds from an empty database to head

## Workstream 0: Freeze Old Direction

- [x] W0.1 Delete `specs/memory-quality-hardening/`
- [x] W0.2 Add this reset spec as the only active memory-architecture plan
- [x] W0.3 Mark `docs/backend/memory-system-v2-migration-plan.md` as superseded or remove it
- [x] W0.4 Stop accepting feature work on old `MemoryType`-based paths

## Workstream 1: Delete Old Product Semantics

- [x] W1.1 Remove `MemoryType.AGENT`
- [x] W1.2 Remove `MemoryType.COMPANY`
- [x] W1.3 Remove `MemoryType.USER_CONTEXT`
- [x] W1.4 Remove `MemoryType.TASK_CONTEXT`
- [x] W1.5 Delete `backend/memory_system/memory_interface.py`
- [x] W1.6 Delete `backend/agent_framework/agent_memory_interface.py`
- [x] W1.7 Remove old scope-based runtime retrieval from `backend/agent_framework/agent_executor.py`
- [x] W1.8 Replace runtime source contract with `user_memory / skills / knowledge_refs`

## Workstream 2: Database and Vector Reset

- [x] W2.1 Add destructive migration to drop old memory tables:
  - `memory_records`
  - `memory_acl`
  - `memory_sessions`
  - `memory_session_events`
  - `memory_observations`
  - `memory_materializations`
  - `memory_entries`
  - `memory_links`
- [x] W2.2 Add fresh tables:
  - `session_ledgers`
  - `session_ledger_events`
  - `user_memory_entries`
  - `user_memory_links`
  - `user_memory_views`
  - `skill_proposals`
- [x] W2.3 Add destructive reset for old Milvus memory collections
- [x] W2.4 Create a single user-memory vector collection
- [x] W2.5 Verify clean bootstrap from empty DB and empty vector store

## Workstream 3: User Memory Pipeline

- [x] W3.1 Create `backend/user_memory/` package
- [x] W3.2 Implement `SessionLedgerRepository`
- [x] W3.3 Implement `SessionLedgerService`
- [x] W3.4 Implement `UserMemoryBuilder` with SimpleMem-style atomic fact extraction
- [x] W3.5 Implement `UserMemoryRepository`
- [x] W3.6 Implement `UserMemoryConsolidator`
- [x] W3.7 Implement `UserMemoryProjector`
- [x] W3.8 Implement `UserMemoryRetriever`
- [x] W3.9 Support `profile` and `episode` views
- [x] W3.10 Implement `SessionLedgerRetentionManager`

## Workstream 4: Skill Learning Pipeline

- [x] W4.1 Create `backend/skill_learning/` package
- [x] W4.2 Implement `SkillProposalBuilder`
- [x] W4.3 Implement `SkillProposalRepository`
- [x] W4.4 Implement `SkillProposalService`
- [x] W4.5 Replace agent-memory extraction with skill-proposal extraction
- [x] W4.6 Add publish flow from `skill_proposals` into existing skill registry
- [x] W4.7 Remove generic memory candidate review path from memory router

## Workstream 5: Remove Legacy Memory Modules

- [x] W5.1 Delete `backend/memory_system/memory_system.py`
- [x] W5.2 Delete `backend/memory_system/memory_repository.py`
- [x] W5.3 Delete `backend/memory_system/legacy_memory_compat_service.py`
- [x] W5.4 Delete `backend/memory_system/session_memory_builder.py`
- [x] W5.5 Delete `backend/memory_system/materialization_retrieval_service.py`
- [x] W5.6 Delete `backend/memory_system/materialization_maintenance_service.py`
- [x] W5.7 Delete `backend/memory_system/materialization_maintenance_manager.py`
- [x] W5.8 Delete `backend/memory_system/retrieval_gateway.py`
- [x] W5.9 Delete `backend/memory_system/collections.py`
- [x] W5.10 Delete `backend/memory_system/partitions.py`
- [x] W5.11 Delete old memory backfill and diagnosis scripts

## Workstream 6: API Reset

- [x] W6.1 Delete or fully repurpose `backend/api_gateway/routers/memory.py`
- [x] W6.2 Add `backend/api_gateway/routers/user_memory.py`
- [x] W6.3 Add `backend/api_gateway/routers/skill_proposals.py`
- [x] W6.4 Remove old generic `/api/v1/memories` product routes
- [x] W6.5 Add user-memory search/profile/episodes/config/admin endpoints
- [x] W6.6 Add skill-proposal list/review/publish endpoints
- [x] W6.7 Keep KB endpoints as the shared-knowledge path

## Workstream 7: Frontend Reset

- [x] W7.1 Remove memory type filters from frontend memory types
- [x] W7.2 Replace generic Memory page with User Memory page
- [x] W7.3 Remove company-memory UI
- [x] W7.4 Remove agent-memory-candidate UI under generic memory
- [x] W7.5 Add Skill Learning review UI
- [x] W7.6 Move shared knowledge navigation to KB only
- [x] W7.7 Replace old memory config panel with:
  - user memory settings
  - skill learning settings
  - internal session-ledger settings

## Workstream 8: Config Reset

- [x] W8.1 Remove old `memory` config sections that encode type-driven semantics
- [x] W8.2 Add `user_memory` config section
- [x] W8.3 Add `skill_learning` config section
- [x] W8.4 Add `session_ledger` config section
- [x] W8.5 Remove old memory scope flags from runtime/agent config
- [x] W8.6 Add new runtime source toggles:
  - `enable_user_memory`
  - `enable_skills`
  - `enable_knowledge_base`

## Workstream 9: Tests To Delete

- [x] W9.1 Delete `backend/tests/e2e/test_memory_sharing.py`
- [x] W9.2 Delete `backend/tests/integration/test_agent_memory_integration.py`
- [x] W9.3 Delete `backend/tests/unit/memory_system/test_materialization_maintenance_manager.py`
- [x] W9.4 Delete `backend/tests/unit/memory_system/test_materialization_maintenance_service.py`
- [x] W9.5 Delete `backend/tests/unit/memory_system/test_materialization_retrieval_service.py`
- [x] W9.6 Delete `backend/tests/unit/memory_system/test_memory_action_planner.py`
- [x] W9.7 Delete `backend/tests/unit/memory_system/test_memory_repository.py`
- [x] W9.8 Delete `backend/tests/unit/memory_system/test_memory_system.py`
- [x] W9.9 Delete `backend/tests/unit/memory_system/test_retrieval_gateway.py`
- [x] W9.10 Delete `backend/tests/unit/memory_system/test_session_memory_builder.py`

## Workstream 10: Tests To Rewrite

- [x] W10.1 Rewrite `backend/tests/unit/api_gateway/routers/test_memory.py` for user-memory and skill-proposal APIs
- [x] W10.2 Rewrite `backend/tests/unit/api_gateway/routers/test_agents_attachment_helpers.py` around user-fact extraction and skill-proposal extraction
- [x] W10.3 Rewrite `backend/tests/integration/test_session_memory_flush_integration.py` around:
  - user-memory writes
  - skill-proposal writes
  - no legacy generic memory writes
- [x] W10.4 Rewrite current session-ledger repository/service tests against new `backend/user_memory/` modules
- [x] W10.5 Rewrite performance memory retrieval tests for user-memory retrieval only
- [x] W10.6 Rewrite access-control tests to match user-memory and KB ownership rules

## Workstream 11: New Tests To Add

- [x] W11.1 Add `backend/tests/unit/user_memory/test_user_memory_builder.py`
- [x] W11.2 Add `backend/tests/unit/user_memory/test_user_memory_consolidator.py`
- [x] W11.3 Add `backend/tests/unit/user_memory/test_user_memory_projector.py`
- [x] W11.4 Add `backend/tests/unit/user_memory/test_user_memory_retriever.py`
- [x] W11.5 Add `backend/tests/unit/user_memory/test_session_ledger_retention_manager.py`
- [x] W11.6 Add `backend/tests/unit/skill_learning/test_skill_proposal_builder.py`
- [x] W11.7 Add `backend/tests/unit/skill_learning/test_skill_proposal_service.py`
- [x] W11.8 Add `backend/tests/integration/test_user_memory_runtime_integration.py`
- [x] W11.9 Add `backend/tests/integration/test_skill_learning_publish_flow.py`

## Workstream 12: Cleanup and Verification

- [x] W12.1 Remove old memory acceptance scripts/reports
- [x] W12.2 Remove dead imports and config references repository-wide
- [x] W12.3 Run backend target suites for user memory, skill learning, runtime, and KB integration
- [x] W12.4 Run frontend lint/type-check for user-memory and skill-learning pages
- [x] W12.5 Run a fresh empty-database bootstrap verification
- [x] W12.6 Review all deleted tests to ensure no old semantics remain hidden in the suite
