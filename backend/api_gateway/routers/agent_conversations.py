"""Persistent agent conversation endpoints."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import logging
import mimetypes
import queue
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_

from access_control.permissions import CurrentUser, get_current_user
from agent_framework.agent_conversation_runner import (
    generate_conversation_title,
    initialize_chat_agent,
)
from agent_framework.conversation_execution import (
    ConversationExecutionPrincipal,
    build_conversation_execution_principal,
)
from agent_framework.conversation_history_compaction import (
    get_conversation_history_compaction_service,
)
from agent_framework.conversation_storage_cleanup import (
    collect_conversation_storage_refs,
    delete_object_references,
    extract_attachment_storage_refs,
)
from agent_framework.conversation_workspace_decay import get_conversation_workspace_decay_service
from agent_framework.persistent_conversations import (
    build_default_conversation_title,
    get_persistent_conversation_runtime_service,
    is_default_conversation_title,
)
from agent_framework.runtime_policy import (
    ExecutionProfile,
    is_agent_test_chat_unified_runtime_enabled,
)
from agent_framework.tools.manage_schedule_tool import (
    ScheduleToolContext,
    clear_schedule_tool_context,
    consume_created_schedule_events,
    set_schedule_tool_context,
)
from agent_scheduling.service import build_schedule_created_event
from api_gateway.routers import agents as agents_router
from database.connection import get_db_session
from database.models import (
    Agent,
    AgentConversation,
    AgentConversationHistorySummary,
    AgentChannelPublication,
    AgentConversationMessageArchive,
    AgentConversationMessage,
    AgentConversationSnapshot,
)
from object_storage.minio_client import get_minio_client
from shared.logging import get_logger
from shared.secret_crypto import encrypt_text

logger = get_logger(__name__)
router = APIRouter()


ConversationChunkCallback = Callable[[Dict[str, Any]], Awaitable[None] | None]


class AgentConversationSummaryResponse(BaseModel):
    id: str
    agentId: str
    ownerUserId: str
    title: str
    status: str
    source: str
    latestSnapshotId: Optional[str] = None
    latestSnapshotStatus: Optional[str] = None
    storageTier: str = "hot"
    archivedAt: Optional[datetime] = None
    deleteAfter: Optional[datetime] = None
    workspaceBytes: int = 0
    workspaceFileCount: int = 0
    compactedMessageCount: int = 0
    lastMessageAt: Optional[datetime] = None
    lastMessagePreview: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime


class AgentConversationDetailResponse(AgentConversationSummaryResponse):
    latestSnapshotGeneration: Optional[int] = None


class AgentConversationHistorySummaryResponse(BaseModel):
    summaryText: str
    summaryJson: Optional[Dict[str, List[str]]] = None
    rawMessageCount: int = 0
    coversUntilMessageId: Optional[str] = None
    coversUntilCreatedAt: Optional[datetime] = None


class AgentConversationArchiveResponse(BaseModel):
    archiveId: str
    conversationId: str
    startMessageId: Optional[str] = None
    endMessageId: Optional[str] = None
    messageCount: int
    status: str
    expiresAt: Optional[datetime] = None
    createdAt: datetime


class AgentConversationMessageResponse(BaseModel):
    id: str
    conversationId: str
    role: str
    contentText: str
    contentJson: Optional[Dict[str, Any]] = None
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    source: str
    externalEventId: Optional[str] = None
    createdAt: datetime


class AgentConversationListResponse(BaseModel):
    items: List[AgentConversationSummaryResponse]
    total: int
    hasMore: bool = False
    nextCursor: Optional[str] = None


class AgentConversationMessagesListResponse(BaseModel):
    items: List[AgentConversationMessageResponse]
    total: int
    historySummary: Optional[AgentConversationHistorySummaryResponse] = None
    compactedMessageCount: int = 0
    archivedSegmentCount: int = 0
    recentWindowSize: int = 0
    hasOlderLiveMessages: bool = False
    olderCursor: Optional[str] = None


class AgentConversationArchiveListResponse(BaseModel):
    items: List[AgentConversationArchiveResponse]
    total: int


class CreateConversationResponse(BaseModel):
    conversation: AgentConversationSummaryResponse


class UpdateConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)


class ReleaseConversationRuntimeResponse(BaseModel):
    success: bool


class FeishuPublicationConfigRequest(BaseModel):
    appId: str = Field(..., min_length=1, max_length=255)
    appSecret: Optional[str] = Field(default=None, max_length=2000)


class FeishuPublicationResponse(BaseModel):
    publicationId: Optional[str] = None
    channelType: str = "feishu"
    deliveryMode: str = "long_connection"
    status: str
    channelIdentity: Optional[str] = None
    appId: Optional[str] = None
    hasAppSecret: bool = False
    connectionState: str = "inactive"
    connectionStatusUpdatedAt: Optional[datetime] = None
    lastConnectedAt: Optional[datetime] = None
    lastEventAt: Optional[datetime] = None
    lastErrorAt: Optional[datetime] = None
    lastErrorMessage: Optional[str] = None


def _latest_snapshot_status_payload(
    session,
    conversation_id: UUID,
) -> tuple[Optional[str], Optional[int], Optional[str]]:
    latest_snapshot = (
        session.query(AgentConversationSnapshot)
        .filter(AgentConversationSnapshot.conversation_id == conversation_id)
        .order_by(AgentConversationSnapshot.generation.desc())
        .first()
    )
    if latest_snapshot is None:
        return None, None, None
    return (
        latest_snapshot.snapshot_status,
        int(latest_snapshot.generation or 0),
        str(latest_snapshot.snapshot_id),
    )


def _last_message_preview(session, conversation_id: UUID) -> Optional[str]:
    message = (
        session.query(AgentConversationMessage)
        .filter(AgentConversationMessage.conversation_id == conversation_id)
        .order_by(AgentConversationMessage.created_at.desc())
        .first()
    )
    if not message:
        return None
    normalized = " ".join(str(message.content_text or "").split()).strip()
    if len(normalized) <= 80:
        return normalized or None
    return normalized[:77] + "..."


def _display_conversation_title(conversation: AgentConversation) -> str:
    title = str(conversation.title or "").strip()
    if is_default_conversation_title(title):
        return build_default_conversation_title(conversation.created_at)
    return title or build_default_conversation_title(conversation.created_at)


def _serialize_conversation_summary(
    session, conversation: AgentConversation
) -> AgentConversationSummaryResponse:
    latest_snapshot_status, latest_generation, latest_snapshot_id = _latest_snapshot_status_payload(
        session,
        conversation.conversation_id,
    )
    return AgentConversationSummaryResponse(
        id=str(conversation.conversation_id),
        agentId=str(conversation.agent_id),
        ownerUserId=str(conversation.owner_user_id),
        title=_display_conversation_title(conversation),
        status=conversation.status,
        source=conversation.source,
        latestSnapshotId=latest_snapshot_id
        or (str(conversation.latest_snapshot_id) if conversation.latest_snapshot_id else None),
        latestSnapshotStatus=latest_snapshot_status,
        storageTier=str(conversation.storage_tier or "hot"),
        archivedAt=conversation.archived_at,
        deleteAfter=conversation.delete_after,
        workspaceBytes=int(conversation.workspace_bytes_estimate or 0),
        workspaceFileCount=int(conversation.workspace_file_count_estimate or 0),
        compactedMessageCount=int(conversation.compacted_message_count or 0),
        lastMessageAt=conversation.last_message_at,
        lastMessagePreview=_last_message_preview(session, conversation.conversation_id),
        createdAt=conversation.created_at,
        updatedAt=conversation.updated_at,
    )


def _serialize_conversation_detail(
    session, conversation: AgentConversation
) -> AgentConversationDetailResponse:
    summary = _serialize_conversation_summary(session, conversation)
    latest_snapshot_status, latest_generation, latest_snapshot_id = _latest_snapshot_status_payload(
        session,
        conversation.conversation_id,
    )
    payload = summary.dict()
    payload["latestSnapshotStatus"] = latest_snapshot_status
    payload["latestSnapshotGeneration"] = latest_generation
    payload["latestSnapshotId"] = latest_snapshot_id or summary.latestSnapshotId
    return AgentConversationDetailResponse(**payload)


def _serialize_message(message: AgentConversationMessage) -> AgentConversationMessageResponse:
    content_json = (
        dict(message.content_json or {}) if isinstance(message.content_json, dict) else None
    )
    attachments = (
        list(message.attachments_json or []) if isinstance(message.attachments_json, list) else []
    )
    return AgentConversationMessageResponse(
        id=str(message.message_id),
        conversationId=str(message.conversation_id),
        role=message.role,
        contentText=message.content_text,
        contentJson=content_json,
        attachments=attachments,
        source=message.source,
        externalEventId=message.external_event_id,
        createdAt=message.created_at,
    )


def _serialize_history_summary(
    summary: AgentConversationHistorySummary,
) -> AgentConversationHistorySummaryResponse:
    summary_json = (
        {key: [str(item) for item in value] for key, value in summary.summary_json.items()}
        if isinstance(summary.summary_json, dict)
        else None
    )
    return AgentConversationHistorySummaryResponse(
        summaryText=str(summary.summary_text or ""),
        summaryJson=summary_json,
        rawMessageCount=int(summary.raw_message_count or 0),
        coversUntilMessageId=(
            str(summary.covers_until_message_id) if summary.covers_until_message_id else None
        ),
        coversUntilCreatedAt=summary.covers_until_created_at,
    )


def _serialize_message_archive(
    archive: AgentConversationMessageArchive,
) -> AgentConversationArchiveResponse:
    return AgentConversationArchiveResponse(
        archiveId=str(archive.archive_id),
        conversationId=str(archive.conversation_id),
        startMessageId=str(archive.start_message_id) if archive.start_message_id else None,
        endMessageId=str(archive.end_message_id) if archive.end_message_id else None,
        messageCount=int(archive.message_count or 0),
        status=str(archive.status or "ready"),
        expiresAt=archive.expires_at,
        createdAt=archive.created_at,
    )


def _build_history_summary_response_from_window(
    history_window: Dict[str, Any],
) -> Optional[AgentConversationHistorySummaryResponse]:
    summary_row = history_window.get("summary_row")
    if summary_row is not None:
        return _serialize_history_summary(summary_row)

    summary_text = str(history_window.get("summary_text") or "").strip()
    if not summary_text:
        return None

    summary_json = history_window.get("summary_json")
    normalized_summary_json = (
        {str(key): [str(item) for item in value] for key, value in summary_json.items()}
        if isinstance(summary_json, dict)
        else None
    )
    return AgentConversationHistorySummaryResponse(
        summaryText=summary_text,
        summaryJson=normalized_summary_json,
        rawMessageCount=int(history_window.get("older_message_count") or 0),
        coversUntilMessageId=None,
        coversUntilCreatedAt=None,
    )


def _parse_optional_datetime(value: Any) -> Optional[datetime]:
    if value in {None, ""}:
        return None
    if isinstance(value, datetime):
        return value
    try:
        normalized = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except (TypeError, ValueError):
        return None


def _encode_cursor(payload: Dict[str, Any]) -> str:
    normalized: Dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        else:
            normalized[key] = str(value)
    raw = json.dumps(normalized, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def _decode_cursor(cursor: Optional[str]) -> Dict[str, Any]:
    if not cursor:
        return {}
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        data = json.loads(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Invalid pagination cursor")
    return data


def _decode_conversation_cursor(cursor: Optional[str]) -> Optional[tuple[datetime, UUID]]:
    payload = _decode_cursor(cursor)
    if not payload:
        return None
    updated_at = _parse_optional_datetime(payload.get("updatedAt"))
    conversation_id = payload.get("conversationId")
    if updated_at is None or conversation_id in {None, ""}:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor")
    try:
        return updated_at, UUID(str(conversation_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc


def _decode_message_cursor(cursor: Optional[str]) -> Optional[tuple[datetime, UUID]]:
    payload = _decode_cursor(cursor)
    if not payload:
        return None
    created_at = _parse_optional_datetime(payload.get("createdAt"))
    message_id = payload.get("messageId")
    if created_at is None or message_id in {None, ""}:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor")
    try:
        return created_at, UUID(str(message_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid pagination cursor") from exc


def _workspace_entry_signature(entry: Dict[str, Any]) -> tuple[bool, int, str]:
    return (
        bool(entry.get("is_directory")),
        int(entry.get("size") or 0),
        str(entry.get("modified_at") or ""),
    )


def _diff_workspace_entries(
    before_entries: List[Dict[str, Any]],
    after_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    before_index = {
        str(entry.get("path") or "").strip(): _workspace_entry_signature(entry)
        for entry in before_entries
        if str(entry.get("path") or "").strip()
    }
    delta: List[Dict[str, Any]] = []
    for entry in after_entries:
        path = str(entry.get("path") or "").strip()
        if not path:
            continue
        if before_index.get(path) != _workspace_entry_signature(entry):
            delta.append(entry)
    return delta


_WORKSPACE_REFERENCE_PATTERN = re.compile(
    r"`?(?P<path>(?:/workspace/|workspace/)?(?:output|shared|input)/[^\s`<>\[\](){}\"'，。；;！？!?]+)`?"
)
_WORKSPACE_SAVE_CLAIM_PATTERN = re.compile(
    r"(已保存(?:到|至)?|保存到文档中|保存到文件中|保存在|已写入|写入到|已创建|已生成|已导出|输出到|saved(?:\s+to)?|written\s+to|created|generated|exported)",
    re.IGNORECASE,
)
_WORKSPACE_LOCATION_TOKENS = (
    "文件路径",
    "文件位置",
    "完整路径",
    "文件信息",
    "文件详情",
    "保存位置",
    "file path",
    "saved to file",
)
_WORKSPACE_FILE_HINT_TOKENS = (
    "文件",
    "文档",
    "报告",
    "附件",
    "file",
    "document",
    "report",
    "attachment",
)
_WORKSPACE_ACCESS_TOKENS = (
    "直接打开",
    "访问",
    "查看",
    "下载",
    "分享",
    "打印",
    "open",
    "view",
    "download",
    "share",
    "print",
)
_WORKSPACE_FILE_SECTION_TOKENS = (
    "文件位置",
    "文件信息",
    "文件详情",
    "使用方式",
)


def _normalize_workspace_artifact_path(value: Any) -> Optional[str]:
    raw = str(value or "").replace("\\", "/").strip().strip("`")
    raw = raw.rstrip(",，。；;!！?？]}>")
    if raw.startswith("/workspace/"):
        raw = raw[len("/workspace/") :]
    elif raw.startswith("workspace/"):
        raw = raw[len("workspace/") :]
    raw = raw.lstrip("/")
    if not raw or ".." in raw:
        return None
    if not raw.startswith(("output/", "shared/", "input/")):
        return None
    return raw


def _extract_workspace_reference_paths(value: str) -> set[str]:
    paths: set[str] = set()
    for match in _WORKSPACE_REFERENCE_PATTERN.finditer(str(value or "")):
        normalized = _normalize_workspace_artifact_path(match.group("path"))
        if normalized:
            paths.add(normalized)
    return paths


def _is_workspace_path_only_block(value: str) -> bool:
    if not _extract_workspace_reference_paths(value):
        return False
    stripped = _WORKSPACE_REFERENCE_PATTERN.sub("", str(value or ""))
    stripped = re.sub(r"[*_`>#\-:：，。；;!！?？\[\](){}\s]+", "", stripped)
    return not stripped


def _sanitize_unverified_workspace_save_claims(
    text: str,
    *,
    artifact_delta_entries: List[Dict[str, Any]],
) -> str:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return ""

    verified_paths = {
        normalized_path
        for entry in artifact_delta_entries
        if (normalized_path := _normalize_workspace_artifact_path(entry.get("path"))) is not None
    }

    sanitized_blocks: List[str] = []
    drop_following_file_boilerplate = False
    for raw_block in re.split(r"\n{2,}", normalized_text):
        block = str(raw_block or "").strip()
        if not block:
            continue

        block_paths = _extract_workspace_reference_paths(block)
        unverified_paths = block_paths - verified_paths
        lowered_block = block.lower()
        has_save_claim = bool(_WORKSPACE_SAVE_CLAIM_PATTERN.search(block))
        has_location_token = any(token in block for token in _WORKSPACE_LOCATION_TOKENS) or any(
            token in lowered_block for token in _WORKSPACE_LOCATION_TOKENS if token.isascii()
        )
        has_file_hint = any(token in block for token in _WORKSPACE_FILE_HINT_TOKENS) or any(
            token in lowered_block for token in _WORKSPACE_FILE_HINT_TOKENS if token.isascii()
        )
        has_access_hint = any(token in block for token in _WORKSPACE_ACCESS_TOKENS) or any(
            token in lowered_block for token in _WORKSPACE_ACCESS_TOKENS if token.isascii()
        )
        short_file_section_heading = len(block) <= 48 and any(
            token in block for token in _WORKSPACE_FILE_SECTION_TOKENS
        )

        should_drop = False
        if unverified_paths and (has_save_claim or has_location_token):
            should_drop = True
        elif not verified_paths and has_save_claim and has_file_hint:
            should_drop = True
        elif drop_following_file_boilerplate and (
            short_file_section_heading
            or (unverified_paths and (has_access_hint or _is_workspace_path_only_block(block)))
        ):
            should_drop = True
        elif not verified_paths and short_file_section_heading:
            should_drop = True

        if should_drop:
            drop_following_file_boilerplate = True
            continue

        drop_following_file_boilerplate = False
        sanitized_blocks.append(block)

    cleaned_blocks: List[str] = []
    for block in sanitized_blocks:
        if re.fullmatch(r"[-*_]{3,}", block):
            if not cleaned_blocks or re.fullmatch(r"[-*_]{3,}", cleaned_blocks[-1]):
                continue
            cleaned_blocks.append("---")
            continue
        cleaned_blocks.append(block)

    while cleaned_blocks and cleaned_blocks[0] == "---":
        cleaned_blocks.pop(0)
    while cleaned_blocks and cleaned_blocks[-1] == "---":
        cleaned_blocks.pop()

    return "\n\n".join(cleaned_blocks).strip()


def _get_feishu_runtime_state(publication: AgentChannelPublication | None) -> dict[str, Any]:
    if publication is None:
        return {}
    config = (
        dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
    )
    runtime = config.get("long_connection_runtime")
    return dict(runtime or {}) if isinstance(runtime, dict) else {}


def _build_absolute_url(request: Request, path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}{path}"


def _load_feishu_publication(session, agent_id: UUID) -> AgentChannelPublication | None:
    return (
        session.query(AgentChannelPublication)
        .filter(AgentChannelPublication.agent_id == agent_id)
        .filter(AgentChannelPublication.channel_type == "feishu")
        .first()
    )


def _serialize_feishu_publication(
    publication: AgentChannelPublication | None,
    *,
    request: Request,
) -> FeishuPublicationResponse:
    if publication is None:
        return FeishuPublicationResponse(status="draft")

    config = (
        dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
    )
    runtime = _get_feishu_runtime_state(publication)
    secrets = (
        dict(publication.secret_encrypted_json or {})
        if isinstance(publication.secret_encrypted_json, dict)
        else {}
    )
    from api_gateway.routers.integrations import _publication_secrets

    decrypted_secrets = _publication_secrets(publication)
    return FeishuPublicationResponse(
        publicationId=str(publication.publication_id),
        status=publication.status,
        channelIdentity=publication.channel_identity,
        appId=config.get("app_id"),
        hasAppSecret=bool(decrypted_secrets.get("app_secret")),
        connectionState=(
            str(runtime.get("state") or "inactive")
            if publication.status == "published"
            else "inactive"
        ),
        connectionStatusUpdatedAt=_parse_optional_datetime(runtime.get("updated_at")),
        lastConnectedAt=_parse_optional_datetime(runtime.get("last_connected_at")),
        lastEventAt=_parse_optional_datetime(runtime.get("last_event_at")),
        lastErrorAt=_parse_optional_datetime(runtime.get("last_error_at")),
        lastErrorMessage=str(runtime.get("last_error_message") or "").strip() or None,
    )


def _upsert_feishu_publication(
    *,
    session,
    agent_id: UUID,
    payload: FeishuPublicationConfigRequest,
) -> AgentChannelPublication:
    publication = _load_feishu_publication(session, agent_id)
    now = datetime.now(timezone.utc)
    if publication is None:
        publication = AgentChannelPublication(
            agent_id=agent_id,
            channel_type="feishu",
            status="draft",
        )
        session.add(publication)
        session.flush()

    config = (
        dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
    )
    config["app_id"] = payload.appId.strip()
    config.pop("bot_name", None)
    config.pop("tenant_key", None)
    publication.config_json = config
    publication.channel_identity = config["app_id"]

    secrets = (
        dict(publication.secret_encrypted_json or {})
        if isinstance(publication.secret_encrypted_json, dict)
        else {}
    )
    if payload.appSecret:
        secrets["app_secret"] = encrypt_text(payload.appSecret.strip())
    secrets.pop("verification_token", None)
    secrets.pop("encrypt_key", None)
    publication.secret_encrypted_json = secrets or None
    publication.updated_at = now
    return publication


def _load_owned_conversation(
    session,
    *,
    agent_id: str,
    conversation_id: str,
    current_user: CurrentUser,
    required_agent_access: str = "read",
) -> AgentConversation:
    try:
        conversation_uuid = UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid conversation id") from exc

    agents_router._get_accessible_agent_or_raise(
        agent_id,
        current_user,
        access_type=required_agent_access,
    )

    row = (
        session.query(AgentConversation)
        .filter(AgentConversation.conversation_id == conversation_uuid)
        .filter(AgentConversation.agent_id == UUID(agent_id))
        .filter(AgentConversation.owner_user_id == UUID(current_user.user_id))
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


def _parse_conversation_uuid(conversation_id: str) -> UUID:
    try:
        return UUID(conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid conversation id") from exc


def _load_agent_for_conversation(agent_id: UUID) -> Agent:
    with get_db_session() as session:
        row = session.query(Agent).filter(Agent.agent_id == agent_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        return row


async def _emit_chunk(
    callback: ConversationChunkCallback | None,
    chunk: Dict[str, Any],
) -> None:
    if callback is None:
        return
    result = callback(chunk)
    if asyncio.iscoroutine(result):
        await result


def _normalize_attachments_for_storage(
    file_refs: List[agents_router.FileReference],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for file_ref in file_refs:
        items.append(
            {
                "name": file_ref.name,
                "type": file_ref.type,
                "size": file_ref.size,
                "content_type": file_ref.content_type,
                "storage_ref": (
                    f"minio:{file_ref.path.split('/', 1)[0]}:{file_ref.path.split('/', 1)[1]}"
                    if "/" in file_ref.path
                    else None
                ),
                "workspace_path": file_ref.workspace_path,
            }
        )
    return items


async def _prepare_uploaded_files(
    *,
    agent_id: str,
    current_user: CurrentUser,
    files: List[UploadFile],
) -> tuple[List[agents_router.FileReference], Dict[str, bytes]]:
    file_refs: List[agents_router.FileReference] = []
    attachment_payloads: Dict[str, bytes] = {}
    if not files:
        return file_refs, attachment_payloads

    minio_client = get_minio_client()
    for upload in files:
        file_data = await upload.read()
        file_stream = io.BytesIO(file_data)
        file_name = upload.filename or "unnamed"
        original_content_type = agents_router._normalize_attachment_content_type(
            upload.content_type
        )
        content_type = agents_router._infer_effective_content_type(file_name, original_content_type)
        file_type = agents_router._infer_attachment_type(file_name, content_type)
        bucket_type = agents_router._infer_attachment_bucket_type(file_name, content_type)
        extracted_text: Optional[str] = None
        extraction_error: Optional[str] = None
        if file_type in {"document", "other"}:
            extracted_text, extraction_error = await asyncio.to_thread(
                agents_router._extract_attachment_text,
                file_name,
                content_type,
                file_data,
            )
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
            },
        )
        file_ref = agents_router.FileReference(
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
    return file_refs, attachment_payloads


async def _build_history_content_from_row(
    message: AgentConversationMessage,
) -> str | List[Dict[str, Any]] | None:
    text = str(message.content_text or "").strip()
    attachments = (
        list(message.attachments_json or []) if isinstance(message.attachments_json, list) else []
    )
    if not attachments:
        return text or None

    multimodal_items: List[Dict[str, Any]] = []
    if text:
        multimodal_items.append({"type": "text", "text": text})

    minio = get_minio_client()
    for attachment in attachments:
        if str(attachment.get("type") or "").lower() != "image":
            continue
        storage_ref = attachment.get("storage_ref")
        parsed_ref = minio.parse_object_reference(storage_ref)
        if not parsed_ref:
            continue
        bucket_name, object_key = parsed_ref
        try:
            image_stream, _ = minio.download_file(bucket_name, object_key)
            payload = image_stream.read()
            content_type = str(attachment.get("content_type") or "image/png")
            extension = content_type.split("/")[-1] or "png"
            encoded = base64.b64encode(payload).decode("utf-8")
            multimodal_items.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{content_type};base64,{encoded}"},
                }
            )
        except Exception as exc:
            logger.warning("Failed to rebuild image attachment context: %s", exc)

    if not multimodal_items:
        return text or None
    if len(multimodal_items) == 1 and multimodal_items[0]["type"] == "text":
        return text or None
    return multimodal_items


async def _build_conversation_history(
    conversation_id: UUID,
) -> tuple[List[Dict[str, Any]], dict[str, Any]]:
    history_window = get_conversation_history_compaction_service().load_runtime_window(
        conversation_id
    )
    history: List[Dict[str, Any]] = []
    summary_text = str(history_window.get("summary_text") or "").strip()
    if summary_text:
        history.append(
            {
                "role": "system",
                "content": (
                    "Earlier persistent conversation summary. "
                    "Use this as durable context, and prefer newer raw messages when they conflict.\n\n"
                    f"{summary_text}"
                ),
            }
        )
    for message in list(history_window.get("recent_messages") or []):
        if message.role not in {"user", "assistant"}:
            continue
        content = await _build_history_content_from_row(message)
        if not content:
            continue
        history.append({"role": message.role, "content": content})
    return _sanitize_conversation_history_messages(history), history_window


def _sanitize_conversation_history_messages(raw_history: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_history, list):
        return []

    sanitized: List[Dict[str, Any]] = []
    for entry in raw_history:
        if not isinstance(entry, dict):
            continue
        role = str(entry.get("role") or "").strip().lower()
        if role not in {"user", "assistant", "system"}:
            continue
        normalized_content = agents_router._normalize_history_content(entry.get("content"))
        if isinstance(normalized_content, list):
            content = normalized_content
        else:
            content = str(normalized_content or "").strip()
        if not content:
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized


def _normalize_workspace_attachment_path(value: Any) -> Optional[str]:
    raw = str(value or "").replace("\\", "/").strip().lstrip("/")
    if raw.startswith("workspace/"):
        raw = raw[len("workspace/") :]
    normalized = raw.strip("/")
    if not normalized or ".." in normalized:
        return None
    if not normalized.startswith("input/"):
        return None
    return normalized


def _rematerialize_conversation_attachments_to_workspace(
    conversation_id: UUID,
    workdir: Path,
) -> tuple[int, List[str]]:
    with get_db_session() as session:
        rows = (
            session.query(AgentConversationMessage.attachments_json)
            .filter(AgentConversationMessage.conversation_id == conversation_id)
            .order_by(AgentConversationMessage.created_at.asc())
            .all()
        )

    minio = get_minio_client()
    written = 0
    errors: List[str] = []
    seen_paths: set[str] = set()
    for row in rows:
        attachments = row[0] if isinstance(row, tuple) else row
        if not isinstance(attachments, list):
            continue
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            workspace_path = _normalize_workspace_attachment_path(attachment.get("workspace_path"))
            storage_ref = str(attachment.get("storage_ref") or "").strip()
            if not workspace_path or not storage_ref or workspace_path in seen_paths:
                continue
            seen_paths.add(workspace_path)
            destination_path, _ = agents_router._resolve_safe_workspace_path(
                workdir, workspace_path
            )
            if destination_path.exists():
                continue
            parsed = minio.parse_object_reference(storage_ref)
            if not parsed:
                errors.append(f"{workspace_path}: invalid storage ref")
                continue
            bucket_name, object_key = parsed
            try:
                file_stream, _ = minio.download_file(bucket_name, object_key)
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                destination_path.write_bytes(file_stream.read())
                written += 1
            except Exception as exc:
                errors.append(f"{workspace_path}: {exc}")
    return written, errors


def _message_source_label(source: str) -> str:
    normalized = str(source or "").strip().lower()
    return normalized if normalized in {"web", "feishu", "schedule"} else "web"


def _conversation_context_origin_surface(
    source: str,
    explicit_origin_surface: Optional[str],
) -> str:
    normalized = str(explicit_origin_surface or "").strip().lower()
    if normalized in {"persistent_chat", "test_chat", "feishu", "schedule_page"}:
        return normalized
    return "feishu" if _message_source_label(source) == "feishu" else "persistent_chat"


def _build_runtime_chunk(
    runtime: Any,
    *,
    is_new_runtime: bool,
) -> Dict[str, Any]:
    return {
        "type": "runtime",
        "runtime_session_id": runtime.runtime_session_id,
        "is_new_runtime": bool(is_new_runtime),
        "restored_from_snapshot": bool(is_new_runtime and runtime.restored_from_snapshot),
        "snapshot_generation": runtime.snapshot_generation,
        "use_sandbox": runtime.use_sandbox,
    }


def _persist_message(
    *,
    conversation_id: UUID,
    role: str,
    content_text: str,
    content_json: Optional[Dict[str, Any]],
    attachments: Optional[List[Dict[str, Any]]],
    source: str,
    external_event_id: Optional[str] = None,
) -> AgentConversationMessage:
    with get_db_session() as session:
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == conversation_id)
            .first()
        )
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        message = AgentConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content_text=content_text,
            content_json=content_json or None,
            attachments_json=attachments or None,
            source=_message_source_label(source),
            external_event_id=external_event_id,
        )
        session.add(message)
        now = datetime.now(timezone.utc)
        conversation.last_message_at = now
        conversation.updated_at = now
        if conversation.storage_tier == "archived":
            conversation.storage_tier = "hot"
            conversation.archived_at = None
            conversation.delete_after = None
        session.commit()
        session.refresh(message)
        return message


def _delete_message_and_cleanup_storage(message_id: UUID) -> bool:
    attachment_refs: set[str] = set()
    with get_db_session() as session:
        message = (
            session.query(AgentConversationMessage)
            .filter(AgentConversationMessage.message_id == message_id)
            .first()
        )
        if message is None:
            return False

        attachment_refs = extract_attachment_storage_refs(message.attachments_json)
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == message.conversation_id)
            .first()
        )

        session.delete(message)
        session.flush()

        latest_message = (
            session.query(AgentConversationMessage)
            .filter(AgentConversationMessage.conversation_id == message.conversation_id)
            .order_by(AgentConversationMessage.created_at.desc())
            .first()
        )
        if conversation is not None:
            conversation.last_message_at = (
                latest_message.created_at if latest_message and latest_message.created_at else None
            )
            conversation.updated_at = datetime.now(timezone.utc)
        session.commit()

    if attachment_refs:
        delete_object_references(attachment_refs)
    return True


def _update_conversation_title(conversation_id: UUID, title: str) -> None:
    normalized = " ".join(str(title or "").split()).strip()
    if not normalized:
        return
    with get_db_session() as session:
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == conversation_id)
            .first()
        )
        if conversation is None or not is_default_conversation_title(conversation.title):
            return
        conversation.title = normalized[:255]
        conversation.updated_at = datetime.now(timezone.utc)
        session.commit()


def _message_exists_for_external_event(
    *,
    conversation_id: UUID,
    external_event_id: str,
) -> bool:
    if not external_event_id:
        return False
    with get_db_session() as session:
        row = (
            session.query(AgentConversationMessage)
            .filter(AgentConversationMessage.conversation_id == conversation_id)
            .filter(AgentConversationMessage.external_event_id == external_event_id)
            .first()
        )
        return row is not None


async def _detect_model_supports_vision(agent_info: Agent) -> bool:
    try:
        from llm_providers.db_manager import ProviderDBManager
        from llm_providers.model_metadata import EnhancedModelCapabilityDetector

        provider_name = agent_info.llm_provider or "ollama"
        model_name = agent_info.llm_model or "llama3.2:latest"
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            provider = db_manager.get_provider(provider_name)
            if provider and provider.model_metadata and model_name in provider.model_metadata:
                metadata = provider.model_metadata[model_name]
                return bool(metadata.get("supports_vision"))
        detector = EnhancedModelCapabilityDetector()
        metadata = detector.detect_metadata(model_name, provider_name)
        return bool(metadata.supports_vision)
    except Exception as exc:
        logger.warning("Failed to resolve model vision metadata: %s", exc)
        return False


async def execute_persistent_conversation_turn(
    *,
    conversation: AgentConversation,
    principal: ConversationExecutionPrincipal,
    message: str,
    files: List[UploadFile],
    source: str = "web",
    external_event_id: Optional[str] = None,
    chunk_callback: ConversationChunkCallback | None = None,
    persist_input_message: bool = True,
    input_message_role: str = "user",
    input_message_text: Optional[str] = None,
    input_message_content_json: Optional[Dict[str, Any]] = None,
    execution_task_text: Optional[str] = None,
    execution_intent_text: Optional[str] = None,
    title_seed_text: Optional[str] = None,
    context_origin_surface: Optional[str] = None,
    extra_execution_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    def create_empty_round_data() -> Dict[str, Any]:
        return {
            "thinking": "",
            "content": "",
            "statusMessages": [],
            "retryAttempts": [],
            "errorFeedback": [],
            "stats": None,
        }

    def has_round_activity(round_data: Dict[str, Any]) -> bool:
        return bool(
            round_data["thinking"]
            or round_data["content"].strip()
            or round_data["statusMessages"]
            or round_data["retryAttempts"]
            or round_data["errorFeedback"]
        )

    def build_round_snapshot(round_data: Dict[str, Any], round_number: int) -> Dict[str, Any]:
        snapshot = {
            "roundNumber": round_number,
            "thinking": round_data["thinking"],
            "content": round_data["content"],
            "statusMessages": list(round_data["statusMessages"]),
        }
        if round_data["retryAttempts"]:
            snapshot["retryAttempts"] = list(round_data["retryAttempts"])
        if round_data["errorFeedback"]:
            snapshot["errorFeedback"] = list(round_data["errorFeedback"])
        if round_data["stats"]:
            snapshot["stats"] = dict(round_data["stats"])
        return snapshot

    if external_event_id and _message_exists_for_external_event(
        conversation_id=conversation.conversation_id,
        external_event_id=external_event_id,
    ):
        return {"duplicate": True, "output": "", "artifacts": []}

    user_text = str(message or "").strip()
    persisted_input_text = str(
        input_message_text if input_message_text is not None else user_text
    ).strip()
    task_intent_text = str(
        execution_intent_text if execution_intent_text is not None else user_text
    ).strip()
    title_context_text = str(
        title_seed_text
        if title_seed_text is not None
        else (persisted_input_text or task_intent_text or user_text)
    ).strip()
    normalized_input_role = str(input_message_role or "user").strip().lower()
    if normalized_input_role not in {"user", "assistant", "system"}:
        normalized_input_role = "user"
    resolved_origin_surface = _conversation_context_origin_surface(
        source,
        context_origin_surface,
    )
    principal_user_id = UUID(principal.user_id)
    history, history_window = await _build_conversation_history(conversation.conversation_id)
    runtime_service = get_persistent_conversation_runtime_service()
    runtime, is_new_runtime = await runtime_service.get_or_create_runtime(conversation=conversation)
    await _emit_chunk(chunk_callback, _build_runtime_chunk(runtime, is_new_runtime=is_new_runtime))
    input_message_row: AgentConversationMessage | None = None
    assistant_message_row: AgentConversationMessage | None = None
    uploaded_attachment_refs: set[str] = set()

    def cleanup_incomplete_turn() -> None:
        if assistant_message_row is not None:
            return
        if input_message_row is not None:
            _delete_message_and_cleanup_storage(input_message_row.message_id)
            return
        if uploaded_attachment_refs:
            delete_object_references(uploaded_attachment_refs)

    try:
        from agent_framework.conversation_workspace_decay import (
            ConversationWorkspaceLimitExceeded,
            get_conversation_workspace_decay_service,
        )

        decay_result = get_conversation_workspace_decay_service().decay_workspace(
            conversation_id=conversation.conversation_id,
            workdir=runtime.workdir,
        )
        deleted_paths = list(decay_result.get("deleted_paths") or [])
        if deleted_paths:
            await _emit_chunk(
                chunk_callback,
                {
                    "type": "info",
                    "content": (
                        f"Workspace auto-cleanup removed {len(deleted_paths)} stale file(s) before execution."
                    ),
                },
            )
    except ConversationWorkspaceLimitExceeded as exc:
        raise RuntimeError(str(exc)) from exc

    restored_attachments, restore_errors = _rematerialize_conversation_attachments_to_workspace(
        conversation.conversation_id,
        runtime.workdir,
    )
    if restored_attachments > 0:
        await _emit_chunk(
            chunk_callback,
            {
                "type": "info",
                "content": (
                    f"Restored {restored_attachments} attachment file(s) into /workspace/input/."
                ),
            },
        )
    for error_text in restore_errors:
        await _emit_chunk(
            chunk_callback,
            {
                "type": "info",
                "content": f"Failed to restore one workspace attachment: {error_text}",
            },
        )

    file_refs, attachment_payloads = await _prepare_uploaded_files(
        agent_id=str(conversation.agent_id),
        current_user=build_conversation_execution_principal(
            user_id=principal.user_id,
            role=principal.role,
            username=principal.username,
        ),
        files=files,
    )
    attachments_payload = _normalize_attachments_for_storage(file_refs)
    uploaded_attachment_refs = extract_attachment_storage_refs(attachments_payload)
    if persist_input_message:
        input_message_row = _persist_message(
            conversation_id=conversation.conversation_id,
            role=normalized_input_role,
            content_text=persisted_input_text or "[Attached files]",
            content_json=input_message_content_json,
            attachments=attachments_payload,
            source=source,
            external_event_id=external_event_id,
        )

    if file_refs:
        written_files, materialize_errors = (
            agents_router._materialize_attachment_files_to_workspace(
                runtime.workdir,
                file_refs,
                attachment_payloads,
            )
        )
        if written_files > 0:
            await _emit_chunk(
                chunk_callback,
                {
                    "type": "info",
                    "content": (
                        f"Copied {written_files} uploaded file(s) to /workspace/input/ for agent access."
                    ),
                },
            )
        for error_text in materialize_errors:
            await _emit_chunk(
                chunk_callback,
                {
                    "type": "info",
                    "content": f"Failed to copy one uploaded file to workspace: {error_text}",
                },
            )

    baseline_artifact_entries = agents_router._list_session_workspace_entries(
        runtime.workdir,
        recursive=True,
    )

    agent_info = _load_agent_for_conversation(conversation.agent_id)
    agent = await initialize_chat_agent(
        agent_info=agent_info,
        owner_user_id=principal_user_id,
        max_iterations=agents_router.AGENT_TEST_MAX_ITERATIONS,
    )

    from agent_framework.agent_executor import ExecutionContext, get_agent_executor

    executor = get_agent_executor()
    request_exec_context = ExecutionContext(
        agent_id=conversation.agent_id,
        user_id=principal_user_id,
        user_role=principal.role,
        task_description=user_text,
        additional_context={"execution_context_tag": agents_router.AGENT_TEST_RUNTIME_CONTEXT_TAG},
    )
    context: Dict[str, Any] = {}
    context_debug: Dict[str, Any] = {}
    try:
        context, context_debug = await asyncio.to_thread(
            executor.build_execution_context_with_debug,
            agent,
            request_exec_context,
            top_k=agent_info.top_k or 5,
            knowledge_min_relevance_score=agent_info.similarity_threshold,
        )
        for debug_message in agents_router._build_retrieval_process_messages(context_debug):
            await _emit_chunk(chunk_callback, {"type": "info", "content": debug_message})
    except Exception as exc:
        logger.error("Failed to build conversation execution context: %s", exc, exc_info=True)

    task_base_text = str(
        execution_task_text if execution_task_text is not None else task_intent_text
    ).strip()
    attachment_context = agents_router._build_attachment_prompt_context(
        file_refs, include_image_notes=True
    )
    message_with_attachments = (
        f"{task_base_text}{attachment_context}" if attachment_context else task_base_text
    )
    attachment_workspace_context = agents_router._build_attachment_workspace_context(file_refs)
    user_message = (
        f"{message_with_attachments}{attachment_workspace_context}"
        if attachment_workspace_context
        else message_with_attachments
    )

    multimodal_content = None
    image_refs = [file_ref for file_ref in file_refs if file_ref.type == "image"]
    if image_refs and await _detect_model_supports_vision(agent_info):
        multimodal_content = []
        if user_message:
            multimodal_content.append({"type": "text", "text": user_message})
        minio = get_minio_client()
        for file_ref in image_refs:
            bucket_name, object_key = file_ref.path.split("/", 1)
            image_stream, _ = minio.download_file(bucket_name, object_key)
            image_data = image_stream.read()
            encoded = base64.b64encode(image_data).decode("utf-8")
            image_format = agents_router._infer_image_format(file_ref.content_type, file_ref.name)
            multimodal_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{image_format};base64,{encoded}"},
                }
            )

    execution_messages: List[Any] = []
    response_metadata_list: List[Dict[str, Any]] = []
    token_queue: "queue.Queue[Any]" = queue.Queue()
    error_holder: List[Optional[str]] = [None]
    segment_response: List[str] = [""]
    segment_execution_messages: List[List[Any]] = [[]]
    segment_response_metadata: List[Dict[str, Any]] = [{}]
    created_schedule_events: List[List[Dict[str, Any]]] = [[]]
    persisted_rounds: List[Dict[str, Any]] = []
    current_round_data = create_empty_round_data()
    current_round_number = 1

    def stream_callback(token_data):
        token_queue.put(token_data)

    def execute_agent() -> None:
        try:
            set_schedule_tool_context(
                ScheduleToolContext(
                    owner_user_id=principal.user_id,
                    owner_role=principal.role,
                    agent_id=str(conversation.agent_id),
                    origin_surface=resolved_origin_surface,
                    bound_conversation_id=str(conversation.conversation_id),
                    origin_message_id=(
                        str(input_message_row.message_id) if input_message_row else None
                    ),
                )
            )
            additional_context = {
                "execution_context_tag": agents_router.AGENT_TEST_RUNTIME_CONTEXT_TAG,
                "task_intent_text": task_intent_text,
                "conversation_history_summary": history_window.get("summary_text"),
                "schedule_origin_surface": resolved_origin_surface,
                "origin_conversation_id": str(conversation.conversation_id),
                "origin_message_id": (
                    str(input_message_row.message_id) if input_message_row else ""
                ),
                "origin_message_text": persisted_input_text or task_intent_text,
            }
            if isinstance(extra_execution_context, dict):
                additional_context.update(extra_execution_context)
            run_context = dict(context)
            run_context.update(additional_context)
            run_exec_context = ExecutionContext(
                agent_id=conversation.agent_id,
                user_id=principal_user_id,
                user_role=principal.role,
                task_description=user_message,
                additional_context=additional_context,
            )
            if is_agent_test_chat_unified_runtime_enabled():
                result = executor.execute(
                    agent,
                    run_exec_context,
                    conversation_history=history or None,
                    execution_profile=ExecutionProfile.DEBUG_CHAT,
                    stream_callback=stream_callback,
                    session_workdir=runtime.workdir,
                    container_id=runtime.sandbox_id,
                    message_content=multimodal_content,
                    prebuilt_execution_context=run_context,
                )
            else:
                result = agent.execute_task(
                    task_description=user_message,
                    context=run_context,
                    conversation_history=history or None,
                    stream_callback=stream_callback,
                    session_workdir=runtime.workdir,
                    container_id=runtime.sandbox_id,
                    message_content=multimodal_content,
                    task_intent_text=user_text,
                )
            if not result.get("success", False):
                error_holder[0] = str(result.get("error") or "Unknown agent execution error")
                failure_output = result.get("output")
                segment_response[0] = str(failure_output) if failure_output is not None else ""
                segment_execution_messages[0] = result.get("messages") or []
                token_queue.put(None)
                return
            segment_response[0] = str(result.get("output") or "")
            segment_execution_messages[0] = result.get("messages") or []
            for msg in reversed(segment_execution_messages[0]):
                if hasattr(msg, "response_metadata") and msg.response_metadata:
                    segment_response_metadata[0] = msg.response_metadata
                    break
            created_schedule_events[0] = consume_created_schedule_events()
            token_queue.put(None)
        except BaseException as exc:  # noqa: BLE001
            logger.error("Persistent conversation agent execution failed: %s", exc, exc_info=True)
            error_holder[0] = str(exc)
            created_schedule_events[0] = consume_created_schedule_events()
            token_queue.put(None)
        finally:
            clear_schedule_tool_context()

    exec_thread = threading.Thread(target=execute_agent, daemon=True)
    exec_thread.start()
    try:
        while True:
            try:
                token_data = await asyncio.to_thread(token_queue.get, True, 0.1)
                if token_data is None:
                    break
                if isinstance(token_data, tuple):
                    token, content_type = token_data
                else:
                    token = token_data
                    content_type = "content"
                if content_type == "round_stats":
                    try:
                        stats_data = json.loads(token)
                        stats_data["type"] = "round_stats"
                        current_round_data["stats"] = {
                            "timeToFirstToken": stats_data.get("timeToFirstToken", 0),
                            "tokensPerSecond": stats_data.get("tokensPerSecond", 0),
                            "inputTokens": stats_data.get("inputTokens", 0),
                            "outputTokens": stats_data.get("outputTokens", 0),
                            "totalTokens": (stats_data.get("inputTokens", 0) or 0)
                            + (stats_data.get("outputTokens", 0) or 0),
                            "totalTime": stats_data.get("totalTime", 0),
                        }
                        await _emit_chunk(chunk_callback, stats_data)
                    except json.JSONDecodeError:
                        logger.warning("Invalid round_stats payload: %s", token)
                else:
                    token_text = str(token or "")
                    if content_type == "info":
                        round_match = re.search(r"第\s*(\d+)\s*轮", token_text)
                        if round_match:
                            new_round_number = int(round_match.group(1))
                            if has_round_activity(current_round_data):
                                persisted_rounds.append(
                                    build_round_snapshot(current_round_data, current_round_number)
                                )
                            current_round_number = new_round_number
                            current_round_data = create_empty_round_data()
                        current_round_data["statusMessages"].append(
                            {
                                "content": token_text,
                                "type": "info",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    elif content_type in {
                        "start",
                        "tool_call",
                        "tool_result",
                        "tool_error",
                        "done",
                        "error",
                    }:
                        current_round_data["statusMessages"].append(
                            {
                                "content": token_text,
                                "type": content_type,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    elif content_type == "retry_attempt":
                        current_round_data["retryAttempts"].append(
                            {
                                "message": token_text,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    elif content_type == "error_feedback":
                        current_round_data["errorFeedback"].append(
                            {
                                "message": token_text,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                    elif content_type == "thinking":
                        current_round_data["thinking"] += token_text
                    elif content_type == "content":
                        current_round_data["content"] += token_text
                    await _emit_chunk(chunk_callback, {"type": content_type, "content": token})
            except queue.Empty:
                if not exec_thread.is_alive():
                    break
                continue
    except asyncio.CancelledError:
        if hasattr(agent, "request_cancellation"):
            try:
                agent.request_cancellation("client stream cancelled")
            except Exception as cancel_error:
                logger.warning(
                    "Failed to signal persistent conversation cancellation: %s",
                    cancel_error,
                    extra={"conversation_id": str(conversation.conversation_id)},
                )
        cleanup_incomplete_turn()
        raise
    finally:
        await asyncio.to_thread(exec_thread.join, 5)
        if exec_thread.is_alive():
            logger.warning(
                "Persistent conversation execution thread still running after cancellation",
                extra={"conversation_id": str(conversation.conversation_id)},
            )

    if error_holder[0]:
        cleanup_incomplete_turn()
        await _emit_chunk(chunk_callback, {"type": "error", "content": f"Error: {error_holder[0]}"})
        raise RuntimeError(error_holder[0])

    raw_final_response_text = segment_response[0].strip()
    execution_messages.extend(
        segment_execution_messages[0] if isinstance(segment_execution_messages[0], list) else []
    )
    response_metadata_list.append(
        segment_response_metadata[0] if isinstance(segment_response_metadata[0], dict) else {}
    )

    input_tokens = 0
    output_tokens = 0
    for metadata in response_metadata_list:
        in_tokens, out_tokens = agents_router._extract_token_usage_from_metadata(metadata)
        input_tokens += in_tokens
        output_tokens += out_tokens
    if input_tokens == 0 and output_tokens == 0:
        input_chars = 0
        for msg in execution_messages:
            if hasattr(msg, "content"):
                if isinstance(msg.content, str):
                    input_chars += len(msg.content)
                elif isinstance(msg.content, list):
                    for item in msg.content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            input_chars += len(item.get("text", ""))
        input_tokens = int(input_chars * 0.5)
        output_tokens = int(len(raw_final_response_text) * 0.5)

    stats = {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": input_tokens + output_tokens,
    }
    artifact_entries = agents_router._list_session_workspace_entries(
        runtime.workdir, recursive=True
    )
    artifact_delta_entries = _diff_workspace_entries(baseline_artifact_entries, artifact_entries)
    final_response_text = _sanitize_unverified_workspace_save_claims(
        raw_final_response_text,
        artifact_delta_entries=artifact_delta_entries,
    )
    if not current_round_data["stats"]:
        current_round_data["stats"] = {
            "timeToFirstToken": 0,
            "tokensPerSecond": 0,
            "inputTokens": input_tokens,
            "outputTokens": output_tokens,
            "totalTokens": input_tokens + output_tokens,
            "totalTime": 0,
        }
    if has_round_activity(current_round_data):
        persisted_rounds.append(build_round_snapshot(current_round_data, current_round_number))
    schedule_events_payload = [
        (
            build_schedule_created_event(event)
            if "schedule_id" not in event and "id" in event
            else dict(event)
        )
        for event in list(created_schedule_events[0] or [])
    ]
    if schedule_events_payload:
        if persisted_rounds:
            persisted_rounds[-1]["scheduleEvents"] = list(schedule_events_payload)
        else:
            persisted_rounds.append(
                {
                    "roundNumber": current_round_number,
                    "thinking": "",
                    "content": "",
                    "statusMessages": [],
                    "scheduleEvents": list(schedule_events_payload),
                }
            )
    assistant_message_row = _persist_message(
        conversation_id=conversation.conversation_id,
        role="assistant",
        content_text=final_response_text,
        content_json={
            "stats": stats,
            "rounds": persisted_rounds,
            "artifacts": artifact_entries,
            "artifactDelta": artifact_delta_entries,
            "scheduleEvents": schedule_events_payload,
        },
        attachments=None,
        source=source,
    )
    if is_default_conversation_title(conversation.title) and final_response_text:
        try:
            generated_title = await generate_conversation_title(
                agent_info=agent_info,
                user_message=title_context_text or "[Attached files]",
                assistant_message=final_response_text,
            )
            if generated_title:
                _update_conversation_title(conversation.conversation_id, generated_title)
                conversation.title = generated_title
                await _emit_chunk(
                    chunk_callback,
                    {
                        "type": "conversation_title",
                        "conversation_id": str(conversation.conversation_id),
                        "title": generated_title,
                    },
                )
        except Exception as exc:
            logger.warning(
                "Failed to generate AI title for conversation %s: %s",
                conversation.conversation_id,
                exc,
            )
    runtime.dirty = True
    snapshot = await runtime_service.snapshot_runtime(conversation_id=conversation.conversation_id)
    for schedule_event in schedule_events_payload:
        await _emit_chunk(
            chunk_callback,
            {
                "type": "schedule_created",
                **schedule_event,
            },
        )
    await _emit_chunk(chunk_callback, {"type": "stats", **stats})
    await _emit_chunk(
        chunk_callback,
        {
            "type": "done",
            "content": "Agent execution completed",
            "partial": False,
        },
    )

    return {
        "output": final_response_text,
        "stats": stats,
        "snapshot": snapshot,
        "artifacts": artifact_entries,
        "artifact_delta": artifact_delta_entries,
        "assistant_message_id": str(assistant_message_row.message_id),
        "schedule_events": schedule_events_payload,
        "duplicate": False,
    }


@router.post(
    "/{agent_id}/conversations",
    response_model=CreateConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_agent_conversation(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    agents_router._get_accessible_agent_or_raise(agent_id, current_user, access_type="execute")
    with get_db_session() as session:
        row = AgentConversation(
            agent_id=UUID(agent_id),
            owner_user_id=UUID(current_user.user_id),
            title=build_default_conversation_title(),
            status="active",
            source="web",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return CreateConversationResponse(
            conversation=_serialize_conversation_summary(session, row)
        )


@router.get("/{agent_id}/conversations", response_model=AgentConversationListResponse)
async def list_agent_conversations(
    agent_id: str,
    limit: int = Query(30, ge=1, le=100),
    cursor: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    started = time.monotonic()
    agents_router._get_accessible_agent_or_raise(agent_id, current_user, access_type="read")
    cursor_value = _decode_conversation_cursor(cursor)
    with get_db_session() as session:
        base_query = (
            session.query(AgentConversation)
            .filter(AgentConversation.agent_id == UUID(agent_id))
            .filter(AgentConversation.owner_user_id == UUID(current_user.user_id))
            .filter(AgentConversation.status == "active")
        )
        total = base_query.count()
        query = base_query
        if cursor_value is not None:
            cursor_updated_at, cursor_conversation_id = cursor_value
            query = query.filter(
                or_(
                    AgentConversation.updated_at < cursor_updated_at,
                    and_(
                        AgentConversation.updated_at == cursor_updated_at,
                        AgentConversation.conversation_id < cursor_conversation_id,
                    ),
                )
            )
        rows = (
            query.order_by(
                AgentConversation.updated_at.desc(),
                AgentConversation.conversation_id.desc(),
            )
            .limit(limit + 1)
            .all()
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        items = [_serialize_conversation_summary(session, row) for row in page_rows]
        next_cursor = None
        if has_more and page_rows:
            last_row = page_rows[-1]
            next_cursor = _encode_cursor(
                {
                    "updatedAt": last_row.updated_at,
                    "conversationId": last_row.conversation_id,
                }
            )

    logger.info(
        "Listed persistent conversations page",
        extra={
            "agent_id": agent_id,
            "user_id": current_user.user_id,
            "limit": limit,
            "returned_count": len(items),
            "has_more": has_more,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        },
    )
    return AgentConversationListResponse(
        items=items,
        total=int(total or 0),
        hasMore=has_more,
        nextCursor=next_cursor,
    )


@router.get(
    "/{agent_id}/conversations/{conversation_id}", response_model=AgentConversationDetailResponse
)
async def get_agent_conversation(
    agent_id: str,
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        row = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
        )
        return _serialize_conversation_detail(session, row)


@router.patch(
    "/{agent_id}/conversations/{conversation_id}", response_model=AgentConversationDetailResponse
)
async def update_agent_conversation(
    agent_id: str,
    conversation_id: str,
    payload: UpdateConversationRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        row = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
        )
        row.title = payload.title.strip()
        row.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(row)
        return _serialize_conversation_detail(session, row)


@router.delete("/{agent_id}/conversations/{conversation_id}", status_code=status.HTTP_200_OK)
async def delete_agent_conversation(
    agent_id: str,
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    runtime_service = get_persistent_conversation_runtime_service()
    conversation_uuid = _parse_conversation_uuid(conversation_id)
    try:
        from user_memory.conversation_memory_service import get_conversation_memory_service

        await get_conversation_memory_service().flush_conversation_memory_delta(
            conversation_uuid,
            reason="delete",
        )
    except Exception as exc:
        logger.warning(
            "Failed to flush persistent conversation memory before delete %s: %s",
            conversation_uuid,
            exc,
        )
    with get_db_session() as session:
        row = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == conversation_uuid)
            .filter(AgentConversation.agent_id == UUID(agent_id))
            .filter(AgentConversation.owner_user_id == UUID(current_user.user_id))
            .first()
        )
        if row is None:
            return {"success": True, "conversation_id": conversation_id, "already_deleted": True}
        object_refs = collect_conversation_storage_refs(session, row.conversation_id)
        conversation_uuid = row.conversation_id
        session.delete(row)
        session.commit()

    await runtime_service.release_runtime(UUID(conversation_id), reason="delete")
    delete_object_references(
        {
            *set(object_refs.get("snapshot_refs") or set()),
            *set(object_refs.get("archive_refs") or set()),
            *set(object_refs.get("attachment_refs") or set()),
        }
    )
    return {"success": True, "conversation_id": str(conversation_uuid)}


@router.get(
    "/{agent_id}/conversations/{conversation_id}/messages",
    response_model=AgentConversationMessagesListResponse,
)
async def list_agent_conversation_messages(
    agent_id: str,
    conversation_id: str,
    limit: int = Query(50, ge=1, le=100),
    before: Optional[str] = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
):
    started = time.monotonic()
    before_cursor = _decode_message_cursor(before)
    with get_db_session() as session:
        row = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
        )
    history_page = get_conversation_history_compaction_service().list_live_message_page(
        row.conversation_id,
        limit=limit,
        before_cursor=before_cursor,
    )
    messages = list(history_page.get("messages") or [])
    items = [_serialize_message(message) for message in messages]
    has_older_live_messages = bool(history_page.get("has_older_live_messages"))
    older_cursor = None
    if has_older_live_messages and messages:
        oldest_loaded_message = messages[0]
        older_cursor = _encode_cursor(
            {
                "createdAt": oldest_loaded_message.created_at,
                "messageId": oldest_loaded_message.message_id,
            }
        )
    logger.info(
        "Listed persistent conversation live messages page",
        extra={
            "agent_id": agent_id,
            "conversation_id": conversation_id,
            "user_id": current_user.user_id,
            "limit": limit,
            "returned_count": len(items),
            "has_older": has_older_live_messages,
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
        },
    )
    return AgentConversationMessagesListResponse(
        items=items,
        total=len(items),
        historySummary=_build_history_summary_response_from_window(history_page),
        compactedMessageCount=int(history_page.get("compacted_message_count") or 0),
        archivedSegmentCount=int(history_page.get("archived_segment_count") or 0),
        recentWindowSize=int(history_page.get("recent_window_size") or 0),
        hasOlderLiveMessages=has_older_live_messages,
        olderCursor=older_cursor,
    )


@router.post("/{agent_id}/conversations/{conversation_id}/messages")
async def send_agent_conversation_message(
    agent_id: str,
    conversation_id: str,
    message: str = Form(..., min_length=1, max_length=5000),
    files: List[UploadFile] = File(default=[]),
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        conversation = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
            required_agent_access="execute",
        )
        conversation_id_uuid = conversation.conversation_id

    async def generate_stream():
        async def emit(chunk: Dict[str, Any]) -> None:
            yield_line = f"data: {json.dumps(chunk, default=str, ensure_ascii=False)}\n\n"
            queue_items.put_nowait(yield_line)

        queue_items: asyncio.Queue[str] = asyncio.Queue()
        done_marker = object()

        async def runner() -> None:
            try:
                with get_db_session() as session:
                    fresh_conversation = (
                        session.query(AgentConversation)
                        .filter(AgentConversation.conversation_id == conversation_id_uuid)
                        .first()
                    )
                    if fresh_conversation is None:
                        raise HTTPException(status_code=404, detail="Conversation not found")
                    await execute_persistent_conversation_turn(
                        conversation=fresh_conversation,
                        principal=build_conversation_execution_principal(
                            user_id=current_user.user_id,
                            role=current_user.role,
                            username=current_user.username,
                        ),
                        message=message,
                        files=files,
                        source="web",
                        chunk_callback=emit,
                    )
            except Exception as exc:
                await emit({"type": "error", "content": f"Error: {exc}"})
            finally:
                await queue_items.put(done_marker)  # type: ignore[arg-type]

        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue_items.get()
                if item is done_marker:
                    break
                yield item
        except asyncio.CancelledError:
            task.cancel()
            raise
        finally:
            if not task.done():
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{agent_id}/conversations/{conversation_id}/runtime/release",
    response_model=ReleaseConversationRuntimeResponse,
)
async def release_agent_conversation_runtime(
    agent_id: str,
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    agents_router._get_accessible_agent_or_raise(agent_id, current_user, access_type="read")
    with get_db_session() as session:
        row = (
            session.query(AgentConversation.conversation_id)
            .filter(AgentConversation.conversation_id == _parse_conversation_uuid(conversation_id))
            .filter(AgentConversation.agent_id == UUID(agent_id))
            .filter(AgentConversation.owner_user_id == UUID(current_user.user_id))
            .first()
        )
        if row is None:
            return ReleaseConversationRuntimeResponse(success=True)
    await get_persistent_conversation_runtime_service().release_runtime(
        UUID(conversation_id),
        reason="user",
    )
    return ReleaseConversationRuntimeResponse(success=True)


@router.get("/{agent_id}/conversations/{conversation_id}/workspace/files")
async def list_conversation_workspace_files(
    agent_id: str,
    conversation_id: str,
    path: str = "",
    recursive: bool = False,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        conversation = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
        )
    runtime, _ = await get_persistent_conversation_runtime_service().get_or_create_runtime(
        conversation=conversation
    )
    entries = agents_router._list_session_workspace_entries(runtime.workdir, path, recursive)
    retention_index = get_conversation_workspace_decay_service().build_retention_index(
        conversation_id=conversation.conversation_id,
        workdir=runtime.workdir,
    )
    enriched_entries: List[Dict[str, Any]] = []
    for entry in entries:
        relative_path = str(entry.get("path") or "").strip()
        enriched_entry = dict(entry)
        enriched_entry["retention_class"] = retention_index.get(relative_path, "durable")
        enriched_entries.append(enriched_entry)
    return enriched_entries


@router.get(
    "/{agent_id}/conversations/{conversation_id}/archives",
    response_model=AgentConversationArchiveListResponse,
)
async def list_agent_conversation_archives(
    agent_id: str,
    conversation_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        row = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
        )
        archives = (
            session.query(AgentConversationMessageArchive)
            .filter(AgentConversationMessageArchive.conversation_id == row.conversation_id)
            .order_by(AgentConversationMessageArchive.created_at.desc())
            .all()
        )
        items = [_serialize_message_archive(archive) for archive in archives]
        return AgentConversationArchiveListResponse(items=items, total=len(items))


@router.get("/{agent_id}/conversations/{conversation_id}/archives/{archive_id}/download")
async def download_agent_conversation_archive(
    agent_id: str,
    conversation_id: str,
    archive_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        row = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
        )
        archive = (
            session.query(AgentConversationMessageArchive)
            .filter(AgentConversationMessageArchive.conversation_id == row.conversation_id)
            .filter(
                AgentConversationMessageArchive.archive_id == _parse_conversation_uuid(archive_id)
            )
            .first()
        )
        if archive is None:
            raise HTTPException(status_code=404, detail="Conversation archive not found")

    minio = get_minio_client()
    parsed = minio.parse_object_reference(archive.archive_ref)
    if not parsed:
        raise HTTPException(status_code=404, detail="Conversation archive object not found")
    bucket_name, object_key = parsed
    archive_stream, _ = minio.download_file(bucket_name, object_key)
    filename = f"conversation-{conversation_id}-archive-{archive_id}.jsonl.gz"
    return StreamingResponse(
        archive_stream,
        media_type="application/gzip",
        headers={
            "Content-Disposition": agents_router._build_download_content_disposition(
                filename,
                disposition="attachment",
            )
        },
    )


@router.get("/{agent_id}/conversations/{conversation_id}/workspace/download")
async def download_conversation_workspace_file(
    agent_id: str,
    conversation_id: str,
    path: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    with get_db_session() as session:
        conversation = _load_owned_conversation(
            session,
            agent_id=agent_id,
            conversation_id=conversation_id,
            current_user=current_user,
        )
    runtime, _ = await get_persistent_conversation_runtime_service().get_or_create_runtime(
        conversation=conversation
    )
    file_path, relative_path = agents_router._resolve_safe_workspace_path(runtime.workdir, path)
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Workspace file not found")
    filename = file_path.name or (relative_path.rsplit("/", 1)[-1] if relative_path else "download")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {
        "Content-Disposition": agents_router._build_download_content_disposition(
            filename,
            disposition="attachment",
        )
    }
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
        headers=headers,
    )


@router.get("/{agent_id}/channels/feishu", response_model=FeishuPublicationResponse)
async def get_agent_feishu_publication(
    agent_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    _, agent_uuid = agents_router._get_accessible_agent_or_raise(
        agent_id,
        current_user,
        access_type="manage",
    )
    with get_db_session() as session:
        publication = _load_feishu_publication(session, agent_uuid)
        return _serialize_feishu_publication(publication, request=request)


@router.put("/{agent_id}/channels/feishu", response_model=FeishuPublicationResponse)
async def save_agent_feishu_publication(
    agent_id: str,
    payload: FeishuPublicationConfigRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    _, agent_uuid = agents_router._get_accessible_agent_or_raise(
        agent_id,
        current_user,
        access_type="manage",
    )
    with get_db_session() as session:
        publication = _upsert_feishu_publication(
            session=session, agent_id=agent_uuid, payload=payload
        )
        session.commit()
        session.refresh(publication)
        try:
            from api_gateway.feishu_long_connection import (
                get_feishu_long_connection_manager,
                update_feishu_long_connection_runtime,
            )

            if publication.status == "published":
                update_feishu_long_connection_runtime(
                    str(publication.publication_id),
                    state="connecting",
                    clear_last_error=True,
                )
            else:
                update_feishu_long_connection_runtime(
                    str(publication.publication_id),
                    state="inactive",
                    clear_last_error=True,
                )

            get_feishu_long_connection_manager().request_reconcile()
            session.refresh(publication)
        except Exception:
            logger.debug("Failed to request Feishu long-connection reconcile after save")
        return _serialize_feishu_publication(publication, request=request)


@router.post("/{agent_id}/channels/feishu/publish", response_model=FeishuPublicationResponse)
async def publish_agent_feishu_publication(
    agent_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    _, agent_uuid = agents_router._get_accessible_agent_or_raise(
        agent_id,
        current_user,
        access_type="manage",
    )
    with get_db_session() as session:
        publication = _load_feishu_publication(session, agent_uuid)
        if publication is None:
            raise HTTPException(status_code=400, detail="Feishu publication config not found")

        config = (
            dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
        )
        from api_gateway.routers.integrations import _publication_secrets

        secrets = _publication_secrets(publication)
        missing_fields = [
            field_name
            for field_name, configured in {
                "appId": bool(config.get("app_id")),
                "appSecret": bool(secrets.get("app_secret")),
            }.items()
            if not configured
        ]
        if missing_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required Feishu config fields: {', '.join(missing_fields)}",
            )

        publication.status = "published"
        publication.channel_identity = config.get("app_id")
        publication.webhook_path = None
        publication.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(publication)
        try:
            from api_gateway.feishu_long_connection import (
                get_feishu_long_connection_manager,
                update_feishu_long_connection_runtime,
            )

            update_feishu_long_connection_runtime(
                str(publication.publication_id),
                state="connecting",
                clear_last_error=True,
            )

            get_feishu_long_connection_manager().request_reconcile()
            session.refresh(publication)
        except Exception:
            logger.debug("Failed to request Feishu long-connection reconcile after publish")
        return _serialize_feishu_publication(publication, request=request)


@router.post("/{agent_id}/channels/feishu/unpublish", response_model=FeishuPublicationResponse)
async def unpublish_agent_feishu_publication(
    agent_id: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    _, agent_uuid = agents_router._get_accessible_agent_or_raise(
        agent_id,
        current_user,
        access_type="manage",
    )
    with get_db_session() as session:
        publication = _load_feishu_publication(session, agent_uuid)
        if publication is None:
            return _serialize_feishu_publication(None, request=request)
        publication.status = "draft"
        publication.webhook_path = None
        publication.updated_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(publication)
        try:
            from api_gateway.feishu_long_connection import (
                get_feishu_long_connection_manager,
                update_feishu_long_connection_runtime,
            )

            update_feishu_long_connection_runtime(
                str(publication.publication_id),
                state="inactive",
                clear_last_error=True,
            )

            get_feishu_long_connection_manager().request_reconcile()
            session.refresh(publication)
        except Exception:
            logger.debug("Failed to request Feishu long-connection reconcile after unpublish")
        return _serialize_feishu_publication(publication, request=request)
