"""Structured retrieval over user-memory metadata fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_

from database.connection import get_db_session
from database.models import UserMemoryEntry, UserMemoryRelation, UserMemoryView
from user_memory.items import RetrievedMemoryItem


@dataclass(frozen=True)
class StructuredTimeRange:
    """Optional time range extracted from planner analysis."""

    start: Optional[datetime] = None
    end: Optional[datetime] = None


@dataclass(frozen=True)
class StructuredQueryFilters:
    """Normalized structured filters for hybrid retrieval."""

    persons: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    predicates: List[str] = field(default_factory=list)
    fact_kinds: List[str] = field(default_factory=list)
    view_types: List[str] = field(default_factory=list)
    time_range: StructuredTimeRange = field(default_factory=StructuredTimeRange)
    allow_history: bool = False


class UserMemoryStructuredSearchService:
    """Metadata-driven entry/view retrieval for user-memory queries."""

    @staticmethod
    def _statuses(filters: StructuredQueryFilters) -> List[str]:
        return ["active", "superseded"] if filters.allow_history else ["active"]

    @staticmethod
    def _entry_to_item(row: Any, *, score: float) -> RetrievedMemoryItem:
        payload = row.entry_data if isinstance(row.entry_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": "structured",
            "search_methods": ["structured"],
            "memory_source": "entry",
            "record_type": "user_fact",
            "entry_id": row.id,
            "entry_key": row.entry_key,
            "fact_kind": row.fact_kind,
            "status": row.status,
            "_structured_score": round(float(score), 4),
        }
        metadata.update(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "fact_kind",
                    "semantic_key",
                    "identity_signature",
                    "canonical_statement",
                    "event_time",
                    "location",
                    "topic",
                    "persons",
                    "entities",
                }
            }
        )
        return RetrievedMemoryItem(
            id=int(row.id),
            content=str(row.canonical_text or "").strip(),
            summary=str(row.summary or "").strip() or None,
            memory_type="user_memory",
            user_id=str(row.user_id),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    @staticmethod
    def _view_to_item(row: Any, *, score: float) -> RetrievedMemoryItem:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": "structured",
            "search_methods": ["structured"],
            "memory_source": "user_memory_view",
            "record_type": str(row.view_type or "view"),
            "view_id": row.id,
            "view_key": row.view_key,
            "view_type": row.view_type,
            "status": row.status,
            "_structured_score": round(float(score), 4),
        }
        metadata.update(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "fact_kind",
                    "semantic_key",
                    "identity_signature",
                    "canonical_statement",
                    "event_time",
                    "location",
                    "topic",
                }
            }
        )
        return RetrievedMemoryItem(
            id=int(row.id),
            content=str(row.content or row.title or "").strip(),
            summary=str(row.content or "").strip() or None,
            memory_type="user_memory",
            user_id=str(row.user_id),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    @staticmethod
    def _entry_score(row: Any, filters: StructuredQueryFilters) -> float:
        score = 0.22
        persons = {str(value).strip() for value in list(row.persons or []) if str(value).strip()}
        entities = {str(value).strip() for value in list(row.entities or []) if str(value).strip()}
        location = str(row.location or "").strip()
        if filters.persons and persons.intersection(filters.persons):
            score += 0.26
        if filters.entities and entities.intersection(filters.entities):
            score += 0.2
        if filters.locations and location and location in set(filters.locations):
            score += 0.16
        if filters.predicates and str(row.predicate or "").strip() in set(filters.predicates):
            score += 0.22
        if filters.fact_kinds and str(row.fact_kind or "").strip() in set(filters.fact_kinds):
            score += 0.18
        if filters.time_range.start and row.event_time_start:
            if row.event_time_start <= (filters.time_range.end or filters.time_range.start):
                score += 0.18
        return min(
            score + 0.12 * max(float(row.importance or 0.0), float(row.confidence or 0.0)), 0.98
        )

    @staticmethod
    def _view_score(row: Any, filters: StructuredQueryFilters) -> float:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        score = 0.22
        if filters.view_types and str(row.view_type or "").strip() in set(filters.view_types):
            score += 0.3
        if filters.locations and str(payload.get("location") or "").strip() in set(
            filters.locations
        ):
            score += 0.16
        if filters.fact_kinds and str(payload.get("fact_kind") or "").strip() in set(
            filters.fact_kinds
        ):
            score += 0.16
        if filters.time_range.start and str(payload.get("event_time") or "").strip():
            score += 0.14
        return min(
            score
            + 0.12
            * max(float(payload.get("importance") or 0.0), float(payload.get("confidence") or 0.0)),
            0.98,
        )

    @staticmethod
    def _relation_to_item(row: Any, *, score: float) -> RetrievedMemoryItem:
        payload = row.relation_data if isinstance(row.relation_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": "structured",
            "search_methods": ["structured"],
            "memory_source": "relation",
            "record_type": "user_relation",
            "relation_id": row.id,
            "relation_key": row.relation_key,
            "fact_kind": "relationship",
            "predicate": row.predicate,
            "object": row.object_text,
            "status": row.status,
            "_structured_score": round(float(score), 4),
        }
        metadata.update(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "semantic_key",
                    "identity_signature",
                    "canonical_statement",
                    "event_time",
                    "location",
                    "persons",
                    "entities",
                }
            }
        )
        return RetrievedMemoryItem(
            id=int(row.id),
            content=str(row.canonical_text or "").strip(),
            summary=str(row.canonical_text or "").strip() or None,
            memory_type="user_memory",
            user_id=str(row.user_id),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    @staticmethod
    def _relation_score(row: Any, filters: StructuredQueryFilters) -> float:
        score = 0.28
        persons = {str(value).strip() for value in list(row.persons or []) if str(value).strip()}
        entities = {str(value).strip() for value in list(row.entities or []) if str(value).strip()}
        location = str(row.location or "").strip()
        predicate = str(row.predicate or "").strip()
        if filters.persons and persons.intersection(filters.persons):
            score += 0.28
        if filters.entities and entities.intersection(filters.entities):
            score += 0.2
        if filters.locations and location and location in set(filters.locations):
            score += 0.16
        if filters.predicates and predicate in set(filters.predicates):
            score += 0.24
        if filters.fact_kinds and "relationship" in set(filters.fact_kinds):
            score += 0.12
        if filters.time_range.start and row.event_time_start:
            if row.event_time_start <= (filters.time_range.end or filters.time_range.start):
                score += 0.14
        return min(
            score + 0.1 * max(float(row.importance or 0.0), float(row.confidence or 0.0)), 0.99
        )

    def search_entries(
        self,
        *,
        user_id: str,
        filters: StructuredQueryFilters,
        top_k: int,
    ) -> List[RetrievedMemoryItem]:
        with get_db_session() as session:
            query = session.query(UserMemoryEntry).filter(UserMemoryEntry.user_id == str(user_id))
            query = query.filter(UserMemoryEntry.status.in_(self._statuses(filters)))
            if filters.fact_kinds:
                query = query.filter(UserMemoryEntry.fact_kind.in_(list(filters.fact_kinds)))
            if filters.time_range.start:
                query = query.filter(
                    and_(
                        UserMemoryEntry.event_time_start.isnot(None),
                        UserMemoryEntry.event_time_start
                        <= (filters.time_range.end or filters.time_range.start),
                        UserMemoryEntry.event_time_end
                        >= (filters.time_range.start or filters.time_range.end),
                    )
                )
            query = query.order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
            rows = list(query.limit(max(int(top_k), 1) * 6).all())

        results: List[RetrievedMemoryItem] = []
        for row in rows:
            persons = {
                str(value).strip() for value in list(row.persons or []) if str(value).strip()
            }
            entities = {
                str(value).strip() for value in list(row.entities or []) if str(value).strip()
            }
            if filters.persons and not persons.intersection(filters.persons):
                continue
            if filters.entities and not entities.intersection(filters.entities):
                continue
            if filters.locations and str(row.location or "").strip() not in set(filters.locations):
                continue
            if filters.predicates and str(row.predicate or "").strip() not in set(
                filters.predicates
            ):
                continue
            results.append(self._entry_to_item(row, score=self._entry_score(row, filters)))

        results.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                (
                    item.timestamp
                    if isinstance(item.timestamp, datetime)
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
            reverse=True,
        )
        return results[: max(int(top_k), 1)]

    def search_relations(
        self,
        *,
        user_id: str,
        filters: StructuredQueryFilters,
        top_k: int,
    ) -> List[RetrievedMemoryItem]:
        if filters.fact_kinds and "relationship" not in set(filters.fact_kinds):
            return []
        with get_db_session() as session:
            query = session.query(UserMemoryRelation).filter(
                UserMemoryRelation.user_id == str(user_id)
            )
            query = query.filter(UserMemoryRelation.status.in_(self._statuses(filters)))
            if filters.predicates:
                query = query.filter(UserMemoryRelation.predicate.in_(list(filters.predicates)))
            if filters.time_range.start:
                query = query.filter(
                    and_(
                        UserMemoryRelation.event_time_start.isnot(None),
                        UserMemoryRelation.event_time_start
                        <= (filters.time_range.end or filters.time_range.start),
                        UserMemoryRelation.event_time_end
                        >= (filters.time_range.start or filters.time_range.end),
                    )
                )
            query = query.order_by(
                UserMemoryRelation.updated_at.desc(), UserMemoryRelation.id.desc()
            )
            rows = list(query.limit(max(int(top_k), 1) * 6).all())

        results: List[RetrievedMemoryItem] = []
        for row in rows:
            persons = {
                str(value).strip() for value in list(row.persons or []) if str(value).strip()
            }
            entities = {
                str(value).strip() for value in list(row.entities or []) if str(value).strip()
            }
            if filters.persons and not persons.intersection(filters.persons):
                continue
            if filters.entities and not entities.intersection(filters.entities):
                continue
            if filters.locations and str(row.location or "").strip() not in set(filters.locations):
                continue
            results.append(self._relation_to_item(row, score=self._relation_score(row, filters)))

        results.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                (
                    item.timestamp
                    if isinstance(item.timestamp, datetime)
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
            reverse=True,
        )
        return results[: max(int(top_k), 1)]

    def search_views(
        self,
        *,
        user_id: str,
        filters: StructuredQueryFilters,
        top_k: int,
    ) -> List[RetrievedMemoryItem]:
        with get_db_session() as session:
            query = session.query(UserMemoryView).filter(UserMemoryView.user_id == str(user_id))
            query = query.filter(UserMemoryView.status.in_(self._statuses(filters)))
            if filters.view_types:
                query = query.filter(UserMemoryView.view_type.in_(list(filters.view_types)))
            query = query.order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
            rows = list(query.limit(max(int(top_k), 1) * 6).all())

        results: List[RetrievedMemoryItem] = []
        for row in rows:
            payload = row.view_data if isinstance(row.view_data, dict) else {}
            if filters.locations and str(payload.get("location") or "").strip() not in set(
                filters.locations
            ):
                continue
            if filters.fact_kinds and str(payload.get("fact_kind") or "").strip() not in set(
                filters.fact_kinds
            ):
                continue
            results.append(self._view_to_item(row, score=self._view_score(row, filters)))

        results.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                (
                    item.timestamp
                    if isinstance(item.timestamp, datetime)
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
            reverse=True,
        )
        return results[: max(int(top_k), 1)]


_structured_search_service: Optional[UserMemoryStructuredSearchService] = None


def get_user_memory_structured_search_service() -> UserMemoryStructuredSearchService:
    """Return the shared structured search service."""

    global _structured_search_service
    if _structured_search_service is None:
        _structured_search_service = UserMemoryStructuredSearchService()
    return _structured_search_service


__all__ = [
    "StructuredQueryFilters",
    "StructuredTimeRange",
    "UserMemoryStructuredSearchService",
    "get_user_memory_structured_search_service",
]
