"""External channel webhook endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import requests
from fastapi import APIRouter, HTTPException, Request

from access_control.permissions import CurrentUser
from agent_framework.persistent_conversations import build_default_conversation_title
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
from shared.secret_crypto import decrypt_text

logger = get_logger(__name__)
router = APIRouter()

_FEISHU_API_BASE = "https://open.feishu.cn/open-apis"
_TENANT_TOKEN_CACHE: dict[str, tuple[str, datetime]] = {}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _load_publication_or_raise(session, publication_id: str) -> AgentChannelPublication:
    try:
        publication_uuid = UUID(publication_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid publication id") from exc

    publication = (
        session.query(AgentChannelPublication)
        .filter(AgentChannelPublication.publication_id == publication_uuid)
        .filter(AgentChannelPublication.channel_type == "feishu")
        .first()
    )
    if publication is None:
        raise HTTPException(status_code=404, detail="Feishu publication not found")
    return publication


def _publication_secrets(publication: AgentChannelPublication) -> dict[str, str]:
    encrypted = (
        dict(publication.secret_encrypted_json or {})
        if isinstance(publication.secret_encrypted_json, dict)
        else {}
    )
    secrets: dict[str, str] = {}
    for key, value in encrypted.items():
        if value:
            secrets[key] = decrypt_text(str(value))
    return secrets


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


def _extract_feishu_message(payload: dict[str, Any]) -> dict[str, Any] | None:
    header = payload.get("header") or {}
    if header.get("event_type") not in {"im.message.receive_v1"}:
        return None

    event = payload.get("event") or {}
    message = event.get("message") or {}
    sender = event.get("sender") or {}
    sender_id = sender.get("sender_id") or {}
    raw_content = message.get("content") or "{}"
    try:
        parsed_content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except json.JSONDecodeError:
        parsed_content = {}

    return {
        "event_id": header.get("event_id") or message.get("message_id"),
        "message_type": message.get("message_type"),
        "chat_id": message.get("chat_id"),
        "chat_type": message.get("chat_type"),
        "thread_key": message.get("root_id") or message.get("parent_id") or message.get("chat_id"),
        "text": str(parsed_content.get("text") or "").strip(),
        "open_id": sender_id.get("open_id"),
        "external_user_id": sender_id.get("user_id"),
        "union_id": sender_id.get("union_id"),
        "tenant_key": header.get("tenant_key"),
    }


def _get_feishu_tenant_access_token(publication: AgentChannelPublication) -> str:
    cache_key = str(publication.publication_id)
    cached = _TENANT_TOKEN_CACHE.get(cache_key)
    if cached and cached[1] > _utc_now():
        return cached[0]

    config = dict(publication.config_json or {}) if isinstance(publication.config_json, dict) else {}
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
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", 0)) != 0:
        raise RuntimeError(payload.get("msg") or "Failed to fetch Feishu tenant access token")

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
        json={"receive_id": chat_id, "msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if int(payload.get("code", 0)) != 0:
        raise RuntimeError(payload.get("msg") or "Failed to send Feishu message")


def _user_can_access_agent(agent: Agent, user: User) -> bool:
    if str(agent.owner_user_id) == str(user.user_id):
        return True

    access_level = str(agent.access_level or "private").strip().lower()
    if access_level == "public":
        return True
    if access_level == "team":
        return bool(
            agent.department_id
            and user.department_id
            and str(agent.department_id) == str(user.department_id)
        )
    return False


def _find_external_binding(
    session,
    *,
    publication_id: UUID,
    open_id: str | None,
    external_user_id: str | None,
    union_id: str | None,
) -> UserExternalBinding | None:
    query = session.query(UserExternalBinding).filter(UserExternalBinding.publication_id == publication_id)
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


def _build_feishu_reply_text(
    *,
    request: Request,
    agent: Agent,
    conversation: AgentConversation,
    output_text: str,
    artifacts: list[dict[str, Any]] | None,
) -> str:
    base_text = output_text.strip() or "Agent execution completed."
    file_paths = [
        str(item.get("path") or "").strip()
        for item in (artifacts or [])
        if not item.get("is_dir") and str(item.get("path") or "").strip()
    ]
    if not file_paths:
        return base_text

    workspace_paths = "\n".join(f"- /workspace/{path}" for path in file_paths[:5])
    conversation_url = (
        f"{str(request.base_url).rstrip('/')}/workforce/{agent.agent_id}/conversations/{conversation.conversation_id}"
    )
    return (
        f"{base_text}\n\n"
        f"已更新工作区文件:\n{workspace_paths}\n\n"
        f"继续在网页查看对话与工作区: {conversation_url}"
    )


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
        if message.get("chat_type") != "p2p":
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前仅支持飞书单聊接入，请使用单聊继续对话。",
            )
            return {"success": True, "ignored": True}
        if message.get("message_type") != "text":
            await asyncio.to_thread(
                _send_feishu_text_message,
                publication,
                chat_id=str(message.get("chat_id") or ""),
                text="当前仅支持文本消息，请直接发送文本内容。",
            )
            return {"success": True, "ignored": True}

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

    result = await execute_persistent_conversation_turn(
        conversation=conversation,
        current_user=current_user,
        message=str(message.get("text") or ""),
        files=[],
        source="feishu",
        external_event_id=message.get("event_id"),
    )
    if result.get("duplicate"):
        return {"success": True, "duplicate": True}

    reply_text = _build_feishu_reply_text(
        request=request,
        agent=agent,
        conversation=conversation,
        output_text=str(result.get("output") or ""),
        artifacts=result.get("artifacts") or [],
    )
    await asyncio.to_thread(
        _send_feishu_text_message,
        publication,
        chat_id=str(message.get("chat_id") or ""),
        text=reply_text,
    )
    return {"success": True}
