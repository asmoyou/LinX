# Object Storage Module

This module provides MinIO object storage integration for the Digital Workforce Platform.

## Features

- **MinIO Client Wrapper**: High-level interface for MinIO operations
- **Bucket Management**: Automatic bucket initialization and configuration
- **File Upload/Download**: Streaming support for large files
- **Versioning**: Automatic versioning for documents bucket
- **Metadata Storage**: PostgreSQL storage for file metadata and search
- **Automatic Cleanup**: Scheduled cleanup of temporary files
- **Access Control**: Integration with platform access control system

## Components

### MinIOClient

The `MinIOClient` class provides a wrapper around the MinIO Python client with additional functionality:

- Bucket initialization and management
- File upload with unique key generation
- File download with streaming support
- Versioning support
- Presigned URL generation
- Object copying
- Automatic cleanup of temporary files
- Health checks

### FileMetadata & FileMetadataManager

The `FileMetadata` model and `FileMetadataManager` class handle storing file metadata in PostgreSQL:

- File information (name, size, type, extension)
- Ownership and context (user, task, agent)
- Processing status tracking
- Extracted text storage for search
- Access control levels
- Soft deletion support
- Search and filtering capabilities

## Configuration

Configuration is loaded from `backend/config.yaml`:

```yaml
storage:
  minio:
    endpoint: "localhost:9000"
    access_key: "minioadmin"
    secret_key: "minioadmin"
    secure: false
    region: "us-east-1"
    buckets:
      documents: "documents"
      audio: "audio"
      video: "video"
      images: "images"
      artifacts: "agent-artifacts"
      backups: "backups"
    max_file_size_mb: 500
    allowed_document_types: ["pdf", "docx", "txt", "md", "html"]
    allowed_audio_types: ["mp3", "wav", "m4a", "flac"]
    allowed_video_types: ["mp4", "avi", "mov", "mkv"]
    allowed_image_types: ["png", "jpg", "jpeg", "gif", "bmp"]
    enable_versioning: true
    temp_file_retention_days: 7
    backup_retention_days: 90
```

## Bucket Structure

Files are organized in MinIO buckets with the following structure:

### User Files
- **documents/**: `{user_id}/{task_id}/{uuid}_{filename}`
- **audio/**: `{user_id}/{task_id}/{uuid}_{filename}`
- **video/**: `{user_id}/{task_id}/{uuid}_{filename}`
- **images/**: `{user_id}/{task_id}/{uuid}_{filename}`

### Agent Files
- **agent-artifacts/**: `{agent_id}/{task_id}/{uuid}_{filename}`

### System Files
- **backups/**: `{backup_type}/{timestamp}/`

## Usage Examples

### Initialize MinIO Client

```python
from backend.object_storage import MinIOClient

# Initialize client (loads config automatically)
client = MinIOClient()

# Initialize all buckets
client.initialize_buckets()

# Health check
if client.health_check():
    print("MinIO is healthy")
```

### Upload a File

```python
import io
from uuid import uuid4

# Prepare file data
file_data = io.BytesIO(b"File content here")
filename = "document.pdf"
user_id = str(uuid4())
task_id = str(uuid4())

# Upload file
bucket_name, object_key = client.upload_file(
    bucket_type="documents",
    file_data=file_data,
    filename=filename,
    user_id=user_id,
    task_id=task_id,
    content_type="application/pdf",
    metadata={"description": "Important document"}
)

print(f"File uploaded: {bucket_name}/{object_key}")
```

### Download a File

```python
# Download file
file_stream, metadata = client.download_file(bucket_name, object_key)

# Read content
content = file_stream.read()

print(f"Downloaded {metadata['size']} bytes")
```

### Store File Metadata

```python
from backend.database.connection import get_db_session
from backend.object_storage import FileMetadataManager
from uuid import uuid4

# Get database session
db = next(get_db_session())
manager = FileMetadataManager(db)

# Create metadata record
file_meta = manager.create_metadata(
    bucket_name=bucket_name,
    object_key=object_key,
    original_filename="document.pdf",
    file_size=1024,
    user_id=uuid4(),
    task_id=uuid4(),
    content_type="application/pdf",
    access_level="private"
)

print(f"Metadata stored: {file_meta.file_id}")
```

### Search Files

```python
# Search files by user
user_files = manager.list_by_user(user_id, limit=50)

# Search with filters
results = manager.search_files(
    user_id=user_id,
    query="report",
    file_extension="pdf",
    processing_status="completed"
)

for file_meta in results:
    print(f"- {file_meta.original_filename} ({file_meta.file_size} bytes)")
```

### Cleanup Temporary Files

```python
# Clean up temporary files older than 7 days
deleted_count = client.cleanup_temporary_files(
    older_than_days=7
)

print(f"Cleaned up {deleted_count} temporary files")
```

## Testing

Run the test suite to verify MinIO integration:

```bash
cd backend
source .venv/bin/activate
python object_storage/test_minio.py
```

The test suite includes:
- MinIO connection test
- Bucket initialization
- File upload/download
- File metadata storage
- Versioning
- Automatic cleanup

## Database Schema

The `file_metadata` table stores file metadata:

```sql
CREATE TABLE file_metadata (
    file_id UUID PRIMARY KEY,
    bucket_name VARCHAR(255) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    version_id VARCHAR(255),
    original_filename VARCHAR(512) NOT NULL,
    file_size INTEGER NOT NULL,
    content_type VARCHAR(255),
    file_extension VARCHAR(50),
    user_id UUID NOT NULL,
    task_id UUID,
    agent_id UUID,
    processing_status VARCHAR(50) NOT NULL DEFAULT 'uploaded',
    processing_error VARCHAR(1024),
    extracted_text TEXT,
    ocr_status VARCHAR(50),
    transcription_status VARCHAR(50),
    metadata JSONB,
    access_level VARCHAR(50) NOT NULL DEFAULT 'private',
    is_temporary BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMP
);
```

## Integration with Other Modules

### Knowledge Base
- Document uploads are processed by the Knowledge Base module
- Extracted text is stored in `file_metadata.extracted_text`
- Embeddings are generated and stored in Milvus

### Task Manager
- Files are associated with tasks via `task_id`
- Task completion triggers cleanup of temporary files

### Agent Framework
- Agents can upload artifacts to the `agent-artifacts` bucket
- Agent-generated files are tracked via `agent_id`

### Access Control
- File access is controlled via `access_level` field
- User permissions are checked before file operations

## Error Handling

All operations include comprehensive error handling:

```python
from minio.error import S3Error

try:
    bucket_name, object_key = client.upload_file(...)
except ValueError as e:
    # File type not allowed or file too large
    print(f"Validation error: {e}")
except S3Error as e:
    # MinIO operation failed
    print(f"Storage error: {e}")
```

## Logging

All operations are logged with appropriate log levels:

- **INFO**: Successful operations
- **WARNING**: Validation failures, file type restrictions
- **ERROR**: Operation failures, connection issues
- **DEBUG**: Detailed operation information

## Performance Considerations

- **Streaming**: Large files are streamed to avoid memory issues
- **Connection Pooling**: MinIO client reuses connections
- **Batch Operations**: Multiple files can be uploaded in parallel
- **Presigned URLs**: Use for direct client-to-MinIO transfers
- **Cleanup**: Scheduled cleanup prevents storage bloat

## Security

- **Access Control**: Files are organized by user/agent ID
- **Versioning**: Documents bucket maintains version history
- **Soft Deletion**: Files are soft-deleted before permanent removal
- **Metadata Validation**: File types and sizes are validated
- **Secure URLs**: Presigned URLs have configurable expiration

## Future Enhancements

- [ ] Encryption at rest for sensitive files
- [ ] Automatic thumbnail generation for images
- [ ] Video frame extraction
- [ ] Audio waveform generation
- [ ] Duplicate file detection
- [ ] Storage quota enforcement
- [ ] Multi-part upload for very large files
- [ ] Lifecycle policies for automatic archival
