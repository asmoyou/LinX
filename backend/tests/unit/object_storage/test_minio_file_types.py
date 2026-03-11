"""Unit tests for MinIO file type validation helpers."""

from datetime import timedelta

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


def test_resolve_public_endpoint_derives_lan_host_from_origin_for_loopback_minio() -> None:
    """Loopback MinIO endpoints should be rewritten to a LAN host for browser access."""
    client = MinIOClient(config=_build_test_config())

    endpoint, secure = client.resolve_public_endpoint(origin_url="http://192.168.1.50:3000")

    assert endpoint == "192.168.1.50:9000"
    assert secure is False


def test_resolve_public_endpoint_prefers_explicit_public_endpoint() -> None:
    """Configured public endpoint should override derived request hosts."""
    config = _build_test_config()
    config["public_endpoint"] = "https://minio.example.com"
    client = MinIOClient(config=config)

    endpoint, secure = client.resolve_public_endpoint(origin_url="http://192.168.1.50:3000")

    assert endpoint == "minio.example.com"
    assert secure is True


def test_parse_object_reference_supports_legacy_presigned_urls() -> None:
    """Legacy MinIO presigned URLs should still map back to bucket/object keys."""
    client = MinIOClient(config=_build_test_config())

    parsed = client.parse_object_reference(
        "http://localhost:9000/images/user-1/avatar.webp?X-Amz-Algorithm=AWS4-HMAC-SHA256"
    )

    assert parsed == ("images", "user-1/avatar.webp")


def test_resolve_avatar_url_uses_public_endpoint_override(monkeypatch) -> None:
    """Avatar resolution should pass through the caller-selected public endpoint."""
    client = MinIOClient(config=_build_test_config())
    calls = []

    def _fake_get_presigned_url(  # noqa: ANN001
        bucket_name,
        object_key,
        expires,
        public_endpoint=None,
        public_secure=None,
    ):
        calls.append((bucket_name, object_key, expires, public_endpoint, public_secure))
        return "http://192.168.1.50:9000/images/user-1/avatar.webp?X-Amz-Signature=test"

    monkeypatch.setattr(client, "get_presigned_url", _fake_get_presigned_url)

    resolved = client.resolve_avatar_url(
        "minio:images:user-1/avatar.webp",
        expires=timedelta(days=7),
        public_endpoint="192.168.1.50:9000",
        public_secure=False,
    )

    assert resolved.startswith("http://192.168.1.50:9000/images/user-1/avatar.webp")
    assert calls == [
        (
            "images",
            "user-1/avatar.webp",
            timedelta(days=7),
            "192.168.1.50:9000",
            False,
        )
    ]
