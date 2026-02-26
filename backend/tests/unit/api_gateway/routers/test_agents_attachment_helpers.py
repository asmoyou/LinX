"""Tests for agent attachment helper functions."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from api_gateway.routers.agents import (
    FileReference,
    _build_agent_metrics_from_task_rows,
    _build_audit_log_entries,
    _build_task_log_entries,
    _build_output_segment_ranges,
    _build_attachment_prompt_context,
    _build_download_content_disposition,
    _build_segmented_user_prompt,
    _call_llm_for_memory_json,
    _extract_session_memory_signals_with_llm,
    _extract_json_object_from_text,
    _extract_agent_memory_candidates,
    _extract_itemized_target_count,
    _normalize_llm_agent_candidates,
    _normalize_llm_user_preference_signals,
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


def test_build_agent_metrics_from_task_rows_counts_statuses() -> None:
    """Task status rows should map into detail metrics with derived rates."""
    metrics = _build_agent_metrics_from_task_rows(
        [
            ("completed", 6),
            ("failed", 2),
            ("pending", 3),
            ("in_progress", 1),
        ]
    )

    assert metrics["tasksCompleted"] == 6
    assert metrics["tasksFailed"] == 2
    assert metrics["tasksExecuted"] == 8
    assert metrics["pendingTasks"] == 3
    assert metrics["inProgressTasks"] == 1
    assert metrics["completionRate"] == pytest.approx(0.75)
    assert metrics["successRate"] == pytest.approx(0.75)
    assert metrics["failureRate"] == pytest.approx(0.25)


def test_build_task_log_entries_sets_level_and_message() -> None:
    """Task activity logs should map statuses to UI-friendly level/message."""
    now = datetime(2026, 2, 25, 10, 0, tzinfo=timezone.utc)
    entries = _build_task_log_entries(
        [
            ("整理周报", "completed", now, now),
            ("同步日报", "failed", now, now),
            ("准备会议材料", "in_progress", now, None),
        ]
    )

    assert [entry["level"] for entry in entries] == ["SUCCESS", "ERROR", "INFO"]
    assert "Task completed" in entries[0]["message"]
    assert "Task failed" in entries[1]["message"]
    assert entries[2]["source"] == "task"


def test_build_audit_log_entries_maps_result_to_level() -> None:
    """Audit activity should derive level from result and include reason."""
    now = datetime(2026, 2, 25, 10, 5, tzinfo=timezone.utc)
    entries = _build_audit_log_entries(
        [
            ("agent_updated", {"result": "success", "action": "update"}, now),
            ("resource_access_denied", {"result": "denied", "reason": "forbidden"}, now),
        ]
    )

    assert entries[0]["level"] == "SUCCESS"
    assert entries[0]["message"] == "Update"
    assert entries[1]["level"] == "ERROR"
    assert "forbidden" in entries[1]["message"]
    assert entries[1]["source"] == "audit"


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


def test_extract_user_preference_signals_keeps_explicit_food_like_signal() -> None:
    """Explicit first-person food preferences should be captured even in one turn."""
    turns = [
        {
            "user_message": "我喜欢黄焖鸡，怎么做的？",
            "agent_response": "可以按家常做法来",
            "timestamp": "2026-02-25T10:04:00+00:00",
        }
    ]

    signals = _extract_user_preference_signals(turns)
    assert any(
        item["key"] == "food_preference_like"
        and item["value"] == "黄焖鸡"
        and item["strong_signal"] is True
        for item in signals
    )


def test_extract_user_preference_signals_keeps_explicit_food_avoid_signal() -> None:
    """Dietary restrictions should be captured as avoid-preference signals."""
    turns = [
        {
            "user_message": "我对花生过敏，帮我避开相关菜品",
            "agent_response": "好的",
            "timestamp": "2026-02-25T10:04:30+00:00",
        }
    ]

    signals = _extract_user_preference_signals(turns)
    assert any(
        item["key"] == "food_preference_avoid"
        and item["value"] == "花生"
        and item["strong_signal"] is True
        for item in signals
    )


def test_extract_json_object_from_text_supports_markdown_block() -> None:
    content = """
说明如下：
```json
{"user_preferences":[{"key":"response_language","value":"zh-CN"}]}
```
"""
    parsed = _extract_json_object_from_text(content)
    assert parsed is not None
    assert parsed["user_preferences"][0]["key"] == "response_language"


def test_normalize_llm_user_preference_signals_filters_low_quality() -> None:
    turn_ts_map = {1: "2026-02-25T10:00:00+00:00", 2: "2026-02-25T10:01:00+00:00"}
    items = [
        {
            "key": "response_language",
            "value": "zh-CN",
            "persistent": True,
            "confidence": 0.9,
            "evidence_turns": [1, 2],
        },
        {
            "key": "one_off_temp",
            "value": "this time only",
            "persistent": False,
            "confidence": 0.4,
            "evidence_turns": [1],
        },
    ]

    normalized = _normalize_llm_user_preference_signals(items, turn_ts_map)
    assert len(normalized) == 1
    assert normalized[0]["key"] == "response_language"
    assert normalized[0]["latest_ts"] == "2026-02-25T10:01:00+00:00"


def test_normalize_llm_user_preference_signals_keeps_single_turn_high_confidence_signal() -> None:
    turn_ts_map = {1: "2026-02-25T10:00:00+00:00"}
    items = [
        {
            "key": "food_preference_like",
            "value": "冒菜和可乐",
            "persistent": False,
            "confidence": 0.91,
            "evidence_turns": [1],
            "reason": "用户明确直接表达偏好",
        }
    ]

    normalized = _normalize_llm_user_preference_signals(items, turn_ts_map)
    assert len(normalized) == 1
    assert normalized[0]["key"] == "food_preference_like"
    assert normalized[0]["value"] == "冒菜和可乐"
    assert normalized[0]["latest_ts"] == "2026-02-25T10:00:00+00:00"


def test_normalize_llm_agent_candidates_keeps_reusable_candidate() -> None:
    turn_ts_map = {2: "2026-02-25T10:02:00+00:00"}
    items = [
        {
            "candidate_type": "sop",
            "title": "旅游攻略写作流程",
            "summary": "先梳理天数与交通，再按天输出可执行清单。",
            "steps": ["确定天数和城市范围", "按天规划路线与交通", "输出每日清单和预算"],
            "confidence": 0.81,
            "evidence_turns": [2],
        }
    ]

    normalized = _normalize_llm_agent_candidates(
        items,
        agent_name="小新2号",
        turn_ts_map=turn_ts_map,
    )
    assert len(normalized) == 1
    assert normalized[0]["candidate_type"] == "sop"
    assert normalized[0]["latest_ts"] == "2026-02-25T10:02:00+00:00"
    assert len(normalized[0]["steps"]) >= 3


@pytest.mark.asyncio
async def test_extract_session_memory_signals_prefers_memory_config_then_fallbacks_to_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRegistry:
        def get_agent(self, _agent_id):  # noqa: ANN001
            return SimpleNamespace(llm_provider="agent_provider", llm_model="agent-model")

    class FakeConfig:
        def get(self, key: str):  # noqa: ANN001
            values = {
                "memory.enhanced_memory.fact_extraction.provider": "memory_provider",
                "memory.enhanced_memory.fact_extraction.model": "memory-model",
                "llm.model_mapping.chat": "fallback-chat-model",
                "llm.providers.memory_provider.models": {"chat": "memory-model"},
            }
            return values.get(key)

    class FakeRouter:
        def __init__(self) -> None:
            self.calls = []

        async def generate(  # noqa: ANN001
            self,
            *,
            prompt,
            provider=None,
            model=None,
            temperature=0.1,
            max_tokens=1800,
            **kwargs,
        ):
            self.calls.append(
                {
                    "provider": provider,
                    "model": model,
                    "prompt": prompt,
                    "kwargs": kwargs,
                }
            )
            if provider == "memory_provider":
                raise ValueError("Provider 'memory_provider' not available")
            return SimpleNamespace(
                content=(
                    '{"user_preferences":[{"key":"output_format","value":"markdown",'
                    '"persistent":true,"confidence":0.9,"evidence_turns":[1]}],'
                    '"agent_memory_candidates":[]}'
                )
            )

    fake_router = FakeRouter()

    monkeypatch.setattr("api_gateway.routers.agents.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr("shared.config.get_config", lambda: FakeConfig())
    monkeypatch.setattr("llm_providers.router.get_llm_provider", lambda: fake_router)

    signals, candidates = await _extract_session_memory_signals_with_llm(
        turns=[
            {
                "user_message": "以后默认markdown输出",
                "agent_response": "收到",
                "timestamp": "2026-02-25T10:00:00+00:00",
            }
        ],
        agent_id="agent-1",
        agent_name="小新2号",
    )

    assert len(fake_router.calls) >= 2
    assert fake_router.calls[0]["provider"] == "memory_provider"
    assert fake_router.calls[0]["model"] == "memory-model"
    assert fake_router.calls[1]["provider"] == "agent_provider"
    assert fake_router.calls[1]["model"] == "agent-model"
    assert fake_router.calls[1]["kwargs"]["response_format"]["type"] == "json_object"
    assert any(item["key"] == "output_format" and item["value"] == "markdown" for item in signals)
    assert candidates == []


@pytest.mark.asyncio
async def test_extract_session_memory_signals_runs_secondary_preference_recall(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeRegistry:
        def get_agent(self, _agent_id):  # noqa: ANN001
            return SimpleNamespace(llm_provider=None, llm_model=None)

    class FakeConfig:
        def get(self, _key: str):  # noqa: ANN001
            return None

    class FakeRouter:
        def __init__(self) -> None:
            self.calls = []

        async def generate(  # noqa: ANN001
            self,
            *,
            prompt,
            provider=None,
            model=None,
            temperature=0.1,
            max_tokens=1800,
            **kwargs,
        ):
            self.calls.append({"prompt": prompt, "kwargs": kwargs})
            if "用户偏好补充抽取器" in prompt:
                return SimpleNamespace(
                    content=(
                        '{"user_preferences":[{"key":"food_preference_like",'
                        '"value":"黄焖鸡","persistent":true,"explicit_source":true,'
                        '"confidence":0.9,"evidence_turns":[1]}]}'
                    )
                )
            return SimpleNamespace(
                content='{"user_preferences":[],"agent_memory_candidates":[]}'
            )

    fake_router = FakeRouter()

    monkeypatch.setattr("api_gateway.routers.agents.get_agent_registry", lambda: FakeRegistry())
    monkeypatch.setattr("shared.config.get_config", lambda: FakeConfig())
    monkeypatch.setattr("llm_providers.router.get_llm_provider", lambda: fake_router)

    signals, candidates = await _extract_session_memory_signals_with_llm(
        turns=[
            {
                "user_message": "我喜欢黄焖鸡，怎么做的？",
                "agent_response": "可以按家常做法来",
                "timestamp": "2026-02-25T10:00:00+00:00",
            }
        ],
        agent_id="agent-1",
        agent_name="小新2号",
    )

    assert len(fake_router.calls) >= 2
    assert all(call["kwargs"]["response_format"]["type"] == "json_object" for call in fake_router.calls)
    assert any(item["key"] == "food_preference_like" and item["value"] == "黄焖鸡" for item in signals)
    assert candidates == []


@pytest.mark.asyncio
async def test_call_llm_for_memory_json_falls_back_when_json_mode_returns_empty() -> None:
    class FakeRouter:
        def __init__(self) -> None:
            self.calls = []

        async def generate(self, **kwargs):  # noqa: ANN003
            self.calls.append(kwargs)
            if "response_format" in kwargs:
                return SimpleNamespace(content="")
            return SimpleNamespace(
                content=(
                    '{"user_preferences":[{"key":"food_preference_like","value":"黄焖鸡",'
                    '"persistent":true,"explicit_source":true,"confidence":0.9,'
                    '"evidence_turns":[1]}],"agent_memory_candidates":[]}'
                )
            )

    fake_router = FakeRouter()
    parsed, parse_meta = await _call_llm_for_memory_json(
        llm_router=fake_router,
        prompt="测试抽取",
        provider="llm-pool",
        model="Qwen/Qwen3-Next-80B-A3B-Instruct",
    )

    assert len(fake_router.calls) == 2
    assert fake_router.calls[0]["response_format"]["type"] == "json_object"
    assert "response_format" not in fake_router.calls[1]
    assert parse_meta["response_mode"] == "plain_fallback"
    assert parse_meta["fallback_triggered"] is True
    assert parse_meta["parse_status"] == "ok"
    assert isinstance(parsed.get("user_preferences"), list)


@pytest.mark.asyncio
async def test_call_llm_for_memory_json_times_out() -> None:
    class SlowRouter:
        async def generate(self, **kwargs):  # noqa: ANN003
            await asyncio.sleep(0.7)
            return SimpleNamespace(content='{"user_preferences":[],"agent_memory_candidates":[]}')

    with pytest.raises(TimeoutError, match="session_memory_extraction_timeout_0.5s"):
        await _call_llm_for_memory_json(
            llm_router=SlowRouter(),
            prompt="测试超时",
            provider="llm-pool",
            model="Qwen/Qwen3-Next-80B-A3B-Instruct",
            timeout_seconds=0.5,
        )


@pytest.mark.asyncio
async def test_call_llm_for_memory_json_timeout_invalidates_provider_cache() -> None:
    class SlowRouter:
        def __init__(self) -> None:
            self.invalidated = []

        async def generate(self, **kwargs):  # noqa: ANN003
            await asyncio.sleep(0.7)
            return SimpleNamespace(content='{"user_preferences":[],"agent_memory_candidates":[]}')

        async def invalidate_provider(self, provider_name: str) -> bool:
            self.invalidated.append(provider_name)
            return True

    router = SlowRouter()
    with pytest.raises(TimeoutError, match="session_memory_extraction_timeout_0.5s"):
        await _call_llm_for_memory_json(
            llm_router=router,
            prompt="测试超时并失效缓存",
            provider="aliyun-bl",
            model="qwen3.5-flash-2026-02-23",
            timeout_seconds=0.5,
        )

    assert router.invalidated == ["aliyun-bl"]


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
