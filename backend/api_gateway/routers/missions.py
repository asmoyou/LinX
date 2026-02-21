"""Missions REST API router.

Provides endpoints for creating, managing, and monitoring missions
through their full lifecycle.
"""

import io
import mimetypes
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------


class CreateMissionRequest(BaseModel):
    title: str = Field(..., max_length=500)
    instructions: str
    department_id: Optional[UUID] = None
    mission_config: Optional[Dict[str, Any]] = None


class UpdateMissionRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    instructions: Optional[str] = None
    department_id: Optional[UUID] = None
    mission_config: Optional[Dict[str, Any]] = None


class ClarifyRequest(BaseModel):
    message: str


class MissionRoleConfigSchema(BaseModel):
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:14b"
    temperature: float = 0.3
    max_tokens: int = 4096


class MissionExecutionConfigSchema(BaseModel):
    max_retries: int = 3
    task_timeout_s: int = 600
    max_rework_cycles: int = 2
    network_access: bool = False
    max_concurrent_tasks: int = 3


class MissionSettingsRequest(BaseModel):
    leader_config: Optional[MissionRoleConfigSchema] = None
    supervisor_config: Optional[MissionRoleConfigSchema] = None
    qa_config: Optional[MissionRoleConfigSchema] = None
    temporary_worker_config: Optional[MissionRoleConfigSchema] = None
    execution_config: Optional[MissionExecutionConfigSchema] = None


class MissionResponse(BaseModel):
    mission_id: UUID
    title: str
    instructions: str
    requirements_doc: Optional[str] = None
    status: str
    created_by_user_id: UUID
    department_id: Optional[UUID] = None
    container_id: Optional[str] = None
    workspace_bucket: Optional[str] = None
    mission_config: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AttachmentResponse(BaseModel):
    attachment_id: UUID
    mission_id: UUID
    filename: str
    file_reference: str
    content_type: Optional[str] = None
    file_size: Optional[int] = None
    uploaded_at: Optional[str] = None

    class Config:
        from_attributes = True


class MissionAgentResponse(BaseModel):
    id: UUID
    mission_id: UUID
    agent_id: UUID
    role: str
    status: str
    is_temporary: bool
    assigned_at: Optional[str] = None

    class Config:
        from_attributes = True


class MissionEventResponse(BaseModel):
    event_id: UUID
    mission_id: UUID
    event_type: str
    agent_id: Optional[UUID] = None
    task_id: Optional[UUID] = None
    event_data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _mission_to_response(m) -> dict:
    """Convert a Mission ORM object to a serialisable dict."""
    return {
        "mission_id": m.mission_id,
        "title": m.title,
        "instructions": m.instructions,
        "requirements_doc": m.requirements_doc,
        "status": m.status,
        "created_by_user_id": m.created_by_user_id,
        "department_id": m.department_id,
        "container_id": m.container_id,
        "workspace_bucket": m.workspace_bucket,
        "mission_config": m.mission_config,
        "result": m.result,
        "error_message": m.error_message,
        "total_tasks": m.total_tasks,
        "completed_tasks": m.completed_tasks,
        "failed_tasks": m.failed_tasks,
        "created_at": str(m.created_at) if m.created_at else None,
        "started_at": str(m.started_at) if m.started_at else None,
        "completed_at": str(m.completed_at) if m.completed_at else None,
        "updated_at": str(m.updated_at) if m.updated_at else None,
    }


def _assert_mission_accessible(mission_id: UUID, user_id: str):
    """Ensure the mission exists and belongs to the current user."""
    from mission_system.mission_repository import get_mission as repo_get

    mission = repo_get(mission_id)
    if mission is None or mission.created_by_user_id != UUID(user_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


# ------------------------------------------------------------------
# Mission CRUD
# ------------------------------------------------------------------


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_mission(
    request: CreateMissionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new mission in draft status."""
    from mission_system.mission_repository import (
        create_mission as repo_create,
        get_mission_settings as repo_get_settings,
    )

    # Merge user's saved settings as defaults, then override with request config
    user_settings = repo_get_settings(UUID(current_user.user_id))
    merged_config = {**user_settings}
    if request.mission_config:
        merged_config.update(request.mission_config)

        # Backward compatibility: map legacy top-level execution keys into execution_config.
        legacy_exec: Dict[str, Any] = {}
        for key in (
            "max_retries",
            "task_timeout_s",
            "max_rework_cycles",
            "max_concurrent_tasks",
            "network_access",
        ):
            if key in request.mission_config:
                legacy_exec[key] = request.mission_config[key]
        if "network_enabled" in request.mission_config and "network_access" not in legacy_exec:
            legacy_exec["network_access"] = bool(request.mission_config["network_enabled"])

        request_exec = request.mission_config.get("execution_config", {})
        if not isinstance(request_exec, dict):
            request_exec = {}

        if legacy_exec or request_exec:
            effective_exec: Dict[str, Any] = {}
            if isinstance(user_settings.get("execution_config"), dict):
                effective_exec.update(user_settings["execution_config"])
            if isinstance(merged_config.get("execution_config"), dict):
                effective_exec.update(merged_config["execution_config"])
            effective_exec.update(request_exec)
            effective_exec.update(legacy_exec)
            merged_config["execution_config"] = effective_exec

    mission = repo_create(
        title=request.title,
        instructions=request.instructions,
        created_by_user_id=UUID(current_user.user_id),
        department_id=request.department_id,
        mission_config=merged_config,
    )
    return _mission_to_response(mission)


@router.get("")
async def list_missions(
    status: Optional[str] = None,
    status_filter: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List the current user's missions."""
    from mission_system.mission_repository import (
        count_missions,
        list_missions as repo_list,
    )

    user_id = UUID(current_user.user_id)
    effective_status = status_filter or status
    missions = repo_list(
        user_id=user_id,
        status=effective_status,
        limit=limit,
        offset=offset,
    )
    total = count_missions(user_id=user_id, status=effective_status)
    return {
        "items": [_mission_to_response(m) for m in missions],
        "total": total,
    }


# ------------------------------------------------------------------
# Mission Settings
# ------------------------------------------------------------------


@router.get("/settings")
async def get_settings(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get the current user's mission settings defaults."""
    from mission_system.mission_repository import get_mission_settings as repo_get_settings

    settings = repo_get_settings(UUID(current_user.user_id))
    return settings


@router.put("/settings")
async def update_settings(
    request: MissionSettingsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update the current user's mission settings defaults."""
    from mission_system.mission_repository import upsert_mission_settings
    from sqlalchemy.exc import SQLAlchemyError

    try:
        data = request.model_dump(exclude_none=True)
        # Convert nested Pydantic models to plain dicts
        for key in [
            "leader_config",
            "supervisor_config",
            "qa_config",
            "temporary_worker_config",
            "execution_config",
        ]:
            if key in data and hasattr(data[key], "model_dump"):
                data[key] = data[key].model_dump()
        settings = upsert_mission_settings(UUID(current_user.user_id), data)
        return settings
    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Mission settings storage is unavailable. "
                "Please run database migrations and try again."
            ),
        )
    except Exception as exc:
        logger.exception("Failed to update mission settings for user %s", current_user.user_id)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update mission settings: {exc}",
        )


@router.get("/{mission_id}")
async def get_mission(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get mission details by ID."""
    from mission_system.mission_repository import get_mission as repo_get

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    return _mission_to_response(mission)


@router.put("/{mission_id}")
async def update_mission(
    mission_id: UUID,
    request: UpdateMissionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a draft mission."""
    from mission_system.mission_repository import (
        get_mission as repo_get,
        update_mission_fields,
    )

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft missions can be updated")

    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if updates:
        update_mission_fields(mission_id, **updates)
    return _mission_to_response(repo_get(mission_id))


@router.delete("/{mission_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mission(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a mission. Running missions are cancelled first, then deleted."""
    from mission_system.mission_repository import (
        delete_mission as repo_delete,
        get_mission as repo_get,
    )
    from mission_system.orchestrator import get_orchestrator

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.created_by_user_id != UUID(current_user.user_id):
        raise HTTPException(status_code=404, detail="Mission not found")

    if mission.status in ("executing", "requirements", "planning", "reviewing", "qa"):
        await get_orchestrator().cancel_mission(mission_id)
    if not repo_delete(mission_id):
        raise HTTPException(status_code=404, detail="Mission not found")
    # Defensive verification to avoid "deleted locally but reappears after refresh" surprises.
    if repo_get(mission_id) is not None:
        logger.error("Mission %s still exists after delete attempt", mission_id)
        raise HTTPException(status_code=500, detail="Mission deletion did not persist")


# ------------------------------------------------------------------
# Attachments
# ------------------------------------------------------------------


@router.post("/{mission_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    mission_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Upload a file attachment to a mission."""
    import io

    from mission_system.mission_repository import (
        add_attachment,
        get_mission as repo_get,
    )
    from object_storage.minio_client import get_minio_client

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.status != "draft":
        raise HTTPException(
            status_code=400,
            detail="Attachments can only be added to draft missions",
        )

    contents = await file.read()
    minio = get_minio_client()
    bucket_name, object_key = minio.upload_file(
        bucket_type="documents",
        file_data=io.BytesIO(contents),
        filename=file.filename or "attachment",
        user_id=current_user.user_id,
        content_type=file.content_type,
    )

    att = add_attachment(
        mission_id=mission_id,
        filename=file.filename or "attachment",
        file_reference=f"{bucket_name}/{object_key}",
        content_type=file.content_type,
        file_size=len(contents),
    )
    return {
        "attachment_id": att.attachment_id,
        "filename": att.filename,
        "file_reference": att.file_reference,
        "content_type": att.content_type,
        "file_size": att.file_size,
    }


@router.get("/{mission_id}/attachments")
async def list_attachments(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all attachments for a mission."""
    from mission_system.mission_repository import list_attachments as repo_list

    return [
        {
            "attachment_id": a.attachment_id,
            "filename": a.filename,
            "file_reference": a.file_reference,
            "content_type": a.content_type,
            "file_size": a.file_size,
        }
        for a in repo_list(mission_id)
    ]


@router.delete(
    "/{mission_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_attachment(
    mission_id: UUID,
    attachment_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a mission attachment."""
    from database.connection import get_db_session
    from database.mission_models import MissionAttachment

    with get_db_session() as session:
        att = (
            session.query(MissionAttachment)
            .filter(
                MissionAttachment.attachment_id == attachment_id,
                MissionAttachment.mission_id == mission_id,
            )
            .first()
        )
        if att is None:
            raise HTTPException(status_code=404, detail="Attachment not found")
        session.delete(att)


# ------------------------------------------------------------------
# Actions
# ------------------------------------------------------------------


@router.post("/{mission_id}/start", status_code=status.HTTP_202_ACCEPTED)
async def start_mission(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Start executing a mission."""
    from mission_system.mission_repository import get_mission as repo_get
    from mission_system.orchestrator import get_orchestrator

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.status != "draft":
        raise HTTPException(status_code=400, detail="Only draft missions can be started")

    await get_orchestrator().start_mission(mission_id, UUID(current_user.user_id))
    # Re-fetch to return the updated mission with new status
    updated = repo_get(mission_id)
    return _mission_to_response(updated)


@router.post("/{mission_id}/cancel")
async def cancel_mission(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Cancel a running mission."""
    from mission_system.mission_repository import get_mission as repo_get
    from mission_system.orchestrator import get_orchestrator

    await get_orchestrator().cancel_mission(mission_id)
    # Re-fetch to return the updated mission with cancelled status
    updated = repo_get(mission_id)
    return _mission_to_response(updated)


@router.post("/{mission_id}/clarify")
async def clarify_mission(
    mission_id: UUID,
    request: ClarifyRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Answer a leader agent's clarification question."""
    from mission_system.event_emitter import get_event_emitter
    from mission_system.orchestrator import get_orchestrator

    get_orchestrator().provide_clarification(mission_id, request.message)

    # Emit a clarification_response event so it shows up in the event stream
    event = get_event_emitter().emit(
        mission_id=mission_id,
        event_type="clarification_response",
        message=request.message,
    )
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "mission_id": event.mission_id,
        "message": event.message,
        "created_at": str(event.created_at) if event.created_at else None,
    }


# ------------------------------------------------------------------
# Queries
# ------------------------------------------------------------------


@router.get("/{mission_id}/agents")
async def list_mission_agents(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List agents assigned to a mission."""
    _assert_mission_accessible(mission_id, current_user.user_id)

    from database.connection import get_db_session
    from database.mission_models import MissionAgent
    from database.models import Agent

    with get_db_session() as session:
        rows = (
            session.query(MissionAgent, Agent)
            .outerjoin(Agent, MissionAgent.agent_id == Agent.agent_id)
            .filter(MissionAgent.mission_id == mission_id)
            .order_by(MissionAgent.assigned_at)
            .all()
        )
        return [
            {
                "id": mission_agent.id,
                "mission_id": mission_agent.mission_id,
                "agent_id": mission_agent.agent_id,
                "agent_name": agent.name if agent else None,
                "role": mission_agent.role,
                "status": mission_agent.status,
                "is_temporary": mission_agent.is_temporary,
                "avatar": agent.avatar if agent else None,
            }
            for mission_agent, agent in rows
        ]


@router.get("/{mission_id}/tasks")
async def list_mission_tasks(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List tasks belonging to a mission."""
    _assert_mission_accessible(mission_id, current_user.user_id)

    from database.connection import get_db_session
    from database.models import Agent, Task

    with get_db_session() as session:
        rows = (
            session.query(Task, Agent.name.label("assigned_agent_name"))
            .outerjoin(Agent, Task.assigned_agent_id == Agent.agent_id)
            .filter(Task.mission_id == mission_id)
            .order_by(Task.created_at)
            .all()
        )
        return [
            {
                "task_id": t.task_id,
                "goal_text": t.goal_text,
                "status": t.status,
                "priority": t.priority,
                "assigned_agent_id": t.assigned_agent_id,
                "assigned_agent_name": assigned_agent_name
                or ((t.task_metadata or {}).get("assigned_agent_name")),
                "dependencies": t.dependencies or [],
                "parent_task_id": t.parent_task_id,
                "acceptance_criteria": t.acceptance_criteria,
                "result": t.result,
                "task_metadata": t.task_metadata,
            }
            for t, assigned_agent_name in rows
        ]


@router.get("/{mission_id}/events")
async def list_mission_events(
    mission_id: UUID,
    event_type: Optional[str] = None,
    limit: int = 100,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List events for a mission."""
    _assert_mission_accessible(mission_id, current_user.user_id)

    from mission_system.mission_repository import list_events

    events = list_events(mission_id, event_type=event_type, limit=limit)
    return [
        {
            "event_id": e.event_id,
            "mission_id": e.mission_id,
            "event_type": e.event_type,
            "agent_id": e.agent_id,
            "task_id": e.task_id,
            "event_data": e.event_data,
            "message": e.message,
            "created_at": str(e.created_at) if e.created_at else None,
        }
        for e in events
    ]


@router.get("/{mission_id}/deliverables")
async def list_deliverables(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List deliverables produced by a completed mission."""
    mission = _assert_mission_accessible(mission_id, current_user.user_id)

    result = mission.result or {}
    return result.get("deliverables", [])


@router.get("/{mission_id}/deliverables/download")
async def download_deliverable(
    mission_id: UUID,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download a mission deliverable by storage path."""
    from mission_system.mission_repository import get_mission as repo_get
    from object_storage.minio_client import get_minio_client

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.created_by_user_id != UUID(current_user.user_id):
        raise HTTPException(status_code=404, detail="Mission not found")

    deliverables = (mission.result or {}).get("deliverables", [])
    matched = next(
        (
            item
            for item in deliverables
            if isinstance(item, dict) and item.get("path") == path
        ),
        None,
    )
    if matched is None:
        raise HTTPException(status_code=404, detail="Deliverable not found")

    if "/" not in path:
        raise HTTPException(status_code=400, detail="Invalid deliverable path")
    bucket_name, object_key = path.split("/", 1)

    try:
        stream, metadata = get_minio_client().download_file(bucket_name, object_key)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    filename = str(matched.get("filename") or object_key.rsplit("/", 1)[-1])
    media_type = (metadata or {}).get("content_type") or "application/octet-stream"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(stream, media_type=media_type, headers=headers)


@router.get("/{mission_id}/workspace/files")
async def list_workspace_files(
    mission_id: UUID,
    path: str = "",
    recursive: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Browse the workspace file tree for a running mission."""
    _assert_mission_accessible(mission_id, current_user.user_id)

    from mission_system.workspace_manager import get_workspace_manager

    try:
        files = get_workspace_manager().list_files(
            mission_id,
            path,
            recursive=recursive,
        )
        return [
            {
                "name": f.name,
                "path": f.path,
                "size": f.size,
                "is_directory": f.is_directory,
                "modified_at": f.modified_at,
            }
            for f in files
        ]
    except RuntimeError as e:
        if str(e).startswith("No workspace found for mission"):
            # Completed/failed missions may have already cleaned up sandboxes.
            # Frontend should still be able to render deliverables without treating this as a hard error.
            return []
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{mission_id}/workspace/download")
async def download_workspace_file(
    mission_id: UUID,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download a file directly from the live mission workspace."""
    _assert_mission_accessible(mission_id, current_user.user_id)

    from mission_system.workspace_manager import get_workspace_manager

    normalized = path.replace("\\", "/").lstrip("/")
    if normalized.startswith("workspace/"):
        normalized = normalized[len("workspace/"):]

    if not normalized or ".." in normalized.split("/"):
        raise HTTPException(status_code=400, detail="Invalid workspace file path")

    try:
        content = get_workspace_manager().read_file_bytes(mission_id, normalized)
    except RuntimeError as exc:
        if str(exc).startswith("No workspace found for mission"):
            raise HTTPException(status_code=404, detail="Workspace is no longer available")
        raise HTTPException(status_code=404, detail=str(exc))

    filename = normalized.rsplit("/", 1)[-1]
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(content), media_type=media_type, headers=headers)
