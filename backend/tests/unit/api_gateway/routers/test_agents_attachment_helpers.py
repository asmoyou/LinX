"""Tests for agent attachment helper functions."""

from types import SimpleNamespace

from api_gateway.routers.agents import (
    FileReference,
    _build_output_segment_ranges,
    _build_attachment_prompt_context,
    _build_segmented_user_prompt,
    _extract_token_usage_from_metadata,
    _extract_attachment_text,
    _infer_attachment_bucket_type,
    _infer_attachment_type,
)


def test_infer_attachment_type_supports_common_documents() -> None:
    """Document MIME/extension variants should classify as document."""
    assert (
        _infer_attachment_type(
            "slides.pptx",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        )
        == "document"
    )
    assert _infer_attachment_type("sheet.xlsx", "application/octet-stream") == "document"
    assert _infer_attachment_type("notes.md", "text/markdown") == "document"


def test_infer_attachment_bucket_type_routes_unknown_to_artifacts() -> None:
    """Unsupported document extensions should avoid strict documents bucket validation."""
    assert _infer_attachment_bucket_type("photo.png", "image/png") == "images"
    assert _infer_attachment_bucket_type("notes.txt", "text/plain") == "documents"
    assert _infer_attachment_bucket_type("archive.zip", "application/zip") == "artifacts"


def test_extract_attachment_text_falls_back_to_plain_decode() -> None:
    """Text-like payloads without dedicated extractors should still be decoded."""
    text, error = _extract_attachment_text(
        "payload.json",
        "application/json",
        b'{"project":"linx","ok":true}',
    )
    assert error is None
    assert '"project":"linx"' in text


def test_extract_attachment_text_uses_kb_extractor(monkeypatch) -> None:
    """KB extractor path should be used for document formats such as PDF."""

    class FakeExtractor:
        def extract(self, _file_path):  # noqa: ANN001
            return SimpleNamespace(text="Extracted via knowledge extractor")

    monkeypatch.setattr(
        "knowledge_base.text_extractors.get_extractor",
        lambda _file_type: FakeExtractor(),
    )

    text, error = _extract_attachment_text("report.pdf", "application/pdf", b"%PDF-1.7 fake")
    assert error is None
    assert text == "Extracted via knowledge extractor"


def test_build_attachment_prompt_context_limits_size_and_includes_fallback() -> None:
    """Prompt context should be bounded and include extraction fallback notes."""
    refs = [
        FileReference(
            path="documents/a",
            type="document",
            name="a.txt",
            size=10,
            content_type="text/plain",
            extracted_text="A" * 7000,
        ),
        FileReference(
            path="documents/b",
            type="document",
            name="b.txt",
            size=10,
            content_type="text/plain",
            extracted_text="B" * 7000,
        ),
        FileReference(
            path="artifacts/c",
            type="document",
            name="c.bin",
            size=10,
            content_type="application/octet-stream",
            extraction_error="unsupported format",
        ),
    ]

    context = _build_attachment_prompt_context(refs)

    assert "Attached files context:" in context
    assert "[Document: c.bin] Attached, but text extraction unavailable" in context
    assert len(context) < 13000


def test_build_output_segment_ranges_respects_limits() -> None:
    """Segment planner should stop at max_output_segments."""
    assert _build_output_segment_ranges(1000, 120, 3) == [(1, 120), (121, 240), (241, 360)]


def test_build_segmented_user_prompt_contains_batch_window() -> None:
    """Segment prompts should include index and item range constraints."""
    prompt = _build_segmented_user_prompt(
        "根据书本出题",
        segment_index=2,
        total_segments=10,
        start_item=121,
        end_item=240,
        target_items=1000,
    )
    assert "第 2/10 段" in prompt
    assert "121-240" in prompt
    assert "不要重复之前段落" in prompt


def test_extract_token_usage_from_metadata_supports_usage_and_token_usage() -> None:
    """Token extraction should parse both usage schema variants."""
    assert _extract_token_usage_from_metadata(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 20}}
    ) == (10, 20)
    assert _extract_token_usage_from_metadata(
        {"token_usage": {"prompt_tokens": 30, "completion_tokens": 40}}
    ) == (30, 40)
