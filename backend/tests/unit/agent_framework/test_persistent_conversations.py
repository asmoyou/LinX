from pathlib import Path
from uuid import uuid4

import pytest

from agent_framework.persistent_conversations import PersistentConversationRuntime, PersistentConversationRuntimeService


@pytest.mark.asyncio
async def test_release_runtime_flushes_conversation_memory_even_when_runtime_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = PersistentConversationRuntimeService(base_workdir=str(tmp_path))
    conversation_id = uuid4()
    service._runtimes[str(conversation_id)] = PersistentConversationRuntime(
        conversation_id=conversation_id,
        agent_id=uuid4(),
        owner_user_id=uuid4(),
        runtime_session_id="runtime-1",
        workdir=tmp_path / "runtime",
        use_sandbox=False,
        sandbox_id=None,
        restored_from_snapshot=False,
        snapshot_generation=0,
    )
    service._runtimes[str(conversation_id)].workdir.mkdir(parents=True, exist_ok=True)

    calls = []

    class _ConversationMemoryServiceStub:
        async def flush_conversation_memory_delta(self, conversation_id_arg, reason):
            calls.append((conversation_id_arg, reason))
            return {"status": "ok"}

    monkeypatch.setattr(
        "user_memory.conversation_memory_service.get_conversation_memory_service",
        lambda: _ConversationMemoryServiceStub(),
    )

    await service.release_runtime(conversation_id, reason="user")

    assert calls == [(conversation_id, "user")]
