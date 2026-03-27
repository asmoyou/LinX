from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from types import SimpleNamespace
from uuid import uuid4

from api_gateway.routers.agent_conversations import (
    _build_execution_cancelled_reply,
    _build_execution_failure_reply,
    _build_runtime_chunk,
    _is_conversation_execution_active,
    _mark_conversation_execution_active,
    _mark_conversation_execution_inactive,
    _resolve_conversation_runtime_policy,
    _serialize_message,
    _summarize_conversation_execution_error,
    _sanitize_unverified_workspace_save_claims,
    release_agent_conversation_runtime,
)
from agent_framework.runtime_policy import FileDeliveryGuardMode


def test_build_runtime_chunk_marks_restore_only_for_new_runtime() -> None:
    runtime = SimpleNamespace(
        runtime_session_id="runtime-1",
        restored_from_snapshot=True,
        snapshot_generation=4,
        use_sandbox=True,
    )

    restored_chunk = _build_runtime_chunk(runtime, is_new_runtime=True)
    reused_chunk = _build_runtime_chunk(runtime, is_new_runtime=False)

    assert restored_chunk == {
        "type": "runtime",
        "runtime_session_id": "runtime-1",
        "is_new_runtime": True,
        "restored_from_snapshot": True,
        "snapshot_generation": 4,
        "use_sandbox": True,
    }
    assert reused_chunk == {
        "type": "runtime",
        "runtime_session_id": "runtime-1",
        "is_new_runtime": False,
        "restored_from_snapshot": False,
        "snapshot_generation": 4,
        "use_sandbox": True,
    }


def test_sanitize_unverified_workspace_save_claims_drops_hallucinated_file_sections() -> None:
    text = """
## 📝 赞美福州的古诗创作完成！

---

我为你创作了一首七言律诗，并保存到文档中：

**文件路径**：`/workspace/output/fuzhou-poem.md`

---

## 🏮 原创作品

闽水悠悠绕郭流，榕城风物韵千秋。

---

## 📁 文件信息

| 项目 | 信息 |
|------|------|
| **文件路径** | `/workspace/output/fuzhou-poem.md` |
| **格式** | Markdown 文档 |
""".strip()

    sanitized = _sanitize_unverified_workspace_save_claims(
        text,
        artifact_delta_entries=[],
    )

    assert "保存到文档中" not in sanitized
    assert "fuzhou-poem.md" not in sanitized
    assert "文件信息" not in sanitized
    assert "原创作品" in sanitized
    assert "闽水悠悠绕郭流" in sanitized


def test_sanitize_unverified_workspace_save_claims_keeps_verified_output_paths() -> None:
    text = """
已将结果保存到 `/workspace/output/fuzhou-poem.md`

## 🏮 原创作品

闽水悠悠绕郭流，榕城风物韵千秋。
""".strip()

    sanitized = _sanitize_unverified_workspace_save_claims(
        text,
        artifact_delta_entries=[{"path": "output/fuzhou-poem.md"}],
    )

    assert "保存到 `/workspace/output/fuzhou-poem.md`" in sanitized
    assert "原创作品" in sanitized


def test_resolve_conversation_runtime_policy_enforces_strict_guard_for_feishu() -> None:
    policy = _resolve_conversation_runtime_policy("feishu")

    assert policy is not None
    assert policy.file_delivery_guard_mode == FileDeliveryGuardMode.STRICT


def test_resolve_conversation_runtime_policy_skips_web_chat() -> None:
    assert _resolve_conversation_runtime_policy("web") is None


def test_serialize_message_filters_internal_artifacts_from_content_json() -> None:
    message = SimpleNamespace(
        message_id=uuid4(),
        conversation_id=uuid4(),
        role="assistant",
        content_text="done",
        content_json={
            "artifacts": [
                {"path": "output/report.pdf"},
                {"path": "code.py"},
                {"path": "context.json"},
            ],
            "artifactDelta": [
                {"path": "output/report.pdf"},
                {"path": ".linx_runtime/pip_cache/cache.bin"},
            ],
        },
        attachments_json=[],
        source="feishu",
        external_event_id=None,
        created_at=datetime.now(timezone.utc),
    )

    payload = _serialize_message(message)

    assert payload.contentJson == {
        "artifacts": [{"path": "output/report.pdf"}],
        "artifactDelta": [{"path": "output/report.pdf"}],
    }



def test_summarize_conversation_execution_error_prefers_terminal_error_summary() -> None:
    raw = """Traceback (most recent call last):
  File "/tmp/x.py", line 1, in <module>
RuntimeError: boom

Error:
Session sandbox is unavailable"""

    assert _summarize_conversation_execution_error(raw) == "Session sandbox is unavailable"


def test_build_execution_failure_reply_mentions_partial_progress() -> None:
    reply = _build_execution_failure_reply(
        "Error:\nSession sandbox is unavailable",
        partial_output="partial draft",
    )

    assert "任务未完成" in reply
    assert "Session sandbox is unavailable" in reply
    assert "部分中间结果" in reply



def test_conversation_execution_activity_helpers_track_reference_counts() -> None:
    conversation_id = uuid4()

    _mark_conversation_execution_active(conversation_id)
    _mark_conversation_execution_active(conversation_id)
    assert _is_conversation_execution_active(conversation_id) is True

    _mark_conversation_execution_inactive(conversation_id)
    assert _is_conversation_execution_active(conversation_id) is True

    _mark_conversation_execution_inactive(conversation_id)
    assert _is_conversation_execution_active(conversation_id) is False


@pytest.mark.asyncio
async def test_release_agent_conversation_runtime_skips_active_execution(monkeypatch) -> None:
    conversation_id = uuid4()
    agent_id = uuid4()
    user_id = uuid4()
    released: list[tuple[object, str]] = []

    class _FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return (conversation_id,)

    class _FakeSession:
        def query(self, *_args, **_kwargs):
            return _FakeQuery()

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    monkeypatch.setattr(
        'api_gateway.routers.agent_conversations.get_db_session',
        _fake_db_session,
    )
    monkeypatch.setattr(
        'api_gateway.routers.agent_conversations.agents_router._get_accessible_agent_or_raise',
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        'api_gateway.routers.agent_conversations.get_persistent_conversation_runtime_service',
        lambda: SimpleNamespace(release_runtime=lambda conversation_id, reason: released.append((conversation_id, reason))),
    )

    _mark_conversation_execution_active(conversation_id)
    try:
        response = await release_agent_conversation_runtime(
            str(agent_id),
            str(conversation_id),
            current_user=SimpleNamespace(user_id=str(user_id), role='admin', username='admin'),
        )
    finally:
        _mark_conversation_execution_inactive(conversation_id)

    assert response.success is True
    assert released == []



def test_build_execution_cancelled_reply_preserves_reason_and_recovery_hint() -> None:
    reply = _build_execution_cancelled_reply(
        "client stream cancelled",
        partial_output="partial draft",
    )

    assert "任务已中断" in reply
    assert "客户端连接已中断" in reply
    assert "已保留你的输入" in reply
