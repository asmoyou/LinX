"""
Object Storage Module

This module provides MinIO object storage integration for the Digital Workforce Platform.
It handles file uploads, downloads, versioning, and metadata management.
"""

from object_storage.minio_client import MinIOClient
from object_storage.file_metadata import FileMetadata, FileMetadataManager

__all__ = [
    "MinIOClient",
    "FileMetadata",
    "FileMetadataManager",
]
