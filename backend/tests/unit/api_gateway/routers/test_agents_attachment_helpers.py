"""Tests for agent attachment helper functions."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api_gateway.routers.agents import (
    FileReference,
    _build_output_segment_ranges,
    _build_attachment_prompt_context,
    _build_download_content_disposition,
    _build_segmented_user_prompt,
    _extract_agent_memory_candidates,
    _extract_itemized_target_count,
    _extract_token_usage_from_metadata,
    _extract_user_preference_signals,
    _is_output_truncated_from_metadata,
    _list_session_workspace_entries,
    _resolve_safe_workspace_path,
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


def test_extract_itemized_target_count_handles_strict_and_fallback_patterns() -> None:
    """Target count inference should support strict units and fallback action prompts."""
    assert _extract_itemized_target_count("请根据教材生成300道小学数学题") == 300
    assert _extract_itemized_target_count("帮我出300到小学数学题，按难度分级") == 300
    assert _extract_itemized_target_count("请总结 2024 年报告") is None


def test_is_output_truncated_from_metadata_detects_length_reason() -> None:
    """Truncation detector should flag finish_reason=length (including choices)."""
    assert _is_output_truncated_from_metadata({"finish_reason": "length"}) is True
    assert _is_output_truncated_from_metadata({"choices": [{"finish_reason": "length"}]}) is True
    assert _is_output_truncated_from_metadata({"finish_reason": "stop"}) is False


def test_resolve_safe_workspace_path_blocks_traversal(tmp_path: Path) -> None:
    """Workspace helper should resolve valid children and reject path traversal."""
    (tmp_path / "safe.txt").write_text("ok", encoding="utf-8")

    resolved, relative = _resolve_safe_workspace_path(tmp_path, "safe.txt")
    assert resolved == (tmp_path / "safe.txt").resolve()
    assert relative == "safe.txt"

    with pytest.raises(HTTPException, match="Invalid workspace file path"):
        _resolve_safe_workspace_path(tmp_path, "../outside.txt")


def test_list_session_workspace_entries_reports_previewable_files(tmp_path: Path) -> None:
    """Workspace file listing should include metadata and previewable flag."""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "b.bin").write_bytes(b"\x00\x01")

    entries = _list_session_workspace_entries(tmp_path, recursive=True)
    by_name = {item["name"]: item for item in entries}

    assert by_name["a.txt"]["previewable_inline"] is True
    assert by_name["b.bin"]["previewable_inline"] is False
    assert by_name["a.txt"]["is_directory"] is False
    assert isinstance(by_name["a.txt"]["modified_at"], str)


def test_build_download_content_disposition_handles_non_ascii_filename() -> None:
    """Download header should include ASCII fallback and UTF-8 filename* encoding."""
    header = _build_download_content_disposition("试卷-数学.pdf")

    assert "attachment;" in header
    assert "filename*=UTF-8''" in header
    assert "%E8%AF%95%E5%8D%B7-%E6%95%B0%E5%AD%A6.pdf" in header


def test_extract_user_preference_signals_ignores_one_off_format_request() -> None:
    """Single-turn deliverable format requests should not become long-term memory."""
    turns = [
        {
            "user_message": "写一份山西旅游攻略，生成md文档给我",
            "agent_response": "已生成",
            "timestamp": "2026-02-25T10:00:00+00:00",
        }
    ]

    assert _extract_user_preference_signals(turns) == []


def test_extract_user_preference_signals_keeps_persistent_cues() -> None:
    """Explicit default/persistent preference cues should be extracted."""
    turns = [
        {
            "user_message": "以后默认用markdown输出，中文回复",
            "agent_response": "好的",
            "timestamp": "2026-02-25T10:01:00+00:00",
        }
    ]

    signals = _extract_user_preference_signals(turns)
    assert any(item["key"] == "output_format" and item["value"] == "markdown" for item in signals)
    assert any(item["key"] == "language" and item["value"] == "zh-CN" for item in signals)
    assert all(item["persistent"] for item in signals)


def test_extract_user_preference_signals_keeps_repeated_non_persistent_preference() -> None:
    """Repeated same preference across turns should be retained even without explicit cue."""
    turns = [
        {
            "user_message": "这次输出成pdf",
            "agent_response": "好的",
            "timestamp": "2026-02-25T10:02:00+00:00",
        },
        {
            "user_message": "还是给我pdf格式",
            "agent_response": "收到",
            "timestamp": "2026-02-25T10:03:00+00:00",
        },
    ]

    signals = _extract_user_preference_signals(turns)
    assert any(item["key"] == "output_format" and item["value"] == "pdf" for item in signals)


def test_extract_agent_memory_candidates_requires_step_structure() -> None:
    """Only step-structured assistant outputs should become agent candidates."""
    turns = [
        {
            "user_message": "写一份福州5天旅游攻略",
            "agent_response": "下面是建议：\n1. 明确旅行天数和节奏\n2. 先排核心景点与交通\n3. 最后按天输出可执行清单",
            "agent_name": "小新2号",
            "timestamp": "2026-02-25T10:05:00+00:00",
        }
    ]

    candidates = _extract_agent_memory_candidates(turns, "小新2号")
    assert len(candidates) == 1
    assert candidates[0]["candidate_type"] == "sop"
    assert len(candidates[0]["steps"]) >= 3


def test_extract_agent_memory_candidates_skips_non_step_reply() -> None:
    """Generic short replies should not produce agent memory candidates."""
    turns = [
        {
            "user_message": "你好",
            "agent_response": "好的，我知道了。",
            "agent_name": "小新2号",
            "timestamp": "2026-02-25T10:06:00+00:00",
        }
    ]

    candidates = _extract_agent_memory_candidates(turns, "小新2号")
    assert candidates == []
