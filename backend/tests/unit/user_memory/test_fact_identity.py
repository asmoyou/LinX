"""Unit tests for server-side user-memory fact identity generation."""

from user_memory.fact_identity import build_user_fact_identity, build_user_memory_view_key


def test_relationship_identity_does_not_trust_free_form_llm_key_suffixes() -> None:
    identity = build_user_fact_identity(
        fact_kind="relationship",
        raw_key="relationship_friend_xiaochen",
        value="小陈",
        canonical_statement="用户与小陈是朋友",
        obj="小陈",
    )

    assert identity.semantic_key == "relationship_friend"
    assert identity.fact_key.startswith("relationship_friend_")
    assert "xiaochen" not in identity.fact_key
    assert identity.identity_signature == "relationship|friend|小陈"


def test_relationship_identity_is_stable_across_different_raw_keys() -> None:
    first = build_user_fact_identity(
        fact_kind="relationship",
        raw_key="relationship_friend_xiaochen",
        value="小陈",
        canonical_statement="用户与小陈是朋友",
        predicate="friend",
        obj="小陈",
    )
    second = build_user_fact_identity(
        fact_kind="relationship",
        raw_key="friend_relation",
        value="小陈",
        canonical_statement="用户与小陈是朋友",
        predicate="friend",
        obj="小陈",
    )

    assert first.semantic_key == second.semantic_key == "relationship_friend"
    assert first.fact_key == second.fact_key
    assert first.identity_signature == second.identity_signature


def test_single_valued_relationship_identity_stays_stable_without_hash_suffix() -> None:
    identity = build_user_fact_identity(
        fact_kind="relationship",
        raw_key="relationship_spouse",
        value="王敏",
        canonical_statement="用户的配偶是王敏",
        predicate="spouse",
        obj="王敏",
    )

    assert identity.semantic_key == "relationship_spouse"
    assert identity.fact_key == "relationship_spouse"
    assert identity.identity_signature == "relationship|spouse|王敏"


def test_event_identity_is_driven_by_time_and_canonical_statement() -> None:
    first = build_user_fact_identity(
        fact_kind="event",
        raw_key="moved_to_hangzhou_2024_08",
        value="用户搬到了杭州",
        canonical_statement="2024年8月用户搬到了杭州",
        event_time="2024-08",
        location="杭州",
        topic="迁居",
    )
    second = build_user_fact_identity(
        fact_kind="event",
        raw_key="important_event",
        value="搬到了杭州",
        canonical_statement="2024年8月用户搬到了杭州",
        event_time="2024-08",
        location="杭州",
        topic="迁居",
    )

    assert first.semantic_key == "moved_to_hangzhou_2024_08"
    assert second.semantic_key == "important_event"
    assert first.fact_key == second.fact_key
    assert first.fact_key.startswith("event_2024_08_")
    assert first.identity_signature == second.identity_signature


def test_episode_view_key_is_stable_across_wording_variants() -> None:
    first_identity = build_user_fact_identity(
        fact_kind="event",
        raw_key="event_dining_with_xiaochen_2026_03_17",
        value="用户将与小陈一起去吃汉堡",
        canonical_statement="2026年3月17日用户将与小陈一起去吃汉堡",
        event_time="2026-03-17",
        persons=["小陈"],
        location="汉堡店",
        topic="聚餐",
    )
    second_identity = build_user_fact_identity(
        fact_kind="event",
        raw_key="important_event",
        value="计划与小陈吃汉堡",
        canonical_statement="用户计划与小陈一起去吃汉堡",
        event_time="2026-03-17",
    )

    first_view_key = build_user_memory_view_key(
        view_type="episode",
        stable_key=first_identity.fact_key,
        canonical_statement="2026年3月17日用户将与小陈一起去吃汉堡",
        event_time="2026-03-17",
        value="用户将与小陈一起去吃汉堡",
    )
    second_view_key = build_user_memory_view_key(
        view_type="episode",
        stable_key=second_identity.fact_key,
        canonical_statement="用户计划与小陈一起去吃汉堡",
        event_time="2026-03-17",
        value="计划与小陈吃汉堡",
    )

    assert first_identity.fact_key == second_identity.fact_key
    assert first_view_key == second_view_key
