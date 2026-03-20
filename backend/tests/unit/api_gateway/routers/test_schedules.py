from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from access_control.permissions import CurrentUser
from agent_scheduling.cron_utils import ScheduleValidationError
import api_gateway.routers.schedules as schedules_router


def _build_schedule_payload() -> dict:
    return {
        "id": "schedule-1",
        "ownerUserId": "user-1",
        "ownerUsername": "alice",
        "agentId": "agent-1",
        "agentName": "Daily Agent",
        "boundConversationId": "conversation-1",
        "boundConversationTitle": "Daily Standup",
        "boundConversationSource": "web",
        "name": "日报提醒",
        "promptTemplate": "提醒我写日报",
        "scheduleType": "recurring",
        "cronExpression": "0 9 * * 1-5",
        "runAtUtc": None,
        "timezone": "Asia/Shanghai",
        "status": "active",
        "createdVia": "agent_auto",
        "originSurface": "persistent_chat",
        "originMessageId": "message-1",
        "nextRunAt": "2025-01-02T01:00:00+00:00",
        "lastRunAt": None,
        "lastRunStatus": None,
        "lastError": None,
        "createdAt": "2025-01-01T00:00:00+00:00",
        "updatedAt": "2025-01-01T00:00:00+00:00",
        "latestRun": None,
    }


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(schedules_router.router, prefix="/api/v1/schedules")
    app.dependency_overrides[schedules_router.get_current_user] = lambda: CurrentUser(
        user_id="user-1",
        username="alice",
        role="admin",
    )
    return TestClient(app)


def test_preview_schedule_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        schedules_router,
        "preview_schedule_payload",
        lambda **_: {
            "is_valid": True,
            "human_summary": "Every weekday at 09:00 (Asia/Shanghai)",
            "normalized_cron": "0 9 * * 1-5",
            "next_occurrences": ["2025-01-02T01:00:00+00:00"],
        },
    )

    response = client.post(
        "/api/v1/schedules/preview",
        json={
            "scheduleType": "recurring",
            "timezone": "Asia/Shanghai",
            "cronExpression": "0 9 * * 1-5",
        },
    )

    assert response.status_code == 200
    assert response.json()["normalized_cron"] == "0 9 * * 1-5"


def test_preview_schedule_translates_validation_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_validation_error(**_kwargs):
        raise ScheduleValidationError("Invalid cron expression")

    monkeypatch.setattr(schedules_router, "preview_schedule_payload", _raise_validation_error)

    response = client.post(
        "/api/v1/schedules/preview",
        json={
            "scheduleType": "recurring",
            "timezone": "Asia/Shanghai",
            "cronExpression": "bad cron",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Invalid cron expression"


def test_list_schedules_passes_filters_to_service(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}

    def _fake_list_schedules(**kwargs):
        captured.update(kwargs)
        return ([_build_schedule_payload()], 1)

    monkeypatch.setattr(schedules_router, "list_schedules", _fake_list_schedules)

    response = client.get(
        "/api/v1/schedules",
        params={
            "scope": "all",
            "status": "active",
            "type": "recurring",
            "createdVia": "agent_auto",
            "agentId": "agent-1",
            "query": "日报",
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert captured == {
        "viewer_user_id": "user-1",
        "viewer_role": "admin",
        "scope": "all",
        "status_filter": "active",
        "schedule_type": "recurring",
        "created_via": "agent_auto",
        "agent_id": "agent-1",
        "query_text": "日报",
        "limit": 50,
        "offset": 0,
    }


def test_create_schedule_returns_created_event(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_payload = _build_schedule_payload()
    event_payload = {
        "schedule_id": "schedule-1",
        "agent_id": "agent-1",
        "name": "日报提醒",
        "status": "active",
        "next_run_at": "2025-01-02T01:00:00+00:00",
        "timezone": "Asia/Shanghai",
        "created_via": "manual_ui",
        "bound_conversation_id": "conversation-1",
        "bound_conversation_title": "Daily Standup",
        "origin_surface": "schedule_page",
    }

    monkeypatch.setattr(schedules_router, "create_schedule", lambda **_: schedule_payload)
    monkeypatch.setattr(schedules_router, "build_schedule_created_event", lambda *_: event_payload)

    response = client.post(
        "/api/v1/schedules",
        json={
            "agentId": "agent-1",
            "name": "日报提醒",
            "promptTemplate": "提醒我写日报",
            "scheduleType": "recurring",
            "cronExpression": "0 9 * * 1-5",
            "timezone": "Asia/Shanghai",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["schedule"]["id"] == "schedule-1"
    assert body["createdEvent"]["schedule_id"] == "schedule-1"
