from uuid import uuid4

import pytest

from user_memory.conversation_memory_manager import run_conversation_memory_scan_once
from user_memory.conversation_memory_service import ConversationMemoryExtractionSettings


@pytest.mark.asyncio
async def test_run_conversation_memory_scan_once_uses_passed_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class _ServiceStub:
        def __init__(self, settings=None):
            captured["settings"] = settings

        async def scan_idle_conversations(self, *, limit, reason, include_all_pending):
            captured["scan_args"] = {
                "limit": limit,
                "reason": reason,
                "include_all_pending": include_all_pending,
            }
            return [uuid4(), uuid4()]

    monkeypatch.setattr(
        "user_memory.conversation_memory_manager.ConversationMemoryService",
        _ServiceStub,
    )

    settings = ConversationMemoryExtractionSettings(
        enabled=True,
        use_advisory_lock=False,
        scan_limit=17,
        idle_timeout_minutes=12,
        overlap_turns=4,
    )

    result = await run_conversation_memory_scan_once(
        settings,
        reason="scheduled",
        include_all_pending=True,
    )

    assert result["status"] == "ok"
    assert result["processed"] == 2
    assert captured["settings"] == settings.with_defaults()
    assert captured["scan_args"] == {
        "limit": 17,
        "reason": "scheduled",
        "include_all_pending": True,
    }
