"""Tests for the session-ledger migration service."""

from pathlib import Path
from uuid import uuid4

from agent_framework.session_manager import ConversationSession
from memory_system.session_ledger_service import MemorySessionLedgerService


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
    service = MemorySessionLedgerService(repository=repo)
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
        extracted_agent_candidates=[
            {
                "fingerprint": "abc123",
                "candidate_type": "successful_path",
                "title": "复杂 PDF 转换后的稳定交付路径",
                "summary": "先判断格式限制，再切换到可稳定输出的转换链路，最后验证用户可接收。",
                "steps": ["识别输入限制", "切换成功的转换链路", "校验输出后交付用户"],
                "avoid": "不要反复尝试已失败的转换器",
                "applicability": "文件格式多次失败后仍需稳定交付",
                "confidence": 0.87,
            }
        ],
    )

    assert result.session_row_id == 42
    assert result.event_count == 2
    assert result.observation_count == 2
    assert result.materialization_count == 2
    assert len(repo.calls) == 1

    persisted = repo.calls[0]
    observations = persisted["observations"]
    materializations = persisted["materializations"]

    assert any(item.observation_type == "user_preference_signal" for item in observations)
    assert any(item.observation_type == "agent_success_path" for item in observations)
    assert any(item.materialization_type == "user_profile" for item in materializations)
    assert any(item.materialization_type == "agent_experience" for item in materializations)


def test_session_ledger_service_persists_events_without_extractions(tmp_path: Path) -> None:
    repo = _RepoStub()
    service = MemorySessionLedgerService(repository=repo)
    session = _build_session(tmp_path)
    turns = list(session.memory_turns)

    result = service.persist_conversation_session(
        session=session,
        reason="expired",
        turns=turns,
        agent_name="Memory Agent",
        extracted_signals=[],
        extracted_agent_candidates=[],
    )

    assert result.event_count == 2
    assert result.observation_count == 0
    assert result.materialization_count == 0
    assert len(repo.calls) == 1
    assert repo.calls[0]["snapshot"].end_reason == "expired"
