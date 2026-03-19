"""Persistence layer for session ledgers, user memory, and learned skill candidates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_

from database.connection import get_db_session
from database.models import (
    SessionLedger,
    SessionLedgerEvent,
    SkillCandidate,
    UserMemoryEmbeddingJob,
    UserMemoryEntry,
    UserMemoryLink,
    UserMemoryRelation,
    UserMemoryView,
)
from shared.datetime_utils import utcnow
from user_memory.fact_identity import build_user_fact_identity, build_user_memory_view_key
from user_memory.indexing_jobs import enqueue_user_memory_upsert_job
from user_memory.vector_documents import parse_event_time_range
from user_memory.vector_index import (
    build_user_memory_embedding_signature,
    resolve_active_user_memory_collection,
)


@dataclass
class SessionLedgerSnapshot:
    """Serializable payload for one session-ledger snapshot."""

    session_id: str
    agent_id: str
    user_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    status: str
    end_reason: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionLedgerEventData:
    """Structured event row for one persisted session snapshot."""

    event_index: int
    event_kind: str
    role: Optional[str]
    content: str
    event_timestamp: Optional[datetime] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryObservationData:
    """In-memory normalized observation derived from session turns."""

    observation_key: str
    observation_type: str
    title: str
    summary: Optional[str] = None
    details: Optional[str] = None
    source_event_indexes: List[int] = field(default_factory=list)
    confidence: float = 0.7
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryProjectionData:
    """In-memory projection rows routed into user views or skill candidates."""

    owner_type: str
    owner_id: str
    projection_type: str
    projection_key: str
    title: str
    summary: Optional[str] = None
    details: Optional[str] = None
    status: str = "active"
    payload: Dict[str, Any] = field(default_factory=dict)
    source_observation_key: Optional[str] = None


@dataclass
class MemoryEntryData:
    """Atomic user-memory entry derived from a normalized observation."""

    owner_type: str
    owner_id: str
    entry_type: str
    entry_key: str
    canonical_text: str
    summary: Optional[str] = None
    details: Optional[str] = None
    confidence: float = 0.7
    importance: float = 0.5
    status: str = "active"
    payload: Dict[str, Any] = field(default_factory=dict)
    source_event_indexes: List[int] = field(default_factory=list)


@dataclass
class MemoryLinkData:
    """Lineage or supersession link between durable user-memory entries."""

    source_kind: str
    source_id: int
    target_kind: str
    target_id: int
    link_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source_session_id: Optional[int] = None


@dataclass
class MemoryRelationData:
    """Typed user-memory relationship edge derived from a normalized observation."""

    owner_id: str
    relation_key: str
    predicate: str
    object_text: str
    canonical_text: str
    confidence: float = 0.7
    importance: float = 0.5
    status: str = "active"
    payload: Dict[str, Any] = field(default_factory=dict)
    event_time: Optional[str] = None
    location: Optional[str] = None
    source_entry_id: Optional[int] = None
    source_session_ledger_id: Optional[int] = None


MemorySessionSnapshot = SessionLedgerSnapshot
MemorySessionEventData = SessionLedgerEventData


class SessionLedgerRepository:
    """Persistence layer for session-ledger snapshots and final memory products."""

    @staticmethod
    def _current_vector_target() -> tuple[str, str]:
        return (
            resolve_active_user_memory_collection(),
            build_user_memory_embedding_signature(),
        )

    @staticmethod
    def _mark_row_vector_pending(row: Any, *, collection_name: str) -> None:
        if hasattr(row, "vector_sync_state"):
            row.vector_sync_state = "pending"
        if hasattr(row, "vector_document_hash"):
            row.vector_document_hash = None
        if hasattr(row, "vector_collection_name"):
            row.vector_collection_name = str(collection_name)
        if hasattr(row, "vector_indexed_at"):
            row.vector_indexed_at = None
        if hasattr(row, "vector_error"):
            row.vector_error = None

    @staticmethod
    def _normalize_review_status(status: str, payload: Dict[str, Any]) -> str:
        payload_status = str(payload.get("review_status") or "").strip().lower()
        if payload_status in {"pending", "published", "rejected"}:
            return payload_status
        normalized = str(status or "").strip().lower()
        if normalized == "active":
            return "published"
        if normalized == "rejected":
            return "rejected"
        return "pending"

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        return [str(item).strip() for item in list(value or []) if str(item).strip()]

    @staticmethod
    def _int_list(value: Any) -> List[int]:
        normalized: List[int] = []
        for item in list(value or []):
            try:
                parsed = int(item)
            except (TypeError, ValueError):
                continue
            if parsed not in normalized:
                normalized.append(parsed)
        return normalized

    @classmethod
    def resolve_entry_identity(
        cls,
        *,
        entry: Optional[MemoryEntryData] = None,
        row: Optional[UserMemoryEntry] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[Any, Dict[str, Any], str, str]:
        source_payload = dict(
            payload
            or (dict(entry.payload or {}) if entry is not None else {})
            or (dict(row.entry_data or {}) if row is not None else {})
        )
        fact_kind = cls._first_text(
            source_payload.get("fact_kind"),
            getattr(row, "fact_kind", None),
            "preference",
        )
        raw_key = cls._first_text(
            source_payload.get("semantic_key"),
            source_payload.get("key"),
            source_payload.get("fact_key"),
            getattr(entry, "entry_key", None),
            getattr(row, "entry_key", None),
        )
        predicate = cls._first_text(
            source_payload.get("predicate"), getattr(row, "predicate", None)
        )
        obj = cls._first_text(source_payload.get("object"), getattr(row, "object_text", None))
        persons = cls._string_list(source_payload.get("persons") or getattr(row, "persons", None))
        entities = cls._string_list(
            source_payload.get("entities") or getattr(row, "entities", None)
        )
        event_time = cls._first_text(
            source_payload.get("event_time"),
            getattr(row, "event_time", None),
        )
        location = cls._first_text(
            source_payload.get("location"),
            getattr(row, "location", None),
        )
        topic = cls._first_text(source_payload.get("topic"), getattr(row, "topic", None))
        canonical_statement = cls._first_text(
            source_payload.get("canonical_statement"),
            getattr(entry, "summary", None),
            getattr(row, "summary", None),
            getattr(row, "canonical_text", None),
        )
        value = cls._first_text(
            source_payload.get("value"),
            source_payload.get("fact_value"),
            obj,
            getattr(entry, "summary", None),
            getattr(row, "summary", None),
            canonical_statement,
        )
        identity = build_user_fact_identity(
            fact_kind=fact_kind,
            raw_key=raw_key,
            value=value,
            canonical_statement=canonical_statement or value,
            predicate=predicate or None,
            obj=obj or None,
            persons=persons,
            entities=entities,
            event_time=event_time or None,
            location=location or None,
            topic=topic or None,
        )
        source_payload["key"] = identity.fact_key
        source_payload["fact_key"] = identity.fact_key
        source_payload["semantic_key"] = identity.semantic_key
        source_payload["identity_signature"] = identity.identity_signature
        source_payload["fact_kind"] = identity.fact_kind
        if canonical_statement:
            source_payload["canonical_statement"] = canonical_statement
        if value:
            source_payload["value"] = value
        if predicate:
            source_payload["predicate"] = predicate
        if obj:
            source_payload["object"] = obj
        if persons:
            source_payload["persons"] = persons
        if entities:
            source_payload["entities"] = entities
        if event_time:
            source_payload["event_time"] = event_time
        if location:
            source_payload["location"] = location
        if topic:
            source_payload["topic"] = topic
        return identity, source_payload, canonical_statement, value

    @classmethod
    def resolve_view_identity(
        cls,
        *,
        projection: Optional[MemoryProjectionData] = None,
        row: Optional[UserMemoryView] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[Any, Dict[str, Any], str]:
        source_payload = dict(
            payload
            or (dict(projection.payload or {}) if projection is not None else {})
            or (dict(row.view_data or {}) if row is not None else {})
        )
        view_type = cls._first_text(
            getattr(projection, "projection_type", None),
            getattr(row, "view_type", None),
            "user_profile",
        )
        fact_kind = cls._first_text(
            source_payload.get("fact_kind"),
            "event" if str(view_type).strip().lower() == "episode" else "preference",
        )
        canonical_statement = cls._first_text(
            source_payload.get("canonical_statement"),
            getattr(projection, "summary", None),
            getattr(row, "content", None),
            getattr(row, "title", None),
        )
        value = cls._first_text(
            source_payload.get("value"),
            source_payload.get("object"),
            getattr(projection, "summary", None),
            getattr(projection, "title", None),
            getattr(row, "content", None),
            getattr(row, "title", None),
            canonical_statement,
        )
        identity, normalized_payload, _canonical_statement, _value = cls.resolve_entry_identity(
            payload={
                **source_payload,
                "fact_kind": fact_kind,
                "canonical_statement": canonical_statement,
                "value": value,
            }
        )
        view_key = build_user_memory_view_key(
            view_type=view_type,
            stable_key=identity.fact_key,
            canonical_statement=canonical_statement or value,
            event_time=normalized_payload.get("event_time"),
            value=value,
        )
        normalized_payload["key"] = identity.fact_key
        normalized_payload["fact_key"] = identity.fact_key
        normalized_payload["semantic_key"] = identity.semantic_key
        normalized_payload["identity_signature"] = identity.identity_signature
        if str(view_type).strip().lower() == "episode":
            normalized_payload["source_entry_key"] = identity.fact_key
        return identity, normalized_payload, view_key

    @classmethod
    def resolve_relation_identity(
        cls,
        *,
        relation: Optional[MemoryRelationData] = None,
        row: Optional[UserMemoryRelation] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[Any, Dict[str, Any]]:
        source_payload = dict(
            payload
            or (dict(relation.payload or {}) if relation is not None else {})
            or (dict(row.relation_data or {}) if row is not None else {})
        )
        predicate = cls._first_text(
            getattr(relation, "predicate", None),
            source_payload.get("predicate"),
            getattr(row, "predicate", None),
        )
        obj = cls._first_text(
            getattr(relation, "object_text", None),
            source_payload.get("object"),
            getattr(row, "object_text", None),
        )
        canonical_statement = cls._first_text(
            getattr(relation, "canonical_text", None),
            source_payload.get("canonical_statement"),
            getattr(row, "canonical_text", None),
        )
        persons = cls._string_list(source_payload.get("persons") or getattr(row, "persons", None))
        entities = cls._string_list(
            source_payload.get("entities") or getattr(row, "entities", None)
        )
        event_time = cls._first_text(
            getattr(relation, "event_time", None),
            source_payload.get("event_time"),
            getattr(row, "event_time", None),
        )
        location = cls._first_text(
            getattr(relation, "location", None),
            source_payload.get("location"),
            getattr(row, "location", None),
        )
        topic = cls._first_text(source_payload.get("topic"))
        raw_key = cls._first_text(
            source_payload.get("semantic_key"),
            source_payload.get("key"),
            getattr(relation, "relation_key", None),
            getattr(row, "relation_key", None),
        )
        identity = build_user_fact_identity(
            fact_kind="relationship",
            raw_key=raw_key,
            value=obj or canonical_statement,
            canonical_statement=canonical_statement or obj,
            predicate=predicate or None,
            obj=obj or None,
            persons=persons,
            entities=entities,
            event_time=event_time or None,
            location=location or None,
            topic=topic or None,
        )
        source_payload["key"] = identity.fact_key
        source_payload["semantic_key"] = identity.semantic_key
        source_payload["identity_signature"] = identity.identity_signature
        source_payload["fact_kind"] = "relationship"
        source_payload["predicate"] = predicate
        source_payload["object"] = obj
        if canonical_statement:
            source_payload["canonical_statement"] = canonical_statement
        if persons:
            source_payload["persons"] = persons
        if entities:
            source_payload["entities"] = entities
        if event_time:
            source_payload["event_time"] = event_time
        if location:
            source_payload["location"] = location
        if topic:
            source_payload["topic"] = topic
        return identity, source_payload

    @staticmethod
    def _apply_view_fields(
        row: UserMemoryView,
        *,
        projection: MemoryProjectionData,
        payload: Dict[str, Any],
        collection_name: Optional[str] = None,
    ) -> None:
        row.user_id = str(projection.owner_id)
        row.view_type = str(projection.projection_type)
        row.view_key = str(projection.projection_key)
        row.title = str(projection.title)
        row.content = str(projection.summary or projection.title or "")
        row.status = str(projection.status or "active")
        view_payload = dict(payload)
        if projection.details:
            view_payload["details"] = str(projection.details)
        row.view_data = view_payload
        if collection_name:
            SessionLedgerRepository._mark_row_vector_pending(
                row,
                collection_name=collection_name,
            )

    @staticmethod
    def _apply_skill_candidate_fields(
        row: SkillCandidate,
        *,
        snapshot: SessionLedgerSnapshot,
        candidate: MemoryProjectionData,
        payload: Dict[str, Any],
        session_ledger_id: Optional[int] = None,
    ) -> None:
        steps = [
            str(step).strip() for step in payload.get("successful_path") or [] if str(step).strip()
        ]
        existing_payload = (
            dict(row.candidate_payload or {}) if isinstance(row.candidate_payload, dict) else {}
        )
        merged_payload = {**existing_payload, **dict(payload)}
        existing_session_ids = SessionLedgerRepository._int_list(
            existing_payload.get("evidence_session_ledger_ids")
        )
        if session_ledger_id is not None and int(session_ledger_id) not in existing_session_ids:
            existing_session_ids.append(int(session_ledger_id))
        row.agent_id = str(candidate.owner_id)
        row.user_id = str(snapshot.user_id)
        row.cluster_key = str(candidate.projection_key)
        row.title = str(candidate.title)
        row.goal = str(payload.get("goal") or candidate.title)
        row.successful_path = steps or list(row.successful_path or [])
        row.why_it_worked = (
            str(payload.get("why_it_worked") or candidate.summary or row.why_it_worked or "") or None
        )
        row.applicability = str(payload.get("applicability") or row.applicability or "") or None
        row.avoid = str(payload.get("avoid") or row.avoid or "") or None
        row.confidence = max(float(row.confidence or 0.0), float(payload.get("confidence") or 0.72))
        next_review_status = SessionLedgerRepository._normalize_review_status(
            candidate.status,
            payload,
        )
        current_review_status = str(row.review_status or "").strip().lower()
        if current_review_status in {"published", "rejected"} and next_review_status == "pending":
            row.review_status = current_review_status
        else:
            row.review_status = next_review_status
        row.review_note = str(payload.get("review_note") or row.review_note or "") or None
        row.evidence_session_ledger_id = (
            int(session_ledger_id) if session_ledger_id is not None else row.evidence_session_ledger_id
        )
        if candidate.details:
            merged_payload.setdefault("review_content", str(candidate.details))
        if existing_session_ids:
            merged_payload["evidence_session_ledger_ids"] = existing_session_ids
        row.candidate_payload = merged_payload

    @staticmethod
    def _apply_entry_fields(
        row: UserMemoryEntry,
        *,
        entry: MemoryEntryData,
        payload: Dict[str, Any],
        source_session_ledger_id: Optional[int] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        existing_payload = dict(row.entry_data or {}) if isinstance(row.entry_data, dict) else {}
        existing_session_ids = SessionLedgerRepository._int_list(
            existing_payload.get("evidence_session_ledger_ids")
        )
        existing_evidence_count = int(existing_payload.get("evidence_count") or 0)
        new_evidence_count = int(payload.get("evidence_count") or 0)
        is_new_evidence_session = False
        if source_session_ledger_id is not None and int(source_session_ledger_id) not in existing_session_ids:
            existing_session_ids.append(int(source_session_ledger_id))
            is_new_evidence_session = True
        merged_event_indexes: List[int] = []
        for value in list(row.source_event_indexes or []) + list(entry.source_event_indexes or []):
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed not in merged_event_indexes:
                merged_event_indexes.append(parsed)
        row.user_id = str(entry.owner_id)
        row.entry_key = str(entry.entry_key)
        row.fact_kind = str(payload.get("fact_kind") or "preference")
        row.canonical_text = str(entry.canonical_text)
        row.summary = str(entry.summary) if entry.summary else row.summary
        row.predicate = str(payload.get("predicate") or "") or None
        row.object_text = str(payload.get("object") or "") or None
        row.event_time = str(payload.get("event_time") or "") or None
        row.location = str(payload.get("location") or "") or None
        row.persons = list(payload.get("persons") or [])
        row.entities = list(payload.get("entities") or [])
        row.topic = str(payload.get("topic") or "") or None
        row.confidence = max(float(row.confidence or 0.0), float(entry.confidence))
        row.importance = max(float(row.importance or 0.0), float(entry.importance))
        row.status = str(entry.status or "active")
        row.source_session_ledger_id = (
            int(source_session_ledger_id)
            if source_session_ledger_id is not None
            else row.source_session_ledger_id
        )
        row.source_event_indexes = merged_event_indexes
        merged_payload = {**existing_payload, **dict(payload)}
        if entry.details:
            merged_payload["details"] = entry.details
        latest_turn_ts = str(payload.get("latest_turn_ts") or "").strip()
        if latest_turn_ts:
            merged_payload["first_seen_at"] = str(
                existing_payload.get("first_seen_at") or latest_turn_ts
            )
            last_seen_at = str(existing_payload.get("last_seen_at") or "").strip()
            merged_payload["last_seen_at"] = (
                latest_turn_ts if not last_seen_at or latest_turn_ts > last_seen_at else last_seen_at
            )
        if new_evidence_count:
            merged_payload["evidence_count"] = existing_evidence_count + (
                new_evidence_count if is_new_evidence_session or not existing_payload else 0
            )
        elif existing_evidence_count:
            merged_payload["evidence_count"] = existing_evidence_count
        if existing_session_ids:
            merged_payload["evidence_session_ledger_ids"] = existing_session_ids
        row.entry_data = merged_payload
        event_time_start, event_time_end = parse_event_time_range(merged_payload.get("event_time"))
        row.event_time_start = event_time_start
        row.event_time_end = event_time_end
        if collection_name:
            SessionLedgerRepository._mark_row_vector_pending(
                row,
                collection_name=collection_name,
            )

    @staticmethod
    def _apply_relation_fields(
        row: UserMemoryRelation,
        *,
        relation: MemoryRelationData,
    ) -> None:
        row.user_id = str(relation.owner_id)
        row.relation_key = str(relation.relation_key)
        row.predicate = str(relation.predicate)
        row.subject_type = "user"
        row.subject_text = "user"
        row.object_text = str(relation.object_text)
        row.canonical_text = str(relation.canonical_text)
        row.event_time = str(relation.event_time or "") or None
        row.event_time_start, row.event_time_end = parse_event_time_range(relation.event_time)
        row.location = str(relation.location or "") or None
        row.persons = list(relation.payload.get("persons") or [])
        row.entities = list(relation.payload.get("entities") or [])
        row.confidence = float(relation.confidence)
        row.importance = float(relation.importance)
        row.status = str(relation.status or "active")
        row.source_entry_id = relation.source_entry_id
        row.source_session_ledger_id = relation.source_session_ledger_id
        row.relation_data = dict(relation.payload or {})

    @staticmethod
    def _enqueue_vector_job(
        db,
        *,
        row: Any,
        source_kind: str,
        collection_name: str,
        embedding_signature: str,
    ) -> None:
        enqueue_user_memory_upsert_job(
            db,
            source_kind=source_kind,
            source_id=int(row.id),
            user_id=str(row.user_id),
            collection_name=collection_name,
            embedding_signature=embedding_signature,
            payload={
                "status": getattr(row, "status", None),
            },
        )

    @staticmethod
    def _build_entry_from_observation(
        *,
        snapshot: SessionLedgerSnapshot,
        observation: MemoryObservationData,
    ) -> Optional[MemoryEntryData]:
        metadata = dict(observation.metadata or {})
        observation_type = str(observation.observation_type or "").strip()
        if observation_type not in {"user_preference_signal", "user_fact_signal"}:
            return None

        key = str(
            metadata.get("fact_key")
            or metadata.get("preference_key")
            or metadata.get("semantic_key")
            or ""
        ).strip()
        value = str(
            metadata.get("fact_value")
            or metadata.get("preference_value")
            or observation.summary
            or ""
        ).strip()
        if not key or not value:
            return None

        canonical_statement = str(
            metadata.get("canonical_statement") or observation.summary or ""
        ).strip()
        fact_kind = str(metadata.get("fact_kind") or "preference").strip()
        semantic_key = str(metadata.get("semantic_key") or key).strip() or key
        if observation_type == "user_preference_signal":
            canonical_text = f"user.preference.{semantic_key}={value}"
        else:
            canonical_text = canonical_statement or f"user.fact.{key}={value}"

        return MemoryEntryData(
            owner_type="user",
            owner_id=str(snapshot.user_id),
            entry_type="user_fact",
            entry_key=key,
            canonical_text=canonical_text,
            summary=(canonical_statement if observation_type != "user_preference_signal" else value)
            or value,
            details=observation.details,
            confidence=float(observation.confidence),
            importance=float(observation.importance),
            status="active",
            payload={
                "key": key,
                "value": value,
                "fact_kind": fact_kind,
                "semantic_key": semantic_key,
                "identity_signature": str(metadata.get("identity_signature") or "") or None,
                "canonical_statement": canonical_statement or None,
                "predicate": str(metadata.get("predicate") or "") or None,
                "object": str(metadata.get("object") or "") or None,
                "event_time": str(metadata.get("event_time") or "") or None,
                "persons": list(metadata.get("persons") or []),
                "entities": list(metadata.get("entities") or []),
                "location": str(metadata.get("location") or "") or None,
                "topic": str(metadata.get("topic") or "") or None,
                "origin": "session_observation",
                **metadata,
            },
            source_event_indexes=list(observation.source_event_indexes or []),
        )

    @staticmethod
    def _build_relation_from_observation(
        *,
        snapshot: SessionLedgerSnapshot,
        observation: MemoryObservationData,
        source_entry_id: Optional[int],
        source_session_ledger_id: Optional[int],
    ) -> Optional[MemoryRelationData]:
        metadata = dict(observation.metadata or {})
        if str(metadata.get("fact_kind") or "").strip() != "relationship":
            return None

        predicate = str(metadata.get("predicate") or "").strip()
        object_text = str(metadata.get("object") or metadata.get("fact_value") or "").strip()
        canonical_text = str(
            metadata.get("canonical_statement") or observation.summary or observation.title or ""
        ).strip()
        relation_key = str(
            metadata.get("fact_key")
            or metadata.get("semantic_key")
            or observation.observation_key
            or ""
        ).strip()
        if not predicate or not object_text or not canonical_text or not relation_key:
            return None

        return MemoryRelationData(
            owner_id=str(snapshot.user_id),
            relation_key=relation_key,
            predicate=predicate,
            object_text=object_text,
            canonical_text=canonical_text,
            confidence=float(observation.confidence),
            importance=float(observation.importance),
            status="active",
            payload={
                "semantic_key": str(metadata.get("semantic_key") or "") or None,
                "identity_signature": str(metadata.get("identity_signature") or "") or None,
                "canonical_statement": canonical_text,
                "predicate": predicate,
                "object": object_text,
                "event_time": str(metadata.get("event_time") or "") or None,
                "persons": list(metadata.get("persons") or []),
                "entities": list(metadata.get("entities") or []),
                "location": str(metadata.get("location") or "") or None,
                "topic": str(metadata.get("topic") or "") or None,
            },
            event_time=str(metadata.get("event_time") or "") or None,
            location=str(metadata.get("location") or "") or None,
            source_entry_id=source_entry_id,
            source_session_ledger_id=source_session_ledger_id,
        )

    @staticmethod
    def _build_relation_from_entry_row(
        row: UserMemoryEntry,
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[MemoryRelationData]:
        relation_payload = dict(payload or row.entry_data or {})
        if str(relation_payload.get("fact_kind") or row.fact_kind or "").strip() != "relationship":
            return None

        predicate = str(relation_payload.get("predicate") or row.predicate or "").strip()
        object_text = str(relation_payload.get("object") or row.object_text or "").strip()
        canonical_text = str(
            relation_payload.get("canonical_statement") or row.summary or row.canonical_text or ""
        ).strip()
        relation_key = str(
            relation_payload.get("key")
            or row.entry_key
            or relation_payload.get("semantic_key")
            or ""
        ).strip()
        if not predicate or not object_text or not canonical_text or not relation_key:
            return None

        return MemoryRelationData(
            owner_id=str(row.user_id),
            relation_key=relation_key,
            predicate=predicate,
            object_text=object_text,
            canonical_text=canonical_text,
            confidence=float(row.confidence or 0.7),
            importance=float(row.importance or 0.5),
            status=str(row.status or "active"),
            payload={
                "semantic_key": str(relation_payload.get("semantic_key") or "") or None,
                "identity_signature": str(relation_payload.get("identity_signature") or "") or None,
                "canonical_statement": canonical_text,
                "predicate": predicate,
                "object": object_text,
                "event_time": str(relation_payload.get("event_time") or row.event_time or "")
                or None,
                "persons": list(relation_payload.get("persons") or row.persons or []),
                "entities": list(relation_payload.get("entities") or row.entities or []),
                "location": str(relation_payload.get("location") or row.location or "") or None,
                "topic": str(relation_payload.get("topic") or row.topic or "") or None,
            },
            event_time=str(relation_payload.get("event_time") or row.event_time or "") or None,
            location=str(relation_payload.get("location") or row.location or "") or None,
            source_entry_id=int(row.id) if row.id is not None else None,
            source_session_ledger_id=(
                int(row.source_session_ledger_id)
                if row.source_session_ledger_id is not None
                else None
            ),
        )

    @staticmethod
    def _get_session_row(db, *, session_id: str) -> Optional[SessionLedger]:
        return (
            db.query(SessionLedger)
            .filter(SessionLedger.session_id == str(session_id))
            .one_or_none()
        )

    @staticmethod
    def _get_user_view_row(
        db,
        *,
        user_id: str,
        view_type: str,
        view_key: str,
    ) -> Optional[UserMemoryView]:
        return (
            db.query(UserMemoryView)
            .filter(
                UserMemoryView.user_id == str(user_id),
                UserMemoryView.view_type == str(view_type),
                UserMemoryView.view_key == str(view_key),
            )
            .one_or_none()
        )

    @classmethod
    def _find_user_view_row(
        cls,
        db,
        *,
        projection: MemoryProjectionData,
        payload: Dict[str, Any],
        view_key: str,
    ) -> Optional[UserMemoryView]:
        existing = cls._get_user_view_row(
            db,
            user_id=str(projection.owner_id),
            view_type=str(projection.projection_type),
            view_key=str(view_key),
        )
        if existing is not None:
            return existing

        identity_signature = str(payload.get("identity_signature") or "").strip()
        view_type = str(projection.projection_type or "").strip()
        if identity_signature:
            existing = (
                db.query(UserMemoryView)
                .filter(
                    UserMemoryView.user_id == str(projection.owner_id),
                    UserMemoryView.view_type == view_type,
                    UserMemoryView.view_data["identity_signature"].astext == identity_signature,
                )
                .order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
                .first()
            )
            if existing is not None:
                return existing
        return None

    @staticmethod
    def _get_skill_candidate_row(
        db,
        *,
        agent_id: str,
        cluster_key: str,
    ) -> Optional[SkillCandidate]:
        return (
            db.query(SkillCandidate)
            .filter(
                SkillCandidate.agent_id == str(agent_id),
                SkillCandidate.cluster_key == str(cluster_key),
            )
            .one_or_none()
        )

    @staticmethod
    def _get_entry_row(
        db,
        *,
        user_id: str,
        entry_key: str,
    ) -> Optional[UserMemoryEntry]:
        return (
            db.query(UserMemoryEntry)
            .filter(
                UserMemoryEntry.user_id == str(user_id),
                UserMemoryEntry.entry_key == str(entry_key),
            )
            .one_or_none()
        )

    @classmethod
    def _find_entry_row(
        cls,
        db,
        *,
        entry: MemoryEntryData,
        payload: Dict[str, Any],
    ) -> Optional[UserMemoryEntry]:
        entry_key = str(entry.entry_key or payload.get("key") or "").strip()
        existing = cls._get_entry_row(
            db,
            user_id=str(entry.owner_id),
            entry_key=entry_key,
        )
        if existing is not None:
            return existing

        identity_signature = str(payload.get("identity_signature") or "").strip()
        if identity_signature:
            existing = (
                db.query(UserMemoryEntry)
                .filter(
                    UserMemoryEntry.user_id == str(entry.owner_id),
                    UserMemoryEntry.entry_data["identity_signature"].astext == identity_signature,
                )
                .order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
                .first()
            )
            if existing is not None:
                return existing
        return None

    @staticmethod
    def _get_link_row(
        db,
        *,
        user_id: str,
        source_entry_id: int,
        target_entry_id: int,
        link_type: str,
    ) -> Optional[UserMemoryLink]:
        return (
            db.query(UserMemoryLink)
            .filter(
                UserMemoryLink.user_id == str(user_id),
                UserMemoryLink.source_entry_id == int(source_entry_id),
                UserMemoryLink.target_entry_id == int(target_entry_id),
                UserMemoryLink.link_type == str(link_type),
            )
            .one_or_none()
        )

    @staticmethod
    def _get_relation_row(
        db,
        *,
        user_id: str,
        relation_key: str,
    ) -> Optional[UserMemoryRelation]:
        return (
            db.query(UserMemoryRelation)
            .filter(
                UserMemoryRelation.user_id == str(user_id),
                UserMemoryRelation.relation_key == str(relation_key),
            )
            .one_or_none()
        )

    @classmethod
    def _find_relation_row(
        cls,
        db,
        *,
        relation: MemoryRelationData,
        payload: Dict[str, Any],
    ) -> Optional[UserMemoryRelation]:
        relation_key = str(relation.relation_key or payload.get("key") or "").strip()
        existing = cls._get_relation_row(
            db,
            user_id=str(relation.owner_id),
            relation_key=relation_key,
        )
        if existing is not None:
            return existing

        identity_signature = str(payload.get("identity_signature") or "").strip()
        if identity_signature:
            existing = (
                db.query(UserMemoryRelation)
                .filter(
                    UserMemoryRelation.user_id == str(relation.owner_id),
                    UserMemoryRelation.relation_data["identity_signature"].astext
                    == identity_signature,
                )
                .order_by(UserMemoryRelation.updated_at.desc(), UserMemoryRelation.id.desc())
                .first()
            )
            if existing is not None:
                return existing
        return None

    def _upsert_entry_row(
        self,
        db,
        *,
        entry: MemoryEntryData,
        source_session_ledger_id: Optional[int] = None,
        collection_name: str,
        embedding_signature: str,
    ) -> UserMemoryEntry:
        identity, payload, _canonical_statement, _value = self.resolve_entry_identity(entry=entry)
        entry.entry_key = identity.fact_key
        entry.payload = payload
        existing = self._find_entry_row(db, entry=entry, payload=payload)
        if existing is None:
            existing = UserMemoryEntry()
            db.add(existing)
        self._apply_entry_fields(
            existing,
            entry=entry,
            payload=payload,
            source_session_ledger_id=source_session_ledger_id,
            collection_name=collection_name,
        )
        db.flush()
        self._enqueue_vector_job(
            db,
            row=existing,
            source_kind="entry",
            collection_name=collection_name,
            embedding_signature=embedding_signature,
        )
        return existing

    def _upsert_relation_row(
        self,
        db,
        *,
        relation: MemoryRelationData,
    ) -> UserMemoryRelation:
        identity, payload = self.resolve_relation_identity(relation=relation)
        relation.relation_key = identity.fact_key
        relation.payload = payload
        existing = self._find_relation_row(db, relation=relation, payload=payload)
        if existing is None:
            existing = UserMemoryRelation()
            db.add(existing)
        self._apply_relation_fields(existing, relation=relation)
        db.flush()
        return existing

    @staticmethod
    def _delete_relation_row(
        db,
        *,
        user_id: str,
        relation_key: Optional[str] = None,
        source_entry_id: Optional[int] = None,
    ) -> None:
        filters = []
        if relation_key:
            filters.append(UserMemoryRelation.relation_key == str(relation_key))
        if source_entry_id is not None:
            filters.append(UserMemoryRelation.source_entry_id == int(source_entry_id))
        if not filters:
            return
        (
            db.query(UserMemoryRelation)
            .filter(UserMemoryRelation.user_id == str(user_id))
            .filter(or_(*filters))
            .delete(synchronize_session=False)
        )

    def _upsert_user_view_row(
        self,
        db,
        *,
        projection: MemoryProjectionData,
        collection_name: str,
        embedding_signature: str,
    ) -> UserMemoryView:
        _identity, payload, view_key = self.resolve_view_identity(projection=projection)
        projection.projection_key = view_key
        projection.payload = payload
        existing = self._find_user_view_row(
            db,
            projection=projection,
            payload=payload,
            view_key=view_key,
        )
        if existing is None:
            existing = UserMemoryView()
            db.add(existing)
        self._apply_view_fields(
            existing,
            projection=projection,
            payload=payload,
            collection_name=collection_name,
        )
        db.flush()
        self._enqueue_vector_job(
            db,
            row=existing,
            source_kind="view",
            collection_name=collection_name,
            embedding_signature=embedding_signature,
        )
        return existing

    def _upsert_skill_candidate_row(
        self,
        db,
        *,
        snapshot: SessionLedgerSnapshot,
        candidate: MemoryProjectionData,
        session_ledger_id: Optional[int],
    ) -> SkillCandidate:
        existing = self._get_skill_candidate_row(
            db,
            agent_id=str(candidate.owner_id),
            cluster_key=str(candidate.projection_key),
        )
        if existing is None:
            existing = SkillCandidate()
            db.add(existing)
        self._apply_skill_candidate_fields(
            existing,
            snapshot=snapshot,
            candidate=candidate,
            payload=dict(candidate.payload or {}),
            session_ledger_id=session_ledger_id,
        )
        db.flush()
        return existing

    def _create_link_row(self, db, *, link: MemoryLinkData, user_id: str) -> UserMemoryLink:
        if str(link.source_kind) != "entry" or str(link.target_kind) != "entry":
            raise ValueError("user_memory_links only support entry-to-entry links")
        existing = self._get_link_row(
            db,
            user_id=user_id,
            source_entry_id=int(link.source_id),
            target_entry_id=int(link.target_id),
            link_type=str(link.link_type),
        )
        if existing is not None:
            existing.link_data = dict(link.payload or {})
            db.flush()
            return existing
        row = UserMemoryLink(
            user_id=str(user_id),
            source_entry_id=int(link.source_id),
            target_entry_id=int(link.target_id),
            link_type=str(link.link_type),
            link_data=dict(link.payload or {}),
        )
        db.add(row)
        db.flush()
        return row

    def record_session_snapshot(
        self,
        *,
        snapshot: SessionLedgerSnapshot,
        events: List[SessionLedgerEventData],
        observations: List[MemoryObservationData],
        projections: List[MemoryProjectionData],
    ) -> int:
        """Upsert one session snapshot and its derived final memory products."""

        with get_db_session() as db:
            collection_name, embedding_signature = self._current_vector_target()
            session_row = self._get_session_row(db, session_id=str(snapshot.session_id))
            if session_row is None:
                session_row = SessionLedger(
                    session_id=str(snapshot.session_id),
                    agent_id=str(snapshot.agent_id),
                    user_id=str(snapshot.user_id),
                    started_at=snapshot.started_at,
                    ended_at=snapshot.ended_at,
                    status=str(snapshot.status or "completed"),
                    end_reason=str(snapshot.end_reason or "") or None,
                    ledger_metadata=dict(snapshot.metadata or {}),
                )
                db.add(session_row)
                db.flush()
            else:
                session_row.agent_id = str(snapshot.agent_id)
                session_row.user_id = str(snapshot.user_id)
                session_row.started_at = snapshot.started_at
                session_row.ended_at = snapshot.ended_at
                session_row.status = str(snapshot.status or "completed")
                session_row.end_reason = str(snapshot.end_reason or "") or None
                session_row.ledger_metadata = dict(snapshot.metadata or {})
                db.flush()

            db.query(SessionLedgerEvent).filter(
                SessionLedgerEvent.session_ledger_id == session_row.id
            ).delete(synchronize_session=False)
            db.flush()

            for event in events:
                db.add(
                    SessionLedgerEvent(
                        session_ledger_id=session_row.id,
                        event_index=int(event.event_index),
                        event_kind=str(event.event_kind),
                        role=str(event.role) if event.role else None,
                        content=str(event.content),
                        event_timestamp=event.event_timestamp,
                        payload=dict(event.payload or {}),
                    )
                )
            db.flush()

            for observation in observations:
                entry = self._build_entry_from_observation(
                    snapshot=snapshot, observation=observation
                )
                if entry is None:
                    continue
                entry_row = self._upsert_entry_row(
                    db,
                    entry=entry,
                    source_session_ledger_id=int(session_row.id),
                    collection_name=collection_name,
                    embedding_signature=embedding_signature,
                )
                relation = self._build_relation_from_observation(
                    snapshot=snapshot,
                    observation=observation,
                    source_entry_id=int(entry_row.id),
                    source_session_ledger_id=int(session_row.id),
                )
                if relation is not None:
                    self._upsert_relation_row(db, relation=relation)
                else:
                    self._delete_relation_row(
                        db,
                        user_id=str(entry_row.user_id),
                        source_entry_id=int(entry_row.id),
                    )

            for projection in projections:
                projection_type = str(projection.projection_type or "").strip().lower()
                if projection_type in {"user_profile", "episode"}:
                    self._upsert_user_view_row(
                        db,
                        projection=projection,
                        collection_name=collection_name,
                        embedding_signature=embedding_signature,
                    )
                    continue
                if projection_type == "skill_candidate":
                    self._upsert_skill_candidate_row(
                        db,
                        snapshot=snapshot,
                        candidate=projection,
                        session_ledger_id=int(session_row.id),
                    )

            db.flush()
            return int(session_row.id)

    def upsert_projection(
        self,
        *,
        projection: MemoryProjectionData,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> int:
        """Upsert a user-memory view or skill candidate by stable identity."""

        del source_observation_id
        snapshot = SessionLedgerSnapshot(
            session_id="manual-upsert",
            agent_id=str(projection.owner_id if projection.owner_type == "agent" else ""),
            user_id=str(projection.payload.get("user_id") or projection.owner_id),
            started_at=utcnow(),
            ended_at=None,
            status="completed",
        )
        with get_db_session() as db:
            collection_name, embedding_signature = self._current_vector_target()
            projection_type = str(projection.projection_type or "").strip().lower()
            if projection_type in {"user_profile", "episode"}:
                row = self._upsert_user_view_row(
                    db,
                    projection=projection,
                    collection_name=collection_name,
                    embedding_signature=embedding_signature,
                )
                return int(row.id)
            if projection_type == "skill_candidate":
                row = self._upsert_skill_candidate_row(
                    db,
                    snapshot=snapshot,
                    candidate=projection,
                    session_ledger_id=source_session_id,
                )
                return int(row.id)
            raise ValueError(f"Unsupported projection type: {projection_type}")

    def upsert_entry(
        self,
        *,
        entry: MemoryEntryData,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> int:
        """Upsert one user-memory entry."""

        del source_observation_id
        if str(entry.owner_type or "") != "user" or str(entry.entry_type or "") != "user_fact":
            raise ValueError("Only user_fact entries are supported in reset-era persistence")
        with get_db_session() as db:
            collection_name, embedding_signature = self._current_vector_target()
            row = self._upsert_entry_row(
                db,
                entry=entry,
                source_session_ledger_id=source_session_id,
                collection_name=collection_name,
                embedding_signature=embedding_signature,
            )
            relation = self._build_relation_from_entry_row(row, payload=dict(entry.payload or {}))
            if relation is not None:
                self._upsert_relation_row(db, relation=relation)
            else:
                self._delete_relation_row(db, user_id=str(row.user_id), source_entry_id=int(row.id))
            return int(row.id)

    def create_link(self, *, link: MemoryLinkData, user_id: Optional[str] = None) -> int:
        """Create or update one user-memory link."""

        if not user_id:
            raise ValueError("user_id is required for user_memory_links")
        with get_db_session() as db:
            row = self._create_link_row(db, link=link, user_id=str(user_id))
            return int(row.id)

    def get_projection(
        self,
        *,
        owner_type: str,
        owner_id: str,
        projection_type: str,
        projection_key: str,
    ) -> Optional[Any]:
        """Load one user-memory view or skill candidate by stable identity."""

        with get_db_session() as db:
            projection_type = str(projection_type or "").strip().lower()
            if str(owner_type) == "user":
                return self._get_user_view_row(
                    db,
                    user_id=str(owner_id),
                    view_type=projection_type,
                    view_key=str(projection_key),
                )
            if str(owner_type) == "agent" and projection_type == "skill_candidate":
                return self._get_skill_candidate_row(
                    db,
                    agent_id=str(owner_id),
                    cluster_key=str(projection_key),
                )
            return None

    def get_projection_by_id(self, projection_id: int) -> Optional[Any]:
        """Load one user-memory view or skill candidate by numeric id."""

        with get_db_session() as db:
            collection_name, embedding_signature = self._current_vector_target()
            row = (
                db.query(UserMemoryView)
                .filter(UserMemoryView.id == int(projection_id))
                .one_or_none()
            )
            if row is not None:
                return row
            return (
                db.query(SkillCandidate).filter(SkillCandidate.id == int(projection_id)).one_or_none()
            )

    def get_entry(
        self,
        *,
        owner_type: str,
        owner_id: str,
        entry_type: str,
        entry_key: str,
    ) -> Optional[UserMemoryEntry]:
        """Load one user-memory entry by stable identity."""

        if str(owner_type) != "user" or str(entry_type) != "user_fact":
            return None
        with get_db_session() as db:
            return self._get_entry_row(db, user_id=str(owner_id), entry_key=str(entry_key))

    def get_entry_by_id(self, entry_id: int) -> Optional[UserMemoryEntry]:
        """Load one entry row by numeric id."""

        with get_db_session() as db:
            return (
                db.query(UserMemoryEntry).filter(UserMemoryEntry.id == int(entry_id)).one_or_none()
            )

    def update_projection(
        self,
        projection_id: int,
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        details: Optional[str] = None,
        status: Optional[str] = None,
        projection_key: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> Optional[Any]:
        """Update a user-memory view or skill candidate."""

        del source_observation_id
        with get_db_session() as db:
            collection_name, embedding_signature = self._current_vector_target()
            row = (
                db.query(UserMemoryView)
                .filter(UserMemoryView.id == int(projection_id))
                .one_or_none()
            )
            if row is not None:
                if projection_key is not None:
                    row.view_key = str(projection_key)
                if title is not None:
                    row.title = str(title)
                if summary is not None:
                    row.content = str(summary) if summary else ""
                if details is not None:
                    row.details = details
                if status is not None:
                    row.status = str(status)
                if payload is not None:
                    row.view_data = dict(payload)
                self._mark_row_vector_pending(row, collection_name=collection_name)
                db.flush()
                self._enqueue_vector_job(
                    db,
                    row=row,
                    source_kind="view",
                    collection_name=collection_name,
                    embedding_signature=embedding_signature,
                )
                return row

            candidate = (
                db.query(SkillCandidate).filter(SkillCandidate.id == int(projection_id)).one_or_none()
            )
            if candidate is None:
                return None
            if title is not None:
                candidate.title = str(title)
                candidate.goal = str(title)
            if summary is not None:
                candidate.why_it_worked = str(summary) if summary else None
            if details is not None:
                candidate.details = details
            if status is not None:
                candidate.status = status
            if payload is not None:
                candidate.candidate_payload = dict(payload)
            if source_session_id is not None:
                candidate.evidence_session_ledger_id = source_session_id
            db.flush()
            return candidate

    def update_entry(
        self,
        entry_id: int,
        *,
        entry_key: Optional[str] = None,
        canonical_text: Optional[str] = None,
        summary: Optional[str] = None,
        details: Optional[str] = None,
        confidence: Optional[float] = None,
        importance: Optional[float] = None,
        status: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> Optional[UserMemoryEntry]:
        """Update selected user-memory entry fields."""

        del source_observation_id
        with get_db_session() as db:
            collection_name, embedding_signature = self._current_vector_target()
            row = (
                db.query(UserMemoryEntry).filter(UserMemoryEntry.id == int(entry_id)).one_or_none()
            )
            if row is None:
                return None
            if entry_key is not None:
                row.entry_key = str(entry_key)
            if canonical_text is not None:
                row.canonical_text = str(canonical_text)
            if summary is not None:
                row.summary = str(summary) if summary else None
            if details is not None:
                row.details = details
            if confidence is not None:
                row.confidence = float(confidence)
            if importance is not None:
                row.importance = float(importance)
            if status is not None:
                row.status = str(status)
            if payload is not None:
                row.entry_data = dict(payload)
                row.fact_kind = str(payload.get("fact_kind") or row.fact_kind or "preference")
                row.predicate = str(payload.get("predicate") or "") or None
                row.object_text = str(payload.get("object") or "") or None
                row.event_time = str(payload.get("event_time") or "") or None
                row.event_time_start, row.event_time_end = parse_event_time_range(row.event_time)
                row.location = str(payload.get("location") or "") or None
                row.persons = list(payload.get("persons") or [])
                row.entities = list(payload.get("entities") or [])
                row.topic = str(payload.get("topic") or "") or None
            if source_session_id is not None:
                row.source_session_ledger_id = source_session_id
            self._mark_row_vector_pending(row, collection_name=collection_name)
            db.flush()
            relation = self._build_relation_from_entry_row(
                row, payload=dict(payload or row.entry_data or {})
            )
            if relation is not None:
                self._upsert_relation_row(db, relation=relation)
            else:
                self._delete_relation_row(db, user_id=str(row.user_id), source_entry_id=int(row.id))
            self._enqueue_vector_job(
                db,
                row=row,
                source_kind="entry",
                collection_name=collection_name,
                embedding_signature=embedding_signature,
            )
            return row

    def update_relation(
        self,
        relation_id: int,
        *,
        relation_key: Optional[str] = None,
        predicate: Optional[str] = None,
        canonical_text: Optional[str] = None,
        confidence: Optional[float] = None,
        importance: Optional[float] = None,
        status: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        source_entry_id: Optional[int] = None,
        source_session_id: Optional[int] = None,
    ) -> Optional[UserMemoryRelation]:
        """Update selected user-memory relation fields."""

        with get_db_session() as db:
            row = (
                db.query(UserMemoryRelation)
                .filter(UserMemoryRelation.id == int(relation_id))
                .one_or_none()
            )
            if row is None:
                return None
            if relation_key is not None:
                row.relation_key = str(relation_key)
            if predicate is not None:
                row.predicate = str(predicate)
            if canonical_text is not None:
                row.canonical_text = str(canonical_text)
            if confidence is not None:
                row.confidence = float(confidence)
            if importance is not None:
                row.importance = float(importance)
            if status is not None:
                row.status = str(status)
            if payload is not None:
                row.relation_data = dict(payload)
                row.predicate = str(payload.get("predicate") or row.predicate or "")
                row.object_text = str(payload.get("object") or row.object_text or "")
                row.canonical_text = str(
                    payload.get("canonical_statement") or row.canonical_text or ""
                )
                row.event_time = str(payload.get("event_time") or "") or None
                row.event_time_start, row.event_time_end = parse_event_time_range(row.event_time)
                row.location = str(payload.get("location") or "") or None
                row.persons = list(payload.get("persons") or [])
                row.entities = list(payload.get("entities") or [])
            if source_entry_id is not None:
                row.source_entry_id = int(source_entry_id)
            if source_session_id is not None:
                row.source_session_ledger_id = int(source_session_id)
            db.flush()
            return row

    def list_projections(
        self,
        *,
        owner_type: Optional[str] = None,
        owner_id: Optional[str] = None,
        projection_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: Optional[int] = 100,
    ) -> List[Any]:
        """List user-memory views or skill candidates ordered by recency."""

        safe_limit = max(int(limit), 1) if limit is not None else None
        with get_db_session() as db:
            normalized_owner_type = str(owner_type or "").strip().lower()
            normalized_type = str(projection_type or "").strip().lower()
            if normalized_owner_type == "agent" or normalized_type == "skill_candidate":
                query = db.query(SkillCandidate)
                if owner_id:
                    query = query.filter(SkillCandidate.agent_id == str(owner_id))
                if status:
                    review_status = self._normalize_review_status(status, {})
                    if str(status).lower() in {"pending_review", "active", "rejected"}:
                        review_status = self._normalize_review_status(status, {})
                    if str(status).lower() == "superseded":
                        return []
                    query = query.filter(SkillCandidate.review_status == review_status)
                query = query.order_by(SkillCandidate.updated_at.desc(), SkillCandidate.id.desc())
                if safe_limit is not None:
                    query = query.limit(safe_limit)
                return list(query.all())

            query = db.query(UserMemoryView)
            if owner_id:
                query = query.filter(UserMemoryView.user_id == str(owner_id))
            if projection_type:
                query = query.filter(UserMemoryView.view_type == str(projection_type))
            if status:
                query = query.filter(UserMemoryView.status == str(status))
            query = query.order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
            if safe_limit is not None:
                query = query.limit(safe_limit)
            return list(query.all())

    def list_entries(
        self,
        *,
        owner_type: Optional[str] = None,
        owner_id: Optional[str] = None,
        entry_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: Optional[int] = 100,
    ) -> List[UserMemoryEntry]:
        """List user-memory atomic entries ordered by recency."""

        if owner_type and str(owner_type) != "user":
            return []
        if entry_type and str(entry_type) != "user_fact":
            return []
        with get_db_session() as db:
            query = db.query(UserMemoryEntry)
            if owner_id:
                query = query.filter(UserMemoryEntry.user_id == str(owner_id))
            if status:
                query = query.filter(UserMemoryEntry.status == str(status))
            query = query.order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
            if limit is not None:
                query = query.limit(max(int(limit), 1))
            return list(query.all())

    def list_relations(
        self,
        *,
        owner_id: Optional[str] = None,
        predicate: Optional[str] = None,
        status: Optional[str] = "active",
        limit: Optional[int] = 100,
    ) -> List[UserMemoryRelation]:
        """List typed user-memory relations ordered by recency."""

        with get_db_session() as db:
            query = db.query(UserMemoryRelation)
            if owner_id:
                query = query.filter(UserMemoryRelation.user_id == str(owner_id))
            if predicate:
                query = query.filter(UserMemoryRelation.predicate == str(predicate))
            if status:
                query = query.filter(UserMemoryRelation.status == str(status))
            query = query.order_by(
                UserMemoryRelation.updated_at.desc(), UserMemoryRelation.id.desc()
            )
            if limit is not None:
                query = query.limit(max(int(limit), 1))
            return list(query.all())

    def list_skill_candidates(
        self,
        *,
        agent_id: Optional[str] = None,
        review_status: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[SkillCandidate]:
        """List skill candidates ordered by recency."""

        with get_db_session() as db:
            query = db.query(SkillCandidate)
            if agent_id:
                query = query.filter(SkillCandidate.agent_id == str(agent_id))
            if review_status and review_status != "all":
                query = query.filter(SkillCandidate.review_status == str(review_status))
            query = query.order_by(SkillCandidate.updated_at.desc(), SkillCandidate.id.desc())
            if limit is not None:
                query = query.limit(max(int(limit), 1))
            return list(query.all())

    def get_skill_candidate(self, candidate_id: int) -> Optional[SkillCandidate]:
        with get_db_session() as db:
            return (
                db.query(SkillCandidate).filter(SkillCandidate.id == int(candidate_id)).one_or_none()
            )

    def get_skill_candidate_by_key(
        self, *, agent_id: str, cluster_key: str
    ) -> Optional[SkillCandidate]:
        with get_db_session() as db:
            return self._get_skill_candidate_row(
                db,
                agent_id=str(agent_id),
                cluster_key=str(cluster_key),
            )

    def cleanup_sessions_ended_before(
        self,
        *,
        cutoff: datetime,
        limit: int = 1000,
        dry_run: bool = False,
    ) -> Dict[str, int]:
        """Delete expired session-ledger rows while preserving durable products."""

        safe_limit = max(int(limit or 0), 1)
        with get_db_session() as db:
            session_rows = (
                db.query(SessionLedger)
                .filter(
                    or_(
                        and_(
                            SessionLedger.ended_at.isnot(None),
                            SessionLedger.ended_at < cutoff,
                        ),
                        and_(
                            SessionLedger.ended_at.is_(None),
                            SessionLedger.started_at < cutoff,
                        ),
                    )
                )
                .order_by(
                    SessionLedger.ended_at.asc().nullsfirst(),
                    SessionLedger.started_at.asc(),
                    SessionLedger.id.asc(),
                )
                .limit(safe_limit)
                .all()
            )
            session_ids = [int(row.id) for row in session_rows if row.id is not None]
            if not session_ids:
                return {
                    "scanned_sessions": 0,
                    "deleted_sessions": 0,
                    "deleted_events": 0,
                    "detached_entries": 0,
                    "detached_relations": 0,
                    "detached_skill_candidates": 0,
                }

            deleted_events = (
                db.query(SessionLedgerEvent)
                .filter(SessionLedgerEvent.session_ledger_id.in_(session_ids))
                .count()
            )
            detached_entries = (
                db.query(UserMemoryEntry)
                .filter(UserMemoryEntry.source_session_ledger_id.in_(session_ids))
                .count()
            )
            detached_relations = (
                db.query(UserMemoryRelation)
                .filter(UserMemoryRelation.source_session_ledger_id.in_(session_ids))
                .count()
            )
            detached_skill_candidates = (
                db.query(SkillCandidate)
                .filter(SkillCandidate.evidence_session_ledger_id.in_(session_ids))
                .count()
            )
            if not dry_run:
                (
                    db.query(UserMemoryEntry)
                    .filter(UserMemoryEntry.source_session_ledger_id.in_(session_ids))
                    .update(
                        {UserMemoryEntry.source_session_ledger_id: None}, synchronize_session=False
                    )
                )
                (
                    db.query(UserMemoryRelation)
                    .filter(UserMemoryRelation.source_session_ledger_id.in_(session_ids))
                    .update(
                        {UserMemoryRelation.source_session_ledger_id: None},
                        synchronize_session=False,
                    )
                )
                (
                    db.query(SkillCandidate)
                    .filter(SkillCandidate.evidence_session_ledger_id.in_(session_ids))
                    .update(
                        {SkillCandidate.evidence_session_ledger_id: None},
                        synchronize_session=False,
                    )
                )
                (
                    db.query(SessionLedger)
                    .filter(SessionLedger.id.in_(session_ids))
                    .delete(synchronize_session=False)
                )
                db.flush()

            return {
                "scanned_sessions": len(session_ids),
                "deleted_sessions": 0 if dry_run else len(session_ids),
                "deleted_events": deleted_events,
                "detached_entries": detached_entries,
                "detached_relations": detached_relations,
                "detached_skill_candidates": detached_skill_candidates,
            }


_session_ledger_repository: Optional[SessionLedgerRepository] = None


def get_session_ledger_repository() -> SessionLedgerRepository:
    """Return a process-wide singleton repository instance."""

    global _session_ledger_repository
    if _session_ledger_repository is None:
        _session_ledger_repository = SessionLedgerRepository()
    return _session_ledger_repository
