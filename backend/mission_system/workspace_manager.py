"""Mission Workspace Manager.

Provides a shared Docker container workspace for mission execution.
All agents in a mission share a single container with a structured
directory layout for inputs, outputs, tasks, shared files, and logs.
"""

import base64
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from object_storage.minio_client import get_minio_client
from shared.config import get_config
from virtualization.container_manager import (
    ContainerConfig,
    ContainerManager,
    get_container_manager,
)

logger = logging.getLogger(__name__)

# Standard workspace directory layout inside the container
WORKSPACE_ROOT = "/workspace"
WORKSPACE_DIRS = ["input", "output", "tasks", "shared", "logs"]


@dataclass
class WorkspaceInfo:
    """Information about a created mission workspace."""

    mission_id: UUID
    container_id: str
    workspace_path: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class FileInfo:
    """Metadata for a file in the workspace."""

    name: str
    path: str
    size: int
    is_directory: bool
    modified_at: Optional[str] = None


@dataclass
class DeliverableInfo:
    """Metadata for a deliverable collected from the output directory."""

    filename: str
    path: str
    size: int
    download_url: Optional[str] = None
    is_target: bool = True


class MissionWorkspaceManager:
    """Manages shared Docker workspaces for mission execution.

    Each mission gets a single container with a structured filesystem.
    All agents execute commands inside this shared container.
    """

    def __init__(self) -> None:
        self._container_manager: ContainerManager = get_container_manager()
        self._workspaces: Dict[UUID, WorkspaceInfo] = {}
        logger.info("MissionWorkspaceManager initialized")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_workspace(
        self,
        mission_id: UUID,
        config: Optional[Dict[str, Any]] = None,
    ) -> WorkspaceInfo:
        """Create a shared Docker container for a mission.

        Args:
            mission_id: Mission UUID.
            config: Optional mission-level configuration overrides.

        Returns:
            WorkspaceInfo with container details.
        """
        config = config or {}
        container_config = self._build_mission_container_config(config)

        container_id = self._container_manager.create_container(
            agent_id=mission_id,  # reuse agent_id param for mission ownership
            config=container_config,
        )

        started = self._container_manager.start_container(container_id)
        if not started:
            raise RuntimeError(
                f"Failed to start workspace container for mission {mission_id}"
            )

        # Initialise workspace directories
        mkdir_cmd = " ".join(
            f"{WORKSPACE_ROOT}/{d}" for d in WORKSPACE_DIRS
        )
        exit_code, _, stderr = self._container_manager.exec_in_container(
            container_id,
            f"mkdir -p {mkdir_cmd}",
        )
        if exit_code != 0:
            raise RuntimeError(
                f"Failed to create workspace dirs: {stderr}"
            )

        workspace = WorkspaceInfo(
            mission_id=mission_id,
            container_id=container_id,
            workspace_path=WORKSPACE_ROOT,
        )
        self._workspaces[mission_id] = workspace

        logger.info(
            "Mission workspace created",
            extra={
                "mission_id": str(mission_id),
                "container_id": container_id,
            },
        )
        return workspace

    def setup_attachments(
        self,
        mission_id: UUID,
        attachments: List[Dict[str, str]],
    ) -> None:
        """Download attachments from MinIO and copy them into the container.

        Each attachment dict must contain ``bucket_name`` and ``object_key``,
        plus ``filename`` for the local name.
        """
        workspace = self._get_workspace(mission_id)
        minio = get_minio_client()

        for att in attachments:
            bucket_name = att["bucket_name"]
            object_key = att["object_key"]
            filename = att["filename"]

            stream, _meta = minio.download_file(bucket_name, object_key)
            content = stream.read()

            # Write via base64 to avoid shell escaping issues
            b64 = base64.b64encode(content).decode("ascii")
            dest = f"{WORKSPACE_ROOT}/input/{filename}"

            exit_code, _, stderr = self._container_manager.exec_in_container(
                workspace.container_id,
                f"echo '{b64}' | base64 -d > '{dest}'",
            )
            if exit_code != 0:
                logger.error(
                    "Failed to copy attachment %s: %s", filename, stderr
                )

        logger.info(
            "Attachments set up for mission %s (%d files)",
            mission_id,
            len(attachments),
        )

    def exec_as_agent(
        self,
        mission_id: UUID,
        agent_id: UUID,
        command: str,
        workdir: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Tuple[int, str, str]:
        """Execute a command inside the shared container on behalf of an agent.

        Args:
            mission_id: Mission UUID.
            agent_id: Agent performing the action (used for logging/env).
            command: Shell command string.
            workdir: Working directory inside the container.
            timeout: Command timeout (not yet enforced by ContainerManager).

        Returns:
            Tuple of (exit_code, stdout, stderr).
        """
        workspace = self._get_workspace(mission_id)
        environment = {"AGENT_ID": str(agent_id)}

        return self._container_manager.exec_in_container(
            workspace.container_id,
            command,
            workdir=workdir or WORKSPACE_ROOT,
            environment=environment,
        )

    def write_file(
        self,
        mission_id: UUID,
        path: str,
        content: str,
    ) -> None:
        """Write a text file into the workspace container.

        Args:
            mission_id: Mission UUID.
            path: Relative path from /workspace (e.g. ``tasks/plan.md``).
            content: File content.
        """
        workspace = self._get_workspace(mission_id)
        full_path = f"{WORKSPACE_ROOT}/{path}"

        self._container_manager.write_file_to_container(
            workspace.container_id,
            full_path,
            content,
        )

    def read_file(self, mission_id: UUID, path: str) -> str:
        """Read a text file from the workspace container.

        Args:
            mission_id: Mission UUID.
            path: Relative path from /workspace.

        Returns:
            File content as a string.
        """
        workspace = self._get_workspace(mission_id)
        full_path = f"{WORKSPACE_ROOT}/{path}"

        exit_code, stdout, stderr = self._container_manager.exec_in_container(
            workspace.container_id,
            f"cat '{full_path}'",
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to read file {path}: {stderr}")
        return stdout

    def list_files(
        self,
        mission_id: UUID,
        path: str = "",
    ) -> List[FileInfo]:
        """List files in a workspace directory.

        Args:
            mission_id: Mission UUID.
            path: Relative path from /workspace (default: root).

        Returns:
            List of FileInfo objects.
        """
        workspace = self._get_workspace(mission_id)
        target = f"{WORKSPACE_ROOT}/{path}" if path else WORKSPACE_ROOT

        # Use ls -la with a machine-friendly format
        exit_code, stdout, stderr = self._container_manager.exec_in_container(
            workspace.container_id,
            f"find '{target}' -maxdepth 1 -printf '%y %s %T@ %p\\n' 2>/dev/null || "
            f"ls -la '{target}'",
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to list files at {path}: {stderr}")

        files: List[FileInfo] = []
        for line in stdout.strip().splitlines():
            parts = line.split(None, 3)
            if len(parts) < 4:
                continue
            kind, size_str, mtime, filepath = parts
            name = filepath.rsplit("/", 1)[-1] if "/" in filepath else filepath
            if name in (".", ".."):
                continue
            files.append(
                FileInfo(
                    name=name,
                    path=filepath,
                    size=int(size_str) if size_str.isdigit() else 0,
                    is_directory=(kind == "d"),
                    modified_at=mtime,
                )
            )
        return files

    def collect_deliverables(
        self,
        mission_id: UUID,
    ) -> List[DeliverableInfo]:
        """Collect files from workspace output/shared directories and upload to MinIO.

        Returns:
            List of DeliverableInfo with download metadata.
        """
        workspace = self._get_workspace(mission_id)
        minio = get_minio_client()
        deliverables: List[DeliverableInfo] = []
        source_dirs = [
            (f"{WORKSPACE_ROOT}/output", True),
            (f"{WORKSPACE_ROOT}/shared", False),
            (f"{WORKSPACE_ROOT}/tasks", False),
            (f"{WORKSPACE_ROOT}/logs", False),
            (f"{WORKSPACE_ROOT}/input", False),
        ]

        seen_filepaths = set()
        for source_dir, is_target in source_dirs:
            exit_code, stdout, _stderr = self._container_manager.exec_in_container(
                workspace.container_id,
                f"find '{source_dir}' -type f -printf '%s %p\\n'",
            )
            if exit_code != 0 or not stdout.strip():
                continue

            for line in stdout.strip().splitlines():
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                size_str, filepath = parts
                if filepath in seen_filepaths:
                    continue
                seen_filepaths.add(filepath)

                relative_path = filepath.replace(f"{WORKSPACE_ROOT}/", "", 1)

                # Read file content from container
                rc, content, err = self._container_manager.exec_in_container(
                    workspace.container_id,
                    f"base64 '{filepath}'",
                )
                if rc != 0:
                    logger.warning("Failed to read deliverable %s: %s", relative_path, err)
                    continue

                file_bytes = base64.b64decode(content.strip())
                file_stream = io.BytesIO(file_bytes)

                bucket_name, object_key = minio.upload_file(
                    bucket_type="artifacts",
                    file_data=file_stream,
                    filename=relative_path,
                    user_id=str(mission_id),
                )

                deliverables.append(
                    DeliverableInfo(
                        filename=relative_path,
                        path=f"{bucket_name}/{object_key}",
                        size=int(size_str) if size_str.isdigit() else len(file_bytes),
                        is_target=is_target,
                    )
                )

        logger.info(
            "Collected %d deliverables for mission %s",
            len(deliverables),
            mission_id,
        )
        return deliverables

    def cleanup_workspace(self, mission_id: UUID) -> None:
        """Stop and remove the mission container. Idempotent.

        Args:
            mission_id: Mission UUID.
        """
        workspace = self._workspaces.pop(mission_id, None)
        if workspace is None:
            return

        try:
            self._container_manager.terminate_container(workspace.container_id)
            logger.info(
                "Workspace cleaned up for mission %s", mission_id
            )
        except Exception:
            logger.exception(
                "Error cleaning up workspace for mission %s", mission_id
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_workspace(self, mission_id: UUID) -> WorkspaceInfo:
        """Retrieve workspace info or raise."""
        workspace = self._workspaces.get(mission_id)
        if workspace is None:
            raise RuntimeError(
                f"No workspace found for mission {mission_id}"
            )
        return workspace

    def _build_mission_container_config(
        self,
        mission_config: Dict[str, Any],
    ) -> ContainerConfig:
        """Build a ContainerConfig tailored for mission workspaces.

        Key differences from per-agent containers:
        - read_only_root is False (agents install packages)
        - Base image is python:3.11-bookworm
        - tmpfs includes /workspace as the main working area
        - 24-hour max lifetime (enforced externally)
        - Network access configurable via mission_config
        """
        execution_config = mission_config.get("execution_config", {})
        if not isinstance(execution_config, dict):
            execution_config = {}

        if "network_access" in execution_config:
            network_enabled = bool(execution_config["network_access"])
        elif "network_access" in mission_config:
            network_enabled = bool(mission_config["network_access"])
        else:
            # Backward compatibility with older key name.
            network_enabled = bool(mission_config.get("network_enabled", True))

        config = ContainerConfig(
            image=mission_config.get("image", "python:3.11-bookworm"),
            read_only_root=False,
            network_disabled=not network_enabled,
            network_mode="bridge" if network_enabled else "isolated-network",
            tmpfs_mounts={
                "/tmp": "size=200M,mode=1777",
            },
            environment={
                "WORKSPACE": WORKSPACE_ROOT,
                "PYTHONUNBUFFERED": "1",
            },
        )
        return config


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_instance: Optional[MissionWorkspaceManager] = None


def get_workspace_manager() -> MissionWorkspaceManager:
    """Get or create the global MissionWorkspaceManager singleton."""
    global _instance
    if _instance is None:
        _instance = MissionWorkspaceManager()
    return _instance
