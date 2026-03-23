"""Skills API router.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
- docs/backend/skill-type-classification.md
"""

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from access_control.skill_access import (
    SKILL_ACCESS_PRIVATE,
    SKILL_ACCESS_PUBLIC,
    SKILL_ACCESS_TEAM,
    build_skill_access_context,
    can_delete_skill,
    can_execute_skill,
    can_read_skill,
    can_set_public_skill,
    can_update_skill,
    list_allowed_share_targets,
    validate_team_skill_target,
)
from object_storage.minio_client import get_minio_client
from shared.datetime_utils import utcnow
from skill_library.execution_engine import get_execution_engine
from skill_library.gating_engine import GatingEngine
from skill_library.langchain_parser import parse_langchain_tool
from skill_library.package_handler import PackageHandler
from skill_library.canonical_service import SkillRevisionInfo, get_canonical_skill_service
from skill_library.skill_md_parser import SkillMdParser
from skill_library.skill_registry import SkillInfo, get_skill_registry
from skill_library.skill_slug import generate_unique_skill_slug, normalize_skill_slug
from skill_library.skill_types import SkillType, StorageType
from skill_library.templates import get_skill_templates, get_template_by_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["skills"])


# Helper function for MinIO operations
def _get_minio_object_key(storage_path: str, bucket_name: str) -> str:
    """Extract object key from storage_path, handling bucket prefix if present.

    Args:
        storage_path: Storage path from database (may include bucket prefix)
        bucket_name: Expected bucket name

    Returns:
        Clean object key without bucket prefix
    """
    object_key = storage_path

    # If storage_path has a slash and doesn't start with expected prefixes
    if "/" in object_key and not object_key.startswith(("system/", "user/")):
        # Check if it has bucket name prefix
        parts = object_key.split("/", 1)
        if parts[0] == bucket_name:
            object_key = parts[1]

    return object_key


def _is_missing_skill_package_error(error: Exception) -> bool:
    """Return whether an exception indicates a missing package object in storage."""
    if isinstance(error, KeyError):
        return True
    error_code = getattr(error, "code", None)
    return str(error_code or "").strip() == "NoSuchKey" or "NoSuchKey" in str(error)


def _extract_agent_skill_package_archive(package_path, extract_path) -> bool:
    """Extract a ZIP or tar.gz skill package into a directory.

    Returns True when the package was ZIP based, False when tar.gz.
    """
    import tarfile
    import zipfile

    try:
        with zipfile.ZipFile(package_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)
        return True
    except zipfile.BadZipFile:
        with tarfile.open(package_path, "r:gz") as tar_ref:
            tar_ref.extractall(extract_path)
        return False


def _materialize_agent_skill_package(
    skill: Any, extract_path, *, log_context: str
) -> tuple[bool, bool]:
    """Materialize an agent_skill package into a temp directory.

    Returns a tuple of:
    - is_zip: whether the extracted/rebuilt package should be written as ZIP
    - used_fallback: whether DB-backed SKILL.md fallback was used
    """
    from pathlib import Path
    import os
    import tempfile

    minio_client = get_minio_client()
    bucket_name = minio_client.buckets.get("artifacts", "agent-artifacts")
    object_key = (
        _get_minio_object_key(skill.storage_path, bucket_name)
        if getattr(skill, "storage_path", None)
        else None
    )

    if object_key:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".zip",
            dir=_get_tempfile_root_dir(),
        ) as tmp_file:
            temp_package_path = Path(tmp_file.name)

        try:
            logger.info(
                "[%s] Downloading: bucket=%s, key=%s",
                log_context,
                bucket_name,
                object_key,
            )
            file_stream, _metadata = minio_client.download_file(bucket_name, object_key)
            temp_package_path.write_bytes(file_stream.read())
            is_zip = _extract_agent_skill_package_archive(temp_package_path, extract_path)
            return is_zip, False
        except Exception as exc:
            if not _is_missing_skill_package_error(exc):
                raise
            logger.warning(
                "[%s] Skill package missing from object storage, falling back to stored SKILL.md",
                log_context,
                extra={
                    "skill_id": str(getattr(skill, "skill_id", "") or ""),
                    "skill_slug": str(getattr(skill, "skill_slug", "") or ""),
                    "storage_path": str(getattr(skill, "storage_path", "") or ""),
                },
            )
        finally:
            try:
                os.unlink(temp_package_path)
            except OSError:
                pass

    skill_md_content = str(getattr(skill, "skill_md_content", "") or "")
    if not skill_md_content:
        raise HTTPException(
            status_code=500,
            detail="Skill package is unavailable and no stored SKILL.md fallback exists",
        )

    skill_md_path = Path(extract_path) / "SKILL.md"
    skill_md_path.write_text(skill_md_content, encoding="utf-8")
    return True, True


def _build_agent_skill_package_status(*, used_fallback: bool) -> Dict[str, Any]:
    """Build frontend-facing status for the current package materialization result."""
    if not used_fallback:
        return {
            "package_missing": False,
            "fallback_mode": False,
            "limited_files": False,
            "message": None,
        }

    return {
        "package_missing": True,
        "fallback_mode": True,
        "limited_files": True,
        "message": (
            "Skill package is missing from object storage. Showing stored SKILL.md only "
            "until the package is re-uploaded or rebuilt."
        ),
    }


def _get_tempfile_root_dir():
    """Return a guaranteed-existing parent directory for temporary files."""
    import tempfile
    from pathlib import Path

    temp_root = Path(tempfile.gettempdir())
    temp_root.mkdir(parents=True, exist_ok=True)
    return temp_root


def _delete_agent_skill_package_object(
    minio_client: Any,
    storage_path: Optional[str],
) -> None:
    """Delete one agent-skill package object if a storage path is present."""
    if not storage_path:
        return

    bucket_name = minio_client.buckets.get("artifacts", "agent-artifacts")
    object_key = _get_minio_object_key(storage_path, bucket_name)
    minio_client.delete_file(bucket_name, object_key)


def _replace_agent_skill_package_storage(
    *,
    skill_uuid: UUID,
    skill_id: str,
    minio_client: Any,
    current_storage_path: Optional[str],
    new_storage_path: str,
    parsed_skill_md_payload: Optional[Dict[str, Any]] = None,
    delete_previous_package: bool = True,
) -> None:
    """Persist a newly uploaded skill package without risking stale-object breakage."""
    from database.connection import get_db_session
    from database.models import Skill as SkillModel

    try:
        with get_db_session() as session:
            db_skill = session.query(SkillModel).filter(SkillModel.skill_id == skill_uuid).first()

            if not db_skill:
                raise HTTPException(status_code=404, detail="Skill not found")

            db_skill.storage_path = new_storage_path
            if parsed_skill_md_payload:
                db_skill.description = parsed_skill_md_payload["description"]
                db_skill.skill_md_content = parsed_skill_md_payload["skill_md_content"]
                db_skill.homepage = parsed_skill_md_payload["homepage"]
                db_skill.skill_metadata = parsed_skill_md_payload["skill_metadata"]
                db_skill.gating_status = parsed_skill_md_payload["gating_status"]
            session.commit()
    except Exception:
        try:
            _delete_agent_skill_package_object(minio_client, new_storage_path)
        except Exception as cleanup_exc:
            logger.warning(
                "Failed to clean up newly uploaded skill package after persistence error: %s",
                cleanup_exc,
                extra={"skill_id": skill_id, "storage_path": new_storage_path},
            )
        raise

    if (
        delete_previous_package
        and current_storage_path
        and current_storage_path != new_storage_path
    ):
        try:
            _delete_agent_skill_package_object(minio_client, current_storage_path)
        except Exception as exc:
            logger.warning(
                "Failed to delete superseded skill package after update: %s",
                exc,
                extra={"skill_id": skill_id, "storage_path": current_storage_path},
            )


def _extract_tool_call_status(call: Any) -> Optional[str]:
    """Extract status field from a tool-call record."""
    if isinstance(call, dict):
        value = call.get("status")
    else:
        value = getattr(call, "status", None)
    if isinstance(value, str):
        return value
    return None


def _looks_like_agent_skill_failure_output(output_text: str) -> bool:
    """Heuristic detection for agent outputs that clearly indicate execution failure."""
    if not output_text:
        return False
    text = output_text.lower()
    failure_signals = (
        "cannot",
        "can't",
        "unable to",
        "could not",
        "failed to",
        "not found",
        "not available",
        "missing",
        "permission denied",
        "no such file",
        "无法",
        "不能",
        "未能",
        "失败",
        "无法访问",
        "无法定位",
        "无法完成",
        "当前环境无法",
        "请检查",
    )
    return any(signal in text for signal in failure_signals)


def _normalize_agent_skill_test_outcome(result: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize agent execution result into a reliable pass/fail outcome."""
    output_text = str(result.get("output") or "")
    tool_calls = result.get("tool_calls") or []
    successful_tool_calls = 0
    if isinstance(tool_calls, list):
        successful_tool_calls = sum(
            1 for call in tool_calls if _extract_tool_call_status(call) == "success"
        )

    reported_success = bool(result.get("success", False))
    has_error = bool(result.get("error"))
    looks_like_failure = _looks_like_agent_skill_failure_output(output_text)
    semantic_failure = looks_like_failure and successful_tool_calls == 0
    effective_success = reported_success and not has_error and not semantic_failure
    effective_error = result.get("error") or (output_text if semantic_failure else None)

    return {
        "effective_success": effective_success,
        "effective_error": effective_error,
        "output_text": output_text,
        "reported_success": reported_success,
        "semantic_failure": semantic_failure,
        "successful_tool_calls": successful_tool_calls,
    }


def _stringify_preview(value: Any, max_chars: int = 500) -> str:
    """Render value as a compact preview string."""
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        text = json.dumps(value, ensure_ascii=False, default=str)
    else:
        text = str(value)
    return text if len(text) <= max_chars else text[:max_chars] + "..."


def _extract_tool_call_field(call: Any, field_name: str, default: Any = None) -> Any:
    """Extract one field from dict/object tool-call representations."""
    if isinstance(call, dict):
        return call.get(field_name, default)
    return getattr(call, field_name, default)


def _serialize_tool_calls_for_response(tool_calls: Any) -> List[Dict[str, Any]]:
    """Serialize internal tool-call records into JSON-safe response payload."""
    if not isinstance(tool_calls, list):
        return []

    steps: List[Dict[str, Any]] = []
    for index, call in enumerate(tool_calls, start=1):
        tool_name = (
            _extract_tool_call_field(call, "tool_name")
            or _extract_tool_call_field(call, "tool")
            or "unknown"
        )
        status = _extract_tool_call_status(call) or "unknown"
        arguments = _extract_tool_call_field(call, "arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        timestamp = _extract_tool_call_field(call, "timestamp")
        if hasattr(timestamp, "isoformat"):
            timestamp = timestamp.isoformat()
        elif timestamp is not None:
            timestamp = str(timestamp)

        steps.append(
            {
                "step": index,
                "round_number": _extract_tool_call_field(call, "round_number"),
                "retry_number": _extract_tool_call_field(call, "retry_number"),
                "tool_name": str(tool_name),
                "status": status,
                "arguments": arguments,
                "error": _extract_tool_call_field(call, "error"),
                "result_preview": _stringify_preview(_extract_tool_call_field(call, "result")),
                "timestamp": timestamp,
            }
        )
    return steps


def _record_skill_execution_stats(skill_id: UUID, execution_time: float) -> None:
    """Record one skill execution and update rolling average latency."""
    try:
        from datetime import datetime

        from database.connection import get_db_session
        from database.models import Skill as SkillModel

        execution_time = max(float(execution_time), 0.0)

        with get_db_session() as session:
            db_skill = session.query(SkillModel).filter(SkillModel.skill_id == skill_id).first()
            if not db_skill:
                logger.warning(
                    "Skip skill execution stats update because skill was not found",
                    extra={"skill_id": str(skill_id)},
                )
                return

            previous_count = int(db_skill.execution_count or 0)
            new_count = previous_count + 1
            db_skill.execution_count = new_count
            db_skill.last_executed_at = utcnow()

            if db_skill.average_execution_time is None:
                db_skill.average_execution_time = execution_time
            else:
                total_time = (db_skill.average_execution_time * previous_count) + execution_time
                db_skill.average_execution_time = total_time / new_count

            session.commit()
    except Exception as exc:
        logger.warning(
            "Failed to record skill execution stats",
            extra={
                "skill_id": str(skill_id),
                "execution_time": execution_time,
                "error": str(exc),
            },
        )


def _require_readable_skill(skill: Any, current_user: CurrentUser) -> Any:
    """Raise not-found when a skill is missing or outside the user's scope."""
    access_context = build_skill_access_context(current_user)
    if not can_read_skill(skill, access_context):
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


def _require_writable_skill(skill: Any, current_user: CurrentUser) -> Any:
    """Raise not-found when a skill is missing or not writable by the user."""
    access_context = build_skill_access_context(current_user)
    if not can_update_skill(skill, access_context):
        raise HTTPException(status_code=404, detail="Skill not found")
    return skill


def _normalize_access_level(raw_value: Optional[str]) -> str:
    access_level = str(raw_value or SKILL_ACCESS_PRIVATE).strip().lower()
    if access_level not in {SKILL_ACCESS_PRIVATE, SKILL_ACCESS_TEAM, SKILL_ACCESS_PUBLIC}:
        raise HTTPException(status_code=400, detail="Invalid access_level")
    return access_level


def _resolve_department_scope(
    *,
    current_user: CurrentUser,
    access_level: str,
    department_id: Optional[str],
    owner_user_id: str,
) -> Optional[str]:
    access_context = build_skill_access_context(current_user)
    if access_level == SKILL_ACCESS_PUBLIC:
        if not can_set_public_skill(owner_user_id=owner_user_id, context=access_context):
            raise HTTPException(
                status_code=403,
                detail="You do not have permission to publish this skill publicly",
            )
        return None

    if access_level == SKILL_ACCESS_TEAM:
        try:
            return validate_team_skill_target(context=access_context, department_id=department_id)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return None


# Request/Response Models
class InterfaceDefinition(BaseModel):
    """Skill interface definition."""

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    required_inputs: Optional[List[str]] = Field(default_factory=list)


class CreateSkillRequest(BaseModel):
    """Request to create a new skill."""

    display_name: str = Field(..., min_length=1, max_length=100)
    skill_slug: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    skill_type: Optional[str] = Field(default="langchain_tool")
    code: Optional[str] = Field(default=None)
    interface_definition: Optional[InterfaceDefinition] = None
    dependencies: Optional[List[str]] = Field(default_factory=list)
    version: str = Field(default="1.0.0")
    access_level: str = Field(default=SKILL_ACCESS_PRIVATE)
    department_id: Optional[str] = None


class UpdateSkillRequest(BaseModel):
    """Request to update a skill."""

    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, min_length=1, max_length=500)
    code: Optional[str] = Field(None)
    interface_definition: Optional[InterfaceDefinition] = None
    dependencies: Optional[List[str]] = None
    access_level: Optional[str] = None
    department_id: Optional[str] = None
    is_active: Optional[bool] = None


class ShareTargetResponse(BaseModel):
    department_id: str
    name: str


class SkillShareTargetsResponse(BaseModel):
    can_publish_public: bool
    default_department_id: Optional[str] = None
    allowed_department_targets: List[ShareTargetResponse] = Field(default_factory=list)


class SkillResponse(BaseModel):
    """Skill response model."""

    skill_id: str
    skill_slug: str
    display_name: str
    description: str
    version: str
    access_level: str = SKILL_ACCESS_PRIVATE
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    source_kind: Optional[str] = None
    artifact_kind: Optional[str] = None
    runtime_mode: Optional[str] = None
    lifecycle_state: Optional[str] = None
    active_revision_id: Optional[str] = None
    can_edit: bool = False
    can_delete: bool = False
    can_publish_public: bool = False
    skill_type: Optional[str] = "langchain_tool"
    storage_type: Optional[str] = None
    code: Optional[str] = None
    interface_definition: InterfaceDefinition
    dependencies: List[str]
    is_active: Optional[bool] = True
    execution_count: Optional[int] = 0
    average_execution_time: Optional[float] = 0.0
    last_executed_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
    skill_md_content: Optional[str] = None
    homepage: Optional[str] = None
    skill_metadata: Optional[dict] = None
    gating_status: Optional[dict] = None

    @classmethod
    def from_skill_info(
        cls,
        skill_info: SkillInfo,
        *,
        current_user: CurrentUser,
        include_code: bool = False,
    ) -> "SkillResponse":
        """Create response from SkillInfo.

        Args:
            skill_info: Skill information
            include_code: Whether to include code in response
        """
        access_context = build_skill_access_context(current_user)
        # Get additional fields from manifest if available (only for agent_skill)
        skill_md_content = getattr(skill_info, "skill_md_content", None)
        homepage = getattr(skill_info, "homepage", None)
        skill_metadata = getattr(skill_info, "skill_metadata", None)
        gating_status = getattr(skill_info, "gating_status", None)

        # Only process manifest for agent_skill type
        if (
            skill_info.skill_type == "agent_skill"
            and hasattr(skill_info, "manifest")
            and skill_info.manifest
        ):
            # manifest is a dict for agent_skill
            skill_md_content = skill_info.manifest.get("skill_md_content")
            homepage = skill_info.manifest.get("homepage")
            skill_metadata = skill_info.manifest.get("skill_metadata") or skill_info.manifest.get(
                "metadata"
            )
            gating_status = skill_info.manifest.get("gating_status")  # Already a dict from asdict()

        return cls(
            skill_id=str(skill_info.skill_id),
            skill_slug=skill_info.skill_slug,
            display_name=skill_info.display_name,
            description=skill_info.description,
            version=skill_info.version,
            access_level=skill_info.access_level,
            department_id=skill_info.department_id,
            department_name=skill_info.department_name,
            source_kind=getattr(skill_info, "source_kind", None),
            artifact_kind=getattr(skill_info, "artifact_kind", None),
            runtime_mode=getattr(skill_info, "runtime_mode", None),
            lifecycle_state=getattr(skill_info, "lifecycle_state", None),
            active_revision_id=str(getattr(skill_info, "active_revision_id", None) or "")
            or None,
            can_edit=can_update_skill(skill_info, access_context),
            can_delete=can_delete_skill(skill_info, access_context),
            can_publish_public=can_set_public_skill(
                owner_user_id=skill_info.created_by,
                context=access_context,
            ),
            skill_type=skill_info.skill_type,
            storage_type=skill_info.storage_type,
            code=skill_info.code if include_code else None,
            interface_definition=InterfaceDefinition(
                inputs=skill_info.interface_definition.get("inputs", {}),
                outputs=skill_info.interface_definition.get("outputs", {}),
                required_inputs=skill_info.interface_definition.get("required_inputs", []),
            ),
            dependencies=skill_info.dependencies,
            is_active=skill_info.is_active,
            execution_count=skill_info.execution_count,
            average_execution_time=skill_info.average_execution_time,
            last_executed_at=(
                skill_info.last_executed_at.isoformat() if skill_info.last_executed_at else None
            ),
            created_at=skill_info.created_at.isoformat() if skill_info.created_at else None,
            updated_at=skill_info.updated_at.isoformat() if skill_info.updated_at else None,
            created_by=str(skill_info.created_by) if skill_info.created_by else None,
            skill_md_content=skill_md_content,
            homepage=homepage,
            skill_metadata=skill_metadata,
            gating_status=gating_status,
        )


class SkillRevisionResponse(BaseModel):
    revision_id: str = Field(alias="revisionId")
    skill_id: str = Field(alias="skillId")
    version: str
    review_state: str = Field(alias="reviewState")
    instruction_md: Optional[str] = Field(default=None, alias="instructionMd")
    tool_code: Optional[str] = Field(default=None, alias="toolCode")
    interface_definition: Optional[Dict[str, Any]] = Field(default=None, alias="interfaceDefinition")
    artifact_storage_kind: str = Field(alias="artifactStorageKind")
    artifact_ref: Optional[str] = Field(default=None, alias="artifactRef")
    manifest: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    search_document: Optional[str] = Field(default=None, alias="searchDocument")
    checksum: Optional[str] = None
    change_note: Optional[str] = Field(default=None, alias="changeNote")
    created_by: Optional[str] = Field(default=None, alias="createdBy")
    created_at: Optional[str] = Field(default=None, alias="createdAt")

    model_config = {"populate_by_name": True}

    @classmethod
    def from_revision_info(cls, info: SkillRevisionInfo) -> "SkillRevisionResponse":
        return cls(
            revisionId=str(info.revision_id),
            skillId=str(info.skill_id),
            version=info.version,
            reviewState=info.review_state,
            instructionMd=info.instruction_md,
            toolCode=info.tool_code,
            interfaceDefinition=info.interface_definition,
            artifactStorageKind=info.artifact_storage_kind,
            artifactRef=info.artifact_ref,
            manifest=info.manifest,
            config=info.config,
            searchDocument=info.search_document,
            checksum=info.checksum,
            changeNote=info.change_note,
            createdBy=info.created_by,
            createdAt=info.created_at.isoformat() if getattr(info.created_at, "isoformat", None) else None,
        )


class SkillRevisionCreateRequest(BaseModel):
    version: str = "1.0.0"
    instruction_md: Optional[str] = Field(default=None, alias="instructionMd")
    tool_code: Optional[str] = Field(default=None, alias="toolCode")
    interface_definition: Dict[str, Any] = Field(default_factory=dict, alias="interfaceDefinition")
    artifact_storage_kind: str = Field(default="inline", alias="artifactStorageKind")
    artifact_ref: Optional[str] = Field(default=None, alias="artifactRef")
    manifest: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    change_note: Optional[str] = Field(default=None, alias="changeNote")
    review_state: str = Field(default="pending_review", alias="reviewState")

    model_config = {"populate_by_name": True}


class SkillRevisionReviewRequest(BaseModel):
    revision_id: str = Field(alias="revisionId")
    review_state: str = Field(alias="reviewState", pattern=r"^(approved|rejected)$")

    model_config = {"populate_by_name": True}


class SkillRevisionActivationRequest(BaseModel):
    revision_id: str = Field(alias="revisionId")

    model_config = {"populate_by_name": True}


class RegisterDefaultsResponse(BaseModel):
    """Response for registering default skills."""

    registered_count: int
    message: str


class SkillsOverviewStatsResponse(BaseModel):
    """Aggregated statistics for the skills library."""

    total_skills: int
    active_skills: int
    inactive_skills: int
    agent_skills: int
    langchain_tool_skills: int
    skills_with_dependencies: int
    total_execution_count: int
    average_execution_time: float
    last_executed_at: Optional[str] = None


@router.get("/share-targets", response_model=SkillShareTargetsResponse)
async def get_skill_share_targets(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Return visibility/share options available to the current user."""
    access_context = build_skill_access_context(current_user)
    targets = list_allowed_share_targets(access_context)
    return SkillShareTargetsResponse(
        can_publish_public=can_set_public_skill(
            owner_user_id=current_user.user_id,
            context=access_context,
        ),
        default_department_id=access_context.department_id,
        allowed_department_targets=[
            ShareTargetResponse(
                department_id=target.department_id,
                name=target.name,
            )
            for target in targets
        ],
    )


@router.get("", response_model=List[SkillResponse])
async def list_skills(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_code: bool = Query(False, description="Include code in response"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all skills with pagination.

    Args:
        limit: Maximum number of skills to return
        offset: Number of skills to skip
        include_code: Whether to include code in response
        current_user: Authenticated user

    Returns:
        List of skills
    """
    try:
        registry = get_skill_registry()
        access_context = build_skill_access_context(current_user)
        skills = registry.list_visible_skills(
            access_context=access_context,
            limit=limit,
            offset=offset,
        )
        return [
            SkillResponse.from_skill_info(skill, current_user=current_user, include_code=include_code)
            for skill in skills
        ]

    except Exception as e:
        logger.error(f"Failed to list skills: {e}")
        raise HTTPException(status_code=500, detail="Failed to list skills")


@router.get("/search", response_model=List[SkillResponse])
async def search_skills(
    query: str = Query(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Search skills by name or description.

    Args:
        query: Search query
        current_user: Authenticated user

    Returns:
        List of matching skills
    """
    try:
        registry = get_skill_registry()
        access_context = build_skill_access_context(current_user)
        skills = registry.search_visible_skills(
            query=query,
            access_context=access_context,
        )
        return [SkillResponse.from_skill_info(skill, current_user=current_user) for skill in skills]

    except Exception as e:
        logger.error(f"Failed to search skills: {e}")
        raise HTTPException(status_code=500, detail="Failed to search skills")


@router.get("/templates", response_model=List[Dict])
async def get_templates(
    category: Optional[str] = Query(
        None, description="Filter by category (agent_skill or langchain_tool)"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all skill templates.

    Args:
        category: Optional category filter
        current_user: Authenticated user

    Returns:
        List of skill templates
    """
    try:
        templates = get_skill_templates()

        # Filter by category if provided
        if category:
            templates = [t for t in templates if t["category"] == category]

        return templates

    except Exception as e:
        logger.error(f"Failed to get templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get templates")


@router.get("/templates/package-example")
async def download_package_template(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download a reference package template for Agent Skills.

    Returns a ZIP file containing:
    - SKILL.md: Main skill definition with natural language instructions (required)
    - weather_helper.py: Python helper script for API calls
    - utils.py: Utility functions for data processing
    - requirements.txt: Python dependencies
    - README.md: Documentation and usage guide (optional)
    - config.yaml: Configuration template (optional)
    - assets/: Additional resources folder (optional)

    The template follows the AgentSkills.io standard format and includes
    working Python code that can be executed by agents.
    """
    import io

    from fastapi.responses import StreamingResponse

    from skill_library.template_generator import generate_agent_skill_template

    try:
        # Generate template ZIP
        zip_content = generate_agent_skill_template()

        return StreamingResponse(
            io.BytesIO(zip_content),
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=agent-skill-package-template.zip",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    except Exception as e:
        logger.error(f"Failed to generate package template: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate package template")


# Environment Variable Management Endpoints
# NOTE: These must be before /{skill_id} route to avoid path conflicts


@router.get("/env-vars", response_model=List[str])
async def list_env_vars(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List environment variable keys for current user.

    Args:
        current_user: Authenticated user

    Returns:
        List of environment variable keys (not values for security)
    """
    try:
        from skill_library.skill_env_manager import get_skill_env_manager

        env_manager = get_skill_env_manager()
        keys = env_manager.list_env_keys_for_user(current_user.user_id)

        return keys

    except Exception as e:
        logger.error(f"Failed to list env vars: {e}")
        raise HTTPException(status_code=500, detail="Failed to list environment variables")


@router.post("/env-vars", status_code=201)
async def set_env_var(
    key: str = Body(..., embed=True),
    value: str = Body(..., embed=True),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Set an environment variable for current user.

    Args:
        key: Environment variable name
        value: Environment variable value
        current_user: Authenticated user

    Returns:
        Success message
    """
    try:
        from skill_library.skill_env_manager import get_skill_env_manager

        # Validate key format
        if not key.isupper() or not key.replace("_", "").isalnum():
            raise HTTPException(
                status_code=400,
                detail="Environment variable key must be uppercase alphanumeric with underscores",
            )

        env_manager = get_skill_env_manager()
        env_manager.set_env_for_user(current_user.user_id, key, value)

        logger.info(
            f"Environment variable set by user {current_user.user_id}", extra={"env_key": key}
        )

        return {"message": f"Environment variable {key} set successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to set env var: {e}")
        raise HTTPException(status_code=500, detail="Failed to set environment variable")


@router.delete("/env-vars/{key}", status_code=204)
async def delete_env_var(
    key: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete an environment variable for current user.

    Args:
        key: Environment variable name
        current_user: Authenticated user
    """
    try:
        from skill_library.skill_env_manager import get_skill_env_manager

        env_manager = get_skill_env_manager()
        env_manager.delete_env_for_user(current_user.user_id, key)

        logger.info(
            f"Environment variable deleted by user {current_user.user_id}", extra={"env_key": key}
        )

    except Exception as e:
        logger.error(f"Failed to delete env var: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete environment variable")


@router.get("/stats/overview", response_model=SkillsOverviewStatsResponse)
async def get_skills_overview_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get aggregated overview metrics for all skills."""
    try:
        from skill_library.skill_model import get_skill_model

        access_context = build_skill_access_context(current_user)
        stats = get_skill_model().get_overview_stats(access_context=access_context)
        return SkillsOverviewStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get skills overview stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get skills overview stats")


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    include_code: bool = Query(True, description="Include code in response"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get skill by ID.

    Args:
        skill_id: Skill UUID
        include_code: Whether to include code in response
        current_user: Authenticated user

    Returns:
        Skill details
    """
    try:
        skill_uuid = UUID(skill_id)
        registry = get_skill_registry()
        access_context = build_skill_access_context(current_user)
        skill = registry.get_visible_skill(skill_id=skill_uuid, access_context=access_context)
        skill = _require_readable_skill(skill, current_user)
        return SkillResponse.from_skill_info(
            skill,
            current_user=current_user,
            include_code=include_code,
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill: {e}")
        raise HTTPException(status_code=500, detail="Failed to get skill")


@router.get("/{skill_id}/revisions", response_model=List[SkillRevisionResponse])
async def list_skill_revisions(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        skill_uuid = UUID(skill_id)
        access_context = build_skill_access_context(current_user)
        rows = get_canonical_skill_service().list_revisions(
            skill_id=skill_uuid,
            access_context=access_context,
        )
        return [SkillRevisionResponse.from_revision_info(row) for row in rows]
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list skill revisions: {e}")
        raise HTTPException(status_code=500, detail="Failed to list skill revisions")


@router.post("/{skill_id}/revisions", response_model=SkillRevisionResponse)
async def create_skill_revision(
    skill_id: str,
    payload: SkillRevisionCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        skill_uuid = UUID(skill_id)
        existing = _require_writable_skill(get_skill_registry().get_skill(skill_uuid), current_user)
        row = get_canonical_skill_service().create_revision(
            skill_id=skill_uuid,
            owner_user_id=str(current_user.user_id),
            revision_payload=payload.model_dump(by_alias=False),
        )
        return SkillRevisionResponse.from_revision_info(row)
    except ValueError as exc:
        message = str(exc)
        if message == "Skill not found":
            raise HTTPException(status_code=404, detail=message)
        raise HTTPException(status_code=400, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create skill revision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create skill revision")


@router.post("/{skill_id}/review", response_model=SkillRevisionResponse)
async def review_skill_revision(
    skill_id: str,
    payload: SkillRevisionReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        skill_uuid = UUID(skill_id)
        _require_writable_skill(get_skill_registry().get_skill(skill_uuid), current_user)
        row = get_canonical_skill_service().review_revision(
            skill_id=skill_uuid,
            revision_id=UUID(payload.revision_id),
            review_state=payload.review_state,
        )
        return SkillRevisionResponse.from_revision_info(row)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to review skill revision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to review skill revision")


@router.post("/{skill_id}/activate-revision", response_model=SkillResponse)
async def activate_skill_revision(
    skill_id: str,
    payload: SkillRevisionActivationRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        skill_uuid = UUID(skill_id)
        _require_writable_skill(get_skill_registry().get_skill(skill_uuid), current_user)
        get_canonical_skill_service().activate_revision(
            skill_id=skill_uuid,
            revision_id=UUID(payload.revision_id),
            actor_user_id=str(current_user.user_id),
        )
        skill = _require_readable_skill(get_skill_registry().get_skill(skill_uuid), current_user)
        return SkillResponse.from_skill_info(skill, current_user=current_user, include_code=True)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate skill revision: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to activate skill revision")


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    display_name: str = Form(...),
    skill_slug: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    skill_type: str = Form(default="langchain_tool"),
    version: str = Form(default="1.0.0"),
    package_file: Optional[UploadFile] = File(None),
    code: Optional[str] = Form(None),
    dependencies: Optional[str] = Form(None),  # JSON string
    access_level: str = Form(default=SKILL_ACCESS_PRIVATE),
    department_id: Optional[str] = Form(None),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new skill.

    For agent_skill: package_file is required (ZIP/tar.gz with SKILL.md)
    For langchain_tool: code is required

    Args:
        display_name: Skill display name
        skill_slug: Optional custom skill slug
        description: Skill description
        skill_type: Type of skill (langchain_tool or agent_skill)
        version: Skill version
        package_file: Package file for agent_skill (ZIP or tar.gz)
        code: Python code for langchain_tool
        dependencies: JSON string of dependencies list
        access_level: Visibility level
        department_id: Department root for team-scoped skills
        current_user: Authenticated user

    Returns:
        Created skill
    """
    try:
        import json

        # Debug logging
        logger.info(
            f"Creating skill: display_name={display_name}, skill_type={skill_type}, "
            f"has_code={bool(code)}, has_package={bool(package_file)}"
        )

        # Parse dependencies
        deps_list = []
        if dependencies:
            try:
                deps_list = json.loads(dependencies)
            except json.JSONDecodeError:
                raise HTTPException(status_code=400, detail="Invalid dependencies JSON")

        registry = get_skill_registry()
        normalized_access_level = _normalize_access_level(access_level)
        access_context = build_skill_access_context(current_user)
        requested_department_id = department_id or access_context.department_id

        # Handle agent_skill with package
        if skill_type == "agent_skill":
            if not package_file:
                raise HTTPException(status_code=400, detail="Package file required for agent_skill")

            # Read package file
            file_data = await package_file.read()

            # Extract and validate package
            handler = PackageHandler(get_minio_client())
            package_info = None
            temp_dir = None

            try:
                package_info = handler.extract_package(file_data)
                temp_dir = package_info.skill_md_path.parent.parent  # Get temp directory root
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid package: {str(e)}")

            try:
                # Validate package
                validation_errors = handler.validate_package(package_info)
                if validation_errors:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Package validation failed: {', '.join(validation_errors)}",
                    )

                # Parse SKILL.md
                parser = SkillMdParser()
                with open(package_info.skill_md_path, "r", encoding="utf-8") as f:
                    skill_md_content = f.read()

                try:
                    parsed = parser.parse(skill_md_content)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Invalid SKILL.md: {str(e)}")

                # Validate parsed skill
                validation_errors = parser.validate(parsed)
                if validation_errors:
                    raise HTTPException(
                        status_code=400,
                        detail=f"SKILL.md validation failed: {', '.join(validation_errors)}",
                    )

                # Check gating requirements
                gating = GatingEngine()
                gating_result = gating.check_eligibility(parsed.metadata)

                # Upload package to MinIO
                resolved_skill_slug = generate_unique_skill_slug(
                    parsed.metadata.skill_slug or skill_slug or display_name,
                    registry,
                )
                resolved_display_name = (
                    str(parsed.metadata.display_name or "").strip()
                    or str(display_name or "").strip()
                    or resolved_skill_slug
                )
                resolved_department_id = _resolve_department_scope(
                    current_user=current_user,
                    access_level=normalized_access_level,
                    department_id=requested_department_id,
                    owner_user_id=str(current_user.user_id),
                )
                try:
                    storage_path = await handler.upload_package(file_data, resolved_skill_slug, version)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")

                # Create skill with SKILL.md data
                from dataclasses import asdict

                # Extract fields from parsed SKILL.md
                skill_md_content_str = skill_md_content
                homepage_str = parsed.metadata.homepage
                skill_metadata_dict = asdict(parsed.metadata)
                gating_status_dict = asdict(gating_result)
                parsed_description = parsed.metadata.description.strip()
                if (
                    description
                    and description.strip()
                    and description.strip() != parsed_description
                ):
                    logger.info(
                        "Ignoring form description for agent_skill and using SKILL.md description",
                        extra={
                            "display_name": resolved_display_name,
                            "skill_slug": resolved_skill_slug,
                            "form_description": description.strip(),
                            "skill_md_description": parsed_description,
                        },
                    )

                skill = registry.register_skill(
                    skill_slug=resolved_skill_slug,
                    display_name=resolved_display_name,
                    description=parsed_description,
                    interface_definition={
                        "inputs": {},
                        "outputs": {"result": "string"},
                        "required_inputs": [],
                    },
                    dependencies=deps_list,
                    version=version,
                    skill_type="agent_skill",
                    storage_type="minio",
                    storage_path=storage_path,
                    manifest={
                        "skill_md_content": skill_md_content,
                        "homepage": parsed.metadata.homepage,
                        "skill_metadata": skill_metadata_dict,
                        "gating_status": gating_status_dict,
                    },
                    skill_md_content=skill_md_content_str,
                    homepage=homepage_str,
                    skill_metadata=skill_metadata_dict,
                    gating_status=gating_status_dict,
                    access_level=normalized_access_level,
                    department_id=resolved_department_id,
                    is_active=True,
                    created_by=str(current_user.user_id),
                    validate=False,
                )

                logger.info(
                    f"Agent skill created from package by user {current_user.user_id}",
                    extra={
                        "skill_id": str(skill.skill_id),
                        "skill_slug": resolved_skill_slug,
                        "storage_path": storage_path,
                        "gating_eligible": gating_result.eligible,
                    },
                )

                return SkillResponse.from_skill_info(skill, current_user=current_user)

            finally:
                # Clean up temporary directory
                if temp_dir and temp_dir.exists():
                    import shutil

                    shutil.rmtree(temp_dir, ignore_errors=True)
                    logger.debug(f"Cleaned up temp directory: {temp_dir}")

        # Handle langchain_tool with code
        elif skill_type == "langchain_tool":
            if not code:
                raise HTTPException(status_code=400, detail="Code required for langchain_tool")
            if not description or not description.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Description required for langchain_tool",
                )

            # Parse interface from code
            interface_def = parse_langchain_tool(code)
            logger.info(f"Parsed interface from code: {interface_def}")

            # Fall back to default interface if parsing failed
            if not interface_def or not interface_def.get("inputs"):
                interface_def = {
                    "inputs": {},
                    "outputs": {"result": "string"},
                    "required_inputs": [],
                }

            resolved_skill_slug = generate_unique_skill_slug(skill_slug or display_name, registry)
            resolved_department_id = _resolve_department_scope(
                current_user=current_user,
                access_level=normalized_access_level,
                department_id=requested_department_id,
                owner_user_id=str(current_user.user_id),
            )
            skill = registry.register_skill(
                skill_slug=resolved_skill_slug,
                display_name=display_name.strip(),
                description=description.strip(),
                interface_definition=interface_def,
                dependencies=deps_list,
                version=version,
                skill_type="langchain_tool",
                storage_type="inline",
                code=code,
                access_level=normalized_access_level,
                department_id=resolved_department_id,
                is_active=True,
                created_by=str(current_user.user_id),
                validate=False,
            )

            logger.info(
                f"LangChain tool created by user {current_user.user_id}",
                extra={"skill_id": str(skill.skill_id), "skill_slug": resolved_skill_slug},
            )

            return SkillResponse.from_skill_info(skill, current_user=current_user)

        else:
            raise HTTPException(status_code=400, detail=f"Invalid skill_type: {skill_type}")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create skill: {str(e)}")


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    request: UpdateSkillRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a skill.

    Args:
        skill_id: Skill UUID
        request: Skill update request
        current_user: Authenticated user

    Returns:
        Updated skill
    """
    try:
        skill_uuid = UUID(skill_id)
        registry = get_skill_registry()

        # Check if skill exists
        existing = _require_writable_skill(registry.get_skill(skill_uuid), current_user)
        target_access_level = (
            _normalize_access_level(request.access_level)
            if request.access_level is not None
            else existing.access_level
        )
        requested_department_id = (
            request.department_id
            if request.department_id is not None
            else existing.department_id
        )
        resolved_department_id = _resolve_department_scope(
            current_user=current_user,
            access_level=target_access_level,
            department_id=requested_department_id,
            owner_user_id=str(existing.created_by or current_user.user_id),
        )

        logger.info(
            f"Updating skill {skill_id}, request data: display_name={bool(request.display_name)}, "
            f"description={bool(request.description)}, code={bool(request.code)}, "
            f"interface_def={bool(request.interface_definition)}, dependencies={bool(request.dependencies)}, "
            f"access_level={request.access_level}, is_active={request.is_active}"
        )

        # If code is provided, re-parse interface (even if code didn't change, we should re-parse)
        interface_def = None
        if request.code:
            # Parse interface from code
            parsed = parse_langchain_tool(request.code)
            logger.info(f"Parsed interface from code: {parsed}")

            # Only use parsed result if it has inputs
            if parsed and parsed.get("inputs"):
                interface_def = parsed
                logger.info(f"Using parsed interface with {len(parsed.get('inputs', {}))} inputs")
            else:
                logger.warning(f"Failed to parse interface from code or no inputs found")

        # Only use provided interface definition if code parsing failed
        if not interface_def and request.interface_definition:
            interface_def = {
                "inputs": request.interface_definition.inputs,
                "outputs": request.interface_definition.outputs,
                "required_inputs": request.interface_definition.required_inputs or [],
            }
            logger.info(f"Using provided interface_definition")

        logger.info(f"Final interface_def to update: {interface_def}")

        updated = registry.update_skill(
            skill_id=skill_uuid,
            display_name=request.display_name,
            description=request.description,
            code=request.code,
            interface_definition=interface_def,
            dependencies=request.dependencies,
            access_level=target_access_level,
            department_id=resolved_department_id,
            is_active=request.is_active,
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Skill not found")

        # Get updated skill info
        skill = _require_readable_skill(registry.get_skill(skill_uuid), current_user)

        logger.info(
            f"Skill updated by user {current_user.user_id}",
            extra={"skill_id": skill_id},
        )

        return SkillResponse.from_skill_info(skill, current_user=current_user)

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill: {e}")
        raise HTTPException(status_code=500, detail="Failed to update skill")


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a skill.

    Args:
        skill_id: Skill UUID
        current_user: Authenticated user
    """
    try:
        skill_uuid = UUID(skill_id)

        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        _require_writable_skill(skill_model.get_skill_by_id(skill_uuid), current_user)
        deleted = skill_model.delete_skill(skill_uuid)

        if not deleted:
            raise HTTPException(status_code=404, detail="Skill not found")

        logger.info(
            f"Skill deleted by user {current_user.user_id}",
            extra={"skill_id": skill_id},
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete skill: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete skill")


@router.post("/from-template", response_model=SkillResponse, status_code=201)
async def create_from_template(
    template_id: str = Body(..., embed=True),
    display_name: str = Body(..., embed=True),
    skill_slug: Optional[str] = Body(None, embed=True),
    description: Optional[str] = Body(None, embed=True),
    access_level: str = Body(SKILL_ACCESS_PRIVATE, embed=True),
    department_id: Optional[str] = Body(None, embed=True),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create skill from template.

    Args:
        template_id: Template identifier
        display_name: Display name for the skill
        skill_slug: Optional custom slug for the skill
        description: Optional custom description
        access_level: Skill visibility
        department_id: Department target when access_level is team
        current_user: Authenticated user

    Returns:
        Created skill
    """
    try:
        # Get template
        template = get_template_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template {template_id} not found")

        # Create skill from template
        registry = get_skill_registry()
        normalized_access_level = _normalize_access_level(access_level)
        resolved_department_id = _resolve_department_scope(
            current_user=current_user,
            access_level=normalized_access_level,
            department_id=department_id,
            owner_user_id=current_user.user_id,
        )
        resolved_skill_slug = generate_unique_skill_slug(skill_slug or display_name, registry)

        # Extract interface from code (simplified - in production, parse AST)
        interface_def = {"inputs": {}, "outputs": {"result": "string"}, "required_inputs": []}

        skill = registry.register_skill(
            skill_slug=resolved_skill_slug,
            display_name=display_name.strip(),
            description=description or template["description"],
            interface_definition=interface_def,
            dependencies=template.get("dependencies", []),
            version="1.0.0",
            skill_type=template["skill_type"],
            code=template["code"],
            access_level=normalized_access_level,
            department_id=resolved_department_id,
            created_by=str(current_user.user_id),
            validate=False,  # Skip validation for templates
        )

        logger.info(
            f"Skill created from template by user {current_user.user_id}",
            extra={
                "skill_id": str(skill.skill_id),
                "skill_slug": resolved_skill_slug,
                "template_id": template_id,
            },
        )

        return SkillResponse.from_skill_info(skill, current_user=current_user)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create skill from template: {e}")
        raise HTTPException(status_code=500, detail="Failed to create skill from template")


@router.post("/{skill_id}/test")
async def test_skill(
    skill_id: str,
    inputs: Optional[Dict[str, Any]] = Body(None),
    natural_language_input: Optional[str] = Body(None),
    agent_id: Optional[str] = Body(None),
    stream: bool = Query(default=False),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Test skill execution.

    For langchain_tool: Use inputs dict with structured parameters
    For agent_skill: Use natural_language_input with an Agent for real execution

    Args:
        skill_id: Skill UUID
        inputs: Input parameters for langchain_tool (structured)
        natural_language_input: Natural language input for agent_skill
        agent_id: Agent ID to execute the skill (agent_skill only)
        stream: Enable SSE streaming for agent_skill testing
        current_user: Authenticated user

    Returns:
        Execution result
    """
    try:
        skill_uuid = UUID(skill_id)

        # Get skill
        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        skill = _require_readable_skill(skill_model.get_skill_by_id(skill_uuid), current_user)

        # Handle agent_skill with natural language testing
        if skill.skill_type == "agent_skill":
            if not natural_language_input:
                raise HTTPException(
                    status_code=400, detail="natural_language_input required for agent_skill"
                )

            if not agent_id:
                raise HTTPException(
                    status_code=400, detail="agent_id required for agent_skill testing"
                )

            if not skill.skill_md_content:
                raise HTTPException(status_code=400, detail="Skill has no SKILL.md content")

            logger.info(f"Executing agent_skill with Agent: agent_id={agent_id}")

            try:
                import asyncio
                import time

                from agent_framework.agent_executor import (
                    ExecutionContext,
                    get_agent_executor,
                )
                from agent_framework.agent_registry import get_agent_registry
                from agent_framework.base_agent import AgentConfig, BaseAgent
                from agent_framework.runtime_policy import (
                    ExecutionProfile,
                    is_agent_test_chat_unified_runtime_enabled,
                )
                from agent_framework.session_manager import get_session_manager
                from api_gateway.routers.agents import _resolve_model_context_window
                from database.connection import get_db_session
                from llm_providers.custom_openai_provider import CustomOpenAIChat
                from llm_providers.db_manager import ProviderDBManager

                current_user_uuid = UUID(current_user.user_id)
                session_mgr = None
                conversation_session = None
                session_cleanup_managed_by_stream = False

                try:
                    agent_uuid = UUID(agent_id)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid agent ID format")
                registry = get_agent_registry()
                agent_info = registry.get_agent(agent_uuid)
                if not agent_info:
                    raise HTTPException(status_code=404, detail="Agent not found")

                if str(agent_info.owner_user_id) != current_user.user_id:
                    raise HTTPException(
                        status_code=403,
                        detail="You don't have permission to test this agent",
                    )

                # Skill tests must always load the selected skill, even if this agent
                # is not explicitly configured with it yet.
                capabilities = list(agent_info.capabilities or [])
                required_skill_id = str(skill.skill_id)
                if required_skill_id not in capabilities:
                    capabilities.append(required_skill_id)

                config = AgentConfig(
                    agent_id=agent_uuid,
                    name=agent_info.name,
                    agent_type=agent_info.agent_type,
                    owner_user_id=current_user_uuid,
                    capabilities=capabilities,
                    access_level=agent_info.access_level or "private",
                    allowed_knowledge=agent_info.allowed_knowledge or [],
                    llm_model=agent_info.llm_model or "llama3.2:latest",
                    temperature=agent_info.temperature or 0.7,
                    max_iterations=20,
                    system_prompt=agent_info.system_prompt,
                )

                agent = BaseAgent(config)
                provider_name = agent_info.llm_provider or "ollama"
                model_name = agent_info.llm_model or "llama3.2:latest"
                temperature = agent_info.temperature or 0.7

                llm = None
                resolved_context_window_tokens: Optional[int] = None
                with get_db_session() as db:
                    db_manager = ProviderDBManager(db)
                    db_provider = db_manager.get_provider(provider_name)

                    if db_provider and db_provider.enabled:
                        resolved_context_window_tokens = _resolve_model_context_window(
                            provider=db_provider,
                            provider_name=provider_name,
                            model_name=model_name,
                        )
                        if db_provider.protocol == "openai_compatible":
                            api_key = None
                            if db_provider.api_key_encrypted:
                                api_key = db_manager._decrypt_api_key(db_provider.api_key_encrypted)
                            llm = CustomOpenAIChat(
                                base_url=db_provider.base_url,
                                model=model_name,
                                temperature=temperature,
                                api_key=api_key,
                                timeout=db_provider.timeout,
                                max_retries=db_provider.max_retries,
                                max_tokens=agent_info.max_tokens,
                                streaming=False,
                            )
                        elif db_provider.protocol == "ollama":
                            llm = CustomOpenAIChat(
                                base_url=db_provider.base_url,
                                model=model_name,
                                temperature=temperature,
                                max_tokens=agent_info.max_tokens,
                                api_key=None,
                                streaming=False,
                            )

                if llm is None:
                    raise ValueError(f"Could not create LLM for provider: {provider_name}")

                agent.llm = llm
                if resolved_context_window_tokens:
                    agent.config.context_window_tokens = resolved_context_window_tokens

                await agent.initialize()

                # Skill testing requires a real workspace root so read_skill can
                # materialize package files under .skills/<skill_name>/...
                session_mgr = get_session_manager()
                conversation_session, _ = await session_mgr.get_or_create_session(
                    agent_id=agent_uuid,
                    user_id=current_user_uuid,
                    use_sandbox=True,
                )
                if not conversation_session.use_sandbox or not conversation_session.sandbox_id:
                    raise HTTPException(
                        status_code=503,
                        detail=(
                            "Sandbox container is unavailable for skill testing. "
                            "Refusing to run on host to avoid environment pollution."
                        ),
                    )
                synced_skill_files = agent._sync_skill_package_files_to_workdir(
                    conversation_session.workdir,
                    log_prefix="[SKILL_TEST_SYNC]",
                )
                logger.info(
                    "Prepared skill test workspace",
                    extra={
                        "skill_id": skill_id,
                        "agent_id": agent_id,
                        "session_id": conversation_session.session_id,
                        "workdir": str(conversation_session.workdir),
                        "sandbox_id": conversation_session.sandbox_id,
                        "synced_skill_files": synced_skill_files,
                    },
                )
                logger.info(
                    "Skill test will run in sandbox container",
                    extra={
                        "skill_id": skill_id,
                        "agent_id": agent_id,
                        "sandbox_id": conversation_session.sandbox_id,
                        "session_id": conversation_session.session_id,
                    },
                )

                task_description = f"""You are testing the agent skill "{skill.display_name}" ({skill.skill_slug}).

Skill description: {skill.description}
User request: {natural_language_input}

Requirements:
1. First call read_skill for "{skill.skill_slug}" before running any skill files.
2. Execute required tools/code using files under .skills/{skill.skill_slug}/ in the workspace.
3. Return concrete execution results and any errors clearly.
"""
                exec_context = ExecutionContext(
                    agent_id=agent_uuid,
                    user_id=current_user_uuid,
                    user_role=current_user.role,
                    task_description=task_description,
                    additional_context={"execution_context_tag": "skill_test_session"},
                )

                execute_kwargs: Dict[str, Any] = {"conversation_history": None}
                if is_agent_test_chat_unified_runtime_enabled():
                    execute_kwargs["execution_profile"] = ExecutionProfile.DEBUG_CHAT

                executor = get_agent_executor()

                def build_result_payload(
                    execution_result: Dict[str, Any], execution_time: float
                ) -> Dict[str, Any]:
                    normalized_outcome = _normalize_agent_skill_test_outcome(execution_result)
                    serialized_tool_calls = _serialize_tool_calls_for_response(
                        execution_result.get("tool_calls")
                    )
                    trace_summary = {
                        "total_steps": len(serialized_tool_calls),
                        "successful_steps": sum(
                            1 for item in serialized_tool_calls if item.get("status") == "success"
                        ),
                        "failed_steps": sum(
                            1
                            for item in serialized_tool_calls
                            if item.get("status") not in {"success", "timeout"}
                        ),
                        "timeout_steps": sum(
                            1 for item in serialized_tool_calls if item.get("status") == "timeout"
                        ),
                    }

                    if (
                        normalized_outcome["reported_success"]
                        and normalized_outcome["semantic_failure"]
                    ):
                        logger.warning(
                            "Agent reported success but output indicates failure; coercing to failed test",
                            extra={
                                "skill_id": skill_id,
                                "agent_id": agent_id,
                                "successful_tool_calls": normalized_outcome[
                                    "successful_tool_calls"
                                ],
                            },
                        )

                    return {
                        "success": normalized_outcome["effective_success"],
                        "input": natural_language_input,
                        "agent_id": str(agent_id),
                        "agent_name": agent_info.name,
                        "output": normalized_outcome["output_text"],
                        "error": normalized_outcome["effective_error"],
                        "execution_time": execution_time,
                        "mode": "agent_execution",
                        "execution_trace": {
                            "session_id": conversation_session.session_id,
                            "sandbox_id": conversation_session.sandbox_id,
                            "workspace_root": "/workspace",
                            "synced_skill_files": synced_skill_files,
                            "summary": trace_summary,
                            "tool_calls": serialized_tool_calls,
                        },
                    }

                if stream:
                    import queue
                    import threading

                    from fastapi.responses import StreamingResponse

                    session_cleanup_managed_by_stream = True

                    async def generate_stream():
                        start_time = time.time()
                        token_queue: queue.Queue = queue.Queue()
                        result_holder: List[Optional[Dict[str, Any]]] = [None]
                        error_holder: List[Optional[str]] = [None]

                        async def cleanup_stream_session() -> None:
                            if not session_mgr or not conversation_session:
                                return
                            try:
                                ended = await session_mgr.end_session(
                                    conversation_session.session_id,
                                    current_user_uuid,
                                )
                                if not ended:
                                    logger.warning(
                                        "Failed to end streamed skill test session cleanly",
                                        extra={
                                            "session_id": conversation_session.session_id,
                                            "agent_id": agent_id,
                                        },
                                    )
                            except Exception as session_error:
                                logger.warning(
                                    "Failed to cleanup streamed skill test session: %s",
                                    session_error,
                                    extra={
                                        "session_id": conversation_session.session_id,
                                        "agent_id": agent_id,
                                    },
                                )

                        def stream_callback(token_data: Any):
                            token_queue.put(token_data)

                        def execute_agent_with_stream():
                            try:
                                result_holder[0] = executor.execute(
                                    agent,
                                    exec_context,
                                    session_workdir=conversation_session.workdir,
                                    container_id=conversation_session.sandbox_id,
                                    stream_callback=stream_callback,
                                    **execute_kwargs,
                                )
                            except Exception as execute_error:
                                error_holder[0] = str(execute_error)
                            finally:
                                token_queue.put(None)

                        worker_thread = threading.Thread(target=execute_agent_with_stream)
                        worker_thread.start()

                        try:
                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "type": "session",
                                        "session_id": conversation_session.session_id,
                                        "sandbox_id": conversation_session.sandbox_id,
                                        "workspace_root": "/workspace",
                                        "synced_skill_files": synced_skill_files,
                                    }
                                )
                                + "\n\n"
                            )

                            while True:
                                try:
                                    token_data = await asyncio.to_thread(token_queue.get, True, 0.1)
                                except queue.Empty:
                                    if not worker_thread.is_alive():
                                        break
                                    continue

                                if token_data is None:
                                    break

                                if isinstance(token_data, tuple):
                                    token, content_type = token_data
                                else:
                                    token = token_data
                                    content_type = "content"

                                yield (
                                    "data: "
                                    + json.dumps({"type": str(content_type), "content": str(token)})
                                    + "\n\n"
                                )

                            await asyncio.to_thread(worker_thread.join, 5)

                            if error_holder[0]:
                                yield (
                                    "data: "
                                    + json.dumps({"type": "error", "content": error_holder[0]})
                                    + "\n\n"
                                )
                                yield (
                                    "data: "
                                    + json.dumps({"type": "done", "success": False})
                                    + "\n\n"
                                )
                                return

                            if result_holder[0] is None:
                                yield (
                                    "data: "
                                    + json.dumps(
                                        {
                                            "type": "error",
                                            "content": "Stream ended without execution result",
                                        }
                                    )
                                    + "\n\n"
                                )
                                yield (
                                    "data: "
                                    + json.dumps({"type": "done", "success": False})
                                    + "\n\n"
                                )
                                return

                            result_payload = build_result_payload(
                                result_holder[0],
                                time.time() - start_time,
                            )
                            _record_skill_execution_stats(
                                skill_uuid, result_payload["execution_time"]
                            )
                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "type": "final_result",
                                        "result": result_payload,
                                    }
                                )
                                + "\n\n"
                            )
                            yield (
                                "data: "
                                + json.dumps(
                                    {"type": "done", "success": bool(result_payload.get("success"))}
                                )
                                + "\n\n"
                            )
                        finally:
                            await cleanup_stream_session()

                    return StreamingResponse(
                        generate_stream(),
                        media_type="text/event-stream",
                        headers={
                            "Cache-Control": "no-cache",
                            "Connection": "keep-alive",
                            "X-Accel-Buffering": "no",
                        },
                    )

                start_time = time.time()
                result = await asyncio.to_thread(
                    executor.execute,
                    agent,
                    exec_context,
                    session_workdir=conversation_session.workdir,
                    container_id=conversation_session.sandbox_id,
                    **execute_kwargs,
                )
                execution_time = time.time() - start_time
                _record_skill_execution_stats(skill_uuid, execution_time)

                logger.info(
                    f"Agent skill executed by Agent {agent_id}",
                    extra={
                        "skill_id": skill_id,
                        "agent_id": agent_id,
                        "execution_time": execution_time,
                    },
                )

                return build_result_payload(result, execution_time)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Agent execution failed: {e}", exc_info=True)
                return {
                    "success": False,
                    "input": natural_language_input,
                    "agent_id": str(agent_id),
                    "error": str(e),
                    "execution_time": 0.0,
                    "mode": "agent_execution",
                }
            finally:
                if session_mgr and conversation_session and not session_cleanup_managed_by_stream:
                    try:
                        ended = await session_mgr.end_session(
                            conversation_session.session_id,
                            current_user_uuid,
                        )
                        if not ended:
                            logger.warning(
                                "Failed to end skill test session cleanly",
                                extra={
                                    "session_id": conversation_session.session_id,
                                    "agent_id": agent_id,
                                },
                            )
                    except Exception as session_error:
                        logger.warning(
                            "Failed to cleanup skill test session: %s",
                            session_error,
                            extra={
                                "session_id": conversation_session.session_id,
                                "agent_id": agent_id,
                            },
                        )

        # Handle langchain_tool / mcp_tool with structured testing
        elif skill.skill_type in ("langchain_tool", "mcp_tool"):
            if inputs is None:
                raise HTTPException(status_code=400, detail="inputs required for tool testing")

            # Execute skill
            engine = get_execution_engine()
            result = await engine.execute_skill(
                skill, inputs, user_id=UUID(str(current_user.user_id))
            )

            logger.info(
                f"Skill tested by user {current_user.user_id}",
                extra={
                    "skill_id": skill_id,
                    "skill_type": skill.skill_type,
                    "success": result.success,
                    "execution_time": result.execution_time,
                },
            )

            return result.to_dict()

        else:
            raise HTTPException(status_code=400, detail=f"Unknown skill_type: {skill.skill_type}")

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to test skill: {str(e)}")


@router.post("/{skill_id}/activate", status_code=204)
async def activate_skill(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Activate a skill.

    Args:
        skill_id: Skill UUID
        current_user: Authenticated user
    """
    try:
        skill_uuid = UUID(skill_id)

        from database.connection import get_db_session
        from database.models import Skill as SkillModel

        # Update skill status in database
        with get_db_session() as session:
            db_skill = session.query(SkillModel).filter(SkillModel.skill_id == skill_uuid).first()

            _require_writable_skill(db_skill, current_user)

            db_skill.is_active = True
            db_skill.lifecycle_state = "active"
            session.commit()

        logger.info(f"Skill activated by user {current_user.user_id}", extra={"skill_id": skill_id})

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to activate skill: {str(e)}")


@router.post("/{skill_id}/deactivate", status_code=204)
async def deactivate_skill(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Deactivate a skill.

    Args:
        skill_id: Skill UUID
        current_user: Authenticated user
    """
    try:
        skill_uuid = UUID(skill_id)

        from database.connection import get_db_session
        from database.models import Skill as SkillModel

        # Update skill status in database
        with get_db_session() as session:
            db_skill = session.query(SkillModel).filter(SkillModel.skill_id == skill_uuid).first()

            _require_writable_skill(db_skill, current_user)

            db_skill.is_active = False
            db_skill.lifecycle_state = "deprecated"
            session.commit()

        # Clear from execution engine cache
        try:
            engine = get_execution_engine()
            engine.clear_cache(skill_uuid)
        except Exception as e:
            logger.warning(f"Failed to clear execution engine cache: {e}")

        logger.info(
            f"Skill deactivated by user {current_user.user_id}", extra={"skill_id": skill_id}
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to deactivate skill: {str(e)}")


@router.get("/{skill_id}/stats")
async def get_skill_stats(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get skill execution statistics.

    Args:
        skill_id: Skill UUID
        current_user: Authenticated user

    Returns:
        Skill statistics
    """
    try:
        skill_uuid = UUID(skill_id)

        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        skill = _require_readable_skill(skill_model.get_skill_by_id(skill_uuid), current_user)

        return {
            "skill_id": str(skill.skill_id),
            "skill_slug": skill.skill_slug,
            "display_name": skill.display_name,
            "execution_count": skill.execution_count,
            "last_executed_at": (
                skill.last_executed_at.isoformat() if skill.last_executed_at else None
            ),
            "average_execution_time": skill.average_execution_time,
            "is_active": skill.is_active,
            "created_at": skill.created_at.isoformat() if skill.created_at else None,
            "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get skill stats")


@router.post("/validate")
async def validate_skill_code(
    code: str = Body(..., embed=True),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Validate skill code for safety and syntax.

    Args:
        code: Python code to validate
        current_user: Authenticated user

    Returns:
        Validation result
    """
    try:
        engine = get_execution_engine()

        # Try to validate the code
        try:
            engine._validate_code_safety(code)

            # Also check if it can be parsed
            import ast

            ast.parse(code)

            # Check if it has a @tool decorated function
            namespace = {"tool": lambda f: f}
            exec(code, namespace)

            has_tool = False
            for name, obj in namespace.items():
                if callable(obj) and name not in ["tool"]:
                    has_tool = True
                    break

            return {
                "valid": True,
                "has_tool_decorator": has_tool,
                "message": "Code validation passed",
                "warnings": [],
            }

        except SyntaxError as e:
            return {
                "valid": False,
                "has_tool_decorator": False,
                "message": f"Syntax error: {str(e)}",
                "warnings": [],
            }
        except ValueError as e:
            return {"valid": False, "has_tool_decorator": False, "message": str(e), "warnings": []}

    except Exception as e:
        logger.error(f"Failed to validate code: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate code")


@router.get("/cache/stats")
async def get_cache_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get skill execution cache statistics.

    Requires admin role.

    Args:
        current_user: Authenticated user

    Returns:
        Cache statistics
    """
    # Only admins can view cache stats
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        engine = get_execution_engine()
        stats = engine.get_cache_stats()

        return stats

    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get cache stats")


@router.post("/cache/clear")
async def clear_cache(
    skill_id: Optional[str] = Body(None, embed=True),
    user_id: Optional[str] = Body(None, embed=True),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Clear skill execution cache.

    Requires admin role.

    Args:
        skill_id: Optional skill ID to clear (clears all if not provided)
        user_id: Optional user ID to clear (clears all if not provided)
        current_user: Authenticated user

    Returns:
        Success message
    """
    # Only admins can clear cache
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        engine = get_execution_engine()

        skill_uuid = UUID(skill_id) if skill_id else None
        user_uuid = UUID(user_id) if user_id else None

        engine.clear_cache(skill_id=skill_uuid, user_id=user_uuid)

        if skill_uuid and user_uuid:
            message = f"Cleared cache for skill {skill_id} and user {user_id}"
        elif skill_uuid:
            message = f"Cleared cache for skill {skill_id}"
        elif user_uuid:
            message = f"Cleared cache for user {user_id}"
        else:
            message = "Cleared all cache"

        logger.info(
            f"Cache cleared by admin {current_user.user_id}",
            extra={"skill_id": skill_id, "user_id": user_id},
        )

        return {"message": message}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid UUID: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear cache")


@router.get("/{skill_id}/files", response_model=Dict[str, Any])
async def get_skill_files(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get file list for agent_skill package.

    Returns the file structure of an agent_skill package stored in MinIO.
    Only works for agent_skill type.

    Args:
        skill_id: Skill UUID
        current_user: Authenticated user

    Returns:
        File tree structure with metadata
    """
    try:
        skill_uuid = UUID(skill_id)

        # Get skill
        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        skill = _require_readable_skill(skill_model.get_skill_by_id(skill_uuid), current_user)

        # Only agent_skill has file structure
        if skill.skill_type != "agent_skill":
            raise HTTPException(
                status_code=400, detail="Only agent_skill type supports file browsing"
            )

        # Download and extract package from MinIO, or fall back to stored SKILL.md
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(dir=_get_tempfile_root_dir()) as extract_dir:
            extract_path = Path(extract_dir)
            _is_zip, used_fallback = _materialize_agent_skill_package(
                skill,
                extract_path,
                log_context="get_skill_files",
            )
            package_status = _build_agent_skill_package_status(used_fallback=used_fallback)

            # Build file tree
            def build_tree(path: Path, base_path: Path) -> dict:
                """Recursively build file tree."""
                items = []

                for item in sorted(path.iterdir()):
                    rel_path = str(item.relative_to(base_path))

                    if item.is_file():
                        size = item.stat().st_size

                        suffix = item.suffix.lower()
                        if suffix in [".py"]:
                            file_type = "python"
                        elif suffix in [".md", ".txt"]:
                            file_type = "text"
                        elif suffix in [".yaml", ".yml", ".json"]:
                            file_type = "config"
                        elif suffix in [".sh"]:
                            file_type = "script"
                        else:
                            file_type = "other"

                        items.append(
                            {
                                "name": item.name,
                                "path": rel_path,
                                "type": "file",
                                "file_type": file_type,
                                "size": size,
                            }
                        )
                    elif item.is_dir():
                        if item.name.startswith(".") or item.name == "__pycache__":
                            continue

                        items.append(
                            {
                                "name": item.name,
                                "path": rel_path,
                                "type": "directory",
                                "children": build_tree(item, base_path),
                            }
                        )

                return items

            file_tree = build_tree(extract_path, extract_path)

            logger.info(
                f"File list retrieved for skill {skill_id}",
                extra={"skill_id": skill_id, "file_count": len(file_tree)},
            )

            return {
                "skill_id": skill_id,
                "skill_slug": skill.skill_slug,
                "display_name": skill.display_name,
                "skill_type": skill.skill_type,
                "files": file_tree,
                "package_status": package_status,
            }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get skill files: {str(e)}")


@router.get("/{skill_id}/files/{file_path:path}")
async def get_skill_file_content(
    skill_id: str,
    file_path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get content of a specific file in agent_skill package.

    Args:
        skill_id: Skill UUID
        file_path: Relative path to file within package
        current_user: Authenticated user

    Returns:
        File content as text
    """
    try:
        skill_uuid = UUID(skill_id)

        # Get skill
        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        skill = _require_readable_skill(skill_model.get_skill_by_id(skill_uuid), current_user)

        # Only agent_skill has file structure
        if skill.skill_type != "agent_skill":
            raise HTTPException(
                status_code=400, detail="Only agent_skill type supports file browsing"
            )

        # Security: Prevent path traversal
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")

        # Download and extract package from MinIO, or fall back to stored SKILL.md
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory(dir=_get_tempfile_root_dir()) as extract_dir:
            extract_path = Path(extract_dir)
            _is_zip, used_fallback = _materialize_agent_skill_package(
                skill,
                extract_path,
                log_context="get_skill_file_content",
            )
            package_status = _build_agent_skill_package_status(used_fallback=used_fallback)

            file_full_path = extract_path / file_path

            if not file_full_path.exists():
                raise HTTPException(status_code=404, detail="File not found in package")

            if not file_full_path.is_file():
                raise HTTPException(status_code=400, detail="Path is not a file")

            try:
                content = file_full_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400, detail="File is binary and cannot be displayed as text"
                )

            size = file_full_path.stat().st_size
            suffix = file_full_path.suffix.lower()

            logger.info(
                f"File content retrieved for skill {skill_id}",
                extra={"skill_id": skill_id, "file_path": file_path},
            )

            return {
                "skill_id": skill_id,
                "file_path": file_path,
                "file_name": file_full_path.name,
                "content": content,
                "size": size,
                "extension": suffix,
                "package_status": package_status,
            }

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file content: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get file content: {str(e)}")


@router.put("/{skill_id}/files/{file_path:path}")
async def update_skill_file_content(
    skill_id: str,
    file_path: str,
    content: str = Body(..., embed=True),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update content of a specific file in agent_skill package.

    Downloads the package, updates the file, re-packages, and uploads back to MinIO.

    Args:
        skill_id: Skill UUID
        file_path: Relative path to file within package
        content: New file content
        current_user: Authenticated user

    Returns:
        Success message
    """
    try:
        skill_uuid = UUID(skill_id)

        # Get skill
        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        skill = _require_writable_skill(skill_model.get_skill_by_id(skill_uuid), current_user)

        # Only agent_skill has file structure
        if skill.skill_type != "agent_skill":
            raise HTTPException(
                status_code=400, detail="Only agent_skill type supports file editing"
            )

        # Security: Prevent path traversal
        if ".." in file_path or file_path.startswith("/"):
            raise HTTPException(status_code=400, detail="Invalid file path")

        # Download, modify, and re-upload package
        import tarfile
        import tempfile
        import zipfile
        from pathlib import Path

        minio_client = get_minio_client()
        previous_storage_path = str(getattr(skill, "storage_path", "") or "") or None

        with tempfile.TemporaryDirectory(dir=_get_tempfile_root_dir()) as extract_dir:
            extract_path = Path(extract_dir)
            is_zip, used_fallback = _materialize_agent_skill_package(
                skill,
                extract_path,
                log_context="update_skill_file_content",
            )

            # Update file content
            file_full_path = extract_path / file_path

            if not file_full_path.exists():
                raise HTTPException(status_code=404, detail="File not found in package")

            if not file_full_path.is_file():
                raise HTTPException(status_code=400, detail="Path is not a file")

            # Write new content
            file_full_path.write_text(content, encoding="utf-8")

            parsed_skill_md_payload: Optional[Dict[str, Any]] = None
            if Path(file_path).name.lower() == "skill.md":
                parser = SkillMdParser()
                try:
                    parsed = parser.parse(content)
                except ValueError as e:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid SKILL.md: {str(e)}",
                    )

                validation_errors = parser.validate(parsed)
                if validation_errors:
                    raise HTTPException(
                        status_code=400,
                        detail=("SKILL.md validation failed: " f"{', '.join(validation_errors)}"),
                    )

                from dataclasses import asdict

                gating = GatingEngine()
                gating_result = gating.check_eligibility(parsed.metadata)
                parsed_skill_md_payload = {
                    "description": parsed.metadata.description.strip(),
                    "skill_md_content": content,
                    "homepage": parsed.metadata.homepage,
                    "skill_metadata": asdict(parsed.metadata),
                    "gating_status": asdict(gating_result),
                }

            # Re-package
            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=".zip",
                dir=_get_tempfile_root_dir(),
            ) as tmp_upload:
                if is_zip:
                    with zipfile.ZipFile(tmp_upload.name, "w", zipfile.ZIP_DEFLATED) as zip_ref:
                        for item in extract_path.rglob("*"):
                            if item.is_file():
                                arcname = item.relative_to(extract_path)
                                zip_ref.write(item, arcname)
                else:
                    with tarfile.open(tmp_upload.name, "w:gz") as tar_ref:
                        tar_ref.add(extract_path, arcname=".")

                tmp_upload.seek(0)
                package_data = tmp_upload.read()

                from skill_library.package_handler import PackageHandler

                handler = PackageHandler(minio_client)
                new_storage_path = await handler.upload_package(
                    package_data, skill.skill_slug, skill.version
                )
                _replace_agent_skill_package_storage(
                    skill_uuid=skill_uuid,
                    skill_id=skill_id,
                    minio_client=minio_client,
                    current_storage_path=previous_storage_path,
                    new_storage_path=new_storage_path,
                    parsed_skill_md_payload=parsed_skill_md_payload,
                    delete_previous_package=bool(previous_storage_path) and not used_fallback,
                )

                logger.info(
                    f"File updated in skill package by user {current_user.user_id}",
                    extra={
                        "skill_id": skill_id,
                        "file_path": file_path,
                        "new_storage_path": new_storage_path,
                    },
                )

                try:
                    import os

                    os.unlink(tmp_upload.name)
                except Exception:
                    pass

                return {"message": "File updated successfully"}

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update file content: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update file content: {str(e)}")


@router.put("/{skill_id}/package")
async def update_skill_package(
    skill_id: str,
    package_file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Re-upload package for agent_skill.

    Replaces the entire package with a new one.

    Args:
        skill_id: Skill UUID
        package_file: New package file (ZIP or tar.gz)
        current_user: Authenticated user

    Returns:
        Success message
    """
    try:
        skill_uuid = UUID(skill_id)

        # Get skill
        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        skill = _require_writable_skill(skill_model.get_skill_by_id(skill_uuid), current_user)

        # Only agent_skill supports package upload
        if skill.skill_type != "agent_skill":
            raise HTTPException(
                status_code=400, detail="Only agent_skill type supports package upload"
            )

        # Read new package file
        file_data = await package_file.read()

        # Validate and extract package
        from skill_library.gating_engine import GatingEngine
        from skill_library.package_handler import PackageHandler
        from skill_library.skill_md_parser import SkillMdParser

        handler = PackageHandler(get_minio_client())
        package_info = None
        temp_dir = None

        try:
            package_info = handler.extract_package(file_data)
            temp_dir = package_info.skill_md_path.parent.parent
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid package: {str(e)}")

        try:
            # Validate package
            validation_errors = handler.validate_package(package_info)
            if validation_errors:
                raise HTTPException(
                    status_code=400,
                    detail=f"Package validation failed: {', '.join(validation_errors)}",
                )

            # Parse SKILL.md
            parser = SkillMdParser()
            with open(package_info.skill_md_path, "r", encoding="utf-8") as f:
                skill_md_content = f.read()

            try:
                parsed = parser.parse(skill_md_content)
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Invalid SKILL.md: {str(e)}")

            # Validate parsed skill
            validation_errors = parser.validate(parsed)
            if validation_errors:
                raise HTTPException(
                    status_code=400,
                    detail=f"SKILL.md validation failed: {', '.join(validation_errors)}",
                )

            # Check gating requirements
            gating = GatingEngine()
            gating_result = gating.check_eligibility(parsed.metadata)

            minio_client = get_minio_client()
            previous_storage_path = str(getattr(skill, "storage_path", "") or "") or None

            # Upload new package to MinIO
            try:
                new_storage_path = await handler.upload_package(
                    file_data, skill.skill_slug, skill.version
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=f"Upload failed: {str(e)}")

            # Update skill in database directly
            from dataclasses import asdict

            skill_metadata_dict = asdict(parsed.metadata)
            gating_status_dict = asdict(gating_result)
            _replace_agent_skill_package_storage(
                skill_uuid=skill_uuid,
                skill_id=skill_id,
                minio_client=minio_client,
                current_storage_path=previous_storage_path,
                new_storage_path=new_storage_path,
                parsed_skill_md_payload={
                    "description": parsed.metadata.description.strip(),
                    "skill_md_content": skill_md_content,
                    "homepage": parsed.metadata.homepage,
                    "skill_metadata": skill_metadata_dict,
                    "gating_status": gating_status_dict,
                },
            )

            logger.info(
                f"Package updated for skill by user {current_user.user_id}",
                extra={
                    "skill_id": skill_id,
                    "storage_path": new_storage_path,
                    "gating_eligible": gating_result.eligible,
                },
            )

            return {"message": "Package updated successfully"}

        finally:
            # Clean up temporary directory
            if temp_dir and temp_dir.exists():
                import shutil

                shutil.rmtree(temp_dir, ignore_errors=True)

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update package: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update package: {str(e)}")
