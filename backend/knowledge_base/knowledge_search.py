"""Knowledge search with permission filtering.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from memory_system.embedding_service import get_embedding_service
from memory_system.milvus_connection import get_milvus_connection
from access_control.knowledge_filter import KnowledgeFilter, get_knowledge_filter

logger = logging.getLogger(__name__)


@dataclass
class SearchFilter:
    """Filter for knowledge search."""
    
    user_id: str
    access_levels: Optional[List[str]] = None
    document_ids: Optional[List[str]] = None
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


class KnowledgeSearch:
    """Search knowledge base with permission filtering."""
    
    def __init__(self):
        """Initialize knowledge search."""
        self.embedding_service = get_embedding_service()
        self.milvus_conn = get_milvus_connection()
        self.knowledge_filter = get_knowledge_filter()
        self.collection_name = "knowledge_embeddings"
        logger.info("KnowledgeSearch initialized")
    
    def search(
        self,
        query: str,
        search_filter: SearchFilter,
    ) -> List[SearchResult]:
        """Search knowledge base with semantic similarity.
        
        Args:
            query: Search query text
            search_filter: Filter criteria
            
        Returns:
            List of SearchResult ordered by relevance
        """
        try:
            # Generate query embedding
            query_embedding = self.embedding_service.embed(query)
            
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
                limit=search_filter.top_k,
                expr=expr,
                output_fields=["document_id", "content", "chunk_index"],
            )
            
            # Convert to SearchResult objects
            search_results = []
            for hits in results:
                for hit in hits:
                    search_results.append(SearchResult(
                        chunk_id=str(hit.id),
                        document_id=hit.entity.get('document_id'),
                        content=hit.entity.get('content'),
                        similarity_score=1.0 / (1.0 + hit.distance),  # Convert distance to similarity
                        chunk_index=hit.entity.get('chunk_index', 0),
                        metadata={},
                    ))
            
            # Apply permission filtering
            filtered_results = self.knowledge_filter.filter_results(
                search_results,
                search_filter.user_id,
            )
            
            logger.info(
                "Knowledge search completed",
                extra={
                    "query_length": len(query),
                    "results": len(filtered_results),
                }
            )
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Knowledge search failed: {e}", exc_info=True)
            raise


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
