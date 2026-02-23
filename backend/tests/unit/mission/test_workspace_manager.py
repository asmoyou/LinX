"""Unit tests for mission workspace artifact collection."""

import base64
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
