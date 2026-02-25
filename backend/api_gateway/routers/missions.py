"""Missions REST API router.

Provides endpoints for creating, managing, and monitoring missions
through their full lifecycle.
"""

import io
import mimetypes
import re
import tempfile
import urllib.parse
import zipfile
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from access_control.permissions import CurrentUser, get_current_user
from shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()
KNOWN_DELIVERABLE_SOURCE_SCOPES = {"output", "shared", "tasks", "logs", "input", "unknown"}
ALLOWED_DELIVERABLE_SCOPES = {"all", "final", "intermediate"}
RUN_BOUNDARY_EVENT_TYPES = {
    "MISSION_STARTED",
    "MISSION_RETRY_REQUESTED",
    "MISSION_PARTIAL_RETRY_REQUESTED",
}
CLARIFICATION_REQUEST_EVENT_TYPES = {"USER_CLARIFICATION_REQUESTED", "clarification_request"}
CLARIFICATION_RESPONSE_EVENT_TYPES = {"clarification_response"}
CLARIFICATION_EVENT_TYPES = (
    CLARIFICATION_REQUEST_EVENT_TYPES | CLARIFICATION_RESPONSE_EVENT_TYPES
)
RUNTIME_DELIVERABLE_PATTERNS = (
    re.compile(r"^code_[0-9a-f]{8}\.(?:py|sh|js|ts|tsx|jsx|bash|zsh|txt)$", re.IGNORECASE),
    re.compile(r"^requirements(?:\.[a-z0-9_-]+)?\.txt$", re.IGNORECASE),
)
RUNTIME_DELIVERABLE_EXACT_NAMES = {
    "runtime_requirements.txt",
}


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------


class CreateMissionRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
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
    require_dependency_review_pass: bool = True
    max_rework_cycles: int = 2
    max_qa_cycles: int = 1
    network_access: bool = False
    max_concurrent_tasks: int = 3
    debug_mode: bool = False
    enable_team_blueprint: bool = True
    prefer_existing_agents: bool = True
    allow_temporary_workers: bool = True
    auto_select_temp_skills: bool = True
    temp_worker_skill_limit: int = 3
    temp_worker_memory_scopes: List[str] = Field(
        default_factory=lambda: ["agent", "company", "user_context"]
    )
    temp_worker_knowledge_strategy: str = "owner_accessible"
    temp_worker_knowledge_limit: int = 6


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
    needs_clarification: bool = False
    pending_clarification_count: int = 0
    latest_clarification_request: Optional[str] = None
    latest_clarification_requested_at: Optional[str] = None

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


def _mission_to_response(m, clarification_state: Optional[Dict[str, Any]] = None) -> dict:
    """Convert a Mission ORM object to a serialisable dict."""
    state = clarification_state or {}
    pending_clarification_count = 0
    try:
        pending_clarification_count = max(
            0,
            int(state.get("pending_clarification_count", 0) or 0),
        )
    except (TypeError, ValueError):
        pending_clarification_count = 0

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
        "needs_clarification": bool(
            state.get("needs_clarification", pending_clarification_count > 0)
        ),
        "pending_clarification_count": pending_clarification_count,
        "latest_clarification_request": state.get("latest_clarification_request"),
        "latest_clarification_requested_at": state.get("latest_clarification_requested_at"),
    }


def _normalize_title_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _coerce_bool_flag(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
        return default
    return default


_LEADING_TITLE_PREFIX_PATTERNS = (
    r"^(请你|请帮我|请帮忙|帮我|帮忙|麻烦你|希望你|我需要你|我需要|需要你|需要)\s*",
    r"^(任务是|需求是|目标是|请完成|完成一下)\s*",
    r"^(需求|目标|任务)\s*[：:]\s*",
)


def _strip_leading_title_prefix(text: str) -> str:
    candidate = text
    for pattern in _LEADING_TITLE_PREFIX_PATTERNS:
        candidate = re.sub(pattern, "", candidate).strip()
    return candidate


def _derive_initial_mission_title(instructions: str) -> str:
    normalized = re.sub(r"\s+", " ", str(instructions or "")).strip()
    if not normalized:
        return "Untitled Mission"

    first_segment = re.split(r"[。！？.!?;\n]", normalized, maxsplit=1)[0].strip()
    candidate = _strip_leading_title_prefix(first_segment or normalized)
    if not candidate:
        candidate = first_segment or normalized

    # Keep create-time titles concise so cards look stable before mission starts.
    contains_cjk = bool(re.search(r"[\u4e00-\u9fff]", candidate))
    max_length = 24 if contains_cjk else 70
    if len(candidate) > max_length:
        candidate = candidate[:max_length].rstrip(" ,;:：。.!?、")

    return candidate or "Untitled Mission"


def _infer_deliverable_source_scope(filename: str) -> str:
    normalized = str(filename or "").replace("\\", "/").lstrip("/")
    head = normalized.split("/", 1)[0].strip().lower() if normalized else ""
    if head in KNOWN_DELIVERABLE_SOURCE_SCOPES:
        return head
    return "unknown"


def _is_runtime_process_artifact(filename: str) -> bool:
    normalized = str(filename or "").replace("\\", "/").strip("/")
    if not normalized:
        return False

    lowered = normalized.lower()
    basename = lowered.rsplit("/", 1)[-1]
    if basename in RUNTIME_DELIVERABLE_EXACT_NAMES:
        return True
    if basename.endswith((".pyc", ".pyo")):
        return True
    if "/__pycache__/" in f"/{lowered}/":
        return True
    return any(pattern.match(basename) for pattern in RUNTIME_DELIVERABLE_PATTERNS)


def _build_content_disposition(filename: str, disposition: str = "attachment") -> str:
    normalized_name = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    if not normalized_name:
        normalized_name = "download"

    ext_ascii = ""
    if "." in normalized_name:
        raw_ext = normalized_name.rsplit(".", 1)[-1]
        cleaned_ext = re.sub(r"[^A-Za-z0-9]+", "", raw_ext)
        if cleaned_ext:
            ext_ascii = cleaned_ext.lower()

    ascii_name = normalized_name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._")
    if not ascii_name or (ext_ascii and ascii_name.lower() == ext_ascii):
        ascii_name = f"download.{ext_ascii}" if ext_ascii else "download"

    encoded_name = urllib.parse.quote(normalized_name)
    safe_disposition = "inline" if disposition == "inline" else "attachment"
    return f'{safe_disposition}; filename="{ascii_name}"; ' f"filename*=UTF-8''{encoded_name}"


def _normalize_deliverable_item(item: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    storage_path = item.get("path")
    if not isinstance(storage_path, str) or not storage_path.strip():
        return None

    normalized = dict(item)
    filename = str(normalized.get("filename") or "").strip()
    raw_scope = str(normalized.get("source_scope") or "").strip().lower()

    raw_is_target = normalized.get("is_target")
    inferred_is_target: Optional[bool] = None
    if isinstance(raw_is_target, bool):
        inferred_is_target = raw_is_target
    elif raw_is_target is not None:
        inferred_is_target = bool(raw_is_target)

    if raw_scope in KNOWN_DELIVERABLE_SOURCE_SCOPES:
        source_scope = raw_scope
    else:
        source_scope = _infer_deliverable_source_scope(filename)
        if source_scope == "unknown" and inferred_is_target is not None:
            source_scope = "output" if inferred_is_target else "shared"

    runtime_artifact = _is_runtime_process_artifact(filename)
    is_target = inferred_is_target if inferred_is_target is not None else source_scope == "output"
    if runtime_artifact:
        is_target = False
        if source_scope == "output":
            source_scope = "shared"

    raw_kind = str(normalized.get("artifact_kind") or "").strip().lower()
    artifact_kind = (
        raw_kind
        if raw_kind in {"final", "intermediate"}
        else ("final" if is_target else "intermediate")
    )
    if runtime_artifact:
        artifact_kind = "intermediate"

    normalized["filename"] = filename or storage_path.split("/", 1)[-1]
    normalized["path"] = storage_path
    normalized["is_target"] = bool(is_target)
    normalized["source_scope"] = source_scope
    normalized["artifact_kind"] = artifact_kind
    return normalized


def _normalize_mission_deliverables(raw_items: Any) -> List[Dict[str, Any]]:
    items = raw_items if isinstance(raw_items, list) else []
    normalized: List[Dict[str, Any]] = []
    for item in items:
        parsed = _normalize_deliverable_item(item)
        if parsed is not None:
            normalized.append(parsed)
    return normalized


def _filter_deliverables_by_scope(
    items: List[Dict[str, Any]],
    scope: str = "all",
) -> List[Dict[str, Any]]:
    if scope == "all":
        return items
    if scope == "final":
        return [
            item
            for item in items
            if item.get("artifact_kind") == "final" or bool(item.get("is_target"))
        ]
    if scope == "intermediate":
        return [
            item
            for item in items
            if item.get("artifact_kind") == "intermediate" or not bool(item.get("is_target"))
        ]
    return items


def _split_storage_path(storage_path: str) -> Optional[Tuple[str, str]]:
    value = str(storage_path or "").strip()
    if "/" not in value:
        return None
    bucket_name, object_key = value.split("/", 1)
    bucket_name = bucket_name.strip()
    object_key = object_key.strip().lstrip("/")
    if not bucket_name or not object_key:
        return None
    return bucket_name, object_key


def _collect_mission_storage_objects(mission: Any) -> List[Tuple[str, str]]:
    objects: set[Tuple[str, str]] = set()

    for attachment in getattr(mission, "attachments", []) or []:
        parsed = _split_storage_path(getattr(attachment, "file_reference", ""))
        if parsed is not None:
            objects.add(parsed)

    result_payload = getattr(mission, "result", None)
    if isinstance(result_payload, dict):
        deliverables = _normalize_mission_deliverables(result_payload.get("deliverables", []))
        for item in deliverables:
            parsed = _split_storage_path(str(item.get("path") or ""))
            if parsed is not None:
                objects.add(parsed)

        snapshot_candidates: List[Any] = [result_payload.get("workspace_snapshot")]
        history = result_payload.get("workspace_snapshots")
        if isinstance(history, list):
            snapshot_candidates.extend(history)
        for candidate in snapshot_candidates:
            path = candidate if isinstance(candidate, str) else candidate.get("path") if isinstance(candidate, dict) else ""
            parsed = _split_storage_path(str(path or ""))
            if parsed is not None:
                objects.add(parsed)

    return sorted(objects)


def _extract_clarification_request_text(event: Any) -> Optional[str]:
    event_data = getattr(event, "event_data", None)
    if isinstance(event_data, dict):
        questions = event_data.get("questions")
        if isinstance(questions, str):
            normalized = questions.strip()
            if normalized:
                return normalized

    message = getattr(event, "message", None)
    if isinstance(message, str):
        normalized = message.strip()
        if normalized:
            return normalized
    return None


def _compute_clarification_state(
    events: List[Any],
    *,
    boundary_ts: Optional[datetime],
) -> Dict[str, Any]:
    pending_count = 0
    latest_request_text: Optional[str] = None
    latest_request_ts: Optional[datetime] = None

    for event in events:
        created_at = getattr(event, "created_at", None)
        if boundary_ts is not None and created_at is not None and created_at < boundary_ts:
            continue

        event_type = str(getattr(event, "event_type", "") or "")
        if event_type in CLARIFICATION_REQUEST_EVENT_TYPES:
            pending_count += 1
            latest_request_text = _extract_clarification_request_text(event)
            latest_request_ts = created_at
        elif event_type in CLARIFICATION_RESPONSE_EVENT_TYPES and pending_count > 0:
            pending_count -= 1

    return {
        "needs_clarification": pending_count > 0,
        "pending_clarification_count": pending_count,
        "latest_clarification_request": latest_request_text,
        "latest_clarification_requested_at": (
            str(latest_request_ts) if latest_request_ts is not None else None
        ),
    }


def _build_mission_clarification_state_map(mission_ids: List[UUID]) -> Dict[UUID, Dict[str, Any]]:
    if not mission_ids:
        return {}

    from database.connection import get_db_session
    from database.mission_models import MissionEvent

    with get_db_session() as session:
        boundary_rows = (
            session.query(MissionEvent.mission_id, MissionEvent.created_at)
            .filter(
                MissionEvent.mission_id.in_(mission_ids),
                MissionEvent.event_type.in_(list(RUN_BOUNDARY_EVENT_TYPES)),
            )
            .order_by(MissionEvent.mission_id.asc(), MissionEvent.created_at.desc())
            .all()
        )
        boundaries: Dict[UUID, datetime] = {}
        for mission_id, created_at in boundary_rows:
            if mission_id not in boundaries and created_at is not None:
                boundaries[mission_id] = created_at

        clarification_events = (
            session.query(MissionEvent)
            .filter(
                MissionEvent.mission_id.in_(mission_ids),
                MissionEvent.event_type.in_(list(CLARIFICATION_EVENT_TYPES)),
            )
            .order_by(MissionEvent.mission_id.asc(), MissionEvent.created_at.asc())
            .all()
        )

    events_by_mission: Dict[UUID, List[Any]] = defaultdict(list)
    for event in clarification_events:
        events_by_mission[event.mission_id].append(event)

    state_map: Dict[UUID, Dict[str, Any]] = {}
    for mission_id in mission_ids:
        state_map[mission_id] = _compute_clarification_state(
            events_by_mission.get(mission_id, []),
            boundary_ts=boundaries.get(mission_id),
        )
    return state_map


def _get_latest_run_boundary_ts(mission_id: UUID) -> Optional[datetime]:
    """Return timestamp of latest mission run boundary event, if present."""
    from database.connection import get_db_session
    from database.mission_models import MissionEvent

    with get_db_session() as session:
        boundary = (
            session.query(MissionEvent.created_at)
            .filter(
                MissionEvent.mission_id == mission_id,
                MissionEvent.event_type.in_(list(RUN_BOUNDARY_EVENT_TYPES)),
            )
            .order_by(MissionEvent.created_at.desc())
            .first()
        )
    if boundary is None:
        return None
    return boundary[0]


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
            "require_dependency_review_pass",
            "max_rework_cycles",
            "max_qa_cycles",
            "max_concurrent_tasks",
            "network_access",
            "debug_mode",
            "enable_team_blueprint",
            "prefer_existing_agents",
            "allow_temporary_workers",
            "auto_select_temp_skills",
            "temp_worker_skill_limit",
            "temp_worker_memory_scopes",
            "temp_worker_knowledge_strategy",
            "temp_worker_knowledge_limit",
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

    normalized_title = _normalize_title_text(request.title)
    requested_auto_generate_title = False
    if isinstance(request.mission_config, dict):
        requested_auto_generate_title = _coerce_bool_flag(
            request.mission_config.get("auto_generate_title"),
            default=False,
        )
    auto_generate_title = requested_auto_generate_title or len(normalized_title) == 0
    effective_title = normalized_title or _derive_initial_mission_title(request.instructions)

    if auto_generate_title:
        merged_config["auto_generate_title"] = True
        seed_title = _normalize_title_text(str(merged_config.get("auto_title_seed") or ""))
        merged_config["auto_title_seed"] = seed_title or effective_title
    else:
        merged_config.pop("auto_generate_title", None)
        merged_config.pop("auto_title_seed", None)

    mission = repo_create(
        title=effective_title,
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
    clarification_state_map = _build_mission_clarification_state_map(
        [mission.mission_id for mission in missions]
    )
    return {
        "items": [
            _mission_to_response(
                mission,
                clarification_state=clarification_state_map.get(mission.mission_id),
            )
            for mission in missions
        ],
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
    mission = _assert_mission_accessible(mission_id, current_user.user_id)
    clarification_state = _build_mission_clarification_state_map([mission_id]).get(mission_id)
    return _mission_to_response(mission, clarification_state=clarification_state)


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
    from mission_system.workspace_manager import get_workspace_manager
    from mission_system.mission_repository import (
        delete_mission as repo_delete,
        get_mission as repo_get,
    )
    from mission_system.orchestrator import get_orchestrator
    from object_storage.minio_client import get_minio_client
    from virtualization.container_manager import get_docker_cleanup_manager

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.created_by_user_id != UUID(current_user.user_id):
        raise HTTPException(status_code=404, detail="Mission not found")

    known_container_ids: set[str] = set()
    if getattr(mission, "container_id", None):
        known_container_ids.add(str(mission.container_id))

    if mission.status in ("executing", "requirements", "planning", "reviewing", "qa"):
        await get_orchestrator().cancel_mission(mission_id)

    refreshed_mission = repo_get(mission_id)
    if refreshed_mission is not None:
        mission = refreshed_mission
        if getattr(mission, "container_id", None):
            known_container_ids.add(str(mission.container_id))

    # Always attempt workspace/container cleanup before deleting mission row.
    try:
        get_workspace_manager().cleanup_workspace(mission_id)
    except Exception:
        logger.warning("Workspace cleanup failed before mission delete: %s", mission_id, exc_info=True)

    if known_container_ids:
        cleanup_manager = get_docker_cleanup_manager()
        for container_id in known_container_ids:
            if not container_id:
                continue
            try:
                cleanup_manager.cleanup_container_by_internal_id(container_id)
            except Exception:
                logger.warning(
                    "Failed to force-clean mission container %s before delete",
                    container_id,
                    exc_info=True,
                )

    storage_objects = _collect_mission_storage_objects(mission)
    if storage_objects:
        minio = get_minio_client()
        for bucket_name, object_key in storage_objects:
            try:
                minio.delete_file(bucket_name, object_key)
            except Exception:
                logger.warning(
                    "Failed to delete mission storage object %s/%s during mission delete",
                    bucket_name,
                    object_key,
                    exc_info=True,
                )

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
    from object_storage.minio_client import get_minio_client

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

        parsed_ref = _split_storage_path(att.file_reference)
        if parsed_ref is not None:
            bucket_name, object_key = parsed_ref
            try:
                get_minio_client().delete_file(bucket_name, object_key)
            except Exception:
                logger.warning(
                    "Failed to delete attachment object %s/%s for mission %s",
                    bucket_name,
                    object_key,
                    mission_id,
                    exc_info=True,
                )
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


@router.post("/{mission_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_mission(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Manually retry a failed/cancelled mission from a clean execution state."""
    from mission_system.event_emitter import get_event_emitter
    from mission_system.mission_repository import (
        get_mission as repo_get,
        reset_failed_mission_for_retry,
    )
    from mission_system.orchestrator import get_orchestrator

    mission = _assert_mission_accessible(mission_id, current_user.user_id)
    if mission.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=400,
            detail="Only failed or cancelled missions can be retried",
        )

    previous_error = mission.error_message
    previous_status = mission.status
    reset_failed_mission_for_retry(mission_id)
    get_event_emitter().emit(
        mission_id=mission_id,
        event_type="MISSION_RETRY_REQUESTED",
        data={"previous_error": previous_error, "previous_status": previous_status},
        message="Manual retry requested",
    )

    await get_orchestrator().start_mission(mission_id, UUID(current_user.user_id))
    updated = repo_get(mission_id)
    return _mission_to_response(updated)


@router.post("/{mission_id}/retry-failed", status_code=status.HTTP_202_ACCEPTED)
async def retry_failed_mission_parts(
    mission_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Retry only failed/unfinished task parts for a failed/cancelled mission."""
    from mission_system.exceptions import MissionError
    from mission_system.mission_repository import get_mission as repo_get
    from mission_system.orchestrator import get_orchestrator

    mission = _assert_mission_accessible(mission_id, current_user.user_id)
    if mission.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=400,
            detail="Only failed or cancelled missions can retry failed parts",
        )

    try:
        await get_orchestrator().retry_failed_parts(mission_id, UUID(current_user.user_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except MissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    updated = repo_get(mission_id)
    clarification_state = _build_mission_clarification_state_map([mission_id]).get(mission_id)
    return _mission_to_response(updated, clarification_state=clarification_state)


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
    latest_run_only: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List events for a mission."""
    _assert_mission_accessible(mission_id, current_user.user_id)

    from mission_system.mission_repository import list_events

    events = list_events(mission_id, event_type=event_type, limit=limit)
    if latest_run_only:
        boundary_ts = _get_latest_run_boundary_ts(mission_id)
        if boundary_ts is not None:
            events = [
                event for event in events if event.created_at and event.created_at >= boundary_ts
            ]
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
    scope: str = "all",
    current_user: CurrentUser = Depends(get_current_user),
):
    """List mission artifacts.

    scope:
    - all: final deliverables + intermediate/process artifacts.
    - final: target/final deliverables only.
    - intermediate: non-target process artifacts only.
    """
    mission = _assert_mission_accessible(mission_id, current_user.user_id)
    normalized_scope = (scope or "all").strip().lower()
    if normalized_scope not in ALLOWED_DELIVERABLE_SCOPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scope: {scope}. Allowed values: all, final, intermediate",
        )

    result = mission.result or {}
    items = _normalize_mission_deliverables(result.get("deliverables", []))
    return _filter_deliverables_by_scope(items, normalized_scope)


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

    deliverables = _normalize_mission_deliverables((mission.result or {}).get("deliverables", []))
    matched = next(
        (item for item in deliverables if isinstance(item, dict) and item.get("path") == path),
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
    headers = {
        "Content-Disposition": _build_content_disposition(filename, disposition="attachment")
    }
    return StreamingResponse(stream, media_type=media_type, headers=headers)


@router.get("/{mission_id}/deliverables/archive")
async def download_deliverables_archive(
    mission_id: UUID,
    target_only: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download mission deliverables as a zip archive.

    Args:
        mission_id: Mission identifier.
        target_only: When true, include only deliverables marked as `is_target`.
    """
    from mission_system.mission_repository import get_mission as repo_get
    from object_storage.minio_client import get_minio_client

    mission = repo_get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")
    if mission.created_by_user_id != UUID(current_user.user_id):
        raise HTTPException(status_code=404, detail="Mission not found")

    raw_deliverables = _normalize_mission_deliverables(
        (mission.result or {}).get("deliverables", [])
    )
    deliverables = _filter_deliverables_by_scope(
        raw_deliverables,
        "final" if target_only else "all",
    )

    if not deliverables:
        raise HTTPException(status_code=404, detail="No deliverables available for archive")

    minio = get_minio_client()
    archive_file = tempfile.SpooledTemporaryFile(max_size=20 * 1024 * 1024, mode="w+b")
    used_arc_names: set[str] = set()

    def _normalize_archive_path(value: str, index: int) -> str:
        normalized = str(value or "").replace("\\", "/").strip("/")
        safe_parts = [part for part in normalized.split("/") if part not in {"", ".", ".."}]
        if not safe_parts:
            return f"file-{index}"
        candidate = "/".join(safe_parts)
        if candidate not in used_arc_names:
            return candidate

        base, ext = (candidate.rsplit(".", 1) + [""])[:2] if "." in candidate else (candidate, "")
        suffix = 2
        while True:
            next_name = f"{base}-{suffix}.{ext}" if ext else f"{base}-{suffix}"
            if next_name not in used_arc_names:
                return next_name
            suffix += 1

    with zipfile.ZipFile(archive_file, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for index, item in enumerate(deliverables, start=1):
            storage_path = str(item.get("path") or "")
            if "/" not in storage_path:
                continue
            bucket_name, object_key = storage_path.split("/", 1)
            filename = str(item.get("filename") or object_key.rsplit("/", 1)[-1])
            arcname = _normalize_archive_path(filename, index)

            try:
                stream, _metadata = minio.download_file(bucket_name, object_key)
                content = stream.read()
                if hasattr(stream, "close"):
                    stream.close()
            except Exception as exc:
                logger.warning(
                    "Skipping deliverable while building archive",
                    extra={
                        "mission_id": str(mission_id),
                        "path": storage_path,
                        "error": str(exc),
                    },
                )
                continue

            zf.writestr(arcname, content)
            used_arc_names.add(arcname)

    if not used_arc_names:
        archive_file.close()
        raise HTTPException(status_code=404, detail="No downloadable deliverables found")

    archive_file.seek(0)
    safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", mission.title or "mission").strip("_")
    if not safe_title:
        safe_title = "mission"
    scope_suffix = "targets" if target_only else "all"
    archive_name = f"{safe_title}_{scope_suffix}_deliverables.zip"
    headers = {
        "Content-Disposition": _build_content_disposition(
            archive_name,
            disposition="attachment",
        )
    }
    return StreamingResponse(
        archive_file,
        media_type="application/zip",
        headers=headers,
        background=BackgroundTask(archive_file.close),
    )


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
        normalized = normalized[len("workspace/") :]

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
    headers = {
        "Content-Disposition": _build_content_disposition(filename, disposition="attachment")
    }
    return StreamingResponse(io.BytesIO(content), media_type=media_type, headers=headers)
