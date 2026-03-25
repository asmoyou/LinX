from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.routers.telemetry as telemetry_router
from access_control.permissions import CurrentUser


class _MetricStub:
    def __init__(self):
        self.calls = []
        self._labels = {}

    def labels(self, **labels):
        self._labels = labels
        return self

    def inc(self, value=1):
        self.calls.append(("inc", dict(self._labels), value))

    def observe(self, value):
        self.calls.append(("observe", dict(self._labels), value))


class _UserLookupQuery:
    def __init__(self, user):
        self._user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._user


class _SessionStub:
    def __init__(self, user):
        self._user = user

    def query(self, *_args, **_kwargs):
        return _UserLookupQuery(self._user)


def _session_context(session):
    @contextmanager
    def _ctx():
        yield session

    return _ctx


def _build_client(
    monkeypatch: pytest.MonkeyPatch, user_attributes: dict | None = None
) -> tuple[TestClient, dict[str, _MetricStub]]:
    app = FastAPI()
    app.include_router(telemetry_router.router, prefix="/api/v1/telemetry")
    app.dependency_overrides[telemetry_router.get_current_user] = lambda: CurrentUser(
        user_id="user-1",
        username="alice",
        role="user",
        session_id="session-1",
    )

    user = SimpleNamespace(
        user_id="user-1",
        attributes=user_attributes or {"privacy": {"allow_telemetry": True}},
    )
    monkeypatch.setattr(telemetry_router, "get_db_session", _session_context(_SessionStub(user)))

    metrics = {
        "reports": _MetricStub(),
        "avg_fps": _MetricStub(),
        "p95_frame_ms": _MetricStub(),
        "long_tasks": _MetricStub(),
        "downgrades": _MetricStub(),
    }
    monkeypatch.setattr(telemetry_router, "frontend_motion_reports_total", metrics["reports"])
    monkeypatch.setattr(telemetry_router, "frontend_motion_avg_fps", metrics["avg_fps"])
    monkeypatch.setattr(telemetry_router, "frontend_motion_p95_frame_ms", metrics["p95_frame_ms"])
    monkeypatch.setattr(telemetry_router, "frontend_motion_long_tasks_total", metrics["long_tasks"])
    monkeypatch.setattr(
        telemetry_router,
        "frontend_motion_downgrades_total",
        metrics["downgrades"],
    )

    return TestClient(app), metrics


def _build_payload() -> dict:
    return {
        "route_group": "/dashboard",
        "effective_tier": "reduced",
        "motion_preference": "auto",
        "os_reduced_motion": False,
        "save_data": False,
        "device_class": "standard",
        "avg_fps": 48.5,
        "p95_frame_ms": 24.1,
        "long_task_count": 3,
        "downgrade_count": 1,
        "sampled_at": "2026-01-01T00:00:00Z",
        "app_version": "test",
    }


def test_frontend_motion_summary_records_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    client, metrics = _build_client(monkeypatch)

    response = client.post("/api/v1/telemetry/frontend-motion-summary", json=_build_payload())

    assert response.status_code == 202
    assert metrics["reports"].calls == [
        (
            "inc",
            {
                "route_group": "/dashboard",
                "effective_tier": "reduced",
                "device_class": "standard",
            },
            1,
        )
    ]
    assert metrics["avg_fps"].calls[0] == (
        "observe",
        {
            "route_group": "/dashboard",
            "effective_tier": "reduced",
        },
        48.5,
    )
    assert metrics["long_tasks"].calls[0][2] == 3
    assert metrics["downgrades"].calls[0][2] == 1


def test_frontend_motion_summary_respects_privacy_opt_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, metrics = _build_client(
        monkeypatch,
        user_attributes={"privacy": {"allow_telemetry": False}},
    )

    response = client.post("/api/v1/telemetry/frontend-motion-summary", json=_build_payload())

    assert response.status_code == 202
    assert metrics["reports"].calls == []
    assert metrics["avg_fps"].calls == []


def test_frontend_motion_summary_validates_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _metrics = _build_client(monkeypatch)
    payload = _build_payload()
    payload["device_class"] = "ultra"

    response = client.post("/api/v1/telemetry/frontend-motion-summary", json=payload)

    assert response.status_code == 422
