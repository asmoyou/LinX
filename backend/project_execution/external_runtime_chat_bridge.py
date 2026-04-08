from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from agent_framework.persistent_conversations import is_default_conversation_title
from database.connection import get_db_session
from database.models import AgentConversation, AgentConversationMessage, AgentConversationSnapshot
from object_storage.minio_client import get_minio_client


def _object_ref(bucket_name: str, object_key: str) -> str:
    return f"minio:{bucket_name}:{object_key}"


def get_external_conversation_workspace_snapshot(
    *,
    conversation_id: UUID,
    agent_id: UUID,
) -> dict[str, Any] | None:
    with get_db_session() as session:
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == conversation_id)
            .filter(AgentConversation.agent_id == agent_id)
            .first()
        )
        if conversation is None:
            return None
        snapshot = (
            session.query(AgentConversationSnapshot)
            .filter(AgentConversationSnapshot.conversation_id == conversation_id)
            .filter(AgentConversationSnapshot.snapshot_status == "ready")
            .order_by(AgentConversationSnapshot.generation.desc())
            .first()
        )
        if snapshot is None or not snapshot.archive_ref:
            return None

    minio = get_minio_client()
    parsed = minio.parse_object_reference(snapshot.archive_ref)
    if not parsed:
        return None
    bucket_name, object_key = parsed
    archive_stream, _ = minio.download_file(bucket_name, object_key)
    archive_bytes = archive_stream.read()
    return {
        "archive_base64": base64.b64encode(archive_bytes).decode("utf-8"),
        "checksum": str(snapshot.checksum or ""),
        "generation": int(snapshot.generation or 0),
        "size_bytes": int(snapshot.size_bytes or 0),
    }


def persist_external_conversation_workspace_snapshot(
    *,
    conversation_id: UUID,
    archive_bytes: bytes,
    workspace_bytes_estimate: int = 0,
    workspace_file_count_estimate: int = 0,
    snapshot_status: str = "ready",
) -> AgentConversationSnapshot | None:
    checksum = hashlib.sha256(archive_bytes).hexdigest()
    minio = get_minio_client()
    bucket_name = minio.buckets["artifacts"]

    with get_db_session() as session:
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == conversation_id)
            .first()
        )
        if conversation is None:
            return None

        previous_ready = (
            session.query(AgentConversationSnapshot)
            .filter(AgentConversationSnapshot.conversation_id == conversation_id)
            .filter(AgentConversationSnapshot.snapshot_status == "ready")
            .order_by(AgentConversationSnapshot.generation.desc())
            .first()
        )
        next_generation = int(previous_ready.generation if previous_ready else 0) + 1
        archive_key = (
            f"{conversation.agent_id}/{conversation_id}/{next_generation:06d}/workspace.tar.gz"
        )
        manifest_key = (
            f"{conversation.agent_id}/{conversation_id}/{next_generation:06d}/manifest.json"
        )
        metadata = {
            "conversation_id": str(conversation_id),
            "agent_id": str(conversation.agent_id),
            "owner_user_id": str(conversation.owner_user_id),
            "generation": str(next_generation),
        }
        minio.client.put_object(
            bucket_name=bucket_name,
            object_name=archive_key,
            data=io.BytesIO(archive_bytes),
            length=len(archive_bytes),
            content_type="application/gzip",
            metadata=metadata,
        )
        manifest_bytes = json.dumps(
            {"entries": [], "generated_at": datetime.now(timezone.utc).isoformat()},
            ensure_ascii=False,
        ).encode("utf-8")
        minio.client.put_object(
            bucket_name=bucket_name,
            object_name=manifest_key,
            data=io.BytesIO(manifest_bytes),
            length=len(manifest_bytes),
            content_type="application/json",
            metadata=metadata,
        )

        snapshot = AgentConversationSnapshot(
            conversation_id=conversation_id,
            generation=next_generation,
            archive_ref=_object_ref(bucket_name, archive_key),
            manifest_ref=_object_ref(bucket_name, manifest_key),
            size_bytes=len(archive_bytes),
            checksum=checksum,
            snapshot_status=snapshot_status,
        )
        session.add(snapshot)
        session.flush()

        if snapshot_status == "ready":
            conversation.latest_snapshot_id = snapshot.snapshot_id
            conversation.updated_at = datetime.now(timezone.utc)
            if hasattr(conversation, "workspace_bytes_estimate"):
                conversation.workspace_bytes_estimate = int(workspace_bytes_estimate or 0)
            if hasattr(conversation, "workspace_file_count_estimate"):
                conversation.workspace_file_count_estimate = int(
                    workspace_file_count_estimate or 0
                )
            if hasattr(conversation, "last_workspace_decay_at"):
                conversation.last_workspace_decay_at = datetime.now(timezone.utc)
            if previous_ready:
                previous_ready.snapshot_status = "superseded"

        session.commit()
        session.refresh(snapshot)

    if previous_ready:
        for ref in (previous_ready.archive_ref, previous_ready.manifest_ref):
            parsed = minio.parse_object_reference(ref)
            if not parsed:
                continue
            bucket, key = parsed
            try:
                minio.delete_file_versions(bucket, key)
            except Exception:
                continue
    return snapshot


def persist_external_conversation_completion(
    *,
    conversation_id: UUID,
    result_payload: Optional[dict[str, Any]] = None,
) -> AgentConversationMessage | None:
    payload = dict(result_payload or {})
    assistant_text = str(
        payload.get("assistant_message")
        or payload.get("final_output")
        or payload.get("output")
        or ""
    ).strip()
    if not assistant_text:
        return None

    content_json: dict[str, Any] = {}
    if isinstance(payload.get("usage"), dict) and payload["usage"]:
        content_json["stats"] = dict(payload["usage"])
    if isinstance(payload.get("rounds"), list) and payload["rounds"]:
        content_json["rounds"] = list(payload["rounds"])
    if isinstance(payload.get("artifacts"), list) and payload["artifacts"]:
        content_json["artifacts"] = list(payload["artifacts"])

    with get_db_session() as session:
        conversation = (
            session.query(AgentConversation)
            .filter(AgentConversation.conversation_id == conversation_id)
            .first()
        )
        if conversation is None:
            return None

        message = AgentConversationMessage(
            conversation_id=conversation_id,
            role="assistant",
            content_text=assistant_text,
            content_json=content_json or None,
            attachments_json=None,
            source="web",
        )
        session.add(message)
        now = datetime.now(timezone.utc)
        conversation.last_message_at = now
        conversation.updated_at = now
        title = str(payload.get("conversation_title") or "").strip()
        if title and is_default_conversation_title(str(conversation.title or "")):
            conversation.title = title[:255]
        session.commit()
        session.refresh(message)
        return message
