"""Tests for user-memory query planning."""

from unittest.mock import patch

from user_memory.query_planner import UserMemoryQueryPlanner


def test_runtime_light_planner_extracts_profile_and_event_hints() -> None:
    planner = UserMemoryQueryPlanner()

    plan = planner.plan(
        query_text="我什么时候搬到杭州，偏好什么回答风格？", planner_mode="runtime_light"
    )

    assert plan.planner_mode == "runtime_light"
    assert "event" in plan.structured_filters.fact_kinds
    assert "user_profile" in plan.structured_filters.view_types
    assert "杭州" in plan.structured_filters.locations


def test_runtime_light_planner_extracts_relation_predicate() -> None:
    planner = UserMemoryQueryPlanner()

    plan = planner.plan(query_text="我配偶是谁", planner_mode="runtime_light")

    assert "relationship" in plan.structured_filters.fact_kinds
    assert "spouse" in plan.structured_filters.predicates


def test_api_full_planner_falls_back_to_runtime_light_when_model_unavailable() -> None:
    planner = UserMemoryQueryPlanner()

    with patch.object(planner, "_call_planner_model", return_value=None):
        plan = planner.plan(query_text="配偶是谁", planner_mode="api_full")

    assert plan.planner_mode == "runtime_light"
    assert plan.query_variants == ["配偶是谁"]


def test_api_full_planner_merges_llm_plan_when_available() -> None:
    planner = UserMemoryQueryPlanner()
    llm_plan = {
        "query_variants": [" spouse name ", "relationship spouse"],
        "keyword_terms": ["spouse", "name"],
        "persons": ["王敏"],
        "entities": [],
        "location": "",
        "time_range": {},
        "fact_kind_hints": ["relationship"],
        "predicates": ["spouse"],
        "view_scope": "",
        "allow_history": False,
        "reflection_worthwhile": True,
    }

    with patch.object(planner, "_call_planner_model", return_value=llm_plan):
        plan = planner.plan(query_text="我配偶是谁", planner_mode="api_full")

    assert plan.planner_mode == "api_full"
    assert "relationship" in plan.structured_filters.fact_kinds
    assert "spouse" in plan.structured_filters.predicates
    assert "王敏" in plan.structured_filters.persons
    assert len(plan.query_variants) >= 2


def test_runtime_light_planner_adds_simplified_variants_for_conversational_questions() -> None:
    planner = UserMemoryQueryPlanner()

    plan = planner.plan(query_text="你知道我喜欢吃什么吗？", planner_mode="runtime_light")

    assert plan.query_variants[0] == "你知道我喜欢吃什么吗？"
    assert "我喜欢吃什么" in plan.query_variants
    assert "我喜欢吃" in plan.query_variants


def test_runtime_light_planner_extracts_person_and_relationship_from_conversational_query() -> None:
    planner = UserMemoryQueryPlanner()

    plan = planner.plan(query_text="那你知道我和小陈的关系吗？", planner_mode="runtime_light")

    assert "relationship" in plan.structured_filters.fact_kinds
    assert "小陈" in plan.structured_filters.persons


def test_runtime_light_planner_extracts_relative_day_for_schedule_queries() -> None:
    planner = UserMemoryQueryPlanner()

    plan = planner.plan(query_text="我今天有哪些行程安排？", planner_mode="runtime_light")

    assert "event" in plan.structured_filters.fact_kinds
    assert "episode" in plan.structured_filters.view_types
    assert plan.structured_filters.time_range.start is not None
    assert plan.structured_filters.time_range.end is not None
    assert plan.structured_filters.allow_history is False


def test_runtime_light_planner_only_enables_history_for_explicit_history_queries() -> None:
    planner = UserMemoryQueryPlanner()

    plan = planner.plan(query_text="我以前什么时候搬到杭州？", planner_mode="runtime_light")

    assert "event" in plan.structured_filters.fact_kinds
    assert plan.structured_filters.allow_history is True
