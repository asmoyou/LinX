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
