"""Unit tests for session-ledger repository helper logic."""

from datetime import datetime, timezone

from memory_system.session_ledger_repository import (
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


def test_build_entry_from_agent_success_path_observation() -> None:
    observation = MemoryObservationData(
        observation_key="agent_path_pdf_delivery",
        observation_type="agent_success_path",
        title="Stable PDF delivery path",
        summary="先识别失败原因，再切换到稳定链路。",
        details="识别限制 -> 切换稳定链路 -> 校验后交付",
        confidence=0.87,
        importance=0.82,
        metadata={
            "steps": ["识别限制", "切换稳定链路", "校验后交付"],
            "applicability": "文件转换多次失败后仍需稳定交付",
            "avoid": "不要反复走已验证失败的转换器",
        },
    )

    entry = SessionLedgerRepository._build_entry_from_observation(  # noqa: SLF001
        snapshot=_snapshot(),
        observation=observation,
    )

    assert entry is not None
    assert entry.owner_type == "agent"
    assert entry.entry_type == "agent_skill_candidate"
    assert entry.entry_key == "agent_path_pdf_delivery"
    assert "agent.experience.goal=Stable PDF delivery path" in entry.canonical_text
    assert (
        "agent.experience.successful_path=识别限制 | 切换稳定链路 | 校验后交付"
        in entry.canonical_text
    )
    assert entry.status == "pending_review"
