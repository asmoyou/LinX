"""Tests for knowledge upload type detection helpers."""

from api_gateway.routers.knowledge import _get_bucket_type, _get_file_type


def test_get_file_type_supports_m4a_mime_variants() -> None:
    """M4A MIME variants should resolve to audio document type."""
    assert _get_file_type("voice-note.unknown", "audio/mp4") == "audio"
    assert _get_file_type("voice-note.unknown", "audio/x-m4a") == "audio"
    assert _get_file_type("voice-note.unknown", "audio/m4a; codecs=mp4a.40.2") == "audio"


def test_get_file_type_falls_back_to_m4a_extension() -> None:
    """When MIME is missing, extension fallback should still classify M4A as audio."""
    assert _get_file_type("voice-note.m4a", None) == "audio"


def test_get_bucket_type_handles_content_type_with_parameters() -> None:
    """Bucket routing should tolerate MIME parameters from clients/browsers."""
    assert _get_bucket_type("voice-note.m4a", "audio/mp4; codecs=mp4a.40.2") == "audio"
