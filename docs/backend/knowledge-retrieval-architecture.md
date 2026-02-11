# Knowledge Retrieval Architecture (RAGFlow-Inspired)

## Goal
Build a stable retrieval foundation for agent runtime use:
- high recall for semantically similar questions
- low irrelevant-hit rate
- predictable latency under embedding/rerank degradation

## Current Baseline in LinX
- Hybrid retrieval: Milvus vector + PostgreSQL BM25 + RRF fusion.
- Query-term overlap rerank and configurable relevance threshold.
- Lexical fallback when BM25 under-retrieves.

## Key Lessons from RAGFlow
- Query analysis is a first-class stage (token expansion, synonym/fine-grained keywords).
- Retrieval uses a large candidate pool, then reranks and applies `similarity_threshold`.
- Threshold is applied after rerank, not before.
- Retrieval output includes stable chunk metadata for downstream prompt assembly and citation.

Reference:
- `examples-of-reference/ragflow/rag/nlp/search.py`
- `examples-of-reference/ragflow/rag/nlp/query.py`

## Target Pipeline for LinX
1. Query analysis
- Extract normalized terms + language-aware tokens.
- Optional query rewrite and synonym expansion.

2. Multi-channel recall
- Vector recall (Milvus).
- Full-text/BM25 recall (PostgreSQL).
- Keyword fallback recall (for timeout/degraded cases).

3. Candidate fusion
- RRF for mixed channels.
- Keep source score and retrieval method in metadata.

4. Rerank
- Prefer model-based rerank when configured.
- Fallback to lexical+vector heuristic rerank when reranker unavailable.

5. Relevance gate
- Apply configurable `min_relevance_score`.
- Keep channel-specific guards for noisy fallback channels.

6. Agent context assembly
- Return top-k chunks + citations + retrieval traces.
- Support token-budget-aware context packing.

## Agent Integration Contract
Expose a retrieval contract suitable for agent framework calls:
- input: query, scope filters, top_k, min_score, latency budget
- output: chunks, scores, document metadata, retrieval traces
- behavior: graceful degradation when embeddings/reranker timeout

## Next Implementation Steps
1. Add model-based rerank execution for `knowledge_base.search.rerank_*`.
2. Add retrieval traces in API response for observability.
3. Add offline eval set and NDCG/Recall@k regression checks.
4. Integrate retrieval contract into agent knowledge toolchain.
