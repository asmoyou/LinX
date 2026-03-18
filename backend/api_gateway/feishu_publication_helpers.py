"""Shared Feishu publication helpers for webhook and long-connection flows."""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request

from database.models import AgentChannelPublication
from shared.config import get_config
from shared.secret_crypto import decrypt_text


def load_publication_or_raise(session, publication_id: str) -> AgentChannelPublication:
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


def publication_secrets(publication: AgentChannelPublication) -> dict[str, str]:
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


def extract_feishu_message(payload: dict[str, Any]) -> dict[str, Any] | None:
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
        "message_id": message.get("message_id"),
        "message_type": message.get("message_type"),
        "chat_id": message.get("chat_id"),
        "chat_type": message.get("chat_type"),
        "thread_key": message.get("root_id") or message.get("parent_id") or message.get("chat_id"),
        "text": str(parsed_content.get("text") or "").strip(),
        "content_payload": parsed_content if isinstance(parsed_content, dict) else {},
        "open_id": sender_id.get("open_id"),
        "external_user_id": sender_id.get("user_id"),
        "union_id": sender_id.get("union_id"),
        "tenant_key": header.get("tenant_key"),
    }


def extract_feishu_message_from_long_connection_event(event: Any) -> dict[str, Any] | None:
    header = getattr(event, "header", None)
    if getattr(header, "event_type", None) not in {"im.message.receive_v1"}:
        return None

    event_data = getattr(event, "event", None)
    message = getattr(event_data, "message", None)
    sender = getattr(event_data, "sender", None)
    sender_id = getattr(sender, "sender_id", None)
    raw_content = getattr(message, "content", None) or "{}"
    try:
        parsed_content = json.loads(raw_content) if isinstance(raw_content, str) else raw_content
    except json.JSONDecodeError:
        parsed_content = {}

    return {
        "event_id": getattr(header, "event_id", None) or getattr(message, "message_id", None),
        "message_id": getattr(message, "message_id", None),
        "message_type": getattr(message, "message_type", None),
        "chat_id": getattr(message, "chat_id", None),
        "chat_type": getattr(message, "chat_type", None),
        "thread_key": getattr(message, "root_id", None)
        or getattr(message, "parent_id", None)
        or getattr(message, "chat_id", None),
        "text": str(parsed_content.get("text") or "").strip(),
        "content_payload": parsed_content if isinstance(parsed_content, dict) else {},
        "open_id": getattr(sender_id, "open_id", None),
        "external_user_id": getattr(sender_id, "user_id", None),
        "union_id": getattr(sender_id, "union_id", None),
        "tenant_key": getattr(header, "tenant_key", None) or getattr(sender, "tenant_key", None),
    }


def resolve_public_web_base_url(request: Request | None = None) -> str | None:
    if request is not None:
        return str(request.base_url).rstrip("/")

    env_base_url = str(
        os.getenv("LINX_PUBLIC_BASE_URL") or os.getenv("PUBLIC_BASE_URL") or ""
    ).strip()
    if env_base_url:
        return env_base_url.rstrip("/")

    origins = get_config().get("api.cors.origins", default=[]) or []
    if isinstance(origins, str):
        origins = [origins]
    for origin in origins:
        normalized = str(origin or "").strip()
        if normalized and normalized != "*":
            return normalized.rstrip("/")
    return None
