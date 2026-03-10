"""Integration tests for session-memory flush with planner action hints."""

from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from agent_framework.session_manager import ConversationSession
from api_gateway.routers import agents as agents_router


class _MemoryInterfaceStub:
    """In-memory stub for session flush persistence assertions."""

    def __init__(self, *, delete_result: str = "deleted-id"):
        self._delete_result = delete_result
        self.user_context_calls = []
        self.agent_memory_calls = []

    def store_user_context(self, *, user_id, agent_id, content, metadata=None):
        payload = {
            "user_id": user_id,
            "agent_id": agent_id,
            "content": content,
            "metadata": dict(metadata or {}),
        }
        self.user_context_calls.append(payload)
        action = str(payload["metadata"].get("memory_action") or "").strip().upper()
        if action == "DELETE":
            return self._delete_result
        return "new-memory-id"

    def store_agent_memory(self, *, agent_id, user_id, content, metadata=None):
        payload = {
            "agent_id": agent_id,
            "user_id": user_id,
            "content": content,
            "metadata": dict(metadata or {}),
        }
        self.agent_memory_calls.append(payload)
        return "agent-memory-id"


class _SessionLedgerServiceStub:
    def __init__(self):
        self.calls = []

    def persist_conversation_session(self, **kwargs):
        self.calls.append(kwargs)
        return {"ok": True}


def _build_session(tmp_path: Path) -> ConversationSession:
    session = ConversationSession(
        session_id="session-flush-test",
        agent_id=uuid4(),
        user_id=uuid4(),
        workdir=tmp_path,
    )
    session.append_memory_turn(
        "以后请用简洁风格回答。",
        "收到，我会采用简洁风格。",
        agent_name="Memory Agent",
    )
    return session


def _signal(*, value: str) -> dict:
    return {
        "key": "response_style",
        "value": value,
        "evidence_count": 3,
        "persistent": True,
        "strong_signal": True,
        "explicit_source": True,
        "confidence": 0.92,
        "latest_ts": "2026-03-02T00:00:00Z",
        "reason": "explicit_preference",
    }


def _existing_preference_map() -> dict:
    return {
        "response_style": {
            "memory_id": 99,
            "value": "detailed",
            "metadata": {
                "signal_type": "user_preference",
                "preference_key": "response_style",
                "preference_value": "detailed",
                "confidence": 0.81,
                "evidence_count": 2,
                "strong_signal": True,
                "latest_turn_ts": "2026-03-01T09:00:00Z",
            },
        }
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_flush_uses_delete_action_for_superseded_preference(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    session = _build_session(tmp_path)
    mem_stub = _MemoryInterfaceStub(delete_result="99")
    upsert_mock = Mock()

    async def _fake_extract_session_memory_signals_with_llm(*, turns, **kwargs):
        assert turns
        return [_signal(value="concise")], []

    monkeypatch.setattr(
        agents_router,
        "_extract_session_memory_signals_with_llm",
        _fake_extract_session_memory_signals_with_llm,
    )
    monkeypatch.setattr(
        agents_router,
        "_load_existing_user_preference_map",
        lambda _user_id: _existing_preference_map(),
    )
    monkeypatch.setattr(
        agents_router,
        "_load_existing_agent_candidate_fingerprints",
        lambda **_kwargs: set(),
    )
    monkeypatch.setattr(agents_router, "_upsert_existing_user_preference_metadata", upsert_mock)
    monkeypatch.setattr(
        "agent_framework.agent_memory_interface.get_agent_memory_interface",
        lambda: mem_stub,
    )

    await agents_router._flush_session_memories(session, "session_end")

    assert len(mem_stub.user_context_calls) == 2
    delete_call = next(
        call
        for call in mem_stub.user_context_calls
        if str(call["metadata"].get("memory_action") or "").upper() == "DELETE"
    )
    add_call = next(
        call
        for call in mem_stub.user_context_calls
        if str(call["metadata"].get("memory_action") or "").upper() != "DELETE"
    )

    assert delete_call["metadata"]["target_memory_id"] == 99
    assert delete_call["metadata"]["is_active"] is False
    assert delete_call["metadata"]["preference_value"] == "detailed"
    assert add_call["metadata"]["preference_value"] == "concise"
    upsert_mock.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_flush_falls_back_to_metadata_upsert_when_delete_action_not_applied(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    session = _build_session(tmp_path)
    mem_stub = _MemoryInterfaceStub(delete_result="")
    upsert_mock = Mock()

    async def _fake_extract_session_memory_signals_with_llm(*, turns, **kwargs):
        assert turns
        return [_signal(value="concise")], []

    monkeypatch.setattr(
        agents_router,
        "_extract_session_memory_signals_with_llm",
        _fake_extract_session_memory_signals_with_llm,
    )
    monkeypatch.setattr(
        agents_router,
        "_load_existing_user_preference_map",
        lambda _user_id: _existing_preference_map(),
    )
    monkeypatch.setattr(
        agents_router,
        "_load_existing_agent_candidate_fingerprints",
        lambda **_kwargs: set(),
    )
    monkeypatch.setattr(agents_router, "_upsert_existing_user_preference_metadata", upsert_mock)
    monkeypatch.setattr(
        "agent_framework.agent_memory_interface.get_agent_memory_interface",
        lambda: mem_stub,
    )

    await agents_router._flush_session_memories(session, "session_end")

    assert len(mem_stub.user_context_calls) == 2
    upsert_mock.assert_called_once()
    assert upsert_mock.call_args.args[0] == 99
    fallback_meta = upsert_mock.call_args.args[1]
    assert fallback_meta["is_active"] is False
    assert fallback_meta["superseded_by_value"] == "concise"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_flush_dual_writes_session_ledger_even_without_memory_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    session = _build_session(tmp_path)
    mem_stub = _MemoryInterfaceStub()
    ledger_stub = _SessionLedgerServiceStub()

    async def _fake_extract_session_memory_signals_with_llm(*, turns, **kwargs):
        assert turns
        return [], []

    monkeypatch.setattr(
        agents_router,
        "_extract_session_memory_signals_with_llm",
        _fake_extract_session_memory_signals_with_llm,
    )
    monkeypatch.setattr(
        "agent_framework.agent_memory_interface.get_agent_memory_interface",
        lambda: mem_stub,
    )
    monkeypatch.setattr(
        "memory_system.session_ledger_service.get_memory_session_ledger_service",
        lambda: ledger_stub,
    )

    await agents_router._flush_session_memories(session, "session_end")

    assert ledger_stub.calls
    assert ledger_stub.calls[0]["reason"] == "session_end"
    assert ledger_stub.calls[0]["turns"]
    assert mem_stub.user_context_calls == []
    assert mem_stub.agent_memory_calls == []
