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
from datetime import datetime, timezone
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

        self.chunking_strategy = ChunkingStrategy.FIXED_SIZE
        self.parsing_method = "standard"
        self.enrichment_enabled = False
        self._load_runtime_config()

        logger.info(
            "DocumentProcessorWorker initialized",
            extra={
                "chunking_strategy": self.chunking_strategy.value,
                "parsing_method": self.parsing_method,
                "enrichment_enabled": self.enrichment_enabled,
            },
        )

    def _load_runtime_config(self) -> None:
        """Refresh runtime configuration for each document process."""
        config = get_config()
        kb_config = config.get_section("knowledge_base") if config else {}

        chunking_cfg = kb_config.get("chunking", {})
        strategy_str = chunking_cfg.get("strategy", ChunkingStrategy.FIXED_SIZE.value)
        try:
            self.chunking_strategy = ChunkingStrategy(strategy_str)
        except ValueError:
            logger.warning(f"Unknown chunking strategy '{strategy_str}', fallback to fixed_size")
            self.chunking_strategy = ChunkingStrategy.FIXED_SIZE

        parsing_cfg = kb_config.get("parsing", {})
        self.parsing_method = parsing_cfg.get("method", "standard")

        enrichment_cfg = kb_config.get("enrichment", {})
        self.enrichment_enabled = bool(enrichment_cfg.get("enabled", False))

        # Chunker auto-refreshes internally when config signature changes.
        self.chunker = get_document_chunker()

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
                    progress=5,
                    stage="queued",
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
                    progress=100,
                    stage="completed",
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
                        progress=100,
                        stage="failed",
                    )

    def _process_document(self, job) -> dict:
        """Process a single document through the full pipeline.

        Args:
            job: ProcessingJob to process

        Returns:
            Dict with processing metadata (chunk_count, total_tokens, etc.)
        """
        # Refresh config before each job so Settings updates take effect without restart.
        self._load_runtime_config()

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
            self._update_processing_progress(job.document_id, progress=15, stage="extracting")

            # Step 1: Parse / extract text
            text = self._extract_text(temp_path, job.mime_type)
            if not text or not text.strip():
                raise ValueError(
                    "No extractable text was found in the document. "
                    "Please check parsing method and model configuration."
                )
            self._update_processing_progress(job.document_id, progress=40, stage="parsed")

            # Step 2: Chunk document
            chunk_result = self.chunker.chunk(
                text=text,
                document_id=job.document_id,
                strategy=self.chunking_strategy,
                metadata={"mime_type": job.mime_type},
            )

            chunks = chunk_result.chunks
            chunk_metadata = chunk_result.chunk_metadata
            if not chunks:
                raise ValueError(
                    "Document parsing produced no chunks. "
                    "Please adjust parsing/chunking settings and retry."
                )
            self._update_processing_progress(job.document_id, progress=65, stage="chunked")

            # Step 3: LLM enrichment (if enabled)
            # For image/video content, enrichment adds noticeable latency with limited recall gain.
            skip_enrichment_for_media = job.mime_type.startswith(
                "image/"
            ) or job.mime_type.startswith("video/")
            if self.enrichment_enabled and chunks and not skip_enrichment_for_media:
                try:
                    from knowledge_base.chunk_enricher import get_chunk_enricher

                    enricher = get_chunk_enricher()
                    chunks, chunk_metadata = enricher.enrich_batch_sync(chunks, chunk_metadata)
                except Exception as enrich_err:
                    logger.warning(f"Enrichment failed, continuing without: {enrich_err}")
            elif self.enrichment_enabled and skip_enrichment_for_media:
                logger.info(
                    "Skipping chunk enrichment for media document",
                    extra={"document_id": job.document_id, "mime_type": job.mime_type},
                )

            # Step 4: Index chunks to Milvus + PostgreSQL
            self._update_processing_progress(job.document_id, progress=85, stage="indexing")
            self.indexer.index_chunks(
                document_id=job.document_id,
                chunks=chunks,
                chunk_metadata=chunk_metadata,
                user_id=job.user_id,
            )
            self._update_processing_progress(job.document_id, progress=95, stage="indexed")

            return {
                "chunk_count": chunk_result.chunk_count,
                "total_tokens": chunk_result.total_tokens,
            }

        finally:
            # Clean up temp file
            temp_path.unlink(missing_ok=True)

    @staticmethod
    def _run_async(coro):
        """Run async parser helpers in the worker's sync context."""
        import asyncio

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def _extract_text(self, file_path: Path, mime_type: str) -> str:
        """Extract text from file based on type and parsing method.

        Args:
            file_path: Path to file
            mime_type: MIME type of file

        Returns:
            Extracted text
        """
        normalized_mime_type = (mime_type or "").split(";", 1)[0].strip().lower()
        if normalized_mime_type in {"", "application/octet-stream", "binary/octet-stream"}:
            suffix_to_mime = {
                ".pdf": "application/pdf",
                ".doc": "application/msword",
                ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".txt": "text/plain",
                ".md": "text/markdown",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".mp3": "audio/mpeg",
                ".wav": "audio/wav",
                ".m4a": "audio/mp4",
                ".flac": "audio/flac",
                ".mp4": "video/mp4",
                ".avi": "video/x-msvideo",
                ".mov": "video/quicktime",
                ".mkv": "video/x-matroska",
            }
            normalized_mime_type = suffix_to_mime.get(
                file_path.suffix.lower(), normalized_mime_type
            )

        effective_type = normalized_mime_type or mime_type
        strict_vision_mode = self.parsing_method == "vision"

        # Vision parsing for images/PDFs when explicitly configured, and for images in auto mode.
        should_try_vision = ("image" in effective_type) or ("pdf" in effective_type)
        if should_try_vision and (
            strict_vision_mode or (self.parsing_method == "auto" and "image" in effective_type)
        ):
            try:
                from knowledge_base.vision_parser import get_vision_parser

                parser = get_vision_parser()
                if "image" in effective_type:
                    result = self._run_async(parser.parse_image(file_path))
                else:
                    result = self._run_async(parser.parse_pdf(file_path))

                vision_text = (result.text or "").strip()
                if vision_text:
                    return vision_text
                if strict_vision_mode:
                    raise ValueError("Vision parsing returned empty text in vision mode")
                logger.warning(
                    "Vision parsing returned empty text, falling back to standard parser",
                    extra={"file_path": str(file_path), "mime_type": effective_type},
                )
            except Exception as vision_err:
                if strict_vision_mode:
                    raise ValueError(
                        f"Vision parsing failed in vision mode: {vision_err}"
                    ) from vision_err
                logger.warning(f"Vision parsing failed, falling back to standard: {vision_err}")

        # Standard extraction
        if "image" in effective_type:
            from knowledge_base.ocr_processor import get_ocr_processor

            ocr_processor = get_ocr_processor()
            result = ocr_processor.process(file_path)
            return result.text
        elif "audio" in effective_type:
            from knowledge_base.audio_processor import get_audio_processor

            audio_processor = get_audio_processor()
            result = audio_processor.transcribe(file_path)
            return result.text
        elif "video" in effective_type:
            errors = []
            audio_text = ""
            vision_text = ""

            # 1) Audio transcription pipeline.
            try:
                from knowledge_base.video_processor import get_video_processor

                video_processor = get_video_processor()
                result = video_processor.process(file_path)
                audio_text = (result.transcription.text or "").strip()
                if not audio_text:
                    errors.append("audio transcription returned empty text")
            except Exception as video_err:
                errors.append(f"audio transcription failed: {video_err}")

            # 2) Vision frame parsing pipeline.
            try:
                vision_text = self._extract_video_with_vision(file_path).strip()
                if not vision_text:
                    errors.append("vision frame parsing returned empty text")
            except Exception as vision_err:
                errors.append(f"vision frame parsing failed: {vision_err}")

            # For videos we prefer multimodal indexing: keep both audio and visual signals.
            if audio_text and vision_text:
                return f"Audio Transcript:\n{audio_text}\n\n" f"Visual Analysis:\n{vision_text}"
            if audio_text:
                return audio_text
            if vision_text:
                return vision_text

            logger.warning(
                "Video extraction degraded to metadata fallback text",
                extra={
                    "file_path": str(file_path),
                    "errors": errors,
                },
            )
            return self._build_video_fallback_text(file_path, errors)
        else:
            extractor = get_extractor(effective_type)
            result = extractor.extract(file_path)

            # Auto mode: if extracted text is sparse, try vision for PDFs
            if (
                self.parsing_method == "auto"
                and "pdf" in effective_type
                and len(result.text.strip()) < 100
            ):
                try:
                    from knowledge_base.vision_parser import get_vision_parser

                    parser = get_vision_parser()
                    vision_result = self._run_async(parser.parse_pdf(file_path))
                    if len(vision_result.text.strip()) > len(result.text.strip()):
                        return vision_result.text
                except Exception:
                    pass  # Fall through to standard result

            return result.text

    def _extract_video_with_vision(self, file_path: Path) -> str:
        """Fallback extraction for videos using sampled frames and vision model."""
        import shutil
        import subprocess
        from tempfile import TemporaryDirectory

        from knowledge_base.vision_parser import get_vision_parser

        ffmpeg_bin = shutil.which("ffmpeg")
        if not ffmpeg_bin:
            raise RuntimeError("ffmpeg is not available for video frame extraction")

        with TemporaryDirectory(prefix="kb_video_frames_") as frame_dir:
            frame_pattern = str(Path(frame_dir) / "frame_%03d.jpg")
            command = [
                ffmpeg_bin,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(file_path),
                "-vf",
                "fps=1,scale=720:480",
                frame_pattern,
            ]
            subprocess.run(command, check=True)

            frames = sorted(Path(frame_dir).glob("frame_*.jpg"))
            if not frames:
                raise RuntimeError("no video frames were extracted")

            parser = get_vision_parser()
            frame_prompt = (
                "This image is a frame sampled from a video. "
                "Primary output language must be zh-CN. "
                "Extract visible text and summarize key scene actions/objects "
                "that are useful for semantic retrieval. "
                "Keep key source-language labels in parentheses."
            )

            # Group one frame per second into 15-second request batches.
            batch_size = 15
            batch_texts = []
            for start in range(0, len(frames), batch_size):
                batch_frames = frames[start : start + batch_size]
                parsed = self._run_async(parser.parse_images(batch_frames, prompt=frame_prompt))
                content = (parsed.text or "").strip()
                if content:
                    end = start + len(batch_frames) - 1
                    batch_texts.append(f"Segment {start:04d}s-{end:04d}s:\n{content}")

            if not batch_texts:
                return ""

            summary = self._run_async(parser.summarize_video_batches(batch_texts)).strip()
            if not summary:
                return "\n\n".join(batch_texts)

            return f"Video Summary:\n{summary}\n\n" f"Segment Details:\n{'\n\n'.join(batch_texts)}"

    @staticmethod
    def _build_video_fallback_text(file_path: Path, errors: list[str]) -> str:
        """Build fallback text so videos without extractable content still index."""
        error_summary = "; ".join(errors[:2]) if errors else "no details"
        return (
            f"Video file '{file_path.name}' was processed, but no transcribable audio or "
            f"readable frame text was detected. Fallback reason: {error_summary}."
        )

    def _update_knowledge_status(
        self,
        document_id: str,
        status: str,
        chunk_count: int = 0,
        token_count: int = 0,
        error_message: str = "",
        progress: Optional[int] = None,
        stage: Optional[str] = None,
    ) -> None:
        """Update KnowledgeItem processing status in PostgreSQL.

        Args:
            document_id: Knowledge item ID
            status: Processing status (processing, completed, failed)
            chunk_count: Number of chunks produced
            token_count: Total token count
            error_message: Error message if failed
            progress: Processing progress percentage
            stage: Current processing stage label
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
                    now_iso = datetime.now(timezone.utc).isoformat()
                    meta["processing_status"] = status
                    meta["processed_at"] = now_iso

                    existing_progress = meta.get("processing_progress")
                    try:
                        existing_progress_int = (
                            int(existing_progress) if existing_progress is not None else None
                        )
                    except (TypeError, ValueError):
                        existing_progress_int = None

                    if status == "processing":
                        meta.setdefault("created_at", now_iso)
                        meta.setdefault("started_at", now_iso)
                        meta["completed_at"] = None
                    elif status == "completed":
                        meta.pop("error_message", None)
                        meta.setdefault("started_at", now_iso)
                        meta["completed_at"] = now_iso
                        meta["chunk_count"] = chunk_count
                        meta["token_count"] = token_count
                    elif status == "failed":
                        meta.setdefault("started_at", now_iso)
                        meta["completed_at"] = now_iso
                        meta["error_message"] = error_message

                    if progress is None:
                        if status == "processing":
                            progress_value = (
                                existing_progress_int if existing_progress_int is not None else 5
                            )
                        elif status in {"completed", "failed"}:
                            progress_value = 100
                        else:
                            progress_value = 0
                    else:
                        progress_value = int(progress)

                    if status == "processing":
                        progress_value = max(5, min(99, progress_value))
                        if existing_progress_int is not None:
                            progress_value = max(existing_progress_int, progress_value)
                    else:
                        progress_value = max(0, min(100, progress_value))

                    meta["processing_progress"] = progress_value
                    if stage:
                        meta["processing_stage"] = stage
                    elif status in {"completed", "failed"}:
                        meta["processing_stage"] = status

                    item.item_metadata = meta
                    session.commit()
                    logger.debug(f"Knowledge item {document_id} status updated to {status}")
                else:
                    logger.warning(f"Knowledge item {document_id} not found for status update")
        except Exception as e:
            logger.error(f"Failed to update knowledge status: {e}", exc_info=True)

    def _update_processing_progress(
        self, document_id: str, progress: int, stage: Optional[str] = None
    ) -> None:
        """Convenience wrapper for in-flight progress updates."""
        self._update_knowledge_status(
            document_id=document_id,
            status="processing",
            progress=progress,
            stage=stage,
        )

    @staticmethod
    def _get_suffix(mime_type: str) -> str:
        """Get file suffix from MIME type.

        Args:
            mime_type: MIME type string

        Returns:
            File suffix with dot prefix
        """
        normalized_mime_type = mime_type.split(";", 1)[0].strip().lower()
        mime_to_suffix = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/msword": ".doc",
            "text/plain": ".txt",
            "text/markdown": ".md",
            "text/html": ".html",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/gif": ".gif",
            "image/bmp": ".bmp",
            "image/webp": ".webp",
            "audio/mpeg": ".mp3",
            "audio/wav": ".wav",
            "audio/mp4": ".m4a",
            "audio/x-m4a": ".m4a",
            "audio/m4a": ".m4a",
            "audio/flac": ".flac",
            "video/mp4": ".mp4",
            "video/x-msvideo": ".avi",
            "video/quicktime": ".mov",
            "video/x-matroska": ".mkv",
        }
        return mime_to_suffix.get(normalized_mime_type, "")


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
