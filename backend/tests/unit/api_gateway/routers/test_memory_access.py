from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from access_control.permissions import CurrentUser
from api_gateway.routers.memory_access import (
    _agent_owned_by_user_sync,
    _is_admin_or_manager,
    _memory_item_to_response,
    _require_agent_read_access_sync,
    _require_user_memory_read_access_sync,
)


@pytest.fixture
def current_user():
    return CurrentUser(
        user_id="test-user-id",
        username="tester",
        role="user",
        token_jti="token-jti",
    )


def test_memory_item_to_response_sets_private_visibility_for_user_memory():
    item = SimpleNamespace(
        id=7,
        content="用户的配偶是王敏",
        summary="relationship fact",
        memory_type="user_memory",
        agent_id=None,
        user_id="user-1",
        timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        similarity_score=0.93,
        metadata={
            "record_type": "user_fact",
            "shared_with_user_ids": ["user-2"],
            "vector_status": "synced",
            "vector_error": None,
            "_combined_score": 0.1,
        },
    )

    result = _memory_item_to_response(item)

    assert result["type"] == "user_memory"
    assert result["summary"] == "relationship fact"
    assert result["metadata"]["visibility"] == "private"
    assert result["metadata"]["record_type"] == "user_fact"
    assert result["indexStatus"] == "synced"
    assert result["isShared"] is True
    assert "_combined_score" not in result["metadata"]


def test_memory_item_to_response_keeps_skill_experience_type():
    item = SimpleNamespace(
        id=3,
        content="agent.experience.goal=Stable PDF delivery path",
        memory_type="skill_experience",
        agent_id="agent-1",
        user_id=None,
        timestamp=datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        similarity_score=0.88,
        metadata={"record_type": "agent_experience"},
    )

    result = _memory_item_to_response(item)

    assert result["type"] == "skill_experience"
    assert result["agentId"] == "agent-1"
    assert result["metadata"]["record_type"] == "agent_experience"


def test_is_admin_or_manager_matches_expected_roles(current_user):
    base = {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "token_jti": current_user.token_jti,
    }
    assert _is_admin_or_manager(CurrentUser(**{**base, "role": "admin"}))
    assert _is_admin_or_manager(CurrentUser(**{**base, "role": "manager"}))
    assert not _is_admin_or_manager(current_user)


def test_agent_owned_by_user_sync_checks_database(current_user):
    session_ctx = MagicMock()
    session = MagicMock()
    session_ctx.__enter__.return_value = session
    session_ctx.__exit__.return_value = False
    session.query.return_value.filter.return_value.first.return_value = (current_user.user_id,)

    with patch("database.connection.get_db_session", return_value=session_ctx):
        assert _agent_owned_by_user_sync(
            "7f9f8b89-0f13-4c95-a827-2199efd28475",
            current_user.user_id,
        )


def test_require_user_memory_read_access_sync_allows_owner(current_user):
    _require_user_memory_read_access_sync(current_user.user_id, current_user)


def test_require_user_memory_read_access_sync_rejects_other_user(current_user):
    with pytest.raises(Exception) as exc:
        _require_user_memory_read_access_sync("other-user", current_user)

    assert exc.value.status_code == 403
    assert exc.value.detail == "You do not have permission to access this user memory"


def test_require_agent_read_access_sync_allows_owner(current_user):
    agent_id = "7f9f8b89-0f13-4c95-a827-2199efd28475"
    session_ctx = MagicMock()
    session = MagicMock()
    session_ctx.__enter__.return_value = session
    session_ctx.__exit__.return_value = False
    query = session.query.return_value
    query.filter.return_value.first.return_value = SimpleNamespace(
        agent_id=agent_id,
        owner_user_id=current_user.user_id,
    )

    with (
        patch("database.connection.get_db_session", return_value=session_ctx),
        patch("access_control.memory_filter.can_access_skill_learning", return_value=True),
    ):
        _require_agent_read_access_sync(agent_id, current_user)


def test_require_agent_read_access_sync_raises_not_found(current_user):
    agent_id = "7f9f8b89-0f13-4c95-a827-2199efd28475"
    session_ctx = MagicMock()
    session = MagicMock()
    session_ctx.__enter__.return_value = session
    session_ctx.__exit__.return_value = False
    session.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("database.connection.get_db_session", return_value=session_ctx),
        pytest.raises(Exception) as exc,
    ):
        _require_agent_read_access_sync(agent_id, current_user)

    assert exc.value.status_code == 404
    assert exc.value.detail == "Agent not found"


def test_require_agent_read_access_sync_rejects_forbidden(current_user):
    agent_id = "7f9f8b89-0f13-4c95-a827-2199efd28475"
    session_ctx = MagicMock()
    session = MagicMock()
    session_ctx.__enter__.return_value = session
    session_ctx.__exit__.return_value = False
    session.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        agent_id=agent_id,
        owner_user_id="other-user-id",
    )

    with (
        patch("database.connection.get_db_session", return_value=session_ctx),
        patch("access_control.memory_filter.can_access_skill_learning", return_value=False),
        pytest.raises(Exception) as exc,
    ):
        _require_agent_read_access_sync(agent_id, current_user)

    assert exc.value.status_code == 403
    assert (
        exc.value.detail == "You do not have permission to access this agent's skill learning data"
    )
