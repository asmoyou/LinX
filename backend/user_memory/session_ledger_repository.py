"""Persistence layer for session ledgers, user memory, and learned skill proposals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, or_

from database.connection import get_db_session
from database.models import (
    SessionLedger,
    SessionLedgerEvent,
    SkillProposal,
    UserMemoryEmbeddingJob,
    UserMemoryEntry,
    UserMemoryLink,
    UserMemoryRelation,
    UserMemoryView,
)
from shared.datetime_utils import utcnow
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
    """In-memory projection rows routed into user views or skill proposals."""

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
    def _apply_skill_proposal_fields(
        row: SkillProposal,
        *,
        snapshot: SessionLedgerSnapshot,
        proposal: MemoryProjectionData,
        payload: Dict[str, Any],
        session_ledger_id: Optional[int] = None,
    ) -> None:
        steps = [
            str(step).strip() for step in payload.get("successful_path") or [] if str(step).strip()
        ]
        row.agent_id = str(proposal.owner_id)
        row.user_id = str(snapshot.user_id)
        row.proposal_key = str(proposal.projection_key)
        row.title = str(proposal.title)
        row.goal = str(payload.get("goal") or proposal.title)
        row.successful_path = steps
        row.why_it_worked = str(payload.get("why_it_worked") or proposal.summary or "") or None
        row.applicability = str(payload.get("applicability") or "") or None
        row.avoid = str(payload.get("avoid") or "") or None
        row.confidence = float(payload.get("confidence") or 0.72)
        row.review_status = SessionLedgerRepository._normalize_review_status(
            proposal.status,
            payload,
        )
        row.review_note = str(payload.get("review_note") or "") or None
        row.evidence_session_ledger_id = session_ledger_id
        merged_payload = dict(payload)
        if proposal.details:
            merged_payload.setdefault("review_content", str(proposal.details))
        row.proposal_payload = merged_payload

    @staticmethod
    def _apply_entry_fields(
        row: UserMemoryEntry,
        *,
        entry: MemoryEntryData,
        payload: Dict[str, Any],
        source_session_ledger_id: Optional[int] = None,
        collection_name: Optional[str] = None,
    ) -> None:
        row.user_id = str(entry.owner_id)
        row.entry_key = str(entry.entry_key)
        row.fact_kind = str(payload.get("fact_kind") or "preference")
        row.canonical_text = str(entry.canonical_text)
        row.summary = str(entry.summary) if entry.summary else None
        row.predicate = str(payload.get("predicate") or "") or None
        row.object_text = str(payload.get("object") or "") or None
        row.event_time = str(payload.get("event_time") or "") or None
        row.location = str(payload.get("location") or "") or None
        row.persons = list(payload.get("persons") or [])
        row.entities = list(payload.get("entities") or [])
        row.topic = str(payload.get("topic") or "") or None
        row.confidence = float(entry.confidence)
        row.importance = float(entry.importance)
        row.status = str(entry.status or "active")
        row.source_session_ledger_id = source_session_ledger_id
        row.source_event_indexes = list(entry.source_event_indexes or [])
        merged_payload = dict(payload)
        if entry.details:
            merged_payload["details"] = entry.details
        row.entry_data = merged_payload
        event_time_start, event_time_end = parse_event_time_range(payload.get("event_time"))
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

    @staticmethod
    def _get_skill_proposal_row(
        db,
        *,
        agent_id: str,
        proposal_key: str,
    ) -> Optional[SkillProposal]:
        return (
            db.query(SkillProposal)
            .filter(
                SkillProposal.agent_id == str(agent_id),
                SkillProposal.proposal_key == str(proposal_key),
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

    def _upsert_entry_row(
        self,
        db,
        *,
        entry: MemoryEntryData,
        source_session_ledger_id: Optional[int] = None,
        collection_name: str,
        embedding_signature: str,
    ) -> UserMemoryEntry:
        existing = self._get_entry_row(
            db,
            user_id=str(entry.owner_id),
            entry_key=str(entry.entry_key),
        )
        if existing is None:
            existing = UserMemoryEntry()
            db.add(existing)
        self._apply_entry_fields(
            existing,
            entry=entry,
            payload=dict(entry.payload or {}),
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
        existing = self._get_relation_row(
            db,
            user_id=str(relation.owner_id),
            relation_key=str(relation.relation_key),
        )
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
        relation_key: str,
    ) -> None:
        (
            db.query(UserMemoryRelation)
            .filter(
                UserMemoryRelation.user_id == str(user_id),
                UserMemoryRelation.relation_key == str(relation_key),
            )
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
        existing = self._get_user_view_row(
            db,
            user_id=str(projection.owner_id),
            view_type=str(projection.projection_type),
            view_key=str(projection.projection_key),
        )
        if existing is None:
            existing = UserMemoryView()
            db.add(existing)
        self._apply_view_fields(
            existing,
            projection=projection,
            payload=dict(projection.payload or {}),
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

    def _upsert_skill_proposal_row(
        self,
        db,
        *,
        snapshot: SessionLedgerSnapshot,
        proposal: MemoryProjectionData,
        session_ledger_id: Optional[int],
    ) -> SkillProposal:
        existing = self._get_skill_proposal_row(
            db,
            agent_id=str(proposal.owner_id),
            proposal_key=str(proposal.projection_key),
        )
        if existing is None:
            existing = SkillProposal()
            db.add(existing)
        self._apply_skill_proposal_fields(
            existing,
            snapshot=snapshot,
            proposal=proposal,
            payload=dict(proposal.payload or {}),
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
                        relation_key=str(entry_row.entry_key),
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
                if projection_type == "skill_proposal":
                    self._upsert_skill_proposal_row(
                        db,
                        snapshot=snapshot,
                        proposal=projection,
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
        """Upsert a user-memory view or skill proposal by stable identity."""

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
            if projection_type == "skill_proposal":
                row = self._upsert_skill_proposal_row(
                    db,
                    snapshot=snapshot,
                    proposal=projection,
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
                self._delete_relation_row(
                    db, user_id=str(row.user_id), relation_key=str(row.entry_key)
                )
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
        """Load one user-memory view or skill proposal by stable identity."""

        with get_db_session() as db:
            projection_type = str(projection_type or "").strip().lower()
            if str(owner_type) == "user":
                return self._get_user_view_row(
                    db,
                    user_id=str(owner_id),
                    view_type=projection_type,
                    view_key=str(projection_key),
                )
            if str(owner_type) == "agent" and projection_type == "skill_proposal":
                return self._get_skill_proposal_row(
                    db,
                    agent_id=str(owner_id),
                    proposal_key=str(projection_key),
                )
            return None

    def get_projection_by_id(self, projection_id: int) -> Optional[Any]:
        """Load one user-memory view or skill proposal by numeric id."""

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
                db.query(SkillProposal).filter(SkillProposal.id == int(projection_id)).one_or_none()
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
        payload: Optional[Dict[str, Any]] = None,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> Optional[Any]:
        """Update a user-memory view or skill proposal."""

        del source_observation_id
        with get_db_session() as db:
            collection_name, embedding_signature = self._current_vector_target()
            row = (
                db.query(UserMemoryView)
                .filter(UserMemoryView.id == int(projection_id))
                .one_or_none()
            )
            if row is not None:
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

            proposal = (
                db.query(SkillProposal).filter(SkillProposal.id == int(projection_id)).one_or_none()
            )
            if proposal is None:
                return None
            if title is not None:
                proposal.title = str(title)
                proposal.goal = str(title)
            if summary is not None:
                proposal.why_it_worked = str(summary) if summary else None
            if details is not None:
                proposal.details = details
            if status is not None:
                proposal.status = status
            if payload is not None:
                proposal.proposal_payload = dict(payload)
            if source_session_id is not None:
                proposal.evidence_session_ledger_id = source_session_id
            db.flush()
            return proposal

    def update_entry(
        self,
        entry_id: int,
        *,
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
                self._delete_relation_row(
                    db, user_id=str(row.user_id), relation_key=str(row.entry_key)
                )
            self._enqueue_vector_job(
                db,
                row=row,
                source_kind="entry",
                collection_name=collection_name,
                embedding_signature=embedding_signature,
            )
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
        """List user-memory views or skill proposals ordered by recency."""

        safe_limit = max(int(limit), 1) if limit is not None else None
        with get_db_session() as db:
            normalized_owner_type = str(owner_type or "").strip().lower()
            normalized_type = str(projection_type or "").strip().lower()
            if normalized_owner_type == "agent" or normalized_type == "skill_proposal":
                query = db.query(SkillProposal)
                if owner_id:
                    query = query.filter(SkillProposal.agent_id == str(owner_id))
                if status:
                    review_status = self._normalize_review_status(status, {})
                    if str(status).lower() in {"pending_review", "active", "rejected"}:
                        review_status = self._normalize_review_status(status, {})
                    if str(status).lower() == "superseded":
                        return []
                    query = query.filter(SkillProposal.review_status == review_status)
                query = query.order_by(SkillProposal.updated_at.desc(), SkillProposal.id.desc())
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

    def list_skill_proposals(
        self,
        *,
        agent_id: Optional[str] = None,
        review_status: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[SkillProposal]:
        """List skill proposals ordered by recency."""

        with get_db_session() as db:
            query = db.query(SkillProposal)
            if agent_id:
                query = query.filter(SkillProposal.agent_id == str(agent_id))
            if review_status and review_status != "all":
                query = query.filter(SkillProposal.review_status == str(review_status))
            query = query.order_by(SkillProposal.updated_at.desc(), SkillProposal.id.desc())
            if limit is not None:
                query = query.limit(max(int(limit), 1))
            return list(query.all())

    def get_skill_proposal(self, proposal_id: int) -> Optional[SkillProposal]:
        with get_db_session() as db:
            return (
                db.query(SkillProposal).filter(SkillProposal.id == int(proposal_id)).one_or_none()
            )

    def get_skill_proposal_by_key(
        self, *, agent_id: str, proposal_key: str
    ) -> Optional[SkillProposal]:
        with get_db_session() as db:
            return self._get_skill_proposal_row(
                db,
                agent_id=str(agent_id),
                proposal_key=str(proposal_key),
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
                    "detached_skill_proposals": 0,
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
            detached_skill_proposals = (
                db.query(SkillProposal)
                .filter(SkillProposal.evidence_session_ledger_id.in_(session_ids))
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
                    db.query(SkillProposal)
                    .filter(SkillProposal.evidence_session_ledger_id.in_(session_ids))
                    .update(
                        {SkillProposal.evidence_session_ledger_id: None}, synchronize_session=False
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
                "detached_skill_proposals": detached_skill_proposals,
            }


_session_ledger_repository: Optional[SessionLedgerRepository] = None


def get_session_ledger_repository() -> SessionLedgerRepository:
    """Return a process-wide singleton repository instance."""

    global _session_ledger_repository
    if _session_ledger_repository is None:
        _session_ledger_repository = SessionLedgerRepository()
    return _session_ledger_repository
