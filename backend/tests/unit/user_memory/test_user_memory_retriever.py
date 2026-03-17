"""Tests for the user-memory retriever facade."""

from unittest.mock import MagicMock, patch

from user_memory.retriever import UserMemoryRetriever


def test_search_user_memory_delegates_to_hybrid_runtime_defaults() -> None:
    retriever = UserMemoryRetriever()
    expected = [object()]
    hybrid = MagicMock()
    hybrid.search_user_memory.return_value = expected

    with patch(
        "user_memory.retriever.get_user_memory_hybrid_retriever", return_value=hybrid
    ) as get_hybrid:
        results = retriever.search_user_memory(user_id="u-1", query_text="配偶是谁", limit=5)

    assert results == expected
    kwargs = get_hybrid.return_value.search_user_memory.call_args.kwargs
    assert kwargs == {
        "user_id": "u-1",
        "query_text": "配偶是谁",
        "limit": 5,
        "min_score": None,
        "planner_mode": "runtime_light",
        "allow_reflection": False,
    }


def test_search_user_memory_passes_explicit_options() -> None:
    retriever = UserMemoryRetriever()
    hybrid = MagicMock()
    hybrid.search_user_memory.return_value = []

    with patch(
        "user_memory.retriever.get_user_memory_hybrid_retriever", return_value=hybrid
    ) as get_hybrid:
        retriever.search_user_memory(
            user_id="u-1",
            query_text="什么时候搬到杭州",
            limit=7,
            min_score=0.6,
            planner_mode="api_full",
            allow_reflection=True,
        )

    kwargs = get_hybrid.return_value.search_user_memory.call_args.kwargs
    assert kwargs["min_score"] == 0.6
    assert kwargs["planner_mode"] == "api_full"
    assert kwargs["allow_reflection"] is True


def test_list_profile_uses_api_defaults() -> None:
    retriever = UserMemoryRetriever()
    hybrid = MagicMock()
    hybrid.list_profile.return_value = ["profile"]

    with patch(
        "user_memory.retriever.get_user_memory_hybrid_retriever", return_value=hybrid
    ) as get_hybrid:
        results = retriever.list_profile(user_id="u-1", query_text="输出格式", limit=3)

    assert results == ["profile"]
    kwargs = get_hybrid.return_value.list_profile.call_args.kwargs
    assert kwargs["planner_mode"] == "api_full"
    assert kwargs["allow_reflection"] is False


def test_list_episodes_uses_api_defaults() -> None:
    retriever = UserMemoryRetriever()
    hybrid = MagicMock()
    hybrid.list_episodes.return_value = ["episode"]

    with patch(
        "user_memory.retriever.get_user_memory_hybrid_retriever", return_value=hybrid
    ) as get_hybrid:
        results = retriever.list_episodes(user_id="u-1", query_text="什么时候搬家", limit=4)

    assert results == ["episode"]
    kwargs = get_hybrid.return_value.list_episodes.call_args.kwargs
    assert kwargs["planner_mode"] == "api_full"
    assert kwargs["allow_reflection"] is False
