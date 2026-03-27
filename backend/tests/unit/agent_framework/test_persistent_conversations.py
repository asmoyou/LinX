import io
import tarfile
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from agent_framework.persistent_conversations import (
    PersistentConversationRuntime,
    PersistentConversationRuntimeService,
    _build_archive_bytes,
)


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


def test_build_archive_bytes_excludes_paths(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "output" / "result.txt").write_text("keep", encoding="utf-8")
    (tmp_path / "logs" / "run.log").write_text("drop", encoding="utf-8")

    archive_bytes, _checksum = _build_archive_bytes(
        tmp_path,
        excluded_paths={"logs"},
    )

    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        names = archive.getnames()

    assert "./output/result.txt" in names
    assert all(not name.startswith("./logs") for name in names)


def test_cleanup_orphaned_persistent_sandboxes_removes_old_orphans(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = PersistentConversationRuntimeService(
        base_workdir=str(tmp_path),
        cleanup_interval_seconds=300,
    )
    active_sandbox_id = "active-sandbox"
    conversation_id = uuid4()
    service._runtimes[str(conversation_id)] = PersistentConversationRuntime(
        conversation_id=conversation_id,
        agent_id=uuid4(),
        owner_user_id=uuid4(),
        runtime_session_id="runtime-1",
        workdir=tmp_path / "runtime",
        use_sandbox=True,
        sandbox_id=active_sandbox_id,
        restored_from_snapshot=False,
        snapshot_generation=0,
    )

    class _FakeContainer:
        def __init__(self, *, name: str, labels: dict[str, str], started_at: str) -> None:
            self.id = f"docker-{name}"
            self.name = name
            self.labels = labels
            self.attrs = {
                "State": {"StartedAt": started_at},
                "Config": {"Labels": labels},
            }
            self.removed = False

        def remove(self, force: bool = False) -> None:
            assert force is True
            self.removed = True

        def reload(self) -> None:
            return None

    orphan = _FakeContainer(
        name="conversation-orphan-1",
        labels={
            "com.linx.managed": "true",
            "com.linx.type": "sandbox",
            "com.linx.container_id": "orphan-sandbox",
            "com.linx.runtime_scope": "persistent_conversation",
        },
        started_at="2024-01-01T00:00:00.000000000Z",
    )
    legacy = _FakeContainer(
        name="conversation-legacy-1",
        labels={
            "com.linx.managed": "true",
            "com.linx.type": "sandbox",
            "com.linx.container_id": "legacy-sandbox",
        },
        started_at="2024-01-01T00:00:00.000000000Z",
    )
    recent = _FakeContainer(
        name="conversation-recent-1",
        labels={
            "com.linx.managed": "true",
            "com.linx.type": "sandbox",
            "com.linx.container_id": "recent-sandbox",
            "com.linx.runtime_scope": "persistent_conversation",
        },
        started_at="2099-01-01T00:00:00.000000000Z",
    )
    active = _FakeContainer(
        name="conversation-active-1",
        labels={
            "com.linx.managed": "true",
            "com.linx.type": "sandbox",
            "com.linx.container_id": active_sandbox_id,
            "com.linx.runtime_scope": "persistent_conversation",
        },
        started_at="2024-01-01T00:00:00.000000000Z",
    )
    session = _FakeContainer(
        name="session-keep-1",
        labels={
            "com.linx.managed": "true",
            "com.linx.type": "sandbox",
            "com.linx.container_id": "session-sandbox",
        },
        started_at="2024-01-01T00:00:00.000000000Z",
    )
    fake_docker_client = SimpleNamespace(
        containers=SimpleNamespace(
            list=lambda all, filters: [orphan, legacy, recent, active, session]
        )
    )
    fake_cleanup_manager = SimpleNamespace(
        docker_available=True,
        docker_client=fake_docker_client,
    )
    tracked_containers = {
        "orphan-sandbox": {"status": "running"},
        "legacy-sandbox": {"status": "running"},
        active_sandbox_id: {"status": "running"},
    }
    fake_container_manager = SimpleNamespace(containers=tracked_containers)

    monkeypatch.setattr(
        "virtualization.container_manager.get_docker_cleanup_manager",
        lambda: fake_cleanup_manager,
    )
    monkeypatch.setattr(
        "virtualization.container_manager.get_container_manager",
        lambda: fake_container_manager,
    )

    removed = service._cleanup_orphaned_sandboxes(force_remove=False)

    assert removed == 2
    assert orphan.removed is True
    assert legacy.removed is True
    assert recent.removed is False
    assert active.removed is False
    assert session.removed is False
    assert "orphan-sandbox" not in tracked_containers
    assert "legacy-sandbox" not in tracked_containers
    assert active_sandbox_id in tracked_containers


def test_cleanup_orphaned_persistent_sandboxes_force_remove_ignores_age(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    service = PersistentConversationRuntimeService(base_workdir=str(tmp_path))

    class _FakeContainer:
        def __init__(self) -> None:
            self.id = "docker-recent"
            self.name = "conversation-recent-1"
            self.labels = {
                "com.linx.managed": "true",
                "com.linx.type": "sandbox",
                "com.linx.container_id": "recent-sandbox",
                "com.linx.runtime_scope": "persistent_conversation",
            }
            self.attrs = {
                "State": {"StartedAt": "2099-01-01T00:00:00.000000000Z"},
                "Config": {"Labels": self.labels},
            }
            self.removed = False

        def remove(self, force: bool = False) -> None:
            assert force is True
            self.removed = True

        def reload(self) -> None:
            return None

    recent = _FakeContainer()
    fake_cleanup_manager = SimpleNamespace(
        docker_available=True,
        docker_client=SimpleNamespace(
            containers=SimpleNamespace(list=lambda all, filters: [recent])
        ),
    )

    monkeypatch.setattr(
        "virtualization.container_manager.get_docker_cleanup_manager",
        lambda: fake_cleanup_manager,
    )
    monkeypatch.setattr(
        "virtualization.container_manager.get_container_manager",
        lambda: SimpleNamespace(containers={"recent-sandbox": {"status": "running"}}),
    )

    removed = service._cleanup_orphaned_sandboxes(force_remove=True)

    assert removed == 1
    assert recent.removed is True


def test_persistent_runtime_uses_shared_runtime_image_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINX_PERSISTENT_CONVERSATION_SANDBOX_IMAGE", "")
    monkeypatch.setenv("LINX_MISSION_SANDBOX_IMAGE", "")
    monkeypatch.setenv("LINX_SANDBOX_PYTHON_IMAGE", "linx/sandbox-runtime:py312-office")

    from importlib import reload
    import agent_framework.persistent_conversations as persistent_conversations

    reloaded = reload(persistent_conversations)

    assert (
        reloaded.DEFAULT_PERSISTENT_CONVERSATION_SANDBOX_IMAGE
        == "linx/sandbox-runtime:py312-office"
    )


@pytest.mark.asyncio
async def test_persistent_runtime_creation_fails_closed_when_sandbox_required(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("LINX_ALLOW_HOST_EXECUTION_FALLBACK", "0")
    monkeypatch.setenv("LINX_ENFORCE_SANDBOX_ISOLATION", "1")
    monkeypatch.setattr(
        "agent_framework.session_manager.get_session_manager",
        lambda: SimpleNamespace(_docker_available=False),
    )

    service = PersistentConversationRuntimeService(
        base_workdir=str(tmp_path),
        use_sandbox_by_default=True,
    )
    monkeypatch.setattr(service, "_get_latest_ready_snapshot", lambda _conversation_id: None)

    conversation = SimpleNamespace(
        conversation_id=uuid4(),
        agent_id=uuid4(),
        owner_user_id=uuid4(),
    )

    with pytest.raises(RuntimeError, match="Docker not available"):
        await service.get_or_create_runtime(conversation=conversation)
