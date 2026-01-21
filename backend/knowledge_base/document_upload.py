"""Document upload handler.

References:
- Requirements 16: Document Processing
- Design Section 14.1: Processing Workflow
"""

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from knowledge_base.file_validator import FileValidator, get_file_validator
from object_storage.minio_client import MinIOClient, get_minio_client

logger = logging.getLogger(__name__)


@dataclass
class UploadResult:
    """Result of document upload."""

    document_id: str
    file_key: str
    bucket: str
    file_size: int
    content_hash: str
    mime_type: str


class DocumentUploadHandler:
    """Handle document uploads to object storage."""

    def __init__(
        self,
        minio_client: Optional[MinIOClient] = None,
        file_validator: Optional[FileValidator] = None,
    ):
        """Initialize upload handler.

        Args:
            minio_client: MinIO client for storage
            file_validator: File validator for validation
        """
        self.minio_client = minio_client or get_minio_client()
        self.file_validator = file_validator or get_file_validator()
        logger.info("DocumentUploadHandler initialized")

    def upload(
        self,
        file_path: Path,
        user_id: str,
        task_id: Optional[str] = None,
    ) -> UploadResult:
        """Upload document to object storage.

        Args:
            file_path: Path to file to upload
            user_id: User ID who owns the document
            task_id: Optional task ID associated with document

        Returns:
            UploadResult with upload details

        Raises:
            ValueError: If file validation fails
        """
        # Validate file
        validation = self.file_validator.validate_file(file_path)
        if not validation.is_valid:
            raise ValueError(f"File validation failed: {validation.error_message}")

        # Generate document ID and file key
        document_id = str(uuid.uuid4())
        file_key = f"{user_id}/{task_id or 'general'}/{document_id}_{file_path.name}"

        # Determine bucket based on file type
        bucket = self._get_bucket_for_file_type(validation.mime_type)

        # Upload to MinIO
        self.minio_client.upload_file(
            bucket_name=bucket,
            object_name=file_key,
            file_path=str(file_path),
        )

        logger.info(
            "Document uploaded",
            extra={
                "document_id": document_id,
                "bucket": bucket,
                "file_key": file_key,
                "size": validation.file_size,
            },
        )

        return UploadResult(
            document_id=document_id,
            file_key=file_key,
            bucket=bucket,
            file_size=validation.file_size,
            content_hash=validation.content_hash,
            mime_type=validation.mime_type,
        )

    def _get_bucket_for_file_type(self, mime_type: str) -> str:
        """Determine appropriate bucket for file type.

        Args:
            mime_type: MIME type of file

        Returns:
            Bucket name
        """
        if "audio" in mime_type:
            return "audio"
        elif "video" in mime_type:
            return "video"
        elif "image" in mime_type:
            return "images"
        else:
            return "documents"


# Singleton instance
_upload_handler: Optional[DocumentUploadHandler] = None


def get_upload_handler() -> DocumentUploadHandler:
    """Get or create the upload handler singleton.

    Returns:
        DocumentUploadHandler instance
    """
    global _upload_handler
    if _upload_handler is None:
        _upload_handler = DocumentUploadHandler()
    return _upload_handler
