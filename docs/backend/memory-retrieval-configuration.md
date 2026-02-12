# Memory Retrieval Configuration (Production)

## 1. Scope

This document defines how the **memory system** resolves embedding/rerank models and performs retrieval in production.

Goals:
- Keep memory retrieval independent from knowledge-base retrieval tuning.
- Allow safe fallback to knowledge-base config when memory-specific fields are not configured.
- Make effective runtime config observable from API/UI.

## 2. Retrieval Pipeline

Memory retrieval now follows this flow:

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

## 3. Embedding Config Resolution

Embedding config is resolved by **scope**.

### 3.1 memory scope

Priority:
1. `memory.embedding.*`
2. if `memory.embedding.inherit_from_knowledge_base=true`, fallback to `knowledge_base.embedding.*`
3. fallback to `llm.embedding_provider` / `llm.default_provider`

### 3.2 knowledge_base scope

Priority:
1. `knowledge_base.embedding.*`
2. optional fallback to `memory.embedding.*` (disabled by default)
3. fallback to `llm.embedding_provider` / `llm.default_provider`

## 4. Rerank Config Resolution (Memory)

Memory rerank settings are primarily from `memory.retrieval.*`.

If memory rerank provider/model is blank, fallback to:
- `knowledge_base.search.rerank_provider`
- `knowledge_base.search.rerank_model`

This gives independent tuning while still supporting zero-friction bootstrap.

## 5. Recommended Production Strategy

Use **split config with controlled inheritance**:

- Keep memory and knowledge-base retrieval parameters separate.
- Keep memory embedding/rerank explicitly configurable in memory scope.
- Allow fallback to knowledge-base defaults only as bootstrap or emergency fallback.
- Keep provider inventory shared at LLM provider layer (DB/config), not duplicated per subsystem.

Practical recommendation:
- In production, set `memory.embedding.provider/model` explicitly.
- Set `memory.retrieval.rerank_provider/model` explicitly when memory quality matters.
- Keep inheritance enabled only if your operations team wants auto-follow behavior.

## 6. Observability and API

Memory config API:
- `GET /api/v1/memories/config`
- `PUT /api/v1/memories/config` (admin only)

Response includes:
- configured values
- `effective` runtime values
- `sources` (where each effective field came from)

This is intended to avoid ambiguity in incident/debug scenarios.
