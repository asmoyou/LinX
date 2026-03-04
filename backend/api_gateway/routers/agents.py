"""Agent Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.7: Create agent endpoints
"""

import base64
import asyncio
import hashlib
import io
import json
import mimetypes
import re
import tempfile
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import psutil  # For system memory monitoring
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from agent_framework.access_policy import normalize_allowed_memory_scopes, resolve_memory_scopes
from agent_framework.agent_registry import get_agent_registry
from object_storage.minio_client import get_minio_client
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()
AGENT_TEST_RUNTIME_CONTEXT_TAG = "agent_test_session"
AGENT_TEST_MAX_ITERATIONS = 20


def _resolve_agent_avatar(avatar_ref: Optional[str]) -> Optional[str]:
    """
    Resolve agent avatar reference to a presigned URL.

    Args:
        avatar_ref: Avatar reference (minio:bucket:key format) or legacy URL

    Returns:
        Presigned URL or original URL, or None if reference is empty
    """
    if not avatar_ref:
        return None

    # Check for minio reference format
    if avatar_ref.startswith("minio:"):
        try:
            minio_client = get_minio_client()
            return minio_client.resolve_avatar_url(avatar_ref)
        except Exception as e:
            logger.warning(f"Failed to resolve agent avatar URL: {e}")
            return None

    # Legacy: detect expired presigned MinIO URLs (localhost:9000/bucket/key?X-Amz-...)
    # and auto-convert them to minio: references for fresh presigned URLs
    if "X-Amz-" in avatar_ref and "localhost:9000/" in avatar_ref:
        try:
            from urllib.parse import urlparse

            parsed = urlparse(avatar_ref)
            # path is like /images/agent-id/filename.webp
            path_parts = parsed.path.lstrip("/").split("/", 1)
            if len(path_parts) == 2:
                bucket_name, object_key = path_parts
                minio_ref = f"minio:{bucket_name}:{object_key}"
                minio_client = get_minio_client()
                url = minio_client.resolve_avatar_url(minio_ref)
                if url:
                    # Auto-fix the DB record in background
                    _auto_fix_avatar_ref(avatar_ref, minio_ref)
                    return url
        except Exception as e:
            logger.warning(f"Failed to convert legacy avatar URL: {e}")

    # Legacy: already a URL, return as-is
    return avatar_ref


def _auto_fix_avatar_ref(old_ref: str, new_ref: str):
    """Auto-fix legacy avatar references in the database."""
    try:
        from database.connection import get_db_session
        from database.models import Agent

        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.avatar == old_ref).first()
            if agent:
                agent.avatar = new_ref
                session.commit()
                logger.info(f"Auto-fixed avatar for agent {agent.agent_id}: minio ref")
    except Exception as e:
        logger.warning(f"Failed to auto-fix avatar reference: {e}")


def _validate_allowed_knowledge(
    allowed_knowledge: List[str],
    current_user: CurrentUser,
) -> List[str]:
    """Validate agent allowed knowledge whitelist against accessible collections."""
    if not allowed_knowledge:
        return []

    normalized_ids: List[str] = []
    for raw_id in allowed_knowledge:
        if raw_id and raw_id.strip() and raw_id not in normalized_ids:
            normalized_ids.append(raw_id.strip())

    parsed_ids: List[UUID] = []
    invalid_ids: List[str] = []
    for collection_id in normalized_ids:
        try:
            parsed_ids.append(UUID(collection_id))
        except ValueError:
            invalid_ids.append(collection_id)

    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid knowledge base IDs: {', '.join(invalid_ids)}",
        )

    from access_control.knowledge_filter import can_access_knowledge_item
    from access_control.rbac import Action
    from database.connection import get_db_session
    from database.models import KnowledgeCollection, User

    current_user_uuid = UUID(current_user.user_id)

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user_uuid).first()
        user_attributes = dict(user.attributes or {}) if user else {}
        if user and user.department_id:
            user_attributes["department_id"] = str(user.department_id)

        collections = (
            session.query(KnowledgeCollection)
            .filter(KnowledgeCollection.collection_id.in_(parsed_ids))
            .all()
        )

    collection_map = {str(collection.collection_id): collection for collection in collections}
    missing_ids = [
        collection_id for collection_id in normalized_ids if collection_id not in collection_map
    ]
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Knowledge bases not found: {', '.join(missing_ids)}",
        )

    inaccessible_ids: List[str] = []
    for collection_id in normalized_ids:
        collection = collection_map[collection_id]
        resource_attributes = {}
        if collection.department_id:
            resource_attributes["department_id"] = str(collection.department_id)

        can_access = can_access_knowledge_item(
            current_user=current_user,
            action=Action.READ,
            owner_user_id=str(collection.owner_user_id),
            access_level=collection.access_level,
            user_attributes=user_attributes or None,
            resource_attributes=resource_attributes or None,
        )
        if not can_access:
            inaccessible_ids.append(collection_id)

    if inaccessible_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Knowledge bases are not accessible: {', '.join(inaccessible_ids)}",
        )

    return normalized_ids


def _validate_allowed_memory(allowed_memory: Optional[List[str]]) -> Optional[List[str]]:
    """Validate and normalize allowed memory scopes."""
    if allowed_memory is None:
        return None

    normalized_scopes, invalid_scopes = normalize_allowed_memory_scopes(allowed_memory)
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory scopes: {', '.join(invalid_scopes)}",
        )
    return normalized_scopes


def _trim_process_text(text: Optional[str], max_chars: int = 120) -> str:
    """Trim long text for process/debug stream display."""
    if not text:
        return ""
    normalized = " ".join(str(text).split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


def _sanitize_transcription_text(text: Optional[str]) -> str:
    """Remove control tokens and normalize whitespace in ASR output."""
    raw = str(text or "")
    # Strip FunASR/SenseVoice control tags like <|zh|><|HAPPY|><|Speech|>.
    cleaned = re.sub(r"<\|[^|>]+?\|>", " ", raw)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _short_id(value: Optional[str], keep: int = 8) -> str:
    """Shorten long ids for process logs."""
    if not value:
        return "-"
    text = str(value)
    if len(text) <= keep:
        return text
    return text[:keep]


def _to_positive_int(value: Any) -> Optional[int]:
    """Best-effort parse for positive integer values."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


_NON_TERMINAL_TASK_STATUSES = {"pending", "in_progress"}


def _mission_bound_tasks_only(task_model: Any):
    """Restrict task stats/logs to mission-generated tasks only."""
    return task_model.mission_id.isnot(None)


def _default_agent_task_stats() -> Dict[str, Any]:
    """Default task metrics for agents with no execution records."""
    return {
        "tasksExecuted": 0,
        "tasksCompleted": 0,
        "tasksFailed": 0,
        "completionRate": 0.0,
    }


def _collect_agent_task_stats(agent_ids: List[UUID]) -> Dict[UUID, Dict[str, Any]]:
    """Aggregate task execution stats for a list of agents."""
    if not agent_ids:
        return {}

    unique_agent_ids = list(dict.fromkeys(agent_ids))
    stats_by_agent: Dict[UUID, Dict[str, Any]] = {
        agent_id: _default_agent_task_stats() for agent_id in unique_agent_ids
    }

    try:
        from database.connection import get_db_session
        from database.models import Task
        from sqlalchemy import func

        with get_db_session() as session:
            rows = (
                session.query(Task.assigned_agent_id, Task.status, func.count(Task.task_id))
                .filter(Task.assigned_agent_id.in_(unique_agent_ids))
                .filter(_mission_bound_tasks_only(Task))
                .group_by(Task.assigned_agent_id, Task.status)
                .all()
            )

        for assigned_agent_id, task_status, count in rows:
            if assigned_agent_id not in stats_by_agent:
                continue

            normalized_status = str(task_status or "").strip().lower()
            if normalized_status in _NON_TERMINAL_TASK_STATUSES:
                continue

            if normalized_status == "completed":
                stats_by_agent[assigned_agent_id]["tasksCompleted"] += int(count)
            else:
                stats_by_agent[assigned_agent_id]["tasksFailed"] += int(count)

        for stats in stats_by_agent.values():
            tasks_executed = stats["tasksCompleted"] + stats["tasksFailed"]
            stats["tasksExecuted"] = tasks_executed
            stats["completionRate"] = (
                round(stats["tasksCompleted"] / tasks_executed, 4) if tasks_executed > 0 else 0.0
            )

    except Exception as e:
        logger.error(f"Failed to collect agent task stats: {e}")

    return stats_by_agent


def _normalize_event_timestamp(value: Any) -> datetime:
    """Normalize timestamps for log/event payloads."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return datetime.now(timezone.utc)


def _normalize_task_status(task_status: Any) -> str:
    """Normalize task status aliases to canonical API values."""
    normalized_status = str(task_status or "").strip().lower()
    if normalized_status in {"in progress", "in-progress"}:
        return "in_progress"
    return normalized_status


def _format_agent_task_log_message(status: str, goal_text: Any) -> str:
    """Build task-oriented activity message for agent logs."""
    status_label = {
        "completed": "Task completed",
        "failed": "Task failed",
        "in_progress": "Task in progress",
        "pending": "Task pending",
    }.get(status, "Task updated")

    task_goal = _trim_process_text(str(goal_text or "").strip(), max_chars=140)
    if task_goal:
        return f"{status_label}: {task_goal}"
    return status_label


def _build_task_log_entries(task_rows: List[Tuple[Any, Any, Any, Any]]) -> List[Dict[str, Any]]:
    """Build detail-page log entries from task rows."""
    entries: List[Dict[str, Any]] = []
    for goal_text, task_status, created_at, completed_at in task_rows:
        normalized_status = _normalize_task_status(task_status)
        event_time = completed_at or created_at
        entries.append(
            {
                "timestamp": _normalize_event_timestamp(event_time),
                "level": (
                    "SUCCESS"
                    if normalized_status == "completed"
                    else "ERROR"
                    if normalized_status == "failed"
                    else "INFO"
                ),
                "message": _format_agent_task_log_message(normalized_status, goal_text),
                "source": "task",
            }
        )
    return entries


def _build_audit_log_entries(audit_rows: List[Tuple[Any, Any, Any]]) -> List[Dict[str, Any]]:
    """Build detail-page log entries from audit rows."""
    entries: List[Dict[str, Any]] = []
    for action, details, timestamp in audit_rows:
        detail_map = details if isinstance(details, dict) else {}
        result = str(detail_map.get("result") or "").strip().lower()
        if result in {"denied", "failed", "error"}:
            level = "ERROR"
        elif result == "success":
            level = "SUCCESS"
        else:
            level = "INFO"
        message_action = str(
            detail_map.get("action")
            or detail_map.get("event_type")
            or action
            or "agent event"
        ).strip()
        message = message_action.replace("_", " ").capitalize() or "Agent event"
        reason = str(detail_map.get("reason") or "").strip()
        if reason:
            message = f"{message}: {reason}"

        entries.append(
            {
                "timestamp": _normalize_event_timestamp(timestamp),
                "level": level,
                "message": message,
                "source": "audit",
            }
        )
    return entries


def _default_agent_metrics() -> Dict[str, Any]:
    """Default metrics payload for agent detail page."""
    return {
        "tasksExecuted": 0,
        "tasksCompleted": 0,
        "tasksFailed": 0,
        "completionRate": 0.0,
        "successRate": 0.0,
        "failureRate": 0.0,
        "pendingTasks": 0,
        "inProgressTasks": 0,
        "lastActivityAt": None,
    }


def _build_agent_metrics_from_task_rows(
    task_status_rows: List[Tuple[Any, Any]],
    last_activity_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Build aggregate task metrics for one agent."""
    metrics = _default_agent_metrics()
    for task_status, count in task_status_rows:
        normalized_status = _normalize_task_status(task_status)
        if normalized_status == "completed":
            metrics["tasksCompleted"] += int(count or 0)
        elif normalized_status == "failed":
            metrics["tasksFailed"] += int(count or 0)
        elif normalized_status == "pending":
            metrics["pendingTasks"] += int(count or 0)
        elif normalized_status == "in_progress":
            metrics["inProgressTasks"] += int(count or 0)

    tasks_executed = metrics["tasksCompleted"] + metrics["tasksFailed"]
    metrics["tasksExecuted"] = tasks_executed
    if tasks_executed > 0:
        metrics["completionRate"] = round(metrics["tasksCompleted"] / tasks_executed, 4)
        metrics["successRate"] = metrics["completionRate"]
        metrics["failureRate"] = round(metrics["tasksFailed"] / tasks_executed, 4)

    if last_activity_at:
        metrics["lastActivityAt"] = _normalize_event_timestamp(last_activity_at)

    return metrics


def _resolve_model_context_window(
    provider: Any,
    provider_name: str,
    model_name: str,
) -> Optional[int]:
    """Resolve model context window from provider metadata or detector fallback."""
    # Priority 1: persisted model metadata from provider config.
    if provider and provider.model_metadata and model_name in provider.model_metadata:
        metadata = provider.model_metadata.get(model_name) or {}
        context_window = _to_positive_int(
            metadata.get("context_window") or metadata.get("context_length")
        )
        if context_window:
            return context_window

    # Priority 2: heuristic detector fallback.
    try:
        from llm_providers.model_metadata import EnhancedModelCapabilityDetector

        detector = EnhancedModelCapabilityDetector()
        detected = detector.detect_metadata(model_name, provider_name)
        return _to_positive_int(detected.context_window)
    except Exception as detect_error:
        logger.warning(
            "Failed to resolve model context window via detector: %s",
            detect_error,
        )
        return None


_HISTORY_ALLOWED_ROLES = {"user", "assistant"}
_MAX_HISTORY_MESSAGES = 24
_MAX_HISTORY_CONTENT_CHARS = 4000
_MAX_HISTORY_MULTIMODAL_ITEMS = 8
_MAX_HISTORY_IMAGE_ITEMS = 4
_MAX_HISTORY_IMAGE_URL_CHARS = 2_000_000


def _normalize_history_content(content: Any) -> Any:
    """Normalize history content payload into plain text or multimodal list."""
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: List[str] = []
        multimodal_items: List[Dict[str, Any]] = []
        image_item_count = 0
        has_image_items = False
        ignored_item_types = {
            "thinking",
            "reasoning",
            "info",
            "status",
            "round_stats",
            "tool_call",
            "tool_result",
            "tool_error",
            "error_feedback",
        }
        for item in content:
            if len(multimodal_items) >= _MAX_HISTORY_MULTIMODAL_ITEMS:
                break
            if isinstance(item, str) and item.strip():
                text_value = item.strip()
                text_parts.append(text_value)
                multimodal_items.append({"type": "text", "text": text_value})
                continue
            if isinstance(item, dict):
                item_type = str(item.get("type") or "").strip().lower()
                if item_type in ignored_item_types:
                    continue
                if item_type == "image_url":
                    if image_item_count >= _MAX_HISTORY_IMAGE_ITEMS:
                        continue

                    image_url = item.get("image_url")
                    url_value: Optional[str] = None
                    if isinstance(image_url, dict):
                        raw_url = image_url.get("url")
                        if isinstance(raw_url, str):
                            url_value = raw_url.strip()
                    elif isinstance(image_url, str):
                        url_value = image_url.strip()

                    if (
                        url_value
                        and len(url_value) <= _MAX_HISTORY_IMAGE_URL_CHARS
                        and (
                            url_value.startswith("data:image/")
                            or url_value.startswith("http://")
                            or url_value.startswith("https://")
                        )
                    ):
                        multimodal_items.append(
                            {"type": "image_url", "image_url": {"url": url_value}}
                        )
                        image_item_count += 1
                        has_image_items = True
                    continue

                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    text_value = text.strip()
                    text_parts.append(text_value)
                    multimodal_items.append({"type": "text", "text": text_value})

        if has_image_items and multimodal_items:
            return multimodal_items
        return "\n".join(text_parts)

    if content is None:
        return ""

    return str(content)


def _sanitize_history_messages(raw_history: Any) -> List[Dict[str, Any]]:
    """Sanitize history payload to avoid context pollution and token explosion."""
    if not isinstance(raw_history, list):
        return []

    sanitized: List[Dict[str, Any]] = []
    for entry in raw_history:
        if not isinstance(entry, dict):
            continue

        role = str(entry.get("role") or "").strip().lower()
        if role not in _HISTORY_ALLOWED_ROLES:
            continue

        normalized_content = _normalize_history_content(entry.get("content"))
        if isinstance(normalized_content, list):
            content = normalized_content
        else:
            content = str(normalized_content or "").strip()
            if len(content) > _MAX_HISTORY_CONTENT_CHARS:
                content = content[:_MAX_HISTORY_CONTENT_CHARS]

        if not content:
            continue

        sanitized.append({"role": role, "content": content})

    if len(sanitized) > _MAX_HISTORY_MESSAGES:
        sanitized = sanitized[-_MAX_HISTORY_MESSAGES:]

    return sanitized


def _infer_image_format(content_type: Optional[str], name: Optional[str] = None) -> str:
    """Infer image format label for data URLs."""
    normalized_type = str(content_type or "").strip().lower()
    normalized_name = str(name or "").strip().lower()

    if "png" in normalized_type or normalized_name.endswith(".png"):
        return "png"
    if "webp" in normalized_type or normalized_name.endswith(".webp"):
        return "webp"
    if "gif" in normalized_type or normalized_name.endswith(".gif"):
        return "gif"
    if (
        "bmp" in normalized_type
        or normalized_name.endswith(".bmp")
        or normalized_name.endswith(".dib")
    ):
        return "bmp"
    if (
        "tif" in normalized_type
        or "tiff" in normalized_type
        or normalized_name.endswith(".tif")
        or normalized_name.endswith(".tiff")
    ):
        return "tiff"
    return "jpeg"




def _extract_token_usage_from_metadata(metadata: Dict[str, Any]) -> Tuple[int, int]:
    """Extract input/output token usage from provider metadata."""
    if not isinstance(metadata, dict):
        return 0, 0

    if "usage" in metadata:
        usage = metadata["usage"]
        if isinstance(usage, dict):
            input_tokens = usage.get("prompt_tokens", 0) or usage.get("input_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0) or usage.get("output_tokens", 0)
            return int(input_tokens or 0), int(output_tokens or 0)

        input_tokens = getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0)
        output_tokens = getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0)
        return int(input_tokens or 0), int(output_tokens or 0)

    if "token_usage" in metadata:
        token_usage = metadata["token_usage"] or {}
        input_tokens = token_usage.get("prompt_tokens", 0)
        output_tokens = token_usage.get("completion_tokens", 0)
        return int(input_tokens or 0), int(output_tokens or 0)

    return 0, 0


_WORKSPACE_INLINE_PREVIEW_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".xml",
    ".html",
    ".htm",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".css",
    ".scss",
    ".sql",
    ".log",
}


def _resolve_safe_workspace_path(workdir: Path, requested_path: str = "") -> Tuple[Path, str]:
    """Resolve user path under session workdir and prevent traversal."""
    root = workdir.resolve()
    raw_path = str(requested_path or "").replace("\\", "/").lstrip("/")
    if raw_path.startswith("workspace/"):
        raw_path = raw_path[len("workspace/") :]

    candidate = (root / raw_path).resolve() if raw_path else root
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid workspace file path")

    if candidate.exists():
        relative = str(candidate.relative_to(root)).replace("\\", "/")
    else:
        relative = raw_path
    return candidate, relative


def _list_session_workspace_entries(
    workdir: Path,
    path: str = "",
    recursive: bool = False,
) -> List[Dict[str, Any]]:
    """List files/directories from a session workspace."""
    target, _ = _resolve_safe_workspace_path(workdir, path)
    if not target.exists():
        return []

    root = workdir.resolve()
    candidates: List[Path] = []
    if target.is_file():
        candidates = [target]
    elif recursive:
        candidates = [item for item in target.rglob("*")]
    else:
        candidates = list(target.iterdir())

    entries: List[Dict[str, Any]] = []
    for item in candidates:
        if item.name in {".DS_Store"}:
            continue

        try:
            stat_result = item.stat()
        except OSError:
            continue

        is_directory = item.is_dir()
        relative_path = str(item.resolve().relative_to(root)).replace("\\", "/")
        # Keep hidden process markers accessible if user explicitly asks for them,
        # but avoid cluttering default list with top-level dot files.
        if not path and not recursive and item.name.startswith("."):
            continue

        entries.append(
            {
                "name": item.name,
                "path": relative_path,
                "size": int(stat_result.st_size) if not is_directory else 0,
                "is_directory": is_directory,
                "modified_at": datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
                "previewable_inline": (
                    (item.suffix or "").lower() in _WORKSPACE_INLINE_PREVIEW_EXTENSIONS
                ),
            }
        )

    entries.sort(key=lambda e: (e["path"].count("/"), e["path"]))
    return entries


def _build_download_content_disposition(
    filename: str,
    disposition: str = "attachment",
) -> str:
    """Build RFC-compliant Content-Disposition header."""
    normalized_name = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    if not normalized_name:
        normalized_name = "download"

    ascii_name = normalized_name.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_name).strip("._")
    if not ascii_name:
        ascii_name = "download"

    encoded_name = urllib.parse.quote(normalized_name)
    safe_disposition = "inline" if disposition == "inline" else "attachment"
    return f'{safe_disposition}; filename="{ascii_name}"; ' f"filename*=UTF-8''{encoded_name}"


def _build_retrieval_process_messages(context_debug: Dict[str, Any]) -> List[str]:
    """Build user-facing retrieval debug messages for SSE process stream."""
    messages: List[str] = []
    timing_debug = context_debug.get("timing_ms") or {}
    context_total_ms = timing_debug.get("total")
    if isinstance(context_total_ms, (int, float)):
        messages.append(f"[上下文构建] 总耗时: {float(context_total_ms):.2f}ms")

    memory_debug = context_debug.get("memory") or {}
    memory_query = _trim_process_text(memory_debug.get("query"), 180)
    if memory_query:
        messages.append(f"[记忆检索] 查询: {memory_query}")

    top_k = memory_debug.get("top_k")
    if isinstance(top_k, int):
        messages.append(f"[记忆检索] top_k: {top_k}")

    memory_timing = memory_debug.get("timing_ms") or {}
    memory_total_ms = memory_timing.get("total")
    if isinstance(memory_total_ms, (int, float)):
        messages.append(f"[记忆检索] 总耗时: {float(memory_total_ms):.2f}ms")

    scopes = memory_debug.get("scopes") or []
    if scopes:
        messages.append(f"[记忆检索] 有效作用域: {', '.join(scopes)}")
    messages.append(
        "[记忆检索] 历史上下文意图: "
        + ("是" if memory_debug.get("history_context_requested") else "否")
    )

    for scope_key, scope_label in (
        ("agent", "agent"),
        ("company", "company"),
        ("user_context", "user_context"),
    ):
        scope_info = memory_debug.get(scope_key) or {}
        if not scope_info.get("enabled"):
            continue

        scope_error = scope_info.get("error")
        if scope_error:
            messages.append(
                f"[记忆检索][{scope_label}] 失败: {_trim_process_text(scope_error, 180)}"
            )
            continue

        scope_filter = _trim_process_text(scope_info.get("filter"), 140)
        if scope_filter:
            messages.append(f"[记忆检索][{scope_label}] 过滤条件: {scope_filter}")

        min_similarity = scope_info.get("min_similarity")
        if isinstance(min_similarity, (int, float)):
            messages.append(
                f"[记忆检索][{scope_label}] 最小相似度阈值: {float(min_similarity):.2f}"
            )
        scope_latency_ms = scope_info.get("latency_ms")
        if isinstance(scope_latency_ms, (int, float)):
            messages.append(f"[记忆检索][{scope_label}] 耗时: {float(scope_latency_ms):.2f}ms")

        pre_filter_hit_count = int(scope_info.get("pre_filter_hit_count") or 0)
        hit_count = int(scope_info.get("hit_count") or 0)
        messages.append(f"[记忆检索][{scope_label}] 命中 {hit_count} 条")

        filtered_out_count = int(scope_info.get("filtered_out_count") or 0)
        if pre_filter_hit_count or filtered_out_count:
            messages.append(
                f"[记忆检索][{scope_label}] 原始命中 {pre_filter_hit_count} 条，"
                f"过滤后 {hit_count} 条，剔除 {filtered_out_count} 条"
            )

        interaction_logs_pruned = int(scope_info.get("interaction_logs_pruned") or 0)
        if interaction_logs_pruned:
            messages.append(
                f"[记忆检索][{scope_label}] 已剔除任务日志型记忆 {interaction_logs_pruned} 条"
            )

        if scope_info.get("fallback_used"):
            fallback_count = int(scope_info.get("fallback_hit_count") or hit_count)
            messages.append(
                f"[记忆检索][{scope_label}] 触发兜底检索(min_similarity=0)，命中 {fallback_count} 条"
            )

        fallback_error = scope_info.get("fallback_error")
        if fallback_error:
            messages.append(
                f"[记忆检索][{scope_label}] 兜底检索失败: {_trim_process_text(fallback_error, 180)}"
            )

        for idx, hit in enumerate(scope_info.get("hits") or [], start=1):
            messages.append(f"[记忆命中][{scope_label}#{idx}] {_trim_process_text(str(hit), 180)}")

    knowledge_debug = context_debug.get("knowledge") or {}
    if knowledge_debug:
        knowledge_query = _trim_process_text(knowledge_debug.get("query"), 180)
        if knowledge_query:
            messages.append(f"[知识库检索] 查询: {knowledge_query}")

        knowledge_top_k = knowledge_debug.get("top_k")
        if isinstance(knowledge_top_k, int):
            messages.append(f"[知识库检索] top_k: {knowledge_top_k}")

        knowledge_timing = knowledge_debug.get("timing_ms") or {}
        knowledge_total_ms = knowledge_timing.get("total")
        if isinstance(knowledge_total_ms, (int, float)):
            messages.append(f"[知识库检索] 总耗时: {float(knowledge_total_ms):.2f}ms")
        candidate_resolution_ms = knowledge_timing.get("candidate_resolution")
        if isinstance(candidate_resolution_ms, (int, float)):
            messages.append(f"[知识库检索] 候选解析耗时: {float(candidate_resolution_ms):.2f}ms")
        search_ms = knowledge_timing.get("search")
        if isinstance(search_ms, (int, float)):
            messages.append(f"[知识库检索] 检索耗时: {float(search_ms):.2f}ms")

        candidate_count = knowledge_debug.get("candidate_document_count")
        if candidate_count is None:
            messages.append("[知识库检索] 候选文档范围: 全部可访问文档")
        else:
            messages.append(f"[知识库检索] 候选文档数: {candidate_count}")

        candidate_preview = knowledge_debug.get("candidate_document_ids_preview") or []
        if candidate_preview:
            preview_text = ", ".join(_short_id(doc_id) for doc_id in candidate_preview[:5])
            messages.append(f"[知识库检索] 候选文档预览: {preview_text}")

        knowledge_error = knowledge_debug.get("error")
        if knowledge_error:
            messages.append(f"[知识库检索] 失败: {_trim_process_text(knowledge_error, 180)}")
        else:
            hit_count = int(knowledge_debug.get("hit_count") or 0)
            messages.append(f"[知识库检索] 命中 {hit_count} 条")

            for idx, hit in enumerate((knowledge_debug.get("hits") or [])[:5], start=1):
                title = _trim_process_text(hit.get("title") or "-", 80)
                file_ref = _trim_process_text(hit.get("file_reference") or "-", 100)
                doc_id = _short_id(hit.get("document_id"))
                score = hit.get("similarity_score")
                score_text = f"{float(score):.3f}" if isinstance(score, (int, float)) else "-"
                excerpt = _trim_process_text(hit.get("excerpt") or "", 180)

                messages.append(
                    f"[知识命中#{idx}] title={title}; file={file_ref}; doc={doc_id}; score={score_text}"
                )
                if excerpt:
                    messages.append(f"[知识片段#{idx}] {excerpt}")

    return messages


_SESSION_MEMORY_CALLBACK_REGISTERED = False
_SESSION_MEMORY_MAX_TURNS = 24
_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH = 16
_SESSION_MEMORY_ITEM_MAX_CHARS = 320
_SESSION_MEMORY_MAX_PREFERENCE_FACTS = 12
_SESSION_MEMORY_MAX_AGENT_CANDIDATES = 4
_SESSION_MEMORY_USER_SIGNAL_TYPE = "user_preference"
_SESSION_MEMORY_AGENT_SIGNAL_TYPE = "agent_memory_candidate"
_SESSION_MEMORY_AGENT_REVIEW_PENDING = "pending"
_SESSION_MEMORY_LLM_MIN_PREFERENCE_CONFIDENCE = 0.62
_SESSION_MEMORY_LLM_MIN_AGENT_CONFIDENCE = 0.6
_SESSION_MEMORY_LLM_PROMPT_MAX_CHARS = 14000
_SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS = 4.0
_SESSION_MEMORY_FAILURE_BACKOFF_SECONDS = 60.0
_SESSION_MEMORY_EXTRACTION_FAIL_UNTIL: Dict[str, float] = {}
_PERSISTENT_PREFERENCE_CUES = (
    "以后",
    "下次",
    "默认",
    "长期",
    "一直",
    "始终",
    "每次",
    "都按",
    "固定",
    "统一",
    "习惯",
    "from now on",
    "default",
    "always",
)
_AGENT_SOP_HINT_CUES = (
    "步骤",
    "流程",
    "sop",
    "step",
    "first",
    "then",
    "最后",
    "最后一步",
)
_BULLET_LINE_PATTERN = re.compile(
    r"^\s*(?:\d+[\.、\)]\s*|[-*•]\s*)(.+)$",
    flags=re.MULTILINE,
)
_FOOD_PREFERENCE_LIKE_PATTERNS = (
    re.compile(r"我(?:比较|更)?(?:偏)?喜欢(?:吃)?(?P<item>[^，。！？；,.!?]{1,24})"),
    re.compile(r"我爱吃(?P<item>[^，。！？；,.!?]{1,24})"),
    re.compile(r"我偏好(?P<item>[^，。！？；,.!?]{1,24})"),
)
_FOOD_PREFERENCE_AVOID_PATTERNS = (
    re.compile(r"我(?:不吃|不喜欢吃|忌口)(?P<item>[^，。！？；,.!?]{1,24})"),
    re.compile(r"我(?:对)?(?P<item>[^，。！？；,.!?]{1,24})过敏"),
)
_PREFERENCE_ITEM_TRAILING_CLEAN_PATTERN = re.compile(
    r"(?:怎么做|怎么弄|咋做|如何做|做法|怎么制作|如何制作).*$",
    flags=re.IGNORECASE,
)


def _normalize_session_memory_text(
    text: Any, max_chars: int = _SESSION_MEMORY_ITEM_MAX_CHARS
) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3] + "..."


def _contains_persistent_preference_cue(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(cue in lowered for cue in _PERSISTENT_PREFERENCE_CUES)


def _detect_output_format_preference(text: str) -> Optional[str]:
    lowered = str(text or "").lower()
    if not lowered:
        return None
    if "markdown" in lowered or "md文档" in lowered or re.search(r"\bmd\b", lowered):
        return "markdown"
    if "pdf" in lowered:
        return "pdf"
    if "docx" in lowered or "word" in lowered or "word文档" in lowered:
        return "word"
    if "excel" in lowered or "xlsx" in lowered:
        return "excel"
    if "ppt" in lowered or "pptx" in lowered:
        return "ppt"
    if "json" in lowered:
        return "json"
    if "html" in lowered:
        return "html"
    if "表格" in lowered:
        return "table"
    return None


def _detect_language_preference(text: str) -> Optional[str]:
    lowered = str(text or "").lower()
    if not lowered:
        return None

    zh = ("中文" in lowered) or ("简体" in lowered) or ("zh-cn" in lowered)
    en = ("英文" in lowered) or ("english" in lowered) or ("en-us" in lowered)
    if zh and en:
        return "bilingual"
    if zh:
        return "zh-CN"
    if en:
        return "en-US"
    return None


def _detect_response_style_preference(text: str) -> Optional[str]:
    lowered = str(text or "").lower()
    if not lowered:
        return None
    if "简洁" in lowered or "简短" in lowered or "精简" in lowered:
        return "concise"
    if "详细" in lowered or "全面" in lowered:
        return "detailed"
    if "分步骤" in lowered or "step by step" in lowered:
        return "step_by_step"
    if "要点" in lowered:
        return "bullet_points"
    if "正式" in lowered:
        return "formal"
    return None


def _normalize_preference_item(value: str, max_chars: int = 24) -> Optional[str]:
    item = str(value or "").strip()
    if not item:
        return None

    item = _PREFERENCE_ITEM_TRAILING_CLEAN_PATTERN.sub("", item).strip()
    item = re.sub(r"^[：:，,\s]+", "", item)
    item = re.sub(r"[，,。！？!?；;\s]+$", "", item)
    item = " ".join(item.split())
    if not item:
        return None
    if len(item) > max_chars:
        return None
    if item in {"什么", "啥", "一下", "一点"}:
        return None
    return item


def _detect_food_preference_signal(text: str) -> Optional[Tuple[str, str]]:
    message = str(text or "").strip()
    if not message:
        return None

    for pattern in _FOOD_PREFERENCE_AVOID_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        item = _normalize_preference_item(match.group("item"))
        if item:
            return "food_preference_avoid", item

    for pattern in _FOOD_PREFERENCE_LIKE_PATTERNS:
        match = pattern.search(message)
        if not match:
            continue
        item = _normalize_preference_item(match.group("item"))
        if item:
            return "food_preference_like", item

    return None


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value

    raw = str(value or "").strip()
    if not raw:
        return None

    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _extract_json_object_from_text(text: str) -> Optional[Dict[str, Any]]:
    parsed, _ = _extract_json_object_from_text_with_meta(text)
    return parsed


def _extract_json_object_from_text_with_meta(
    text: str,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    raw = str(text or "")
    stripped = raw.strip()
    metadata: Dict[str, Any] = {
        "parse_status": "empty_response",
        "parse_source": None,
        "json_root_type": None,
        "parse_error": None,
        "raw_content_chars": len(raw),
    }
    if not stripped:
        return None, metadata

    candidates: List[Tuple[str, str]] = []
    seen_candidates: set[str] = set()

    def _add_candidate(source: str, candidate: str) -> None:
        normalized_candidate = str(candidate or "").strip()
        if not normalized_candidate or normalized_candidate in seen_candidates:
            return
        seen_candidates.add(normalized_candidate)
        candidates.append((source, normalized_candidate))

    _add_candidate("raw", stripped)

    block_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw, flags=re.IGNORECASE)
    if block_match:
        _add_candidate("code_fence", block_match.group(1))

    left = raw.find("{")
    right = raw.rfind("}")
    if left >= 0 and right > left:
        _add_candidate("brace_slice", raw[left : right + 1])

    first_non_object_root: Optional[str] = None
    parse_errors: List[str] = []
    for source, candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception as e:
            parse_errors.append(
                f"{source}:{_normalize_session_memory_text(str(e), max_chars=96)}"
            )
            continue

        if isinstance(parsed, dict):
            metadata.update(
                {
                    "parse_status": "ok",
                    "parse_source": source,
                    "json_root_type": "object",
                }
            )
            return parsed, metadata

        if not first_non_object_root:
            first_non_object_root = type(parsed).__name__

    if first_non_object_root:
        metadata.update(
            {
                "parse_status": "json_not_object",
                "json_root_type": first_non_object_root,
            }
        )
    else:
        metadata.update({"parse_status": "json_parse_failed"})

    if parse_errors:
        metadata["parse_error"] = _normalize_session_memory_text(
            "; ".join(parse_errors),
            max_chars=240,
        )
    return None, metadata


def _normalize_memory_key(value: Any, max_chars: int = 64) -> Optional[str]:
    key = str(value or "").strip().lower()
    if not key:
        return None
    key = re.sub(r"[^a-z0-9_]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    if not key:
        return None
    if len(key) > max_chars:
        key = key[:max_chars].rstrip("_")
    return key or None


def _coerce_confidence(value: Any, default: float = 0.7) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = default
    return max(0.0, min(1.0, parsed))


def _resolve_provider_default_chat_model_from_config(
    config: Any,
    provider_name: Optional[str],
) -> Optional[str]:
    if not config or not provider_name:
        return None

    raw_models = config.get(f"llm.providers.{provider_name}.models")
    if isinstance(raw_models, dict):
        for preferred_key in ("chat", "default", "completion", "instruct"):
            candidate = str(raw_models.get(preferred_key) or "").strip()
            if candidate:
                return candidate
        for value in raw_models.values():
            candidate = str(value or "").strip()
            if candidate:
                return candidate
        return None

    if isinstance(raw_models, list):
        for value in raw_models:
            candidate = str(value or "").strip()
            if candidate:
                return candidate
        return None

    candidate = str(raw_models or "").strip()
    return candidate or None


def _build_llm_memory_extraction_prompt(
    turns: List[Dict[str, str]],
    agent_name: str,
) -> Tuple[str, Dict[int, Optional[str]]]:
    selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
    lines: List[str] = []
    turn_ts_map: Dict[int, Optional[str]] = {}

    for idx, turn in enumerate(selected_turns, start=1):
        user_text = _normalize_session_memory_text(
            turn.get("user_message", ""),
            max_chars=520,
        )
        agent_text = _normalize_session_memory_text(
            turn.get("agent_response", ""),
            max_chars=760,
        )
        timestamp = str(turn.get("timestamp") or "").strip() or None
        turn_ts_map[idx] = timestamp
        lines.append(
            "\n".join(
                [
                    f"[TURN {idx}] timestamp={timestamp or '-'}",
                    f"USER: {user_text or '-'}",
                    f"ASSISTANT: {agent_text or '-'}",
                ]
            )
        )

    transcript = "\n\n".join(lines)
    if len(transcript) > _SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:
        transcript = transcript[-_SESSION_MEMORY_LLM_PROMPT_MAX_CHARS :]

    prompt = f"""
你是“会话记忆抽取器”。你要从会话中提取高价值、可长期复用的记忆。输出必须是 JSON 对象，不要输出解释文字。

Agent 名称: {agent_name or "-"}

抽取目标:
1. user_preferences: 提取“用户画像事实”，不仅限于喜欢/不喜欢。
2. agent_memory_candidates: 提取可跨场景复用的通用方法模板（后续人工审批）。

user_preferences 可包含的画像要素（示例）:
- 偏好/禁忌: food_preference_like, food_preference_avoid, communication_style_preference
- 经历/背景: experience_*
- 能力/擅长: skill_*, capability_*
- 长期目标: goal_*
- 稳定约束: allergy_*, constraint_*, budget_preference_*
- 习惯/决策方式: habit_*, decision_style_*

强约束:
- 只保留“未来任务仍有帮助”的稳定事实；一次性临时诉求不提取。
- 禁止猜测和延伸推断，只能提取用户明确说过的信息。
- 若单次会话出现多条有效画像事实，必须全部提取，不要只保留 1 条。
- key 使用英文 snake_case；value 简短明确。
- 如无有效项，返回空数组。

高优先级规则:
- 对用户直接陈述（如“我喜欢X/我做过X/我擅长X/我不吃X/我过敏X/我通常预算X”）优先提取。
- 这类直接陈述建议 explicit_source=true，confidence >= 0.82。

agent_memory_candidates 规则:
- 必须可迁移、可复用：避免绑定具体人名/地名/商品名/单次任务细节。
- 输出应简洁：summary 1-2 句，steps 2-4 步，每步一句动作。
- 优先抽象为通用流程，如“澄清目标 -> 识别约束 -> 生成方案 -> 校验结果”。
- 若只是本次答案内容而非方法模板，不要提取。

输出 JSON Schema:
{{
  "user_preferences": [
    {{
      "key": "snake_case",
      "value": "简短明确",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.0,
      "reason": "为什么值得记忆",
      "evidence_turns": [1, 2]
    }}
  ],
  "agent_memory_candidates": [
    {{
      "candidate_type": "sop",
      "title": "流程标题",
      "summary": "通用方法总结",
      "steps": ["步骤1", "步骤2", "步骤3"],
      "applicability": "适用场景",
      "avoid": "不适用或注意事项",
      "confidence": 0.0,
      "evidence_turns": [2]
    }}
  ]
}}

示例:
输入:
USER: 我喜欢骑车，做过电商运营，也擅长写SQL
ASSISTANT: 收到

输出:
{{
  "user_preferences": [
    {{
      "key": "activity_preference_like",
      "value": "骑车",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.9,
      "reason": "用户明确陈述喜欢的活动",
      "evidence_turns": [1]
    }},
    {{
      "key": "experience_background",
      "value": "做过电商运营",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.86,
      "reason": "用户明确陈述过往经历",
      "evidence_turns": [1]
    }},
    {{
      "key": "skill_strength",
      "value": "SQL",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.88,
      "reason": "用户明确陈述擅长技能",
      "evidence_turns": [1]
    }}
  ],
  "agent_memory_candidates": []
}}

会话文本:
{transcript}
""".strip()

    return prompt, turn_ts_map


def _build_llm_explicit_preference_recall_prompt(
    turns: List[Dict[str, str]],
) -> Tuple[str, Dict[int, Optional[str]]]:
    selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
    lines: List[str] = []
    turn_ts_map: Dict[int, Optional[str]] = {}

    for idx, turn in enumerate(selected_turns, start=1):
        user_text = _normalize_session_memory_text(
            turn.get("user_message", ""),
            max_chars=520,
        )
        agent_text = _normalize_session_memory_text(
            turn.get("agent_response", ""),
            max_chars=420,
        )
        timestamp = str(turn.get("timestamp") or "").strip() or None
        turn_ts_map[idx] = timestamp
        lines.append(
            "\n".join(
                [
                    f"[TURN {idx}] timestamp={timestamp or '-'}",
                    f"USER: {user_text or '-'}",
                    f"ASSISTANT: {agent_text or '-'}",
                ]
            )
        )

    transcript = "\n\n".join(lines)
    if len(transcript) > _SESSION_MEMORY_LLM_PROMPT_MAX_CHARS:
        transcript = transcript[-_SESSION_MEMORY_LLM_PROMPT_MAX_CHARS :]

    prompt = f"""
你是“用户偏好补充抽取器”。你的目标是补充抽取用户明确陈述的稳定画像事实。
输出必须是 JSON 对象，不要输出解释文字。

补充抽取规则:
- 不仅抽取偏好，也可抽取经历/能力/长期目标/稳定约束/习惯（都要求用户明确陈述）。
- 可以是单轮，但必须是“用户直接表达”；禁止猜测、禁止偏好延伸。
- 一次性临时要求（如“这次导出 PDF”）不抽取。
- 同一会话若有多条有效画像事实，应全部提取。
- key 必须是英文 snake_case；value 必须简短。
- 如无有效项，返回空数组。
- 若出现明确陈述（如“我喜欢吃黄焖鸡/我擅长SQL/我做过运营”），不得漏提。

输出 JSON Schema:
{{
  "user_preferences": [
    {{
      "key": "snake_case",
      "value": "简短明确",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.0,
      "reason": "为什么值得记忆",
      "evidence_turns": [1]
    }}
  ]
}}

示例:
输入:
USER: 我喜欢吃黄焖鸡，也做过前端开发，擅长 SQL
ASSISTANT: 收到

输出:
{{
  "user_preferences": [
    {{
      "key": "food_preference_like",
      "value": "黄焖鸡",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.9,
      "reason": "用户明确陈述喜欢的食物",
      "evidence_turns": [1]
    }},
    {{
      "key": "experience_background",
      "value": "做过前端开发",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.86,
      "reason": "用户明确陈述过往经历",
      "evidence_turns": [1]
    }},
    {{
      "key": "skill_strength",
      "value": "SQL",
      "persistent": true,
      "explicit_source": true,
      "confidence": 0.88,
      "reason": "用户明确陈述擅长技能",
      "evidence_turns": [1]
    }}
  ]
}}

会话文本:
{transcript}
""".strip()

    return prompt, turn_ts_map


def _is_response_format_not_supported_error(error: Exception) -> bool:
    message = str(error or "").lower()
    if not message:
        return False
    unsupported_cues = (
        "response_format",
        "json_object",
        "json schema",
        "unsupported",
        "unexpected keyword argument",
        "extra fields not permitted",
        "unknown field",
    )
    return any(cue in message for cue in unsupported_cues)


def _coerce_positive_timeout_seconds(value: Any, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    return min(max(parsed, 0.5), 120.0)


async def _invalidate_timed_out_llm_provider(
    *,
    llm_router: Any,
    provider_name: Optional[str],
) -> None:
    if not provider_name:
        return
    invalidate_fn = getattr(llm_router, "invalidate_provider", None)
    if not callable(invalidate_fn):
        return
    try:
        invalidated = await invalidate_fn(provider_name)
        if invalidated:
            logger.info(
                "Session memory extraction invalidated timed-out provider cache",
                extra={"provider": provider_name},
            )
    except Exception as e:
        logger.warning(
            "Session memory extraction failed to invalidate timed-out provider cache",
            extra={"provider": provider_name, "error": str(e)},
        )


async def _call_llm_for_memory_json(
    *,
    llm_router: Any,
    prompt: str,
    provider: Optional[str],
    model: Optional[str],
    timeout_seconds: float = _SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    base_kwargs = {
        "prompt": prompt,
        "provider": provider,
        "model": model,
        "temperature": 0.1,
        "max_tokens": 1800,
    }

    async def _generate_and_parse(
        *,
        with_response_format: bool,
        response_mode: str,
        fallback_triggered: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        kwargs = dict(base_kwargs)
        if with_response_format:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = await asyncio.wait_for(
                llm_router.generate(**kwargs),
                timeout=max(float(timeout_seconds), 0.5),
            )
        except asyncio.TimeoutError as timeout_error:
            await _invalidate_timed_out_llm_provider(
                llm_router=llm_router,
                provider_name=provider,
            )
            raise TimeoutError(
                f"session_memory_extraction_timeout_{max(float(timeout_seconds), 0.5):.1f}s"
            ) from timeout_error
        raw_content = str(getattr(response, "content", "") or "")
        parsed_payload, parse_meta = _extract_json_object_from_text_with_meta(raw_content)
        parse_meta.update(
            {
                "response_mode": response_mode,
                "fallback_triggered": fallback_triggered,
            }
        )
        return parsed_payload or {}, parse_meta

    try:
        parsed_payload, parse_meta = await _generate_and_parse(
            with_response_format=True,
            response_mode="json_object",
            fallback_triggered=False,
        )
        if str(parse_meta.get("parse_status")) == "ok":
            return parsed_payload, parse_meta
        logger.info(
            "Session memory extraction fallback to plain response mode after non-json response",
            extra={
                "provider": provider or "auto",
                "model": model or "auto",
                "parse_status": parse_meta.get("parse_status"),
                "raw_content_chars": parse_meta.get("raw_content_chars"),
            },
        )
    except Exception as first_error:
        if not _is_response_format_not_supported_error(first_error):
            raise
        logger.info(
            "Session memory extraction fallback to plain response mode",
            extra={
                "provider": provider or "auto",
                "model": model or "auto",
                "error": str(first_error),
            },
        )

    return await _generate_and_parse(
        with_response_format=False,
        response_mode="plain_fallback",
        fallback_triggered=True,
    )


def _normalize_llm_user_preference_signals(
    raw_items: Any,
    turn_ts_map: Dict[int, Optional[str]],
    max_items: int = _SESSION_MEMORY_MAX_PREFERENCE_FACTS,
) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    safe_max_items = max(int(max_items or 0), 1)
    extracted: List[Dict[str, Any]] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        key = _normalize_memory_key(raw.get("key"))
        value = _normalize_session_memory_text(raw.get("value", ""), max_chars=120)
        if not key or not value:
            continue

        confidence = _coerce_confidence(raw.get("confidence"), default=0.72)
        if confidence < _SESSION_MEMORY_LLM_MIN_PREFERENCE_CONFIDENCE:
            continue

        evidence_turns_raw = raw.get("evidence_turns")
        evidence_turns: List[int] = []
        if isinstance(evidence_turns_raw, list):
            for item in evidence_turns_raw:
                parsed = _to_positive_int(item)
                if parsed and parsed not in evidence_turns:
                    evidence_turns.append(parsed)

        evidence_count = (
            len(evidence_turns)
            if evidence_turns
            else (_to_positive_int(raw.get("evidence_count")) or 1)
        )
        is_persistent = bool(raw.get("persistent"))
        explicit_source = bool(raw.get("explicit_source"))
        # Allow single-turn direct preference statements if model gives strong confidence.
        allow_single_turn = explicit_source or confidence >= 0.82
        if not is_persistent and evidence_count < 2 and not allow_single_turn:
            continue

        latest_turn_ts: Optional[str] = None
        for turn_idx in evidence_turns:
            candidate_ts = turn_ts_map.get(turn_idx)
            if not candidate_ts:
                continue
            if (latest_turn_ts is None) or str(candidate_ts) > str(latest_turn_ts):
                latest_turn_ts = str(candidate_ts)

        reason = _normalize_session_memory_text(raw.get("reason", ""), max_chars=200)
        extracted.append(
            {
                "key": key,
                "value": value,
                "evidence_count": evidence_count,
                "persistent": is_persistent,
                "strong_signal": is_persistent,
                "confidence": confidence,
                "latest_ts": latest_turn_ts,
                "reason": reason or None,
                "explicit_source": explicit_source,
            }
        )

    extracted.sort(
        key=lambda item: (
            int(bool(item.get("persistent"))),
            float(item.get("confidence") or 0.0),
            int(item.get("evidence_count") or 0),
            str(item.get("latest_ts") or ""),
        ),
        reverse=True,
    )
    return extracted[:safe_max_items]


def _build_agent_candidate_fingerprint(topic: str, steps: List[str]) -> str:
    payload = f"{topic.strip().lower()}||{'|'.join(steps).strip().lower()}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]


def _normalize_llm_agent_candidates(
    raw_items: Any,
    *,
    agent_name: str,
    turn_ts_map: Dict[int, Optional[str]],
    max_items: int = _SESSION_MEMORY_MAX_AGENT_CANDIDATES,
) -> List[Dict[str, Any]]:
    if not isinstance(raw_items, list):
        return []

    safe_max_items = max(int(max_items or 0), 1)
    candidates: List[Dict[str, Any]] = []
    seen_fingerprints: set[str] = set()

    for raw in raw_items:
        if not isinstance(raw, dict):
            continue

        title = _normalize_session_memory_text(
            raw.get("title", "") or raw.get("topic", ""),
            max_chars=72,
        )
        summary = _normalize_session_memory_text(raw.get("summary", ""), max_chars=180)
        steps_raw = raw.get("steps")
        steps: List[str] = []
        if isinstance(steps_raw, list):
            for step in steps_raw:
                normalized_step = _normalize_session_memory_text(step, max_chars=72)
                if normalized_step and normalized_step not in steps:
                    steps.append(normalized_step)
        elif isinstance(steps_raw, str):
            for chunk in re.split(r"[|\n]", steps_raw):
                normalized_step = _normalize_session_memory_text(chunk, max_chars=72)
                if normalized_step and normalized_step not in steps:
                    steps.append(normalized_step)

        if len(steps) > 4:
            steps = steps[:4]

        if len(steps) < 2 and len(summary) < 30:
            continue

        confidence = _coerce_confidence(raw.get("confidence"), default=0.7)
        if confidence < _SESSION_MEMORY_LLM_MIN_AGENT_CONFIDENCE:
            continue

        candidate_type = _normalize_memory_key(raw.get("candidate_type"), max_chars=32) or "sop"
        applicability = _normalize_session_memory_text(raw.get("applicability", ""), max_chars=140)
        avoid = _normalize_session_memory_text(raw.get("avoid", ""), max_chars=140)

        topic_for_fingerprint = title or summary or "generic_sop"
        fingerprint = _build_agent_candidate_fingerprint(topic_for_fingerprint, steps)
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)

        evidence_turns_raw = raw.get("evidence_turns")
        evidence_turns: List[int] = []
        if isinstance(evidence_turns_raw, list):
            for item in evidence_turns_raw:
                parsed = _to_positive_int(item)
                if parsed and parsed not in evidence_turns:
                    evidence_turns.append(parsed)
        latest_turn_ts: Optional[str] = None
        for turn_idx in evidence_turns:
            candidate_ts = turn_ts_map.get(turn_idx)
            if not candidate_ts:
                continue
            if (latest_turn_ts is None) or str(candidate_ts) > str(latest_turn_ts):
                latest_turn_ts = str(candidate_ts)

        candidates.append(
            {
                "candidate_type": candidate_type,
                "topic": topic_for_fingerprint,
                "title": title,
                "summary": summary,
                "steps": steps,
                "applicability": applicability or None,
                "avoid": avoid or None,
                "confidence": confidence,
                "fingerprint": fingerprint,
                "agent_name": agent_name,
                "latest_ts": latest_turn_ts,
            }
        )
        if len(candidates) >= safe_max_items:
            break

    return candidates


async def _extract_session_memory_signals_with_llm(
    *,
    turns: List[Dict[str, str]],
    agent_id: Any,
    agent_name: str,
    session_id: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not turns:
        return [], []

    prompt, turn_ts_map = _build_llm_memory_extraction_prompt(turns, agent_name)

    agent_provider_name: Optional[str] = None
    agent_model_name: Optional[str] = None
    configured_provider_name: Optional[str] = None
    configured_model_name: Optional[str] = None
    global_chat_model: Optional[str] = None
    extraction_timeout_seconds = _SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS
    failure_backoff_seconds = _SESSION_MEMORY_FAILURE_BACKOFF_SECONDS
    max_preference_facts = _SESSION_MEMORY_MAX_PREFERENCE_FACTS
    max_agent_candidates = _SESSION_MEMORY_MAX_AGENT_CANDIDATES
    cfg: Any = None
    try:
        registry = get_agent_registry()
        agent_info = registry.get_agent(agent_id)
        if agent_info:
            agent_provider_name = str(agent_info.llm_provider or "").strip() or None
            agent_model_name = str(agent_info.llm_model or "").strip() or None
    except Exception:
        agent_provider_name = None
        agent_model_name = None

    try:
        from shared.config import get_config

        cfg = get_config()
        configured_provider = cfg.get("memory.enhanced_memory.fact_extraction.provider")
        configured_model = cfg.get("memory.enhanced_memory.fact_extraction.model")
        configured_chat = cfg.get("llm.model_mapping.chat")
        configured_timeout = cfg.get("memory.enhanced_memory.fact_extraction.timeout_seconds")
        configured_failure_backoff = cfg.get(
            "memory.enhanced_memory.fact_extraction.failure_backoff_seconds"
        )
        configured_max_facts = cfg.get("memory.enhanced_memory.fact_extraction.max_facts")
        configured_max_preferences = cfg.get(
            "memory.enhanced_memory.fact_extraction.max_preference_facts"
        )
        configured_max_candidates = cfg.get(
            "memory.enhanced_memory.fact_extraction.max_agent_candidates"
        )
        configured_provider_name = str(configured_provider or "").strip() or None
        configured_model_name = str(configured_model or "").strip() or None
        global_chat_model = str(configured_chat).strip() if configured_chat else None
        extraction_timeout_seconds = _coerce_positive_timeout_seconds(
            configured_timeout,
            default=_SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS,
        )
        failure_backoff_seconds = _coerce_positive_timeout_seconds(
            configured_failure_backoff,
            default=_SESSION_MEMORY_FAILURE_BACKOFF_SECONDS,
        )
        configured_max_facts_value = _to_positive_int(configured_max_facts)
        max_preference_facts = (
            _to_positive_int(configured_max_preferences)
            or configured_max_facts_value
            or _SESSION_MEMORY_MAX_PREFERENCE_FACTS
        )
        max_agent_candidates = (
            _to_positive_int(configured_max_candidates)
            or _SESSION_MEMORY_MAX_AGENT_CANDIDATES
        )
    except Exception:
        cfg = None
        configured_provider_name = None
        configured_model_name = None
        global_chat_model = None
        extraction_timeout_seconds = _SESSION_MEMORY_LLM_ATTEMPT_TIMEOUT_SECONDS
        failure_backoff_seconds = _SESSION_MEMORY_FAILURE_BACKOFF_SECONDS
        max_preference_facts = _SESSION_MEMORY_MAX_PREFERENCE_FACTS
        max_agent_candidates = _SESSION_MEMORY_MAX_AGENT_CANDIDATES

    backoff_key = f"{str(agent_id)}::{str(session_id or '')}"
    current_monotonic = time.monotonic()
    backoff_until = _SESSION_MEMORY_EXTRACTION_FAIL_UNTIL.get(backoff_key, 0.0)
    if current_monotonic < backoff_until:
        logger.info(
            "Session memory extraction skipped due to active failure backoff",
            extra={
                "agent_id": str(agent_id),
                "session_id": session_id,
                "remaining_backoff_seconds": round(backoff_until - current_monotonic, 3),
                "failure_backoff_seconds": failure_backoff_seconds,
            },
        )
        return [], []

    def _activate_failure_backoff(reason: str) -> None:
        if failure_backoff_seconds <= 0:
            return
        fail_until = time.monotonic() + max(float(failure_backoff_seconds), 0.5)
        _SESSION_MEMORY_EXTRACTION_FAIL_UNTIL[backoff_key] = fail_until
        logger.info(
            "Session memory extraction failure backoff activated",
            extra={
                "agent_id": str(agent_id),
                "session_id": session_id,
                "reason": reason,
                "failure_backoff_seconds": failure_backoff_seconds,
                "fail_until_monotonic": round(fail_until, 3),
            },
        )

    primary_provider = configured_provider_name or agent_provider_name
    primary_model = configured_model_name
    if not primary_model and primary_provider:
        primary_model = _resolve_provider_default_chat_model_from_config(cfg, primary_provider)
    if not primary_model and primary_provider == agent_provider_name:
        primary_model = agent_model_name
    if not primary_model:
        primary_model = global_chat_model

    attempt_plan: List[Tuple[Optional[str], Optional[str]]] = []
    if primary_provider or primary_model:
        attempt_plan.append((primary_provider, primary_model))
    if agent_provider_name or agent_model_name:
        attempt_plan.append((agent_provider_name, agent_model_name))
    if primary_model:
        attempt_plan.append((None, primary_model))
    attempt_plan.append((None, None))

    attempts: List[Tuple[Optional[str], Optional[str]]] = []
    for candidate in attempt_plan:
        if candidate not in attempts:
            attempts.append(candidate)
    attempt_plan_summary = [
        {"provider": provider_name or "auto", "model": model_name or "auto"}
        for provider_name, model_name in attempts
    ]
    extraction_log_base = {
        "agent_id": str(agent_id),
        "session_id": session_id,
    }
    logger.info(
        "Session memory extraction attempt plan",
        extra={
            **extraction_log_base,
            "attempt_plan": attempt_plan_summary,
            "attempt_timeout_seconds": extraction_timeout_seconds,
            "failure_backoff_seconds": failure_backoff_seconds,
            "max_preference_facts": max_preference_facts,
            "max_agent_candidates": max_agent_candidates,
        },
    )

    try:
        from llm_providers.router import get_llm_provider

        llm_router = get_llm_provider()
    except Exception as e:
        logger.warning(
            "LLM-based session memory extraction failed",
            extra={**extraction_log_base, "error": str(e)},
        )
        _activate_failure_backoff("llm_router_unavailable")
        return [], []

    async def _run_extraction_with_attempts(
        extraction_prompt: str,
        phase: str,
    ) -> Tuple[Dict[str, Any], Optional[str], Optional[str], Optional[Exception], Dict[str, Any]]:
        parsed_payload: Dict[str, Any] = {}
        used_provider: Optional[str] = None
        used_model: Optional[str] = None
        last_error: Optional[Exception] = None
        extraction_meta: Dict[str, Any] = {
            "phase": phase,
            "parse_status": "not_attempted",
            "response_mode": None,
            "fallback_triggered": False,
            "raw_content_chars": 0,
        }

        for attempt_index, (attempt_provider, attempt_model) in enumerate(attempts, start=1):
            try:
                parsed_payload, extraction_meta = await _call_llm_for_memory_json(
                    llm_router=llm_router,
                    prompt=extraction_prompt,
                    provider=attempt_provider,
                    model=attempt_model,
                    timeout_seconds=extraction_timeout_seconds,
                )
                extraction_meta = {
                    **extraction_meta,
                    "phase": phase,
                    "attempt": attempt_index,
                    "provider": attempt_provider or "auto",
                    "model": attempt_model or "auto",
                }
                parse_status = str(extraction_meta.get("parse_status") or "")
                if parse_status != "ok":
                    last_error = ValueError(f"memory_json_{parse_status or 'unknown'}")
                    logger.warning(
                        "Session memory extraction response parse failed",
                        extra={
                            **extraction_log_base,
                            "phase": phase,
                            "attempt": attempt_index,
                            "provider": attempt_provider or "auto",
                            "model": attempt_model or "auto",
                            "parse_status": parse_status or "unknown",
                            "parse_source": extraction_meta.get("parse_source"),
                            "json_root_type": extraction_meta.get("json_root_type"),
                            "response_mode": extraction_meta.get("response_mode"),
                            "raw_content_chars": extraction_meta.get("raw_content_chars"),
                            "fallback_triggered": bool(
                                extraction_meta.get("fallback_triggered")
                            ),
                            "parse_error": extraction_meta.get("parse_error"),
                        },
                    )
                    continue
                used_provider = attempt_provider
                used_model = attempt_model
                if primary_provider and attempt_provider != primary_provider:
                    logger.info(
                        "Session memory extraction fallback provider succeeded",
                        extra={
                            **extraction_log_base,
                            "phase": phase,
                            "original_provider": primary_provider,
                            "attempt": attempt_index,
                            "fallback_provider": attempt_provider or "auto",
                        },
                    )
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    "Session memory extraction attempt failed",
                    extra={
                        **extraction_log_base,
                        "phase": phase,
                        "attempt": attempt_index,
                        "provider": attempt_provider or "auto",
                        "model": attempt_model or "auto",
                        "error": str(e),
                    },
                )

        return parsed_payload, used_provider, used_model, last_error, extraction_meta

    parsed, used_provider, used_model, last_error, primary_extraction_meta = (
        await _run_extraction_with_attempts(
        prompt,
        "primary",
        )
    )
    if last_error and not parsed:
        logger.warning(
            "LLM-based session memory extraction failed",
            extra={
                **extraction_log_base,
                "error": str(last_error),
                "phase": primary_extraction_meta.get("phase"),
                "parse_status": primary_extraction_meta.get("parse_status"),
                "response_mode": primary_extraction_meta.get("response_mode"),
                "raw_content_chars": primary_extraction_meta.get("raw_content_chars"),
                "attempt": primary_extraction_meta.get("attempt"),
                "provider": primary_extraction_meta.get("provider"),
                "model": primary_extraction_meta.get("model"),
                "parse_error": primary_extraction_meta.get("parse_error"),
            },
        )
        _activate_failure_backoff("all_attempts_failed")
        return [], []

    user_items = parsed.get("user_preferences")
    candidate_items = parsed.get("agent_memory_candidates")
    user_signals = _normalize_llm_user_preference_signals(
        user_items,
        turn_ts_map,
        max_items=max_preference_facts,
    )
    agent_candidates = _normalize_llm_agent_candidates(
        candidate_items,
        agent_name=agent_name,
        turn_ts_map=turn_ts_map,
        max_items=max_agent_candidates,
    )

    secondary_raw_user_preferences = 0
    secondary_normalized_user_preferences = 0
    secondary_preference_pass_used = False
    secondary_extraction_meta: Dict[str, Any] = {
        "phase": "explicit_preference_recall",
        "parse_status": "not_run",
        "response_mode": None,
        "fallback_triggered": False,
        "raw_content_chars": 0,
    }
    if not user_signals:
        secondary_preference_pass_used = True
        recall_prompt, recall_turn_ts_map = _build_llm_explicit_preference_recall_prompt(turns)
        (
            recall_parsed,
            recall_provider,
            recall_model,
            recall_error,
            secondary_extraction_meta,
        ) = await _run_extraction_with_attempts(recall_prompt, "explicit_preference_recall")
        if recall_error and not recall_parsed:
            logger.warning(
                "LLM explicit-preference recall extraction failed",
                extra={
                    **extraction_log_base,
                    "error": str(recall_error),
                    "phase": secondary_extraction_meta.get("phase"),
                    "parse_status": secondary_extraction_meta.get("parse_status"),
                    "response_mode": secondary_extraction_meta.get("response_mode"),
                    "raw_content_chars": secondary_extraction_meta.get("raw_content_chars"),
                    "attempt": secondary_extraction_meta.get("attempt"),
                    "provider": secondary_extraction_meta.get("provider"),
                    "model": secondary_extraction_meta.get("model"),
                    "parse_error": secondary_extraction_meta.get("parse_error"),
                },
            )
        else:
            recall_user_items = recall_parsed.get("user_preferences")
            secondary_raw_user_preferences = (
                len(recall_user_items) if isinstance(recall_user_items, list) else 0
            )
            recall_signals = _normalize_llm_user_preference_signals(
                recall_user_items,
                recall_turn_ts_map,
                max_items=max_preference_facts,
            )
            secondary_normalized_user_preferences = len(recall_signals)
            if recall_signals:
                merged_by_key: Dict[str, Dict[str, Any]] = {
                    str(item.get("key")): item for item in user_signals if item.get("key")
                }
                for signal in recall_signals:
                    key = str(signal.get("key") or "").strip()
                    if not key:
                        continue
                    existing = merged_by_key.get(key)
                    if not existing:
                        merged_by_key[key] = signal
                        continue
                    current_score = (
                        int(bool(signal.get("persistent"))),
                        int(bool(signal.get("explicit_source"))),
                        float(signal.get("confidence") or 0.0),
                        int(signal.get("evidence_count") or 0),
                        str(signal.get("latest_ts") or ""),
                    )
                    existing_score = (
                        int(bool(existing.get("persistent"))),
                        int(bool(existing.get("explicit_source"))),
                        float(existing.get("confidence") or 0.0),
                        int(existing.get("evidence_count") or 0),
                        str(existing.get("latest_ts") or ""),
                    )
                    if current_score >= existing_score:
                        merged_by_key[key] = signal
                user_signals = sorted(
                    merged_by_key.values(),
                    key=lambda item: (
                        int(bool(item.get("persistent"))),
                        int(bool(item.get("explicit_source"))),
                        float(item.get("confidence") or 0.0),
                        int(item.get("evidence_count") or 0),
                        str(item.get("latest_ts") or ""),
                    ),
                    reverse=True,
                )[:max_preference_facts]
            if not used_provider and recall_provider:
                used_provider = recall_provider
            if not used_model and recall_model:
                used_model = recall_model

    primary_raw_user_preferences = len(user_items) if isinstance(user_items, list) else 0
    primary_raw_agent_candidates = len(candidate_items) if isinstance(candidate_items, list) else 0
    if (
        str(primary_extraction_meta.get("parse_status")) == "ok"
        and primary_raw_user_preferences == 0
        and primary_raw_agent_candidates == 0
    ):
        logger.info(
            "Session memory extraction primary response contained no extractable candidates",
            extra={
                **extraction_log_base,
                "response_mode": primary_extraction_meta.get("response_mode"),
                "parse_source": primary_extraction_meta.get("parse_source"),
                "raw_content_chars": primary_extraction_meta.get("raw_content_chars"),
                "parsed_top_level_keys": sorted(list(parsed.keys()))[:10],
            },
        )

    logger.info(
        "Session memory extraction completed",
        extra={
            **extraction_log_base,
            "provider": used_provider or "auto",
            "model": used_model or "auto",
            "turn_count": len(turns),
            "raw_user_preferences": primary_raw_user_preferences,
            "raw_agent_candidates": primary_raw_agent_candidates,
            "normalized_user_preferences": len(user_signals),
            "normalized_agent_candidates": len(agent_candidates),
            "secondary_preference_pass_used": secondary_preference_pass_used,
            "secondary_raw_user_preferences": secondary_raw_user_preferences,
            "secondary_normalized_user_preferences": secondary_normalized_user_preferences,
            "primary_phase": primary_extraction_meta.get("phase"),
            "primary_attempt": primary_extraction_meta.get("attempt"),
            "primary_parse_status": primary_extraction_meta.get("parse_status"),
            "primary_parse_source": primary_extraction_meta.get("parse_source"),
            "primary_response_mode": primary_extraction_meta.get("response_mode"),
            "primary_fallback_triggered": bool(
                primary_extraction_meta.get("fallback_triggered")
            ),
            "primary_raw_content_chars": primary_extraction_meta.get("raw_content_chars"),
            "secondary_phase": secondary_extraction_meta.get("phase"),
            "secondary_attempt": secondary_extraction_meta.get("attempt"),
            "secondary_parse_status": secondary_extraction_meta.get("parse_status"),
            "secondary_parse_source": secondary_extraction_meta.get("parse_source"),
            "secondary_response_mode": secondary_extraction_meta.get("response_mode"),
            "secondary_fallback_triggered": bool(
                secondary_extraction_meta.get("fallback_triggered")
            ),
            "secondary_raw_content_chars": secondary_extraction_meta.get("raw_content_chars"),
        },
    )
    _SESSION_MEMORY_EXTRACTION_FAIL_UNTIL.pop(backoff_key, None)
    return user_signals, agent_candidates


def _extract_user_preference_signals(turns: List[Dict[str, str]]) -> List[Dict[str, Any]]:
    """Extract persistent/repeated user preference signals from session turns."""
    selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for turn in selected_turns:
        user_message = _normalize_session_memory_text(turn.get("user_message", ""))
        if not user_message:
            continue

        persistent = _contains_persistent_preference_cue(user_message)
        latest_ts = _parse_iso_datetime(turn.get("timestamp"))
        detections: List[Tuple[str, str, bool]] = []

        output_format = _detect_output_format_preference(user_message)
        if output_format:
            detections.append(("output_format", output_format, False))

        language = _detect_language_preference(user_message)
        if language:
            detections.append(("language", language, False))

        style = _detect_response_style_preference(user_message)
        if style:
            detections.append(("response_style", style, False))

        food_preference = _detect_food_preference_signal(user_message)
        if food_preference:
            detections.append((food_preference[0], food_preference[1], True))

        for preference_key, preference_value, strong_signal in detections:
            bucket = grouped.setdefault(
                (preference_key, preference_value),
                {
                    "count": 0,
                    "persistent": False,
                    "strong_signal": False,
                    "latest_ts": None,
                },
            )
            bucket["count"] += 1
            bucket["persistent"] = bool(bucket["persistent"] or persistent)
            bucket["strong_signal"] = bool(bucket["strong_signal"] or strong_signal)
            if latest_ts and (
                bucket["latest_ts"] is None or latest_ts > bucket["latest_ts"]
            ):
                bucket["latest_ts"] = latest_ts

    extracted: List[Dict[str, Any]] = []
    for (preference_key, preference_value), bucket in grouped.items():
        evidence_count = int(bucket["count"])
        is_persistent = bool(bucket["persistent"])
        strong_signal = bool(bucket.get("strong_signal"))
        if not is_persistent and not strong_signal and evidence_count < 2:
            continue

        latest_ts = bucket.get("latest_ts")
        extracted.append(
            {
                "key": preference_key,
                "value": preference_value,
                "evidence_count": evidence_count,
                "persistent": is_persistent,
                "strong_signal": strong_signal,
                "confidence": (
                    0.92 if strong_signal else 0.88 if is_persistent else 0.68
                ),
                "latest_ts": latest_ts.isoformat() if isinstance(latest_ts, datetime) else None,
            }
        )

    extracted.sort(
        key=lambda item: (
            int(bool(item.get("persistent")) or bool(item.get("strong_signal"))),
            int(bool(item.get("strong_signal"))),
            int(item.get("evidence_count") or 0),
            str(item.get("latest_ts") or ""),
        ),
        reverse=True,
    )
    return extracted[:_SESSION_MEMORY_MAX_PREFERENCE_FACTS]


def _build_user_preference_memory_content(signal: Dict[str, Any]) -> str:
    return f"user.preference.{signal['key']}={signal['value']}"


def _build_user_preference_seed_facts(signal: Dict[str, Any]) -> List[Dict[str, Any]]:
    preference_key = _normalize_memory_key(signal.get("key"), max_chars=80)
    preference_value = _normalize_session_memory_text(signal.get("value", ""), max_chars=120)
    if not preference_key or not preference_value:
        return []

    confidence = _coerce_confidence(signal.get("confidence"), default=0.78)
    importance = 0.9 if bool(signal.get("persistent")) else 0.74
    return [
        {
            "key": f"user.preference.{preference_key}",
            "value": preference_value,
            "category": "user_preference",
            "confidence": confidence,
            "importance": importance,
            "source": "session_llm",
        }
    ]


def _split_user_preference_content(content: str) -> Tuple[Optional[str], Optional[str]]:
    normalized = str(content or "").strip()
    if not normalized.lower().startswith("user.preference.") or "=" not in normalized:
        return None, None

    left, right = normalized.split("=", 1)
    key = left.replace("user.preference.", "", 1).strip()
    value = right.strip()
    if not key or not value:
        return None, None
    return key, value


def _extract_step_lines(response: str) -> List[str]:
    matches = _BULLET_LINE_PATTERN.findall(str(response or ""))
    cleaned: List[str] = []
    for line in matches:
        value = _normalize_session_memory_text(line, max_chars=96)
        if value:
            cleaned.append(value)
    return cleaned


def _extract_agent_memory_candidates(
    turns: List[Dict[str, str]],
    agent_name: str,
) -> List[Dict[str, Any]]:
    selected_turns = turns[-_SESSION_MEMORY_MAX_TURNS_FOR_FLUSH:]
    candidates: List[Dict[str, Any]] = []
    seen_fingerprints = set()

    for turn in reversed(selected_turns):
        raw_response_text = str(turn.get("agent_response") or "")
        response_text = _normalize_session_memory_text(raw_response_text, max_chars=2400)
        if len(response_text) < 40:
            continue

        step_lines = _extract_step_lines(raw_response_text)
        if len(step_lines) < 3:
            continue

        topic = _normalize_session_memory_text(turn.get("user_message", ""), max_chars=96)
        if not topic:
            continue

        step_lines = step_lines[:5]
        fingerprint = _build_agent_candidate_fingerprint(topic, step_lines)
        if fingerprint in seen_fingerprints:
            continue
        seen_fingerprints.add(fingerprint)

        lowered_response = raw_response_text.lower()
        has_sop_hint = any(cue in lowered_response for cue in _AGENT_SOP_HINT_CUES)
        confidence = 0.76 if has_sop_hint else 0.64
        turn_ts = _parse_iso_datetime(turn.get("timestamp"))

        candidates.append(
            {
                "candidate_type": "sop",
                "topic": topic,
                "steps": step_lines,
                "confidence": confidence,
                "fingerprint": fingerprint,
                "agent_name": agent_name,
                "latest_ts": turn_ts.isoformat() if isinstance(turn_ts, datetime) else None,
            }
        )

        if len(candidates) >= _SESSION_MEMORY_MAX_AGENT_CANDIDATES:
            break

    return candidates


def _build_agent_candidate_content(candidate: Dict[str, Any]) -> str:
    steps_raw = candidate.get("steps") or []
    normalized_steps: List[str] = []
    for step in steps_raw:
        normalized_step = _normalize_session_memory_text(step, max_chars=72)
        if normalized_step and normalized_step not in normalized_steps:
            normalized_steps.append(normalized_step)
    steps = normalized_steps[:4]
    step_text = " | ".join(steps)

    title = _normalize_session_memory_text(candidate.get("title", ""), max_chars=72)
    summary = _normalize_session_memory_text(candidate.get("summary", ""), max_chars=180)
    lines: List[str] = [
        f"interaction.sop.topic={candidate.get('topic')}",
        f"interaction.sop.title={title or candidate.get('topic')}",
        f"interaction.sop.steps={step_text}",
    ]
    if summary:
        lines.append(f"interaction.sop.summary={summary}")
    applicability = _normalize_session_memory_text(candidate.get("applicability", ""), max_chars=120)
    if applicability:
        lines.append(f"interaction.sop.applicability={applicability}")
    avoid = _normalize_session_memory_text(candidate.get("avoid", ""), max_chars=120)
    if avoid:
        lines.append(f"interaction.sop.avoid={avoid}")
    agent_name = str(candidate.get("agent_name") or "").strip()
    if agent_name:
        lines.append(f"agent.identity.name={agent_name}")
    return "\n".join(lines)


def _build_agent_candidate_seed_facts(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    facts: List[Dict[str, Any]] = []
    confidence = _coerce_confidence(candidate.get("confidence"), default=0.72)
    importance = 0.78

    def _append_fact(key: str, value: Any, *, category: str) -> None:
        normalized_value = _normalize_session_memory_text(value, max_chars=260)
        if not key or not normalized_value:
            return
        facts.append(
            {
                "key": key,
                "value": normalized_value,
                "category": category,
                "confidence": confidence,
                "importance": importance,
                "source": "session_llm",
            }
        )

    _append_fact("interaction.sop.topic", candidate.get("topic"), category="interaction")
    _append_fact("interaction.sop.title", candidate.get("title"), category="interaction")
    steps = candidate.get("steps")
    if isinstance(steps, list):
        steps_value = " | ".join(
            _normalize_session_memory_text(step, max_chars=72) for step in steps if step
        )
        _append_fact("interaction.sop.steps", steps_value, category="interaction")
    _append_fact("interaction.sop.summary", candidate.get("summary"), category="interaction")
    _append_fact(
        "interaction.sop.applicability",
        candidate.get("applicability"),
        category="interaction",
    )
    _append_fact("interaction.sop.avoid", candidate.get("avoid"), category="interaction")
    _append_fact("agent.identity.name", candidate.get("agent_name"), category="agent")
    return facts


def _load_existing_user_preference_map(user_id: str) -> Dict[str, Dict[str, Any]]:
    """Load latest user preference memory per key for dedupe/upsert."""
    from memory_system.memory_interface import MemoryType
    from memory_system.memory_repository import get_memory_repository

    repo = get_memory_repository()
    rows = repo.list_memories(
        memory_type=MemoryType.USER_CONTEXT,
        user_id=str(user_id),
        limit=400,
    )

    latest_by_key: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        metadata = dict(row.metadata or {})
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type != _SESSION_MEMORY_USER_SIGNAL_TYPE:
            continue

        key = str(metadata.get("preference_key") or "").strip()
        value = str(metadata.get("preference_value") or "").strip()
        if (not key or not value) and row.content:
            parsed_key, parsed_value = _split_user_preference_content(str(row.content))
            key = key or str(parsed_key or "")
            value = value or str(parsed_value or "")
        if not key or not value:
            continue

        row_latest_ts = _parse_iso_datetime(metadata.get("latest_turn_ts")) or _parse_iso_datetime(
            row.timestamp
        )
        existing = latest_by_key.get(key)
        if existing:
            existing_ts = _parse_iso_datetime(existing.get("latest_turn_ts")) or _parse_iso_datetime(
                existing.get("timestamp")
            )
            if existing_ts and row_latest_ts and existing_ts >= row_latest_ts:
                continue

        latest_by_key[key] = {
            "memory_id": int(row.id),
            "value": value,
            "metadata": metadata,
            "latest_turn_ts": row_latest_ts.isoformat() if row_latest_ts else None,
            "timestamp": row.timestamp.isoformat() if row.timestamp else None,
        }

    return latest_by_key


def _upsert_existing_user_preference_metadata(
    memory_id: int,
    metadata: Dict[str, Any],
) -> None:
    from memory_system.memory_repository import get_memory_repository

    repo = get_memory_repository()
    repo.update_record(
        memory_id,
        metadata=metadata,
        mark_vector_pending=False,
    )


def _load_existing_agent_candidate_fingerprints(
    *,
    agent_id: str,
    user_id: str,
) -> set[str]:
    """Load known agent candidate fingerprints to avoid duplicate drafts."""
    from memory_system.memory_interface import MemoryType
    from memory_system.memory_repository import get_memory_repository

    repo = get_memory_repository()
    rows = repo.list_memories(
        memory_type=MemoryType.AGENT,
        agent_id=str(agent_id),
        user_id=str(user_id),
        limit=400,
    )

    fingerprints: set[str] = set()
    for row in rows:
        metadata = dict(row.metadata or {})
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type != _SESSION_MEMORY_AGENT_SIGNAL_TYPE:
            continue
        fingerprint = str(metadata.get("candidate_fingerprint") or "").strip()
        if fingerprint:
            fingerprints.add(fingerprint)

    return fingerprints


async def _flush_session_memories(
    session: "ConversationSession",
    reason: str,
) -> None:
    turns = session.drain_memory_turns()
    if not turns:
        return

    agent_name = ""
    for turn in reversed(turns):
        candidate = str(turn.get("agent_name") or "").strip()
        if candidate:
            agent_name = candidate
            break

    if not agent_name:
        try:
            registry = get_agent_registry()
            agent_info = registry.get_agent(session.agent_id)
            if agent_info:
                agent_name = agent_info.name or ""
        except Exception:
            agent_name = ""

    from agent_framework.agent_memory_interface import get_agent_memory_interface

    mem_interface = get_agent_memory_interface()
    turn_count = len(turns)
    extracted_signals, extracted_agent_candidates = await _extract_session_memory_signals_with_llm(
        turns=turns,
        agent_id=session.agent_id,
        agent_name=agent_name,
        session_id=session.session_id,
    )
    deduped_signals_by_key: Dict[str, Dict[str, Any]] = {}
    for signal in extracted_signals:
        signal_key = str(signal.get("key") or "").strip()
        signal_value = str(signal.get("value") or "").strip()
        if not signal_key or not signal_value:
            continue
        existing_signal = deduped_signals_by_key.get(signal_key)
        if not existing_signal:
            deduped_signals_by_key[signal_key] = signal
            continue

        current_score = (
            int(bool(signal.get("persistent"))),
            int(signal.get("evidence_count") or 0),
            str(signal.get("latest_ts") or ""),
        )
        existing_score = (
            int(bool(existing_signal.get("persistent"))),
            int(existing_signal.get("evidence_count") or 0),
            str(existing_signal.get("latest_ts") or ""),
        )
        if current_score >= existing_score:
            deduped_signals_by_key[signal_key] = signal
    extracted_signals = list(deduped_signals_by_key.values())
    if not extracted_signals and not extracted_agent_candidates:
        logger.info(
            "Skipped session memory persistence: no valuable memory signals extracted",
            extra={"session_id": session.session_id, "turn_count": turn_count},
        )
        return

    extracted_at = datetime.utcnow().isoformat() + "Z"
    metadata_base = {
        "source": "agent_test_preference_extractor",
        "session_id": session.session_id,
        "turn_count": turn_count,
        "session_end_reason": reason,
        "aggregated": True,
        "agent_name": agent_name,
        "extracted_at": extracted_at,
    }

    preference_metadata_base = {**metadata_base, "source": "agent_test_preference_extractor"}
    agent_candidate_metadata_base = {
        **metadata_base,
        "source": "agent_test_agent_candidate_extractor",
    }

    try:
        existing_preference_map = _load_existing_user_preference_map(str(session.user_id))
    except Exception as e:
        logger.warning(
            "Failed to load existing user preference memories before upsert",
            extra={"session_id": session.session_id, "error": str(e)},
        )
        existing_preference_map = {}

    preference_created = 0
    preference_updated = 0
    preference_skipped = 0
    for signal in extracted_signals:
        try:
            signal_key = str(signal.get("key") or "").strip()
            signal_value = str(signal.get("value") or "").strip()
            if not signal_key or not signal_value:
                preference_skipped += 1
                continue

            existing = existing_preference_map.get(signal_key)
            if existing and str(existing.get("value") or "").strip() == signal_value:
                memory_id = existing.get("memory_id")
                if memory_id:
                    existing_meta = dict(existing.get("metadata") or {})
                    existing_meta.update(
                        {
                            "evidence_count": max(
                                int(existing_meta.get("evidence_count") or 0),
                                int(signal.get("evidence_count") or 0),
                            ),
                            "confidence": max(
                                float(existing_meta.get("confidence") or 0.0),
                                float(signal.get("confidence") or 0.0),
                            ),
                            "latest_turn_ts": signal.get("latest_ts")
                            or existing_meta.get("latest_turn_ts"),
                            "updated_at_extracted": extracted_at,
                            "is_active": True,
                            "strong_signal": bool(
                                signal.get("strong_signal") or existing_meta.get("strong_signal")
                            ),
                            "explicit_source": bool(
                                signal.get("explicit_source") or existing_meta.get("explicit_source")
                            ),
                        }
                    )
                    _upsert_existing_user_preference_metadata(int(memory_id), existing_meta)
                    preference_updated += 1
                    continue
                preference_skipped += 1
                continue

            if existing and str(existing.get("value") or "").strip() != signal_value:
                memory_id = existing.get("memory_id")
                previous_value = str(existing.get("value") or "").strip()
                if memory_id:
                    old_meta = dict(existing.get("metadata") or {})
                    old_meta.update(
                        {
                            "is_active": False,
                            "superseded_at": extracted_at,
                            "superseded_by_value": signal_value,
                        }
                    )
                    delete_applied = False
                    if previous_value:
                        delete_seed_facts = old_meta.get("facts", [])
                        if not isinstance(delete_seed_facts, list) or not delete_seed_facts:
                            delete_seed_facts = _build_user_preference_seed_facts(
                                {
                                    "key": signal_key,
                                    "value": previous_value,
                                    "persistent": bool(old_meta.get("strong_signal")),
                                    "confidence": max(
                                        _coerce_confidence(old_meta.get("confidence"), default=0.0),
                                        _coerce_confidence(signal.get("confidence"), default=0.0),
                                    ),
                                }
                            )

                        delete_result = mem_interface.store_user_context(
                            user_id=session.user_id,
                            agent_id=session.agent_id,
                            content=f"user.preference.{signal_key}={previous_value}",
                            metadata={
                                **preference_metadata_base,
                                "signal_type": _SESSION_MEMORY_USER_SIGNAL_TYPE,
                                "preference_key": signal_key,
                                "preference_value": previous_value,
                                "evidence_count": max(
                                    int(old_meta.get("evidence_count") or 0),
                                    int(signal.get("evidence_count") or 0),
                                ),
                                "confidence": max(
                                    _coerce_confidence(old_meta.get("confidence"), default=0.0),
                                    _coerce_confidence(signal.get("confidence"), default=0.0),
                                ),
                                "reason": "superseded_by_new_value",
                                "latest_turn_ts": signal.get("latest_ts")
                                or old_meta.get("latest_turn_ts"),
                                "strong_signal": bool(
                                    signal.get("strong_signal") or old_meta.get("strong_signal")
                                ),
                                "explicit_source": bool(
                                    signal.get("explicit_source") or old_meta.get("explicit_source")
                                ),
                                "is_active": False,
                                "superseded_at": extracted_at,
                                "superseded_by_value": signal_value,
                                "memory_action": "DELETE",
                                "target_memory_id": int(memory_id),
                                "skip_secondary_fact_extraction": True,
                                "facts": delete_seed_facts,
                            },
                        )
                        delete_applied = bool(delete_result)

                    if not delete_applied:
                        _upsert_existing_user_preference_metadata(int(memory_id), old_meta)

            mem_interface.store_user_context(
                user_id=session.user_id,
                agent_id=session.agent_id,
                content=_build_user_preference_memory_content(signal),
                metadata={
                    **preference_metadata_base,
                    "signal_type": _SESSION_MEMORY_USER_SIGNAL_TYPE,
                    "preference_key": signal_key,
                    "preference_value": signal_value,
                    "evidence_count": signal["evidence_count"],
                    "confidence": signal["confidence"],
                    "reason": signal.get("reason"),
                    "latest_turn_ts": signal.get("latest_ts"),
                    "strong_signal": bool(signal.get("strong_signal")),
                    "explicit_source": bool(signal.get("explicit_source")),
                    "is_active": True,
                    "skip_secondary_fact_extraction": True,
                    "facts": _build_user_preference_seed_facts(signal),
                },
            )
            existing_preference_map[signal_key] = {
                "memory_id": None,
                "value": signal_value,
                "metadata": {
                    "signal_type": _SESSION_MEMORY_USER_SIGNAL_TYPE,
                    "preference_key": signal_key,
                    "preference_value": signal_value,
                    "latest_turn_ts": signal.get("latest_ts"),
                    "strong_signal": bool(signal.get("strong_signal")),
                    "explicit_source": bool(signal.get("explicit_source")),
                    "is_active": True,
                },
            }
            preference_created += 1
        except Exception as e:
            logger.warning(
                "Failed to store extracted user preference memory on session end",
                extra={
                    "session_id": session.session_id,
                    "reason": reason,
                    "error": str(e),
                    "preference_key": signal.get("key"),
                },
            )

    try:
        existing_candidate_fingerprints = _load_existing_agent_candidate_fingerprints(
            agent_id=str(session.agent_id),
            user_id=str(session.user_id),
        )
    except Exception as e:
        logger.warning(
            "Failed to load existing agent candidate fingerprints",
            extra={"session_id": session.session_id, "error": str(e)},
        )
        existing_candidate_fingerprints = set()
    candidate_created = 0
    candidate_skipped = 0
    for candidate in extracted_agent_candidates:
        fingerprint = str(candidate.get("fingerprint") or "").strip()
        if not fingerprint:
            candidate_skipped += 1
            continue
        if fingerprint in existing_candidate_fingerprints:
            candidate_skipped += 1
            continue

        try:
            mem_interface.store_agent_memory(
                agent_id=session.agent_id,
                user_id=session.user_id,
                content=_build_agent_candidate_content(candidate),
                metadata={
                    **agent_candidate_metadata_base,
                    "signal_type": _SESSION_MEMORY_AGENT_SIGNAL_TYPE,
                    "candidate_type": candidate.get("candidate_type") or "sop",
                    "candidate_title": candidate.get("title"),
                    "candidate_summary": candidate.get("summary"),
                    "candidate_applicability": candidate.get("applicability"),
                    "candidate_avoid": candidate.get("avoid"),
                    "candidate_fingerprint": fingerprint,
                    "review_status": _SESSION_MEMORY_AGENT_REVIEW_PENDING,
                    "review_required": True,
                    "inject_policy": "only_published",
                    "confidence": candidate.get("confidence"),
                    "latest_turn_ts": candidate.get("latest_ts"),
                    "is_active": True,
                    "skip_secondary_fact_extraction": True,
                    "facts": _build_agent_candidate_seed_facts(candidate),
                },
            )
            existing_candidate_fingerprints.add(fingerprint)
            candidate_created += 1
        except Exception as e:
            logger.warning(
                "Failed to store extracted agent memory candidate on session end",
                extra={
                    "session_id": session.session_id,
                    "reason": reason,
                    "error": str(e),
                    "candidate_type": candidate.get("candidate_type"),
                },
            )

    logger.info(
        "Stored extracted session memories",
        extra={
            "session_id": session.session_id,
            "reason": reason,
            "preference_created": preference_created,
            "preference_updated": preference_updated,
            "preference_skipped": preference_skipped,
            "preference_candidates": len(extracted_signals),
            "agent_candidate_created": candidate_created,
            "agent_candidate_skipped": candidate_skipped,
            "agent_candidate_candidates": len(extracted_agent_candidates),
        },
    )


def _ensure_session_memory_callback_registered() -> None:
    global _SESSION_MEMORY_CALLBACK_REGISTERED
    if _SESSION_MEMORY_CALLBACK_REGISTERED:
        return

    from agent_framework.session_manager import get_session_manager

    session_mgr = get_session_manager()
    session_mgr.register_session_end_callback(_flush_session_memories)
    _SESSION_MEMORY_CALLBACK_REGISTERED = True


# Agent cache with TTL (Time To Live) and memory-aware sizing
class AgentCacheEntry:
    """Cache entry for an initialized agent with TTL."""

    def __init__(self, agent, llm, ttl_minutes: int = 30):
        self.agent = agent
        self.llm = llm
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.ttl = timedelta(minutes=ttl_minutes)
        self.access_count = 0

    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return datetime.now() - self.last_used > self.ttl

    def touch(self):
        """Update last used timestamp and increment access count."""
        self.last_used = datetime.now()
        self.access_count += 1


# Global cache for initialized agents (cache_key -> CacheEntry)
_agent_cache: Dict[str, AgentCacheEntry] = {}
_AGENT_CACHE_KEY_VERSION = "v2"


def _build_agent_cache_key(
    agent_id: str,
    provider: Optional[str],
    model: Optional[str],
    capabilities: Optional[List[str]],
) -> str:
    """Build a stable cache key for initialized agent instances."""
    capabilities_hash = hash(tuple(sorted(capabilities or [])))
    provider_key = provider or ""
    model_key = model or ""
    return f"{_AGENT_CACHE_KEY_VERSION}_{agent_id}_{provider_key}_{model_key}_{capabilities_hash}"


def get_dynamic_cache_limit() -> int:
    """
    Calculate dynamic cache limit based on available system memory.

    Returns:
        int: Maximum number of agents to cache
    """
    try:
        # Get system memory info
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)  # Convert to GB

        # Conservative estimate: each cached agent uses ~50-100MB
        # Allow caching if we have at least 2GB available
        if available_gb < 2:
            return 10  # Minimal caching
        elif available_gb < 4:
            return 20
        elif available_gb < 8:
            return 30
        elif available_gb < 16:
            return 50
        else:
            return 100  # Maximum caching for systems with plenty of RAM

    except Exception as e:
        logger.warning(f"Failed to get system memory info: {e}, using default limit")
        return 30  # Safe default


def get_cache_stats() -> dict:
    """Get current cache statistics."""
    total_entries = len(_agent_cache)
    expired_entries = sum(1 for entry in _agent_cache.values() if entry.is_expired())

    # Calculate memory usage estimate
    memory_estimate_mb = total_entries * 75  # Rough estimate: 75MB per agent

    # Get system memory
    try:
        memory = psutil.virtual_memory()
        available_gb = memory.available / (1024**3)
        total_gb = memory.total / (1024**3)
        used_percent = memory.percent
    except:
        available_gb = 0
        total_gb = 0
        used_percent = 0

    return {
        "total_entries": total_entries,
        "expired_entries": expired_entries,
        "active_entries": total_entries - expired_entries,
        "memory_estimate_mb": memory_estimate_mb,
        "cache_limit": get_dynamic_cache_limit(),
        "system_memory_available_gb": round(available_gb, 2),
        "system_memory_total_gb": round(total_gb, 2),
        "system_memory_used_percent": round(used_percent, 1),
    }


def clear_agent_cache():
    """Clear the agent cache. Useful after code changes."""
    global _agent_cache
    stats = get_cache_stats()
    _agent_cache.clear()
    logger.info(f"Agent cache cleared: {stats['total_entries']} entries removed")


def cleanup_expired_cache():
    """Remove expired entries from cache and enforce memory limits."""
    global _agent_cache

    # Remove expired entries
    expired_keys = [key for key, entry in _agent_cache.items() if entry.is_expired()]
    for key in expired_keys:
        del _agent_cache[key]
        logger.debug(f"Removed expired cache entry: {key}")

    # Get dynamic cache limit based on available memory
    cache_limit = get_dynamic_cache_limit()

    # If cache is still too large, remove least recently used entries
    if len(_agent_cache) > cache_limit:
        # Sort by last_used time (oldest first)
        sorted_entries = sorted(_agent_cache.items(), key=lambda x: x[1].last_used)
        to_remove = len(_agent_cache) - cache_limit

        for key, entry in sorted_entries[:to_remove]:
            del _agent_cache[key]
            logger.info(
                f"Removed LRU cache entry: {key} "
                f"(last used: {entry.last_used}, access count: {entry.access_count})"
            )

        logger.info(
            f"Cache size reduced from {len(_agent_cache) + to_remove} to {len(_agent_cache)} "
            f"(limit: {cache_limit}, available memory: {get_cache_stats()['system_memory_available_gb']}GB)"
        )


def _get_cached_agent_status_value(agent: Any) -> str:
    """Return normalized status for a cached agent instance."""
    try:
        raw_status = (
            agent.get_status() if hasattr(agent, "get_status") else getattr(agent, "status", None)
        )
    except Exception as status_error:
        logger.warning(f"Failed to inspect cached agent status: {status_error}")
        return "unknown"

    if raw_status is None:
        return "unknown"

    status_value = getattr(raw_status, "value", raw_status)
    normalized = str(status_value).strip().lower()
    return normalized or "unknown"


def get_cached_agent(cache_key: str):
    """Get agent from cache if exists and not expired."""
    cleanup_expired_cache()  # Clean up on every access

    if cache_key in _agent_cache:
        entry = _agent_cache[cache_key]
        if not entry.is_expired():
            status_value = _get_cached_agent_status_value(entry.agent)
            if status_value != "active":
                del _agent_cache[cache_key]
                logger.warning(
                    "Evicted non-active cached agent before reuse",
                    extra={"cache_key": cache_key, "agent_status": status_value},
                )
                return None, None
            entry.touch()  # Update last used time and access count
            logger.debug(
                f"Cache hit: {cache_key} "
                f"(access count: {entry.access_count}, age: {(datetime.now() - entry.created_at).seconds}s)"
            )
            return entry.agent, entry.llm
        else:
            # Remove expired entry
            del _agent_cache[cache_key]
            logger.debug(f"Cache expired: {cache_key}")

    logger.debug(f"Cache miss: {cache_key}")
    return None, None


def cache_agent(cache_key: str, agent, llm, ttl_minutes: int = 30):
    """Cache an initialized agent with TTL."""
    global _agent_cache
    cleanup_expired_cache()  # Clean up before adding

    _agent_cache[cache_key] = AgentCacheEntry(agent, llm, ttl_minutes)

    stats = get_cache_stats()
    logger.info(
        f"Cached agent: {cache_key} "
        f"(TTL: {ttl_minutes}min, cache size: {stats['total_entries']}/{stats['cache_limit']}, "
        f"memory estimate: {stats['memory_estimate_mb']}MB, "
        f"available: {stats['system_memory_available_gb']}GB)"
    )


def invalidate_agent_cache(agent_id: str):
    """
    Invalidate all cache entries for a specific agent.

    This removes all cached versions of an agent (different provider/model/capabilities combinations).
    """
    global _agent_cache
    cache_keys_to_remove = [
        key
        for key in _agent_cache.keys()
        if key.startswith(f"{agent_id}_")
        or key.startswith(f"{_AGENT_CACHE_KEY_VERSION}_{agent_id}_")
    ]

    for key in cache_keys_to_remove:
        entry = _agent_cache[key]
        del _agent_cache[key]
        logger.info(
            f"Invalidated cache: {key} "
            f"(age: {(datetime.now() - entry.created_at).seconds}s, access count: {entry.access_count})"
        )

    return len(cache_keys_to_remove)


class CreateAgentRequest(BaseModel):
    """Create agent request."""

    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., min_length=1, max_length=100)  # template type
    template_id: Optional[str] = None
    avatar: Optional[str] = None
    systemPrompt: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    maxTokens: Optional[int] = Field(default=2000, ge=1, le=8000)
    topP: Optional[float] = Field(default=0.9, ge=0.0, le=1.0)
    accessLevel: Optional[str] = Field(default="private")
    allowedKnowledge: List[str] = Field(default_factory=list)
    allowedMemory: List[str] = Field(default_factory=list)


class UpdateAgentRequest(BaseModel):
    """Update agent request."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    avatar: Optional[str] = None
    systemPrompt: Optional[str] = None
    skills: Optional[List[str]] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    maxTokens: Optional[int] = Field(None, ge=1, le=8000)
    topP: Optional[float] = Field(None, ge=0.0, le=1.0)
    accessLevel: Optional[str] = None
    allowedKnowledge: Optional[List[str]] = None
    allowedMemory: Optional[List[str]] = None
    # Retrieval Configuration
    topK: Optional[int] = Field(None, ge=1, le=20)
    similarityThreshold: Optional[float] = Field(None, ge=0.0, le=1.0)
    # Department
    department_id: Optional[str] = None


class AgentResponse(BaseModel):
    """Agent response model."""

    id: str
    name: str
    type: str
    avatar: Optional[str] = None
    status: str
    currentTask: Optional[str] = None
    tasksExecuted: int = 0
    tasksCompleted: int = 0
    tasksFailed: int = 0
    completionRate: float = 0.0
    uptime: str = "0h 0m"
    systemPrompt: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    model: Optional[str] = None
    provider: Optional[str] = None
    temperature: float = 0.7
    maxTokens: int = 2000
    topP: float = 0.9
    accessLevel: str = "private"
    allowedKnowledge: List[str] = Field(default_factory=list)
    allowedMemory: List[str] = Field(default_factory=list)
    # Retrieval Configuration
    topK: Optional[int] = None
    similarityThreshold: Optional[float] = None
    departmentId: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class AgentLogEntryResponse(BaseModel):
    """Agent detail activity log entry."""

    timestamp: datetime
    level: str = "INFO"
    message: str
    source: str = "task"


class AgentMetricsResponse(BaseModel):
    """Agent detail metrics payload."""

    tasksExecuted: int = 0
    tasksCompleted: int = 0
    tasksFailed: int = 0
    completionRate: float = 0.0
    successRate: float = 0.0
    failureRate: float = 0.0
    pendingTasks: int = 0
    inProgressTasks: int = 0
    lastActivityAt: Optional[datetime] = None


def _get_owned_agent_or_raise(agent_id: str, current_user: CurrentUser):
    """Resolve one agent and enforce owner-only access."""
    try:
        agent_uuid = UUID(agent_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent id: {agent_id}",
        ) from exc

    registry = get_agent_registry()
    agent = registry.get_agent(agent_uuid)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    if str(agent.owner_user_id) != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this agent",
        )

    return agent, agent_uuid


def _public_agent_skills(agent_type: str, capabilities: Optional[List[str]]) -> List[str]:
    """Normalize capabilities for API responses.

    Temporary mission workers may carry internal capabilities that are not platform skills.
    Hide them from the workforce skills UI to avoid misleading counts/configuration state.
    """
    if agent_type == "mission_temp_worker":
        return []
    return capabilities or []


class AvailableProvidersResponse(BaseModel):
    """Available LLM providers and models for agent configuration."""

    providers: Dict[str, List[str]]  # provider_name -> list of model names


@router.get("/available-providers", response_model=AvailableProvidersResponse)
async def get_available_providers(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get available LLM providers and their models for agent configuration.

    Returns only enabled providers from database with their available models.
    This endpoint is used by the agent configuration UI to populate provider/model dropdowns.
    """
    try:
        from database.connection import get_db_session
        from llm_providers.db_manager import ProviderDBManager

        providers_dict = {}

        # Get providers directly from database
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            db_providers = db_manager.list_providers()

            logger.info(f"[AVAILABLE-PROVIDERS] Found {len(db_providers)} providers in database")

            for p in db_providers:
                logger.info(
                    f"[AVAILABLE-PROVIDERS] Provider: {p.name}, enabled={p.enabled}, models={len(p.models) if p.models else 0}"
                )
                # Only include enabled providers with models
                if p.enabled and p.models:
                    providers_dict[p.name] = p.models

        logger.info(
            f"[AVAILABLE-PROVIDERS] Returning {len(providers_dict)} providers: {list(providers_dict.keys())}"
        )
        return AvailableProvidersResponse(providers=providers_dict)

    except Exception as e:
        logger.error(f"Failed to get available providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available providers: {str(e)}",
        )


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    request: CreateAgentRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """Create a new agent."""
    try:
        registry = get_agent_registry()
        validated_allowed_knowledge = _validate_allowed_knowledge(
            request.allowedKnowledge or [],
            current_user,
        )
        validated_allowed_memory = _validate_allowed_memory(request.allowedMemory or [])

        # Register agent in database with LLM configuration
        agent_info = registry.register_agent(
            name=request.name,
            agent_type=request.type,
            owner_user_id=UUID(current_user.user_id),
            capabilities=request.skills or [],
            llm_provider=request.provider,
            llm_model=request.model,
            system_prompt=request.systemPrompt,
            temperature=request.temperature or 0.7,
            max_tokens=request.maxTokens or 2000,
            top_p=request.topP or 0.9,
            access_level=request.accessLevel or "private",
            allowed_knowledge=validated_allowed_knowledge,
            allowed_memory=validated_allowed_memory or [],
        )

        # Update status to idle after creation
        agent_info = registry.update_agent(
            agent_id=agent_info.agent_id,
            status="idle",
        )

        logger.info(
            f"Agent created: {agent_info.name}",
            extra={"agent_id": str(agent_info.agent_id), "user_id": current_user.user_id},
        )

        return AgentResponse(
            id=str(agent_info.agent_id),
            name=agent_info.name,
            type=agent_info.agent_type,
            avatar=_resolve_agent_avatar(agent_info.avatar),
            status=agent_info.status,
            currentTask=None,
            tasksExecuted=0,
            tasksCompleted=0,
            tasksFailed=0,
            completionRate=0.0,
            uptime="0h 0m",
            systemPrompt=agent_info.system_prompt,
            skills=_public_agent_skills(agent_info.agent_type, agent_info.capabilities),
            model=agent_info.llm_model,
            provider=agent_info.llm_provider,
            temperature=agent_info.temperature,
            maxTokens=agent_info.max_tokens,
            topP=agent_info.top_p,
            accessLevel=agent_info.access_level,
            allowedKnowledge=agent_info.allowed_knowledge,
            allowedMemory=agent_info.allowed_memory,
            topK=agent_info.top_k,
            similarityThreshold=agent_info.similarity_threshold,
            departmentId=str(agent_info.department_id) if agent_info.department_id else None,
            createdAt=agent_info.created_at,
            updatedAt=agent_info.updated_at,
        )
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}",
        )


@router.get("", response_model=List[AgentResponse])
async def list_agents(current_user: CurrentUser = Depends(get_current_user)):
    """List user's agents."""
    try:
        registry = get_agent_registry()

        # Get agents for current user
        agents = registry.list_agents(owner_user_id=UUID(current_user.user_id))
        task_stats_by_agent = _collect_agent_task_stats([agent.agent_id for agent in agents])

        responses: List[AgentResponse] = []
        for agent in agents:
            task_stats = task_stats_by_agent.get(agent.agent_id, _default_agent_task_stats())
            responses.append(
                AgentResponse(
                    id=str(agent.agent_id),
                    name=agent.name,
                    type=agent.agent_type,
                    avatar=_resolve_agent_avatar(agent.avatar),
                    status=agent.status,
                    currentTask=None,  # TODO: Get from task manager
                    tasksExecuted=task_stats["tasksExecuted"],
                    tasksCompleted=task_stats["tasksCompleted"],
                    tasksFailed=task_stats["tasksFailed"],
                    completionRate=task_stats["completionRate"],
                    uptime="0h 0m",  # Deprecated in UI but kept for compatibility
                    systemPrompt=agent.system_prompt,
                    skills=_public_agent_skills(agent.agent_type, agent.capabilities),
                    model=agent.llm_model,
                    provider=agent.llm_provider,
                    temperature=agent.temperature,
                    maxTokens=agent.max_tokens,
                    topP=agent.top_p,
                    accessLevel=agent.access_level,
                    allowedKnowledge=agent.allowed_knowledge,
                    allowedMemory=agent.allowed_memory,
                    topK=agent.top_k,
                    similarityThreshold=agent.similarity_threshold,
                    departmentId=str(agent.department_id) if agent.department_id else None,
                    createdAt=agent.created_at,
                    updatedAt=agent.updated_at,
                )
            )

        return responses

    except Exception as e:
        logger.error(f"Failed to list agents: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get agent details."""
    try:
        agent, _ = _get_owned_agent_or_raise(agent_id, current_user)

        task_stats = _collect_agent_task_stats([agent.agent_id]).get(
            agent.agent_id, _default_agent_task_stats()
        )

        return AgentResponse(
            id=str(agent.agent_id),
            name=agent.name,
            type=agent.agent_type,
            avatar=_resolve_agent_avatar(agent.avatar),
            status=agent.status,
            currentTask=None,
            tasksExecuted=task_stats["tasksExecuted"],
            tasksCompleted=task_stats["tasksCompleted"],
            tasksFailed=task_stats["tasksFailed"],
            completionRate=task_stats["completionRate"],
            uptime="0h 0m",
            systemPrompt=agent.system_prompt,
            skills=_public_agent_skills(agent.agent_type, agent.capabilities),
            model=agent.llm_model,
            provider=agent.llm_provider,
            temperature=agent.temperature,
            maxTokens=agent.max_tokens,
            topP=agent.top_p,
            accessLevel=agent.access_level,
            allowedKnowledge=agent.allowed_knowledge,
            allowedMemory=agent.allowed_memory,
            topK=agent.top_k,
            similarityThreshold=agent.similarity_threshold,
            departmentId=str(agent.department_id) if agent.department_id else None,
            createdAt=agent.created_at,
            updatedAt=agent.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent: {str(e)}",
        )


@router.get("/{agent_id}/metrics", response_model=AgentMetricsResponse)
async def get_agent_metrics(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get aggregate metrics for one agent detail page."""
    try:
        _, agent_uuid = _get_owned_agent_or_raise(agent_id, current_user)

        from database.connection import get_db_session
        from database.models import Task
        from sqlalchemy import func

        with get_db_session() as session:
            task_status_rows = (
                session.query(Task.status, func.count(Task.task_id))
                .filter(Task.assigned_agent_id == agent_uuid)
                .filter(_mission_bound_tasks_only(Task))
                .group_by(Task.status)
                .all()
            )
            last_activity_at = (
                session.query(func.max(func.coalesce(Task.completed_at, Task.created_at)))
                .filter(Task.assigned_agent_id == agent_uuid)
                .filter(_mission_bound_tasks_only(Task))
                .scalar()
            )

        return AgentMetricsResponse(
            **_build_agent_metrics_from_task_rows(
                task_status_rows=task_status_rows,
                last_activity_at=last_activity_at,
            )
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get metrics for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent metrics: {str(e)}",
        )


@router.get("/{agent_id}/logs", response_model=List[AgentLogEntryResponse])
async def get_agent_logs(
    agent_id: str,
    limit: int = Query(100, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get recent task/audit logs for one agent detail page."""
    try:
        _, agent_uuid = _get_owned_agent_or_raise(agent_id, current_user)

        from database.connection import get_db_session
        from database.models import AuditLog, Task
        from sqlalchemy import and_, func, or_

        with get_db_session() as session:
            task_rows = (
                session.query(Task.goal_text, Task.status, Task.created_at, Task.completed_at)
                .filter(Task.assigned_agent_id == agent_uuid)
                .filter(_mission_bound_tasks_only(Task))
                .order_by(func.coalesce(Task.completed_at, Task.created_at).desc())
                .limit(limit)
                .all()
            )

            audit_rows = (
                session.query(AuditLog.action, AuditLog.details, AuditLog.timestamp)
                .filter(
                    or_(
                        AuditLog.agent_id == agent_uuid,
                        and_(
                            AuditLog.resource_type == "agent",
                            AuditLog.resource_id == agent_uuid,
                        ),
                    )
                )
                .order_by(AuditLog.timestamp.desc())
                .limit(limit)
                .all()
            )

        entries = _build_task_log_entries(task_rows) + _build_audit_log_entries(audit_rows)
        entries.sort(key=lambda item: item["timestamp"], reverse=True)
        return [AgentLogEntryResponse(**item) for item in entries[:limit]]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get logs for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent logs: {str(e)}",
        )


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    request: UpdateAgentRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update agent configuration."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this agent",
            )

        # Update agent with all configuration fields
        validated_allowed_knowledge = (
            _validate_allowed_knowledge(request.allowedKnowledge, current_user)
            if request.allowedKnowledge is not None
            else None
        )
        validated_allowed_memory = _validate_allowed_memory(request.allowedMemory)
        updated_agent = registry.update_agent(
            agent_id=UUID(agent_id),
            name=request.name,
            avatar=request.avatar,
            capabilities=request.skills,
            llm_provider=request.provider,
            llm_model=request.model,
            system_prompt=request.systemPrompt,
            temperature=request.temperature,
            max_tokens=request.maxTokens,
            top_p=request.topP,
            access_level=request.accessLevel,
            allowed_knowledge=validated_allowed_knowledge,
            allowed_memory=validated_allowed_memory,
            top_k=request.topK,
            similarity_threshold=request.similarityThreshold,
            department_id=request.department_id,
        )

        if not updated_agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Invalidate cache for this agent (all provider/model combinations)
        invalidated_count = invalidate_agent_cache(agent_id)

        logger.info(
            f"Agent updated: {updated_agent.name} (invalidated {invalidated_count} cache entries)",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )

        task_stats = _collect_agent_task_stats([updated_agent.agent_id]).get(
            updated_agent.agent_id, _default_agent_task_stats()
        )

        return AgentResponse(
            id=str(updated_agent.agent_id),
            name=updated_agent.name,
            type=updated_agent.agent_type,
            avatar=_resolve_agent_avatar(updated_agent.avatar),
            status=updated_agent.status,
            currentTask=None,
            tasksExecuted=task_stats["tasksExecuted"],
            tasksCompleted=task_stats["tasksCompleted"],
            tasksFailed=task_stats["tasksFailed"],
            completionRate=task_stats["completionRate"],
            uptime="0h 0m",
            systemPrompt=updated_agent.system_prompt,
            skills=_public_agent_skills(updated_agent.agent_type, updated_agent.capabilities),
            model=updated_agent.llm_model,
            provider=updated_agent.llm_provider,
            temperature=updated_agent.temperature,
            maxTokens=updated_agent.max_tokens,
            topP=updated_agent.top_p,
            accessLevel=updated_agent.access_level,
            allowedKnowledge=updated_agent.allowed_knowledge,
            allowedMemory=updated_agent.allowed_memory,
            topK=updated_agent.top_k,
            similarityThreshold=updated_agent.similarity_threshold,
            departmentId=str(updated_agent.department_id) if updated_agent.department_id else None,
            createdAt=updated_agent.created_at,
            updatedAt=updated_agent.updated_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent: {str(e)}",
        )


@router.post("/{agent_id}/avatar", response_model=Dict[str, str])
async def upload_agent_avatar(
    agent_id: str,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Upload agent avatar image.

    Accepts image files (JPEG, PNG, WebP) and stores them in MinIO.
    Returns the avatar URL.
    """
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this agent",
            )

        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "image/webp"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
            )

        # Read file data
        file_data = await file.read()
        file_stream = io.BytesIO(file_data)

        # Upload to MinIO
        minio_client = get_minio_client()

        # Prepare metadata - only include ASCII-safe values
        upload_metadata = {
            "agent_id": agent_id,
            "type": "agent_avatar",
        }

        # Only add agent_name if it's ASCII-safe
        try:
            agent.name.encode("ascii")
            upload_metadata["agent_name"] = agent.name
        except UnicodeEncodeError:
            # Skip non-ASCII agent names in metadata
            logger.debug(f"Skipping non-ASCII agent name in metadata: {agent.name}")

        bucket_name, object_key = minio_client.upload_file(
            bucket_type="images",
            file_data=file_stream,
            filename=f"avatar_{agent_id}.webp",
            user_id=current_user.user_id,
            task_id=None,
            agent_id=agent_id,
            content_type=file.content_type,
            metadata=upload_metadata,
        )

        # Store avatar reference (not presigned URL) for on-demand URL generation
        avatar_ref = minio_client.create_avatar_reference(bucket_name, object_key)

        # Generate presigned URL for immediate response (valid for 7 days)
        from datetime import timedelta

        avatar_url = minio_client.get_presigned_url(
            bucket_name=bucket_name, object_key=object_key, expires=timedelta(days=7)
        )

        # Update agent with avatar reference (store ref, not URL)
        updated_agent = registry.update_agent(
            agent_id=UUID(agent_id),
            avatar=avatar_ref,
        )

        logger.info(
            f"Avatar uploaded for agent: {agent.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id, "object_key": object_key},
        )

        return {
            "avatar_url": avatar_url,
            "avatar_ref": avatar_ref,
            "bucket": bucket_name,
            "key": object_key,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload avatar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar: {str(e)}",
        )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Delete an agent."""
    try:
        registry = get_agent_registry()
        agent = registry.get_agent(UUID(agent_id))

        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to delete this agent",
            )

        # Delete agent
        deleted = registry.delete_agent(UUID(agent_id))

        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Invalidate cache for this agent
        invalidated_count = invalidate_agent_cache(agent_id)

        logger.info(
            f"Agent deleted: {agent_id} (invalidated {invalidated_count} cache entries)",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete agent: {str(e)}",
        )


@router.post("/cache/clear", status_code=status.HTTP_200_OK)
async def clear_cache(current_user: CurrentUser = Depends(get_current_user)):
    """
    Clear the agent cache. Useful for debugging or after code changes.

    This will force all agents to be reinitialized on next use.
    """
    try:
        stats_before = get_cache_stats()
        clear_agent_cache()
        stats_after = get_cache_stats()

        logger.info(
            f"Agent cache cleared by user",
            extra={
                "user_id": current_user.user_id,
                "entries_cleared": stats_before["total_entries"],
                "memory_freed_mb": stats_before["memory_estimate_mb"],
            },
        )

        return {
            "message": "Agent cache cleared successfully",
            "entries_cleared": stats_before["total_entries"],
            "memory_freed_mb": stats_before["memory_estimate_mb"],
            "stats_before": stats_before,
            "stats_after": stats_after,
        }

    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}",
        )


@router.get("/cache/stats", status_code=status.HTTP_200_OK)
async def get_cache_statistics(current_user: CurrentUser = Depends(get_current_user)):
    """
    Get current agent cache statistics.

    Returns information about:
    - Number of cached agents
    - Memory usage estimates
    - System memory availability
    - Cache limits
    """
    try:
        stats = get_cache_stats()

        # Add detailed cache entries info
        cache_entries = []
        for key, entry in _agent_cache.items():
            age_seconds = (datetime.now() - entry.created_at).total_seconds()
            idle_seconds = (datetime.now() - entry.last_used).total_seconds()

            cache_entries.append(
                {
                    "key": key,
                    "age_seconds": int(age_seconds),
                    "idle_seconds": int(idle_seconds),
                    "access_count": entry.access_count,
                    "is_expired": entry.is_expired(),
                    "ttl_minutes": int(entry.ttl.total_seconds() / 60),
                }
            )

        # Sort by access count (most used first)
        cache_entries.sort(key=lambda x: x["access_count"], reverse=True)

        return {
            "summary": stats,
            "entries": cache_entries,
            "recommendations": _get_cache_recommendations(stats),
        }

    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache stats: {str(e)}",
        )


def _get_cache_recommendations(stats: dict) -> list:
    """Generate recommendations based on cache statistics."""
    recommendations = []

    # Check memory pressure
    if stats["system_memory_used_percent"] > 90:
        recommendations.append(
            {
                "level": "warning",
                "message": "System memory usage is high (>90%). Consider clearing cache or reducing cache limit.",
            }
        )

    # Check cache utilization
    utilization = stats["active_entries"] / stats["cache_limit"] if stats["cache_limit"] > 0 else 0
    if utilization > 0.9:
        recommendations.append(
            {
                "level": "info",
                "message": f"Cache is {int(utilization * 100)}% full. Old entries will be evicted automatically.",
            }
        )

    # Check expired entries
    if stats["expired_entries"] > stats["active_entries"] * 0.3:
        recommendations.append(
            {
                "level": "info",
                "message": f"{stats['expired_entries']} expired entries detected. They will be cleaned up automatically.",
            }
        )

    # Check available memory
    if stats["system_memory_available_gb"] < 2:
        recommendations.append(
            {
                "level": "warning",
                "message": "Low system memory (<2GB available). Cache limit has been reduced automatically.",
            }
        )

    if not recommendations:
        recommendations.append({"level": "success", "message": "Cache is operating normally."})

    return recommendations


@router.post("/cache/clear", status_code=status.HTTP_200_OK)
async def clear_cache(current_user: CurrentUser = Depends(get_current_user)):
    """Clear the agent cache. Useful after code changes or for troubleshooting."""
    clear_agent_cache()
    return {"message": "Agent cache cleared successfully", "cached_agents": 0}


_GENERIC_CONTENT_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
_ATTACHMENT_MAX_CHARS_PER_FILE = 6000
_ATTACHMENT_MAX_CHARS_TOTAL = 12000
_ATTACHMENT_MAX_TEXT_BYTES = 2 * 1024 * 1024
_ATTACHMENT_WORKSPACE_DIR = "input"
_ATTACHMENT_DEFAULT_FILENAME = "attachment.bin"
_SPEECH_INPUT_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024
_SPEECH_INPUT_AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".flac",
    ".webm",
    ".ogg",
    ".aac",
    ".mp4",
}

_MINIO_DOCUMENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "pptx",
    "xls",
    "xlsx",
    "txt",
    "md",
    "html",
}

_ATTACHMENT_DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".pptx",
    ".xls",
    ".xlsx",
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".rtf",
}

_ATTACHMENT_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".csv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".rtf",
    ".log",
    ".ini",
    ".cfg",
    ".conf",
    ".toml",
    ".sql",
    ".sh",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
}


def _normalize_attachment_content_type(content_type: Optional[str]) -> Optional[str]:
    """Normalize MIME type by dropping parameters and lower-casing."""
    if not content_type:
        return None
    return content_type.split(";", 1)[0].strip().lower()


def _infer_effective_content_type(filename: str, content_type: Optional[str]) -> str:
    """Infer the most useful MIME type using header first and extension fallback."""
    normalized = _normalize_attachment_content_type(content_type) or ""
    if normalized and normalized not in _GENERIC_CONTENT_TYPES:
        return normalized

    guessed = _normalize_attachment_content_type(mimetypes.guess_type(filename or "")[0])
    if guessed:
        return guessed

    extension_map = {
        ".doc": "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".xls": "application/vnd.ms-excel",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".json": "application/json",
        ".xml": "application/xml",
        ".yaml": "application/x-yaml",
        ".yml": "application/x-yaml",
        ".html": "text/html",
        ".htm": "text/html",
        ".pdf": "application/pdf",
    }
    return extension_map.get(
        Path(filename or "").suffix.lower(), normalized or "application/octet-stream"
    )


def _infer_attachment_type(filename: str, content_type: Optional[str]) -> str:
    """Classify uploaded attachment into image/document/audio/video/other."""
    normalized = _normalize_attachment_content_type(content_type) or ""
    suffix = Path(filename or "").suffix.lower()

    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("audio/"):
        return "audio"
    if normalized.startswith("video/"):
        return "video"

    if suffix in _ATTACHMENT_DOCUMENT_EXTENSIONS:
        return "document"

    document_mime_hints = (
        "pdf",
        "word",
        "presentation",
        "spreadsheet",
        "excel",
        "text/",
        "markdown",
        "html",
        "json",
        "xml",
        "yaml",
        "csv",
    )
    if any(hint in normalized for hint in document_mime_hints):
        return "document"

    return "other"


def _infer_attachment_bucket_type(filename: str, content_type: Optional[str]) -> str:
    """Choose a MinIO bucket type for attachment upload."""
    file_type = _infer_attachment_type(filename, content_type)
    if file_type == "image":
        return "images"
    if file_type == "audio":
        return "audio"
    if file_type == "video":
        return "video"
    if file_type == "document":
        ext = Path(filename or "").suffix.lower().lstrip(".")
        return "documents" if ext in _MINIO_DOCUMENT_EXTENSIONS else "artifacts"
    return "artifacts"


def _is_likely_text_attachment(filename: str, content_type: Optional[str]) -> bool:
    """Heuristic for deciding whether raw bytes can be safely decoded as text."""
    normalized = _normalize_attachment_content_type(content_type) or ""
    suffix = Path(filename or "").suffix.lower()
    if suffix in _ATTACHMENT_TEXT_EXTENSIONS:
        return True
    if normalized.startswith("text/"):
        return True
    return normalized in {
        "application/json",
        "application/xml",
        "application/x-yaml",
        "application/yaml",
        "application/javascript",
    }


def _decode_text_payload(file_data: bytes) -> str:
    """Best-effort decode for text-like payloads."""
    sample = file_data[:_ATTACHMENT_MAX_TEXT_BYTES]
    for encoding in ("utf-8", "utf-8-sig", "utf-16"):
        try:
            return sample.decode(encoding)
        except UnicodeDecodeError:
            continue
    return sample.decode("utf-8", errors="replace")


def _truncate_attachment_excerpt(text: str, max_chars: int) -> str:
    """Trim attachment text before injecting into LLM prompt."""
    normalized = (text or "").strip()
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= 32:
        return normalized[:max_chars]
    return normalized[: max_chars - 16] + "\n...[truncated]"


def _extract_attachment_text(
    filename: str,
    content_type: Optional[str],
    file_data: bytes,
) -> tuple[str, Optional[str]]:
    """Extract text for document-like attachments using KB extractors with plain-text fallback."""
    if not file_data:
        return "", "empty file"

    effective_content_type = _infer_effective_content_type(filename, content_type)
    suffix = Path(filename or "").suffix.lower()

    extraction_input = effective_content_type or suffix
    should_use_kb_extractor = suffix in _ATTACHMENT_DOCUMENT_EXTENSIONS or any(
        hint in extraction_input
        for hint in (
            "pdf",
            "word",
            "presentation",
            "spreadsheet",
            "excel",
            "markdown",
            "text/",
            "html",
        )
    )

    if should_use_kb_extractor:
        temp_path: Optional[Path] = None
        try:
            from knowledge_base.text_extractors import get_extractor

            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".bin") as tmp_file:
                tmp_file.write(file_data)
                temp_path = Path(tmp_file.name)

            extractor = get_extractor(extraction_input)
            result = extractor.extract(temp_path)
            extracted_text = (result.text or "").strip()
            if extracted_text:
                extracted_text = _truncate_attachment_excerpt(
                    extracted_text,
                    _ATTACHMENT_MAX_CHARS_PER_FILE * 2,
                )
                return extracted_text, None
            return "", "extractor returned empty text"
        except Exception as extraction_error:
            if not _is_likely_text_attachment(filename, effective_content_type):
                return "", _trim_process_text(str(extraction_error), max_chars=180)
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    if _is_likely_text_attachment(filename, effective_content_type):
        decoded_text = _decode_text_payload(file_data).strip()
        if decoded_text:
            decoded_text = _truncate_attachment_excerpt(
                decoded_text,
                _ATTACHMENT_MAX_CHARS_PER_FILE * 2,
            )
            return decoded_text, None
        return "", "decoded text is empty"

    return "", "unsupported or binary file type"


def _build_attachment_prompt_context(
    file_refs: List["FileReference"],
    *,
    include_image_notes: bool = True,
) -> str:
    """Build a bounded prompt section summarizing uploaded attachment content."""
    if not file_refs:
        return ""

    sections: List[str] = []
    remaining = _ATTACHMENT_MAX_CHARS_TOTAL

    for file_ref in file_refs:
        if file_ref.extracted_text:
            excerpt = _truncate_attachment_excerpt(
                file_ref.extracted_text,
                _ATTACHMENT_MAX_CHARS_PER_FILE,
            )
            if remaining <= 0:
                sections.append("[Files] Additional extracted text omitted due to size limit.")
                break
            if len(excerpt) > remaining:
                excerpt = _truncate_attachment_excerpt(excerpt, remaining)
            sections.append(f"[Document: {file_ref.name}]\n{excerpt}")
            remaining -= len(excerpt)
            continue

        if file_ref.type == "document":
            reason = _trim_process_text(file_ref.extraction_error or "unavailable", max_chars=120)
            sections.append(
                f"[Document: {file_ref.name}] Attached, but text extraction unavailable ({reason})."
            )
        elif include_image_notes and file_ref.type == "image":
            sections.append(f"[Image: {file_ref.name}] Attached.")
        elif file_ref.type == "audio":
            sections.append(f"[Audio: {file_ref.name}] Attached.")
        elif file_ref.type == "video":
            sections.append(f"[Video: {file_ref.name}] Attached.")
        else:
            sections.append(f"[File: {file_ref.name}] Attached.")

    if not sections:
        return ""

    return "\n\nAttached files context:\n" + "\n\n".join(sections)


def _sanitize_workspace_attachment_filename(filename: str) -> str:
    """Normalize user-provided attachment filename for workspace storage."""
    name = Path(str(filename or "")).name.strip().replace("\x00", "")
    if not name:
        return _ATTACHMENT_DEFAULT_FILENAME
    name = name.replace("\\", "_").replace("/", "_")
    return name or _ATTACHMENT_DEFAULT_FILENAME


def _materialize_attachment_files_to_workspace(
    workdir: Path,
    file_refs: List["FileReference"],
    attachment_payloads: Dict[str, bytes],
    *,
    target_dir: str = _ATTACHMENT_WORKSPACE_DIR,
) -> Tuple[int, List[str]]:
    """Write uploaded file bytes to session workspace and annotate workspace paths."""
    if not file_refs or not attachment_payloads:
        return 0, []

    destination_root = (workdir / target_dir).resolve()
    destination_root.mkdir(parents=True, exist_ok=True)

    written_count = 0
    errors: List[str] = []
    reserved_names: set[str] = set()

    for file_ref in file_refs:
        payload = attachment_payloads.get(file_ref.path)
        if payload is None:
            continue

        safe_name = _sanitize_workspace_attachment_filename(file_ref.name)
        stem = Path(safe_name).stem or "attachment"
        suffix = Path(safe_name).suffix
        candidate = safe_name
        duplicate_index = 2
        while candidate in reserved_names or (destination_root / candidate).exists():
            candidate = f"{stem}_{duplicate_index}{suffix}"
            duplicate_index += 1

        destination_path = destination_root / candidate
        try:
            destination_path.write_bytes(payload)
            reserved_names.add(candidate)
            written_count += 1
            file_ref.workspace_path = f"{target_dir}/{candidate}".replace("\\", "/")
        except OSError as exc:
            errors.append(f"{file_ref.name}: {str(exc)}")

    return written_count, errors


def _build_attachment_workspace_context(file_refs: List["FileReference"]) -> str:
    """Build prompt section that tells the agent where uploaded files are in workspace."""
    if not file_refs:
        return ""

    lines: List[str] = []
    for file_ref in file_refs:
        if not file_ref.workspace_path:
            continue
        lines.append(f"- {file_ref.name}: /workspace/{file_ref.workspace_path}")

    if not lines:
        return ""

    has_extracted_documents = any(
        file_ref.type == "document" and bool(file_ref.extracted_text)
        for file_ref in file_refs
    )
    usage_hint = (
        "Prefer the extracted document text above when available; only read raw files for missing details."
        if has_extracted_documents
        else "Use these paths when reading original uploaded files."
    )

    return (
        "\n\nAttached files are available in workspace:\n"
        + "\n".join(lines)
        + f"\n{usage_hint}"
    )


class TestAgentRequest(BaseModel):
    """Test agent request."""

    message: str = Field(..., min_length=1, max_length=5000)
    history: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Conversation history with role and content"
    )


class FileReference(BaseModel):
    """Reference to an uploaded file."""

    path: str  # MinIO object key
    type: str  # file type: image, document, audio, video, other
    name: str  # original filename
    size: int  # file size in bytes
    content_type: str  # MIME type
    extracted_text: Optional[str] = None  # Extracted text for document-like files
    extraction_error: Optional[str] = None  # Extraction failure reason, if any
    workspace_path: Optional[str] = None  # Session workspace path (e.g., input/report.pdf)


class SpeechTranscriptionResponse(BaseModel):
    """Voice input transcription response."""

    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    processing_time: Optional[float] = None


@router.post("/transcribe", response_model=SpeechTranscriptionResponse)
async def transcribe_voice_input(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Transcribe one audio file to text for test-chat voice input."""
    _ = current_user  # Auth guard only.

    filename = file.filename or "voice_input.wav"
    suffix = Path(filename).suffix.lower()
    normalized_content_type = _normalize_attachment_content_type(file.content_type)
    effective_content_type = _infer_effective_content_type(filename, normalized_content_type)

    if (
        not effective_content_type.startswith("audio/")
        and suffix not in _SPEECH_INPUT_AUDIO_EXTENSIONS
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only audio files are supported for voice transcription.",
        )

    file_data = await file.read()
    if not file_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty.",
        )

    if len(file_data) > _SPEECH_INPUT_MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                "Audio file is too large. "
                f"Maximum allowed size is {_SPEECH_INPUT_MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
            ),
        )

    temp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix or ".wav") as temp_file:
            temp_file.write(file_data)
            temp_path = Path(temp_file.name)

        def _transcribe_audio(path: Path):
            from knowledge_base.audio_processor import get_audio_processor

            return get_audio_processor().transcribe(path)

        transcription = await asyncio.to_thread(_transcribe_audio, temp_path)
        text = _sanitize_transcription_text(transcription.text)
        if not text:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Speech transcription returned empty text.",
            )

        return SpeechTranscriptionResponse(
            text=text,
            language=transcription.language,
            duration=transcription.duration,
            processing_time=transcription.processing_time,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Voice input transcription failed",
            extra={"filename": filename, "content_type": effective_content_type},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech transcription failed: {_trim_process_text(str(exc), max_chars=220)}",
        )
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)


@router.post("/{agent_id}/test")
async def test_agent(
    agent_id: str,
    message: str = Body(..., min_length=1, max_length=5000, embed=True),
    history: Optional[str] = Body(None, embed=True),  # JSON string of conversation history
    files: List[UploadFile] = File(default=[]),
    stream: bool = Query(default=True),  # Query parameter to enable/disable streaming
    session_id: Optional[str] = Query(
        None, description="Session ID for persistent execution environment"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Test agent with a message and optional files (streaming SSE response or single response).

    This endpoint tests the full agent capabilities including:
    - System prompt
    - Skills/functions (dynamically loaded)
    - Memory access
    - Real agent execution via AgentExecutor
    - Conversation history support
    - Agent caching for faster subsequent requests
    - File processing via agent skills

    File Processing:
    - Image attachments are passed to vision-capable models as multimodal input
    - Document attachments are parsed to text using knowledge_base extractors
    - Text-like unknown files use a safe decode fallback
    - Unsupported/binary files are still attached with a metadata note
    - Uploaded files are materialized under `/workspace/input/` for direct file access

    Args:
        agent_id: Agent ID
        message: User message
        history: Optional JSON string of conversation history
        files: Optional list of uploaded files
        stream: Enable streaming (default: True)
        session_id: Optional session ID for persistent execution environment
        current_user: Current authenticated user

    Session Persistence:
        - If session_id is provided, the session's working directory is reused
        - Files created in previous rounds persist across conversation turns
        - Installed dependencies (pip packages) persist within the session
        - A new session is created if session_id is not provided or invalid
        - Session events are emitted: {"type": "session", "session_id": "...", "new_session": true/false}
    """
    import asyncio
    import json
    import queue
    import threading

    from fastapi.responses import StreamingResponse
    from langchain_community.chat_models import ChatOllama

    from agent_framework.agent_executor import ExecutionContext, get_agent_executor
    from agent_framework.base_agent import AgentConfig, BaseAgent
    from agent_framework.runtime_policy import (
        ExecutionProfile,
        is_agent_test_chat_unified_runtime_enabled,
    )
    from llm_providers.custom_openai_provider import CustomOpenAIChat

    try:
        _ensure_session_memory_callback_registered()
        use_unified_runtime = is_agent_test_chat_unified_runtime_enabled()

        # Parse and sanitize history from JSON string.
        parsed_history: List[Dict[str, Any]] = []
        if history:
            try:
                raw_history = json.loads(history)
                parsed_history = _sanitize_history_messages(raw_history)

                if isinstance(raw_history, list) and len(parsed_history) != len(raw_history):
                    logger.info(
                        "Sanitized conversation history for agent test",
                        extra={
                            "agent_id": agent_id,
                            "received_messages": len(raw_history),
                            "kept_messages": len(parsed_history),
                        },
                    )
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse history JSON: {e}")

        # Upload files to MinIO and create file references
        file_refs: List[FileReference] = []
        attachment_payloads: Dict[str, bytes] = {}
        if files:
            minio_client = get_minio_client()

            for file in files:
                try:
                    # Read file data
                    file_data = await file.read()
                    file_stream = io.BytesIO(file_data)
                    file_name = file.filename or "unnamed"

                    # Detect file type and pick the appropriate bucket.
                    original_content_type = _normalize_attachment_content_type(file.content_type)
                    content_type = _infer_effective_content_type(file_name, original_content_type)
                    file_type = _infer_attachment_type(file_name, content_type)
                    bucket_type = _infer_attachment_bucket_type(file_name, content_type)

                    extracted_text: Optional[str] = None
                    extraction_error: Optional[str] = None
                    if file_type in {"document", "other"}:
                        extracted_text, extraction_error = await asyncio.to_thread(
                            _extract_attachment_text,
                            file_name,
                            content_type,
                            file_data,
                        )
                        if extracted_text:
                            logger.info(
                                "Extracted attachment text for agent test",
                                extra={
                                    "agent_id": agent_id,
                                    "attachment_name": file_name,
                                    "file_type": file_type,
                                    "chars": len(extracted_text),
                                },
                            )

                    # Upload to MinIO
                    # Note: MinIO metadata only supports ASCII characters
                    # Store filename in file_ref instead of metadata
                    bucket_name, object_key = minio_client.upload_file(
                        bucket_type=bucket_type,
                        file_data=file_stream,
                        filename=file_name,
                        user_id=current_user.user_id,
                        task_id=None,
                        agent_id=agent_id,
                        content_type=content_type,
                        metadata={
                            "agent_id": agent_id,
                            "uploaded_by": current_user.user_id,
                            # Don't include filename in metadata to avoid non-ASCII errors
                        },
                    )

                    # Create file reference
                    file_ref = FileReference(
                        path=f"{bucket_name}/{object_key}",
                        type=file_type,
                        name=file_name,
                        size=len(file_data),
                        content_type=content_type,
                        extracted_text=extracted_text,
                        extraction_error=extraction_error,
                    )
                    file_refs.append(file_ref)
                    attachment_payloads[file_ref.path] = file_data

                    logger.info(
                        f"File uploaded for agent test: {file.filename}",
                        extra={
                            "agent_id": agent_id,
                            "file_type": file_type,
                            "size": len(file_data),
                            "object_key": object_key,
                        },
                    )

                except Exception as file_error:
                    logger.error(f"Failed to upload file {file.filename}: {file_error}")
                    # Continue with other files
                    continue

        attachment_context = _build_attachment_prompt_context(file_refs, include_image_notes=True)
        message_with_attachments = (
            f"{message}{attachment_context}" if attachment_context else message
        )

        registry = get_agent_registry()
        agent_info = registry.get_agent(UUID(agent_id))

        if not agent_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )

        # Check ownership
        if str(agent_info.owner_user_id) != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to test this agent",
            )

        logger.info(
            f"Testing agent: {agent_info.name}",
            extra={"agent_id": agent_id, "user_id": current_user.user_id},
        )

        async def generate_stream():
            """Generate SSE stream for agent execution with real streaming."""
            conversation_session = None
            token_queue = None
            exec_thread = None
            agent = None
            try:
                # Track timing and tokens
                import time

                start_time = time.time()
                first_token_time = None
                last_token_time = None
                input_tokens = 0
                output_tokens = 0

                # Session management for persistent execution environment
                from agent_framework.session_manager import get_session_manager

                session_mgr = get_session_manager()
                conversation_session, is_new_session = await session_mgr.get_or_create_session(
                    agent_id=UUID(agent_id),
                    user_id=UUID(current_user.user_id),
                    session_id=session_id,
                )

                # Emit session event to frontend
                session_event = {
                    "type": "session",
                    "session_id": conversation_session.session_id,
                    "new_session": is_new_session,
                    "workdir": str(conversation_session.workdir),
                    "use_sandbox": conversation_session.use_sandbox,
                    "sandbox_id": conversation_session.sandbox_id,
                }
                yield f"data: {json.dumps(session_event)}\n\n"

                logger.info(
                    f"Session {'created' if is_new_session else 'resumed'}: {conversation_session.session_id}",
                    extra={
                        "session_id": conversation_session.session_id,
                        "agent_id": agent_id,
                        "new_session": is_new_session,
                        "workdir": str(conversation_session.workdir),
                        "use_sandbox": conversation_session.use_sandbox,
                        "sandbox_id": conversation_session.sandbox_id,
                    },
                )

                if file_refs:
                    written_files, materialize_errors = _materialize_attachment_files_to_workspace(
                        conversation_session.workdir,
                        file_refs,
                        attachment_payloads,
                    )
                    if written_files > 0:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "info",
                                    "content": (
                                        f"Copied {written_files} uploaded file(s) to "
                                        "/workspace/input/ for agent access."
                                    ),
                                }
                            )
                            + "\n\n"
                        )
                    for error_text in materialize_errors:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "type": "info",
                                    "content": (
                                        "Failed to copy one uploaded file to workspace: "
                                        f"{error_text}"
                                    ),
                                }
                            )
                            + "\n\n"
                        )

                # Check if agent is already cached
                # Include capabilities in cache key to invalidate when skills change
                cache_key = _build_agent_cache_key(
                    agent_id=agent_id,
                    provider=agent_info.llm_provider,
                    model=agent_info.llm_model,
                    capabilities=agent_info.capabilities,
                )
                agent, llm = get_cached_agent(cache_key)

                if agent is not None and llm is not None:
                    logger.info(f"Reusing cached agent: {agent_info.name}")
                    yield f"data: {json.dumps({'type': 'info', 'content': 'Using cached agent...'})}\n\n"
                else:
                    # Send start event
                    yield f"data: {json.dumps({'type': 'start', 'content': 'Agent execution started'})}\n\n"
                    yield f"data: {json.dumps({'type': 'info', 'content': 'Initializing agent...'})}\n\n"

                    # Create agent config
                    config = AgentConfig(
                        agent_id=UUID(agent_id),
                        name=agent_info.name,
                        agent_type=agent_info.agent_type,
                        owner_user_id=UUID(current_user.user_id),
                        capabilities=agent_info.capabilities or [],
                        access_level=agent_info.access_level or "private",
                        allowed_knowledge=agent_info.allowed_knowledge or [],
                        allowed_memory=agent_info.allowed_memory or [],
                        llm_model=agent_info.llm_model or "llama3.2:latest",
                        temperature=agent_info.temperature or 0.7,
                        max_iterations=AGENT_TEST_MAX_ITERATIONS,
                        system_prompt=agent_info.system_prompt,
                    )

                    # Create agent instance
                    agent = BaseAgent(config)

                    provider_name = agent_info.llm_provider or "ollama"
                    model_name = agent_info.llm_model or "llama3.2:latest"
                    temperature = agent_info.temperature or 0.7

                    # Create LLM instance - only from database
                    llm = None
                    resolved_context_window_tokens: Optional[int] = None
                    try:
                        from database.connection import get_db_session
                        from llm_providers.db_manager import ProviderDBManager

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
                                        api_key = db_manager._decrypt_api_key(
                                            db_provider.api_key_encrypted
                                        )

                                    # Use CustomOpenAIChat for all OpenAI-compatible providers
                                    # It intelligently handles /v1 suffix in base_url
                                    base_url = db_provider.base_url
                                    llm = CustomOpenAIChat(
                                        base_url=base_url,
                                        model=model_name,
                                        temperature=temperature,
                                        api_key=api_key,
                                        timeout=db_provider.timeout,
                                        max_retries=db_provider.max_retries,
                                        max_tokens=agent_info.max_tokens,
                                        streaming=True,
                                    )
                                    logger.info(
                                        f"[LLM-INIT] Using CustomOpenAIChat: provider={provider_name}, base_url={base_url}"
                                    )

                                elif db_provider.protocol == "ollama":
                                    # Use CustomOpenAIChat for Ollama to support reasoning content streaming
                                    # Ollama provides OpenAI-compatible API at /v1/chat/completions
                                    llm = CustomOpenAIChat(
                                        base_url=db_provider.base_url,
                                        model=model_name,
                                        temperature=temperature,
                                        max_tokens=agent_info.max_tokens,
                                        api_key=None,  # Ollama doesn't require API key
                                        streaming=True,
                                    )
                                    logger.info(
                                        f"[LLM-INIT] Using CustomOpenAIChat for Ollama: {provider_name} at {db_provider.base_url}"
                                    )
                            else:
                                logger.error(
                                    f"Provider '{provider_name}' not found or disabled in database"
                                )

                    except Exception as db_error:
                        logger.error(
                            f"Failed to load provider from database: {db_error}", exc_info=True
                        )

                    if llm is None:
                        raise ValueError(f"Could not create LLM for provider: {provider_name}")

                    agent.llm = llm
                    if resolved_context_window_tokens:
                        agent.config.context_window_tokens = resolved_context_window_tokens
                        logger.info(
                            "Resolved model context window for agent",
                            extra={
                                "agent_id": agent_id,
                                "model_name": model_name,
                                "context_window_tokens": resolved_context_window_tokens,
                            },
                        )

                    # Initialize agent (now async)
                    await agent.initialize()

                    # Cache the initialized agent with 30 minute TTL.
                    cache_agent(cache_key, agent, llm, ttl_minutes=30)

                model_info = f"{agent_info.llm_model or 'llama3.2:latest'} via {agent_info.llm_provider or 'ollama'}"
                yield f"data: {json.dumps({'type': 'info', 'content': f'Using model: {model_info}'})}\n\n"

                if agent.config.capabilities:
                    yield f"data: {json.dumps({'type': 'info', 'content': f'Available skills: {', '.join(agent.config.capabilities)}'})}\n\n"

                yield f"data: {json.dumps({'type': 'info', 'content': 'Retrieving relevant memories and processing...'})}\n\n"
                logger.debug(
                    "[STREAM] Sent status: type='info', content='Retrieving relevant memories and processing...'"
                )

                # Build memory/knowledge context via AgentExecutor to keep
                # streaming and non-streaming behavior consistent.
                context = {}
                context_debug: Dict[str, Any] = {}
                request_exec_context = ExecutionContext(
                    agent_id=UUID(agent_id),
                    user_id=UUID(current_user.user_id),
                    user_role=current_user.role,
                    task_description=message,
                    additional_context={"execution_context_tag": AGENT_TEST_RUNTIME_CONTEXT_TAG},
                )
                executor = get_agent_executor()
                try:
                    memory_scopes = resolve_memory_scopes(
                        access_level=agent_info.access_level,
                        allowed_memory=agent_info.allowed_memory,
                    )
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "info",
                                "content": f"Effective memory scopes: {', '.join(memory_scopes)}",
                            }
                        )
                        + "\n\n"
                    )

                    context, context_debug = await asyncio.to_thread(
                        executor.build_execution_context_with_debug,
                        agent,
                        request_exec_context,
                        top_k=agent_info.top_k or 5,
                        knowledge_min_relevance_score=agent_info.similarity_threshold,
                    )

                    for debug_message in _build_retrieval_process_messages(context_debug):
                        yield (
                            "data: "
                            + json.dumps({"type": "info", "content": debug_message})
                            + "\n\n"
                        )

                except Exception as context_error:
                    logger.error(
                        "Failed to retrieve execution context: %s",
                        context_error,
                        exc_info=True,
                    )

                if file_refs:
                    yield (
                        "data: "
                        + json.dumps(
                            {"type": "info", "content": f"Processing {len(file_refs)} file(s)..."}
                        )
                        + "\n\n"
                    )
                    for file_ref in file_refs:
                        if file_ref.extracted_text:
                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "type": "info",
                                        "content": (
                                            f"Extracted text from {file_ref.name} "
                                            f"({len(file_ref.extracted_text)} chars)"
                                        ),
                                    }
                                )
                                + "\n\n"
                            )
                        elif file_ref.type == "document":
                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "type": "info",
                                        "content": (
                                            f"Attached {file_ref.name} "
                                            f"(text extraction unavailable)"
                                        ),
                                    }
                                )
                                + "\n\n"
                            )

                # Keep task text clean; BaseAgent will inject retrieval context consistently.
                attachment_workspace_context = _build_attachment_workspace_context(file_refs)
                user_message = (
                    f"{message_with_attachments}{attachment_workspace_context}"
                    if attachment_workspace_context
                    else message_with_attachments
                )

                # Check if model supports vision
                model_supports_vision = False
                try:
                    from database.connection import get_db_session
                    from llm_providers.db_manager import ProviderDBManager
                    from llm_providers.model_metadata import EnhancedModelCapabilityDetector

                    provider_name = agent_info.llm_provider or "ollama"
                    model_name = agent_info.llm_model or "llama3.2:latest"

                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        provider = db_manager.get_provider(provider_name)

                        if (
                            provider
                            and provider.model_metadata
                            and model_name in provider.model_metadata
                        ):
                            # Use stored metadata from database
                            metadata_dict = provider.model_metadata[model_name]
                            model_supports_vision = metadata_dict.get("supports_vision", False)
                            logger.info(
                                f"Model {model_name} vision support from database: {model_supports_vision}"
                            )
                        else:
                            # Generate metadata using detector (same as API endpoint)
                            detector = EnhancedModelCapabilityDetector()
                            metadata = detector.detect_metadata(model_name, provider_name)
                            model_supports_vision = metadata.supports_vision
                            logger.info(
                                f"Model {model_name} vision support from detector: {model_supports_vision}"
                            )

                except Exception as meta_error:
                    logger.error(
                        f"Failed to check model vision support: {meta_error}", exc_info=True
                    )
                    model_supports_vision = False

                # Build message content based on model capabilities
                multimodal_content = None  # Will be passed to agent for vision models
                current_image_refs = [file_ref for file_ref in file_refs if file_ref.type == "image"]
                has_image_payload = bool(current_image_refs)
                if model_supports_vision and has_image_payload:
                    # For vision models, use multimodal content format
                    multimodal_content = []
                    vision_preference_hint = (
                        "\n\n[Vision handling hint]\n"
                        "You can directly read attached images in this multimodal message. "
                        "Prefer direct visual understanding first. "
                        "Use OCR tools only when the user explicitly asks for OCR or when direct "
                        "visual reading is clearly insufficient."
                    )

                    # Add text content
                    if user_message:
                        multimodal_content.append(
                            {"type": "text", "text": f"{user_message}{vision_preference_hint}"}
                        )

                    # Add image content
                    minio_client = get_minio_client()
                    for file_ref in current_image_refs:
                        try:
                            # Download image from MinIO
                            bucket_name, object_key = file_ref.path.split("/", 1)
                            image_stream, _metadata = minio_client.download_file(
                                bucket_name, object_key
                            )

                            # Read image data
                            image_data = image_stream.read()

                            # Convert to base64
                            image_base64 = base64.b64encode(image_data).decode("utf-8")
                            image_format = _infer_image_format(file_ref.content_type, file_ref.name)

                            # Add image to message content
                            multimodal_content.append(
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/{image_format};base64,{image_base64}"
                                    },
                                }
                            )

                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "type": "info",
                                        "content": (
                                            f"Image {file_ref.name} added to message for vision model"
                                        ),
                                    }
                                )
                                + "\n\n"
                            )

                        except Exception as img_error:
                            logger.error(f"Failed to load image {file_ref.name}: {img_error}")
                            yield (
                                "data: "
                                + json.dumps(
                                    {
                                        "type": "info",
                                        "content": f"Failed to load image {file_ref.name}",
                                    }
                                )
                                + "\n\n"
                            )

                    logger.info(
                        f"Built multimodal content with {len(multimodal_content)} parts "
                        f"for vision model"
                    )

                # Send status message before generating content
                yield f"data: {json.dumps({'type': 'info', 'content': 'Generating response...'})}\n\n"
                logger.debug("[STREAM] Sent status: type='info', content='Generating response...'")

                execution_messages: List[Any] = []
                response_metadata_list: List[Dict[str, Any]] = []
                run_error: Optional[str] = None
                token_queue = queue.Queue()
                error_holder = [None]
                segment_response = [""]
                segment_response_metadata = [{}]
                segment_execution_messages = [[]]

                def stream_callback(token_data):
                    """Callback for streaming tokens from agent."""
                    nonlocal first_token_time, last_token_time
                    if first_token_time is None:
                        first_token_time = time.time()
                    last_token_time = time.time()
                    token_queue.put(token_data)

                def execute_agent(
                    task_description_override: str,
                    history_override: List[Dict[str, Any]],
                    content_override: Optional[Any],
                ):
                    """Execute agent in a separate thread."""
                    try:
                        run_exec_context = ExecutionContext(
                            agent_id=UUID(agent_id),
                            user_id=UUID(current_user.user_id),
                            user_role=current_user.role,
                            task_description=task_description_override,
                            additional_context={
                                "execution_context_tag": AGENT_TEST_RUNTIME_CONTEXT_TAG,
                                "task_intent_text": message,
                            },
                        )
                        if use_unified_runtime:
                            result = executor.execute(
                                agent,
                                run_exec_context,
                                conversation_history=history_override or None,
                                execution_profile=ExecutionProfile.DEBUG_CHAT,
                                stream_callback=stream_callback,
                                session_workdir=conversation_session.workdir,
                                container_id=conversation_session.sandbox_id,
                                message_content=content_override,
                                prebuilt_execution_context=context,
                            )
                        else:
                            # Legacy fallback path.
                            result = agent.execute_task(
                                task_description=task_description_override,
                                context=context,
                                conversation_history=history_override or None,
                                stream_callback=stream_callback,
                                session_workdir=conversation_session.workdir,
                                container_id=conversation_session.sandbox_id,
                                message_content=content_override,
                                task_intent_text=message,
                            )

                        if not result.get("success", False):
                            failure_error = str(
                                result.get("error") or "Unknown agent execution error"
                            )
                            failure_output = result.get("output")
                            segment_response[0] = (
                                str(failure_output) if failure_output is not None else ""
                            )
                            segment_execution_messages[0] = result.get("messages") or []
                            error_holder[0] = failure_error
                            token_queue.put(None)
                            return

                        # Store final response
                        segment_response[0] = result.get("output", "")
                        segment_execution_messages[0] = result.get("messages") or []

                        # Get metadata if available
                        if segment_execution_messages[0]:
                            for msg in reversed(segment_execution_messages[0]):
                                if hasattr(msg, "response_metadata") and msg.response_metadata:
                                    segment_response_metadata[0] = msg.response_metadata
                                    break

                        # Signal completion
                        token_queue.put(None)

                    except BaseException as e:
                        logger.error(f"Agent execution error: {e}", exc_info=True)
                        error_holder[0] = str(e)
                        token_queue.put(None)

                # Start agent execution in background thread
                exec_thread = threading.Thread(
                    target=execute_agent,
                    args=(
                        user_message,
                        list(parsed_history),
                        multimodal_content,
                    ),
                )
                exec_thread.start()

                # Stream tokens as they arrive
                segment_output_completed = False
                while True:
                    try:
                        # Wait for token with timeout without blocking the event loop
                        token_data = await asyncio.to_thread(token_queue.get, True, 0.1)

                        if token_data is None:
                            # Execution complete
                            segment_output_completed = True
                            break

                        # token_data can be either a string (old format) or tuple (token, type)
                        if isinstance(token_data, tuple):
                            token, content_type = token_data
                        else:
                            token = token_data
                            content_type = "content"

                        # Debug: Log what we're sending
                        logger.debug(
                            f"[STREAM] Sending to frontend: type='{content_type}', length={len(str(token))}"
                        )

                        # Handle round_stats specially - the token is already JSON
                        if content_type == "round_stats":
                            try:
                                stats_data = json.loads(token)
                                stats_data["type"] = "round_stats"
                                yield f"data: {json.dumps(stats_data)}\n\n"
                            except json.JSONDecodeError:
                                logger.warning(f"[STREAM] Invalid round_stats JSON: {token}")
                        else:
                            # Send token to client with type information
                            yield (
                                f"data: {json.dumps({'type': content_type, 'content': token})}\n\n"
                            )

                    except queue.Empty:
                        # Check if thread is still alive
                        if not exec_thread.is_alive():
                            # Thread finished but no None signal - something went wrong
                            logger.warning(
                                "[STREAM] Thread finished without sending completion signal"
                            )
                            break
                        # No token yet, continue waiting
                        continue

                if segment_output_completed:
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "info",
                                "content": "模型输出已结束，正在进行结果收尾与状态校验...",
                            }
                        )
                        + "\n\n"
                    )

                # Wait for thread to complete (should already be done)
                await asyncio.to_thread(exec_thread.join, 5)

                # Check if there was an error
                if error_holder[0]:
                    run_error = error_holder[0]
                    logger.error(f"[STREAM] Agent execution error: {run_error}")

                final_response_text = (segment_response[0] if segment_response[0] is not None else "").strip()

                if isinstance(segment_response_metadata[0], dict):
                    response_metadata_list.append(segment_response_metadata[0])
                else:
                    response_metadata_list.append({})

                if isinstance(segment_execution_messages[0], list):
                    execution_messages.extend(segment_execution_messages[0])

                # Surface execution error if any.
                if run_error:
                    yield (
                        "data: "
                        + json.dumps({"type": "error", "content": f"Error: {run_error}"})
                        + "\n\n"
                    )
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "type": "done",
                                "content": "Agent execution failed",
                                "partial": True,
                            }
                        )
                        + "\n\n"
                    )

                # Calculate statistics
                end_time = time.time()

                # Aggregate token usage from all segment metadata.
                input_tokens = 0
                output_tokens = 0
                for metadata in response_metadata_list:
                    logger.info(
                        "[TOKEN-STATS] Segment metadata: %s",
                        json.dumps(metadata, default=str, ensure_ascii=False),
                    )
                    segment_input_tokens, segment_output_tokens = (
                        _extract_token_usage_from_metadata(metadata)
                    )
                    input_tokens += segment_input_tokens
                    output_tokens += segment_output_tokens

                # Fallback: estimate if no metadata available
                if input_tokens == 0 and output_tokens == 0:
                    # 流式模式下LLM API通常不返回token统计，需要估算
                    # 改进的估算：中文1字符≈1.5token，英文1字符≈0.25token
                    # 简化：平均1字符≈0.5token（考虑中英文混合）
                    input_chars = 0
                    for msg in execution_messages:
                        if hasattr(msg, "content"):
                            if isinstance(msg.content, str):
                                input_chars += len(msg.content)
                            elif isinstance(msg.content, list):
                                # 多模态内容（图片+文本）
                                for item in msg.content:
                                    if isinstance(item, dict) and item.get("type") == "text":
                                        input_chars += len(item.get("text", ""))

                    # 改进的token估算：中英文混合平均
                    input_tokens = int(input_chars * 0.5)
                    output_tokens = int(len(final_response_text) * 0.5)

                    logger.info(
                        "Token estimation (no metadata from streaming API): "
                        f"input={input_tokens} (chars={input_chars}), "
                        f"output={output_tokens} (chars={len(final_response_text)}), "
                        f"messages_count={len(execution_messages)}"
                    )
                else:
                    logger.info(
                        f"Token from metadata: input={input_tokens}, output={output_tokens}"
                    )

                total_tokens = input_tokens + output_tokens

                # Calculate speeds (only generation time, not initialization)
                time_to_first_token = (first_token_time - start_time) if first_token_time else 0

                # Tokens per second: only count generation time (first token to last token)
                # If no chunks were streamed (chunk_count=0), use total time instead
                if first_token_time and last_token_time and output_tokens > 0:
                    generation_time = last_token_time - first_token_time
                    if generation_time > 0:
                        tokens_per_second = output_tokens / generation_time
                    else:
                        # Fallback: use total time if generation_time is 0
                        total_time = end_time - start_time
                        tokens_per_second = output_tokens / total_time if total_time > 0 else 0
                elif output_tokens > 0:
                    # No streaming happened (chunk_count=0), use total time
                    total_time = end_time - start_time
                    tokens_per_second = output_tokens / total_time if total_time > 0 else 0
                else:
                    tokens_per_second = 0

                if not run_error:
                    # Send statistics
                    stats = {
                        "type": "stats",
                        "timeToFirstToken": round(time_to_first_token, 2),
                        "tokensPerSecond": round(tokens_per_second, 1),
                        "inputTokens": input_tokens,
                        "outputTokens": output_tokens,
                        "totalTokens": total_tokens,
                        "totalTime": round(end_time - start_time, 2),
                    }
                    yield f"data: {json.dumps(stats)}\n\n"
                    done_payload = {
                        "type": "done",
                        "content": "Agent execution completed",
                        "partial": False,
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n"

                    # Buffer turn-level memory candidates; flush once on session end.
                    if final_response_text:
                        try:
                            conversation_session.append_memory_turn(
                                user_message=message,
                                agent_response=final_response_text,
                                agent_name=agent_info.name,
                                max_turns=_SESSION_MEMORY_MAX_TURNS,
                            )
                            logger.debug(
                                "Buffered session memory candidate",
                                extra={
                                    "session_id": conversation_session.session_id,
                                    "buffered_turns": len(conversation_session.memory_turns),
                                },
                            )
                        except Exception as uc_error:
                            logger.warning(
                                f"Failed to buffer session memory candidate (continuing): {uc_error}"
                            )

                logger.info(
                    f"Agent test completed: {agent_info.name} (tokens: {input_tokens}/{output_tokens}, speed: {tokens_per_second:.1f} tok/s)"
                )

            except asyncio.CancelledError:
                if token_queue is not None:
                    try:
                        token_queue.put_nowait(None)
                    except Exception:
                        pass
                if agent is not None and hasattr(agent, "request_cancellation"):
                    try:
                        agent.request_cancellation("client stream cancelled")
                    except Exception as cancel_error:
                        logger.warning(
                            "Failed to signal agent cancellation after stream disconnect: %s",
                            cancel_error,
                            extra={"agent_id": agent_id},
                        )
                thread_still_running = False
                if exec_thread is not None and exec_thread.is_alive():
                    exec_thread.join(timeout=5.0)
                    if exec_thread.is_alive():
                        thread_still_running = True
                        logger.warning(
                            "Agent execution thread still running after stream cancellation",
                            extra={"agent_id": agent_id},
                        )
                if thread_still_running:
                    invalidated_count = invalidate_agent_cache(agent_id)
                    logger.warning(
                        "Invalidated cached agent entries after stream cancellation",
                        extra={
                            "agent_id": agent_id,
                            "invalidated_entries": invalidated_count,
                        },
                    )
                logger.info(
                    "Agent test stream cancelled by client",
                    extra={
                        "agent_id": agent_id,
                        "session_id": (
                            conversation_session.session_id if conversation_session else "unknown"
                        ),
                    },
                )
                return
            except Exception as e:
                logger.error(f"Error during agent test streaming: {e}", exc_info=True)
                yield f"data: {json.dumps({'type': 'error', 'content': f'Error: {str(e)}'})}\n\n"

        if stream:
            # Return streaming response
            return StreamingResponse(
                generate_stream(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )
        else:
            # Non-streaming response - execute and return complete result
            try:
                # Session management for persistent execution environment
                from agent_framework.session_manager import get_session_manager

                session_mgr = get_session_manager()
                conversation_session, _ = await session_mgr.get_or_create_session(
                    agent_id=UUID(agent_id),
                    user_id=UUID(current_user.user_id),
                    session_id=session_id,
                )

                if file_refs:
                    _materialize_attachment_files_to_workspace(
                        conversation_session.workdir,
                        file_refs,
                        attachment_payloads,
                    )

                attachment_workspace_context = _build_attachment_workspace_context(file_refs)
                user_message = (
                    f"{message_with_attachments}{attachment_workspace_context}"
                    if attachment_workspace_context
                    else message_with_attachments
                )

                # Create agent config
                config = AgentConfig(
                    agent_id=UUID(agent_id),
                    name=agent_info.name,
                    agent_type=agent_info.agent_type,
                    owner_user_id=UUID(current_user.user_id),
                    capabilities=agent_info.capabilities or [],
                    access_level=agent_info.access_level or "private",
                    allowed_knowledge=agent_info.allowed_knowledge or [],
                    allowed_memory=agent_info.allowed_memory or [],
                    llm_model=agent_info.llm_model or "llama3.2:latest",
                    temperature=agent_info.temperature or 0.7,
                    max_iterations=AGENT_TEST_MAX_ITERATIONS,
                    system_prompt=agent_info.system_prompt,
                )

                agent = BaseAgent(config)

                provider_name = agent_info.llm_provider or "ollama"
                model_name = agent_info.llm_model or "llama3.2:latest"
                temperature = agent_info.temperature or 0.7

                # Create LLM instance - only from database
                llm = None
                resolved_context_window_tokens: Optional[int] = None
                try:
                    from database.connection import get_db_session
                    from llm_providers.db_manager import ProviderDBManager

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
                                    api_key = db_manager._decrypt_api_key(
                                        db_provider.api_key_encrypted
                                    )

                                # Use CustomOpenAIChat for all OpenAI-compatible providers
                                # It intelligently handles /v1 suffix in base_url
                                base_url = db_provider.base_url
                                llm = CustomOpenAIChat(
                                    base_url=base_url,
                                    model=model_name,
                                    temperature=temperature,
                                    api_key=api_key,
                                    timeout=db_provider.timeout,
                                    max_retries=db_provider.max_retries,
                                    max_tokens=agent_info.max_tokens,
                                )
                                logger.info(
                                    f"[LLM-INIT] Using CustomOpenAIChat (non-streaming): provider={provider_name}, base_url={base_url}"
                                )
                            elif db_provider.protocol == "ollama":
                                # Use CustomOpenAIChat for Ollama to support reasoning content
                                llm = CustomOpenAIChat(
                                    base_url=db_provider.base_url,
                                    model=model_name,
                                    temperature=temperature,
                                    max_tokens=agent_info.max_tokens,
                                    api_key=None,  # Ollama doesn't require API key
                                    streaming=False,
                                )
                                logger.info(
                                    f"[LLM-INIT] Using CustomOpenAIChat for Ollama (non-streaming): {provider_name}"
                                )
                        else:
                            logger.error(
                                f"Provider '{provider_name}' not found or disabled in database"
                            )

                except Exception as db_error:
                    logger.error(
                        f"Failed to load provider from database: {db_error}", exc_info=True
                    )

                if llm is None:
                    raise ValueError(f"Could not create LLM for provider: {provider_name}")

                agent.llm = llm
                if resolved_context_window_tokens:
                    agent.config.context_window_tokens = resolved_context_window_tokens
                    logger.info(
                        "Resolved model context window for agent (non-stream)",
                        extra={
                            "agent_id": agent_id,
                            "model_name": model_name,
                            "context_window_tokens": resolved_context_window_tokens,
                        },
                    )
                await agent.initialize()

                # Execute without streaming
                exec_context = ExecutionContext(
                    agent_id=UUID(agent_id),
                    user_id=UUID(current_user.user_id),
                    user_role=current_user.role,
                    task_description=user_message,
                    additional_context={
                        "execution_context_tag": AGENT_TEST_RUNTIME_CONTEXT_TAG,
                        "task_intent_text": message,
                    },
                )

                executor = get_agent_executor()
                execute_kwargs: Dict[str, Any] = {
                    "conversation_history": parsed_history or None,
                    "knowledge_min_relevance_score": agent_info.similarity_threshold,
                }
                if use_unified_runtime:
                    execute_kwargs["execution_profile"] = ExecutionProfile.DEBUG_CHAT
                result = await asyncio.to_thread(
                    executor.execute,
                    agent,
                    exec_context,
                    session_workdir=conversation_session.workdir,
                    container_id=conversation_session.sandbox_id,
                    **execute_kwargs,
                )

                return {
                    "success": result.get("success"),
                    "output": result.get("output"),
                    "error": result.get("error"),
                }

            except Exception as e:
                logger.error(f"Non-streaming execution failed: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Execution failed: {str(e)}",
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test agent: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test agent: {str(e)}",
        )


@router.delete("/{agent_id}/sessions/{session_id}")
async def end_agent_session(
    agent_id: str,
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    End an agent session and clean up its resources.

    This endpoint explicitly ends a conversation session, cleaning up:
    - Working directory and all files created during the session
    - Sandbox container (if sandbox mode was enabled)
    - Any cached state associated with the session

    The session is also automatically cleaned up after TTL expiration (default: 30 minutes
    of inactivity), so this endpoint is optional but recommended for explicit cleanup
    when the user closes the test dialog.

    Args:
        agent_id: Agent ID
        session_id: Session ID to end
        current_user: Current authenticated user

    Returns:
        Success message with session details
    """
    try:
        from agent_framework.session_manager import get_session_manager

        _ensure_session_memory_callback_registered()
        session_mgr = get_session_manager()
        session = session_mgr.get_session(session_id)

        if not session:
            # Session already gone (expired or cleaned up) — desired state achieved.
            # DELETE is idempotent: return success, not 404.
            logger.info(
                f"Session {session_id} already ended (not found)",
                extra={"session_id": session_id, "agent_id": agent_id},
            )
            return {
                "message": "Session already ended",
                "session_id": session_id,
                "agent_id": agent_id,
            }

        # Verify the session belongs to the requesting user
        if session.user_id != UUID(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to end this session",
            )

        # Verify the session is for the correct agent
        if str(session.agent_id) != agent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_id} does not belong to agent {agent_id}",
            )

        # End the session
        ended = await session_mgr.end_session(session_id, UUID(current_user.user_id))

        if ended:
            logger.info(
                f"Session ended by user: {session_id}",
                extra={
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "user_id": current_user.user_id,
                },
            )
            return {
                "message": "Session ended successfully",
                "session_id": session_id,
                "agent_id": agent_id,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to end session",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to end session {session_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to end session: {str(e)}",
        )


@router.get("/{agent_id}/sessions")
async def get_agent_sessions(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get all active sessions for an agent.

    Returns information about all sessions the current user has for the specified agent.
    This is useful for debugging and monitoring session state.

    Args:
        agent_id: Agent ID
        current_user: Current authenticated user

    Returns:
        List of session information
    """
    try:
        from agent_framework.session_manager import get_session_manager

        session_mgr = get_session_manager()
        user_sessions = session_mgr.get_user_sessions(UUID(current_user.user_id))

        # Filter to sessions for this agent
        agent_sessions = [
            {
                "session_id": s.session_id,
                "agent_id": str(s.agent_id),
                "created_at": s.created_at.isoformat(),
                "last_activity": s.last_activity.isoformat(),
                "remaining_ttl_seconds": s.remaining_ttl_seconds(),
                "use_sandbox": s.use_sandbox,
                "workdir": str(s.workdir),
            }
            for s in user_sessions
            if str(s.agent_id) == agent_id
        ]

        return {
            "agent_id": agent_id,
            "sessions": agent_sessions,
            "total_count": len(agent_sessions),
        }

    except Exception as e:
        logger.error(f"Failed to get sessions for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sessions: {str(e)}",
        )


@router.get("/{agent_id}/sessions/{session_id}/workspace/files")
async def list_agent_session_workspace_files(
    agent_id: str,
    session_id: str,
    path: str = "",
    recursive: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List files from an active agent-test session workspace."""
    try:
        from agent_framework.session_manager import get_session_manager

        session_mgr = get_session_manager()
        session = session_mgr.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        if session.user_id != UUID(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this session",
            )
        if str(session.agent_id) != agent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_id} does not belong to agent {agent_id}",
            )

        session.touch()
        return _list_session_workspace_entries(session.workdir, path, recursive)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to list workspace files for session {session_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list workspace files: {str(e)}",
        )


@router.get("/{agent_id}/sessions/{session_id}/workspace/download")
async def download_agent_session_workspace_file(
    agent_id: str,
    session_id: str,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download one file from an active agent-test session workspace."""
    try:
        from fastapi.responses import FileResponse
        from agent_framework.session_manager import get_session_manager

        session_mgr = get_session_manager()
        session = session_mgr.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found or expired")

        if session.user_id != UUID(current_user.user_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this session",
            )
        if str(session.agent_id) != agent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Session {session_id} does not belong to agent {agent_id}",
            )

        file_path, relative_path = _resolve_safe_workspace_path(session.workdir, path)
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="Workspace file not found")

        session.touch()
        filename = file_path.name or (
            relative_path.rsplit("/", 1)[-1] if relative_path else "download"
        )
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        headers = {
            "Content-Disposition": _build_download_content_disposition(
                filename,
                disposition="attachment",
            )
        }
        return FileResponse(
            path=file_path, media_type=media_type, filename=filename, headers=headers
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to download workspace file from session {session_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download workspace file: {str(e)}",
        )


# ============================================================================
# Agent Skills Configuration Endpoints
# ============================================================================


class AgentSkillsResponse(BaseModel):
    """Response model for agent skills configuration."""

    agent_id: str
    configured_skills: List[str] = Field(
        description="List of skill names configured for this agent"
    )
    available_skills: List[Dict[str, str]] = Field(description="List of all available skills")


@router.get("/{agent_id}/skills", response_model=AgentSkillsResponse)
async def get_agent_skills(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get agent's configured skills and available skills.

    Returns:
        - configured_skills: Skills currently configured for this agent (in capabilities)
        - available_skills: All skills available in the system
    """
    try:
        agent_uuid = UUID(agent_id)
        registry = get_agent_registry()

        # Get agent info
        agent_info = registry.get_agent(agent_uuid)
        if not agent_info:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Check ownership
        if str(agent_info.owner_user_id) != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this agent")

        # Get all available skills from database
        from database.connection import get_db_session
        from database.models import Skill

        available_skills = []
        with get_db_session() as session:
            skills = session.query(Skill).filter(Skill.is_active == True).order_by(Skill.name).all()

            for skill in skills:
                available_skills.append(
                    {
                        "skill_id": str(skill.skill_id),
                        "name": skill.name,
                        "description": skill.description,
                        "skill_type": skill.skill_type,
                        "version": skill.version,
                    }
                )

        available_skill_names = {item["name"] for item in available_skills}
        configured_skills = [
            name for name in (agent_info.capabilities or []) if name in available_skill_names
        ]
        if agent_info.agent_type == "mission_temp_worker":
            configured_skills = []

        return AgentSkillsResponse(
            agent_id=agent_id,
            configured_skills=configured_skills,
            available_skills=available_skills,
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get agent skills: {str(e)}")


class UpdateAgentSkillsRequest(BaseModel):
    """Request model for updating agent skills."""

    skill_names: List[str] = Field(description="List of skill names to configure for this agent")


@router.put("/{agent_id}/skills", response_model=AgentResponse)
async def update_agent_skills(
    agent_id: str,
    request: UpdateAgentSkillsRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update agent's configured skills.

    This updates the agent's capabilities list with the selected skills.
    The agent will load these skills on next initialization.
    """
    try:
        agent_uuid = UUID(agent_id)
        registry = get_agent_registry()

        # Get agent info
        agent_info = registry.get_agent(agent_uuid)
        if not agent_info:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Check ownership
        if str(agent_info.owner_user_id) != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to modify this agent")

        # Validate that all skill names exist
        from database.connection import get_db_session
        from database.models import Skill

        with get_db_session() as session:
            for skill_name in request.skill_names:
                skill = (
                    session.query(Skill)
                    .filter(Skill.name == skill_name, Skill.is_active == True)
                    .first()
                )

                if not skill:
                    raise HTTPException(
                        status_code=400, detail=f"Skill '{skill_name}' not found or not active"
                    )

        # Update agent capabilities
        updated_agent = registry.update_agent(agent_uuid, capabilities=request.skill_names)

        if not updated_agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Clear agent from cache to force reload with new skills
        cache_key = f"{agent_id}:{current_user.user_id}"
        if cache_key in _agent_cache:
            del _agent_cache[cache_key]
            logger.info(f"Cleared agent cache after skills update: {agent_id}")

        logger.info(
            f"Updated agent skills: {agent_id}",
            extra={
                "agent_id": agent_id,
                "skill_count": len(request.skill_names),
                "skills": request.skill_names,
            },
        )

        task_stats = _collect_agent_task_stats([updated_agent.agent_id]).get(
            updated_agent.agent_id, _default_agent_task_stats()
        )

        # Return updated agent info
        return AgentResponse(
            id=str(updated_agent.agent_id),
            name=updated_agent.name,
            type=updated_agent.agent_type,
            avatar=_resolve_agent_avatar(updated_agent.avatar),
            skills=_public_agent_skills(updated_agent.agent_type, updated_agent.capabilities),
            status=updated_agent.status,
            systemPrompt=updated_agent.system_prompt,
            currentTask=None,
            tasksExecuted=task_stats["tasksExecuted"],
            tasksCompleted=task_stats["tasksCompleted"],
            tasksFailed=task_stats["tasksFailed"],
            completionRate=task_stats["completionRate"],
            uptime="0h 0m",
            model=updated_agent.llm_model,
            provider=updated_agent.llm_provider,
            temperature=updated_agent.temperature,
            maxTokens=updated_agent.max_tokens,
            topP=updated_agent.top_p,
            accessLevel=updated_agent.access_level,
            allowedKnowledge=updated_agent.allowed_knowledge,
            allowedMemory=updated_agent.allowed_memory,
            topK=updated_agent.top_k,
            similarityThreshold=updated_agent.similarity_threshold,
            departmentId=str(updated_agent.department_id) if updated_agent.department_id else None,
            createdAt=updated_agent.created_at,
            updatedAt=updated_agent.updated_at,
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid agent ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update agent skills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update agent skills: {str(e)}")
