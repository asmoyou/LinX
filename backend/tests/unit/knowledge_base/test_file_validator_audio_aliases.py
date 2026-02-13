"""Tests for audio MIME aliases in file validator."""

from unittest.mock import Mock

import pytest


def test_validate_file_accepts_audio_x_m4a_alias(tmp_path) -> None:
    """libmagic may return audio/x-m4a for M4A files; validator should still accept it."""
    pytest.importorskip("magic")

    try:
        from knowledge_base.file_validator import FileValidator, SupportedFileType
    except ImportError as exc:
        pytest.skip(f"python-magic/libmagic unavailable: {exc}")

    file_path = tmp_path / "sample.m4a"
    file_path.write_bytes(b"fake-audio-bytes")

    validator = FileValidator(enable_malware_scan=False)
    validator.magic = Mock()
    validator.magic.from_file.return_value = "audio/x-m4a"

    result = validator.validate_file(file_path)

    assert result.is_valid is True
    assert result.file_type == SupportedFileType.M4A
    assert result.mime_type == SupportedFileType.M4A.value
