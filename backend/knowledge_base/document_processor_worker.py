"""Document processor worker for background processing.

Processes documents through the full pipeline: parse → chunk → enrich → index.
Writes processing status back to PostgreSQL KnowledgeItem.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

from knowledge_base.document_chunker import ChunkingStrategy, get_document_chunker
from knowledge_base.knowledge_indexer import get_knowledge_indexer
from knowledge_base.processing_queue import JobStatus, ProcessingQueue, get_processing_queue
from knowledge_base.text_extractors import get_extractor
from object_storage.minio_client import get_minio_client
from shared.config import get_config

logger = logging.getLogger(__name__)


class DocumentProcessorWorker:
    """Worker for processing documents in background."""

    def __init__(self):
        """Initialize document processor worker."""
        self.queue = get_processing_queue()
        self.minio_client = get_minio_client()
        self.chunker = get_document_chunker()
        self.indexer = get_knowledge_indexer()
        self.running = False
        self.worker_thread = None

        # Load config for pipeline settings
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}

        # Chunking config
        chunking_cfg = kb_config.get("chunking", {})
        strategy_str = chunking_cfg.get("strategy", "fixed_size")
        self.chunking_strategy = ChunkingStrategy(strategy_str)

        # Parsing config
        parsing_cfg = kb_config.get("parsing", {})
        self.parsing_method = parsing_cfg.get("method", "standard")

        # Enrichment config
        enrichment_cfg = kb_config.get("enrichment", {})
        self.enrichment_enabled = enrichment_cfg.get("enabled", False)

        logger.info(
            "DocumentProcessorWorker initialized",
            extra={
                "chunking_strategy": strategy_str,
                "parsing_method": self.parsing_method,
                "enrichment_enabled": self.enrichment_enabled,
            },
        )

    def start(self) -> None:
        """Start the worker thread."""
        if self.running:
            logger.warning("Worker already running")
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._process_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Worker started")

    def stop(self) -> None:
        """Stop the worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=10)
        logger.info("Worker stopped")

    def _process_loop(self) -> None:
        """Main processing loop."""
        while self.running:
            job = None
            try:
                # Dequeue next job
                job = self.queue.dequeue(timeout=5)
                if not job:
                    continue

                logger.info(f"Processing job: {job.job_id}")
                self.queue.update_status(job.job_id, JobStatus.PROCESSING)

                # Update KnowledgeItem status to processing
                self._update_knowledge_status(
                    job.document_id,
                    "processing",
                )

                # Process document
                result_meta = self._process_document(job)

                self.queue.update_status(job.job_id, JobStatus.COMPLETED)

                # Update KnowledgeItem status to completed
                self._update_knowledge_status(
                    job.document_id,
                    "completed",
                    chunk_count=result_meta.get("chunk_count", 0),
                    token_count=result_meta.get("total_tokens", 0),
                )

                logger.info(f"Job completed: {job.job_id}")

            except Exception as e:
                logger.error(f"Job processing failed: {e}", exc_info=True)
                if job:
                    self.queue.update_status(
                        job.job_id,
                        JobStatus.FAILED,
                        error_message=str(e),
                    )
                    # Update KnowledgeItem status to failed
                    self._update_knowledge_status(
                        job.document_id,
                        "failed",
                        error_message=str(e),
                    )

    def _process_document(self, job) -> dict:
        """Process a single document through the full pipeline.

        Args:
            job: ProcessingJob to process

        Returns:
            Dict with processing metadata (chunk_count, total_tokens, etc.)
        """
        # Download file from MinIO to temp file
        # download_file returns (data_stream, metadata), not a file path
        data_stream, _file_meta = self.minio_client.download_file(
            bucket_name=job.bucket,
            object_key=job.file_key,
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=self._get_suffix(job.mime_type)) as f:
            f.write(data_stream.read())
            temp_path = Path(f.name)

        try:
            # Step 1: Parse / extract text
            text = self._extract_text(temp_path, job.mime_type)

            # Step 2: Chunk document
            chunk_result = self.chunker.chunk(
                text=text,
                document_id=job.document_id,
                strategy=self.chunking_strategy,
                metadata={"mime_type": job.mime_type},
            )

            chunks = chunk_result.chunks
            chunk_metadata = chunk_result.chunk_metadata

            # Step 3: LLM enrichment (if enabled)
            if self.enrichment_enabled and chunks:
                try:
                    from knowledge_base.chunk_enricher import get_chunk_enricher

                    enricher = get_chunk_enricher()
                    chunks, chunk_metadata = enricher.enrich_batch_sync(chunks, chunk_metadata)
                except Exception as enrich_err:
                    logger.warning(f"Enrichment failed, continuing without: {enrich_err}")

            # Step 4: Index chunks to Milvus + PostgreSQL
            self.indexer.index_chunks(
                document_id=job.document_id,
                chunks=chunks,
                chunk_metadata=chunk_metadata,
                user_id=job.user_id,
            )

            return {
                "chunk_count": chunk_result.chunk_count,
                "total_tokens": chunk_result.total_tokens,
            }

        finally:
            # Clean up temp file
            temp_path.unlink(missing_ok=True)

    def _extract_text(self, file_path: Path, mime_type: str) -> str:
        """Extract text from file based on type and parsing method.

        Args:
            file_path: Path to file
            mime_type: MIME type of file

        Returns:
            Extracted text
        """
        # Vision parsing for images or when explicitly configured
        if self.parsing_method == "vision" or (
            self.parsing_method == "auto" and "image" in mime_type
        ):
            try:
                from knowledge_base.vision_parser import get_vision_parser

                parser = get_vision_parser()
                # Run async parser in sync context
                import asyncio

                loop = asyncio.new_event_loop()
                try:
                    if "image" in mime_type:
                        result = loop.run_until_complete(parser.parse_image(file_path))
                    else:
                        result = loop.run_until_complete(parser.parse_pdf(file_path))
                    return result.text
                finally:
                    loop.close()
            except Exception as vision_err:
                if self.parsing_method == "vision":
                    raise
                logger.warning(f"Vision parsing failed, falling back to standard: {vision_err}")

        # Standard extraction
        if "image" in mime_type:
            from knowledge_base.ocr_processor import get_ocr_processor

            ocr_processor = get_ocr_processor()
            result = ocr_processor.process(file_path)
            return result.text
        elif "audio" in mime_type:
            from knowledge_base.audio_processor import get_audio_processor

            audio_processor = get_audio_processor()
            result = audio_processor.transcribe(file_path)
            return result.text
        elif "video" in mime_type:
            from knowledge_base.video_processor import get_video_processor

            video_processor = get_video_processor()
            result = video_processor.process(file_path)
            return result.transcription.text
        else:
            extractor = get_extractor(mime_type)
            result = extractor.extract(file_path)

            # Auto mode: if extracted text is sparse, try vision for PDFs
            if (
                self.parsing_method == "auto"
                and "pdf" in mime_type
                and len(result.text.strip()) < 100
            ):
                try:
                    from knowledge_base.vision_parser import get_vision_parser

                    parser = get_vision_parser()
                    import asyncio

                    loop = asyncio.new_event_loop()
                    try:
                        vision_result = loop.run_until_complete(parser.parse_pdf(file_path))
                        if len(vision_result.text.strip()) > len(result.text.strip()):
                            return vision_result.text
                    finally:
                        loop.close()
                except Exception:
                    pass  # Fall through to standard result

            return result.text

    def _update_knowledge_status(
        self,
        document_id: str,
        status: str,
        chunk_count: int = 0,
        token_count: int = 0,
        error_message: str = "",
    ) -> None:
        """Update KnowledgeItem processing status in PostgreSQL.

        Args:
            document_id: Knowledge item ID
            status: Processing status (processing, completed, failed)
            chunk_count: Number of chunks produced
            token_count: Total token count
            error_message: Error message if failed
        """
        try:
            from database.connection import get_db_session
            from database.models import KnowledgeItem

            with get_db_session() as session:
                item = (
                    session.query(KnowledgeItem)
                    .filter(KnowledgeItem.knowledge_id == document_id)
                    .first()
                )
                if item:
                    meta = dict(item.item_metadata) if item.item_metadata else {}
                    meta["processing_status"] = status
                    meta["processed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

                    if status == "completed":
                        meta["chunk_count"] = chunk_count
                        meta["token_count"] = token_count
                    elif status == "failed":
                        meta["error_message"] = error_message

                    item.item_metadata = meta
                    session.commit()
                    logger.debug(
                        f"Knowledge item {document_id} status updated to {status}"
                    )
                else:
                    logger.warning(
                        f"Knowledge item {document_id} not found for status update"
                    )
        except Exception as e:
            logger.error(f"Failed to update knowledge status: {e}", exc_info=True)

    @staticmethod
    def _get_suffix(mime_type: str) -> str:
        """Get file suffix from MIME type.

        Args:
            mime_type: MIME type string

        Returns:
            File suffix with dot prefix
        """
        mime_to_suffix = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/html": ".html",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "video/mp4": ".mp4",
        }
        return mime_to_suffix.get(mime_type, "")


# Singleton instance
_processor_worker: Optional[DocumentProcessorWorker] = None


def get_processor_worker() -> DocumentProcessorWorker:
    """Get or create the processor worker singleton.

    Returns:
        DocumentProcessorWorker instance
    """
    global _processor_worker
    if _processor_worker is None:
        _processor_worker = DocumentProcessorWorker()
    return _processor_worker


def start_worker() -> None:
    """Start the document processor worker."""
    worker = get_processor_worker()
    worker.start()


def stop_worker() -> None:
    """Stop the document processor worker."""
    worker = get_processor_worker()
    worker.stop()
