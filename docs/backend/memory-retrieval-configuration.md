# User Memory Retrieval Configuration (Production)

## 1. Scope

This document defines how the reset-era `user_memory` pipeline resolves embedding and rerank
models and performs retrieval in production.

Goals:
- Keep user-memory retrieval independent from knowledge-base retrieval tuning.
- Allow safe fallback to knowledge-base config when user-memory-specific fields are not
  configured.
- Make effective runtime config observable from API/UI.

## 2. Retrieval Pipeline

User-memory retrieval now follows this flow:

1. Build candidate set from Milvus (`top_k` + filter expression).
2. Convert vector distance to similarity (metric-aware: `COSINE`/`IP`/`L2`).
3. Compute base score with configurable weights:
   - `similarity_weight`
   - `recency_weight`
4. Apply threshold (`similarity_threshold`) and basic guards.
5. Optional model rerank (if `enable_reranking=true`):
   - call rerank API (`/v1/rerank` then `/rerank` fallback)
   - combine rerank score with base score using `rerank_weight`
6. Return top results.

Keyword fallback behavior:
- If semantic search misses, fallback uses `MemoryRepository.search_keywords`.
- In strict mode, keyword fallback enforces boundary-aware term matching, phrase/coverage reweighting, and stronger quality gates.

## 3. Embedding Config Resolution

Embedding config is resolved by **scope**.

### 3.1 user_memory scope

Priority:
1. `user_memory.embedding.*`
2. if `user_memory.embedding.inherit_from_knowledge_base=true`, fallback to
   `knowledge_base.embedding.*`
3. fallback to `llm.embedding_provider` / `llm.default_provider`

### 3.2 knowledge_base scope

Priority:
1. `knowledge_base.embedding.*`
2. optional fallback to `user_memory.embedding.*` (disabled by default)
3. fallback to `llm.embedding_provider` / `llm.default_provider`

## 4. Rerank Config Resolution (User Memory)

User-memory rerank settings are primarily from `user_memory.retrieval.*`.

If user-memory rerank provider/model is blank, fallback to:
- `knowledge_base.search.rerank_provider`
- `knowledge_base.search.rerank_model`

This gives independent tuning while still supporting zero-friction bootstrap.

## 5. Recommended Production Strategy

Use **split config with controlled inheritance**:

- Keep user-memory and knowledge-base retrieval parameters separate.
- Keep user-memory embedding/rerank explicitly configurable in `user_memory` scope.
- Allow fallback to knowledge-base defaults only as bootstrap or emergency fallback.
- Keep provider inventory shared at LLM provider layer (DB/config), not duplicated per subsystem.

Practical recommendation:
- In production, set `user_memory.embedding.provider/model` explicitly.
- Set `user_memory.retrieval.rerank_provider/model` explicitly when user-memory quality matters.
- Keep inheritance enabled only if your operations team wants auto-follow behavior.

## 6. Observability and API

User-memory config API:
- `GET /api/v1/user-memory/config`
- `PUT /api/v1/user-memory/config` (admin only)

Response includes:
- configured values
- `effective` runtime values
- `sources` (where each effective field came from)

This is intended to avoid ambiguity in incident/debug scenarios.

## 7. Runtime and Safety Flags

Use these reset-era flags for staged rollout/rollback:

- `user_memory.retrieval.strict_keyword_fallback` (default: `true`)
  - `true`: strict keyword semantics with stronger overlap/quality gate.
  - `false`: legacy keyword semantics (rollback path).

- `runtime_context.enable_user_memory` / `runtime_context.enable_skills` /
  `runtime_context.enable_knowledge_base`
  - Toggle which durable sources the agent runtime injects.

- `user_memory.observability.enable_quality_counters` (default: `true`)
  - Enables quality telemetry counters:
  - blocked writes
  - consolidation actions
  - retrieval source quality (`vector` / `keyword`)

## 8. Top-K Relevance Evaluation

Run retrieval evaluation against the reset-era user-memory and skill-learning suites.
The legacy `scripts/evaluate_memory_retrieval_topk.py` path has been removed.
Track retrieval source breakdown (`vector` / `keyword`) as part of result analysis.
