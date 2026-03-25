from contextlib import contextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from access_control.permissions import CurrentUser
from api_gateway.routers.users import (
    BindingCodeResponse,
    _serialize_binding_code,
    get_current_user_binding_code,
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

    def query(self, *_args, **_kwargs):
        return _UserLookupQuery(self._user)


def _session_context(session):
    @contextmanager
    def _ctx():
        yield session

    return _ctx


def _binding_code_row(code_id=None):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        code_id=code_id or uuid4(),
        code_encrypted="encrypted",
        status="active",
        rotated_at=None,
        last_used_at=None,
        created_at=now,
        updated_at=now,
    )


def test_serialize_binding_code_rejects_undecryptable_payload() -> None:
    with patch("api_gateway.routers.users.decrypt_text", return_value=None):
        with pytest.raises(ValueError, match="could not be decrypted"):
            _serialize_binding_code(_binding_code_row())


@pytest.mark.asyncio
async def test_get_current_user_binding_code_rotates_code_after_decrypt_failure() -> None:
    user_id = uuid4()
    session = _SessionStub(SimpleNamespace(user_id=user_id))
    stale_row = _binding_code_row()
    fresh_row = _binding_code_row()
    expected = BindingCodeResponse(
        code="ABCD1234EFGH",
        masked_code="ABCD****EFGH",
        status="active",
        rotated_at=None,
        last_used_at=None,
        created_at=fresh_row.created_at.isoformat(),
        updated_at=fresh_row.updated_at.isoformat(),
    )

    with patch("api_gateway.routers.users.get_db_session", _session_context(session)):
        with patch("api_gateway.routers.users._get_or_create_active_binding_code", return_value=stale_row):
            with patch("api_gateway.routers.users._refresh_active_binding_code", return_value=fresh_row) as refresh_mock:
                with patch(
                    "api_gateway.routers.users._serialize_binding_code",
                    side_effect=[ValueError("Binding code could not be decrypted"), expected],
                ) as serialize_mock:
                    response = await get_current_user_binding_code(
                        current_user=CurrentUser(
                            user_id=str(user_id),
                            username="alice",
                            role="user",
                        )
                    )

    assert response == expected
    refresh_mock.assert_called_once_with(session, user_id)
    assert serialize_mock.call_count == 2


@pytest.mark.asyncio
async def test_get_current_user_binding_code_rejects_invalid_user_ids() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_binding_code(
            current_user=CurrentUser(
                user_id="not-a-uuid",
                username="alice",
                role="user",
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid user ID"
