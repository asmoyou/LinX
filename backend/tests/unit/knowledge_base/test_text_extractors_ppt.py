"""Tests for PowerPoint extraction in knowledge base text extractors."""

from types import SimpleNamespace

import pytest

from knowledge_base.text_extractors import (
    PPTXExtractor,
    get_extractor,
)


def test_get_extractor_routes_powerpoint_pptx_mime_types() -> None:
    """PPTX MIME labels should route to the PPTX extractor."""
    assert isinstance(
        get_extractor("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        PPTXExtractor,
    )
    assert isinstance(get_extractor("slides.pptx"), PPTXExtractor)


def test_get_extractor_rejects_legacy_ppt_formats() -> None:
    """Legacy PPT should be rejected; caller should convert to PPTX before upload."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        get_extractor("application/vnd.ms-powerpoint")
    with pytest.raises(ValueError, match="Unsupported file type"):
        get_extractor("slides.ppt")


def test_pptx_extractor_serializes_slide_text_tables_and_notes(monkeypatch, tmp_path) -> None:
    """PPTX extractor should keep slide structure, tables, and speaker notes."""
    presentation_path = tmp_path / "deck.pptx"
    presentation_path.write_bytes(b"dummy-pptx")

    class _FakeCell:
        def __init__(self, text: str):
            self.text = text

    class _FakeRow:
        def __init__(self, values: list[str]):
            self.cells = [_FakeCell(value) for value in values]

    class _FakeTable:
        def __init__(self, rows: list[list[str]]):
            self.rows = [_FakeRow(values) for values in rows]

    class _FakeTextFrame:
        def __init__(self, text: str):
            self.text = text

    class _FakeShape:
        def __init__(
            self,
            *,
            text: str | None = None,
            table_rows: list[list[str]] | None = None,
            children: list["_FakeShape"] | None = None,
        ) -> None:
            self.has_text_frame = text is not None
            self.text_frame = _FakeTextFrame(text or "")
            self.has_table = table_rows is not None
            self.table = _FakeTable(table_rows or [])
            self.shapes = children or []

    class _FakeSlide:
        def __init__(self, shapes: list[_FakeShape], notes: str = "") -> None:
            self.shapes = shapes
            self.has_notes_slide = bool(notes)
            self.notes_slide = (
                SimpleNamespace(notes_text_frame=SimpleNamespace(text=notes))
                if notes
                else None
            )

    class _FakePresentation:
        def __init__(self, _file_path) -> None:  # noqa: ANN001
            self.slides = [
                _FakeSlide(
                    [
                        _FakeShape(text="Roadmap Update"),
                        _FakeShape(table_rows=[["KPI", "Value"], ["ARR", "120%"]]),
                    ],
                    notes="Speaker note one",
                ),
                _FakeSlide([_FakeShape(text="Next Steps")]),
            ]
            self.core_properties = SimpleNamespace(
                author="LinX",
                title="Quarterly Review",
                subject="Q1",
                created=None,
                modified=None,
            )

    monkeypatch.setattr("knowledge_base.text_extractors.PptxPresentation", _FakePresentation)

    result = PPTXExtractor().extract(presentation_path)

    assert "[Slide 1]" in result.text
    assert "Roadmap Update" in result.text
    assert "KPI | Value" in result.text
    assert "[Speaker Notes]" in result.text
    assert result.metadata["slide_count"] == 2
    assert result.page_count == 2
    assert result.word_count > 0


def test_pptx_extractor_requires_python_pptx(monkeypatch, tmp_path) -> None:
    """A clear error should be raised when python-pptx is unavailable."""
    presentation_path = tmp_path / "deck.pptx"
    presentation_path.write_bytes(b"dummy-pptx")

    monkeypatch.setattr("knowledge_base.text_extractors.PptxPresentation", None)

    with pytest.raises(ValueError, match="python-pptx"):
        PPTXExtractor().extract(presentation_path)
