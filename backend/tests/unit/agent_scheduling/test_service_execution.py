import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace
from uuid import uuid4

import pytest

import agent_scheduling.service as schedule_service


def test_build_schedule_execution_prompt_marks_triggered_run() -> None:
    schedule = SimpleNamespace(
        name="去超市买菜",
        schedule_type="once",
        timezone="Asia/Shanghai",
        prompt_template="提醒我去超市买菜",
    )
    run = SimpleNamespace(
        scheduled_for=datetime(2026, 3, 20, 8, 30, tzinfo=timezone.utc),
    )

    prompt = schedule_service._build_schedule_execution_prompt(
        schedule=schedule,
        run=run,
    )

    assert "不是用户刚刚发送的新消息" in prompt
    assert "不要再次创建、修改或查询这个定时任务" in prompt
    assert "去超市买菜" in prompt
    assert "提醒我去超市买菜" in prompt


@pytest.mark.asyncio
async def test_execute_schedule_run_uses_schedule_trigger_semantics(monkeypatch) -> None:
    owner = SimpleNamespace(
        user_id=uuid4(),
        role="admin",
        username="alice",
    )
    conversation = SimpleNamespace(
        conversation_id=uuid4(),
        status="active",
        source="web",
    )
    schedule = SimpleNamespace(
        schedule_id=uuid4(),
        name="去超市买菜",
        prompt_template="提醒我去超市买菜",
        schedule_type="once",
        timezone="Asia/Shanghai",
        bound_conversation_id=conversation.conversation_id,
        bound_conversation=conversation,
        owner=owner,
        status="active",
        next_run_at=datetime(2026, 3, 20, 8, 30, tzinfo=timezone.utc),
        last_run_at=None,
        last_run_status=None,
        last_error=None,
    )
    run = SimpleNamespace(
        run_id=uuid4(),
        schedule=schedule,
        scheduled_for=datetime(2026, 3, 20, 8, 30, tzinfo=timezone.utc),
        status="queued",
        completed_at=None,
        error_message=None,
        conversation_id=None,
        assistant_message_id=None,
        delivery_channel=None,
    )

    @contextmanager
    def _fake_session():
        yield SimpleNamespace()

    captured: dict = {}

    async def _fake_execute_persistent_conversation_turn(**kwargs):
        captured.update(kwargs)
        return {
            "output": "该去超市买菜了。",
            "assistant_message_id": str(uuid4()),
            "artifact_delta": [],
            "artifacts": [],
        }

    monkeypatch.setattr(schedule_service, "get_db_session", _fake_session)
    monkeypatch.setattr(
        schedule_service,
        "_load_run_for_execution",
        lambda _session, run_id: run,
    )
    fake_conversations_module = ModuleType("api_gateway.routers.agent_conversations")
    fake_conversations_module.execute_persistent_conversation_turn = (
        _fake_execute_persistent_conversation_turn
    )
    monkeypatch.setitem(
        sys.modules,
        "api_gateway.routers.agent_conversations",
        fake_conversations_module,
    )

    async def _fake_deliver_to_feishu_if_needed(**_kwargs):
        return "web"

    monkeypatch.setattr(
        schedule_service,
        "_deliver_to_feishu_if_needed",
        _fake_deliver_to_feishu_if_needed,
    )

    result = await schedule_service.execute_schedule_run(run_id=str(run.run_id))

    assert result.status == "succeeded"
    assert captured["source"] == "schedule"
    assert captured["persist_input_message"] is True
    assert captured["input_message_role"] == "system"
    assert captured["input_message_text"] == "定时任务已触发：去超市买菜"
    assert captured["context_origin_surface"] == "persistent_chat"
    assert captured["message"] == "提醒我去超市买菜"
    assert captured["title_seed_text"] == "去超市买菜"
    assert captured["extra_execution_context"]["schedule_triggered"] is True
    assert captured["extra_execution_context"]["schedule_id"] == str(schedule.schedule_id)
    assert "不是用户刚刚发送的新消息" in captured["execution_task_text"]
    assert schedule.status == "completed"
    assert schedule.next_run_at is None


@pytest.mark.asyncio
async def test_deliver_to_feishu_if_needed_uses_markdown_card_message(monkeypatch) -> None:
    from api_gateway.routers import integrations as integrations_router

    publication = SimpleNamespace(status="published")
    conversation = SimpleNamespace(
        source="feishu",
        external_links=[
            SimpleNamespace(
                publication=publication,
                external_chat_key="chat-1",
            )
        ],
    )
    schedule = SimpleNamespace(
        agent=SimpleNamespace(name="日报助手"),
        bound_conversation=conversation,
    )
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        integrations_router,
        "_build_feishu_reply_text",
        lambda **_kwargs: "## 今日总结\n- 第一项",
    )

    def _fake_send(publication_obj, *, chat_id: str, markdown_text: str) -> None:
        captured["publication"] = publication_obj
        captured["chat_id"] = chat_id
        captured["markdown_text"] = markdown_text

    monkeypatch.setattr(
        integrations_router,
        "_send_feishu_markdown_card_message",
        _fake_send,
    )

    channel = await schedule_service._deliver_to_feishu_if_needed(
        schedule=schedule,
        result={"output": "## 今日总结", "artifact_delta": [], "artifacts": []},
    )

    assert channel == "feishu"
    assert captured == {
        "publication": publication,
        "chat_id": "chat-1",
        "markdown_text": "## 今日总结\n- 第一项",
    }
