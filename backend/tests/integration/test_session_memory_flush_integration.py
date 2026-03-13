"""Integration tests for session flush in the reset ledger pipeline."""

from pathlib import Path
from uuid import uuid4

import pytest

from agent_framework.session_manager import ConversationSession
from api_gateway.routers import agents as agents_router


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


def _agent_candidate() -> dict:
    return {
        "title": "稳定 PDF 转换交付路径",
        "topic": "稳定 PDF 转换交付路径",
        "steps": ["优先走 libreoffice headless", "失败时切换图片中转", "最终上传 PDF 给用户"],
        "summary": "分层兜底可以避免单一路径失败。",
        "confidence": 0.87,
        "fingerprint": "stable_pdf_delivery_path",
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_flush_persists_extracted_signals_into_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    session = _build_session(tmp_path)
    ledger_stub = _SessionLedgerServiceStub()

    async def _fake_extract_session_memory_signals_with_llm(*, turns, **kwargs):
        assert turns
        return [_signal(value="concise")], []

    monkeypatch.setattr(
        agents_router,
        "_extract_session_memory_signals_with_llm",
        _fake_extract_session_memory_signals_with_llm,
    )
    monkeypatch.setattr(
        "user_memory.session_ledger_service.get_session_ledger_service",
        lambda: ledger_stub,
    )

    await agents_router._flush_session_memories(session, "session_end")

    assert ledger_stub.calls
    assert ledger_stub.calls[0]["reason"] == "session_end"
    assert ledger_stub.calls[0]["extracted_signals"][0]["value"] == "concise"
    assert ledger_stub.calls[0]["extracted_agent_candidates"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_flush_persists_agent_candidates_into_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    session = _build_session(tmp_path)
    ledger_stub = _SessionLedgerServiceStub()

    async def _fake_extract_session_memory_signals_with_llm(*, turns, **kwargs):
        assert turns
        return [], [_agent_candidate()]

    monkeypatch.setattr(
        agents_router,
        "_extract_session_memory_signals_with_llm",
        _fake_extract_session_memory_signals_with_llm,
    )
    monkeypatch.setattr(agents_router, "_extract_user_preference_signals", lambda _turns: [])
    monkeypatch.setattr(
        "user_memory.session_ledger_service.get_session_ledger_service",
        lambda: ledger_stub,
    )

    await agents_router._flush_session_memories(session, "session_end")

    assert ledger_stub.calls
    assert ledger_stub.calls[0]["extracted_signals"] == []
    assert ledger_stub.calls[0]["extracted_agent_candidates"][0]["fingerprint"] == (
        "stable_pdf_delivery_path"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_flush_writes_ledger_even_without_memory_candidates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    session = _build_session(tmp_path)
    ledger_stub = _SessionLedgerServiceStub()

    async def _fake_extract_session_memory_signals_with_llm(*, turns, **kwargs):
        assert turns
        return [], []

    monkeypatch.setattr(
        agents_router,
        "_extract_session_memory_signals_with_llm",
        _fake_extract_session_memory_signals_with_llm,
    )
    monkeypatch.setattr(agents_router, "_extract_user_preference_signals", lambda _turns: [])
    monkeypatch.setattr(
        "user_memory.session_ledger_service.get_session_ledger_service",
        lambda: ledger_stub,
    )

    await agents_router._flush_session_memories(session, "session_end")

    assert ledger_stub.calls
    assert ledger_stub.calls[0]["reason"] == "session_end"
    assert ledger_stub.calls[0]["turns"]
    assert ledger_stub.calls[0]["extracted_signals"] == []
    assert ledger_stub.calls[0]["extracted_agent_candidates"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_flush_uses_heuristic_user_fact_fallback_when_llm_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    session = _build_session(tmp_path)
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
        "user_memory.session_ledger_service.get_session_ledger_service",
        lambda: ledger_stub,
    )

    await agents_router._flush_session_memories(session, "session_end")

    assert ledger_stub.calls
    assert ledger_stub.calls[0]["extracted_signals"]
    assert ledger_stub.calls[0]["extracted_signals"][0]["key"] == "response_style"
