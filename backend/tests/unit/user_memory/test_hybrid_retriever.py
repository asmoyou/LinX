"""Tests for hybrid user-memory retrieval."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from user_memory.hybrid_retriever import UserMemoryHybridRetriever
from user_memory.items import RetrievedMemoryItem
from user_memory.query_planner import QueryPlan
from user_memory.structured_search import StructuredQueryFilters, StructuredTimeRange


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


def test_view_to_item_uses_distinct_view_summary() -> None:
    retriever = UserMemoryHybridRetriever()
    row = SimpleNamespace(
        id=30,
        user_id="u-1",
        view_type="user_profile",
        view_key="preference_food_hamburger",
        status="active",
        view_data={},
        title="用户喜欢吃汉堡",
        summary="饮食偏好",
        content="用户喜欢吃汉堡",
        updated_at=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 3, 10, 11, 0, 0, tzinfo=timezone.utc),
    )

    item = retriever._view_to_item(row, score=0.77, method="semantic")

    assert item.summary == "饮食偏好"
    assert item.content == "用户喜欢吃汉堡"


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


def test_apply_rerank_preserves_strong_structured_hits_when_model_score_is_tiny() -> None:
    retriever = UserMemoryHybridRetriever()
    candidate = _item(16, "2026年3月17日用户将与小陈一起去吃汉堡", 0.62, entry=True)
    candidate.metadata.update(
        {
            "search_methods": ["structured"],
            "fact_kind": "event",
            "_structured_score": 0.96,
        }
    )
    other = _item(17, "用户喜欢喝可乐", 0.41, entry=True)
    other.metadata.update({"search_methods": ["lexical"], "_lexical_score": 0.41})

    with patch.object(retriever, "_call_rerank_api", return_value=[(0, 0.05), (1, 0.6)]):
        reranked, model_applied = retriever._apply_rerank(
            query_text="我今天有哪些行程安排？",
            query_terms=["今天", "行程", "安排"],
            results=[candidate, other],
            top_k=5,
        )

    assert model_applied is True
    reranked_by_id = {item.id: item for item in reranked}
    assert reranked_by_id[16].similarity_score >= 0.3


def test_apply_rerank_does_not_preserve_generic_profile_structured_floor() -> None:
    retriever = UserMemoryHybridRetriever()
    generic = _item(22, "用户喜欢喝可乐", 0.794, entry=False)
    generic.metadata.update(
        {
            "search_methods": ["structured"],
            "view_type": "user_profile",
            "fact_kind": "preference",
            "_structured_score": 0.794,
        }
    )
    specific = _item(23, "用户喜欢吃汉堡", 0.99, entry=False)
    specific.metadata.update(
        {
            "search_methods": ["lexical", "structured"],
            "view_type": "user_profile",
            "fact_kind": "preference",
            "_structured_score": 0.794,
        }
    )

    reranked, model_applied = retriever._apply_rerank(  # noqa: SLF001
        query_text="你知道我喜欢吃什么吗？",
        query_terms=["我喜欢吃什么", "我喜欢吃", "吃什么"],
        results=[generic, specific],
        top_k=5,
        structured_filters=StructuredQueryFilters(
            fact_kinds=["preference"],
            view_types=["user_profile"],
        ),
    )

    assert model_applied is True
    assert [item.id for item in reranked][:1] == [23]
    reranked_by_id = {item.id: item for item in reranked}
    assert reranked_by_id[22].similarity_score < 0.6


def test_apply_temporal_filters_drops_non_overlapping_event_candidates() -> None:
    retriever = UserMemoryHybridRetriever()
    plan = QueryPlan(
        planner_mode="runtime_light",
        query_variants=["我今天有哪些行程安排？"],
        keyword_terms=["今天", "行程", "安排"],
        structured_filters=StructuredQueryFilters(
            fact_kinds=["event"],
            view_types=["episode"],
            time_range=StructuredTimeRange(
                start=datetime(2026, 3, 17, 0, 0, 0, tzinfo=timezone.utc),
                end=datetime(2026, 3, 17, 23, 59, 59, tzinfo=timezone.utc),
            ),
            allow_history=False,
        ),
        reflection_worthwhile=False,
        vector_top_k=40,
        lexical_top_k=25,
        structured_top_k=15,
        rerank_top_k=20,
    )
    future_episode = _item(18, "2026年3月18日用户将与小陈一起去吃汉堡", 0.72, entry=False)
    future_episode.metadata.update(
        {
            "view_type": "episode",
            "fact_kind": "event",
            "event_time": "2026-03-18",
        }
    )
    today_episode = _item(19, "2026年3月17日用户将与小陈一起去吃汉堡", 0.61, entry=False)
    today_episode.metadata.update(
        {
            "view_type": "episode",
            "fact_kind": "event",
            "event_time": "2026-03-17",
        }
    )

    filtered = retriever._apply_temporal_filters(  # noqa: SLF001
        plan=plan,
        results=[future_episode, today_episode],
    )

    assert [item.id for item in filtered] == [19]


def test_heuristic_rerank_prefers_specific_preference_matches_over_generic_ones() -> None:
    retriever = UserMemoryHybridRetriever()
    food = _item(20, "用户喜欢吃汉堡", 0.62, entry=False)
    food.metadata.update({"search_methods": ["semantic", "lexical"], "_semantic_score": 0.62})
    generic = _item(21, "用户喜欢喝可乐", 0.83, entry=False)
    generic.metadata.update({"search_methods": ["semantic", "lexical"], "_semantic_score": 0.83})

    reranked = retriever._heuristic_rerank(  # noqa: SLF001
        query_terms=["喜欢吃什么", "喜欢吃", "吃什么", "喜欢"],
        results=[generic, food],
    )

    assert [item.id for item in reranked][:1] == [20]
