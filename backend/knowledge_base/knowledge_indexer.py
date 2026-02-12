"""Knowledge indexing service for storing embeddings and chunks.

Dual indexing: Milvus (vector embeddings) + PostgreSQL (BM25 full-text search).

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
import uuid
from dataclasses import dataclass
from typing import List, Optional

from database.connection import get_db_session
from database.models import KnowledgeChunk, KnowledgeItem
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
        self.embedding_service = get_embedding_service(scope="knowledge_base")
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
        """Index document chunks with embeddings in Milvus and full-text in PostgreSQL.

        Args:
            document_id: Document identifier
            chunks: List of text chunks (may be enriched with keywords/questions)
            chunk_metadata: Metadata for each chunk
            user_id: User ID who owns the document
            access_level: Access level (private, team, public)

        Returns:
            IndexingResult with indexing details
        """
        import time

        start_time = time.time()

        try:
            if not chunks:
                logger.warning(
                    "Skip indexing because no chunks were produced",
                    extra={"document_id": document_id},
                )
                return IndexingResult(
                    document_id=document_id,
                    chunks_indexed=0,
                    embeddings_generated=0,
                    indexing_time=time.time() - start_time,
                )

            normalized_metadata = list(chunk_metadata or [])
            if len(normalized_metadata) != len(chunks):
                logger.warning(
                    "Chunk metadata length mismatch; normalizing metadata list",
                    extra={
                        "document_id": document_id,
                        "chunks": len(chunks),
                        "metadata": len(normalized_metadata),
                    },
                )
                if len(normalized_metadata) < len(chunks):
                    normalized_metadata.extend(
                        {"chunk_index": i} for i in range(len(normalized_metadata), len(chunks))
                    )
                else:
                    normalized_metadata = normalized_metadata[: len(chunks)]

            # Generate embeddings for all chunks
            embeddings = self.embedding_service.generate_embeddings_batch(chunks)

            # Prepare IDs for PostgreSQL chunks (Milvus uses auto_id)
            # Use uuid.UUID objects, not strings — SQLAlchemy UUID(as_uuid=True) needs exact type
            ids = [uuid.uuid4() for _ in chunks]

            # Insert into Milvus
            from pymilvus import Collection

            collection = Collection(self.collection_name)

            # Field order must match schema (excluding auto_id 'id'):
            # knowledge_id, chunk_index, embedding, content, owner_user_id, access_level, metadata
            entities = [
                [document_id] * len(chunks),
                [meta.get("chunk_index", i) for i, meta in enumerate(normalized_metadata)],
                embeddings,
                chunks,
                [user_id] * len(chunks),
                [access_level] * len(chunks),
                [meta for meta in normalized_metadata],
            ]

            collection.insert(entities)
            collection.flush()

            # Store chunks in PostgreSQL for BM25 search
            self._store_chunks_in_postgres(
                document_id=document_id,
                chunk_ids=ids,
                chunks=chunks,
                chunk_metadata=normalized_metadata,
            )

            indexing_time = time.time() - start_time

            logger.info(
                "Knowledge indexed (dual)",
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

    def _store_chunks_in_postgres(
        self,
        document_id: str,
        chunk_ids: list,
        chunks: List[str],
        chunk_metadata: List[dict],
    ) -> None:
        """Store chunks in PostgreSQL knowledge_chunks table for BM25 search.

        The search_vector column is auto-populated by a database trigger.

        Args:
            document_id: Document ID (FK to knowledge_items)
            chunk_ids: UUIDs for each chunk
            chunks: Chunk text content
            chunk_metadata: Metadata with keywords, questions, summary, etc.
        """
        try:
            from uuid import UUID as PyUUID

            # Ensure document_id is a proper UUID object
            doc_uuid = PyUUID(document_id) if isinstance(document_id, str) else document_id

            with get_db_session() as session:
                for i, (chunk_id, chunk, meta) in enumerate(zip(chunk_ids, chunks, chunk_metadata)):
                    knowledge_chunk = KnowledgeChunk(
                        chunk_id=chunk_id,
                        knowledge_id=doc_uuid,
                        chunk_index=meta.get("chunk_index", i),
                        content=chunk,
                        keywords=meta.get("keywords"),
                        questions=meta.get("questions"),
                        summary=meta.get("summary"),
                        token_count=meta.get("token_count"),
                        chunk_metadata=meta,
                    )
                    session.add(knowledge_chunk)
                session.commit()

            logger.debug(f"Stored {len(chunks)} chunks in PostgreSQL for document {document_id}")

        except Exception as e:
            logger.error(f"Failed to store chunks in PostgreSQL: {e}", exc_info=True)
            # Don't re-raise: Milvus indexing succeeded, BM25 is supplementary


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
