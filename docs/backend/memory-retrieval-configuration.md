# User Memory Retrieval Configuration

## 1. Scope

This document describes the current reset-era user-memory retrieval stack for:

- `user_memory_entries`
- `user_memory_views`
- runtime context injection
- `/api/v1/user-memory*` query endpoints

User-memory now runs on a hybrid pipeline:

- PostgreSQL remains the source of truth for entries and views
- Milvus stores the user-memory vector index
- PostgreSQL FTS / trigram / structured filters provide lexical and symbolic retrieval
- the final ranking path uses hybrid fusion and reranking

## 2. Runtime Architecture

Write path:

1. `session ledger -> observations -> entries/views`
2. the same transaction enqueues embedding jobs in `user_memory_embedding_jobs`
3. the indexing worker writes entry/view embeddings into the active Milvus collection

Read path:

1. planner builds query variants, keyword terms, and structured filters
2. semantic retrieval queries Milvus
3. lexical retrieval queries PostgreSQL search indexes
4. structured retrieval filters PostgreSQL metadata fields
5. candidates are merged with reciprocal-rank fusion
6. reranking applies model rerank when configured, otherwise heuristic rerank
7. the final relevance gate applies `user_memory.retrieval.similarity_threshold`

Cleanup path:

- `backfill_user_memory_embeddings.py` builds the active collection
- `reconcile_user_memory_embeddings.py` checks missing/orphan vectors
- periodic vector cleanup runs reconcile + optional compaction

## 3. Planner Modes

Runtime and API share the same hybrid core but use different planner policies.

Runtime:

- `planner_mode=runtime_light`
- deterministic planning only
- no extra LLM call
- no reflection

API:

- `planner_mode=api_full`
- one optional LLM planning pass
- up to one reflection round when enabled and worthwhile
- `/api/v1/user-memory/profile` scopes retrieval to `view_type=user_profile`
- `/api/v1/user-memory/episodes` scopes retrieval to `view_type=episode` and supplements with `fact_kind=event` when needed

Wildcard queries (`""` or `"*"`) bypass the full hybrid path and return recent active rows from PostgreSQL.

## 4. Active Config Surface

Canonical user-memory retrieval config:

- `user_memory.embedding.*`
- `user_memory.retrieval.hybrid_enabled`
- `user_memory.retrieval.similarity_threshold`
- `user_memory.retrieval.vector.*`
- `user_memory.retrieval.lexical.*`
- `user_memory.retrieval.structured.*`
- `user_memory.retrieval.fusion.*`
- `user_memory.retrieval.rerank.*`
- `user_memory.retrieval.planner.*`
- `user_memory.retrieval.reflection.*`
- `user_memory.vector_indexing.*`
- `user_memory.vector_cleanup.*`
- `user_memory.extraction.*`
- `user_memory.consolidation.*`
- `session_ledger.*`
- `runtime_context.enable_*`

`GET /api/v1/user-memory/config` also returns:

- `user_memory.indexState.activeCollection`
- `user_memory.indexState.activeSignature`
- `user_memory.indexState.buildState`
- `user_memory.indexState.lastBackfillStartedAt`
- `user_memory.indexState.lastBackfillCompletedAt`
- `user_memory.indexState.lastReconcileAt`
- `user_memory.indexState.reindexRequired`

## 5. Removed Legacy Surface

The API no longer exposes these legacy retrieval keys:

- `user_memory.retrieval.legacy_fallback_enabled`
- `user_memory.retrieval.strict_keyword_fallback`
- flat rerank keys such as `user_memory.retrieval.rerank_provider`
- nested `user_memory.retrieval.milvus.*`

If these keys still exist in an older config file, the config endpoint canonicalizes them into the
new hybrid structure and omits the legacy names from responses.

## 6. Operational Scripts

Use these scripts for vector-index lifecycle management:

- `backend/scripts/bootstrap_user_memory_vector_index.py`
- `backend/scripts/backfill_user_memory_embeddings.py`
- `backend/scripts/reconcile_user_memory_embeddings.py`
- `backend/scripts/verify_user_memory_cutover.py`

Recommended cutover sequence:

1. bootstrap the active collection
2. backfill embeddings
3. run verify to compare hybrid retrieval against the recent-row baseline and inspect dry-run reconcile output
4. deploy the application
5. run reconcile daily during the first post-cutover week
