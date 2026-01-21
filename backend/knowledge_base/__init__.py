"""Knowledge Base and Document Processing module.

This module provides document processing pipeline including:
- Document upload and validation
- Text extraction from various formats (PDF, DOCX, TXT, MD)
- OCR for images
- Audio/video transcription
- Document chunking and embedding generation
- Knowledge indexing and retrieval

References:
- Requirements 4, 16: Knowledge Base and Document Processing
- Design Section 14: Document Processing Pipeline
"""

from knowledge_base.audio_processor import (
    AudioProcessor,
    TranscriptionResult,
    get_audio_processor,
)
from knowledge_base.document_chunker import (
    ChunkingStrategy,
    ChunkResult,
    DocumentChunker,
    get_document_chunker,
)
from knowledge_base.document_processor_worker import (
    DocumentProcessorWorker,
    get_processor_worker,
    start_worker,
    stop_worker,
)
from knowledge_base.document_upload import (
    DocumentUploadHandler,
    UploadResult,
    get_upload_handler,
)
from knowledge_base.file_validator import (
    FileValidationResult,
    FileValidator,
    SupportedFileType,
    get_file_validator,
)
from knowledge_base.knowledge_indexer import (
    IndexingResult,
    KnowledgeIndexer,
    get_knowledge_indexer,
)
from knowledge_base.knowledge_search import (
    KnowledgeSearch,
    SearchFilter,
    SearchResult,
    get_knowledge_search,
)
from knowledge_base.ocr_processor import (
    OCRProcessor,
    OCRResult,
    get_ocr_processor,
)
from knowledge_base.processing_queue import (
    JobStatus,
    ProcessingJob,
    ProcessingQueue,
    get_processing_queue,
)
from knowledge_base.text_extractors import (
    DOCXExtractor,
    ExtractionResult,
    MarkdownExtractor,
    PDFExtractor,
    TextExtractor,
    TextFileExtractor,
)
from knowledge_base.video_processor import (
    VideoProcessingResult,
    VideoProcessor,
    get_video_processor,
)

__all__ = [
    # Document upload
    "DocumentUploadHandler",
    "UploadResult",
    "get_upload_handler",
    # File validation
    "FileValidator",
    "FileValidationResult",
    "SupportedFileType",
    "get_file_validator",
    # Text extraction
    "TextExtractor",
    "PDFExtractor",
    "DOCXExtractor",
    "TextFileExtractor",
    "MarkdownExtractor",
    "ExtractionResult",
    # OCR processing
    "OCRProcessor",
    "OCRResult",
    "get_ocr_processor",
    # Audio processing
    "AudioProcessor",
    "TranscriptionResult",
    "get_audio_processor",
    # Video processing
    "VideoProcessor",
    "VideoProcessingResult",
    "get_video_processor",
    # Document chunking
    "DocumentChunker",
    "ChunkResult",
    "ChunkingStrategy",
    "get_document_chunker",
    # Knowledge indexing
    "KnowledgeIndexer",
    "IndexingResult",
    "get_knowledge_indexer",
    # Knowledge search
    "KnowledgeSearch",
    "SearchResult",
    "SearchFilter",
    "get_knowledge_search",
    # Processing queue
    "ProcessingQueue",
    "ProcessingJob",
    "JobStatus",
    "get_processing_queue",
    # Document processor worker
    "DocumentProcessorWorker",
    "get_processor_worker",
    "start_worker",
    "stop_worker",
]
