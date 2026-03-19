"""External channel webhook endpoints."""

from __future__ import annotations

import asyncio
import io
import json
import mimetypes
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException, Request, UploadFile
from starlette.datastructures import Headers

from access_control.permissions import CurrentUser
from agent_framework.persistent_conversations import (
    build_default_conversation_title,
    get_persistent_conversation_runtime_service,
)
from api_gateway.feishu_publication_helpers import (
    extract_feishu_message as _extract_feishu_message,
    extract_feishu_message_from_long_connection_event as _extract_feishu_message_from_long_connection_event,
    load_publication_or_raise as _load_publication_or_raise,
    publication_secrets as _publication_secrets,
    resolve_public_web_base_url as _resolve_public_web_base_url,
)
from api_gateway.routers import agents as agents_router
from api_gateway.routers.agent_conversations import execute_persistent_conversation_turn
from database.connection import get_db_session
from database.models import (
    Agent,
    AgentChannelPublication,
    AgentConversation,
    AgentConversationMessage,
    ExternalConversationLink,
    User,
    UserBindingCode,
    UserExternalBinding,
)
from shared.binding_codes import hash_user_binding_code, normalize_user_binding_code
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

_FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
_TENANT_TOKEN_CACHE: dict[str, tuple[str, datetime]] = {}
_FEISHU_MAX_DIRECT_FILE_MESSAGES = 3
_FEISHU_MAX_DIRECT_FILE_SIZE_BYTES = 30 * 1024 * 1024
_FEISHU_IGNORED_ARTIFACT_ROOTS = {"input", "logs", "tasks"}
_FEISHU_IGNORED_ARTIFACT_NAMES = {
    ".linx_runtime",
    ".skills",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
}
_FEISHU_PROCESSING_REACTION_EMOJI_TYPES = ("EYES", "SMILE")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_feishu_api_error(payload: dict[str, Any], *, default_error: str) -> str:
    message = str(payload.get("msg") or "").strip()
    details: list[str] = []

    code = payload.get("code")
    if code not in (None, ""):
        details.append(f"code={code}")

    error = payload.get("error")
    if isinstance(error, dict):
        permission_violations = error.get("permission_violations")
        if isinstance(permission_violations, list):
            scopes = sorted(
                {
                    str(item.get("subject") or "").strip()
                    for item in permission_violations
                    if isinstance(item, dict) and str(item.get("subject") or "").strip()
                }
            )
            if scopes:
                details.append(f"missing_scopes={','.join(scopes)}")

    summary = f"{default_error}: {message}" if message else default_error
    if details:
        summary = f"{summary} ({'; '.join(details)})"
    return summary


def _parse_feishu_json_response(
    response: requests.Response,
    *,
    default_error: str,
) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError(default_error)

    if not isinstance(payload, dict):
        response.raise_for_status()
        raise RuntimeError(default_error)

    if response.status_code >= 400 or int(payload.get("code", 0) or 0) != 0:
        raise RuntimeError(_format_feishu_api_error(payload, default_error=default_error))

    return payload


def _classify_feishu_file_delivery_error(exc: Exception) -> str | None:
    message = str(exc)
    if (
        "im:resource:upload" in message
        or "missing_scopes=im:resource,im:resource:upload" in message
    ):
        return "当前飞书应用未开通文件上传权限，已改为发送文本结果和网页链接。"
    return None


def _validate_feishu_verification_token(
    payload: dict[str, Any],
    publication: AgentChannelPublication,
) -> None:
    secrets = _publication_secrets(publication)
    expected_token = secrets.get("verification_token")
    if not expected_token:
        return
    received_token = payload.get("token") or (payload.get("header") or {}).get("token")
    if str(received_token or "") != expected_token:
        raise HTTPException(status_code=403, detail="Invalid Feishu verification token")


def _get_feishu_tenant_access_token(publication: AgentChannelPublication) -> str:
    cache_key = str(publication.publication_id)
    cached = _TENANT_TOKEN_CACHE.get(cache_key)
    if cached and cached[1] > _utc_now():
        return cached[0]

    config = (
        dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
    )
    secrets = _publication_secrets(publication)
    app_id = str(config.get("app_id") or "").strip()
    app_secret = str(secrets.get("app_secret") or "").strip()
    if not app_id or not app_secret:
        raise RuntimeError("Feishu app credentials are incomplete")

    response = requests.post(
        f"{_FEISHU_API_BASE}/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=20,
    )
    payload = _parse_feishu_json_response(
        response,
        default_error="Failed to fetch Feishu tenant access token",
    )

    token = str(payload.get("tenant_access_token") or "").strip()
    expire_seconds = int(payload.get("expire", 7200) or 7200)
    if not token:
        raise RuntimeError("Feishu tenant access token is missing")

    _TENANT_TOKEN_CACHE[cache_key] = (
        token,
        _utc_now() + timedelta(seconds=max(expire_seconds - 120, 60)),
    )
    return token


def _send_feishu_text_message(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    text: str,
) -> None:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    response = requests.post(
        f"{_FEISHU_API_BASE}/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        timeout=20,
    )
    _parse_feishu_json_response(response, default_error="Failed to send Feishu message")


def _send_feishu_file_message(
    publication: AgentChannelPublication,
    *,
    chat_id: str,
    file_path: Path,
    file_name: str,
) -> None:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    with file_path.open("rb") as handle:
        upload_response = requests.post(
            f"{_FEISHU_API_BASE}/im/v1/files",
            headers={"Authorization": f"Bearer {tenant_access_token}"},
            data={"file_type": "stream", "file_name": file_name},
            files={
                "file": (
                    file_name,
                    handle,
                    mimetypes.guess_type(file_name)[0] or "application/octet-stream",
                )
            },
            timeout=120,
        )
    upload_payload = _parse_feishu_json_response(
        upload_response,
        default_error="Failed to upload Feishu file",
    )

    file_key = (
        str((upload_payload.get("data") or {}).get("file_key") or "").strip()
        or str(upload_payload.get("file_key") or "").strip()
    )
    if not file_key:
        raise RuntimeError("Feishu file upload succeeded but file_key is missing")

    send_response = requests.post(
        f"{_FEISHU_API_BASE}/im/v1/messages",
        params={"receive_id_type": "chat_id"},
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        json={
            "receive_id": chat_id,
            "msg_type": "file",
            "content": json.dumps({"file_key": file_key}, ensure_ascii=False),
        },
        timeout=20,
    )
    _parse_feishu_json_response(send_response, default_error="Failed to send Feishu file message")


def _send_feishu_message_reaction(
    publication: AgentChannelPublication,
    *,
    message_id: str,
    emoji_type: str,
) -> None:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    response = requests.post(
        f"{_FEISHU_API_BASE}/im/v1/messages/{message_id}/reactions",
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        json={"reaction_type": {"emoji_type": emoji_type}},
        timeout=20,
    )
    _parse_feishu_json_response(response, default_error="Failed to add Feishu message reaction")


def _try_add_feishu_processing_reaction(
    publication: AgentChannelPublication,
    *,
    message_id: str | None,
) -> None:
    normalized_message_id = str(message_id or "").strip()
    if not normalized_message_id:
        return

    for emoji_type in _FEISHU_PROCESSING_REACTION_EMOJI_TYPES:
        try:
            _send_feishu_message_reaction(
                publication,
                message_id=normalized_message_id,
                emoji_type=emoji_type,
            )
            return
        except Exception as exc:
            logger.debug(
                "Failed to add Feishu processing reaction",
                extra={
                    "message_id": normalized_message_id,
                    "emoji_type": emoji_type,
                    "error": str(exc),
                },
            )


def _user_can_access_agent(agent: Agent, user: User) -> bool:
    from access_control.agent_access import build_agent_access_context_for_user_id, can_read_agent

    with get_db_session() as session:
        context = build_agent_access_context_for_user_id(
            session=session,
            user_id=str(user.user_id),
            role=str(user.role or ""),
        )
        return can_read_agent(agent, context)


def _find_external_binding(
    session,
    *,
    publication_id: UUID,
    open_id: str | None,
    external_user_id: str | None,
    union_id: str | None,
) -> UserExternalBinding | None:
    query = session.query(UserExternalBinding).filter(
        UserExternalBinding.publication_id == publication_id
    )
    if open_id:
        row = query.filter(UserExternalBinding.external_open_id == open_id).first()
        if row:
            return row
    if external_user_id:
        row = query.filter(UserExternalBinding.external_user_id == external_user_id).first()
        if row:
            return row
    if union_id:
        row = query.filter(UserExternalBinding.external_union_id == union_id).first()
        if row:
            return row
    return None


def _bind_user_from_code(
    session,
    *,
    publication: AgentChannelPublication,
    message_text: str,
    open_id: str | None,
    external_user_id: str | None,
    union_id: str | None,
    tenant_key: str | None,
) -> UserExternalBinding | None:
    normalized_code = normalize_user_binding_code(message_text)
    if not normalized_code:
        return None

    binding_code = (
        session.query(UserBindingCode)
        .filter(UserBindingCode.code_hash == hash_user_binding_code(normalized_code))
        .filter(UserBindingCode.status == "active")
        .first()
    )
    if binding_code is None:
        return None

    user = session.query(User).filter(User.user_id == binding_code.user_id).first()
    agent = session.query(Agent).filter(Agent.agent_id == publication.agent_id).first()
    if user is None or agent is None:
        return None
    if not _user_can_access_agent(agent, user):
        return None

    existing = _find_external_binding(
        session,
        publication_id=publication.publication_id,
        open_id=open_id,
        external_user_id=external_user_id,
        union_id=union_id,
    )
    now = _utc_now()
    if existing is None:
        existing = UserExternalBinding(
            user_id=user.user_id,
            channel_type="feishu",
            publication_id=publication.publication_id,
            external_user_id=external_user_id,
            external_open_id=open_id,
            external_union_id=union_id,
            tenant_key=tenant_key,
            metadata_json={"bound_via": "binding_code"},
            created_at=now,
            last_seen_at=now,
        )
        session.add(existing)
    else:
        existing.user_id = user.user_id
        existing.external_user_id = external_user_id
        existing.external_open_id = open_id
        existing.external_union_id = union_id
        existing.tenant_key = tenant_key
        existing.last_seen_at = now

    binding_code.last_used_at = now
    return existing


def _get_or_create_external_conversation(
    session,
    *,
    publication: AgentChannelPublication,
    binding: UserExternalBinding,
    chat_key: str,
    thread_key: str,
) -> AgentConversation:
    link = (
        session.query(ExternalConversationLink)
        .filter(ExternalConversationLink.publication_id == publication.publication_id)
        .filter(ExternalConversationLink.external_chat_key == chat_key)
        .filter(ExternalConversationLink.external_thread_key == thread_key)
        .first()
    )
    if link is not None:
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == link.conversation_id)
            .first()
        )
        if conversation is not None:
            return conversation

    conversation = AgentConversation(
        agent_id=publication.agent_id,
        owner_user_id=binding.user_id,
        title=build_default_conversation_title(),
        status="active",
        source="feishu",
    )
    session.add(conversation)
    session.flush()

    session.add(
        ExternalConversationLink(
            publication_id=publication.publication_id,
            conversation_id=conversation.conversation_id,
            external_chat_key=chat_key,
            external_thread_key=thread_key,
        )
    )
    return conversation


def _conversation_already_processed(
    session,
    *,
    conversation_id: UUID,
    external_event_id: str | None,
) -> bool:
    if not external_event_id:
        return False
    row = (
        session.query(AgentConversationMessage)
        .filter(AgentConversationMessage.conversation_id == conversation_id)
        .filter(AgentConversationMessage.external_event_id == external_event_id)
        .first()
    )
    return row is not None


def _is_feishu_deliverable_artifact(entry: dict[str, Any]) -> bool:
    return _is_feishu_sendable_artifact(entry, allow_input=False)


def _is_feishu_sendable_artifact(
    entry: dict[str, Any],
    *,
    allow_input: bool,
) -> bool:
    if bool(entry.get("is_directory") or entry.get("is_dir")):
        return False

    path = str(entry.get("path") or "").strip().strip("/")
    if not path:
        return False

    parts = [part for part in path.split("/") if part]
    if not parts:
        return False

    if parts[0] in _FEISHU_IGNORED_ARTIFACT_ROOTS and (parts[0] != "input" or not allow_input):
        return False
    if any(part.startswith(".") or part in _FEISHU_IGNORED_ARTIFACT_NAMES for part in parts):
        return False
    return True


def _select_feishu_deliverable_artifacts(
    artifacts: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return [entry for entry in (artifacts or []) if _is_feishu_deliverable_artifact(entry)]


def _select_feishu_explicitly_requested_artifacts(
    artifacts: list[dict[str, Any]] | None,
    *texts: str | None,
) -> list[dict[str, Any]]:
    candidates = [
        entry
        for entry in (artifacts or [])
        if _is_feishu_sendable_artifact(entry, allow_input=True)
    ]
    haystack = "\n".join(str(text or "") for text in texts).lower()
    if not haystack.strip():
        return []

    selected: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    by_name: dict[str, list[dict[str, Any]]] = {}
    for artifact in candidates:
        path = str(artifact.get("path") or "").strip()
        if not path:
            continue
        file_name = Path(path).name.lower()
        if file_name:
            by_name.setdefault(file_name, []).append(artifact)

        normalized_path = path.lower()
        if (
            normalized_path in haystack
            or f"/workspace/{normalized_path}" in haystack
            or f"workspace/{normalized_path}" in haystack
        ):
            selected.append(artifact)
            seen_paths.add(path)

    for file_name, matches in by_name.items():
        if len(matches) != 1 or file_name not in haystack:
            continue
        artifact = matches[0]
        path = str(artifact.get("path") or "").strip()
        if not path or path in seen_paths:
            continue
        selected.append(artifact)
        seen_paths.add(path)

    return selected


def _looks_like_feishu_file_send_request(text: str | None) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False

    has_send_intent = any(
        token in normalized
        for token in (
            "发我",
            "发送",
            "给我文件",
            "把文件给我",
            "download",
            "send me",
            "attach",
            "附件",
        )
    )
    has_file_hint = (
        bool(
            re.search(
                r"(/workspace/|workspace/|output/|shared/|input/|[\w.-]+\.(md|txt|pdf|docx?|xlsx?|pptx?|html|csv|json|zip))",
                normalized,
            )
        )
        or "文件" in normalized
        or "file" in normalized
    )
    return has_send_intent and has_file_hint


def _resolve_feishu_artifact_file_paths(
    conversation: AgentConversation,
    artifacts: list[dict[str, Any]] | None,
) -> list[tuple[dict[str, Any], Path]]:
    runtime = get_persistent_conversation_runtime_service().get_active_runtime(
        conversation.conversation_id
    )
    if runtime is None:
        return []

    resolved: list[tuple[dict[str, Any], Path]] = []
    for artifact in artifacts or []:
        artifact_path = str(artifact.get("path") or "").strip()
        if not artifact_path:
            continue
        try:
            local_path, _ = agents_router._resolve_safe_workspace_path(
                Path(runtime.workdir), artifact_path
            )
        except HTTPException:
            continue
        if not local_path.exists() or not local_path.is_file():
            continue
        resolved.append((artifact, local_path))
    return resolved


def _guess_feishu_attachment_filename(
    message: dict[str, Any], fallback_suffix: str = ".bin"
) -> str:
    content_payload = (
        dict(message.get("content_payload") or {})
        if isinstance(message.get("content_payload"), dict)
        else {}
    )
    for field_name in ("file_name", "name", "title"):
        value = str(content_payload.get(field_name) or "").strip()
        if value:
            return value
    message_id = str(
        message.get("message_id") or message.get("event_id") or "feishu_attachment"
    ).strip()
    return f"{message_id}{fallback_suffix}"


def _download_feishu_message_attachment(
    publication: AgentChannelPublication,
    *,
    message_id: str,
    file_key: str,
    resource_type: str,
) -> tuple[bytes, str | None]:
    tenant_access_token = _get_feishu_tenant_access_token(publication)
    response = requests.get(
        f"{_FEISHU_API_BASE}/im/v1/messages/{message_id}/resources/{file_key}",
        params={"type": resource_type},
        headers={"Authorization": f"Bearer {tenant_access_token}"},
        timeout=120,
    )
    content_type = str(response.headers.get("Content-Type") or "")
    if content_type.startswith("application/json"):
        _parse_feishu_json_response(
            response,
            default_error="Failed to download Feishu message attachment",
        )
        raise RuntimeError("Feishu attachment download returned JSON unexpectedly")
    response.raise_for_status()

    file_name = None
    content_disposition = str(response.headers.get("Content-Disposition") or "")
    if "filename=" in content_disposition:
        file_name = content_disposition.split("filename=", 1)[1].strip().strip('"')
    return response.content, file_name


async def _prepare_feishu_message_uploads(
    *,
    publication: AgentChannelPublication,
    message: dict[str, Any],
) -> list[UploadFile]:
    message_type = str(message.get("message_type") or "").strip().lower()
    if message_type not in {"file", "image"}:
        return []

    content_payload = (
        dict(message.get("content_payload") or {})
        if isinstance(message.get("content_payload"), dict)
        else {}
    )
    resource_type = "image" if message_type == "image" else "file"
    resource_key = str(
        content_payload.get("file_key")
        or content_payload.get("image_key")
        or content_payload.get("resource_key")
        or ""
    ).strip()
    message_id = str(message.get("message_id") or "").strip()
    if not resource_key or not message_id:
        return []

    file_bytes, downloaded_name = await asyncio.to_thread(
        _download_feishu_message_attachment,
        publication,
        message_id=message_id,
        file_key=resource_key,
        resource_type=resource_type,
    )
    file_name = downloaded_name or _guess_feishu_attachment_filename(
        message,
        fallback_suffix=".png" if message_type == "image" else ".bin",
    )
    content_type = (
        "image/png"
        if message_type == "image"
        else mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    )

    return [
        UploadFile(
            file=io.BytesIO(file_bytes),
            size=len(file_bytes),
            filename=file_name,
            headers=Headers({"content-type": content_type}),
        )
    ]


def _build_feishu_reply_text(
    *,
    agent: Agent,
    conversation: AgentConversation,
    output_text: str,
    delivered_artifacts: list[dict[str, Any]] | None,
    pending_artifacts: list[dict[str, Any]] | None,
    delivery_notes: list[str] | None = None,
    base_url: str | None = None,
) -> str:
    base_text = output_text.strip() or "Agent execution completed."
    deduped_notes = [note.strip() for note in (delivery_notes or []) if str(note).strip()]
    pending_paths = [
        str(item.get("path") or "").strip()
        for item in (pending_artifacts or [])
        if str(item.get("path") or "").strip()
    ]
    if not pending_paths and not deduped_notes:
        return base_text

    note_block = "\n".join(f"- {note}" for note in deduped_notes[:3])
    more_notes = max(0, len(deduped_notes) - 3)
    if more_notes:
        note_block = f"{note_block}\n- 另外 {more_notes} 条说明"

    pending_labels = "\n".join(f"- {path}" for path in pending_paths[:5])
    more_count = max(0, len(pending_paths) - 5)
    summary_prefix = (
        "本轮还有部分产物未直接发送，可在网页查看："
        if delivered_artifacts
        else "本轮产生了以下文件："
    )
    if more_count:
        pending_labels = f"{pending_labels}\n- 另外 {more_count} 个文件"
    detail_blocks = [block for block in (note_block, pending_labels) if block]
    detail_text = "\n".join(detail_blocks)
    if not base_url:
        return f"{base_text}\n\n{summary_prefix}\n{detail_text}"

    conversation_url = f"{base_url.rstrip('/')}/workforce/{agent.agent_id}/conversations/{conversation.conversation_id}"
    return (
        f"{base_text}\n\n"
        f"{summary_prefix}\n{detail_text}\n\n"
        f"网页查看对话与工作区: {conversation_url}"
    )


async def process_feishu_publication_message(
    publication_id: str | UUID,
    message: dict[str, Any],
    *,
    base_url: str | None = None,
) -> dict[str, Any]:
    with get_db_session() as session:
        publication = _load_publication_or_raise(session, str(publication_id))
        if publication.status != "published":
            return {"success": False, "ignored": True, "reason": "publication_inactive"}

        if message.get("chat_type") != "p2p":
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前仅支持飞书单聊接入，请使用单聊继续对话。",
            )
            return {"success": True, "ignored": True}
        message_type = str(message.get("message_type") or "").strip().lower()
        if message_type not in {"text", "file", "image"}:
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前仅支持文本和文件消息，请直接发送文本或上传文件。",
            )
            return {"success": True, "ignored": True}

        await asyncio.to_thread(
            _try_add_feishu_processing_reaction,
            publication,
            message_id=message.get("message_id"),
        )

        binding = _find_external_binding(
            session,
            publication_id=publication.publication_id,
            open_id=message.get("open_id"),
            external_user_id=message.get("external_user_id"),
            union_id=message.get("union_id"),
        )
        if binding is None:
            binding = _bind_user_from_code(
                session,
                publication=publication,
                message_text=str(message.get("text") or ""),
                open_id=message.get("open_id"),
                external_user_id=message.get("external_user_id"),
                union_id=message.get("union_id"),
                tenant_key=message.get("tenant_key"),
            )
            if binding is None:
                session.commit()
                await asyncio.to_thread(
                    _send_feishu_text_message,
                    publication,
                    chat_id=str(message.get("chat_id") or ""),
                    text="请先发送用户识别码完成绑定。",
                )
                return {"success": True, "bound": False}

            session.commit()
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="绑定成功，后续消息将直接转发给 Agent。",
            )
            return {"success": True, "bound": True}

        binding.last_seen_at = _utc_now()
        user = session.query(User).filter(User.user_id == binding.user_id).first()
        agent = session.query(Agent).filter(Agent.agent_id == publication.agent_id).first()
        if user is None or agent is None:
            raise HTTPException(status_code=404, detail="Bound user or agent no longer exists")
        if not _user_can_access_agent(agent, user):
            session.commit()
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前绑定用户没有访问该 Agent 的权限，请刷新绑定或联系管理员。",
            )
            return {"success": True, "authorized": False}

        conversation = _get_or_create_external_conversation(
            session,
            publication=publication,
            binding=binding,
            chat_key=str(message.get("chat_id") or ""),
            thread_key=str(message.get("thread_key") or ""),
        )
        session.commit()
        session.refresh(conversation)

        if _conversation_already_processed(
            session,
            conversation_id=conversation.conversation_id,
            external_event_id=message.get("event_id"),
        ):
            return {"success": True, "duplicate": True}

        current_user = CurrentUser(
            user_id=str(user.user_id),
            username=user.username,
            role=user.role,
        )

    feishu_uploads = await _prepare_feishu_message_uploads(
        publication=publication,
        message=message,
    )
    result = await execute_persistent_conversation_turn(
        conversation=conversation,
        current_user=current_user,
        message=str(message.get("text") or ""),
        files=feishu_uploads,
        source="feishu",
        external_event_id=message.get("event_id"),
    )
    if result.get("duplicate"):
        return {"success": True, "duplicate": True}

    current_artifacts = list(result.get("artifacts") or [])
    delta_artifacts = _select_feishu_deliverable_artifacts(result.get("artifact_delta") or [])
    requested_artifacts = _select_feishu_explicitly_requested_artifacts(
        current_artifacts,
        str(message.get("text") or ""),
        str(result.get("output") or ""),
    )
    deliverable_artifacts: list[dict[str, Any]] = []
    seen_artifact_paths: set[str] = set()
    for artifact in [*delta_artifacts, *requested_artifacts]:
        path = str(artifact.get("path") or "").strip()
        if not path or path in seen_artifact_paths:
            continue
        deliverable_artifacts.append(artifact)
        seen_artifact_paths.add(path)

    resolved_deliverable_files = _resolve_feishu_artifact_file_paths(
        conversation,
        deliverable_artifacts,
    )
    sent_artifacts: list[dict[str, Any]] = []
    pending_artifacts: list[dict[str, Any]] = []
    delivery_notes: list[str] = []
    resolved_paths = {
        str(artifact.get("path") or "").strip() for artifact, _ in resolved_deliverable_files
    }
    pending_artifacts.extend(
        artifact
        for artifact in deliverable_artifacts
        if str(artifact.get("path") or "").strip() not in resolved_paths
    )

    for artifact, local_path in resolved_deliverable_files[:_FEISHU_MAX_DIRECT_FILE_MESSAGES]:
        if local_path.stat().st_size > _FEISHU_MAX_DIRECT_FILE_SIZE_BYTES:
            pending_artifacts.append(artifact)
            continue
        try:
            await asyncio.to_thread(
                _send_feishu_file_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                file_path=local_path,
                file_name=local_path.name,
            )
            sent_artifacts.append(artifact)
        except Exception as exc:
            logger.warning(
                "Failed to send Feishu deliverable file: %s",
                exc,
                extra={
                    "publication_id": str(publication.publication_id),
                    "conversation_id": str(conversation.conversation_id),
                    "artifact_path": str(artifact.get("path") or ""),
                },
            )
            delivery_note = _classify_feishu_file_delivery_error(exc)
            if delivery_note:
                delivery_notes.append(delivery_note)
            pending_artifacts.append(artifact)

    if len(resolved_deliverable_files) > _FEISHU_MAX_DIRECT_FILE_MESSAGES:
        pending_artifacts.extend(
            artifact
            for artifact, _ in resolved_deliverable_files[_FEISHU_MAX_DIRECT_FILE_MESSAGES:]
        )

    deduped_pending: list[dict[str, Any]] = []
    seen_pending_paths: set[str] = set()
    for artifact in pending_artifacts:
        path = str(artifact.get("path") or "").strip()
        if not path or path in seen_pending_paths:
            continue
        deduped_pending.append(artifact)
        seen_pending_paths.add(path)

    if (
        not deliverable_artifacts
        and not deduped_pending
        and not sent_artifacts
        and _looks_like_feishu_file_send_request(str(message.get("text") or ""))
    ):
        delivery_notes.append(
            "如果需要发送现有工作区文件，请在消息里写明文件名或路径，例如 output/report.md。"
        )

    reply_text = _build_feishu_reply_text(
        agent=agent,
        conversation=conversation,
        output_text=str(result.get("output") or ""),
        delivered_artifacts=sent_artifacts,
        pending_artifacts=deduped_pending,
        delivery_notes=delivery_notes,
        base_url=base_url or _resolve_public_web_base_url(),
    )
    if reply_text.strip():
        await asyncio.to_thread(
            _send_feishu_text_message,
            publication,
            chat_id=str(message.get("chat_id") or ""),
            text=reply_text,
        )
    return {"success": True}


@router.post("/feishu/{publication_id}/events")
async def handle_feishu_events(publication_id: str, request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    with get_db_session() as session:
        publication = _load_publication_or_raise(session, publication_id)
        if publication.status != "published":
            raise HTTPException(status_code=409, detail="Feishu publication is not active")
        _validate_feishu_verification_token(payload, publication)

        if payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        message = _extract_feishu_message(payload)
        if message is None:
            return {"success": True, "ignored": True}
    return await process_feishu_publication_message(
        publication_id,
        message,
        base_url=_resolve_public_web_base_url(request),
    )
