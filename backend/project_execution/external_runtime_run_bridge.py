from __future__ import annotations

import base64
import io
import tarfile
import tempfile
from pathlib import Path
from typing import Any
from uuid import UUID

from database.connection import get_db_session
from database.project_execution_models import ExternalAgentDispatch, ProjectRun
from project_execution.run_workspace_manager import get_run_workspace_manager


def _resolve_run_workspace_root(run: ProjectRun) -> Path:
    runtime_context = run.runtime_context if isinstance(run.runtime_context, dict) else {}
    run_workspace = (
        runtime_context.get("run_workspace")
        if isinstance(runtime_context.get("run_workspace"), dict)
        else {}
    )
    root_path = run_workspace.get("root_path") or str(
        get_run_workspace_manager().get_run_workspace_root(run.project_id, run.run_id)
    )
    return Path(str(root_path))


def _build_workspace_archive_bytes(workspace_root: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.add(workspace_root, arcname=".")
    return buffer.getvalue()


def _safe_extract_archive_bytes(archive_bytes: bytes, target_dir: Path) -> None:
    target_root = target_dir.resolve()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            candidate = (target_root / member.name).resolve()
            if candidate != target_root and target_root not in candidate.parents:
                raise ValueError(f"Blocked unsafe archive member: {member.name}")
        archive.extractall(path=target_root)


def get_external_run_workspace_archive(*, run_id: UUID, agent_id: UUID) -> dict[str, Any] | None:
    with get_db_session() as session:
        run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()
        if run is None:
            return None
        dispatch_exists = (
            session.query(ExternalAgentDispatch.dispatch_id)
            .filter(ExternalAgentDispatch.run_id == run_id)
            .filter(ExternalAgentDispatch.agent_id == agent_id)
            .first()
        )
        if dispatch_exists is None:
            return None
        workspace_root = _resolve_run_workspace_root(run)

    workspace_root.mkdir(parents=True, exist_ok=True)
    archive_bytes = _build_workspace_archive_bytes(workspace_root)
    return {
        "archive_base64": base64.b64encode(archive_bytes).decode("utf-8"),
        "size_bytes": len(archive_bytes),
    }


def apply_external_run_workspace_archive(
    *,
    run_id: UUID,
    agent_id: UUID,
    archive_bytes: bytes,
) -> dict[str, Any] | None:
    with get_db_session() as session:
        run = session.query(ProjectRun).filter(ProjectRun.run_id == run_id).first()
        if run is None:
            return None
        dispatch_exists = (
            session.query(ExternalAgentDispatch.dispatch_id)
            .filter(ExternalAgentDispatch.run_id == run_id)
            .filter(ExternalAgentDispatch.agent_id == agent_id)
            .first()
        )
        if dispatch_exists is None:
            return None
        workspace_root = _resolve_run_workspace_root(run)

    with tempfile.TemporaryDirectory(prefix="linx-run-workspace-") as temp_dir:
        temp_root = Path(temp_dir)
        _safe_extract_archive_bytes(archive_bytes, temp_root)
        manager = get_run_workspace_manager()
        manager.capture_runtime(temp_root, workspace_root)

    file_count = 0
    total_bytes = 0
    if workspace_root.exists():
        for item in workspace_root.rglob("*"):
            if not item.is_file():
                continue
            try:
                stat = item.stat()
            except OSError:
                continue
            file_count += 1
            total_bytes += int(stat.st_size)
    return {
        "size_bytes": total_bytes,
        "workspace_file_count_estimate": file_count,
    }
