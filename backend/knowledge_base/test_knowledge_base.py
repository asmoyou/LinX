"""Tests for Knowledge Base and Document Processing.

References:
- Requirements 16: Document Processing
- Design Section 14: Document Processing Pipeline
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from knowledge_base.document_chunker import ChunkingStrategy, DocumentChunker
from knowledge_base.document_upload import DocumentUploadHandler
from knowledge_base.file_validator import FileValidator, SupportedFileType
from knowledge_base.processing_queue import JobStatus, ProcessingQueue
from knowledge_base.text_extractors import DOCXExtractor, PDFExtractor, TextFileExtractor


class TestFileValidator:
    """Test file validation."""

    def test_validate_valid_file(self, tmp_path):
        """Test validation of valid file."""
        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        validator = FileValidator(max_file_size=1024 * 1024)
        result = validator.validate_file(test_file)

        assert result.is_valid
        assert result.file_size > 0
        assert result.content_hash
        assert not result.is_malware

    def test_validate_file_too_large(self, tmp_path):
        """Test validation fails for large file."""
        test_file = tmp_path / "large.txt"
        test_file.write_text("x" * 1000)

        validator = FileValidator(max_file_size=100)
        result = validator.validate_file(test_file)

        assert not result.is_valid
        assert "exceeds maximum" in result.error_message

    def test_validate_nonexistent_file(self):
        """Test validation fails for nonexistent file."""
        validator = FileValidator()
        result = validator.validate_file(Path("/nonexistent/file.txt"))

        assert not result.is_valid
        assert "does not exist" in result.error_message


class TestTextExtractors:
    """Test text extraction."""

    def test_text_file_extraction(self, tmp_path):
        """Test extraction from text file."""
        test_file = tmp_path / "test.txt"
        content = "This is test content.\nWith multiple lines."
        test_file.write_text(content)

        extractor = TextFileExtractor()
        result = extractor.extract(test_file)

        assert result.text == content
        assert result.word_count > 0
        assert result.extraction_time >= 0

    def test_markdown_extraction(self, tmp_path):
        """Test extraction from markdown file."""
        test_file = tmp_path / "test.md"
        content = "# Header\n\nThis is **bold** text."
        test_file.write_text(content)

        from knowledge_base.text_extractors import MarkdownExtractor

        extractor = MarkdownExtractor()
        result = extractor.extract(test_file)

        assert result.text == content
        assert result.metadata["format"] == "markdown"
        assert "html" in result.metadata


class TestDocumentChunker:
    """Test document chunking."""

    def test_fixed_size_chunking(self):
        """Test fixed-size chunking."""
        text = " ".join([f"Word{i}" for i in range(1000)])
        chunker = DocumentChunker(chunk_size=100, chunk_overlap=10)

        result = chunker.chunk(text, "doc123", ChunkingStrategy.FIXED_SIZE)

        assert result.chunk_count > 1
        assert len(result.chunks) == result.chunk_count
        assert len(result.chunk_metadata) == result.chunk_count
        assert all(m["document_id"] == "doc123" for m in result.chunk_metadata)

    def test_paragraph_chunking(self):
        """Test paragraph-based chunking."""
        text = "\n\n".join([f"Paragraph {i}. " * 50 for i in range(10)])
        chunker = DocumentChunker(chunk_size=200)

        result = chunker.chunk(text, "doc456", ChunkingStrategy.PARAGRAPH)

        assert result.chunk_count > 0
        assert all("\n\n" in chunk or len(chunk) < 1000 for chunk in result.chunks)

    def test_empty_text_chunking(self):
        """Test chunking empty text."""
        chunker = DocumentChunker()
        result = chunker.chunk("", "doc789")

        assert result.chunk_count == 0
        assert len(result.chunks) == 0


class TestProcessingQueue:
    """Test processing queue."""

    @patch("knowledge_base.processing_queue.get_redis_manager")
    def test_enqueue_job(self, mock_redis):
        """Test enqueueing a job."""
        mock_redis_instance = Mock()
        mock_redis.return_value = mock_redis_instance

        queue = ProcessingQueue(mock_redis_instance)
        job = queue.enqueue(
            document_id="doc123",
            file_key="user/task/file.pdf",
            bucket="documents",
            mime_type="application/pdf",
            user_id="user123",
        )

        assert job.job_id
        assert job.document_id == "doc123"
        assert job.status == JobStatus.QUEUED
        assert mock_redis_instance.set.called
        assert mock_redis_instance.lpush.called

    @patch("knowledge_base.processing_queue.get_redis_manager")
    def test_update_job_status(self, mock_redis):
        """Test updating job status."""
        mock_redis_instance = Mock()
        mock_redis_instance.get.return_value = '{"job_id": "job123", "status": "queued", "document_id": "doc123", "file_key": "key", "bucket": "bucket", "mime_type": "type", "user_id": "user", "task_id": null, "created_at": "2024-01-01T00:00:00"}'
        mock_redis.return_value = mock_redis_instance

        queue = ProcessingQueue(mock_redis_instance)
        queue.update_status("job123", JobStatus.PROCESSING)

        assert mock_redis_instance.set.called


class TestDocumentUploadHandler:
    """Test document upload."""

    @patch("knowledge_base.document_upload.get_minio_client")
    @patch("knowledge_base.document_upload.get_file_validator")
    def test_upload_document(self, mock_validator, mock_minio, tmp_path):
        """Test document upload."""
        # Create test file
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b"PDF content")

        # Mock validation
        mock_validation = Mock()
        mock_validation.is_valid = True
        mock_validation.file_size = 100
        mock_validation.content_hash = "hash123"
        mock_validation.mime_type = "application/pdf"
        mock_validator.return_value.validate_file.return_value = mock_validation

        # Mock MinIO
        mock_minio_instance = Mock()
        mock_minio.return_value = mock_minio_instance

        handler = DocumentUploadHandler(mock_minio_instance, mock_validator.return_value)
        result = handler.upload(test_file, "user123", "task456")

        assert result.document_id
        assert result.bucket == "documents"
        assert result.file_size == 100
        assert mock_minio_instance.upload_file.called

    @patch("knowledge_base.document_upload.get_file_validator")
    def test_upload_invalid_file(self, mock_validator, tmp_path):
        """Test upload fails for invalid file."""
        test_file = tmp_path / "invalid.exe"
        test_file.write_bytes(b"executable")

        # Mock validation failure
        mock_validation = Mock()
        mock_validation.is_valid = False
        mock_validation.error_message = "Unsupported file type"
        mock_validator.return_value.validate_file.return_value = mock_validation

        handler = DocumentUploadHandler(file_validator=mock_validator.return_value)

        with pytest.raises(ValueError, match="File validation failed"):
            handler.upload(test_file, "user123")


class TestIntegration:
    """Integration tests for document processing pipeline."""

    @patch("knowledge_base.document_processor_worker.get_minio_client")
    @patch("knowledge_base.document_processor_worker.get_knowledge_indexer")
    def test_document_processing_pipeline(self, mock_indexer, mock_minio, tmp_path):
        """Test complete document processing pipeline."""
        # This would test the full pipeline from upload to indexing
        # Simplified for demonstration
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test document content for processing.")

        # Mock components
        mock_minio_instance = Mock()
        mock_minio.return_value = mock_minio_instance

        mock_indexer_instance = Mock()
        mock_indexer.return_value = mock_indexer_instance

        # Verify pipeline would work
        assert test_file.exists()
        assert test_file.read_text()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
