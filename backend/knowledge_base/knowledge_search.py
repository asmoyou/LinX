"""Hybrid knowledge search with Milvus vector + PostgreSQL BM25.

Combines semantic vector search (Milvus) with full-text BM25 search (PostgreSQL)
using Reciprocal Rank Fusion (RRF) for result merging.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from memory_system.embedding_service import get_embedding_service
from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config

logger = logging.getLogger(__name__)


@dataclass
class SearchFilter:
    """Filter for knowledge search."""

    user_id: str
    access_levels: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
    department_ids: Optional[List[str]] = None
    top_k: int = 10


@dataclass
class SearchResult:
    """Result of knowledge search."""

    chunk_id: str
    document_id: str
    content: str
    similarity_score: float
    chunk_index: int
    metadata: dict
    keywords: Optional[List[str]] = None
    summary: Optional[str] = None
    search_method: str = "hybrid"


class KnowledgeSearch:
    """Hybrid search combining vector similarity and BM25 full-text search."""

    def __init__(self):
        """Initialize knowledge search."""
        self.embedding_service = get_embedding_service()
        self.milvus_conn = get_milvus_connection()
        self.collection_name = "knowledge_embeddings"

        # Load search config
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}
        search_cfg = kb_config.get("search", {})

        self.enable_semantic = search_cfg.get("enable_semantic", True)
        self.enable_fulltext = search_cfg.get("enable_fulltext", True)
        self.semantic_weight = search_cfg.get("semantic_weight", 0.7)
        self.fulltext_weight = search_cfg.get("fulltext_weight", 0.3)
        self.fusion_method = search_cfg.get("fusion_method", "rrf")
        self.rrf_k = search_cfg.get("rrf_k", 60)

        logger.info(
            "KnowledgeSearch initialized (hybrid)",
            extra={
                "semantic": self.enable_semantic,
                "fulltext": self.enable_fulltext,
                "fusion": self.fusion_method,
            },
        )

    def search(
        self,
        query: str,
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Search knowledge base using hybrid vector + BM25 search.

        Args:
            query: Search query text
            search_filter: Filter criteria

        Returns:
            List of SearchResult ordered by relevance
        """
        try:
            vector_results = []
            bm25_results = []

            # Vector search via Milvus
            if self.enable_semantic:
                vector_results = self._vector_search(query, search_filter)

            # BM25 search via PostgreSQL
            if self.enable_fulltext:
                bm25_results = self._bm25_search(query, search_filter)

            # Merge results
            if vector_results and bm25_results:
                merged = self._rrf_merge(vector_results, bm25_results)
            elif vector_results:
                merged = vector_results
            elif bm25_results:
                merged = bm25_results
            else:
                merged = []

            # Apply permission filtering via access_control module
            filtered_results = self._apply_permission_filter(merged, search_filter)

            # Limit to top_k
            filtered_results = filtered_results[: search_filter.top_k]

            logger.info(
                "Hybrid knowledge search completed",
                extra={
                    "query_length": len(query),
                    "vector_hits": len(vector_results),
                    "bm25_hits": len(bm25_results),
                    "merged_results": len(filtered_results),
                },
            )

            return filtered_results

        except Exception as e:
            logger.error(f"Knowledge search failed: {e}", exc_info=True)
            raise

    def _vector_search(
        self,
        query: str,
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Perform vector similarity search via Milvus.

        Args:
            query: Search query
            search_filter: Filter criteria

        Returns:
            List of SearchResult from vector search
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_service.generate_embedding(query)

            # Build Milvus search expression
            expr_parts = [f'user_id == "{search_filter.user_id}"']

            if search_filter.document_ids:
                doc_ids_str = '", "'.join(search_filter.document_ids)
                expr_parts.append(f'document_id in ["{doc_ids_str}"]')

            expr = " && ".join(expr_parts)

            # Search in Milvus
            from pymilvus import Collection

            collection = Collection(self.collection_name)

            search_params = {"metric_type": "L2", "params": {"nprobe": 10}}
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=search_filter.top_k * 2,  # Fetch more for fusion
                expr=expr,
                output_fields=["document_id", "content", "chunk_index"],
            )

            # Convert to SearchResult objects
            search_results = []
            for hits in results:
                for hit in hits:
                    search_results.append(
                        SearchResult(
                            chunk_id=str(hit.id),
                            document_id=hit.entity.get("document_id"),
                            content=hit.entity.get("content"),
                            similarity_score=1.0
                            / (1.0 + hit.distance),  # Convert distance to similarity
                            chunk_index=hit.entity.get("chunk_index", 0),
                            metadata={},
                            search_method="vector",
                        )
                    )

            return search_results

        except Exception as e:
            logger.error(f"Vector search failed: {e}", exc_info=True)
            return []

    def _bm25_search(
        self,
        query: str,
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Perform BM25 full-text search via PostgreSQL tsvector.

        Args:
            query: Search query
            search_filter: Filter criteria

        Returns:
            List of SearchResult from BM25 search
        """
        try:
            from sqlalchemy import func, text

            from database.connection import get_db_session
            from database.models import KnowledgeChunk, KnowledgeItem

            with get_db_session() as session:
                # Build ts_query from search terms
                ts_query = func.plainto_tsquery("pg_catalog.simple", query)

                # Build query with join to knowledge_items for access filtering
                q = (
                    session.query(
                        KnowledgeChunk.chunk_id,
                        KnowledgeChunk.knowledge_id,
                        KnowledgeChunk.content,
                        KnowledgeChunk.chunk_index,
                        KnowledgeChunk.keywords,
                        KnowledgeChunk.summary,
                        KnowledgeChunk.chunk_metadata,
                        func.ts_rank(KnowledgeChunk.search_vector, ts_query).label("rank"),
                    )
                    .join(
                        KnowledgeItem,
                        KnowledgeItem.knowledge_id == KnowledgeChunk.knowledge_id,
                    )
                    .filter(KnowledgeChunk.search_vector.op("@@")(ts_query))
                    .filter(KnowledgeItem.owner_user_id == search_filter.user_id)
                )

                # Apply document filter
                if search_filter.document_ids:
                    q = q.filter(
                        KnowledgeChunk.knowledge_id.in_(search_filter.document_ids)
                    )

                # Apply department filter
                if search_filter.department_ids:
                    q = q.filter(
                        KnowledgeItem.department_id.in_(search_filter.department_ids)
                    )

                # Order by BM25 rank
                q = q.order_by(text("rank DESC")).limit(search_filter.top_k * 2)

                rows = q.all()

                # Convert to SearchResult
                search_results = []
                for row in rows:
                    search_results.append(
                        SearchResult(
                            chunk_id=str(row.chunk_id),
                            document_id=str(row.knowledge_id),
                            content=row.content,
                            similarity_score=float(row.rank),
                            chunk_index=row.chunk_index,
                            metadata=row.chunk_metadata or {},
                            keywords=row.keywords,
                            summary=row.summary,
                            search_method="bm25",
                        )
                    )

                return search_results

        except Exception as e:
            logger.error(f"BM25 search failed: {e}", exc_info=True)
            return []

    def _apply_permission_filter(
        self,
        results: List[SearchResult],
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Apply permission filtering to search results.

        Both Milvus and BM25 queries already filter by owner user_id.
        This provides additional access-level filtering for team/public items.

        Args:
            results: Search results to filter
            search_filter: Filter with user context

        Returns:
            Filtered list of SearchResult
        """
        try:
            from access_control.knowledge_filter import filter_knowledge_results
            from access_control.permissions import CurrentUser

            # Convert SearchResults to dicts for the filter function
            result_dicts = []
            for r in results:
                result_dicts.append({
                    "chunk_id": r.chunk_id,
                    "document_id": r.document_id,
                    "owner_user_id": search_filter.user_id,
                    "access_level": r.metadata.get("access_level", "private"),
                    "content": r.content,
                    "similarity_score": r.similarity_score,
                    "chunk_index": r.chunk_index,
                    "metadata": r.metadata,
                    "keywords": r.keywords,
                    "summary": r.summary,
                    "search_method": r.search_method,
                })

            current_user = CurrentUser(
                user_id=search_filter.user_id,
                role="user",
            )

            filtered_dicts = filter_knowledge_results(
                results=result_dicts,
                current_user=current_user,
            )

            # Convert back to SearchResult objects
            filtered_ids = {d["chunk_id"] for d in filtered_dicts}
            return [r for r in results if r.chunk_id in filtered_ids]

        except ImportError:
            logger.warning("access_control.knowledge_filter not available, skipping filter")
            return results
        except Exception as e:
            logger.warning(f"Permission filtering failed, returning unfiltered: {e}")
            return results

    def _rrf_merge(
        self,
        vector_results: List[SearchResult],
        bm25_results: List[SearchResult],
    ) -> List[SearchResult]:
        """Merge results using Reciprocal Rank Fusion.

        RRF score(d) = Σ weight / (k + rank) for each result list.

        Args:
            vector_results: Results from vector search
            bm25_results: Results from BM25 search

        Returns:
            Merged and re-ranked results
        """
        scores: Dict[str, float] = {}
        result_map: Dict[str, SearchResult] = {}

        # Score vector results
        for rank, result in enumerate(vector_results):
            key = result.chunk_id
            rrf_score = self.semantic_weight / (self.rrf_k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            if key not in result_map:
                result_map[key] = result

        # Score BM25 results
        for rank, result in enumerate(bm25_results):
            key = result.chunk_id
            rrf_score = self.fulltext_weight / (self.rrf_k + rank + 1)
            scores[key] = scores.get(key, 0.0) + rrf_score
            if key not in result_map:
                result_map[key] = result
            else:
                # Merge metadata: prefer BM25 keywords/summary
                existing = result_map[key]
                if result.keywords and not existing.keywords:
                    existing.keywords = result.keywords
                if result.summary and not existing.summary:
                    existing.summary = result.summary

        # Sort by RRF score
        sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)

        merged = []
        for key in sorted_keys:
            result = result_map[key]
            result.similarity_score = scores[key]
            result.search_method = "hybrid"
            merged.append(result)

        return merged


# Singleton instance
_knowledge_search: Optional[KnowledgeSearch] = None


def get_knowledge_search() -> KnowledgeSearch:
    """Get or create the knowledge search singleton.

    Returns:
        KnowledgeSearch instance
    """
    global _knowledge_search
    if _knowledge_search is None:
        _knowledge_search = KnowledgeSearch()
    return _knowledge_search
