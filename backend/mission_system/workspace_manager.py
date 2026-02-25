"""Mission Workspace Manager.

Provides a shared Docker container workspace for mission execution.
All agents in a mission share a single container with a structured
directory layout for inputs, output, tasks, shared files, and logs.
"""

import base64
import io
import logging
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from object_storage.minio_client import get_minio_client
from virtualization.container_manager import (
    ContainerConfig,
    ContainerManager,
    get_container_manager,
)

logger = logging.getLogger(__name__)

# Standard workspace directory layout inside the container
WORKSPACE_ROOT = "/workspace"
WORKSPACE_DIRS = ["input", "output", "tasks", "shared", "logs"]
MISSION_HOST_WORKSPACE_ROOT = Path(
    os.getenv(
        "LINX_MISSION_WORKSPACE_ROOT",
        str(Path(tempfile.gettempdir()) / "linx_mission_workspaces"),
    )
)
RUNTIME_ARTIFACT_NAME_PATTERNS = (
    re.compile(r"^code_[0-9a-f]{8}\.(?:py|sh|js|ts|tsx|jsx|bash|zsh|txt)$", re.IGNORECASE),
    re.compile(r"^requirements(?:\.[a-z0-9_-]+)?\.txt$", re.IGNORECASE),
)
RUNTIME_ARTIFACT_EXACT_NAMES = {
    "runtime_requirements.txt",
}


@dataclass
class WorkspaceInfo:
    """Information about a created mission workspace."""

    mission_id: UUID
    container_id: str
    workspace_path: str
    host_workspace_path: Optional[str] = None
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
    source_scope: str = "output"
    artifact_kind: str = "final"


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

    @staticmethod
    def _is_runtime_process_artifact(relative_path: str) -> bool:
        """Return True for runtime/generated artifacts that should not be final deliverables."""
        normalized = str(relative_path or "").replace("\\", "/").strip("/")
        if not normalized:
            return True

        lowered = normalized.lower()
        basename = lowered.rsplit("/", 1)[-1]
        if basename in RUNTIME_ARTIFACT_EXACT_NAMES:
            return True
        if basename.endswith((".pyc", ".pyo")):
            return True
        if "/__pycache__/" in f"/{lowered}/":
            return True
        return any(pattern.match(basename) for pattern in RUNTIME_ARTIFACT_NAME_PATTERNS)

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
        host_workspace_path = self._prepare_host_workspace(mission_id)
        container_config = self._build_mission_container_config(
            mission_id=mission_id,
            mission_config=config,
            host_workspace_path=host_workspace_path,
        )

        container_id = self._container_manager.create_container(
            agent_id=mission_id,  # reuse agent_id param for mission ownership
            config=container_config,
        )

        started = self._container_manager.start_container(container_id)
        if not started:
            raise RuntimeError(f"Failed to start workspace container for mission {mission_id}")

        # Initialise workspace directories
        mkdir_cmd = " ".join(f"{WORKSPACE_ROOT}/{d}" for d in WORKSPACE_DIRS)
        exit_code, _, stderr = self._container_manager.exec_in_container(
            container_id,
            f"mkdir -p {mkdir_cmd}",
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to create workspace dirs: {stderr}")

        workspace = WorkspaceInfo(
            mission_id=mission_id,
            container_id=container_id,
            workspace_path=WORKSPACE_ROOT,
            host_workspace_path=host_workspace_path,
        )
        self._workspaces[mission_id] = workspace

        logger.info(
            "Mission workspace created",
            extra={
                "mission_id": str(mission_id),
                "container_id": container_id,
                "host_workspace_path": host_workspace_path,
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
                logger.error("Failed to copy attachment %s: %s", filename, stderr)

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

    def get_container_id(self, mission_id: UUID) -> Optional[str]:
        """Return workspace container ID for a mission, if available."""
        workspace = self._workspaces.get(mission_id)
        if workspace is None:
            return None
        return workspace.container_id

    def get_host_workspace_path(self, mission_id: UUID) -> Optional[str]:
        """Return host workspace path for a mission, if available."""
        workspace = self._workspaces.get(mission_id)
        if workspace is None:
            return None
        return workspace.host_workspace_path

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
        recursive: bool = False,
    ) -> List[FileInfo]:
        """List files in a workspace directory.

        Args:
            mission_id: Mission UUID.
            path: Relative path from /workspace (default: root).
            recursive: Whether to include nested files/directories recursively.

        Returns:
            List of FileInfo objects.
        """
        workspace = self._get_workspace(mission_id)
        target = f"{WORKSPACE_ROOT}/{path}" if path else WORKSPACE_ROOT

        # Use ls -la with a machine-friendly format
        find_command = (
            f"find '{target}' -mindepth 1 "
            + ("" if recursive else "-maxdepth 1 ")
            + "-printf '%y %s %T@ %p\\n' 2>/dev/null || "
            + f"ls -la '{target}'"
        )
        exit_code, stdout, stderr = self._container_manager.exec_in_container(
            workspace.container_id,
            find_command,
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

    def read_file_bytes(self, mission_id: UUID, path: str) -> bytes:
        """Read a file from the workspace container as bytes.

        Args:
            mission_id: Mission UUID.
            path: Relative path from /workspace.

        Returns:
            Raw file bytes.
        """
        workspace = self._get_workspace(mission_id)
        safe_path = path.replace("\\", "/").lstrip("/")
        if safe_path.startswith("workspace/"):
            safe_path = safe_path[len("workspace/") :]

        if not safe_path:
            raise RuntimeError("Invalid file path")

        full_path = f"{WORKSPACE_ROOT}/{safe_path}"
        exit_code, stdout, stderr = self._container_manager.exec_in_container(
            workspace.container_id,
            f"base64 '{full_path}'",
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to read file {path}: {stderr}")

        try:
            return base64.b64decode(stdout.strip())
        except Exception as exc:
            raise RuntimeError(f"Failed to decode file {path}: {exc}")

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
            (f"{WORKSPACE_ROOT}/output", True, "output"),
            (f"{WORKSPACE_ROOT}/shared", False, "shared"),
            (f"{WORKSPACE_ROOT}/tasks", False, "tasks"),
            (f"{WORKSPACE_ROOT}/logs", False, "logs"),
            (f"{WORKSPACE_ROOT}/input", False, "input"),
        ]

        seen_filepaths = set()
        for source_dir, is_target, source_scope in source_dirs:
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
                if not relative_path:
                    continue
                runtime_artifact = self._is_runtime_process_artifact(relative_path)
                effective_is_target = is_target and not runtime_artifact

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
                        is_target=effective_is_target,
                        source_scope=source_scope,
                        artifact_kind="final" if effective_is_target else "intermediate",
                    )
                )

        # Compatibility fallback:
        # Some agent outputs are written to /workspace root instead of /workspace/output.
        # Persist these root files as final deliverables so users can still retrieve them.
        exit_code, stdout, _stderr = self._container_manager.exec_in_container(
            workspace.container_id,
            f"find '{WORKSPACE_ROOT}' -maxdepth 1 -type f -printf '%s %p\\n'",
        )
        if exit_code == 0 and stdout.strip():
            for line in stdout.strip().splitlines():
                parts = line.split(None, 1)
                if len(parts) != 2:
                    continue
                size_str, filepath = parts
                if filepath in seen_filepaths:
                    continue
                seen_filepaths.add(filepath)

                relative_path = filepath.replace(f"{WORKSPACE_ROOT}/", "", 1)
                if not relative_path:
                    continue
                runtime_artifact = self._is_runtime_process_artifact(relative_path)

                rc, content, err = self._container_manager.exec_in_container(
                    workspace.container_id,
                    f"base64 '{filepath}'",
                )
                if rc != 0:
                    logger.warning("Failed to read root deliverable %s: %s", relative_path, err)
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
                        is_target=not runtime_artifact,
                        source_scope="shared" if runtime_artifact else "output",
                        artifact_kind="intermediate" if runtime_artifact else "final",
                    )
                )

        logger.info(
            "Collected %d deliverables for mission %s",
            len(deliverables),
            mission_id,
        )
        return deliverables

    def snapshot_workspace(
        self,
        mission_id: UUID,
        reason: str = "automatic",
    ) -> Dict[str, Any]:
        """Snapshot the live workspace filesystem into object storage.

        The snapshot archive is uploaded to MinIO artifacts storage and can be
        restored later when retrying failed mission parts.
        """
        workspace = self._get_workspace(mission_id)
        minio = get_minio_client()

        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        archive_name = f"workspace_snapshot_{timestamp}.tar.gz"
        archive_path = f"/tmp/{archive_name}"

        try:
            exit_code, _stdout, stderr = self._container_manager.exec_in_container(
                workspace.container_id,
                f"tar -czf '{archive_path}' -C '{WORKSPACE_ROOT}' .",
            )
            if exit_code != 0:
                raise RuntimeError(f"Failed to create workspace snapshot archive: {stderr}")

            exit_code, file_count_stdout, _stderr = self._container_manager.exec_in_container(
                workspace.container_id,
                f"find '{WORKSPACE_ROOT}' -type f | wc -l",
            )
            file_count = 0
            if exit_code == 0:
                try:
                    file_count = int((file_count_stdout or "0").strip() or "0")
                except ValueError:
                    file_count = 0

            exit_code, archive_b64, stderr = self._container_manager.exec_in_container(
                workspace.container_id,
                f"base64 '{archive_path}'",
            )
            if exit_code != 0:
                raise RuntimeError(f"Failed to read workspace snapshot archive: {stderr}")

            try:
                archive_bytes = base64.b64decode((archive_b64 or "").strip())
            except Exception as exc:
                raise RuntimeError(f"Failed to decode workspace snapshot archive: {exc}")

            metadata = {
                "artifact_type": "workspace_snapshot",
                "mission_id": str(mission_id),
                "snapshot_reason": str(reason or "automatic"),
                "snapshot_timestamp": datetime.utcnow().isoformat(),
            }
            bucket_name, object_key = minio.upload_file(
                bucket_type="artifacts",
                file_data=io.BytesIO(archive_bytes),
                filename=archive_name,
                user_id=str(mission_id),
                content_type="application/gzip",
                metadata=metadata,
            )

            snapshot_record: Dict[str, Any] = {
                "path": f"{bucket_name}/{object_key}",
                "filename": archive_name,
                "size": len(archive_bytes),
                "file_count": file_count,
                "reason": str(reason or "automatic"),
                "created_at": datetime.utcnow().isoformat(),
            }
            return snapshot_record
        finally:
            self._container_manager.exec_in_container(
                workspace.container_id,
                f"rm -f '{archive_path}'",
            )

    def restore_workspace(
        self,
        mission_id: UUID,
        storage_path: str,
    ) -> Dict[str, Any]:
        """Restore workspace content from an object storage snapshot archive."""
        workspace = self._get_workspace(mission_id)
        minio = get_minio_client()

        parsed_path = self._split_storage_path(storage_path)
        if parsed_path is None:
            raise RuntimeError(f"Invalid workspace snapshot path: {storage_path}")
        bucket_name, object_key = parsed_path

        archive_name = object_key.rsplit("/", 1)[-1] or "workspace_snapshot_restore.tar.gz"
        archive_path = f"/tmp/{archive_name}"

        try:
            stream, _meta = minio.download_file(bucket_name, object_key)
            archive_bytes = stream.read()
            archive_b64 = base64.b64encode(archive_bytes).decode("ascii")

            self._write_base64_to_container_file(
                container_id=workspace.container_id,
                base64_payload=archive_b64,
                target_path=archive_path,
            )

            exit_code, _stdout, stderr = self._container_manager.exec_in_container(
                workspace.container_id,
                f"tar -xzf '{archive_path}' -C '{WORKSPACE_ROOT}' --overwrite",
            )
            if exit_code != 0:
                raise RuntimeError(f"Failed to extract workspace snapshot archive: {stderr}")

            exit_code, file_count_stdout, _stderr = self._container_manager.exec_in_container(
                workspace.container_id,
                f"find '{WORKSPACE_ROOT}' -type f | wc -l",
            )
            restored_file_count = 0
            if exit_code == 0:
                try:
                    restored_file_count = int((file_count_stdout or "0").strip() or "0")
                except ValueError:
                    restored_file_count = 0

            return {
                "path": storage_path,
                "restored_file_count": restored_file_count,
                "archive_size": len(archive_bytes),
                "restored_at": datetime.utcnow().isoformat(),
            }
        finally:
            self._container_manager.exec_in_container(
                workspace.container_id,
                f"rm -f '{archive_path}' '{archive_path}.b64'",
            )

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
            if workspace.host_workspace_path:
                try:
                    shutil.rmtree(workspace.host_workspace_path, ignore_errors=True)
                except Exception:
                    logger.exception(
                        "Error cleaning host workspace for mission %s", mission_id
                    )
            logger.info("Workspace cleaned up for mission %s", mission_id)
        except Exception:
            logger.exception("Error cleaning up workspace for mission %s", mission_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_workspace(self, mission_id: UUID) -> WorkspaceInfo:
        """Retrieve workspace info or raise."""
        workspace = self._workspaces.get(mission_id)
        if workspace is None:
            raise RuntimeError(f"No workspace found for mission {mission_id}")
        return workspace

    @staticmethod
    def _split_storage_path(storage_path: str) -> Optional[Tuple[str, str]]:
        """Split MinIO storage path (<bucket>/<object_key>) into tuple."""
        value = str(storage_path or "").strip()
        if "/" not in value:
            return None
        bucket_name, object_key = value.split("/", 1)
        bucket_name = bucket_name.strip()
        object_key = object_key.strip().lstrip("/")
        if not bucket_name or not object_key:
            return None
        return bucket_name, object_key

    def _write_base64_to_container_file(
        self,
        container_id: str,
        base64_payload: str,
        target_path: str,
        *,
        chunk_size: int = 16384,
    ) -> None:
        """Write base64 payload into a container file in chunks.

        Chunked writes avoid shell argument-size limits for larger archives.
        """
        temp_b64_path = f"{target_path}.b64"

        exit_code, _stdout, stderr = self._container_manager.exec_in_container(
            container_id,
            f": > '{temp_b64_path}'",
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to initialize base64 temp file: {stderr}")

        for index in range(0, len(base64_payload), chunk_size):
            chunk = base64_payload[index : index + chunk_size]
            exit_code, _stdout, stderr = self._container_manager.exec_in_container(
                container_id,
                f"printf '%s' '{chunk}' >> '{temp_b64_path}'",
            )
            if exit_code != 0:
                raise RuntimeError(
                    "Failed to write base64 chunk to container "
                    f"(offset={index}, size={len(chunk)}): {stderr}"
                )

        exit_code, _stdout, stderr = self._container_manager.exec_in_container(
            container_id,
            f"base64 -d '{temp_b64_path}' > '{target_path}'",
        )
        if exit_code != 0:
            raise RuntimeError(f"Failed to decode base64 payload in container: {stderr}")

    @staticmethod
    def _prepare_host_workspace(mission_id: UUID) -> str:
        """Create a dedicated host workspace directory for a mission."""
        workspace_root = MISSION_HOST_WORKSPACE_ROOT.expanduser()
        workspace_path = workspace_root / str(mission_id)
        if workspace_path.exists():
            shutil.rmtree(workspace_path, ignore_errors=True)
        workspace_path.mkdir(parents=True, exist_ok=True)
        return str(workspace_path.resolve())

    def _build_mission_container_config(
        self,
        mission_id: UUID,
        mission_config: Dict[str, Any],
        host_workspace_path: str,
    ) -> ContainerConfig:
        """Build a ContainerConfig tailored for mission workspaces.

        Key differences from per-agent containers:
        - read_only_root is False (agents install packages)
        - Base image is python:3.11-bookworm
        - /tmp uses tmpfs for ephemeral temporary files
        - /workspace is bind-mounted to a dedicated host mission workspace
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
            name=f"mission-{str(mission_id).replace('-', '')[:12]}",
            image=mission_config.get("image", "python:3.11-bookworm"),
            read_only_root=False,
            network_disabled=not network_enabled,
            network_mode="bridge" if network_enabled else "isolated-network",
            tmpfs_mounts={
                "/tmp": "size=200M,mode=1777",
            },
            volume_mounts={
                host_workspace_path: WORKSPACE_ROOT,
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
