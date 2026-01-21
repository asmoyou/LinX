"""Knowledge indexing service for storing embeddings.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional

from database.connection import get_db_session
from database.models import KnowledgeItem
from memory_system.embedding_service import get_embedding_service
from memory_system.milvus_connection import get_milvus_connection

logger = logging.getLogger(__name__)


@dataclass
class IndexingResult:
    """Result of knowledge indexing."""

    document_id: str
    chunks_indexed: int
    embeddings_generated: int
    indexing_time: float


class KnowledgeIndexer:
    """Index document chunks in Milvus and PostgreSQL."""

    def __init__(self):
        """Initialize knowledge indexer."""
        self.embedding_service = get_embedding_service()
        self.milvus_conn = get_milvus_connection()
        self.collection_name = "knowledge_embeddings"
        logger.info("KnowledgeIndexer initialized")

    def index_chunks(
        self,
        document_id: str,
        chunks: List[str],
        chunk_metadata: List[dict],
        user_id: str,
        access_level: str = "private",
    ) -> IndexingResult:
        """Index document chunks with embeddings.

        Args:
            document_id: Document identifier
            chunks: List of text chunks
            chunk_metadata: Metadata for each chunk
            user_id: User ID who owns the document
            access_level: Access level (private, team, public)

        Returns:
            IndexingResult with indexing details
        """
        import time

        start_time = time.time()

        try:
            # Generate embeddings for all chunks
            embeddings = self.embedding_service.embed_batch(chunks)

            # Prepare data for Milvus
            ids = [str(uuid.uuid4()) for _ in chunks]

            # Insert into Milvus
            from pymilvus import Collection

            collection = Collection(self.collection_name)

            entities = [
                ids,
                embeddings,
                [document_id] * len(chunks),
                [user_id] * len(chunks),
                chunks,
                [meta.get("chunk_index", i) for i, meta in enumerate(chunk_metadata)],
            ]

            collection.insert(entities)
            collection.flush()

            # Store metadata in PostgreSQL
            with get_db_session() as session:
                for i, (chunk_id, chunk, meta) in enumerate(zip(ids, chunks, chunk_metadata)):
                    knowledge_item = KnowledgeItem(
                        id=chunk_id,
                        document_id=document_id,
                        user_id=user_id,
                        content=chunk,
                        chunk_index=meta.get("chunk_index", i),
                        access_level=access_level,
                        metadata=meta,
                    )
                    session.add(knowledge_item)
                session.commit()

            indexing_time = time.time() - start_time

            logger.info(
                "Knowledge indexed",
                extra={
                    "document_id": document_id,
                    "chunks": len(chunks),
                    "time": indexing_time,
                },
            )

            return IndexingResult(
                document_id=document_id,
                chunks_indexed=len(chunks),
                embeddings_generated=len(embeddings),
                indexing_time=indexing_time,
            )

        except Exception as e:
            logger.error(f"Knowledge indexing failed: {e}", exc_info=True)
            raise


# Singleton instance
_knowledge_indexer: Optional[KnowledgeIndexer] = None


def get_knowledge_indexer() -> KnowledgeIndexer:
    """Get or create the knowledge indexer singleton.

    Returns:
        KnowledgeIndexer instance
    """
    global _knowledge_indexer
    if _knowledge_indexer is None:
        _knowledge_indexer = KnowledgeIndexer()
    return _knowledge_indexer
