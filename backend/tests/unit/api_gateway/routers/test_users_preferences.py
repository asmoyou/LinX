from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from access_control.permissions import CurrentUser
from api_gateway.routers.users import UserPreferences, get_user_preferences, update_user_preferences


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


def test_user_preferences_defaults_motion_preference_to_auto() -> None:
    preferences = UserPreferences()

    assert preferences.motion_preference == "auto"


@pytest.mark.asyncio
async def test_get_user_preferences_reads_motion_preference() -> None:
    user = SimpleNamespace(attributes={"preferences": {"motion_preference": "reduced"}})
    session = _SessionStub(user)

    with patch("database.connection.get_db_session", _session_context(session)):
        response = await get_user_preferences(
            current_user=CurrentUser(user_id="user-1", username="alice", role="user")
        )

    assert response.motion_preference == "reduced"


@pytest.mark.asyncio
async def test_update_user_preferences_writes_motion_preference() -> None:
    user = SimpleNamespace(attributes={"preferences": {"motion_preference": "auto"}})
    session = _SessionStub(user)
    request = UserPreferences(motion_preference="off")

    with patch("database.connection.get_db_session", _session_context(session)):
        with patch("sqlalchemy.orm.attributes.flag_modified"):
            response = await update_user_preferences(
                preferences=request,
                current_user=CurrentUser(user_id="user-1", username="alice", role="user"),
            )

    assert response.motion_preference == "off"
    assert user.attributes["preferences"]["motion_preference"] == "off"
    assert session.commit_called is True
