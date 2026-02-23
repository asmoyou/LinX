"""Tests for mission deliverable helper behavior."""

from api_gateway.routers.missions import (
    _build_content_disposition,
    _normalize_deliverable_item,
)


def test_build_content_disposition_encodes_unicode_filename() -> None:
    header = _build_content_disposition("output/福州古诗.docx", disposition="attachment")

    assert header.startswith("attachment;")
    assert "filename*=UTF-8''" in header
    # Header bytes must remain ASCII-safe for HTTP transport.
    assert all(ord(ch) < 128 for ch in header)


def test_normalize_deliverable_item_demotes_runtime_script() -> None:
    item = {
        "filename": "code_ab12cd34.py",
        "path": "artifacts/demo/code_ab12cd34.py",
        "is_target": True,
        "source_scope": "output",
        "artifact_kind": "final",
    }

    normalized = _normalize_deliverable_item(item)

    assert normalized is not None
    assert normalized["is_target"] is False
    assert normalized["artifact_kind"] == "intermediate"
    assert normalized["source_scope"] == "shared"


def test_normalize_deliverable_item_keeps_real_output_as_final() -> None:
    item = {
        "filename": "output/final_report.docx",
        "path": "artifacts/demo/final_report.docx",
        "is_target": True,
        "source_scope": "output",
        "artifact_kind": "final",
    }

    normalized = _normalize_deliverable_item(item)

    assert normalized is not None
    assert normalized["is_target"] is True
    assert normalized["artifact_kind"] == "final"
    assert normalized["source_scope"] == "output"
