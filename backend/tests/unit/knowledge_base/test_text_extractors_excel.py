"""Tests for Excel extraction in knowledge base text extractors."""

from pathlib import Path

import pandas as pd

from knowledge_base.text_extractors import ExcelExtractor, get_extractor


def test_get_extractor_routes_excel_mime_types() -> None:
    """Excel MIME labels should route to the spreadsheet extractor."""
    assert isinstance(
        get_extractor("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ExcelExtractor,
    )
    assert isinstance(get_extractor("application/vnd.ms-excel"), ExcelExtractor)


def test_excel_extractor_serializes_sheet_content(monkeypatch, tmp_path) -> None:
    """Excel extractor should include worksheet names, headers, and row values."""
    workbook_path = tmp_path / "report.xlsx"
    workbook_path.write_bytes(b"dummy-binary")

    mock_sheets = {
        "Revenue": pd.DataFrame(
            [
                {"Month": "Jan", "Amount": 1200},
                {"Month": "Feb", "Amount": 1800},
            ]
        ),
        "Costs": pd.DataFrame([{"Month": "Jan", "Amount": 700}]),
    }

    def _mock_read_excel(_file_path: Path, sheet_name=None, dtype=None):  # noqa: ANN001
        assert sheet_name is None
        assert dtype is str
        return mock_sheets

    monkeypatch.setattr("knowledge_base.text_extractors.pd.read_excel", _mock_read_excel)

    result = ExcelExtractor().extract(workbook_path)

    assert "[Sheet: Revenue]" in result.text
    assert "Month\tAmount" in result.text
    assert "Jan\t1200" in result.text
    assert result.metadata["sheet_count"] == 2
    assert result.page_count == 2
    assert result.word_count > 0
