"""Unit tests for user-memory session-ledger repository helper logic."""

from datetime import datetime, timezone

from user_memory.session_ledger_repository import (
    MemoryObservationData,
    MemorySessionSnapshot,
    SessionLedgerRepository,
)


def _snapshot() -> MemorySessionSnapshot:
    now = datetime(2026, 3, 10, 16, 0, 0, tzinfo=timezone.utc)
    return MemorySessionSnapshot(
        session_id="session-1",
        agent_id="agent-1",
        user_id="user-1",
        started_at=now,
        ended_at=now,
        status="completed",
    )


def test_build_entry_from_user_preference_observation() -> None:
    observation = MemoryObservationData(
        observation_key="pref_response_style",
        observation_type="user_preference_signal",
        title="User preference: response_style",
        summary="concise",
        details="explicit_preference",
        confidence=0.92,
        importance=0.9,
        metadata={
            "preference_key": "response_style",
            "preference_value": "concise",
            "explicit_source": True,
        },
    )

    entry = SessionLedgerRepository._build_entry_from_observation(  # noqa: SLF001
        snapshot=_snapshot(),
        observation=observation,
    )

    assert entry is not None
    assert entry.owner_type == "user"
    assert entry.entry_type == "user_fact"
    assert entry.entry_key == "response_style"
    assert entry.canonical_text == "user.preference.response_style=concise"
    assert entry.status == "active"


def test_build_entry_from_user_fact_observation_uses_canonical_statement() -> None:
    observation = MemoryObservationData(
        observation_key="user_fact_relationship_spouse",
        observation_type="user_fact_signal",
        title="User relationship: spouse",
        summary="用户的配偶是王敏",
        details="用户明确陈述人物关系",
        confidence=0.93,
        importance=0.9,
        metadata={
            "fact_key": "relationship_spouse",
            "fact_value": "王敏",
            "fact_kind": "relationship",
            "canonical_statement": "用户的配偶是王敏",
            "predicate": "spouse",
            "object": "王敏",
            "persons": ["王敏"],
        },
    )

    entry = SessionLedgerRepository._build_entry_from_observation(  # noqa: SLF001
        snapshot=_snapshot(),
        observation=observation,
    )

    assert entry is not None
    assert entry.entry_key == "relationship_spouse"
    assert entry.canonical_text == "用户的配偶是王敏"
    assert entry.payload["fact_kind"] == "relationship"
    assert entry.payload["persons"] == ["王敏"]


def test_build_relation_from_observation_uses_server_generated_identity() -> None:
    observation = MemoryObservationData(
        observation_key="user_fact_relationship_friend",
        observation_type="user_fact_signal",
        title="User relationship: friend",
        summary="用户与小陈是朋友",
        confidence=0.91,
        importance=0.84,
        metadata={
            "fact_key": "relationship_friend_b13f7f2a9c20",
            "semantic_key": "relationship_friend",
            "identity_signature": "relationship|friend|小陈",
            "fact_kind": "relationship",
            "canonical_statement": "用户与小陈是朋友",
            "predicate": "friend",
            "object": "小陈",
            "persons": ["小陈"],
        },
    )

    relation = SessionLedgerRepository._build_relation_from_observation(  # noqa: SLF001
        snapshot=_snapshot(),
        observation=observation,
        source_entry_id=42,
        source_session_ledger_id=7,
    )

    assert relation is not None
    assert relation.relation_key == "relationship_friend_b13f7f2a9c20"
    assert relation.predicate == "friend"
    assert relation.object_text == "小陈"
    assert relation.payload["identity_signature"] == "relationship|friend|小陈"
    assert relation.source_entry_id == 42


def test_resolve_entry_identity_rewrites_legacy_preference_key_to_canonical_identity() -> None:
    legacy_payload = {
        "key": "preference_food_hamburger",
        "semantic_key": "preference_food_hamburger",
        "fact_kind": "preference",
        "value": "汉堡",
        "canonical_statement": "用户喜欢吃汉堡",
    }
    current_payload = {
        "key": "preference_7161fef42c9a",
        "semantic_key": "preference_food_hamburger",
        "fact_kind": "preference",
        "value": "汉堡",
        "canonical_statement": "用户喜欢吃汉堡",
    }

    legacy_identity, normalized_legacy, _canonical_statement, _value = (
        SessionLedgerRepository.resolve_entry_identity(payload=legacy_payload)
    )
    current_identity, normalized_current, _canonical_statement, _value = (
        SessionLedgerRepository.resolve_entry_identity(payload=current_payload)
    )

    assert legacy_identity.identity_signature == current_identity.identity_signature
    assert legacy_identity.fact_key == current_identity.fact_key
    assert normalized_legacy["key"] == normalized_current["key"]
    assert normalized_legacy["identity_signature"] == normalized_current["identity_signature"]


def test_resolve_relation_identity_rewrites_legacy_relation_key_to_canonical_identity() -> None:
    legacy_payload = {
        "key": "relationship_friend_xiaochen",
        "semantic_key": "relationship_friend_xiaochen",
        "predicate": "friend",
        "object": "小陈",
        "canonical_statement": "用户与小陈是朋友",
        "persons": ["小陈"],
    }

    identity, payload = SessionLedgerRepository.resolve_relation_identity(payload=legacy_payload)

    assert identity.identity_signature == "relationship|friend|小陈"
    assert payload["key"] == identity.fact_key
    assert payload["identity_signature"] == identity.identity_signature


def test_resolve_entry_identity_merges_event_variants_with_same_time_and_people() -> None:
    first_payload = {
        "key": "event_dining_with_xiaochen_2026_03_17",
        "semantic_key": "event_dining_with_xiaochen_2026_03_17",
        "fact_kind": "event",
        "value": "用户将与小陈一起去吃汉堡",
        "canonical_statement": "2026年3月17日用户将与小陈一起去吃汉堡",
        "event_time": "2026-03-17",
        "persons": ["小陈"],
        "location": "汉堡店",
        "topic": "聚餐",
    }
    second_payload = {
        "key": "important_event",
        "semantic_key": "important_event",
        "fact_kind": "event",
        "value": "计划与小陈吃汉堡",
        "canonical_statement": "用户计划与小陈一起去吃汉堡",
        "event_time": "2026-03-17",
    }

    first_identity, _first_payload, _canonical_statement, _value = (
        SessionLedgerRepository.resolve_entry_identity(payload=first_payload)
    )
    second_identity, _second_payload, _canonical_statement, _value = (
        SessionLedgerRepository.resolve_entry_identity(payload=second_payload)
    )

    assert first_identity.identity_signature == second_identity.identity_signature
    assert first_identity.fact_key == second_identity.fact_key
