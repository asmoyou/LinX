"""Tests for session-memory builders."""

from memory_system.session_memory_builder import (
    build_agent_candidate_content,
    dedupe_user_preference_signals,
)


def test_dedupe_user_preference_signals_keeps_strongest_per_key():
    signals = [
        {
            "key": "response_style",
            "value": "concise",
            "persistent": False,
            "evidence_count": 1,
            "latest_ts": "2026-03-08T10:00:00Z",
        },
        {
            "key": "response_style",
            "value": "step_by_step",
            "persistent": True,
            "evidence_count": 2,
            "latest_ts": "2026-03-08T10:05:00Z",
        },
        {
            "key": "language",
            "value": "zh-CN",
            "persistent": True,
            "evidence_count": 1,
            "latest_ts": "2026-03-08T10:06:00Z",
        },
    ]

    deduped = dedupe_user_preference_signals(signals)
    by_key = {item["key"]: item for item in deduped}

    assert len(deduped) == 2
    assert by_key["response_style"]["value"] == "step_by_step"
    assert by_key["language"]["value"] == "zh-CN"


def test_build_agent_candidate_content_omits_duplicate_topic_and_title():
    candidate = {
        "topic": "复杂 PDF 转换后的稳定交付路径",
        "title": "复杂 PDF 转换后的稳定交付路径",
        "steps": ["识别输入限制", "切换成功链路", "校验输出后交付"],
        "summary": "先定位限制，再复用稳定转换链路。",
    }

    content = build_agent_candidate_content(candidate)

    assert "interaction.sop.title=复杂 PDF 转换后的稳定交付路径" in content
    assert "interaction.sop.topic=复杂 PDF 转换后的稳定交付路径" not in content
