"""Tests for merged user-memory retrieval."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from user_memory.retriever import UserMemoryRetriever


class _Item(SimpleNamespace):
    pass


def _memory_item(
    *,
    item_id: int,
    content: str,
    score: float,
    source: str,
    ts: datetime | None = None,
    metadata: dict | None = None,
):
    return _Item(
        id=item_id,
        content=content,
        similarity_score=score,
        timestamp=ts or datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        metadata={
            "memory_source": source,
            ("entry_id" if source == "entry" else "view_id"): item_id,
            **(metadata or {}),
        },
    )


def test_search_user_memory_merges_entries_and_profile_views():
    retriever = UserMemoryRetriever()
    with (
        patch(
            "user_memory.retriever.get_memory_entry_retrieval_service",
            return_value=SimpleNamespace(
                retrieve_user_facts=lambda **_: [
                    _memory_item(item_id=1, content="用户的配偶是王敏", score=0.92, source="entry")
                ]
            ),
        ),
        patch(
            "user_memory.retriever.get_user_memory_view_retrieval_service",
            return_value=SimpleNamespace(
                retrieve_user_profile=lambda **_: [
                    _memory_item(
                        item_id=2,
                        content="user.preference.response_style=concise",
                        score=0.81,
                        source="user_memory_view",
                    )
                ]
            ),
        ),
    ):
        results = retriever.search_user_memory(user_id="u-1", query_text="配偶是谁", limit=5)

    assert [item.content for item in results] == [
        "用户的配偶是王敏",
        "user.preference.response_style=concise",
    ]


def test_list_profile_applies_min_score_filter():
    retriever = UserMemoryRetriever()
    with patch(
        "user_memory.retriever.get_user_memory_view_retrieval_service",
        return_value=SimpleNamespace(
            retrieve_user_profile=lambda **_: [
                _memory_item(
                    item_id=2,
                    content="user.preference.response_style=concise",
                    score=0.81,
                    source="user_memory_view",
                ),
                _memory_item(
                    item_id=3,
                    content="user.preference.output_format=markdown",
                    score=0.32,
                    source="user_memory_view",
                ),
            ]
        ),
    ):
        results = retriever.list_profile(user_id="u-1", query_text="*", limit=5, min_score=0.5)

    assert [item.content for item in results] == ["user.preference.response_style=concise"]


def test_list_episodes_prefers_episode_views():
    retriever = UserMemoryRetriever()
    with (
        patch(
            "user_memory.retriever.get_user_memory_view_retrieval_service",
            return_value=SimpleNamespace(
                retrieve_user_episodes=lambda **_: [
                    _memory_item(
                        item_id=3,
                        content="在2024年8月，搬到了杭州",
                        score=0.87,
                        source="user_memory_view",
                        metadata={"record_type": "episode", "event_time": "2024年8月"},
                    )
                ]
            ),
        ),
        patch(
            "user_memory.retriever.get_memory_entry_retrieval_service",
            return_value=SimpleNamespace(
                retrieve_user_facts=lambda **_: (_ for _ in ()).throw(
                    AssertionError("event-fact fallback should not run when episode views exist")
                )
            ),
        ),
    ):
        results = retriever.list_episodes(user_id="u-1", query_text="什么时候搬到杭州", limit=5)

    assert [item.content for item in results] == ["在2024年8月，搬到了杭州"]


def test_list_episodes_falls_back_to_event_facts_when_episode_views_missing():
    retriever = UserMemoryRetriever()
    with (
        patch(
            "user_memory.retriever.get_user_memory_view_retrieval_service",
            return_value=SimpleNamespace(retrieve_user_episodes=lambda **_: []),
        ),
        patch(
            "user_memory.retriever.get_memory_entry_retrieval_service",
            return_value=SimpleNamespace(
                retrieve_user_facts=lambda **_: [
                    _memory_item(
                        item_id=1,
                        content="在2024年8月，搬到了杭州",
                        score=0.87,
                        source="entry",
                        metadata={"fact_kind": "event"},
                    ),
                    _memory_item(
                        item_id=2,
                        content="用户的配偶是王敏",
                        score=0.9,
                        source="entry",
                        metadata={"fact_kind": "relationship"},
                    ),
                ]
            ),
        ),
    ):
        results = retriever.list_episodes(user_id="u-1", query_text="什么时候搬到杭州", limit=5)

    assert [item.content for item in results] == ["在2024年8月，搬到了杭州"]
