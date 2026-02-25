"""Unit tests for mission deletion cleanup behavior."""

from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import pytest

from api_gateway.routers.missions import delete_attachment, delete_mission


@pytest.mark.asyncio
async def test_delete_mission_cleans_storage_and_containers(monkeypatch):
    mission_id = uuid4()
    user_id = uuid4()
    deleted_paths = []
    cleaned_workspaces = []
    cleaned_containers = []

    mission = SimpleNamespace(
        mission_id=mission_id,
        status="failed",
        created_by_user_id=user_id,
        container_id="container-internal-id",
        attachments=[SimpleNamespace(file_reference="documents/input.txt")],
        result={
            "deliverables": [
                {
                    "filename": "output/final.md",
                    "path": "artifacts/final.md",
                    "is_target": True,
                }
            ],
            "workspace_snapshot": {"path": "artifacts/ws_latest.tar.gz"},
            "workspace_snapshots": [
                {"path": "artifacts/ws_old.tar.gz"},
                {"path": "artifacts/ws_latest.tar.gz"},
            ],
        },
    )

    state = {"deleted": False}

    def _fake_repo_get(_mission_id):
        if state["deleted"]:
            return None
        return mission

    def _fake_repo_delete(_mission_id):
        state["deleted"] = True
        return True

    class _FakeMinio:
        def delete_file(self, bucket_name, object_key):
            deleted_paths.append((bucket_name, object_key))

    class _FakeWorkspaceManager:
        def cleanup_workspace(self, _mission_id):
            cleaned_workspaces.append(_mission_id)

    class _FakeDockerCleanupManager:
        def cleanup_container_by_internal_id(self, container_id):
            cleaned_containers.append(container_id)
            return True

    monkeypatch.setattr("mission_system.mission_repository.get_mission", _fake_repo_get)
    monkeypatch.setattr("mission_system.mission_repository.delete_mission", _fake_repo_delete)
    monkeypatch.setattr(
        "mission_system.orchestrator.get_orchestrator",
        lambda: SimpleNamespace(cancel_mission=lambda *_args, **_kwargs: None),
    )
    monkeypatch.setattr(
        "mission_system.workspace_manager.get_workspace_manager",
        lambda: _FakeWorkspaceManager(),
    )
    monkeypatch.setattr(
        "object_storage.minio_client.get_minio_client",
        lambda: _FakeMinio(),
    )
    monkeypatch.setattr(
        "virtualization.container_manager.get_docker_cleanup_manager",
        lambda: _FakeDockerCleanupManager(),
    )

    await delete_mission(mission_id=mission_id, current_user=SimpleNamespace(user_id=str(user_id)))

    assert cleaned_workspaces == [mission_id]
    assert cleaned_containers == ["container-internal-id"]
    assert set(deleted_paths) == {
        ("documents", "input.txt"),
        ("artifacts", "final.md"),
        ("artifacts", "ws_old.tar.gz"),
        ("artifacts", "ws_latest.tar.gz"),
    }


@pytest.mark.asyncio
async def test_delete_attachment_removes_object_storage_file(monkeypatch):
    mission_id = uuid4()
    attachment_id = uuid4()
    deleted_paths = []
    deleted_rows = []

    attachment = SimpleNamespace(file_reference="documents/attachment.md")

    class _FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return attachment

    class _FakeSession:
        def query(self, *args, **kwargs):
            return _FakeQuery()

        def delete(self, row):
            deleted_rows.append(row)

    @contextmanager
    def _fake_db_session():
        yield _FakeSession()

    class _FakeMinio:
        def delete_file(self, bucket_name, object_key):
            deleted_paths.append((bucket_name, object_key))

    monkeypatch.setattr("database.connection.get_db_session", _fake_db_session)
    monkeypatch.setattr(
        "object_storage.minio_client.get_minio_client",
        lambda: _FakeMinio(),
    )

    await delete_attachment(
        mission_id=mission_id,
        attachment_id=attachment_id,
        current_user=SimpleNamespace(user_id=str(uuid4())),
    )

    assert deleted_paths == [("documents", "attachment.md")]
    assert deleted_rows == [attachment]
