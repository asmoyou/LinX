from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from access_control.permissions import CurrentUser
from api_gateway.main import app
from api_gateway.routers import user_memory


@pytest.fixture
def current_user():
    return CurrentUser(
        user_id="test-user-id",
        username="tester",
        role="user",
        token_jti="token-jti",
    )


def test_user_memory_routes_registered():
    route_paths = {
        (route.path, tuple(sorted(route.methods)))
        for route in app.routes
        if hasattr(route, "methods")
    }

    assert ("/api/v1/user-memory", ("GET",)) in route_paths
    assert ("/api/v1/user-memory/profile", ("GET",)) in route_paths
    assert ("/api/v1/user-memory/episodes", ("GET",)) in route_paths
    assert ("/api/v1/user-memory/config", ("GET",)) in route_paths
    assert ("/api/v1/user-memory/config", ("PUT",)) in route_paths
    assert ("/api/v1/user-memory/admin/maintain-materializations", ("POST",)) in route_paths


@pytest.mark.asyncio
async def test_list_user_memory_uses_user_scope(current_user):
    captured = {}

    def _search_user_memory(**kwargs):
        captured.update(kwargs)
        return [
            SimpleNamespace(
                id=1,
                content="user.preference.response_style=concise",
                timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
                similarity_score=0.91,
                metadata={"signal_type": "user_preference"},
                memory_type="user_memory",
                agent_id=None,
                user_id="resolved-user-id",
            )
        ]

    retriever = SimpleNamespace(search_user_memory=_search_user_memory)

    with (
        patch(
            "api_gateway.routers.user_memory._require_user_memory_read_access_sync",
            return_value=None,
        ),
        patch("api_gateway.routers.user_memory.get_user_memory_retriever", return_value=retriever),
    ):
        response = await user_memory.list_user_memory(
            query_text="回答简洁一点",
            user_id="resolved-user-id",
            limit=10,
            min_score=0.5,
            current_user=current_user,
        )

    assert captured["query_text"] == "回答简洁一点"
    assert captured["user_id"] == "resolved-user-id"
    assert captured["limit"] == 10
    assert captured["min_score"] == 0.5
    assert response[0].content == "user.preference.response_style=concise"
    assert response[0].type == "user_memory"


@pytest.mark.asyncio
async def test_list_user_memory_profile_reads_user_profile_materialization(current_user):
    captured = {}

    def _list_profile(**kwargs):
        captured.update(kwargs)
        return [
            SimpleNamespace(
                id=2,
                content="user.preference.output_format=markdown",
                timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
                similarity_score=0.88,
                metadata={"materialization_type": "user_profile", "record_type": "user_profile"},
                memory_type="user_memory",
                agent_id=None,
                user_id="resolved-user-id",
            )
        ]

    retriever = SimpleNamespace(list_profile=_list_profile)

    with (
        patch(
            "api_gateway.routers.user_memory._require_user_memory_read_access_sync",
            return_value=None,
        ),
        patch("api_gateway.routers.user_memory.get_user_memory_retriever", return_value=retriever),
    ):
        response = await user_memory.list_user_memory_profile(
            user_id="resolved-user-id",
            query_text="markdown",
            limit=5,
            min_score=0.4,
            current_user=current_user,
        )

    assert captured["user_id"] == "resolved-user-id"
    assert captured["query_text"] == "markdown"
    assert captured["limit"] == 5
    assert captured["min_score"] == 0.4
    assert response[0].metadata["materialization_type"] == "user_profile"


@pytest.mark.asyncio
async def test_list_user_memory_episodes_reads_event_entries(current_user):
    captured = {}

    def _list_episodes(**kwargs):
        captured.update(kwargs)
        return [
            SimpleNamespace(
                id=3,
                content="在2024年8月，搬到了杭州",
                timestamp=datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
                similarity_score=0.79,
                metadata={"fact_kind": "event", "record_type": "user_fact"},
                memory_type="user_memory",
                agent_id=None,
                user_id="resolved-user-id",
            )
        ]

    retriever = SimpleNamespace(list_episodes=_list_episodes)

    with (
        patch(
            "api_gateway.routers.user_memory._require_user_memory_read_access_sync",
            return_value=None,
        ),
        patch("api_gateway.routers.user_memory.get_user_memory_retriever", return_value=retriever),
    ):
        response = await user_memory.list_user_memory_episodes(
            user_id="resolved-user-id",
            query_text="什么时候搬到杭州",
            limit=5,
            min_score=0.4,
            current_user=current_user,
        )

    assert captured["user_id"] == "resolved-user-id"
    assert captured["query_text"] == "什么时候搬到杭州"
    assert response[0].content == "在2024年8月，搬到了杭州"
    assert response[0].metadata["fact_kind"] == "event"


@pytest.mark.asyncio
async def test_list_user_memory_checks_owner_scope_before_search(current_user):
    with patch(
        "api_gateway.routers.user_memory._require_user_memory_read_access_sync",
        side_effect=user_memory.HTTPException(status_code=403, detail="forbidden"),
    ):
        with pytest.raises(user_memory.HTTPException) as exc:
            await user_memory.list_user_memory(
                query_text="*",
                user_id="other-user",
                limit=10,
                min_score=None,
                current_user=current_user,
            )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_user_memory_config_delegates_to_shared_config_helper(current_user):
    expected = {"retrieval": {"top_k": 10}}

    with patch(
        "api_gateway.routers.user_memory.get_memory_config", return_value=expected
    ) as getter:
        result = await user_memory.get_user_memory_config(current_user=current_user)

    assert result == expected
    assert getter.call_args.kwargs == {"current_user": current_user}


@pytest.mark.asyncio
async def test_update_user_memory_config_passes_update_data_keyword(current_user):
    request = user_memory.MemoryConfigUpdateRequest(
        user_memory={"retrieval": {"top_k": 8}}
    )

    with patch(
        "api_gateway.routers.user_memory.update_memory_config",
        return_value={"user_memory": {"retrieval": {"top_k": 8}}},
    ) as updater:
        result = await user_memory.update_user_memory_config(
            request=request,
            current_user=current_user,
        )

    assert result == {"user_memory": {"retrieval": {"top_k": 8}}}
    assert updater.call_args.kwargs == {
        "update_data": request,
        "current_user": current_user,
    }


@pytest.mark.asyncio
async def test_maintain_user_memory_materializations_delegates_to_shared_helper(current_user):
    with patch(
        "api_gateway.routers.user_memory.maintain_materializations",
        return_value="ok",
    ) as maintain:
        result = await user_memory.maintain_user_memory_materializations(
            dry_run=False,
            user_id="user-1",
            agent_id="agent-1",
            limit=25,
            current_user=current_user,
        )

    assert result == "ok"
    assert maintain.call_args.kwargs == {
        "dry_run": False,
        "user_id": "user-1",
        "agent_id": "agent-1",
        "limit": 25,
        "current_user": current_user,
    }
