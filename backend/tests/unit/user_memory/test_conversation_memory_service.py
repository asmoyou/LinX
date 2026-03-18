from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from user_memory.conversation_memory_repository import ClaimedConversationMemoryBatch, ConversationMemoryTurn
from user_memory.conversation_memory_service import (
    ConversationMemoryExtractionSettings,
    ConversationMemoryService,
)


class _RepositoryStub:
    def __init__(self):
        self.completed = []
        self.failed = []

    def complete_claim(self, **kwargs):
        self.completed.append(kwargs)
        return True

    def fail_claim(self, **kwargs):
        self.failed.append(kwargs)
        return True


class _LedgerStub:
    def __init__(self):
        self.calls = []

    def persist_turn_batch(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(session_row_id=77)


def _build_turn(*, text: str, reply: str, origin: str) -> ConversationMemoryTurn:
    timestamp = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)
    turn = ConversationMemoryTurn(
        user_message=text,
        agent_response=reply,
        agent_name="Memory Agent",
        started_at=timestamp,
        completed_at=timestamp,
        user_message_ids=(uuid4(),),
        assistant_message_id=uuid4(),
    )
    return turn


def _build_batch(*, overlap_count: int = 1) -> ClaimedConversationMemoryBatch:
    overlap_turns = tuple(
        _build_turn(text="旧上下文", reply="旧回复", origin="overlap") for _ in range(overlap_count)
    )
    new_turn = _build_turn(text="用户说我擅长 SQL", reply="收到", origin="new")
    return ClaimedConversationMemoryBatch(
        conversation_id=uuid4(),
        agent_id=uuid4(),
        user_id=uuid4(),
        agent_name="Memory Agent",
        conversation_created_at=datetime(2026, 3, 21, 9, 0, tzinfo=timezone.utc),
        run_token="run-token",
        run_sequence=3,
        reason="client_release",
        synthetic_session_id=f"agent-conversation:{uuid4()}:until:{new_turn.assistant_message_id}",
        last_processed_assistant_message_id=uuid4(),
        target_assistant_message_id=new_turn.assistant_message_id,
        target_assistant_created_at=new_turn.completed_at,
        overlap_turns=overlap_turns,
        new_turns=(new_turn,),
        last_processed_turn_count=5,
        previous_failures=0,
    )


@pytest.mark.asyncio
async def test_flush_claimed_batch_filters_overlap_only_evidence() -> None:
    service = ConversationMemoryService(
        settings=ConversationMemoryExtractionSettings(enabled=True)
    )
    repository = _RepositoryStub()
    ledger = _LedgerStub()
    service._repository = repository
    service._ledger_service = ledger
    service._builder = SimpleNamespace(
        extract_session_memory_signals_with_llm=_async_return(
            (
                [
                    {"key": "old_fact", "value": "旧事实", "evidence_turns": [1], "confidence": 0.9},
                    {"key": "new_fact", "value": "SQL", "evidence_turns": [2], "confidence": 0.9},
                ],
                [
                    {
                        "fingerprint": "old_skill",
                        "title": "旧路径",
                        "steps": ["a", "b"],
                        "summary": "只来自 overlap",
                        "evidence_turns": [1],
                        "confidence": 0.8,
                    },
                    {
                        "fingerprint": "new_skill",
                        "title": "新路径",
                        "steps": ["a", "b"],
                        "summary": "命中新 turn",
                        "evidence_turns": [2],
                        "confidence": 0.8,
                    },
                ],
            )
        ),
        extract_user_preference_signals=lambda turns: [],
    )

    result = await service._flush_claimed_batch(_build_batch())

    assert result["status"] == "ok"
    assert ledger.calls[0]["turns"] == [
        {
            "user_message": "用户说我擅长 SQL",
            "agent_response": "收到",
            "agent_name": "Memory Agent",
            "timestamp": "2026-03-21T10:00:00+00:00",
            "turn_origin": "new",
        }
    ]
    assert [item["key"] for item in ledger.calls[0]["extracted_signals"]] == ["new_fact"]
    assert [item["fingerprint"] for item in ledger.calls[0]["extracted_agent_candidates"]] == [
        "new_skill"
    ]
    assert repository.completed


@pytest.mark.asyncio
async def test_flush_claimed_batch_falls_back_to_heuristic_signals_for_new_turns() -> None:
    service = ConversationMemoryService(
        settings=ConversationMemoryExtractionSettings(enabled=True)
    )
    repository = _RepositoryStub()
    ledger = _LedgerStub()
    service._repository = repository
    service._ledger_service = ledger
    service._builder = SimpleNamespace(
        extract_session_memory_signals_with_llm=_async_return(([], [])),
        extract_user_preference_signals=lambda turns: [
            {
                "key": "response_style",
                "value": "concise",
                "confidence": 0.92,
                "persistent": True,
                "evidence_count": 1,
                "latest_ts": "2026-03-21T10:00:00+00:00",
            }
        ],
    )

    result = await service._flush_claimed_batch(_build_batch(overlap_count=0))

    assert result["status"] == "ok"
    assert ledger.calls[0]["extracted_signals"][0]["key"] == "response_style"
    assert not repository.failed


def _async_return(value):
    async def _runner(*args, **kwargs):
        return value

    return _runner
