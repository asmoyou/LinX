"""Unit tests for first-run platform setup endpoints."""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException, status

from api_gateway.routers.auth import (
    InitializePlatformRequest,
    _build_setup_status,
    _validate_timezone_name,
    initialize_platform,
)


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
        self.commit_called = False

    def query(self, *_args, **_kwargs):
        return _UserLookupQuery(self._user)

    def commit(self):
        self.commit_called = True


def _session_context(session):
    @contextmanager
    def _ctx():
        yield session

    return _ctx


def test_validate_timezone_name_accepts_iana_timezone():
    assert _validate_timezone_name("Asia/Shanghai") == "Asia/Shanghai"


def test_validate_timezone_name_rejects_invalid_timezone():
    with pytest.raises(HTTPException) as exc_info:
        _validate_timezone_name("Mars/Olympus")

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == "Invalid timezone"


def test_build_setup_status_uses_bootstrap_metadata():
    with patch("api_gateway.routers.auth._has_admin_account", return_value=True):
        with patch(
            "api_gateway.routers.auth.get_platform_setting",
            return_value={
                "default_admin_username": "admin",
                "initialized_at": "2026-03-11T12:00:00+00:00",
                "language": "zh",
                "timezone": "Asia/Shanghai",
            },
        ):
            response = _build_setup_status(session=object())

    assert response.requires_setup is False
    assert response.has_admin_account is True
    assert response.default_admin_username == "admin"
    assert response.language == "zh"
    assert response.timezone == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_initialize_platform_creates_admin_and_returns_tokens():
    fake_user = SimpleNamespace(
        user_id="user-1",
        username="admin",
        email="admin@example.com",
        role="admin",
        attributes={},
    )
    session = _SessionStub(fake_user)
    request = InitializePlatformRequest(
        email="admin@example.com",
        password="SecurePassword123!",
        language="zh",
        timezone="Asia/Shanghai",
        theme="dark",
    )
    http_request = SimpleNamespace(
        headers={"user-agent": "pytest"},
        client=SimpleNamespace(host="127.0.0.1"),
    )

    def _register_user_admin(*_args, **kwargs):
        fake_user.attributes = dict(kwargs["attributes"])
        return SimpleNamespace(
            user_id="user-1",
            username="admin",
            role="admin",
        )

    with patch("database.connection.get_db_session", _session_context(session)):
        with patch("api_gateway.routers.auth._has_admin_account", return_value=False):
            with patch(
                "api_gateway.routers.auth.register_user_admin",
                side_effect=_register_user_admin,
            ) as register_mock:
                with patch("api_gateway.routers.auth.upsert_platform_setting") as upsert_mock:
                    with patch(
                        "api_gateway.routers.auth.create_token_pair",
                        return_value=SimpleNamespace(
                            access_token="access-token",
                            refresh_token="refresh-token",
                            token_type="bearer",
                            expires_in=3600,
                        ),
                    ):
                        with patch(
                            "api_gateway.routers.auth.decode_token",
                            return_value=SimpleNamespace(
                                session_id="session-1",
                                jti="token-jti",
                            ),
                        ):
                            with patch("api_gateway.routers.auth.log_authentication_event"):
                                with patch("sqlalchemy.orm.attributes.flag_modified"):
                                    response = await initialize_platform(
                                        request=request,
                                        http_request=http_request,
                                    )

    assert response.access_token == "access-token"
    assert response.refresh_token == "refresh-token"
    assert response.user["username"] == "admin"
    assert fake_user.attributes["preferences"]["timezone"] == "Asia/Shanghai"
    assert fake_user.attributes["preferences"]["language"] == "zh"
    assert fake_user.attributes["security_sessions"][0]["session_id"] == "session-1"
    assert session.commit_called is True
    register_mock.assert_called_once()
    upsert_mock.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_platform_rejects_when_admin_already_exists():
    session = _SessionStub(user=None)
    request = InitializePlatformRequest(
        email="admin@example.com",
        password="SecurePassword123!",
        language="en",
        timezone="UTC",
        theme="system",
    )
    http_request = SimpleNamespace(headers={}, client=None)

    with patch("database.connection.get_db_session", _session_context(session)):
        with patch("api_gateway.routers.auth._has_admin_account", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                await initialize_platform(request=request, http_request=http_request)

    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.detail == "Platform has already been initialized"
