from __future__ import annotations

from types import SimpleNamespace

from api_gateway import feishu_long_connection
from api_gateway.feishu_long_connection import (
    FeishuLongConnectionManager,
    FeishuPublicationTarget,
    _resolve_feishu_long_connection_proxy,
)
from api_gateway.routers.integrations import (
    _build_feishu_reply_text,
    _extract_feishu_message_from_long_connection_event,
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
        "message_type": "text",
        "chat_id": "chat-1",
        "chat_type": "p2p",
        "thread_key": "root-1",
        "text": "hello from feishu",
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
        artifacts=[{"path": "output/report.md", "is_dir": False}],
        base_url=None,
    )

    assert "Finished" in text
    assert "/workspace/output/report.md" in text
    assert "workforce/agent-1/conversations/conv-1" not in text


def test_feishu_long_connection_manager_reconciles_worker_lifecycle() -> None:
    manager = FeishuLongConnectionManager()
    manager._ctx = SimpleNamespace(Process=lambda *args, **kwargs: _FakeProcess(*args, **kwargs))

    first_target = FeishuPublicationTarget(publication_id="pub-1", config_fingerprint="fp-1")
    manager._reconcile_workers({"pub-1": first_target})

    first_worker = manager._workers["pub-1"]
    first_pid = first_worker.process.pid
    assert first_worker.process.is_alive() is True

    manager._reconcile_workers({"pub-1": FeishuPublicationTarget(publication_id="pub-1", config_fingerprint="fp-1")})
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
