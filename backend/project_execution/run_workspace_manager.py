from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import UUID

from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class RunWorkspaceDescriptor:
    project_space_root: Path
    run_workspace_root: Path
    sandbox_mode: str = "run_shared"


class RunWorkspaceManager:
    def __init__(self, base_root: str | None = None) -> None:
        root = base_root or os.environ.get(
            "LINX_PROJECT_EXECUTION_WORKSPACE_ROOT", "/tmp/linx_project_execution"
        )
        self.base_root = Path(root)
        self.base_root.mkdir(parents=True, exist_ok=True)

    def _project_root(self, project_id: UUID) -> Path:
        return self.base_root / "projects" / str(project_id)

    def get_project_space_root(self, project_id: UUID) -> Path:
        return self._project_root(project_id) / "project-space"

    def get_run_workspace_root(self, project_id: UUID, run_id: UUID) -> Path:
        return self._project_root(project_id) / "run-workspaces" / str(run_id)

    def ensure_project_space(self, project_id: UUID) -> Path:
        root = self.get_project_space_root(project_id)
        for relative in (
            "input",
            "shared",
            "knowledge",
            "deliverables",
            "system/revisions",
            "system/plans",
            "system/promotion",
            "system/audit",
        ):
            (root / relative).mkdir(parents=True, exist_ok=True)
        return root

    def create_run_workspace(self, project_id: UUID, run_id: UUID) -> RunWorkspaceDescriptor:
        project_space_root = self.ensure_project_space(project_id)
        run_workspace_root = self.get_run_workspace_root(project_id, run_id)
        if run_workspace_root.exists():
            shutil.rmtree(run_workspace_root, ignore_errors=True)
        run_workspace_root.mkdir(parents=True, exist_ok=True)
        for relative in (".linx/shared", ".linx/scratchpad", ".linx/artifacts", ".linx/locks"):
            (run_workspace_root / relative).mkdir(parents=True, exist_ok=True)
        self._copy_contents(project_space_root, run_workspace_root)
        return RunWorkspaceDescriptor(
            project_space_root=project_space_root,
            run_workspace_root=run_workspace_root,
            sandbox_mode="run_shared",
        )

    def materialize_to_runtime(self, run_workspace_root: Path, runtime_workdir: Path) -> None:
        runtime_workdir.mkdir(parents=True, exist_ok=True)
        self._clear_directory(runtime_workdir)
        self._copy_contents(run_workspace_root, runtime_workdir)

    def capture_runtime(self, runtime_workdir: Path, run_workspace_root: Path) -> None:
        run_workspace_root.mkdir(parents=True, exist_ok=True)
        self._clear_directory(run_workspace_root)
        self._copy_contents(runtime_workdir, run_workspace_root)

    def promote_run_workspace(self, run_workspace_root: Path, project_space_root: Path) -> None:
        project_space_root.mkdir(parents=True, exist_ok=True)
        self._copy_contents(run_workspace_root, project_space_root)

    def _clear_directory(self, root: Path) -> None:
        if not root.exists():
            return
        for child in root.iterdir():
            if child.name == ".git":
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)

    def _copy_contents(self, source_root: Path, dest_root: Path) -> None:
        if not source_root.exists():
            return
        for child in source_root.iterdir():
            if child.name in {".git", "__pycache__"}:
                continue
            destination = dest_root / child.name
            if child.is_dir() and not child.is_symlink():
                shutil.copytree(child, destination, dirs_exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(child, destination)


_run_workspace_manager: RunWorkspaceManager | None = None


def get_run_workspace_manager() -> RunWorkspaceManager:
    global _run_workspace_manager
    if _run_workspace_manager is None:
        _run_workspace_manager = RunWorkspaceManager()
    return _run_workspace_manager
