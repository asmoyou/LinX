"""Unit tests for mission notification service."""

from types import SimpleNamespace
from uuid import uuid4

from mission_system.notification_service import create_notifications_for_mission_event


def test_create_notifications_for_clarification_event(monkeypatch):
    mission_id = uuid4()
    event_id = uuid4()
    owner_user_id = uuid4()

    monkeypatch.setattr(
        "mission_system.notification_service.get_mission",
        lambda _mission_id: SimpleNamespace(
            mission_id=mission_id,
            title="订单流程优化",
            created_by_user_id=owner_user_id,
        ),
    )

    captured = {}

    def _fake_create_user_notification(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "mission_system.notification_service.create_user_notification",
        _fake_create_user_notification,
    )

    create_notifications_for_mission_event(
        event_id=event_id,
        mission_id=mission_id,
        event_type="USER_CLARIFICATION_REQUESTED",
        data={"questions": "请确认是否需要支持多租户？"},
        message=None,
    )

    assert captured["user_id"] == owner_user_id
    assert captured["notification_type"] == "mission_clarification_required"
    assert captured["severity"] == "warning"
    assert captured["action_url"].endswith(f"{mission_id}&focus=clarification")
    assert "支持多租户" in captured["message"]
    assert captured["dedupe_key"] == f"mission-event:{event_id}"


def test_create_notifications_for_qa_fail_event(monkeypatch):
    mission_id = uuid4()
    event_id = uuid4()
    owner_user_id = uuid4()

    monkeypatch.setattr(
        "mission_system.notification_service.get_mission",
        lambda _mission_id: SimpleNamespace(
            mission_id=mission_id,
            title="支付回调接口改造",
            created_by_user_id=owner_user_id,
        ),
    )

    captured = {}

    def _fake_create_user_notification(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "mission_system.notification_service.create_user_notification",
        _fake_create_user_notification,
    )

    create_notifications_for_mission_event(
        event_id=event_id,
        mission_id=mission_id,
        event_type="QA_VERDICT",
        data={"verdict": "FAIL", "summary": "缺少边界条件用例"},
        message=None,
    )

    assert captured["notification_type"] == "mission_qa_failed"
    assert captured["severity"] == "warning"
    assert "缺少边界条件用例" in captured["message"]


def test_create_notifications_for_qa_pass_event_skips(monkeypatch):
    mission_id = uuid4()
    event_id = uuid4()

    monkeypatch.setattr(
        "mission_system.notification_service.get_mission",
        lambda _mission_id: SimpleNamespace(
            mission_id=mission_id,
            title="报表导出优化",
            created_by_user_id=uuid4(),
        ),
    )

    created = []

    def _fake_create_user_notification(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr(
        "mission_system.notification_service.create_user_notification",
        _fake_create_user_notification,
    )

    create_notifications_for_mission_event(
        event_id=event_id,
        mission_id=mission_id,
        event_type="QA_VERDICT",
        data={"verdict": "PASS", "summary": "校验通过"},
        message=None,
    )

    assert created == []
