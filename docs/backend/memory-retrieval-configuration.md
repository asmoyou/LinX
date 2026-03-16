# User Memory Retrieval Configuration (Production)

## 1. Scope

This document describes the reset-era runtime path for:

- `user_memory_entries`
- `user_memory_views` (`profile` / `episode`)
- published skills that originated from approved `skill_proposals`

The reset architecture no longer uses a dedicated Milvus+rereank retrieval stack for user
memory. User-memory runtime recall is now PostgreSQL-backed and view-aware.

## 2. Runtime Retrieval Pipeline

At runtime, context assembly reads from three durable sources:

1. `user_memory`
2. `skills`
3. `knowledge_base`

`runtime_context.enable_user_memory`, `runtime_context.enable_skills`, and
`runtime_context.enable_knowledge_base` independently gate those sources.

When `user_memory` is enabled, the retriever:

1. queries `user_memory_views` for `profile` projections
2. queries `user_memory_views` for `episode` projections
3. queries `user_memory_entries` for atomic user facts
4. scores candidates with lexical / heuristic matching in PostgreSQL
5. applies `user_memory.retrieval.similarity_threshold`
6. merges and truncates the final context set

When `skills` is enabled, the runtime path reads published skills from the skill registry and
uses the published proposal only as provenance / summary source. It no longer treats learned
skills as a separate long-term memory view product.

## 3. What The Embedding Config Still Does

`user_memory.embedding.*` no longer drives a user-memory Milvus index or runtime vector recall.
User-memory runtime retrieval is PostgreSQL-only.

That config still exists because the codebase has a shared embedding-resolution surface keyed by
`user_memory`, and a few non-memory callers still reuse it for generic embedding generation (for
example semantic skill similarity helpers). It should be treated as a shared embedding client
configuration, not as a user-memory vector-search control surface.

Priority for `user_memory.embedding.provider/model/dimension`:

1. `user_memory.embedding.*`
2. if `user_memory.embedding.inherit_from_knowledge_base=true`, fallback to
   `knowledge_base.embedding.*`
3. fallback to `llm.embedding_provider` / `llm.default_provider`

The config API exposes:

- configured values
- `effective` resolved values
- `sources` for provider / model / dimension

## 4. Active User-Memory Knobs

These settings are still exposed in the current reset pipeline:

- `user_memory.embedding.provider`
- `user_memory.embedding.model`
- `user_memory.embedding.dimension`
- `user_memory.embedding.batch_size`
- `user_memory.embedding.inherit_from_knowledge_base`
- `user_memory.retrieval.similarity_threshold`
- `user_memory.extraction.provider`
- `user_memory.extraction.model`
- `user_memory.extraction.timeout_seconds`
- `user_memory.extraction.max_facts`
- `user_memory.extraction.max_preference_facts`
- `user_memory.extraction.enable_heuristic_fallback`
- `user_memory.extraction.secondary_recall_enabled`
- `user_memory.extraction.failure_backoff_seconds`
- `user_memory.consolidation.*`
- `session_ledger.*`
- `runtime_context.enable_*`

Skill-learning settings live under `skill_learning.extraction.*` and
`skill_learning.publish_policy.*`.

## 5. Removed User-Memory Knobs

These reset-era user-memory fields are no longer part of the supported config surface:

- `user_memory.retrieval.top_k`
- `user_memory.retrieval.strict_keyword_fallback`
- `user_memory.retrieval.enable_reranking`
- all `user_memory.retrieval.rerank_*`
- `user_memory.retrieval.similarity_weight`
- `user_memory.retrieval.recency_weight`
- `user_memory.retrieval.milvus.*`
- `user_memory.vector_cleanup.*`
- `skill_learning.proposal_review.*`
- `skill_learning.publish_policy.enabled`
- `runtime_context.collection_retry_attempts`
- `runtime_context.collection_retry_delay_seconds`
- `runtime_context.search_timeout_seconds`
- `runtime_context.delete_timeout_seconds`

If these keys still exist in an old config file, they are leftover migration residue and should
be removed.

## 6. API Surface

User-memory config API:

- `GET /api/v1/user-memory/config`
- `PUT /api/v1/user-memory/config` (admin only)

The response is intentionally canonicalized so the UI only shows the reset-era supported
configuration surface.
