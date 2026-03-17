"""Tests for hybrid user-memory retrieval."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from user_memory.hybrid_retriever import UserMemoryHybridRetriever
from user_memory.items import RetrievedMemoryItem


def _item(item_id: int, content: str, score: float, *, entry: bool = True) -> RetrievedMemoryItem:
    metadata = {
        "entry_id" if entry else "view_id": item_id,
        "memory_source": "entry" if entry else "user_memory_view",
    }
    return RetrievedMemoryItem(
        id=item_id,
        content=content,
        memory_type="user_memory",
        timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        metadata=metadata,
        similarity_score=score,
    )


def test_search_user_memory_wildcard_bypasses_hybrid_pipeline() -> None:
    retriever = UserMemoryHybridRetriever()
    recent_results = [_item(1, "user.preference.response_style=concise", 0.88)]

    with patch.object(retriever, "_recent_search", return_value=recent_results) as recent:
        results = retriever.search_user_memory(user_id="u-1", query_text="*", limit=5)

    assert results == recent_results
    recent.assert_called_once()


def test_list_profile_scopes_to_user_profile_views() -> None:
    retriever = UserMemoryHybridRetriever()
    expected = [_item(2, "user.preference.output_format=markdown", 0.77, entry=False)]

    with patch.object(retriever, "_search_hybrid", return_value=expected) as search_hybrid:
        results = retriever.list_profile(user_id="u-1", query_text="markdown", limit=5)

    assert results == expected
    assert search_hybrid.call_args.kwargs["source_kinds"] == ["view"]
    assert search_hybrid.call_args.kwargs["view_types"] == ["user_profile"]


def test_list_episodes_supplements_event_facts_when_views_are_insufficient() -> None:
    retriever = UserMemoryHybridRetriever()
    view_item = _item(3, "在2024年8月，搬到了杭州", 0.72, entry=False)
    fact_item = _item(4, "在2024年8月，搬到了杭州并开始新的工作", 0.69, entry=True)

    with patch.object(
        retriever, "_search_hybrid", side_effect=[[view_item], [fact_item]]
    ) as search_hybrid:
        results = retriever.list_episodes(user_id="u-1", query_text="什么时候搬到杭州", limit=3)

    assert [item.id for item in results] == [3, 4]
    assert search_hybrid.call_args_list[0].kwargs["view_types"] == ["episode"]
    assert search_hybrid.call_args_list[1].kwargs["fact_kinds"] == ["event"]


def test_parse_rerank_response_normalizes_negative_scores() -> None:
    retriever = UserMemoryHybridRetriever()

    parsed = retriever._parse_rerank_response(
        {
            "results": [
                {"index": 0, "relevance_score": -9.7},
                {"index": 1, "relevance_score": -2.1},
                {"index": 2, "relevance_score": -5.4},
            ]
        },
        3,
    )

    assert [index for index, _ in parsed] == [1, 2, 0]
    assert parsed[0][1] == 1.0
    assert 0.0 < parsed[1][1] < 1.0
    assert parsed[-1][1] == 0.0


def test_collapse_duplicate_memories_prefers_view_surface_and_preserves_best_score() -> None:
    retriever = UserMemoryHybridRetriever()
    entry_item = _item(5, "用户喜欢吃汉堡", 0.81, entry=True)
    entry_item.metadata.update(
        {
            "semantic_key": "preference_food_hamburger",
            "fact_kind": "preference",
            "entry_key": "preference_food_hamburger",
        }
    )
    view_item = _item(7, "用户喜欢吃汉堡", 0.72, entry=False)
    view_item.metadata.update(
        {
            "semantic_key": "preference_food_hamburger",
            "view_type": "user_profile",
            "view_key": "preference_food_hamburger",
        }
    )

    collapsed = retriever._collapse_duplicate_memories([entry_item, view_item])

    assert len(collapsed) == 1
    assert collapsed[0].metadata["view_type"] == "user_profile"
    assert collapsed[0].similarity_score == 0.81


def test_collapse_duplicate_profile_memories_uses_canonical_statement_when_keys_differ() -> None:
    retriever = UserMemoryHybridRetriever()
    first = _item(10, "用户喜欢喝可乐", 0.66, entry=True)
    first.metadata.update(
        {
            "semantic_key": "preference_drink_cola",
            "fact_kind": "preference",
            "canonical_statement": "用户喜欢喝可乐",
        }
    )
    second = _item(11, "用户喜欢喝可乐", 0.74, entry=False)
    second.metadata.update(
        {
            "semantic_key": "preference_drink_coke",
            "view_type": "user_profile",
            "canonical_statement": "用户喜欢喝可乐",
        }
    )

    collapsed = retriever._collapse_duplicate_memories([first, second])

    assert len(collapsed) == 1
    assert collapsed[0].metadata["view_type"] == "user_profile"
    assert collapsed[0].similarity_score == 0.74


def test_collapse_duplicate_event_memories_normalizes_minor_wording_differences() -> None:
    retriever = UserMemoryHybridRetriever()
    first = _item(12, "2026年3月17日用户将和小陈一起去吃汉堡", 0.61, entry=True)
    first.metadata.update(
        {
            "fact_kind": "event",
            "event_time": "2026-03-17",
            "canonical_statement": "2026年3月17日用户将和小陈一起去吃汉堡",
        }
    )
    second = _item(13, "2026年3月17日用户将与小陈一起去吃汉堡", 0.73, entry=False)
    second.metadata.update(
        {
            "view_type": "episode",
            "fact_kind": "event",
            "event_time": "2026-03-17",
            "canonical_statement": "2026年3月17日用户将与小陈一起去吃汉堡",
        }
    )

    collapsed = retriever._collapse_duplicate_memories([first, second])

    assert len(collapsed) == 1
    assert collapsed[0].metadata["view_type"] == "episode"
    assert collapsed[0].similarity_score == 0.73


def test_collapse_duplicate_relation_and_entry_prefers_relation_surface_when_identity_matches() -> (
    None
):
    retriever = UserMemoryHybridRetriever()
    entry_item = _item(14, "用户与小陈是朋友", 0.79, entry=True)
    entry_item.metadata.update(
        {
            "fact_kind": "relationship",
            "semantic_key": "relationship_friend",
            "identity_signature": "relationship|friend|小陈",
            "canonical_statement": "用户与小陈是朋友",
        }
    )
    relation_item = RetrievedMemoryItem(
        id=15,
        content="用户与小陈是朋友",
        memory_type="user_memory",
        timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        metadata={
            "relation_id": 15,
            "memory_source": "relation",
            "fact_kind": "relationship",
            "predicate": "friend",
            "identity_signature": "relationship|friend|小陈",
            "canonical_statement": "用户与小陈是朋友",
        },
        similarity_score=0.72,
    )

    collapsed = retriever._collapse_duplicate_memories([entry_item, relation_item])

    assert len(collapsed) == 1
    assert collapsed[0].metadata["memory_source"] == "relation"
    assert collapsed[0].similarity_score == 0.79
