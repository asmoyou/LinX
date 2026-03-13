"""
Test MinIO Object Storage

This script tests the MinIO client wrapper and file metadata management.
"""

import io
import logging
import sys
from pathlib import Path
from uuid import uuid4

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database.connection import get_db_session
from database.models import Base
from object_storage.file_metadata import FileMetadata, FileMetadataManager
from object_storage.minio_client import MinIOClient
from shared.config import get_config
from shared.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def test_minio_connection():
    """Test MinIO connection and health check."""
    logger.info("=" * 60)
    logger.info("Testing MinIO Connection")
    logger.info("=" * 60)

    try:
        client = MinIOClient()

        # Health check
        assert client.health_check(), "MinIO health check failed"
        logger.info("✓ MinIO connection successful")

    except Exception as e:
        raise AssertionError(f"MinIO connection failed: {e}") from e


def test_bucket_initialization():
    """Test bucket initialization."""
    logger.info("=" * 60)
    logger.info("Testing Bucket Initialization")
    logger.info("=" * 60)

    try:
        client = MinIOClient()

        # Initialize buckets
        client.initialize_buckets()
        logger.info("✓ All buckets initialized successfully")

        # List buckets
        buckets = client.client.list_buckets()
        logger.info(f"✓ Found {len(buckets)} buckets:")
        for bucket in buckets:
            logger.info(f"  - {bucket.name}")

    except Exception as e:
        raise AssertionError(f"Bucket initialization failed: {e}") from e


def test_file_upload_download():
    """Test file upload and download."""
    logger.info("=" * 60)
    logger.info("Testing File Upload and Download")
    logger.info("=" * 60)

    try:
        client = MinIOClient()

        # Create test file
        test_content = b"This is a test file for MinIO object storage."
        test_filename = "test_document.txt"
        test_user_id = str(uuid4())
        test_task_id = str(uuid4())

        file_data = io.BytesIO(test_content)

        # Upload file
        bucket_name, object_key = client.upload_file(
            bucket_type="documents",
            file_data=file_data,
            filename=test_filename,
            user_id=test_user_id,
            task_id=test_task_id,
            content_type="text/plain",
            metadata={"test": "true"},
        )

        logger.info(f"✓ File uploaded: {bucket_name}/{object_key}")

        # Get metadata
        metadata = client.get_file_metadata(bucket_name, object_key)
        logger.info(f"✓ File metadata retrieved:")
        logger.info(f"  - Size: {metadata['size']} bytes")
        logger.info(f"  - Content-Type: {metadata['content_type']}")
        logger.info(f"  - ETag: {metadata['etag']}")

        # Download file
        downloaded_data, download_metadata = client.download_file(bucket_name, object_key)
        downloaded_content = downloaded_data.read()

        assert downloaded_content == test_content, "Downloaded content does not match original"
        logger.info("✓ File downloaded successfully and content matches")

        # Generate presigned URL
        url = client.get_presigned_url(bucket_name, object_key)
        logger.info(f"✓ Presigned URL generated: {url[:50]}...")

        # Clean up
        client.delete_file(bucket_name, object_key)
        logger.info(f"✓ Test file deleted")

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise AssertionError(f"File upload/download test failed: {e}") from e


def test_file_metadata_storage():
    """Test file metadata storage in PostgreSQL."""
    logger.info("=" * 60)
    logger.info("Testing File Metadata Storage")
    logger.info("=" * 60)

    try:
        # Get database session
        from database.connection import DatabaseConnectionPool

        pool = DatabaseConnectionPool()
        pool.initialize()

        with pool.get_session() as db:
            bind = db.get_bind()
            Base.metadata.create_all(bind=bind, tables=[FileMetadata.__table__])
            manager = FileMetadataManager(db)

        # Create test metadata
        test_user_id = uuid4()
        test_task_id = uuid4()

        file_meta = manager.create_metadata(
            bucket_name="documents",
            object_key=f"{test_user_id}/{test_task_id}/test.pdf",
            original_filename="test_document.pdf",
            file_size=1024,
            user_id=test_user_id,
            task_id=test_task_id,
            content_type="application/pdf",
            custom_metadata={"test": "true"},
        )

        logger.info(f"✓ File metadata created: {file_meta.file_id}")

        # Retrieve metadata
        retrieved = manager.get_by_id(file_meta.file_id)
        assert retrieved is not None, "Failed to retrieve file metadata"
        logger.info(f"✓ File metadata retrieved:")
        logger.info(f"  - Filename: {retrieved.original_filename}")
        logger.info(f"  - Size: {retrieved.file_size} bytes")
        logger.info(f"  - Status: {retrieved.processing_status}")

        # Update processing status
        manager.update_processing_status(file_meta.file_id, "completed")
        logger.info("✓ Processing status updated")

        # List files by user
        user_files = manager.list_by_user(test_user_id)
        logger.info(f"✓ Found {len(user_files)} files for user")

        # Search files
        search_results = manager.search_files(
            user_id=test_user_id, query="test", file_extension="pdf"
        )
        logger.info(f"✓ Search found {len(search_results)} files")

        # Soft delete
        manager.soft_delete(file_meta.file_id)
        logger.info("✓ File metadata soft deleted")

        # Verify deletion
        deleted = manager.get_by_id(file_meta.file_id)
        assert deleted is None, "Soft delete failed"
        logger.info("✓ Soft delete verified")

        pool.close()

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise AssertionError(f"File metadata storage test failed: {e}") from e


def test_versioning():
    """Test file versioning."""
    logger.info("=" * 60)
    logger.info("Testing File Versioning")
    logger.info("=" * 60)

    try:
        client = MinIOClient()

        test_user_id = str(uuid4())
        test_task_id = str(uuid4())
        test_filename = "versioned_document.txt"

        # Upload version 1
        v1_content = b"Version 1 content"
        v1_data = io.BytesIO(v1_content)
        bucket_name, object_key = client.upload_file(
            bucket_type="documents",
            file_data=v1_data,
            filename=test_filename,
            user_id=test_user_id,
            task_id=test_task_id,
        )
        logger.info(f"✓ Version 1 uploaded: {bucket_name}/{object_key}")

        # Upload version 2 (same key)
        v2_content = b"Version 2 content - updated"
        v2_data = io.BytesIO(v2_content)
        bucket_name, object_key = client.upload_file(
            bucket_type="documents",
            file_data=v2_data,
            filename=test_filename,
            user_id=test_user_id,
            task_id=test_task_id,
        )
        logger.info(f"✓ Version 2 uploaded: {bucket_name}/{object_key}")

        # Download latest version
        downloaded_data, metadata = client.download_file(bucket_name, object_key)
        latest_content = downloaded_data.read()

        assert latest_content == v2_content, "Latest version content mismatch"
        logger.info("✓ Latest version retrieved correctly")

        # Clean up
        client.delete_file(bucket_name, object_key)
        logger.info("✓ Test file deleted")

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise AssertionError(f"Versioning test failed: {e}") from e


def test_cleanup():
    """Test automatic cleanup of temporary files."""
    logger.info("=" * 60)
    logger.info("Testing Automatic Cleanup")
    logger.info("=" * 60)

    try:
        client = MinIOClient()

        # Upload a temporary file
        test_content = b"Temporary file content"
        test_data = io.BytesIO(test_content)
        test_user_id = str(uuid4())

        bucket_name, object_key = client.upload_file(
            bucket_type="artifacts",
            file_data=test_data,
            filename="temp_file.txt",
            user_id=test_user_id,
            metadata={"temporary": "true"},
        )
        logger.info(f"✓ Temporary file uploaded: {bucket_name}/{object_key}")

        # Run cleanup (with 0 days to clean everything)
        deleted_count = client.cleanup_temporary_files(bucket_name=bucket_name, older_than_days=0)
        logger.info(f"✓ Cleanup completed: {deleted_count} files deleted")

    except Exception as e:
        import traceback

        traceback.print_exc()
        raise AssertionError(f"Cleanup test failed: {e}") from e


def main():
    """Run all tests."""
    logger.info("\n" + "=" * 60)
    logger.info("MinIO Object Storage Test Suite")
    logger.info("=" * 60 + "\n")

    tests = [
        ("MinIO Connection", test_minio_connection),
        ("Bucket Initialization", test_bucket_initialization),
        ("File Upload/Download", test_file_upload_download),
        ("File Metadata Storage", test_file_metadata_storage),
        ("File Versioning", test_versioning),
        ("Automatic Cleanup", test_cleanup),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            logger.error(f"Test '{test_name}' crashed: {e}")
            results.append((test_name, False))
        logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info(f"{status}: {test_name}")

    logger.info("=" * 60)
    logger.info(f"Results: {passed}/{total} tests passed")
    logger.info("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
