"""
MinIO Client Wrapper

This module provides a wrapper around the MinIO Python client with additional
functionality for the Digital Workforce Platform.
"""

import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import BinaryIO, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from minio import Minio
from minio.commonconfig import ENABLED, CopySource
from minio.error import S3Error
from minio.versioningconfig import VersioningConfig

from shared.config import get_config
from shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class MinIOClient:
    """
    MinIO client wrapper for object storage operations.

    This class provides a high-level interface for interacting with MinIO,
    including bucket management, file upload/download, versioning, and cleanup.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize MinIO client.

        Args:
            config: Optional configuration dictionary. If not provided,
                   configuration will be loaded from config.yaml
        """
        if config is None:
            cfg = get_config()
            self.config = cfg.get_section("storage.minio")
        else:
            self.config = config

        # Initialize MinIO client
        normalized_endpoint, normalized_secure = self._normalize_endpoint_setting(
            self.config["endpoint"], self.config["secure"]
        )
        self.client = self._build_client(normalized_endpoint, normalized_secure)

        # Bucket names from configuration
        self.buckets = self.config["buckets"]

        # File type restrictions
        self.allowed_types = {
            "documents": self.config["allowed_document_types"],
            "audio": self.config["allowed_audio_types"],
            "video": self.config["allowed_video_types"],
            "images": self.config["allowed_image_types"],
        }

        # Size limits
        self.max_file_size_bytes = self.config["max_file_size_mb"] * 1024 * 1024

        # Retention settings
        self.temp_file_retention_days = self.config["temp_file_retention_days"]
        self.backup_retention_days = self.config["backup_retention_days"]

        logger.info(f"MinIO client initialized for endpoint: {self.config['endpoint']}")

    def _build_client(self, endpoint: str, secure: bool) -> Minio:
        """Build a MinIO client for the provided endpoint."""
        return Minio(
            endpoint=endpoint,
            access_key=self.config["access_key"],
            secret_key=self.config["secret_key"],
            secure=secure,
            region=self.config.get("region", "us-east-1"),
        )

    @staticmethod
    def _normalize_endpoint_setting(endpoint: str, secure_default: bool) -> Tuple[str, bool]:
        """Normalize endpoint strings with or without an explicit scheme."""
        value = str(endpoint or "").strip().rstrip("/")
        if not value:
            raise ValueError("MinIO endpoint cannot be empty")

        if "://" in value:
            parsed = urlparse(value)
            normalized_endpoint = parsed.netloc or parsed.path
            secure = parsed.scheme.lower() == "https"
            return normalized_endpoint, secure

        return value, secure_default

    @staticmethod
    def _split_endpoint_host_port(endpoint: str) -> Tuple[Optional[str], Optional[int]]:
        """Split endpoint string into hostname and port."""
        parsed = urlparse(f"//{endpoint}")
        return parsed.hostname, parsed.port

    @classmethod
    def _is_loopback_host(cls, hostname: Optional[str]) -> bool:
        """Return True when the host is only reachable from the current machine."""
        if not hostname:
            return False
        return hostname.lower() in _LOOPBACK_HOSTS

    @staticmethod
    def _extract_hostname(value: Optional[str]) -> Optional[str]:
        """Extract hostname from Origin/Referer/X-Forwarded-Host style values."""
        raw = str(value or "").strip()
        if not raw:
            return None

        candidate = raw.split(",", 1)[0].strip()
        parsed = urlparse(candidate if "://" in candidate else f"//{candidate}")
        return parsed.hostname

    def _matches_configured_endpoint(self, netloc: str) -> bool:
        """Check whether a URL host matches one of the configured MinIO endpoints."""
        candidate_host, candidate_port = self._split_endpoint_host_port(netloc)
        if not candidate_host:
            return False

        known_endpoint_values = [
            self.config.get("endpoint"),
            self.config.get("public_endpoint"),
            os.getenv("MINIO_PUBLIC_ENDPOINT"),
        ]

        for endpoint_value in known_endpoint_values:
            if not endpoint_value:
                continue

            normalized_endpoint, _ = self._normalize_endpoint_setting(
                endpoint_value, self.config["secure"]
            )
            known_host, known_port = self._split_endpoint_host_port(normalized_endpoint)
            if not known_host:
                continue

            if candidate_host == known_host and candidate_port == known_port:
                return True

        return False

    def resolve_public_endpoint(
        self,
        origin_url: Optional[str] = None,
        referer_url: Optional[str] = None,
        forwarded_host: Optional[str] = None,
    ) -> Tuple[str, bool]:
        """
        Resolve the endpoint browsers should use for presigned URLs.

        Preference order:
        1. Explicit public endpoint from config/env
        2. Derived LAN/public hostname when backend uses loopback MinIO access
        3. Fallback to the configured internal endpoint
        """
        configured_public_endpoint = self.config.get("public_endpoint") or os.getenv(
            "MINIO_PUBLIC_ENDPOINT"
        )
        if configured_public_endpoint:
            return self._normalize_endpoint_setting(
                configured_public_endpoint, self.config["secure"]
            )

        endpoint, secure = self._normalize_endpoint_setting(
            self.config["endpoint"], self.config["secure"]
        )
        endpoint_host, endpoint_port = self._split_endpoint_host_port(endpoint)
        if not self._is_loopback_host(endpoint_host):
            return endpoint, secure

        for candidate in (forwarded_host, origin_url, referer_url):
            public_host = self._extract_hostname(candidate)
            if public_host and not self._is_loopback_host(public_host):
                return (f"{public_host}:{endpoint_port}" if endpoint_port else public_host), secure

        return endpoint, secure

    def initialize_buckets(self) -> None:
        """
        Initialize all required buckets.

        Creates buckets if they don't exist and configures versioning
        for the documents bucket.

        Note: Errors are logged but not raised to allow operation to continue
        even if some buckets cannot be initialized.
        """
        for bucket_key, bucket_name in self.buckets.items():
            try:
                # Check if bucket exists
                if not self.client.bucket_exists(bucket_name):
                    logger.info(f"Creating bucket: {bucket_name}")
                    self.client.make_bucket(bucket_name)
                    logger.info(f"Bucket created successfully: {bucket_name}")
                else:
                    logger.info(f"Bucket already exists: {bucket_name}")

                # Enable versioning for documents bucket
                if bucket_key == "documents" and self.config.get("enable_versioning", True):
                    self._enable_versioning(bucket_name)

            except S3Error as e:
                # Log error but don't raise - allow other buckets to be initialized
                logger.warning(f"Could not initialize bucket {bucket_name}: {e}")
                # Continue with next bucket
                continue

    def _enable_versioning(self, bucket_name: str) -> None:
        """
        Enable versioning for a bucket.

        Args:
            bucket_name: Name of the bucket

        Raises:
            S3Error: If versioning configuration fails
        """
        try:
            config = VersioningConfig(ENABLED)
            self.client.set_bucket_versioning(bucket_name, config)
            logger.info(f"Versioning enabled for bucket: {bucket_name}")
        except S3Error as e:
            logger.error(f"Error enabling versioning for {bucket_name}: {e}")
            raise

    def generate_object_key(
        self, user_id: str, task_id: Optional[str], filename: str, agent_id: Optional[str] = None
    ) -> str:
        """
        Generate a unique object key for file storage.

        Args:
            user_id: User ID
            task_id: Task ID (optional for agent artifacts)
            filename: Original filename
            agent_id: Agent ID (for agent artifacts)

        Returns:
            Unique object key in format: {user_id}/{task_id}/{uuid}_{filename}
            or {agent_id}/{task_id}/{uuid}_{filename} for agent artifacts
        """
        # Generate unique ID to prevent collisions
        unique_id = str(uuid.uuid4())

        # Sanitize filename
        safe_filename = Path(filename).name

        # Build key based on context
        if agent_id:
            # Agent artifacts
            if task_id:
                return f"{agent_id}/{task_id}/{unique_id}_{safe_filename}"
            else:
                return f"{agent_id}/{unique_id}_{safe_filename}"
        else:
            # User files
            if task_id:
                return f"{user_id}/{task_id}/{unique_id}_{safe_filename}"
            else:
                return f"{user_id}/{unique_id}_{safe_filename}"

    def validate_file_type(self, filename: str, bucket_type: str) -> bool:
        """
        Validate if file type is allowed for the bucket.

        Args:
            filename: Name of the file
            bucket_type: Type of bucket (documents, audio, video, images)

        Returns:
            True if file type is allowed, False otherwise
        """
        if bucket_type not in self.allowed_types:
            return True  # No restrictions for other bucket types

        file_ext = Path(filename).suffix.lstrip(".").lower()
        allowed_extensions = set(self.allowed_types[bucket_type])

        # Backward compatibility for legacy Word binary format.
        if bucket_type == "documents" and file_ext == "doc" and "docx" in allowed_extensions:
            allowed = True
        else:
            allowed = file_ext in allowed_extensions

        if not allowed:
            logger.warning(f"File type '{file_ext}' not allowed for bucket type '{bucket_type}'")

        return allowed

    def upload_file(
        self,
        bucket_type: str,
        file_data: BinaryIO,
        filename: str,
        user_id: str,
        task_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, str]:
        """
        Upload a file to MinIO.

        Args:
            bucket_type: Type of bucket (documents, audio, video, images, artifacts, backups)
            file_data: File data as binary stream
            filename: Original filename
            user_id: User ID
            task_id: Optional task ID
            agent_id: Optional agent ID (for artifacts)
            content_type: Optional content type
            metadata: Optional metadata dictionary

        Returns:
            Tuple of (bucket_name, object_key)

        Raises:
            ValueError: If file type is not allowed or file is too large
            S3Error: If upload fails
        """
        # Get bucket name
        bucket_name = self.buckets.get(bucket_type)
        if not bucket_name:
            raise ValueError(f"Unknown bucket type: {bucket_type}")

        # Validate file type
        if not self.validate_file_type(filename, bucket_type):
            raise ValueError(
                f"File type not allowed for {bucket_type}. "
                f"Allowed types: {self.allowed_types.get(bucket_type, 'any')}"
            )

        # Generate object key
        object_key = self.generate_object_key(user_id, task_id, filename, agent_id)

        # Get file size
        file_data.seek(0, 2)  # Seek to end
        file_size = file_data.tell()
        file_data.seek(0)  # Reset to beginning

        # Validate file size
        if file_size > self.max_file_size_bytes:
            raise ValueError(
                f"File size ({file_size} bytes) exceeds maximum "
                f"({self.max_file_size_bytes} bytes)"
            )

        # Prepare metadata
        upload_metadata = metadata or {}

        # Only add filename to metadata if it's ASCII-safe
        # MinIO metadata only supports ASCII characters
        try:
            filename.encode("ascii")
            upload_metadata["original_filename"] = filename
        except UnicodeEncodeError:
            # Skip non-ASCII filenames in metadata
            # Filename is still preserved in object_key
            logger.warning(f"Skipping non-ASCII filename in metadata: {filename}")

        upload_metadata.update(
            {
                "user_id": user_id,
                "upload_timestamp": utcnow().isoformat(),
            }
        )
        if task_id:
            upload_metadata["task_id"] = task_id
        if agent_id:
            upload_metadata["agent_id"] = agent_id

        try:
            # Upload file
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_key,
                data=file_data,
                length=file_size,
                content_type=content_type,
                metadata=upload_metadata,
            )

            logger.info(
                f"File uploaded successfully: {bucket_name}/{object_key} " f"({file_size} bytes)"
            )

            return bucket_name, object_key

        except S3Error as e:
            logger.error(f"Error uploading file to {bucket_name}/{object_key}: {e}")
            raise

    def download_file(
        self, bucket_name: str, object_key: str, version_id: Optional[str] = None
    ) -> Tuple[BinaryIO, Dict]:
        """
        Download a file from MinIO with streaming support.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key
            version_id: Optional version ID for versioned objects

        Returns:
            Tuple of (file_stream, metadata)

        Raises:
            S3Error: If download fails
        """
        try:
            # Get object
            response = self.client.get_object(
                bucket_name=bucket_name, object_name=object_key, version_id=version_id
            )

            # Read data into BytesIO for streaming
            data = io.BytesIO(response.read())
            data.seek(0)

            # Get metadata
            metadata = {
                "content_type": response.headers.get("Content-Type"),
                "size": int(response.headers.get("Content-Length", 0)),
                "etag": response.headers.get("ETag", "").strip('"'),
                "last_modified": response.headers.get("Last-Modified"),
            }

            # Add custom metadata
            for key, value in response.headers.items():
                if key.startswith("X-Amz-Meta-"):
                    metadata_key = key.replace("X-Amz-Meta-", "").lower()
                    metadata[metadata_key] = value

            logger.info(f"File downloaded successfully: {bucket_name}/{object_key}")

            return data, metadata

        except S3Error as e:
            logger.error(f"Error downloading file {bucket_name}/{object_key}: {e}")
            raise
        finally:
            if "response" in locals():
                response.close()
                response.release_conn()

    def download_file_streaming(
        self, bucket_name: str, object_key: str, chunk_size: int = 8192
    ) -> Tuple[callable, Dict]:
        """
        Download a file from MinIO as a streaming generator.

        Unlike download_file() which reads the entire file into memory,
        this method yields chunks for efficient streaming to HTTP responses.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key
            chunk_size: Size of each chunk in bytes

        Returns:
            Tuple of (generator_function, metadata)

        Raises:
            S3Error: If download fails
        """
        try:
            response = self.client.get_object(bucket_name=bucket_name, object_name=object_key)

            # Get metadata from headers
            metadata = {
                "content_type": response.headers.get("Content-Type"),
                "size": int(response.headers.get("Content-Length", 0)),
                "etag": response.headers.get("ETag", "").strip('"'),
                "last_modified": response.headers.get("Last-Modified"),
            }

            # Add custom metadata
            for key, value in response.headers.items():
                if key.startswith("X-Amz-Meta-"):
                    metadata_key = key.replace("X-Amz-Meta-", "").lower()
                    metadata[metadata_key] = value

            def generate():
                try:
                    for chunk in response.stream(chunk_size):
                        yield chunk
                finally:
                    response.close()
                    response.release_conn()

            logger.info(f"Streaming download started: {bucket_name}/{object_key}")

            return generate(), metadata

        except S3Error as e:
            logger.error(f"Error streaming file {bucket_name}/{object_key}: {e}")
            raise

    def get_file_metadata(
        self, bucket_name: str, object_key: str, version_id: Optional[str] = None
    ) -> Dict:
        """
        Get metadata for a file without downloading it.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key
            version_id: Optional version ID

        Returns:
            Dictionary containing file metadata

        Raises:
            S3Error: If operation fails
        """
        try:
            stat = self.client.stat_object(
                bucket_name=bucket_name, object_name=object_key, version_id=version_id
            )

            metadata = {
                "bucket_name": bucket_name,
                "object_key": object_key,
                "size": stat.size,
                "etag": stat.etag,
                "content_type": stat.content_type,
                "last_modified": stat.last_modified.isoformat() if stat.last_modified else None,
                "version_id": stat.version_id,
                "is_delete_marker": stat.is_delete_marker,
            }

            # Add custom metadata
            if stat.metadata:
                for key, value in stat.metadata.items():
                    metadata[key.lower()] = value

            return metadata

        except S3Error as e:
            logger.error(f"Error getting metadata for {bucket_name}/{object_key}: {e}")
            raise

    def list_objects(
        self,
        bucket_name: str,
        prefix: Optional[str] = None,
        recursive: bool = True,
        include_user_meta: bool = False,
        include_version: bool = False,
    ) -> List[Dict]:
        """
        List objects in a bucket.

        Args:
            bucket_name: Name of the bucket
            prefix: Optional prefix to filter objects
            recursive: Whether to list recursively

        Returns:
            List of object metadata dictionaries
        """
        try:
            objects = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=prefix,
                recursive=recursive,
                include_user_meta=include_user_meta,
                include_version=include_version,
            )

            result = []
            for obj in objects:
                item = {
                    "object_key": obj.object_name,
                    "size": obj.size,
                    "etag": obj.etag,
                    "last_modified": (obj.last_modified.isoformat() if obj.last_modified else None),
                    "is_dir": obj.is_dir,
                    "version_id": getattr(obj, "version_id", None),
                    "is_delete_marker": bool(getattr(obj, "is_delete_marker", False)),
                }
                if include_user_meta and getattr(obj, "metadata", None):
                    item["metadata"] = {
                        str(key).strip().lower(): str(value or "").strip()
                        for key, value in dict(obj.metadata).items()
                    }
                result.append(item)

            logger.info(
                f"Listed {len(result)} objects from {bucket_name} " f"with prefix '{prefix or ''}'"
            )

            return result

        except S3Error as e:
            logger.error(f"Error listing objects in {bucket_name}: {e}")
            raise

    def delete_file(
        self, bucket_name: str, object_key: str, version_id: Optional[str] = None
    ) -> None:
        """
        Delete a file from MinIO.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key
            version_id: Optional version ID for versioned objects

        Raises:
            S3Error: If deletion fails
        """
        try:
            self.client.remove_object(
                bucket_name=bucket_name, object_name=object_key, version_id=version_id
            )

            logger.info(f"File deleted successfully: {bucket_name}/{object_key}")

        except S3Error as e:
            logger.error(f"Error deleting file {bucket_name}/{object_key}: {e}")
            raise

    def delete_file_versions(self, bucket_name: str, object_key: str) -> int:
        """Delete the current object plus every retained version/delete marker."""

        deleted_count = 0
        try:
            versions = self.client.list_objects(
                bucket_name=bucket_name,
                prefix=object_key,
                recursive=True,
                include_version=True,
            )
            matching_versions = [
                version
                for version in versions
                if getattr(version, "object_name", None) == object_key
            ]

            if not matching_versions:
                self.client.remove_object(bucket_name=bucket_name, object_name=object_key)
                return 1

            for version in matching_versions:
                self.client.remove_object(
                    bucket_name=bucket_name,
                    object_name=object_key,
                    version_id=getattr(version, "version_id", None),
                )
                deleted_count += 1

            logger.info(
                "Deleted all versions for %s/%s (%s entries)",
                bucket_name,
                object_key,
                deleted_count,
            )
            return deleted_count
        except S3Error as e:
            logger.error(f"Error deleting all versions for {bucket_name}/{object_key}: {e}")
            raise

    def cleanup_temporary_files(
        self, bucket_name: Optional[str] = None, older_than_days: Optional[int] = None
    ) -> int:
        """
        Clean up temporary files older than specified days.

        Args:
            bucket_name: Optional specific bucket to clean. If None, cleans artifacts bucket
            older_than_days: Number of days. If None, uses config value

        Returns:
            Number of files deleted

        Raises:
            S3Error: If cleanup fails
        """
        if bucket_name is None:
            bucket_name = self.buckets["artifacts"]

        if older_than_days is None:
            older_than_days = self.temp_file_retention_days

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        try:
            objects = self.client.list_objects(bucket_name, recursive=True)
            deleted_count = 0

            for obj in objects:
                if obj.last_modified and obj.last_modified < cutoff_date:
                    self.client.remove_object(bucket_name, obj.object_name)
                    deleted_count += 1
                    logger.debug(f"Deleted temporary file: {bucket_name}/{obj.object_name}")

            logger.info(
                f"Cleanup completed: {deleted_count} files deleted from {bucket_name} "
                f"(older than {older_than_days} days)"
            )

            return deleted_count

        except S3Error as e:
            logger.error(f"Error during cleanup of {bucket_name}: {e}")
            raise

    def get_presigned_url(
        self,
        bucket_name: str,
        object_key: str,
        expires: timedelta = timedelta(hours=1),
        public_endpoint: Optional[str] = None,
        public_secure: Optional[bool] = None,
    ) -> str:
        """
        Generate a presigned URL for temporary access to a file.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key
            expires: Expiration time (default: 1 hour)

        Returns:
            Presigned URL

        Raises:
            S3Error: If URL generation fails
        """
        try:
            endpoint_override = (
                public_endpoint
                or self.config.get("public_endpoint")
                or os.getenv("MINIO_PUBLIC_ENDPOINT")
            )
            secure_default = public_secure if public_secure is not None else self.config["secure"]
            client = self.client

            if endpoint_override:
                normalized_endpoint, normalized_secure = self._normalize_endpoint_setting(
                    endpoint_override, secure_default
                )
                client = self._build_client(normalized_endpoint, normalized_secure)

            url = client.presigned_get_object(
                bucket_name=bucket_name, object_name=object_key, expires=expires
            )

            logger.info(
                f"Generated presigned URL for {bucket_name}/{object_key} " f"(expires in {expires})"
            )

            return url

        except S3Error as e:
            logger.error(f"Error generating presigned URL for {bucket_name}/{object_key}: {e}")
            raise

    def parse_object_reference(self, reference: Optional[str]) -> Optional[Tuple[str, str]]:
        """
        Parse a stored MinIO reference or legacy presigned URL into bucket/object_key.

        Supported formats:
        - minio:<bucket>:<object_key>
        - Presigned/legacy MinIO URLs pointing at a configured endpoint
        """
        value = str(reference or "").strip()
        if not value:
            return None

        if value.startswith("minio:"):
            parts = value.split(":", 2)
            if len(parts) != 3:
                return None

            _, bucket_name, object_key = parts
            if bucket_name and object_key:
                return bucket_name, object_key
            return None

        parsed = urlparse(value)
        if parsed.scheme.lower() not in {"http", "https"}:
            return None

        path = parsed.path.lstrip("/")
        if "/" not in path:
            return None

        bucket_name, object_key = path.split("/", 1)
        if bucket_name not in self.buckets.values() or not object_key:
            return None

        query_keys = {key.lower() for key in parse_qs(parsed.query).keys()}
        is_presigned = any(key.startswith("x-amz-") for key in query_keys)
        if is_presigned or self._matches_configured_endpoint(parsed.netloc):
            return bucket_name, object_key

        return None

    def copy_object(
        self,
        source_bucket: str,
        source_key: str,
        dest_bucket: str,
        dest_key: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Copy an object from one location to another.

        Args:
            source_bucket: Source bucket name
            source_key: Source object key
            dest_bucket: Destination bucket name
            dest_key: Destination object key
            metadata: Optional new metadata

        Raises:
            S3Error: If copy fails
        """
        try:
            source = CopySource(source_bucket, source_key)

            self.client.copy_object(
                bucket_name=dest_bucket, object_name=dest_key, source=source, metadata=metadata
            )

            logger.info(
                f"Object copied: {source_bucket}/{source_key} -> " f"{dest_bucket}/{dest_key}"
            )

        except S3Error as e:
            logger.error(
                f"Error copying object from {source_bucket}/{source_key} "
                f"to {dest_bucket}/{dest_key}: {e}"
            )
            raise

    def health_check(self) -> bool:
        """
        Check if MinIO is accessible and healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Try to list buckets as a health check
            self.client.list_buckets()
            logger.debug("MinIO health check passed")
            return True
        except Exception as e:
            logger.error(f"MinIO health check failed: {e}")
            return False

    def create_avatar_reference(self, bucket_name: str, object_key: str) -> str:
        """
        Create a storage reference for avatar (not a presigned URL).

        This returns a reference string that can be stored in the database
        and later resolved to a presigned URL when needed.

        Args:
            bucket_name: Name of the bucket
            object_key: Object key

        Returns:
            Reference string in format: minio:{bucket_name}:{object_key}
        """
        return f"minio:{bucket_name}:{object_key}"

    def resolve_avatar_url(
        self,
        avatar_reference: str,
        expires: timedelta = timedelta(days=7),
        public_endpoint: Optional[str] = None,
        public_secure: Optional[bool] = None,
    ) -> Optional[str]:
        """
        Resolve an avatar reference to a presigned URL.

        If the reference is already a URL (legacy data), return it as-is.
        If it's a minio: reference, generate a fresh presigned URL.

        Args:
            avatar_reference: Either a URL or a minio:{bucket}:{key} reference
            expires: Expiration time for the presigned URL (default: 7 days)

        Returns:
            Presigned URL or original URL, or None if reference is empty
        """
        if not avatar_reference:
            return None

        parsed_reference = self.parse_object_reference(avatar_reference)
        if parsed_reference:
            try:
                bucket_name, object_key = parsed_reference
                return self.get_presigned_url(
                    bucket_name,
                    object_key,
                    expires,
                    public_endpoint=public_endpoint,
                    public_secure=public_secure,
                )
            except Exception as e:
                logger.error(f"Failed to resolve avatar reference {avatar_reference}: {e}")
                return None

        # Legacy: already a URL, return as-is (will eventually expire)
        return avatar_reference


# Singleton instance
_minio_client: Optional[MinIOClient] = None


def get_minio_client() -> MinIOClient:
    """
    Get or create the MinIO client singleton.

    Returns:
        MinIOClient instance
    """
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient()
        _minio_client.initialize_buckets()
    return _minio_client
