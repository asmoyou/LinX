"""Knowledge indexing service for storing embeddings and chunks.

Dual indexing: Milvus (vector embeddings) + PostgreSQL (BM25 full-text search).

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional

from pymilvus import MilvusException

from database.connection import get_db_session
from database.models import KnowledgeChunk, KnowledgeItem
from knowledge_base.text_normalizer import normalize_knowledge_text
from memory_system.embedding_service import get_embedding_service
from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config

logger = logging.getLogger(__name__)


class AwaitableIndexingResult(dict):
    """Dict wrapper that can also be awaited in compatibility paths."""

    def __await__(self):
        async def _resolve():
            return self

        return _resolve().__await__()


@dataclass
class IndexingResult:
    """Result of knowledge indexing."""

    document_id: str
    chunks_indexed: int
    embeddings_generated: int
    indexing_time: float

    def __await__(self):
        async def _resolve():
            return self

        return _resolve().__await__()


class KnowledgeIndexer:
    """Index document chunks in Milvus and PostgreSQL."""

    def __init__(self):
        """Initialize knowledge indexer."""
        self.embedding_service = get_embedding_service(scope="knowledge_base")
        self.milvus_conn = get_milvus_connection()
        self.collection_name = "knowledge_embeddings"
        config = get_config()
        self._milvus_flush_timeout_seconds = float(
            config.get("knowledge_base.processing.indexing.flush_timeout_seconds", 8.0)
        )
        self._milvus_retry_backoff_seconds = float(
            config.get("knowledge_base.processing.indexing.retry_backoff_seconds", 1.0)
        )
        self._milvus_max_retries = max(
            0,
            int(config.get("knowledge_base.processing.indexing.milvus_max_retries", 2)),
        )
        self._milvus_allow_flush_degrade = bool(
            config.get("knowledge_base.processing.indexing.allow_flush_degrade", True)
        )
        logger.info(
            "KnowledgeIndexer initialized",
            extra={
                "milvus_flush_timeout_seconds": self._milvus_flush_timeout_seconds,
                "milvus_retry_backoff_seconds": self._milvus_retry_backoff_seconds,
                "milvus_max_retries": self._milvus_max_retries,
                "milvus_allow_flush_degrade": self._milvus_allow_flush_degrade,
            },
        )

    def index_chunks(
        self,
        document_id: str,
        chunks: List[str],
        chunk_metadata: Optional[List[dict]] = None,
        user_id: Optional[str] = None,
        access_level: str = "private",
    ):
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
        start_time = time.time()

        try:
            if chunk_metadata is None or user_id is None:
                single_embed = getattr(self.embedding_service, "generate_embedding", None)
                if callable(single_embed):
                    for chunk in chunks:
                        single_embed(chunk)
                else:
                    self.embedding_service.generate_embeddings_batch(chunks)
                return AwaitableIndexingResult(
                    {
                        "success": True,
                        "indexed_count": len(chunks),
                        "knowledge_id": str(document_id),
                    }
                )

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

            prepared_chunks = [
                normalize_knowledge_text(chunk) or str(chunk or "") for chunk in chunks
            ]
            prepared_metadata = [
                self._sanitize_chunk_metadata(meta) for meta in normalized_metadata
            ]

            # Generate embeddings for all chunks
            embeddings = self.embedding_service.generate_embeddings_batch(prepared_chunks)

            # Prepare IDs for PostgreSQL chunks (Milvus uses auto_id)
            # Use uuid.UUID objects, not strings — SQLAlchemy UUID(as_uuid=True) needs exact type
            ids = [uuid.uuid4() for _ in chunks]

            # Field order must match schema (excluding auto_id 'id'):
            # knowledge_id, chunk_index, embedding, content, owner_user_id, access_level, metadata
            entities = [
                [document_id] * len(chunks),
                [meta.get("chunk_index", i) for i, meta in enumerate(prepared_metadata)],
                embeddings,
                prepared_chunks,
                [user_id] * len(chunks),
                [access_level] * len(chunks),
                [meta for meta in prepared_metadata],
            ]

            self._insert_and_flush_with_retry(document_id=document_id, entities=entities)

            # Store chunks in PostgreSQL for BM25 search
            self._store_chunks_in_postgres(
                document_id=document_id,
                chunk_ids=ids,
                chunks=prepared_chunks,
                chunk_metadata=prepared_metadata,
            )

            indexing_time = time.time() - start_time

            logger.info(
                "Knowledge indexed (dual)",
                extra={
                    "document_id": document_id,
                    "chunks": len(prepared_chunks),
                    "time": indexing_time,
                },
            )

            return IndexingResult(
                document_id=document_id,
                chunks_indexed=len(prepared_chunks),
                embeddings_generated=len(embeddings),
                indexing_time=indexing_time,
            )

        except Exception as e:
            logger.error(f"Knowledge indexing failed: {e}", exc_info=True)
            raise

    @staticmethod
    def _sanitize_chunk_metadata(meta: Optional[dict]) -> dict:
        normalized = dict(meta or {})
        summary = normalize_knowledge_text(normalized.get("summary"))
        if summary:
            normalized["summary"] = summary
        elif "summary" in normalized:
            normalized.pop("summary", None)

        keywords = normalized.get("keywords")
        if isinstance(keywords, list):
            cleaned_keywords = []
            for keyword in keywords:
                cleaned = normalize_knowledge_text(keyword)
                if cleaned and cleaned not in cleaned_keywords:
                    cleaned_keywords.append(cleaned)
            if cleaned_keywords:
                normalized["keywords"] = cleaned_keywords
            else:
                normalized.pop("keywords", None)

        questions = normalized.get("questions")
        if isinstance(questions, list):
            cleaned_questions = []
            for question in questions:
                cleaned = normalize_knowledge_text(question)
                if cleaned and cleaned not in cleaned_questions:
                    cleaned_questions.append(cleaned)
            if cleaned_questions:
                normalized["questions"] = cleaned_questions
            else:
                normalized.pop("questions", None)

        return normalized

    def _insert_and_flush_with_retry(self, document_id: str, entities: List[list]) -> None:
        """Insert vectors and flush Milvus with retry/reconnect on transient failures."""
        inserted = False
        max_attempts = self._milvus_max_retries + 1
        last_error: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                collection = self.milvus_conn.get_collection(
                    self.collection_name,
                    force_refresh=attempt > 1,
                )

                if not inserted:
                    collection.insert(entities)
                    inserted = True

                collection.flush(timeout=self._milvus_flush_timeout_seconds)
                if attempt > 1:
                    logger.info(
                        "Milvus indexing recovered after retry",
                        extra={
                            "document_id": document_id,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                        },
                    )
                return

            except Exception as exc:
                last_error = exc
                retryable = self._is_retryable_milvus_error(exc)
                should_retry = retryable and attempt < max_attempts

                log_extra = {
                    "document_id": document_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "inserted": inserted,
                    "error": str(exc),
                }

                if should_retry:
                    logger.warning(
                        "Milvus insert/flush failed with retryable error, reconnecting and retrying",
                        extra=log_extra,
                    )
                    self._recover_milvus_connection()
                    backoff_seconds = self._milvus_retry_backoff_seconds * (2 ** (attempt - 1))
                    if backoff_seconds > 0:
                        time.sleep(backoff_seconds)
                    continue

                logger.error(
                    "Milvus insert/flush failed",
                    extra=log_extra,
                    exc_info=True,
                )
                break

        if last_error is not None:
            if (
                inserted
                and self._milvus_allow_flush_degrade
                and self._is_retryable_milvus_error(last_error)
            ):
                logger.error(
                    "Milvus flush remained unavailable after retries; continuing without flush",
                    extra={"document_id": document_id, "error": str(last_error)},
                )
                return
            raise last_error

    def _recover_milvus_connection(self) -> None:
        """Best-effort reconnect for transient Milvus channel/connection failures."""
        try:
            self.milvus_conn.reconnect()
        except Exception as reconnect_error:
            logger.warning(
                "Milvus reconnect failed, retry will continue with refreshed collection handle: "
                f"{reconnect_error}"
            )
            self.milvus_conn.invalidate_collection_handle(self.collection_name)

    @staticmethod
    def _is_retryable_milvus_error(error: Exception) -> bool:
        """Return True for transient Milvus errors worth retrying."""
        retryable_markers = (
            "channel not found",
            "deadline exceeded",
            "timed out",
            "timeout",
            "connection refused",
            "connection reset",
            "broken pipe",
            "service unavailable",
            "temporarily unavailable",
        )
        message = str(error).lower()
        if any(marker in message for marker in retryable_markers):
            return True

        return isinstance(error, (TimeoutError, ConnectionError))

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
