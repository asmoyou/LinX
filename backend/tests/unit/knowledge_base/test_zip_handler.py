"""Tests for knowledge base ZIP extraction limits."""

import io
import zipfile

from knowledge_base import zip_handler


def _build_zip(entries: dict[str, bytes]) -> io.BytesIO:
    """Build an in-memory ZIP archive with provided entries."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    buffer.seek(0)
    return buffer


def test_extract_zip_rejects_archive_over_size_limit(monkeypatch) -> None:
    """Archive should be rejected when compressed ZIP size exceeds configured limit."""
    zip_stream = _build_zip({"doc.txt": b"hello world"})

    monkeypatch.setattr(zip_handler, "MAX_ZIP_SIZE", 10)

    result = zip_handler.extract_zip(zip_stream)

    assert not result.extracted_files
    assert any("ZIP file size" in message for message in result.errors)


def test_extract_zip_rejects_single_file_over_limit(monkeypatch) -> None:
    """Each extracted file should respect per-file limit."""
    zip_stream = _build_zip({"doc.txt": b"this is longer than five bytes"})

    monkeypatch.setattr(zip_handler, "MAX_ZIP_SIZE", 10 * 1024 * 1024)
    monkeypatch.setattr(zip_handler, "MAX_SINGLE_FILE_SIZE", 5)

    result = zip_handler.extract_zip(zip_stream)

    assert not result.extracted_files
    assert any("per-file limit" in message for message in result.errors)


def test_extract_zip_extracts_supported_file_within_limits(monkeypatch) -> None:
    """Supported small file should be extracted successfully."""
    zip_stream = _build_zip({"note.txt": b"ok"})

    monkeypatch.setattr(zip_handler, "MAX_ZIP_SIZE", 10 * 1024 * 1024)
    monkeypatch.setattr(zip_handler, "MAX_SINGLE_FILE_SIZE", 1024 * 1024)
    monkeypatch.setattr(zip_handler, "MAX_TOTAL_SIZE", 10 * 1024 * 1024)

    result = zip_handler.extract_zip(zip_stream)

    assert len(result.extracted_files) == 1
    assert result.extracted_files[0].filename == "note.txt"
    assert result.extracted_files[0].size == 2
    assert not result.errors
