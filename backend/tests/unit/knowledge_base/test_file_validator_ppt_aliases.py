"""Tests for PPTX validation and legacy PPT rejection in file validator."""

from unittest.mock import Mock

import pytest


def test_validate_file_rejects_legacy_ppt_alias_mime(tmp_path) -> None:
    """Legacy PPT MIME aliases should be rejected."""
    pytest.importorskip("magic", exc_type=ImportError)

    try:
        from knowledge_base.file_validator import FileValidator
    except ImportError as exc:
        pytest.skip(f"python-magic/libmagic unavailable: {exc}")

    file_path = tmp_path / "slides.ppt"
    file_path.write_bytes(b"fake-ppt-bytes")

    validator = FileValidator(enable_malware_scan=False)
    validator.magic = Mock()
    validator.magic.from_file.return_value = "application/x-mspowerpoint"

    result = validator.validate_file(file_path)

    assert result.is_valid is False
    assert result.file_type is None


def test_validate_file_falls_back_to_pptx_extension(tmp_path) -> None:
    """When MIME is generic, .pptx extension should still be accepted."""
    pytest.importorskip("magic", exc_type=ImportError)

    try:
        from knowledge_base.file_validator import FileValidator, SupportedFileType
    except ImportError as exc:
        pytest.skip(f"python-magic/libmagic unavailable: {exc}")

    file_path = tmp_path / "slides.pptx"
    file_path.write_bytes(b"fake-pptx-bytes")

    validator = FileValidator(enable_malware_scan=False)
    validator.magic = Mock()
    validator.magic.from_file.return_value = "application/octet-stream"

    result = validator.validate_file(file_path)

    assert result.is_valid is True
    assert result.file_type == SupportedFileType.PPTX
    assert result.mime_type == SupportedFileType.PPTX.value
