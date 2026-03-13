"""
File Metadata Management

This module handles storing and retrieving file metadata in PostgreSQL.
"""

import logging
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Session, relationship

from database.models import Base
from shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)


class FileMetadata(Base):
    """
    File metadata model for PostgreSQL storage.

    Stores metadata about files stored in MinIO for indexing and search.
    """

    __tablename__ = "file_metadata"

    # Primary key
    file_id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # MinIO reference
    bucket_name = Column(String(255), nullable=False, index=True)
    object_key = Column(String(1024), nullable=False, index=True)
    version_id = Column(String(255), nullable=True)

    # File information
    original_filename = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)
    content_type = Column(String(255), nullable=True)
    file_extension = Column(String(50), nullable=True, index=True)

    # Ownership and context
    user_id = Column(PGUUID(as_uuid=True), nullable=False, index=True)
    task_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)
    agent_id = Column(PGUUID(as_uuid=True), nullable=True, index=True)

    # Processing status
    processing_status = Column(
        String(50), nullable=False, default="uploaded", index=True
    )  # uploaded, processing, completed, failed
    processing_error = Column(String(1024), nullable=True)

    # Extracted content (for search)
    extracted_text = Column(String, nullable=True)
    ocr_status = Column(String(50), nullable=True)  # pending, completed, failed, not_applicable
    transcription_status = Column(
        String(50), nullable=True
    )  # pending, completed, failed, not_applicable

    # Custom metadata
    custom_metadata = Column(JSON, nullable=True)

    # Access control
    access_level = Column(
        String(50), nullable=False, default="private", index=True
    )  # private, team, public

    # Flags
    is_temporary = Column(Boolean, default=False, index=True)
    is_deleted = Column(Boolean, default=False, index=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=utcnow)
    updated_at = Column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    deleted_at = Column(DateTime, nullable=True)

    # Indexes for common queries
    __table_args__ = (
        Index("idx_file_user_task", "user_id", "task_id"),
        Index("idx_file_bucket_key", "bucket_name", "object_key"),
        Index("idx_file_status", "processing_status", "is_deleted"),
        Index("idx_file_temporary", "is_temporary", "created_at"),
    )

    def to_dict(self) -> Dict:
        """Convert model to dictionary."""
        return {
            "file_id": str(self.file_id),
            "bucket_name": self.bucket_name,
            "object_key": self.object_key,
            "version_id": self.version_id,
            "original_filename": self.original_filename,
            "file_size": self.file_size,
            "content_type": self.content_type,
            "file_extension": self.file_extension,
            "user_id": str(self.user_id) if self.user_id else None,
            "task_id": str(self.task_id) if self.task_id else None,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "processing_status": self.processing_status,
            "processing_error": self.processing_error,
            "ocr_status": self.ocr_status,
            "transcription_status": self.transcription_status,
            "custom_metadata": self.custom_metadata,
            "access_level": self.access_level,
            "is_temporary": self.is_temporary,
            "is_deleted": self.is_deleted,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }


class FileMetadataManager:
    """
    Manager for file metadata operations.

    Provides high-level interface for storing and retrieving file metadata.
    """

    def __init__(self, db_session: Session):
        """
        Initialize file metadata manager.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def create_metadata(
        self,
        bucket_name: str,
        object_key: str,
        original_filename: str,
        file_size: int,
        user_id: UUID,
        task_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        content_type: Optional[str] = None,
        version_id: Optional[str] = None,
        custom_metadata: Optional[Dict] = None,
        access_level: str = "private",
        is_temporary: bool = False,
    ) -> FileMetadata:
        """
        Create file metadata record.

        Args:
            bucket_name: MinIO bucket name
            object_key: MinIO object key
            original_filename: Original filename
            file_size: File size in bytes
            user_id: User ID
            task_id: Optional task ID
            agent_id: Optional agent ID
            content_type: Optional content type
            version_id: Optional version ID
            custom_metadata: Optional custom metadata
            access_level: Access level (private, team, public)
            is_temporary: Whether file is temporary

        Returns:
            Created FileMetadata instance
        """
        # Extract file extension
        file_extension = None
        if "." in original_filename:
            file_extension = original_filename.rsplit(".", 1)[1].lower()

        # Create metadata record
        file_meta = FileMetadata(
            bucket_name=bucket_name,
            object_key=object_key,
            version_id=version_id,
            original_filename=original_filename,
            file_size=file_size,
            content_type=content_type,
            file_extension=file_extension,
            user_id=user_id,
            task_id=task_id,
            agent_id=agent_id,
            custom_metadata=custom_metadata,
            access_level=access_level,
            is_temporary=is_temporary,
            processing_status="uploaded",
        )

        self.db.add(file_meta)
        self.db.commit()
        self.db.refresh(file_meta)

        logger.info(f"Created file metadata: {file_meta.file_id} " f"({bucket_name}/{object_key})")

        return file_meta

    def get_by_id(self, file_id: UUID) -> Optional[FileMetadata]:
        """
        Get file metadata by ID.

        Args:
            file_id: File ID

        Returns:
            FileMetadata instance or None
        """
        return (
            self.db.query(FileMetadata)
            .filter(FileMetadata.file_id == file_id, FileMetadata.is_deleted == False)
            .first()
        )

    def get_by_object_key(self, bucket_name: str, object_key: str) -> Optional[FileMetadata]:
        """
        Get file metadata by bucket and object key.

        Args:
            bucket_name: Bucket name
            object_key: Object key

        Returns:
            FileMetadata instance or None
        """
        return (
            self.db.query(FileMetadata)
            .filter(
                FileMetadata.bucket_name == bucket_name,
                FileMetadata.object_key == object_key,
                FileMetadata.is_deleted == False,
            )
            .first()
        )

    def list_by_user(
        self, user_id: UUID, task_id: Optional[UUID] = None, limit: int = 100, offset: int = 0
    ) -> List[FileMetadata]:
        """
        List files for a user.

        Args:
            user_id: User ID
            task_id: Optional task ID filter
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of FileMetadata instances
        """
        query = self.db.query(FileMetadata).filter(
            FileMetadata.user_id == user_id, FileMetadata.is_deleted == False
        )

        if task_id:
            query = query.filter(FileMetadata.task_id == task_id)

        return query.order_by(FileMetadata.created_at.desc()).limit(limit).offset(offset).all()

    def list_by_task(self, task_id: UUID) -> List[FileMetadata]:
        """
        List files for a task.

        Args:
            task_id: Task ID

        Returns:
            List of FileMetadata instances
        """
        return (
            self.db.query(FileMetadata)
            .filter(FileMetadata.task_id == task_id, FileMetadata.is_deleted == False)
            .order_by(FileMetadata.created_at.desc())
            .all()
        )

    def list_by_agent(self, agent_id: UUID) -> List[FileMetadata]:
        """
        List files for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            List of FileMetadata instances
        """
        return (
            self.db.query(FileMetadata)
            .filter(FileMetadata.agent_id == agent_id, FileMetadata.is_deleted == False)
            .order_by(FileMetadata.created_at.desc())
            .all()
        )

    def update_processing_status(
        self, file_id: UUID, status: str, error: Optional[str] = None
    ) -> Optional[FileMetadata]:
        """
        Update file processing status.

        Args:
            file_id: File ID
            status: New status
            error: Optional error message

        Returns:
            Updated FileMetadata instance or None
        """
        file_meta = self.get_by_id(file_id)
        if not file_meta:
            return None

        file_meta.processing_status = status
        file_meta.processing_error = error
        file_meta.updated_at = utcnow()

        self.db.commit()
        self.db.refresh(file_meta)

        logger.info(f"Updated processing status for {file_id}: {status}")

        return file_meta

    def update_extracted_text(
        self,
        file_id: UUID,
        extracted_text: str,
        ocr_status: Optional[str] = None,
        transcription_status: Optional[str] = None,
    ) -> Optional[FileMetadata]:
        """
        Update extracted text and processing status.

        Args:
            file_id: File ID
            extracted_text: Extracted text content
            ocr_status: Optional OCR status
            transcription_status: Optional transcription status

        Returns:
            Updated FileMetadata instance or None
        """
        file_meta = self.get_by_id(file_id)
        if not file_meta:
            return None

        file_meta.extracted_text = extracted_text
        if ocr_status:
            file_meta.ocr_status = ocr_status
        if transcription_status:
            file_meta.transcription_status = transcription_status
        file_meta.updated_at = utcnow()

        self.db.commit()
        self.db.refresh(file_meta)

        logger.info(f"Updated extracted text for {file_id}")

        return file_meta

    def soft_delete(self, file_id: UUID) -> bool:
        """
        Soft delete a file metadata record.

        Args:
            file_id: File ID

        Returns:
            True if deleted, False if not found
        """
        file_meta = self.get_by_id(file_id)
        if not file_meta:
            return False

        file_meta.is_deleted = True
        file_meta.deleted_at = utcnow()
        file_meta.updated_at = utcnow()

        self.db.commit()

        logger.info(f"Soft deleted file metadata: {file_id}")

        return True

    def list_temporary_files(self, older_than_days: int = 7) -> List[FileMetadata]:
        """
        List temporary files older than specified days.

        Args:
            older_than_days: Number of days

        Returns:
            List of FileMetadata instances
        """
        from datetime import timedelta

        cutoff_date = utcnow() - timedelta(days=older_than_days)

        return (
            self.db.query(FileMetadata)
            .filter(
                FileMetadata.is_temporary == True,
                FileMetadata.is_deleted == False,
                FileMetadata.created_at < cutoff_date,
            )
            .all()
        )

    def search_files(
        self,
        user_id: UUID,
        query: Optional[str] = None,
        file_extension: Optional[str] = None,
        processing_status: Optional[str] = None,
        limit: int = 100,
    ) -> List[FileMetadata]:
        """
        Search files with filters.

        Args:
            user_id: User ID
            query: Optional text search query
            file_extension: Optional file extension filter
            processing_status: Optional processing status filter
            limit: Maximum number of results

        Returns:
            List of FileMetadata instances
        """
        filters = [FileMetadata.user_id == user_id, FileMetadata.is_deleted == False]

        if query:
            # Search in filename and extracted text
            search_filter = FileMetadata.original_filename.ilike(
                f"%{query}%"
            ) | FileMetadata.extracted_text.ilike(f"%{query}%")
            filters.append(search_filter)

        if file_extension:
            filters.append(FileMetadata.file_extension == file_extension.lower())

        if processing_status:
            filters.append(FileMetadata.processing_status == processing_status)

        return (
            self.db.query(FileMetadata)
            .filter(*filters)
            .order_by(FileMetadata.created_at.desc())
            .limit(limit)
            .all()
        )
