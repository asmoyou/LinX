"""Tests for the user-memory session-ledger service."""

from pathlib import Path
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


def test_session_ledger_service_builds_observations_and_materializations(tmp_path: Path) -> None:
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
    assert result.materialization_count == 1
    assert repo.calls[0]["snapshot"].end_reason == "user"
