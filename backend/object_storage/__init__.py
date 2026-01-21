"""
Object Storage Module

This module provides MinIO object storage integration for the Digital Workforce Platform.
It handles file uploads, downloads, versioning, and metadata management.
"""

from object_storage.file_metadata import FileMetadata, FileMetadataManager
from object_storage.minio_client import MinIOClient, get_minio_client

__all__ = [
    "MinIOClient",
    "get_minio_client",
    "FileMetadata",
    "FileMetadataManager",
]
