"""Tests for SessionManager sandbox lifecycle behavior."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from agent_framework.session_manager import SessionManager
from virtualization.sandbox_selector import SandboxType


@pytest.mark.asyncio
async def test_release_sandbox_fallback_cleanup(monkeypatch, tmp_path):
    """Fallback cleanup should run when tracked terminate fails."""
    monkeypatch.setattr(SessionManager, "_check_docker_availability", lambda self: False)
    manager = SessionManager(base_workdir=str(tmp_path), use_sandbox_by_default=False)

    class FakeContainerManager:
        def terminate_container(self, sandbox_id: str) -> bool:
            return False

    class FakeCleanupManager:
        def __init__(self):
            self.cleaned_ids = []

        def cleanup_container_by_internal_id(self, sandbox_id: str) -> bool:
            self.cleaned_ids.append(sandbox_id)
            return True

    fake_cleanup = FakeCleanupManager()
    monkeypatch.setattr(
        "virtualization.container_manager.get_container_manager",
        lambda: FakeContainerManager(),
    )
    monkeypatch.setattr(
        "virtualization.container_manager.get_docker_cleanup_manager",
        lambda: fake_cleanup,
    )

    released = await manager._release_sandbox("sandbox-123")

    assert released is True
    assert fake_cleanup.cleaned_ids == ["sandbox-123"]


@pytest.mark.asyncio
async def test_session_creation_fails_when_sandbox_required_and_docker_unavailable(
    monkeypatch, tmp_path
):
    """Strict isolation should fail closed instead of falling back to host execution."""
    monkeypatch.setenv("LINX_ALLOW_HOST_EXECUTION_FALLBACK", "0")
    monkeypatch.setenv("LINX_ENFORCE_SANDBOX_ISOLATION", "1")
    monkeypatch.setattr(SessionManager, "_check_docker_availability", lambda self: False)
    manager = SessionManager(base_workdir=str(tmp_path), use_sandbox_by_default=True)

    with pytest.raises(RuntimeError, match="Docker not available"):
        await manager.get_or_create_session(
            agent_id=uuid4(),
            user_id=uuid4(),
            session_id=None,
        )


@pytest.mark.asyncio
async def test_release_sandbox_returns_false_when_all_cleanup_paths_fail(monkeypatch, tmp_path):
    """Release should fail loudly when both terminate and fallback fail."""
    monkeypatch.setattr(SessionManager, "_check_docker_availability", lambda self: False)
    manager = SessionManager(base_workdir=str(tmp_path), use_sandbox_by_default=False)

    class FakeContainerManager:
        def terminate_container(self, sandbox_id: str) -> bool:
            return False

    class FakeCleanupManager:
        def cleanup_container_by_internal_id(self, sandbox_id: str) -> bool:
            return False

    monkeypatch.setattr(
        "virtualization.container_manager.get_container_manager",
        lambda: FakeContainerManager(),
    )
    monkeypatch.setattr(
        "virtualization.container_manager.get_docker_cleanup_manager",
        lambda: FakeCleanupManager(),
    )

    released = await manager._release_sandbox("sandbox-456")

    assert released is False


@pytest.mark.asyncio
async def test_acquire_sandbox_uses_unique_container_name(monkeypatch, tmp_path):
    """Container name should include both agent prefix and session suffix."""
    monkeypatch.setattr(SessionManager, "_check_docker_availability", lambda self: True)
    manager = SessionManager(base_workdir=str(tmp_path), use_sandbox_by_default=True)

    created = {}

    class FakeContainerManager:
        docker_available = True
        default_sandbox = SandboxType.DOCKER_ENHANCED

        def create_container(self, agent_id, config):
            created["config"] = config
            return "sandbox-internal-id"

        def start_container(self, container_id: str) -> bool:
            return True

    monkeypatch.setattr(
        "virtualization.container_manager.get_container_manager",
        lambda: FakeContainerManager(),
    )

    agent_id = uuid4()
    session_workdir = tmp_path / "session_abc123def456"
    session_workdir.mkdir(parents=True, exist_ok=True)

    sandbox_id = await manager._acquire_sandbox(agent_id, session_workdir)

    assert sandbox_id == "sandbox-internal-id"
    assert created["config"].name == f"session-{agent_id.hex[:8]}-abc123def456"
    assert created["config"].tmpfs_mounts == {"/tmp": "size=1G,mode=1777"}
    assert created["config"].environment["PIP_CACHE_DIR"] == "/opt/linx_pip_cache"
    assert created["config"].environment["LINX_DEP_WORKDIR"] == "/opt/linx_runtime"


@pytest.mark.asyncio
async def test_end_session_triggers_callbacks_with_buffered_turns(monkeypatch, tmp_path):
    """Ending a session should trigger registered callbacks before cleanup."""
    monkeypatch.setattr(SessionManager, "_check_docker_availability", lambda self: False)
    manager = SessionManager(base_workdir=str(tmp_path), use_sandbox_by_default=False)

    user_id = uuid4()
    agent_id = uuid4()
    session, _ = await manager.get_or_create_session(
        agent_id=agent_id,
        user_id=user_id,
        use_sandbox=False,
    )
    session.append_memory_turn("如何做锅包肉？", "给出详细步骤", agent_name="小新客服")

    callback_events = []

    async def on_session_end(closed_session, reason: str) -> None:
        callback_events.append(
            {
                "session_id": closed_session.session_id,
                "reason": reason,
                "turn_count": len(closed_session.memory_turns),
            }
        )
        closed_session.drain_memory_turns()

    manager.register_session_end_callback(on_session_end)

    ended = await manager.end_session(session.session_id, user_id)

    assert ended is True
    assert callback_events == [
        {"session_id": session.session_id, "reason": "user", "turn_count": 1}
    ]
    assert manager.get_session(session.session_id) is None


@pytest.mark.asyncio
async def test_resuming_session_for_different_agent_creates_new_session(monkeypatch, tmp_path):
    """A session id must not resume another agent's workspace for the same user."""
    monkeypatch.setattr(SessionManager, "_check_docker_availability", lambda self: False)
    manager = SessionManager(base_workdir=str(tmp_path), use_sandbox_by_default=False)

    user_id = uuid4()
    first_agent_id = uuid4()
    second_agent_id = uuid4()

    first_session, first_is_new = await manager.get_or_create_session(
        agent_id=first_agent_id,
        user_id=user_id,
        use_sandbox=False,
    )
    resumed_session, resumed_is_new = await manager.get_or_create_session(
        agent_id=second_agent_id,
        user_id=user_id,
        session_id=first_session.session_id,
        use_sandbox=False,
    )

    assert first_is_new is True
    assert resumed_is_new is True
    assert resumed_session.session_id != first_session.session_id
    assert resumed_session.agent_id == second_agent_id
    assert manager.get_session(first_session.session_id) is first_session


@pytest.mark.asyncio
async def test_expired_cleanup_triggers_callbacks(monkeypatch, tmp_path):
    """Expired session cleanup should trigger callbacks with reason=expired."""
    monkeypatch.setattr(SessionManager, "_check_docker_availability", lambda self: False)
    manager = SessionManager(base_workdir=str(tmp_path), use_sandbox_by_default=False)

    user_id = uuid4()
    agent_id = uuid4()
    session, _ = await manager.get_or_create_session(
        agent_id=agent_id,
        user_id=user_id,
        use_sandbox=False,
    )
    session.append_memory_turn("用户问题", "助手回答", agent_name="test-agent")
    session.last_activity = datetime.now() - timedelta(minutes=session.ttl_minutes + 1)

    callback_reasons = []

    async def on_session_end(closed_session, reason: str) -> None:
        callback_reasons.append(reason)
        closed_session.drain_memory_turns()

    manager.register_session_end_callback(on_session_end)

    cleaned = await manager._cleanup_expired_sessions()

    assert cleaned == 1
    assert callback_reasons == ["expired"]
    assert manager.get_session(session.session_id) is None
