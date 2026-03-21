from __future__ import annotations

import json
import pytest
import requests
from types import SimpleNamespace

from api_gateway import feishu_long_connection
from api_gateway.feishu_long_connection import (
    FeishuLongConnectionManager,
    FeishuPublicationTarget,
    _resolve_feishu_long_connection_proxy,
)
from api_gateway.routers.agent_conversations import _diff_workspace_entries
from api_gateway.routers import integrations as integrations_router
from api_gateway.routers.integrations import (
    FeishuApiError,
    FeishuFileDeliveryRetryService,
    _QueuedFeishuFileDelivery,
    _build_feishu_reply_text,
    _classify_feishu_file_delivery_error,
    _extract_feishu_message_from_long_connection_event,
    _queued_feishu_file_delivery_note,
    _format_feishu_api_error,
    _looks_like_feishu_file_send_request,
    _parse_feishu_json_response,
    _prepare_feishu_message_uploads,
    _resolve_feishu_artifact_file_paths,
    _send_feishu_markdown_card_message,
    _send_feishu_text_message,
    _select_feishu_deliverable_artifacts,
    _select_feishu_explicitly_requested_artifacts,
)


class _FakeProcess:
    _next_pid = 1000

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = _FakeProcess._next_pid
        _FakeProcess._next_pid += 1
        self._alive = False

    def start(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        self._alive = False

    def join(self, timeout: float | None = None) -> None:
        return None

    def kill(self) -> None:
        self._alive = False


def test_extract_feishu_message_from_long_connection_event_parses_expected_fields() -> None:
    event = SimpleNamespace(
        header=SimpleNamespace(
            event_type="im.message.receive_v1",
            event_id="evt-123",
            tenant_key="tenant-header",
        ),
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(
                    open_id="open-1",
                    user_id="user-1",
                    union_id="union-1",
                ),
                tenant_key="tenant-sender",
            ),
            message=SimpleNamespace(
                message_id="msg-1",
                root_id="root-1",
                parent_id=None,
                chat_id="chat-1",
                chat_type="p2p",
                message_type="text",
                content='{"text":"hello from feishu"}',
            ),
        ),
    )

    message = _extract_feishu_message_from_long_connection_event(event)

    assert message == {
        "event_id": "evt-123",
        "message_id": "msg-1",
        "message_type": "text",
        "chat_id": "chat-1",
        "chat_type": "p2p",
        "thread_key": "root-1",
        "text": "hello from feishu",
        "content_payload": {"text": "hello from feishu"},
        "open_id": "open-1",
        "external_user_id": "user-1",
        "union_id": "union-1",
        "tenant_key": "tenant-header",
    }


def test_extract_feishu_message_from_long_connection_event_keeps_file_payload() -> None:
    event = SimpleNamespace(
        header=SimpleNamespace(
            event_type="im.message.receive_v1",
            event_id="evt-file-1",
            tenant_key="tenant-header",
        ),
        event=SimpleNamespace(
            sender=SimpleNamespace(
                sender_id=SimpleNamespace(open_id="open-1", user_id="user-1", union_id="union-1"),
                tenant_key="tenant-sender",
            ),
            message=SimpleNamespace(
                message_id="msg-file-1",
                root_id=None,
                parent_id=None,
                chat_id="chat-1",
                chat_type="p2p",
                message_type="file",
                content='{"file_key":"file-key-1","file_name":"spec.pdf"}',
            ),
        ),
    )

    message = _extract_feishu_message_from_long_connection_event(event)

    assert message == {
        "event_id": "evt-file-1",
        "message_id": "msg-file-1",
        "message_type": "file",
        "chat_id": "chat-1",
        "chat_type": "p2p",
        "thread_key": "chat-1",
        "text": "",
        "content_payload": {"file_key": "file-key-1", "file_name": "spec.pdf"},
        "open_id": "open-1",
        "external_user_id": "user-1",
        "union_id": "union-1",
        "tenant_key": "tenant-header",
    }


def test_build_feishu_reply_text_without_base_url_omits_workspace_link() -> None:
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text="Finished",
        delivered_artifacts=[],
        pending_artifacts=[{"path": "output/report.md", "is_directory": False}],
        base_url=None,
    )

    assert "Finished" in text
    assert "output/report.md" in text
    assert "workforce/agent-1/conversations/conv-1" not in text


def test_build_feishu_reply_text_includes_delivery_notes() -> None:
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text="Finished",
        delivered_artifacts=[],
        pending_artifacts=[{"path": "output/report.md", "is_directory": False}],
        delivery_notes=["当前飞书应用未开通文件上传权限，已改为发送文本结果和网页链接。"],
        base_url=None,
    )

    assert "当前飞书应用未开通文件上传权限" in text
    assert "output/report.md" in text


def test_build_feishu_reply_text_suppresses_redundant_file_creation_text_when_file_delivered() -> (
    None
):
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text="✅ 文档已创建：output/fuzhou-travel-guide.md",
        delivered_artifacts=[{"path": "output/fuzhou-travel-guide.md", "is_directory": False}],
        pending_artifacts=[],
        base_url=None,
    )

    assert text == ""


def test_build_feishu_reply_text_condenses_file_content_dump_for_file_request() -> None:
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        request_text="把那个贪吃蛇的文件发给我，代码文件",
        output_text=(
            "✅ 贪吃蛇游戏代码文件已找到！\n\n"
            "文件位置：output/snake-game.html\n\n"
            "## 完整代码\n"
            "```html\n"
            "<!DOCTYPE html><html><body>...</body></html>\n"
            "```"
        ),
        delivered_artifacts=[{"path": "output/snake-game.html", "is_directory": False}],
        pending_artifacts=[],
        base_url=None,
    )

    assert "已发送" in text
    assert "完整代码" not in text
    assert "<!DOCTYPE html>" not in text


def test_build_feishu_reply_text_condenses_file_content_dump_after_delivery_even_without_request_hint() -> (
    None
):
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text=(
            "文件位置：output/final-report.md\n\n" "## 完整内容\n" "# Report\n\n" + ("A" * 1200)
        ),
        delivered_artifacts=[{"path": "output/final-report.md", "is_directory": False}],
        pending_artifacts=[],
        base_url=None,
    )

    assert "已发送" in text
    assert "完整内容" not in text
    assert "A" * 100 not in text


def test_build_feishu_reply_text_condenses_preview_into_outline_when_file_delivered() -> None:
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text=(
            "✅ **福州旅游攻略已为你准备好！**\n\n"
            "---\n\n"
            "## 📄 文件位置\n\n"
            "**普通版**：`/workspace/output/fuzhou-travel-guide.md`\n\n"
            "---\n\n"
            "## 📋 文档内容预览\n\n"
            "### 🌟 福州简介 | Introduction to Fuzhou\n\n"
            "### 🏛️ 必游景点 | Must-Visit Attractions\n\n"
            "### 🍜 美食攻略 | Food Guide\n\n"
            "### 🗺️ 行程推荐 | Suggested Itineraries\n\n"
            "### 🚗 实用信息 | Practical Information\n"
        ),
        delivered_artifacts=[{"path": "output/fuzhou-travel-guide.md", "is_directory": False}],
        pending_artifacts=[],
        base_url=None,
    )

    assert "福州旅游攻略已发送" in text
    assert "内容概览：福州简介、必游景点、美食攻略、行程推荐、实用信息。" in text
    assert "文档内容预览" not in text


def test_build_feishu_reply_text_keeps_substantive_summary_when_file_delivered() -> None:
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text=(
            "我已经整理完调研结论，并把最终报告发给你。"
            "核心建议是先验证供应商成本，再评估灰度发布窗口。"
        ),
        delivered_artifacts=[{"path": "output/final-report.md", "is_directory": False}],
        pending_artifacts=[],
        base_url=None,
    )

    assert "核心建议" in text


def test_build_feishu_reply_text_trims_dump_and_keeps_summary_prefix_when_file_delivered() -> None:
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text=(
            "已整理好报告，重点是供应商成本偏高，建议先做小流量验证。\n\n"
            "## 完整内容\n"
            "# Final Report\n\n" + ("A" * 1200)
        ),
        delivered_artifacts=[{"path": "output/final-report.md", "is_directory": False}],
        pending_artifacts=[],
        base_url=None,
    )

    assert text == "已整理好报告，重点是供应商成本偏高，建议先做小流量验证。"


def test_build_feishu_reply_text_keeps_short_summary_for_file_request() -> None:
    agent = SimpleNamespace(agent_id="agent-1")
    conversation = SimpleNamespace(conversation_id="conv-1")

    text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        request_text="把最终报告文件发我",
        output_text="报告已经发你了。重点看第 2 节的风险判断和第 4 节的上线建议。",
        delivered_artifacts=[{"path": "output/final-report.md", "is_directory": False}],
        pending_artifacts=[],
        base_url=None,
    )

    assert "重点看第 2 节" in text


def _successful_feishu_message_response() -> requests.Response:
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"code":0,"msg":"success"}'
    response.encoding = "utf-8"
    return response


def test_send_feishu_text_message_uses_plain_text_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        integrations_router,
        "_get_feishu_tenant_access_token",
        lambda _publication: "tenant-token",
    )

    def _fake_post(url: str, **kwargs) -> requests.Response:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _successful_feishu_message_response()

    monkeypatch.setattr(integrations_router.requests, "post", _fake_post)

    _send_feishu_text_message(
        SimpleNamespace(publication_id="pub-1"),
        chat_id="chat-1",
        text="**不会渲染**",
    )

    assert str(captured["url"]).endswith("/im/v1/messages")
    payload = dict(captured["kwargs"]["json"])
    assert payload["receive_id"] == "chat-1"
    assert payload["msg_type"] == "text"
    assert json.loads(str(payload["content"])) == {"text": "**不会渲染**"}


def test_send_feishu_markdown_card_message_uses_interactive_lark_md_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        integrations_router,
        "_get_feishu_tenant_access_token",
        lambda _publication: "tenant-token",
    )

    def _fake_post(url: str, **kwargs) -> requests.Response:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return _successful_feishu_message_response()

    monkeypatch.setattr(integrations_router.requests, "post", _fake_post)

    _send_feishu_markdown_card_message(
        SimpleNamespace(publication_id="pub-1"),
        chat_id="chat-1",
        markdown_text="## 标题\n- 列表项\n\n网页查看对话与工作区: https://example.com/workspace",
    )

    assert str(captured["url"]).endswith("/im/v1/messages")
    payload = dict(captured["kwargs"]["json"])
    assert payload["receive_id"] == "chat-1"
    assert payload["msg_type"] == "interactive"

    card = json.loads(str(payload["content"]))
    assert card["schema"] == "2.0"
    assert "header" not in card
    assert card["body"]["direction"] == "vertical"
    assert card["body"]["elements"][0]["tag"] == "markdown"
    assert (
        card["body"]["elements"][0]["content"]
        == "## 标题\n- 列表项\n\n[网页查看对话与工作区](https://example.com/workspace)"
    )


def test_select_feishu_deliverable_artifacts_filters_runtime_and_directories() -> None:
    artifacts = [
        {"path": "output/report.md", "is_directory": False},
        {"path": ".linx_runtime/python_deps", "is_directory": True},
        {"path": ".linx_runtime/pip_cache/wheel.whl", "is_directory": False},
        {"path": "input/source.pdf", "is_directory": False},
        {"path": "shared/summary.pdf", "is_directory": False},
    ]

    filtered = _select_feishu_deliverable_artifacts(artifacts)

    assert filtered == [
        {"path": "output/report.md", "is_directory": False},
        {"path": "shared/summary.pdf", "is_directory": False},
    ]


def test_diff_workspace_entries_returns_only_this_turn_changes() -> None:
    before = [
        {
            "path": "output/report.md",
            "is_directory": False,
            "size": 10,
            "modified_at": "2026-03-18T10:00:00+00:00",
        },
        {
            "path": "shared/existing.txt",
            "is_directory": False,
            "size": 5,
            "modified_at": "2026-03-18T10:00:00+00:00",
        },
    ]
    after = [
        {
            "path": "output/report.md",
            "is_directory": False,
            "size": 18,
            "modified_at": "2026-03-18T10:05:00+00:00",
        },
        {
            "path": "shared/existing.txt",
            "is_directory": False,
            "size": 5,
            "modified_at": "2026-03-18T10:00:00+00:00",
        },
        {
            "path": ".linx_runtime/python_deps/site.py",
            "is_directory": False,
            "size": 20,
            "modified_at": "2026-03-18T10:05:00+00:00",
        },
    ]

    delta = _diff_workspace_entries(before, after)

    assert delta == [
        {
            "path": "output/report.md",
            "is_directory": False,
            "size": 18,
            "modified_at": "2026-03-18T10:05:00+00:00",
        },
        {
            "path": ".linx_runtime/python_deps/site.py",
            "is_directory": False,
            "size": 20,
            "modified_at": "2026-03-18T10:05:00+00:00",
        },
    ]


def test_format_feishu_api_error_includes_missing_scopes() -> None:
    message = _format_feishu_api_error(
        {
            "code": 99991672,
            "msg": "Access denied",
            "error": {
                "permission_violations": [
                    {"subject": "im:resource:upload"},
                    {"subject": "im:resource"},
                ]
            },
        },
        default_error="Failed to upload Feishu file",
    )

    assert "Failed to upload Feishu file: Access denied" in message
    assert "code=99991672" in message
    assert "missing_scopes=im:resource,im:resource:upload" in message


def test_classify_feishu_file_delivery_error_handles_missing_scope() -> None:
    exc = RuntimeError(
        "Failed to upload Feishu file: Access denied "
        "(code=99991672; missing_scopes=im:resource,im:resource:upload)"
    )

    note = _classify_feishu_file_delivery_error(exc)

    assert note == "当前飞书应用未开通文件上传权限，已改为发送文本结果和网页链接。"


def test_classify_feishu_file_delivery_error_handles_transient_failure() -> None:
    exc = FeishuApiError(
        "Failed to upload Feishu file (http_status=429; log_id=log-1)",
        status_code=429,
        log_id="log-1",
    )

    note = _classify_feishu_file_delivery_error(exc)

    assert note == "飞书文件接口暂时不可用，多次重试后仍失败，已改为发送文本结果和网页链接。"


def test_queued_feishu_file_delivery_note_mentions_background_retry() -> None:
    assert (
        _queued_feishu_file_delivery_note()
        == "飞书文件接口暂时不可用，系统会在后台继续重试发送；当前先发送文本结果和网页链接。"
    )


def test_parse_feishu_json_response_preserves_http_context_for_non_json_failure() -> None:
    response = requests.Response()
    response.status_code = 400
    response._content = b"bad multipart request"
    response.encoding = "utf-8"
    response.headers["X-Tt-Logid"] = "log-123"

    with pytest.raises(FeishuApiError) as exc_info:
        _parse_feishu_json_response(
            response,
            default_error="Failed to upload Feishu file",
        )

    exc = exc_info.value
    assert exc.status_code == 400
    assert exc.log_id == "log-123"
    assert exc.response_preview == "bad multipart request"
    assert "http_status=400" in str(exc)
    assert "log_id=log-123" in str(exc)


def test_feishu_file_delivery_retry_service_requeues_retryable_failures(monkeypatch) -> None:
    service = FeishuFileDeliveryRetryService()
    enqueued: list[tuple[_QueuedFeishuFileDelivery, float]] = []

    monkeypatch.setattr(
        integrations_router,
        "_load_feishu_publication_for_retry",
        lambda _publication_id: SimpleNamespace(publication_id="pub-1"),
    )

    def _fake_send(*_args, **_kwargs) -> None:
        raise FeishuApiError(
            "Failed to upload Feishu file (http_status=429; log_id=retry-log)",
            status_code=429,
            log_id="retry-log",
        )

    monkeypatch.setattr(integrations_router, "_send_feishu_file_bytes_message", _fake_send)
    monkeypatch.setattr(
        service,
        "enqueue",
        lambda job, delay_seconds=0.0: enqueued.append((job, delay_seconds)) or True,
    )

    service._process_job(
        _QueuedFeishuFileDelivery(
            publication_id="pub-1",
            conversation_id="conv-1",
            chat_id="chat-1",
            artifact_path="output/report.md",
            file_name="report.md",
            file_bytes=b"hello",
        )
    )

    assert len(enqueued) == 1
    queued_job, delay = enqueued[0]
    assert queued_job.attempt == 2
    assert queued_job.max_attempts == 3
    assert delay == 0.5


def test_feishu_file_delivery_retry_service_stops_on_non_retryable_failures(monkeypatch) -> None:
    service = FeishuFileDeliveryRetryService()
    enqueued: list[tuple[_QueuedFeishuFileDelivery, float]] = []

    monkeypatch.setattr(
        integrations_router,
        "_load_feishu_publication_for_retry",
        lambda _publication_id: SimpleNamespace(publication_id="pub-1"),
    )

    def _fake_send(*_args, **_kwargs) -> None:
        raise FeishuApiError(
            "Failed to upload Feishu file: Access denied "
            "(code=99991672; missing_scopes=im:resource:upload; http_status=400; log_id=log-1)",
            status_code=400,
            error_code=99991672,
            log_id="log-1",
        )

    monkeypatch.setattr(integrations_router, "_send_feishu_file_bytes_message", _fake_send)
    monkeypatch.setattr(
        service,
        "enqueue",
        lambda job, delay_seconds=0.0: enqueued.append((job, delay_seconds)) or True,
    )

    service._process_job(
        _QueuedFeishuFileDelivery(
            publication_id="pub-1",
            conversation_id="conv-1",
            chat_id="chat-1",
            artifact_path="output/report.md",
            file_name="report.md",
            file_bytes=b"hello",
        )
    )

    assert enqueued == []


def test_select_feishu_explicitly_requested_artifacts_matches_existing_file() -> None:
    artifacts = [
        {"path": "output/report.md", "is_directory": False},
        {"path": "shared/plan.txt", "is_directory": False},
        {"path": ".linx_runtime/cache.bin", "is_directory": False},
    ]

    matched = _select_feishu_explicitly_requested_artifacts(
        artifacts,
        "把 output/report.md 发我",
    )

    assert matched == [{"path": "output/report.md", "is_directory": False}]


def test_select_feishu_explicitly_requested_artifacts_matches_unique_basename() -> None:
    artifacts = [
        {"path": "output/fuzhou-travel-guide.md", "is_directory": False},
        {"path": "shared/plan.txt", "is_directory": False},
    ]

    matched = _select_feishu_explicitly_requested_artifacts(
        artifacts,
        "请把 fuzhou-travel-guide.md 发给我",
    )

    assert matched == [{"path": "output/fuzhou-travel-guide.md", "is_directory": False}]


def test_looks_like_feishu_file_send_request_detects_intent() -> None:
    assert _looks_like_feishu_file_send_request("把 output/report.md 发我") is True
    assert _looks_like_feishu_file_send_request("把那个贪吃蛇的文件发给我，代码文件") is True
    assert _looks_like_feishu_file_send_request("帮我总结这个需求") is False


def test_resolve_feishu_artifact_file_paths_returns_existing_files(monkeypatch, tmp_path) -> None:
    runtime = SimpleNamespace(workdir=str(tmp_path))
    workspace_file = tmp_path / "output" / "report.md"
    workspace_file.parent.mkdir(parents=True, exist_ok=True)
    workspace_file.write_text("hello", encoding="utf-8")
    conversation = SimpleNamespace(conversation_id="conv-1")

    monkeypatch.setattr(
        integrations_router,
        "get_persistent_conversation_runtime_service",
        lambda: SimpleNamespace(get_active_runtime=lambda _conversation_id: runtime),
    )

    resolved = _resolve_feishu_artifact_file_paths(
        conversation,
        [{"path": "output/report.md", "is_directory": False}],
    )

    assert resolved == [
        (
            {"path": "output/report.md", "is_directory": False},
            workspace_file,
        )
    ]


@pytest.mark.asyncio
async def test_prepare_feishu_message_uploads_downloads_file_attachment(monkeypatch) -> None:
    publication = SimpleNamespace(publication_id="pub-1")
    message = {
        "message_type": "file",
        "message_id": "msg-file-1",
        "content_payload": {
            "file_key": "file-key-1",
            "file_name": "spec.pdf",
        },
    }

    monkeypatch.setattr(
        integrations_router,
        "_download_feishu_message_attachment",
        lambda *_args, **_kwargs: (b"pdf-bytes", "spec.pdf"),
    )

    uploads = await _prepare_feishu_message_uploads(
        publication=publication,
        message=message,
    )

    assert len(uploads) == 1
    assert uploads[0].filename == "spec.pdf"
    assert uploads[0].content_type == "application/pdf"
    assert await uploads[0].read() == b"pdf-bytes"


def test_feishu_long_connection_manager_reconciles_worker_lifecycle() -> None:
    manager = FeishuLongConnectionManager()
    manager._ctx = SimpleNamespace(Process=lambda *args, **kwargs: _FakeProcess(*args, **kwargs))

    first_target = FeishuPublicationTarget(publication_id="pub-1", config_fingerprint="fp-1")
    manager._reconcile_workers({"pub-1": first_target})

    first_worker = manager._workers["pub-1"]
    first_pid = first_worker.process.pid
    assert first_worker.process.is_alive() is True

    manager._reconcile_workers(
        {"pub-1": FeishuPublicationTarget(publication_id="pub-1", config_fingerprint="fp-1")}
    )
    same_worker = manager._workers["pub-1"]
    assert same_worker.process.pid == first_pid

    first_worker.process.terminate()
    manager._reconcile_workers({"pub-1": first_target})

    restarted_worker = manager._workers["pub-1"]
    assert restarted_worker.process.is_alive() is True
    assert restarted_worker.process.pid != first_pid

    updated_target = FeishuPublicationTarget(publication_id="pub-1", config_fingerprint="fp-2")
    manager._reconcile_workers({"pub-1": updated_target})

    updated_worker = manager._workers["pub-1"]
    assert updated_worker.process.is_alive() is True
    assert updated_worker.process.pid != restarted_worker.process.pid

    manager._reconcile_workers({})
    assert manager._workers == {}


def test_resolve_feishu_long_connection_proxy_uses_system_mode_by_default(monkeypatch) -> None:
    monkeypatch.delenv("FEISHU_LONG_CONNECTION_PROXY_MODE", raising=False)
    monkeypatch.delenv("FEISHU_LONG_CONNECTION_PROXY_URL", raising=False)
    monkeypatch.setattr(
        feishu_long_connection,
        "get_config",
        lambda: SimpleNamespace(get=lambda key, default=None: default),
    )

    mode, proxy = _resolve_feishu_long_connection_proxy()

    assert mode == "system"
    assert proxy is True


def test_resolve_feishu_long_connection_proxy_supports_explicit_mode(monkeypatch) -> None:
    monkeypatch.setenv("FEISHU_LONG_CONNECTION_PROXY_MODE", "explicit")
    monkeypatch.setenv("FEISHU_LONG_CONNECTION_PROXY_URL", "socks5://127.0.0.1:7890")
    monkeypatch.setattr(
        feishu_long_connection,
        "get_config",
        lambda: SimpleNamespace(get=lambda key, default=None: default),
    )

    mode, proxy = _resolve_feishu_long_connection_proxy()

    assert mode == "explicit"
    assert proxy == "socks5://127.0.0.1:7890"
