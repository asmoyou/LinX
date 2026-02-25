"""Unit tests for mission workspace artifact collection."""

import base64
import io
from uuid import uuid4

from mission_system.workspace_manager import MissionWorkspaceManager, WorkspaceInfo


def test_collect_deliverables_includes_workspace_root_files(monkeypatch):
    mission_id = uuid4()
    encoded = base64.b64encode(b"docx-bytes").decode("ascii")

    class FakeContainerManager:
        def exec_in_container(self, _container_id, command, **_kwargs):
            if command.startswith("find '/workspace/output'"):
                return 0, "", ""
            if command.startswith("find '/workspace/shared'"):
                return 0, "", ""
            if command.startswith("find '/workspace/tasks'"):
                return 0, "", ""
            if command.startswith("find '/workspace/logs'"):
                return 0, "", ""
            if command.startswith("find '/workspace/input'"):
                return 0, "", ""
            if command.startswith("find '/workspace' -maxdepth 1 -type f"):
                return 0, "123 /workspace/final.docx\n", ""
            if command == "base64 '/workspace/final.docx'":
                return 0, encoded, ""
            raise AssertionError(f"unexpected command: {command}")

    class FakeMinio:
        def upload_file(self, *, bucket_type, file_data, filename, user_id):
            assert bucket_type == "artifacts"
            assert filename == "final.docx"
            assert user_id == str(mission_id)
            assert file_data.read() == b"docx-bytes"
            return "artifacts", "missions/final.docx"

    monkeypatch.setattr(
        "mission_system.workspace_manager.get_minio_client",
        lambda: FakeMinio(),
    )

    manager = MissionWorkspaceManager.__new__(MissionWorkspaceManager)
    manager._container_manager = FakeContainerManager()
    manager._workspaces = {
        mission_id: WorkspaceInfo(
            mission_id=mission_id,
            container_id="container-1",
            workspace_path="/workspace",
        )
    }

    deliverables = manager.collect_deliverables(mission_id)
    assert len(deliverables) == 1
    item = deliverables[0]
    assert item.filename == "final.docx"
    assert item.is_target is True
    assert item.source_scope == "output"
    assert item.artifact_kind == "final"


def test_collect_deliverables_demotes_runtime_root_script(monkeypatch):
    mission_id = uuid4()
    encoded = base64.b64encode(b"print('hello')").decode("ascii")

    class FakeContainerManager:
        def exec_in_container(self, _container_id, command, **_kwargs):
            if command.startswith("find '/workspace/output'"):
                return 0, "", ""
            if command.startswith("find '/workspace/shared'"):
                return 0, "", ""
            if command.startswith("find '/workspace/tasks'"):
                return 0, "", ""
            if command.startswith("find '/workspace/logs'"):
                return 0, "", ""
            if command.startswith("find '/workspace/input'"):
                return 0, "", ""
            if command.startswith("find '/workspace' -maxdepth 1 -type f"):
                return 0, "88 /workspace/code_ab12cd34.py\n", ""
            if command == "base64 '/workspace/code_ab12cd34.py'":
                return 0, encoded, ""
            raise AssertionError(f"unexpected command: {command}")

    class FakeMinio:
        def upload_file(self, *, bucket_type, file_data, filename, user_id):
            assert bucket_type == "artifacts"
            assert filename == "code_ab12cd34.py"
            assert user_id == str(mission_id)
            assert file_data.read() == b"print('hello')"
            return "artifacts", "missions/code_ab12cd34.py"

    monkeypatch.setattr(
        "mission_system.workspace_manager.get_minio_client",
        lambda: FakeMinio(),
    )

    manager = MissionWorkspaceManager.__new__(MissionWorkspaceManager)
    manager._container_manager = FakeContainerManager()
    manager._workspaces = {
        mission_id: WorkspaceInfo(
            mission_id=mission_id,
            container_id="container-1",
            workspace_path="/workspace",
        )
    }

    deliverables = manager.collect_deliverables(mission_id)
    assert len(deliverables) == 1
    item = deliverables[0]
    assert item.filename == "code_ab12cd34.py"
    assert item.is_target is False
    assert item.source_scope == "shared"
    assert item.artifact_kind == "intermediate"


def test_collect_deliverables_reads_output_directory_only(monkeypatch):
    mission_id = uuid4()
    encoded = base64.b64encode(b"final-markdown").decode("ascii")

    class FakeContainerManager:
        def exec_in_container(self, _container_id, command, **_kwargs):
            if command.startswith("find '/workspace/output'"):
                return (0, "12 /workspace/output/final.md\n", "")
            if command.startswith("find '/workspace/shared'"):
                return 0, "", ""
            if command.startswith("find '/workspace/tasks'"):
                return 0, "", ""
            if command.startswith("find '/workspace/logs'"):
                return 0, "", ""
            if command.startswith("find '/workspace/input'"):
                return 0, "", ""
            if command.startswith("find '/workspace' -maxdepth 1 -type f"):
                return 0, "", ""
            if command == "base64 '/workspace/output/final.md'":
                return 0, encoded, ""
            if "/workspace/outputs" in command:
                raise AssertionError("outputs path should not be accessed")
            raise AssertionError(f"unexpected command: {command}")

    class FakeMinio:
        def upload_file(self, *, bucket_type, file_data, filename, user_id):
            assert bucket_type == "artifacts"
            assert filename == "output/final.md"
            assert user_id == str(mission_id)
            assert file_data.read() == b"final-markdown"
            return "artifacts", "missions/output/final.md"

    monkeypatch.setattr(
        "mission_system.workspace_manager.get_minio_client",
        lambda: FakeMinio(),
    )

    manager = MissionWorkspaceManager.__new__(MissionWorkspaceManager)
    manager._container_manager = FakeContainerManager()
    manager._workspaces = {
        mission_id: WorkspaceInfo(
            mission_id=mission_id,
            container_id="container-1",
            workspace_path="/workspace",
        )
    }

    deliverables = manager.collect_deliverables(mission_id)
    assert len(deliverables) == 1
    item = deliverables[0]
    assert item.filename == "output/final.md"
    assert item.is_target is True
    assert item.source_scope == "output"
    assert item.artifact_kind == "final"


def test_snapshot_workspace_uploads_archive(monkeypatch):
    mission_id = uuid4()
    archive_bytes = b"workspace-archive"
    archive_b64 = base64.b64encode(archive_bytes).decode("ascii")

    class FakeContainerManager:
        def exec_in_container(self, _container_id, command, **_kwargs):
            if command.startswith("tar -czf '/tmp/workspace_snapshot_"):
                return 0, "", ""
            if command == "find '/workspace' -type f | wc -l":
                return 0, "5\n", ""
            if command.startswith("base64 '/tmp/workspace_snapshot_"):
                return 0, archive_b64, ""
            if command.startswith("rm -f '/tmp/workspace_snapshot_"):
                return 0, "", ""
            raise AssertionError(f"unexpected command: {command}")

    class FakeMinio:
        def upload_file(
            self,
            *,
            bucket_type,
            file_data,
            filename,
            user_id,
            content_type=None,
            metadata=None,
        ):
            assert bucket_type == "artifacts"
            assert filename.startswith("workspace_snapshot_")
            assert user_id == str(mission_id)
            assert content_type == "application/gzip"
            assert file_data.read() == archive_bytes
            assert metadata is not None
            assert metadata.get("artifact_type") == "workspace_snapshot"
            assert metadata.get("snapshot_reason") == "failed"
            return "artifacts", "snapshots/workspace_snapshot.tar.gz"

    monkeypatch.setattr(
        "mission_system.workspace_manager.get_minio_client",
        lambda: FakeMinio(),
    )

    manager = MissionWorkspaceManager.__new__(MissionWorkspaceManager)
    manager._container_manager = FakeContainerManager()
    manager._workspaces = {
        mission_id: WorkspaceInfo(
            mission_id=mission_id,
            container_id="container-1",
            workspace_path="/workspace",
        )
    }

    snapshot = manager.snapshot_workspace(mission_id, reason="failed")

    assert snapshot["path"] == "artifacts/snapshots/workspace_snapshot.tar.gz"
    assert snapshot["size"] == len(archive_bytes)
    assert snapshot["file_count"] == 5
    assert snapshot["reason"] == "failed"


def test_restore_workspace_downloads_and_extracts_snapshot(monkeypatch):
    mission_id = uuid4()
    restore_stream = io.BytesIO(b"workspace-archive")

    class FakeContainerManager:
        def exec_in_container(self, _container_id, command, **_kwargs):
            if command.startswith(": > '/tmp/workspace_snapshot_restore.tar.gz.b64'"):
                return 0, "", ""
            if command.startswith("printf '%s' '") and command.endswith(
                "' >> '/tmp/workspace_snapshot_restore.tar.gz.b64'"
            ):
                return 0, "", ""
            if command == (
                "base64 -d '/tmp/workspace_snapshot_restore.tar.gz.b64' > "
                "'/tmp/workspace_snapshot_restore.tar.gz'"
            ):
                return 0, "", ""
            if command == (
                "tar -xzf '/tmp/workspace_snapshot_restore.tar.gz' -C '/workspace' --overwrite"
            ):
                return 0, "", ""
            if command == "find '/workspace' -type f | wc -l":
                return 0, "7\n", ""
            if command == (
                "rm -f '/tmp/workspace_snapshot_restore.tar.gz' "
                "'/tmp/workspace_snapshot_restore.tar.gz.b64'"
            ):
                return 0, "", ""
            raise AssertionError(f"unexpected command: {command}")

    class FakeMinio:
        def download_file(self, bucket_name, object_key):
            assert bucket_name == "artifacts"
            assert object_key == "workspace_snapshot_restore.tar.gz"
            restore_stream.seek(0)
            return restore_stream, {}

    monkeypatch.setattr(
        "mission_system.workspace_manager.get_minio_client",
        lambda: FakeMinio(),
    )

    manager = MissionWorkspaceManager.__new__(MissionWorkspaceManager)
    manager._container_manager = FakeContainerManager()
    manager._workspaces = {
        mission_id: WorkspaceInfo(
            mission_id=mission_id,
            container_id="container-1",
            workspace_path="/workspace",
        )
    }

    restored = manager.restore_workspace(
        mission_id,
        "artifacts/workspace_snapshot_restore.tar.gz",
    )

    assert restored["path"] == "artifacts/workspace_snapshot_restore.tar.gz"
    assert restored["restored_file_count"] == 7
    assert restored["archive_size"] == len(b"workspace-archive")


def test_build_mission_container_config_sets_mission_name_and_workspace_mount():
    mission_id = uuid4()
    host_workspace_path = f"/tmp/linx-mission-test-{mission_id}"

    manager = MissionWorkspaceManager.__new__(MissionWorkspaceManager)
    config = manager._build_mission_container_config(
        mission_id=mission_id,
        mission_config={},
        host_workspace_path=host_workspace_path,
    )

    assert config.name.startswith("mission-")
    assert config.volume_mounts[host_workspace_path] == "/workspace"
    assert config.environment["WORKSPACE"] == "/workspace"


def test_create_workspace_does_not_create_legacy_outputs_alias():
    mission_id = uuid4()
    executed_commands = []

    class FakeContainerManager:
        def create_container(self, *, agent_id, config):
            assert agent_id == mission_id
            assert config is not None
            return "container-1"

        def start_container(self, container_id):
            assert container_id == "container-1"
            return True

        def exec_in_container(self, container_id, command, **_kwargs):
            assert container_id == "container-1"
            executed_commands.append(command)
            return 0, "", ""

    manager = MissionWorkspaceManager.__new__(MissionWorkspaceManager)
    manager._container_manager = FakeContainerManager()
    manager._workspaces = {}
    manager._prepare_host_workspace = lambda _mission_id: "/tmp/linx-mission-test"
    manager._build_mission_container_config = lambda **_kwargs: object()

    manager.create_workspace(mission_id, config={})

    assert (
        "mkdir -p /workspace/input /workspace/output /workspace/tasks /workspace/shared "
        "/workspace/logs"
    ) in executed_commands
    assert all("/workspace/outputs" not in command for command in executed_commands)
