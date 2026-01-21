"""Document processor worker for background processing.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
import tempfile
import threading
from pathlib import Path
from typing import Optional

from knowledge_base.audio_processor import get_audio_processor
from knowledge_base.document_chunker import get_document_chunker
from knowledge_base.knowledge_indexer import get_knowledge_indexer
from knowledge_base.ocr_processor import get_ocr_processor
from knowledge_base.processing_queue import JobStatus, ProcessingQueue, get_processing_queue
from knowledge_base.text_extractors import get_extractor
from knowledge_base.video_processor import get_video_processor
from object_storage.minio_client import get_minio_client

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
        logger.info("DocumentProcessorWorker initialized")

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
            try:
                # Dequeue next job
                job = self.queue.dequeue(timeout=5)
                if not job:
                    continue

                logger.info(f"Processing job: {job.job_id}")
                self.queue.update_status(job.job_id, JobStatus.PROCESSING)

                # Process document
                self._process_document(job)

                self.queue.update_status(job.job_id, JobStatus.COMPLETED)
                logger.info(f"Job completed: {job.job_id}")

            except Exception as e:
                logger.error(f"Job processing failed: {e}", exc_info=True)
                if job:
                    self.queue.update_status(
                        job.job_id,
                        JobStatus.FAILED,
                        error_message=str(e),
                    )

    def _process_document(self, job) -> None:
        """Process a single document.

        Args:
            job: ProcessingJob to process
        """
        # Download file from MinIO
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            self.minio_client.download_file(
                bucket_name=job.bucket,
                object_name=job.file_key,
                file_path=str(temp_path),
            )

        try:
            # Extract text based on file type
            text = self._extract_text(temp_path, job.mime_type)

            # Chunk document
            chunk_result = self.chunker.chunk(
                text=text,
                document_id=job.document_id,
                metadata={"mime_type": job.mime_type},
            )

            # Index chunks
            self.indexer.index_chunks(
                document_id=job.document_id,
                chunks=chunk_result.chunks,
                chunk_metadata=chunk_result.chunk_metadata,
                user_id=job.user_id,
            )

        finally:
            # Clean up temp file
            temp_path.unlink()

    def _extract_text(self, file_path: Path, mime_type: str) -> str:
        """Extract text from file based on type.

        Args:
            file_path: Path to file
            mime_type: MIME type of file

        Returns:
            Extracted text
        """
        if "image" in mime_type:
            ocr_processor = get_ocr_processor()
            result = ocr_processor.process(file_path)
            return result.text
        elif "audio" in mime_type:
            audio_processor = get_audio_processor()
            result = audio_processor.transcribe(file_path)
            return result.text
        elif "video" in mime_type:
            video_processor = get_video_processor()
            result = video_processor.process(file_path)
            return result.transcription.text
        else:
            extractor = get_extractor(mime_type)
            result = extractor.extract(file_path)
            return result.text


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
