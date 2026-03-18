"""History compaction for persistent conversations."""

from __future__ import annotations

import asyncio
import gzip
import io
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from langchain_core.messages import HumanMessage, SystemMessage

from agent_framework.agent_conversation_runner import _build_llm_for_agent
from database.connection import get_db_session
from database.models import (
    Agent,
    AgentConversation,
    AgentConversationHistorySummary,
    AgentConversationMessage,
    AgentConversationMessageArchive,
)
from object_storage.minio_client import get_minio_client
from shared.config import Config, get_config

logger = logging.getLogger(__name__)

SUMMARY_KEYS = (
    "goals",
    "decisions",
    "important_files",
    "user_preferences",
    "pending_work",
    "deliverables",
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cfg_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _cfg_int(
    value: Any,
    default: int,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _normalize_summary_json(value: Any) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    raw = value if isinstance(value, dict) else {}
    for key in SUMMARY_KEYS:
        items = raw.get(key) if isinstance(raw, dict) else None
        values: list[str] = []
        if isinstance(items, list):
            for item in items:
                text = " ".join(str(item or "").split()).strip()
                if text:
                    values.append(text[:320])
        normalized[key] = values
    return normalized


def _summary_json_to_text(summary_json: dict[str, list[str]]) -> str:
    labels = {
        "goals": "Goals",
        "decisions": "Decisions",
        "important_files": "Important files",
        "user_preferences": "User preferences",
        "pending_work": "Pending work",
        "deliverables": "Deliverables",
    }
    lines: list[str] = []
    for key in SUMMARY_KEYS:
        values = list(summary_json.get(key) or [])
        if not values:
            continue
        lines.append(f"{labels[key]}:")
        lines.extend(f"- {item}" for item in values[:12])
    return "\n".join(lines).strip()


def _extract_json_object(raw_text: Any) -> Optional[dict[str, Any]]:
    text = str(raw_text or "").strip()
    if not text:
        return None

    candidates = [text]
    fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, flags=re.IGNORECASE)
    if fenced:
        candidates.append(fenced.group(1))
    left = text.find("{")
    right = text.rfind("}")
    if left >= 0 and right > left:
        candidates.append(text[left : right + 1])

    seen: set[str] = set()
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            parsed = json.loads(normalized)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _trim_text(value: Any, max_chars: int = 220) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _serialize_message_record(message: AgentConversationMessage) -> dict[str, Any]:
    return {
        "message_id": str(message.message_id),
        "conversation_id": str(message.conversation_id),
        "role": message.role,
        "content_text": message.content_text,
        "content_json": message.content_json,
        "attachments_json": message.attachments_json,
        "source": message.source,
        "external_event_id": message.external_event_id,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _split_messages_by_turn_window(
    messages: list[AgentConversationMessage],
    turn_window: int,
) -> tuple[list[AgentConversationMessage], list[AgentConversationMessage]]:
    if not messages:
        return [], []

    current_turn = 0
    turn_indexes: list[int] = []
    for message in messages:
        if message.role == "user":
            current_turn += 1
        turn_indexes.append(current_turn)

    if current_turn <= turn_window:
        return [], list(messages)

    cutoff_turn = max(current_turn - turn_window, 0)
    older: list[AgentConversationMessage] = []
    recent: list[AgentConversationMessage] = []
    for message, turn_index in zip(messages, turn_indexes):
        if turn_index <= cutoff_turn:
            older.append(message)
        else:
            recent.append(message)
    return older, recent


def _build_fallback_summary_text(messages: list[AgentConversationMessage]) -> Optional[str]:
    if not messages:
        return None

    user_lines: list[str] = []
    assistant_lines: list[str] = []
    important_files: list[str] = []
    for message in messages:
        if message.role == "user" and message.content_text:
            user_lines.append(_trim_text(message.content_text, max_chars=180))
        elif message.role == "assistant" and message.content_text:
            assistant_lines.append(_trim_text(message.content_text, max_chars=220))

        if isinstance(message.content_json, dict):
            for key in ("artifacts", "artifactDelta"):
                for item in list(message.content_json.get(key) or []):
                    if not isinstance(item, dict):
                        continue
                    path = " ".join(str(item.get("path") or "").split()).strip()
                    if path:
                        important_files.append(path)

    summary_json = {
        "goals": user_lines[:6],
        "decisions": assistant_lines[:6],
        "important_files": important_files[:8],
        "user_preferences": [],
        "pending_work": assistant_lines[-3:],
        "deliverables": important_files[:6],
    }
    text = _summary_json_to_text(_normalize_summary_json(summary_json))
    return text or None


@dataclass(frozen=True)
class ConversationHistoryCompactionSettings:
    enabled: bool = True
    recent_turn_window: int = 40
    min_message_age_hours: int = 24
    archive_expiry_days: int = 90

    def with_defaults(self) -> "ConversationHistoryCompactionSettings":
        return ConversationHistoryCompactionSettings(
            enabled=self.enabled,
            recent_turn_window=self.recent_turn_window,
            min_message_age_hours=self.min_message_age_hours,
            archive_expiry_days=self.archive_expiry_days,
        )


def load_conversation_history_compaction_settings(
    config: Optional[Config] = None,
) -> ConversationHistoryCompactionSettings:
    cfg = config or get_config()
    raw_history = cfg.get("persistent_conversations.history", {}) or {}
    raw_lifecycle = cfg.get("persistent_conversations.lifecycle", {}) or {}
    return ConversationHistoryCompactionSettings(
        enabled=_cfg_bool(raw_history.get("compaction_enabled"), True),
        recent_turn_window=_cfg_int(
            raw_history.get("recent_turn_window"),
            40,
            minimum=4,
            maximum=200,
        ),
        min_message_age_hours=_cfg_int(
            raw_history.get("min_message_age_hours"),
            24,
            minimum=1,
            maximum=24 * 30,
        ),
        archive_expiry_days=_cfg_int(
            raw_lifecycle.get("delete_after_days"),
            90,
            minimum=7,
            maximum=3650,
        ),
    ).with_defaults()


class ConversationHistoryCompactionService:
    def __init__(
        self,
        *,
        settings: Optional[ConversationHistoryCompactionSettings] = None,
    ) -> None:
        self.settings = (
            settings or load_conversation_history_compaction_settings()
        ).with_defaults()

    def load_history_window(self, conversation_id: UUID) -> dict[str, Any]:
        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                return {
                    "summary_text": None,
                    "summary_json": None,
                    "summary_row": None,
                    "recent_messages": [],
                    "older_message_count": 0,
                    "compacted_message_count": 0,
                    "archived_segment_count": 0,
                    "recent_window_size": 0,
                }

            messages = (
                session.query(AgentConversationMessage)
                .filter(AgentConversationMessage.conversation_id == conversation_id)
                .filter(AgentConversationMessage.role.in_(("user", "assistant")))
                .order_by(AgentConversationMessage.created_at.asc())
                .all()
            )
            older_messages, recent_messages = _split_messages_by_turn_window(
                messages,
                self.settings.recent_turn_window,
            )
            summary_row = (
                session.query(AgentConversationHistorySummary)
                .filter(AgentConversationHistorySummary.conversation_id == conversation_id)
                .first()
            )
            archived_segment_count = (
                session.query(AgentConversationMessageArchive)
                .filter(AgentConversationMessageArchive.conversation_id == conversation_id)
                .count()
            )

            summary_text = summary_row.summary_text if summary_row else None
            summary_json = (
                _normalize_summary_json(summary_row.summary_json)
                if summary_row and isinstance(summary_row.summary_json, dict)
                else None
            )
            fallback_summary_text = (
                _build_fallback_summary_text(older_messages) if older_messages else None
            )
            if summary_text and fallback_summary_text:
                summary_text = f"{summary_text}\n\nRecent older raw message highlights:\n{fallback_summary_text}"
            elif not summary_text and fallback_summary_text:
                summary_text = fallback_summary_text

            return {
                "summary_text": summary_text,
                "summary_json": summary_json,
                "summary_row": summary_row,
                "recent_messages": recent_messages,
                "older_message_count": len(older_messages),
                "compacted_message_count": int(conversation.compacted_message_count or 0),
                "archived_segment_count": int(archived_segment_count or 0),
                "recent_window_size": self.settings.recent_turn_window,
            }

    async def compact_conversation(
        self,
        conversation_id: UUID,
        *,
        reason: str = "manual",
        recent_turn_window: Optional[int] = None,
    ) -> dict[str, Any]:
        if not self.settings.enabled:
            return {"status": "disabled", "reason": reason, "conversation_id": str(conversation_id)}

        effective_turn_window = max(int(recent_turn_window or self.settings.recent_turn_window), 1)
        with get_db_session() as session:
            conversation = (
                session.query(AgentConversation)
                .filter(AgentConversation.conversation_id == conversation_id)
                .first()
            )
            if conversation is None:
                return {
                    "status": "missing",
                    "reason": reason,
                    "conversation_id": str(conversation_id),
                }

            agent = session.query(Agent).filter(Agent.agent_id == conversation.agent_id).first()
            if agent is None:
                return {
                    "status": "missing_agent",
                    "reason": reason,
                    "conversation_id": str(conversation_id),
                }

            messages = (
                session.query(AgentConversationMessage)
                .filter(AgentConversationMessage.conversation_id == conversation_id)
                .filter(AgentConversationMessage.role.in_(("user", "assistant")))
                .order_by(AgentConversationMessage.created_at.asc())
                .all()
            )
            older_messages, _recent_messages = _split_messages_by_turn_window(
                messages,
                effective_turn_window,
            )
            cutoff = _utcnow() - timedelta(hours=self.settings.min_message_age_hours)
            compactable = [
                message
                for message in older_messages
                if message.created_at and message.created_at <= cutoff
            ]
            if not compactable:
                return {
                    "status": "skipped",
                    "reason": reason,
                    "conversation_id": str(conversation_id),
                    "skip_reason": "no_eligible_messages",
                }

            summary_row = (
                session.query(AgentConversationHistorySummary)
                .filter(AgentConversationHistorySummary.conversation_id == conversation_id)
                .first()
            )
            previous_summary_json = (
                _normalize_summary_json(summary_row.summary_json)
                if summary_row and isinstance(summary_row.summary_json, dict)
                else None
            )

            archive_payload = self._build_archive_payload(compactable)
            archive_ref = self._upload_archive(
                conversation=conversation,
                archive_payload=archive_payload,
                reason=reason,
            )

            try:
                summary_json = await self._generate_summary_json(
                    agent=agent,
                    previous_summary_json=previous_summary_json,
                    compacted_messages=compactable,
                )
            except Exception as exc:
                self._delete_archive_ref(archive_ref)
                logger.warning(
                    "Conversation history summary generation failed for %s: %s",
                    conversation_id,
                    exc,
                )
                return {
                    "status": "skipped",
                    "reason": reason,
                    "conversation_id": str(conversation_id),
                    "skip_reason": "summary_generation_failed",
                    "error": str(exc),
                }

            if not summary_json:
                self._delete_archive_ref(archive_ref)
                return {
                    "status": "skipped",
                    "reason": reason,
                    "conversation_id": str(conversation_id),
                    "skip_reason": "summary_generation_failed",
                }

            summary_text = _summary_json_to_text(summary_json)
            now = _utcnow()
            expires_at = conversation.delete_after or (
                now + timedelta(days=self.settings.archive_expiry_days)
            )
            archive_row = AgentConversationMessageArchive(
                conversation_id=conversation_id,
                start_message_id=compactable[0].message_id,
                end_message_id=compactable[-1].message_id,
                message_count=len(compactable),
                archive_ref=archive_ref,
                expires_at=expires_at,
                status="ready",
            )
            session.add(archive_row)

            if summary_row is None:
                summary_row = AgentConversationHistorySummary(
                    conversation_id=conversation_id,
                    created_at=now,
                )
                session.add(summary_row)

            summary_row.covers_until_message_id = compactable[-1].message_id
            summary_row.covers_until_created_at = compactable[-1].created_at
            summary_row.raw_message_count = int(summary_row.raw_message_count or 0) + len(
                compactable
            )
            summary_row.summary_text = summary_text
            summary_row.summary_json = summary_json
            summary_row.updated_at = now

            for message in compactable:
                session.delete(message)

            conversation.last_history_compaction_at = now
            conversation.compacted_message_count = int(
                conversation.compacted_message_count or 0
            ) + len(compactable)
            if conversation.storage_tier == "hot":
                conversation.storage_tier = "compacted"
            conversation.updated_at = now

            session.commit()
            return {
                "status": "ok",
                "reason": reason,
                "conversation_id": str(conversation_id),
                "archived_messages": len(compactable),
                "archive_ref": archive_ref,
                "summary_text": summary_text,
            }

    def _build_archive_payload(self, messages: list[AgentConversationMessage]) -> bytes:
        lines = [
            json.dumps(_serialize_message_record(message), ensure_ascii=False).encode("utf-8")
            for message in messages
        ]
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb") as stream:
            for line in lines:
                stream.write(line)
                stream.write(b"\n")
        return buffer.getvalue()

    def _upload_archive(
        self,
        *,
        conversation: AgentConversation,
        archive_payload: bytes,
        reason: str,
    ) -> str:
        minio = get_minio_client()
        bucket_name = minio.buckets["artifacts"]
        object_key = (
            f"{conversation.agent_id}/{conversation.conversation_id}/history/"
            f"{_utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex}.jsonl.gz"
        )
        minio.client.put_object(
            bucket_name=bucket_name,
            object_name=object_key,
            data=io.BytesIO(archive_payload),
            length=len(archive_payload),
            content_type="application/gzip",
            metadata={
                "conversation_id": str(conversation.conversation_id),
                "agent_id": str(conversation.agent_id),
                "reason": reason,
            },
        )
        return f"minio:{bucket_name}:{object_key}"

    def _delete_archive_ref(self, archive_ref: str) -> None:
        minio = get_minio_client()
        parsed = minio.parse_object_reference(archive_ref)
        if not parsed:
            return
        bucket_name, object_key = parsed
        try:
            minio.delete_file_versions(bucket_name, object_key)
        except Exception as exc:
            logger.warning(
                "Failed to delete compacted archive %s/%s: %s", bucket_name, object_key, exc
            )

    async def _generate_summary_json(
        self,
        *,
        agent: Agent,
        previous_summary_json: Optional[dict[str, list[str]]],
        compacted_messages: list[AgentConversationMessage],
    ) -> Optional[dict[str, list[str]]]:
        transcript_lines: list[str] = []
        for message in compacted_messages[-120:]:
            role_label = "User" if message.role == "user" else "Assistant"
            transcript_lines.append(
                f"{role_label}: {_trim_text(message.content_text, max_chars=400)}"
            )

        previous_summary_text = (
            json.dumps(previous_summary_json, ensure_ascii=False, indent=2)
            if previous_summary_json
            else "{}"
        )
        prompt = (
            "Summarize the archived persistent conversation history.\n"
            "Return JSON only.\n"
            "The JSON object must contain these keys exactly: "
            '"goals", "decisions", "important_files", "user_preferences", '
            '"pending_work", "deliverables".\n'
            "Each key must map to an array of short strings.\n"
            "Keep durable facts only. Omit transient retries, tool noise, and duplicate items.\n\n"
            "Previous summary JSON:\n"
            f"{previous_summary_text}\n\n"
            "New archived transcript:\n"
            f"{chr(10).join(transcript_lines)}"
        )

        llm = _build_llm_for_agent(
            agent,
            streaming=False,
            temperature=0.1,
            max_tokens=900,
        )
        response = await asyncio.to_thread(
            llm.invoke,
            [
                SystemMessage(
                    content=(
                        "You produce compact JSON summaries for archived chat history. "
                        "Return JSON only with the required keys."
                    )
                ),
                HumanMessage(content=prompt),
            ],
        )
        additional_kwargs = getattr(response, "additional_kwargs", {}) or {}
        raw_candidates = [
            additional_kwargs.get("final_content"),
            getattr(response, "content", response),
            additional_kwargs.get("reasoning_content"),
        ]
        for raw_candidate in raw_candidates:
            parsed = _extract_json_object(raw_candidate)
            if parsed:
                return _normalize_summary_json(parsed)
        return None


_history_compaction_service: Optional[ConversationHistoryCompactionService] = None


def get_conversation_history_compaction_service() -> ConversationHistoryCompactionService:
    global _history_compaction_service
    if _history_compaction_service is None:
        _history_compaction_service = ConversationHistoryCompactionService()
    return _history_compaction_service


__all__ = [
    "ConversationHistoryCompactionService",
    "ConversationHistoryCompactionSettings",
    "get_conversation_history_compaction_service",
    "load_conversation_history_compaction_settings",
]
