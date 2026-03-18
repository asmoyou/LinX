"""Tests for the user-memory session-ledger service."""

from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from agent_framework.session_manager import ConversationSession
from user_memory.session_ledger_service import SessionLedgerService


class _RepoStub:
    def __init__(self):
        self.calls = []

    def record_session_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return 42


def _build_session(tmp_path: Path) -> ConversationSession:
    session = ConversationSession(
        session_id="ledger-session",
        agent_id=uuid4(),
        user_id=uuid4(),
        workdir=tmp_path,
    )
    session.append_memory_turn(
        "请以后回答更简洁一些。",
        "收到，后续我会优先给出简洁答案。",
        agent_name="Memory Agent",
    )
    return session


def test_session_ledger_service_builds_observations_and_projections(tmp_path: Path) -> None:
    repo = _RepoStub()
    service = SessionLedgerService(repository=repo)
    session = _build_session(tmp_path)
    turns = list(session.memory_turns)

    result = service.persist_conversation_session(
        session=session,
        reason="user",
        turns=turns,
        agent_name="Memory Agent",
        extracted_signals=[
            {
                "key": "response_style",
                "value": "concise",
                "persistent": True,
                "explicit_source": True,
                "confidence": 0.93,
                "latest_ts": "2026-03-07T10:00:00Z",
                "reason": "explicit_preference",
            }
        ],
        extracted_agent_candidates=[],
    )

    assert result.session_row_id == 42
    assert result.event_count == 2
    assert result.observation_count == 1
    assert result.projection_count == 1
    assert repo.calls[0]["snapshot"].end_reason == "user"


def test_session_ledger_service_materializes_user_episode_views(tmp_path: Path) -> None:
    repo = _RepoStub()
    service = SessionLedgerService(repository=repo)
    session = _build_session(tmp_path)
    turns = list(session.memory_turns)

    result = service.persist_conversation_session(
        session=session,
        reason="user",
        turns=turns,
        agent_name="Memory Agent",
        extracted_signals=[
            {
                "key": "life_event_move",
                "semantic_key": "life_event_move",
                "value": "搬到了杭州",
                "fact_kind": "event",
                "persistent": False,
                "explicit_source": True,
                "confidence": 0.91,
                "event_time": "2024年8月",
                "topic": "迁居",
                "canonical_statement": "在2024年8月，搬到了杭州",
                "latest_ts": "2026-03-07T10:00:00Z",
                "reason": "explicit_event",
            }
        ],
        extracted_agent_candidates=[],
    )

    projections = repo.calls[0]["projections"]

    assert result.observation_count == 1
    assert result.projection_count == 1
    assert any(item.projection_type == "episode" for item in projections)


def test_session_ledger_service_persists_synthetic_turn_batch(tmp_path: Path) -> None:
    repo = _RepoStub()
    service = SessionLedgerService(repository=repo)

    result = service.persist_turn_batch(
        session_id="agent-conversation:conv-1:until:msg-1",
        agent_id=str(uuid4()),
        user_id=str(uuid4()),
        started_at=datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc),
        reason="client_release",
        turns=[
            {
                "user_message": "以后默认给我简洁回答。",
                "agent_response": "收到。",
                "agent_name": "Memory Agent",
                "timestamp": "2026-03-21T10:00:00+00:00",
            }
        ],
        agent_name="Memory Agent",
        extracted_signals=[],
        extracted_agent_candidates=[],
        metadata={"conversation_id": "conv-1", "run_sequence": 2},
    )

    assert result.session_row_id == 42
    assert repo.calls[0]["snapshot"].session_id == "agent-conversation:conv-1:until:msg-1"
    assert repo.calls[0]["snapshot"].metadata["conversation_id"] == "conv-1"
