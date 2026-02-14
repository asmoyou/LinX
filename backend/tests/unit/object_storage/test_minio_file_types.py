"""Unit tests for MinIO file type validation helpers."""

from object_storage.minio_client import MinIOClient


def _build_test_config() -> dict:
    return {
        "endpoint": "localhost:9000",
        "access_key": "minioadmin",
        "secret_key": "minioadmin",
        "secure": False,
        "region": "us-east-1",
        "buckets": {
            "documents": "documents",
            "audio": "audio",
            "video": "video",
            "images": "images",
            "artifacts": "artifacts",
            "backups": "backups",
        },
        "allowed_document_types": ["pdf", "docx", "pptx", "txt"],
        "allowed_audio_types": ["mp3"],
        "allowed_video_types": ["mp4"],
        "allowed_image_types": ["png"],
        "max_file_size_mb": 10,
        "temp_file_retention_days": 7,
        "backup_retention_days": 7,
    }


def test_validate_file_type_allows_doc_when_docx_is_enabled() -> None:
    """Legacy .doc should be accepted when .docx support is configured."""
    client = MinIOClient(config=_build_test_config())
    assert client.validate_file_type("legacy.doc", "documents") is True


def test_validate_file_type_rejects_doc_without_docx_support() -> None:
    """Fallback acceptance should not bypass an explicit no-doc/no-docx policy."""
    config = _build_test_config()
    config["allowed_document_types"] = ["pdf", "txt"]
    client = MinIOClient(config=config)
    assert client.validate_file_type("legacy.doc", "documents") is False
