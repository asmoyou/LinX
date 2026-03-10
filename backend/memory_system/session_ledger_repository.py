"""Repository for session-ledger memory migration tables."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from database.connection import get_db_session
from database.models import (
    MemoryEntry,
    MemoryLink,
    MemoryMaterialization,
    MemoryObservation,
    MemorySession,
    MemorySessionEvent,
)


@dataclass
class MemorySessionSnapshot:
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
class MemorySessionEventData:
    """Structured event row for one persisted session snapshot."""

    event_index: int
    event_kind: str
    role: Optional[str]
    content: str
    event_timestamp: Optional[datetime] = None
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryObservationData:
    """Observation derived from session turns and extraction outputs."""

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
class MemoryMaterializationData:
    """Stable projection built from one or more observations."""

    owner_type: str
    owner_id: str
    materialization_type: str
    materialization_key: str
    title: str
    summary: Optional[str] = None
    details: Optional[str] = None
    status: str = "active"
    payload: Dict[str, Any] = field(default_factory=dict)
    source_observation_key: Optional[str] = None


@dataclass
class MemoryEntryData:
    """Atomic memory entry derived from a normalized observation."""

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


@dataclass
class MemoryLinkData:
    """Lineage link between observations, entries, and materializations."""

    source_kind: str
    source_id: int
    target_kind: str
    target_id: int
    link_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    source_session_id: Optional[int] = None


class SessionLedgerRepository:
    """Persistence layer for session-ledger snapshots and projections."""

    @staticmethod
    def _apply_materialization_fields(
        row: MemoryMaterialization,
        *,
        materialization: MemoryMaterializationData,
        payload: Dict[str, Any],
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> None:
        row.owner_type = str(materialization.owner_type)
        row.owner_id = str(materialization.owner_id)
        row.materialization_type = str(materialization.materialization_type)
        row.materialization_key = str(materialization.materialization_key)
        row.title = str(materialization.title)
        row.summary = str(materialization.summary) if materialization.summary else None
        row.details = str(materialization.details) if materialization.details else None
        row.status = str(materialization.status or "active")
        row.materialized_data = payload
        if source_session_id is not None:
            row.source_session_id = source_session_id
        if source_observation_id is not None:
            row.source_observation_id = source_observation_id

    @staticmethod
    def _apply_entry_fields(
        row: MemoryEntry,
        *,
        entry: MemoryEntryData,
        payload: Dict[str, Any],
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> None:
        row.owner_type = str(entry.owner_type)
        row.owner_id = str(entry.owner_id)
        row.entry_type = str(entry.entry_type)
        row.entry_key = str(entry.entry_key)
        row.canonical_text = str(entry.canonical_text)
        row.summary = str(entry.summary) if entry.summary else None
        row.details = str(entry.details) if entry.details else None
        row.confidence = float(entry.confidence)
        row.importance = float(entry.importance)
        row.status = str(entry.status or "active")
        row.entry_data = payload
        if source_session_id is not None:
            row.source_session_id = source_session_id
        if source_observation_id is not None:
            row.source_observation_id = source_observation_id

    @staticmethod
    def _build_entry_from_observation(
        *,
        snapshot: MemorySessionSnapshot,
        observation: MemoryObservationData,
    ) -> Optional[MemoryEntryData]:
        metadata = dict(observation.metadata or {})
        observation_type = str(observation.observation_type or "").strip()

        if observation_type == "user_preference_signal":
            key = str(metadata.get("preference_key") or "").strip()
            value = str(metadata.get("preference_value") or observation.summary or "").strip()
            if not key or not value:
                return None
            return MemoryEntryData(
                owner_type="user",
                owner_id=str(snapshot.user_id),
                entry_type="user_fact",
                entry_key=key,
                canonical_text=f"user.preference.{key}={value}",
                summary=value,
                details=observation.details,
                confidence=float(observation.confidence),
                importance=float(observation.importance),
                status="active",
                payload={
                    "key": key,
                    "value": value,
                    "origin": "session_observation",
                    **metadata,
                },
            )

        if observation_type == "agent_success_path":
            steps = [str(step).strip() for step in metadata.get("steps") or [] if str(step).strip()]
            if not observation.title or not steps:
                return None
            fingerprint = str(metadata.get("fingerprint") or observation.observation_key).strip()
            lines = [f"agent.experience.goal={observation.title}"]
            lines.append(f"agent.experience.successful_path={' | '.join(steps)}")
            if observation.summary:
                lines.append(f"agent.experience.why_it_worked={observation.summary}")
            applicability = str(metadata.get("applicability") or "").strip()
            avoid = str(metadata.get("avoid") or "").strip()
            if applicability:
                lines.append(f"agent.experience.applicability={applicability}")
            if avoid:
                lines.append(f"agent.experience.avoid={avoid}")
            return MemoryEntryData(
                owner_type="agent",
                owner_id=str(snapshot.agent_id),
                entry_type="agent_skill_candidate",
                entry_key=fingerprint,
                canonical_text="\n".join(lines),
                summary=observation.summary,
                details=observation.details,
                confidence=float(observation.confidence),
                importance=float(observation.importance),
                status="pending_review",
                payload={
                    "goal": observation.title,
                    "successful_path": steps,
                    "origin": "session_observation",
                    **metadata,
                },
            )

        return None

    def record_session_snapshot(
        self,
        *,
        snapshot: MemorySessionSnapshot,
        events: List[MemorySessionEventData],
        observations: List[MemoryObservationData],
        materializations: List[MemoryMaterializationData],
    ) -> int:
        """Upsert one session snapshot and replace its derived rows."""

        with get_db_session() as db:
            session_row = (
                db.query(MemorySession)
                .filter(MemorySession.session_id == str(snapshot.session_id))
                .one_or_none()
            )

            if session_row is None:
                session_row = MemorySession(
                    session_id=str(snapshot.session_id),
                    agent_id=str(snapshot.agent_id),
                    user_id=str(snapshot.user_id),
                    started_at=snapshot.started_at,
                    ended_at=snapshot.ended_at,
                    status=str(snapshot.status or "completed"),
                    end_reason=str(snapshot.end_reason or "") or None,
                    session_metadata=dict(snapshot.metadata or {}),
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
                session_row.session_metadata = dict(snapshot.metadata or {})
                db.flush()

            db.query(MemorySessionEvent).filter(
                MemorySessionEvent.memory_session_id == session_row.id
            ).delete(synchronize_session=False)
            db.query(MemoryObservation).filter(
                MemoryObservation.memory_session_id == session_row.id
            ).delete(synchronize_session=False)
            db.query(MemoryLink).filter(MemoryLink.source_session_id == session_row.id).delete(
                synchronize_session=False
            )
            db.flush()

            for event in events:
                db.add(
                    MemorySessionEvent(
                        memory_session_id=session_row.id,
                        event_index=int(event.event_index),
                        event_kind=str(event.event_kind),
                        role=str(event.role) if event.role else None,
                        content=str(event.content),
                        event_timestamp=event.event_timestamp,
                        payload=dict(event.payload or {}),
                    )
                )
            db.flush()

            observation_rows: Dict[str, MemoryObservation] = {}
            for observation in observations:
                row = MemoryObservation(
                    memory_session_id=session_row.id,
                    observation_key=str(observation.observation_key),
                    observation_type=str(observation.observation_type),
                    title=str(observation.title),
                    summary=str(observation.summary) if observation.summary else None,
                    details=str(observation.details) if observation.details else None,
                    source_event_indexes=list(observation.source_event_indexes or []),
                    confidence=float(observation.confidence),
                    importance=float(observation.importance),
                    observation_metadata=dict(observation.metadata or {}),
                )
                db.add(row)
                db.flush()
                observation_rows[row.observation_key] = row

            materialization_rows_by_observation_key: Dict[str, MemoryMaterialization] = {}
            for materialization in materializations:
                existing = self._get_materialization_row(
                    db,
                    owner_type=str(materialization.owner_type),
                    owner_id=str(materialization.owner_id),
                    materialization_type=str(materialization.materialization_type),
                    materialization_key=str(materialization.materialization_key),
                )
                source_observation = (
                    observation_rows.get(str(materialization.source_observation_key or ""))
                    if materialization.source_observation_key
                    else None
                )
                payload = dict(materialization.payload or {})

                if existing is None:
                    existing = MemoryMaterialization(
                        source_session_id=session_row.id,
                        source_observation_id=source_observation.id if source_observation else None,
                    )
                    self._apply_materialization_fields(
                        existing,
                        materialization=materialization,
                        payload=payload,
                        source_session_id=session_row.id,
                        source_observation_id=source_observation.id if source_observation else None,
                    )
                    db.add(existing)
                else:
                    self._apply_materialization_fields(
                        existing,
                        materialization=materialization,
                        payload=payload,
                        source_session_id=session_row.id,
                        source_observation_id=(
                            source_observation.id
                            if source_observation
                            else existing.source_observation_id
                        ),
                    )
                db.flush()
                if materialization.source_observation_key:
                    materialization_rows_by_observation_key[
                        str(materialization.source_observation_key)
                    ] = existing

            for observation in observations:
                observation_row = observation_rows.get(str(observation.observation_key))
                if observation_row is None:
                    continue
                entry = self._build_entry_from_observation(
                    snapshot=snapshot,
                    observation=observation,
                )
                if entry is None:
                    continue
                entry_row = self._upsert_entry_row(
                    db,
                    entry=entry,
                    source_session_id=session_row.id,
                    source_observation_id=observation_row.id,
                )
                self._create_link_row(
                    db,
                    link=MemoryLinkData(
                        source_kind="observation",
                        source_id=int(observation_row.id),
                        target_kind="entry",
                        target_id=int(entry_row.id),
                        link_type="atomized_as",
                        payload={"observation_key": str(observation.observation_key)},
                        source_session_id=session_row.id,
                    ),
                )
                materialization_row = materialization_rows_by_observation_key.get(
                    str(observation.observation_key)
                )
                if materialization_row is None:
                    continue
                self._create_link_row(
                    db,
                    link=MemoryLinkData(
                        source_kind="entry",
                        source_id=int(entry_row.id),
                        target_kind="materialization",
                        target_id=int(materialization_row.id),
                        link_type="materialized_as",
                        payload={
                            "observation_key": str(observation.observation_key),
                            "materialization_key": str(materialization_row.materialization_key),
                        },
                        source_session_id=session_row.id,
                    ),
                )

            db.flush()
            return int(session_row.id)

    @staticmethod
    def _get_materialization_row(
        db,
        *,
        owner_type: str,
        owner_id: str,
        materialization_type: str,
        materialization_key: str,
    ) -> Optional[MemoryMaterialization]:
        return (
            db.query(MemoryMaterialization)
            .filter(
                MemoryMaterialization.owner_type == str(owner_type),
                MemoryMaterialization.owner_id == str(owner_id),
                MemoryMaterialization.materialization_type == str(materialization_type),
                MemoryMaterialization.materialization_key == str(materialization_key),
            )
            .one_or_none()
        )

    @staticmethod
    def _get_entry_row(
        db,
        *,
        owner_type: str,
        owner_id: str,
        entry_type: str,
        entry_key: str,
    ) -> Optional[MemoryEntry]:
        return (
            db.query(MemoryEntry)
            .filter(
                MemoryEntry.owner_type == str(owner_type),
                MemoryEntry.owner_id == str(owner_id),
                MemoryEntry.entry_type == str(entry_type),
                MemoryEntry.entry_key == str(entry_key),
            )
            .one_or_none()
        )

    def _upsert_entry_row(
        self,
        db,
        *,
        entry: MemoryEntryData,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> MemoryEntry:
        payload = dict(entry.payload or {})
        existing = self._get_entry_row(
            db,
            owner_type=str(entry.owner_type),
            owner_id=str(entry.owner_id),
            entry_type=str(entry.entry_type),
            entry_key=str(entry.entry_key),
        )
        if existing is None:
            existing = MemoryEntry()
            db.add(existing)
        self._apply_entry_fields(
            existing,
            entry=entry,
            payload=payload,
            source_session_id=source_session_id,
            source_observation_id=source_observation_id,
        )
        db.flush()
        return existing

    @staticmethod
    def _get_link_row(
        db,
        *,
        source_kind: str,
        source_id: int,
        target_kind: str,
        target_id: int,
        link_type: str,
    ) -> Optional[MemoryLink]:
        return (
            db.query(MemoryLink)
            .filter(
                MemoryLink.source_kind == str(source_kind),
                MemoryLink.source_id == int(source_id),
                MemoryLink.target_kind == str(target_kind),
                MemoryLink.target_id == int(target_id),
                MemoryLink.link_type == str(link_type),
            )
            .one_or_none()
        )

    def _create_link_row(
        self,
        db,
        *,
        link: MemoryLinkData,
    ) -> MemoryLink:
        existing = self._get_link_row(
            db,
            source_kind=link.source_kind,
            source_id=link.source_id,
            target_kind=link.target_kind,
            target_id=link.target_id,
            link_type=link.link_type,
        )
        if existing is not None:
            existing.link_data = dict(link.payload or {})
            if link.source_session_id is not None:
                existing.source_session_id = link.source_session_id
            db.flush()
            return existing

        row = MemoryLink(
            source_session_id=link.source_session_id,
            source_kind=str(link.source_kind),
            source_id=int(link.source_id),
            target_kind=str(link.target_kind),
            target_id=int(link.target_id),
            link_type=str(link.link_type),
            link_data=dict(link.payload or {}),
        )
        db.add(row)
        db.flush()
        return row

    def upsert_materialization(
        self,
        *,
        materialization: MemoryMaterializationData,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> int:
        """Upsert a single materialization outside the session snapshot write path."""

        payload = dict(materialization.payload or {})
        with get_db_session() as db:
            existing = self._get_materialization_row(
                db,
                owner_type=str(materialization.owner_type),
                owner_id=str(materialization.owner_id),
                materialization_type=str(materialization.materialization_type),
                materialization_key=str(materialization.materialization_key),
            )
            if existing is None:
                existing = MemoryMaterialization()
                db.add(existing)
            self._apply_materialization_fields(
                existing,
                materialization=materialization,
                payload=payload,
                source_session_id=source_session_id,
                source_observation_id=source_observation_id,
            )
            db.flush()
            return int(existing.id)

    def upsert_entry(
        self,
        *,
        entry: MemoryEntryData,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> int:
        """Upsert a single memory entry outside the session snapshot write path."""

        with get_db_session() as db:
            row = self._upsert_entry_row(
                db,
                entry=entry,
                source_session_id=source_session_id,
                source_observation_id=source_observation_id,
            )
            return int(row.id)

    def create_link(
        self,
        *,
        link: MemoryLinkData,
    ) -> int:
        """Create or update one lineage link."""

        with get_db_session() as db:
            row = self._create_link_row(db, link=link)
            return int(row.id)

    def get_materialization(
        self,
        *,
        owner_type: str,
        owner_id: str,
        materialization_type: str,
        materialization_key: str,
    ) -> Optional[MemoryMaterialization]:
        """Load one materialization by its stable identity."""

        with get_db_session() as db:
            return self._get_materialization_row(
                db,
                owner_type=owner_type,
                owner_id=owner_id,
                materialization_type=materialization_type,
                materialization_key=materialization_key,
            )

    def get_materialization_by_id(self, materialization_id: int) -> Optional[MemoryMaterialization]:
        """Load one materialization row by numeric id."""

        with get_db_session() as db:
            return (
                db.query(MemoryMaterialization)
                .filter(MemoryMaterialization.id == int(materialization_id))
                .one_or_none()
            )

    def get_entry(
        self,
        *,
        owner_type: str,
        owner_id: str,
        entry_type: str,
        entry_key: str,
    ) -> Optional[MemoryEntry]:
        """Load one entry by its stable identity."""

        with get_db_session() as db:
            return self._get_entry_row(
                db,
                owner_type=owner_type,
                owner_id=owner_id,
                entry_type=entry_type,
                entry_key=entry_key,
            )

    def get_entry_by_id(self, entry_id: int) -> Optional[MemoryEntry]:
        """Load one entry row by numeric id."""

        with get_db_session() as db:
            return db.query(MemoryEntry).filter(MemoryEntry.id == int(entry_id)).one_or_none()

    def update_materialization(
        self,
        materialization_id: int,
        *,
        title: Optional[str] = None,
        summary: Optional[str] = None,
        details: Optional[str] = None,
        status: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        source_session_id: Optional[int] = None,
        source_observation_id: Optional[int] = None,
    ) -> Optional[MemoryMaterialization]:
        """Update selected materialization fields and return the refreshed row."""

        with get_db_session() as db:
            row = (
                db.query(MemoryMaterialization)
                .filter(MemoryMaterialization.id == int(materialization_id))
                .one_or_none()
            )
            if row is None:
                return None
            if title is not None:
                row.title = str(title)
            if summary is not None:
                row.summary = str(summary) if summary else None
            if details is not None:
                row.details = str(details) if details else None
            if status is not None:
                row.status = str(status)
            if payload is not None:
                row.materialized_data = dict(payload)
            if source_session_id is not None:
                row.source_session_id = source_session_id
            if source_observation_id is not None:
                row.source_observation_id = source_observation_id
            db.flush()
            return row

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
    ) -> Optional[MemoryEntry]:
        """Update selected entry fields and return the refreshed row."""

        with get_db_session() as db:
            row = db.query(MemoryEntry).filter(MemoryEntry.id == int(entry_id)).one_or_none()
            if row is None:
                return None
            if canonical_text is not None:
                row.canonical_text = str(canonical_text)
            if summary is not None:
                row.summary = str(summary) if summary else None
            if details is not None:
                row.details = str(details) if details else None
            if confidence is not None:
                row.confidence = float(confidence)
            if importance is not None:
                row.importance = float(importance)
            if status is not None:
                row.status = str(status)
            if payload is not None:
                row.entry_data = dict(payload)
            if source_session_id is not None:
                row.source_session_id = source_session_id
            if source_observation_id is not None:
                row.source_observation_id = source_observation_id
            db.flush()
            return row

    def list_materializations(
        self,
        *,
        owner_type: Optional[str] = None,
        owner_id: Optional[str] = None,
        materialization_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: Optional[int] = 100,
    ) -> List[MemoryMaterialization]:
        """List materialized projections for one owner ordered by recency."""

        with get_db_session() as db:
            query = db.query(MemoryMaterialization)
            if owner_type:
                query = query.filter(MemoryMaterialization.owner_type == str(owner_type))
            if owner_id:
                query = query.filter(MemoryMaterialization.owner_id == str(owner_id))
            if materialization_type:
                query = query.filter(
                    MemoryMaterialization.materialization_type == str(materialization_type)
                )
            if status:
                query = query.filter(MemoryMaterialization.status == str(status))
            query = query.order_by(
                MemoryMaterialization.updated_at.desc(),
                MemoryMaterialization.id.desc(),
            )
            if limit is not None:
                query = query.limit(max(int(limit), 1))
            return list(query.all())

    def list_entries(
        self,
        *,
        owner_type: Optional[str] = None,
        owner_id: Optional[str] = None,
        entry_type: Optional[str] = None,
        status: Optional[str] = "active",
        limit: Optional[int] = 100,
    ) -> List[MemoryEntry]:
        """List atomic memory entries ordered by recency."""

        with get_db_session() as db:
            query = db.query(MemoryEntry)
            if owner_type:
                query = query.filter(MemoryEntry.owner_type == str(owner_type))
            if owner_id:
                query = query.filter(MemoryEntry.owner_id == str(owner_id))
            if entry_type:
                query = query.filter(MemoryEntry.entry_type == str(entry_type))
            if status:
                query = query.filter(MemoryEntry.status == str(status))
            query = query.order_by(
                MemoryEntry.updated_at.desc(),
                MemoryEntry.id.desc(),
            )
            if limit is not None:
                query = query.limit(max(int(limit), 1))
            return list(query.all())


_session_ledger_repository: Optional[SessionLedgerRepository] = None


def get_session_ledger_repository() -> SessionLedgerRepository:
    """Return a process-wide singleton repository instance."""

    global _session_ledger_repository
    if _session_ledger_repository is None:
        _session_ledger_repository = SessionLedgerRepository()
    return _session_ledger_repository
