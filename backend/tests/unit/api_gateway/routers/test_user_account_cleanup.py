from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from access_control.permissions import CurrentUser
from api_gateway.routers.users import DeleteAccountRequest, delete_current_user_account


class _UserQuery:
    def __init__(self, user):
        self._user = user

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._user


class _SessionStub:
    def __init__(self, user):
        self.user = user
        self.deleted_row = None
        self.committed = False

    def query(self, _model):
        return _UserQuery(self.user)

    def delete(self, row):
        self.deleted_row = row

    def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_delete_current_user_account_cleans_user_memory(monkeypatch):
    deleted_vectors = []
    session = _SessionStub(
        SimpleNamespace(
            user_id="user-1",
            username="tester",
            password_hash="hashed-password",
        )
    )

    @contextmanager
    def _fake_db_session():
        yield session

    monkeypatch.setattr("database.connection.get_db_session", _fake_db_session)
    monkeypatch.setattr("access_control.models.verify_password", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        "api_gateway.routers.users.blacklist_token_jti", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        "api_gateway.routers.users.blacklist_session_id",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "user_memory.storage_cleanup.prepare_user_memory_rows_for_user_deletion",
        lambda _session, user_id: {
            "user_id": user_id,
            "entry_ids": ["101", "102"],
            "memory_views": 1,
            "skill_proposals": 2,
            "session_ledgers": 3,
        },
    )
    monkeypatch.setattr(
        "user_memory.storage_cleanup.delete_user_memory_entry_vectors",
        lambda entry_ids: deleted_vectors.extend(entry_ids)
        or {"deleted_entry_ids": len(entry_ids)},
    )

    current_user = CurrentUser(
        user_id="user-1",
        username="tester",
        role="user",
        token_jti="token-1",
    )

    response = await delete_current_user_account(
        request=DeleteAccountRequest(current_password="password123", confirmation="DELETE"),
        current_user=current_user,
    )

    assert response == {"message": "Account deleted"}
    assert session.deleted_row.user_id == "user-1"
    assert session.committed is True
    assert deleted_vectors == ["101", "102"]
