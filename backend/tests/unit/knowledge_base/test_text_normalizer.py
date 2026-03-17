"""Tests for knowledge text normalization helpers."""

from knowledge_base.text_normalizer import normalize_knowledge_text


def test_normalize_knowledge_text_strips_multimodal_scaffolding() -> None:
    raw = (
        "Audio Transcript:\n"
        "<|nospeech|><|EMO_UNKNOWN|> 欢迎来到卡丁车赛道。\n\n"
        "Visual Analysis:\n"
        "Video Summary:\n"
        "### 摘要（zh-CN）\n"
        "**1) 整体剧情** 视频片段呈现卡丁车赛道的动态场景。\n\n"
        "Segment Details:\n"
        "Segment 0000s-0014s:\n"
        "- 红白轮胎护栏\n"
        "- 卡丁车高速过弯\n"
    )

    normalized = normalize_knowledge_text(raw)

    assert "<|" not in normalized
    assert "Audio Transcript:" not in normalized
    assert "Visual Analysis:" not in normalized
    assert "Video Summary:" not in normalized
    assert "Segment Details:" not in normalized
    assert "###" not in normalized
    assert "**" not in normalized
    assert "卡丁车赛道" in normalized
    assert "欢迎来到卡丁车赛道" in normalized
    assert "红白轮胎护栏" in normalized


def test_normalize_knowledge_text_keeps_plain_document_content() -> None:
    raw = "第一段内容。\n\n第二段内容，包含检索关键词。"

    normalized = normalize_knowledge_text(raw)

    assert normalized == raw
