"""Tests for legacy Word (.doc) extraction paths."""

import subprocess

import pytest

from knowledge_base.text_extractors import DOCExtractor, DOCXExtractor, get_extractor


def test_get_extractor_distinguishes_doc_and_docx() -> None:
    """application/msword should not be routed to DOCX parser directly."""
    assert isinstance(get_extractor("application/msword"), DOCExtractor)
    assert isinstance(
        get_extractor("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        DOCXExtractor,
    )


def test_doc_extractor_uses_textutil_when_available(monkeypatch, tmp_path) -> None:
    """Legacy doc extraction should use host converter output when available."""
    test_file = tmp_path / "legacy.doc"
    test_file.write_bytes(b"dummy-doc-content")

    def _fake_which(name: str) -> str | None:
        return "/usr/bin/textutil" if name == "textutil" else None

    def _fake_run(command, **kwargs):  # noqa: ANN001
        assert command[0] == "textutil"
        return subprocess.CompletedProcess(command, 0, stdout="Legacy Word Content", stderr="")

    monkeypatch.setattr("knowledge_base.text_extractors.shutil.which", _fake_which)
    monkeypatch.setattr("knowledge_base.text_extractors.subprocess.run", _fake_run)

    result = DOCExtractor().extract(test_file)

    assert result.text == "Legacy Word Content"
    assert result.metadata["extractor"] == "textutil"
    assert result.word_count == 3


def test_doc_extractor_raises_clear_error_without_tools(monkeypatch, tmp_path) -> None:
    """When no extraction tool is available, error message should be actionable."""
    test_file = tmp_path / "legacy.doc"
    test_file.write_bytes(b"dummy-doc-content")

    monkeypatch.setattr("knowledge_base.text_extractors.shutil.which", lambda _name: None)

    def _raise_docx_error(self, _file_path):  # noqa: ANN001
        raise ValueError("not a docx archive")

    monkeypatch.setattr(DOCXExtractor, "extract", _raise_docx_error)

    with pytest.raises(ValueError, match="Legacy Word"):
        DOCExtractor().extract(test_file)
