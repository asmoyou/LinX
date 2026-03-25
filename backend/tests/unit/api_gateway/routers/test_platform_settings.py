from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.routers.platform_settings as platform_settings_router
from access_control.permissions import CurrentUser


class _SessionStub:
    def __init__(self):
        self.commit_called = False

    def commit(self):
        self.commit_called = True


def _session_context(session):
    @contextmanager
    def _ctx():
        yield session

    return _ctx


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    session = _SessionStub()
    app = FastAPI()
    app.include_router(platform_settings_router.router, prefix="/api/v1/platform")
    monkeypatch.setattr(platform_settings_router, "get_db_session", _session_context(session))
    app.state.session = session
    return TestClient(app)


def test_get_ui_experience_returns_platform_settings(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.app.dependency_overrides[platform_settings_router.get_current_user] = (
        lambda: CurrentUser(user_id="admin-1", username="admin", role="admin")
    )
    monkeypatch.setattr(
        platform_settings_router,
        "get_ui_experience_settings",
        lambda _session: {
            "default_motion_preference": "reduced",
            "emergency_disable_motion": False,
            "telemetry_sample_rate": 0.25,
        },
    )

    response = client.get("/api/v1/platform/settings/ui-experience")

    assert response.status_code == 200
    assert response.json() == {
        "default_motion_preference": "reduced",
        "emergency_disable_motion": False,
        "telemetry_sample_rate": 0.25,
    }


def test_update_ui_experience_accepts_manager_role(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict = {}
    client.app.dependency_overrides[platform_settings_router.get_current_user] = (
        lambda: CurrentUser(user_id="manager-1", username="manager", role="manager")
    )

    def _capture_update(session, value):
        captured["session"] = session
        captured["value"] = value

    monkeypatch.setattr(platform_settings_router, "upsert_ui_experience_settings", _capture_update)

    response = client.put(
        "/api/v1/platform/settings/ui-experience",
        json={
            "default_motion_preference": "off",
            "emergency_disable_motion": True,
            "telemetry_sample_rate": 0.1,
        },
    )

    assert response.status_code == 200
    assert response.json()["default_motion_preference"] == "off"
    assert captured["value"]["emergency_disable_motion"] is True
    assert client.app.state.session.commit_called is True


def test_update_ui_experience_rejects_non_admin_roles(client: TestClient) -> None:
    client.app.dependency_overrides[platform_settings_router.get_current_user] = (
        lambda: CurrentUser(user_id="user-1", username="alice", role="user")
    )

    response = client.put(
        "/api/v1/platform/settings/ui-experience",
        json={
            "default_motion_preference": "full",
            "emergency_disable_motion": False,
            "telemetry_sample_rate": 0.2,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions to manage platform UI settings"
