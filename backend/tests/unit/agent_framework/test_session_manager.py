"""Tests for SessionManager sandbox lifecycle behavior."""

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
