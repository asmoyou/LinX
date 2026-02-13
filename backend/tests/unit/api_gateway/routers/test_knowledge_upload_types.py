"""Tests for knowledge upload type detection helpers."""

import io
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from api_gateway.routers.knowledge import (
    _build_docx_filename,
    _convert_legacy_doc_bytes_to_docx,
    _generate_thumbnail_stream,
    _get_bucket_type,
    _get_file_type,
    _is_legacy_word_doc,
    _parse_minio_reference,
    _should_attempt_thumbnail_backfill,
)


def test_get_file_type_supports_m4a_mime_variants() -> None:
    """M4A MIME variants should resolve to audio document type."""
    assert _get_file_type("voice-note.unknown", "audio/mp4") == "audio"
    assert _get_file_type("voice-note.unknown", "audio/x-m4a") == "audio"
    assert _get_file_type("voice-note.unknown", "audio/m4a; codecs=mp4a.40.2") == "audio"


def test_get_file_type_falls_back_to_m4a_extension() -> None:
    """When MIME is missing, extension fallback should still classify M4A as audio."""
    assert _get_file_type("voice-note.m4a", None) == "audio"


def test_get_file_type_supports_excel_uploads() -> None:
    """Excel MIME/extension should map to the dedicated excel document type."""
    assert (
        _get_file_type(
            "report.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        == "excel"
    )
    assert _get_file_type("legacy-sheet.xls", None) == "excel"


def test_get_bucket_type_handles_content_type_with_parameters() -> None:
    """Bucket routing should tolerate MIME parameters from clients/browsers."""
    assert _get_bucket_type("voice-note.m4a", "audio/mp4; codecs=mp4a.40.2") == "audio"


def test_generate_thumbnail_stream_supports_video(monkeypatch) -> None:
    """Video files should produce a JPEG thumbnail when moviepy is available."""

    class FakeVideoFileClip:
        def __init__(self, _path: str):
            self.duration = 2.0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return None

        def get_frame(self, _time: float):
            return np.zeros((32, 48, 3), dtype=np.uint8)

    fake_moviepy_editor = types.ModuleType("moviepy.editor")
    fake_moviepy_editor.VideoFileClip = FakeVideoFileClip
    monkeypatch.setitem(sys.modules, "moviepy.editor", fake_moviepy_editor)

    generated = _generate_thumbnail_stream(
        file_data=io.BytesIO(b"not-a-real-video"),
        filename="clip.mp4",
        content_type="video/mp4",
    )

    assert generated is not None
    stream, mime_type = generated
    assert mime_type == "image/jpeg"
    assert stream.getbuffer().nbytes > 0


def test_parse_minio_reference_handles_valid_and_invalid_values() -> None:
    """MinIO references should parse safely without raising."""
    assert _parse_minio_reference("minio:images:foo/bar.jpg") == ("images", "foo/bar.jpg")
    assert _parse_minio_reference("minio:missing-key") is None
    assert _parse_minio_reference("http://example.com/x.jpg") is None


def test_should_attempt_thumbnail_backfill_respects_recent_failures() -> None:
    """Recent failed attempts should be throttled to avoid repeated heavy extraction."""
    now = datetime(2026, 2, 13, tzinfo=timezone.utc)

    assert _should_attempt_thumbnail_backfill({}) is True
    assert (
        _should_attempt_thumbnail_backfill({"thumbnail_reference": "minio:images:x.jpg"}) is False
    )

    recent_failure_metadata = {
        "thumbnail_backfill_last_error": "PyMuPDF unavailable",
        "thumbnail_backfill_last_attempt_at": (now - timedelta(minutes=10)).isoformat(),
    }
    assert _should_attempt_thumbnail_backfill(recent_failure_metadata, now=now) is False

    stale_failure_metadata = {
        "thumbnail_backfill_last_error": "PyMuPDF unavailable",
        "thumbnail_backfill_last_attempt_at": (now - timedelta(hours=2)).isoformat(),
    }
    assert _should_attempt_thumbnail_backfill(stale_failure_metadata, now=now) is True


def test_is_legacy_word_doc_detects_doc_variants() -> None:
    """Legacy DOC detection should handle extension and MIME fallbacks."""
    assert _is_legacy_word_doc("legacy.doc", "application/msword") is True
    assert _is_legacy_word_doc("legacy.bin", "application/msword") is True
    assert _is_legacy_word_doc("modern.docx", "application/msword") is False
    assert (
        _is_legacy_word_doc(
            "modern.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        is False
    )


def test_build_docx_filename_rewrites_extension() -> None:
    """Converted filename should preserve stem and force .docx extension."""
    assert _build_docx_filename("legacy.doc") == "legacy.docx"
    assert _build_docx_filename("report.final.v1") == "report.final.docx"


def test_convert_legacy_doc_bytes_to_docx_uses_textutil_when_available(monkeypatch) -> None:
    """Conversion helper should return generated DOCX bytes from tool output."""

    def _fake_which(command: str):  # noqa: ANN001
        return "/usr/bin/textutil" if command == "textutil" else None

    def _fake_run(command, check, capture_output, text):  # noqa: ANN001
        output_index = command.index("-output") + 1
        output_path = Path(command[output_index])
        output_path.write_bytes(b"converted-docx-binary")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("api_gateway.routers.knowledge.shutil.which", _fake_which)
    monkeypatch.setattr("api_gateway.routers.knowledge.subprocess.run", _fake_run)

    converted = _convert_legacy_doc_bytes_to_docx(b"legacy-doc-binary", "legacy.doc")
    assert converted == b"converted-docx-binary"


def test_convert_legacy_doc_bytes_to_docx_raises_when_no_converter(monkeypatch) -> None:
    """A clear error should be raised when no conversion tool is available."""
    monkeypatch.setattr("api_gateway.routers.knowledge.shutil.which", lambda _command: None)
    with pytest.raises(ValueError, match="no converter tool available"):
        _convert_legacy_doc_bytes_to_docx(b"legacy-doc-binary", "legacy.doc")
