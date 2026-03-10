"""PostgreSQL repository for memory business records.

Milvus remains a vector index. Business CRUD reads/writes must rely on this repository.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import case, desc, func, literal, or_

from database.connection import get_db_session
from database.models import MemoryACL, MemoryRecord
from memory_system.memory_interface import MemoryItem, MemoryType

VECTOR_STATUS_PENDING = "pending"
VECTOR_STATUS_SYNCED = "synced"
VECTOR_STATUS_FAILED = "failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MemoryRecordData:
    """Serializable memory record view detached from SQLAlchemy session."""

    id: int
    milvus_id: Optional[int] = None
    memory_type: MemoryType = MemoryType.COMPANY
    content: str = ""
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    task_id: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_agent_id: Optional[str] = None
    department_id: Optional[str] = None
    visibility: str = "account"
    sensitivity: str = "internal"
    source_memory_id: Optional[int] = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utc_now)
    vector_status: str = VECTOR_STATUS_PENDING
    vector_error: Optional[str] = None
    vector_updated_at: Optional[datetime] = None

    def to_memory_item(
        self,
        *,
        similarity_score: Optional[float] = None,
        include_vector_status: bool = True,
    ) -> MemoryItem:
        """Convert record data to API-facing MemoryItem."""
        metadata = dict(self.metadata or {})
        metadata.setdefault("owner_user_id", self.owner_user_id)
        metadata.setdefault("owner_agent_id", self.owner_agent_id)
        metadata.setdefault("department_id", self.department_id)
        metadata.setdefault("visibility", self.visibility)
        metadata.setdefault("sensitivity", self.sensitivity)
        metadata.setdefault("source_memory_id", self.source_memory_id)
        metadata.setdefault("expires_at", self.expires_at.isoformat() if self.expires_at else None)
        if include_vector_status:
            metadata.setdefault("vector_status", self.vector_status)
            if self.vector_error:
                metadata.setdefault("vector_error", self.vector_error)

        return MemoryItem(
            id=self.id,
            content=self.content,
            memory_type=self.memory_type,
            agent_id=self.agent_id,
            user_id=self.user_id,
            task_id=self.task_id,
            timestamp=self.timestamp,
            metadata=metadata,
            similarity_score=similarity_score,
        )


class MemoryRepository:
    """Repository for memory records persisted in PostgreSQL."""

    @staticmethod
    def _parse_datetime(raw: Any) -> Optional[datetime]:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw
        text = str(raw).strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _coerce_optional_int(raw: Any) -> Optional[int]:
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _default_visibility(memory_type: MemoryType) -> str:
        if memory_type in {MemoryType.AGENT, MemoryType.USER_CONTEXT}:
            return "private"
        return "department_tree"

    def _normalize_security_fields(
        self,
        *,
        memory_type: MemoryType,
        metadata: Dict[str, Any],
        user_id: Optional[str],
        agent_id: Optional[str],
        owner_user_id: Optional[str] = None,
        owner_agent_id: Optional[str] = None,
        department_id: Optional[str] = None,
        visibility: Optional[str] = None,
        sensitivity: Optional[str] = None,
        source_memory_id: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        normalized = dict(metadata or {})

        resolved_owner_user_id = (
            owner_user_id
            if owner_user_id is not None
            else str(normalized.get("owner_user_id") or user_id or "").strip() or None
        )
        resolved_owner_agent_id = (
            owner_agent_id
            if owner_agent_id is not None
            else str(normalized.get("owner_agent_id") or agent_id or "").strip() or None
        )
        resolved_department_id = (
            department_id
            if department_id is not None
            else str(normalized.get("department_id") or "").strip() or None
        )
        resolved_visibility = (
            str(visibility).strip().lower()
            if visibility is not None
            else str(normalized.get("visibility") or "").strip().lower()
        )
        if not resolved_visibility:
            resolved_visibility = self._default_visibility(memory_type)

        resolved_sensitivity = (
            str(sensitivity).strip().lower()
            if sensitivity is not None
            else str(normalized.get("sensitivity") or "").strip().lower()
        )
        if not resolved_sensitivity:
            resolved_sensitivity = "internal"

        resolved_source_memory_id = (
            source_memory_id
            if source_memory_id is not None
            else self._coerce_optional_int(normalized.get("source_memory_id"))
        )
        resolved_expires_at = (
            expires_at
            if expires_at is not None
            else self._parse_datetime(normalized.get("expires_at"))
        )

        normalized["owner_user_id"] = resolved_owner_user_id
        normalized["owner_agent_id"] = resolved_owner_agent_id
        normalized["department_id"] = resolved_department_id
        normalized["visibility"] = resolved_visibility
        normalized["sensitivity"] = resolved_sensitivity
        normalized["source_memory_id"] = resolved_source_memory_id
        normalized["expires_at"] = resolved_expires_at.isoformat() if resolved_expires_at else None

        return {
            "metadata": normalized,
            "owner_user_id": resolved_owner_user_id,
            "owner_agent_id": resolved_owner_agent_id,
            "department_id": resolved_department_id,
            "visibility": resolved_visibility,
            "sensitivity": resolved_sensitivity,
            "source_memory_id": resolved_source_memory_id,
            "expires_at": resolved_expires_at,
        }

    @staticmethod
    def _coerce_float(raw: Any, default: float = 0.0) -> float:
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _coerce_int(raw: Any, default: int = 0) -> int:
        try:
            return int(raw)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _escape_like(term: str) -> str:
        return str(term or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    @staticmethod
    def _normalize_keyword_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
        return " ".join(normalized.split())

    @staticmethod
    def _is_cjk_text(text: str) -> bool:
        return bool(re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", str(text or "")))

    @staticmethod
    def _is_boundary_sensitive_term(term: str) -> bool:
        return bool(re.fullmatch(r"[a-z0-9][a-z0-9._-]*", str(term or "")))

    @classmethod
    def _term_matches_content(cls, normalized_content: str, term: str) -> bool:
        normalized_term = cls._normalize_keyword_text(term)
        if len(normalized_term) < 2:
            return False

        if cls._is_cjk_text(normalized_term):
            return normalized_term in normalized_content

        if cls._is_boundary_sensitive_term(normalized_term):
            pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
            return bool(re.search(pattern, normalized_content))

        return normalized_term in normalized_content

    @classmethod
    def _compute_keyword_match_features(
        cls,
        *,
        content: str,
        query_terms: List[str],
        normalized_full_query: str,
    ) -> Dict[str, Any]:
        normalized_content = cls._normalize_keyword_text(content)
        if not normalized_content:
            return {
                "strict_term_hits": 0,
                "strong_term_hits": 0,
                "coverage_ratio": 0.0,
                "phrase_hit": False,
            }

        strict_term_hits = 0
        strong_term_hits = 0
        normalized_terms: List[str] = []
        seen = set()
        for raw_term in query_terms:
            normalized_term = cls._normalize_keyword_text(raw_term)
            if len(normalized_term) < 2:
                continue
            if normalized_term in seen:
                continue
            seen.add(normalized_term)
            normalized_terms.append(normalized_term)
            if cls._term_matches_content(normalized_content, normalized_term):
                strict_term_hits += 1
                if (cls._is_cjk_text(normalized_term) and len(normalized_term) >= 2) or (
                    not cls._is_cjk_text(normalized_term) and len(normalized_term) >= 4
                ):
                    strong_term_hits += 1

        total_terms = max(len(normalized_terms), 1)
        coverage_ratio = min(max(strict_term_hits / total_terms, 0.0), 1.0)
        phrase_hit = len(normalized_full_query) >= 2 and normalized_full_query in normalized_content
        return {
            "strict_term_hits": strict_term_hits,
            "strong_term_hits": strong_term_hits,
            "coverage_ratio": coverage_ratio,
            "phrase_hit": phrase_hit,
        }

    @staticmethod
    def _passes_keyword_quality_gate(
        *,
        strict_term_hits: int,
        strong_term_hits: int,
        phrase_hit: bool,
        required_term_hits: int,
        total_terms: int,
    ) -> bool:
        if strict_term_hits < required_term_hits:
            return False
        if total_terms >= 3 and not phrase_hit and strong_term_hits <= 0:
            return False
        return True

    @classmethod
    def _metadata_utility_score(cls, row: MemoryRecord) -> float:
        """Compute utility score for eviction ordering (lower means easier to evict)."""
        metadata = dict(row.memory_metadata or {})
        importance = min(max(cls._coerce_float(metadata.get("importance_score"), 0.0), 0.0), 1.0)
        mention_count = max(cls._coerce_int(metadata.get("mention_count"), 1), 1)
        tier = str(metadata.get("memory_tier") or "").strip().lower()
        core_boost = 0.2 if tier == "core" else 0.0
        mention_boost = min(mention_count / 20.0, 0.2)
        return importance + core_boost + mention_boost

    @staticmethod
    def _parse_memory_type(raw_type: Any) -> MemoryType:
        try:
            return MemoryType(raw_type)
        except Exception:
            return MemoryType.COMPANY

    @classmethod
    def _to_data(cls, row: MemoryRecord) -> MemoryRecordData:
        metadata = dict(row.memory_metadata or {})
        metadata.setdefault("owner_user_id", row.owner_user_id)
        metadata.setdefault("owner_agent_id", row.owner_agent_id)
        metadata.setdefault("department_id", row.department_id)
        metadata.setdefault("visibility", row.visibility)
        metadata.setdefault("sensitivity", row.sensitivity)
        metadata.setdefault("source_memory_id", row.source_memory_id)
        metadata.setdefault("expires_at", row.expires_at.isoformat() if row.expires_at else None)
        return MemoryRecordData(
            id=int(row.id),
            milvus_id=int(row.milvus_id) if row.milvus_id is not None else None,
            memory_type=cls._parse_memory_type(row.memory_type),
            content=row.content,
            user_id=row.user_id,
            agent_id=row.agent_id,
            task_id=row.task_id,
            owner_user_id=row.owner_user_id,
            owner_agent_id=row.owner_agent_id,
            department_id=row.department_id,
            visibility=row.visibility or "account",
            sensitivity=row.sensitivity or "internal",
            source_memory_id=(
                int(row.source_memory_id) if row.source_memory_id is not None else None
            ),
            expires_at=row.expires_at,
            metadata=metadata,
            timestamp=row.timestamp,
            vector_status=row.vector_status or VECTOR_STATUS_PENDING,
            vector_error=row.vector_error,
            vector_updated_at=row.vector_updated_at,
        )

    @staticmethod
    def _build_filters(
        query,
        *,
        memory_type: Optional[MemoryType] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        include_deleted: bool = False,
    ):
        if not include_deleted:
            query = query.filter(MemoryRecord.is_deleted.is_(False))
        if memory_type:
            query = query.filter(MemoryRecord.memory_type == memory_type.value)
        if agent_id:
            query = query.filter(MemoryRecord.agent_id == agent_id)
        if user_id:
            query = query.filter(MemoryRecord.user_id == user_id)
        if task_id:
            query = query.filter(MemoryRecord.task_id == task_id)
        return query

    def create(self, memory_item: MemoryItem) -> MemoryRecordData:
        """Create a memory record in PostgreSQL with pending vector sync status."""
        timestamp = memory_item.timestamp or _utc_now()
        metadata = dict(memory_item.metadata or {})
        task_id = memory_item.task_id or metadata.get("task_id")
        security = self._normalize_security_fields(
            memory_type=memory_item.memory_type,
            metadata=metadata,
            user_id=memory_item.user_id,
            agent_id=memory_item.agent_id,
        )
        metadata = security["metadata"]

        with get_db_session() as session:
            row = MemoryRecord(
                memory_type=memory_item.memory_type.value,
                content=memory_item.content,
                user_id=memory_item.user_id,
                agent_id=memory_item.agent_id,
                task_id=task_id,
                owner_user_id=security["owner_user_id"],
                owner_agent_id=security["owner_agent_id"],
                department_id=security["department_id"],
                visibility=security["visibility"],
                sensitivity=security["sensitivity"],
                source_memory_id=security["source_memory_id"],
                expires_at=security["expires_at"],
                memory_metadata=metadata,
                timestamp=timestamp,
                vector_status=VECTOR_STATUS_PENDING,
                vector_error=None,
                vector_updated_at=None,
                is_deleted=False,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            return self._to_data(row)

    def get(self, memory_id: int, *, include_deleted: bool = False) -> Optional[MemoryRecordData]:
        """Get a memory by PostgreSQL memory id."""
        with get_db_session() as session:
            query = session.query(MemoryRecord).filter(MemoryRecord.id == memory_id)
            query = self._build_filters(query, include_deleted=include_deleted)
            row = query.first()
            return self._to_data(row) if row else None

    def get_by_milvus_id(
        self,
        milvus_id: int,
        *,
        include_deleted: bool = False,
    ) -> Optional[MemoryRecordData]:
        """Get memory record by Milvus id."""
        with get_db_session() as session:
            query = session.query(MemoryRecord).filter(MemoryRecord.milvus_id == milvus_id)
            query = self._build_filters(query, include_deleted=include_deleted)
            row = query.first()
            return self._to_data(row) if row else None

    def get_by_milvus_ids(self, milvus_ids: List[int]) -> Dict[int, MemoryRecordData]:
        """Batch load records keyed by Milvus id."""
        if not milvus_ids:
            return {}

        unique_ids = sorted({int(mid) for mid in milvus_ids})
        with get_db_session() as session:
            rows = (
                session.query(MemoryRecord)
                .filter(MemoryRecord.is_deleted.is_(False))
                .filter(MemoryRecord.milvus_id.in_(unique_ids))
                .all()
            )
            data = [self._to_data(row) for row in rows]
            return {item.milvus_id: item for item in data if item.milvus_id is not None}

    def list_memories(
        self,
        *,
        memory_type: Optional[MemoryType] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[MemoryRecordData]:
        """List memories from PostgreSQL with optional filters."""
        with get_db_session() as session:
            query = session.query(MemoryRecord)
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
                task_id=task_id,
            )
            query = query.order_by(desc(MemoryRecord.timestamp))
            if limit is not None:
                query = query.limit(limit)
            rows = query.all()
            return [self._to_data(row) for row in rows]

    def search_text(
        self,
        query_text: str,
        *,
        memory_type: Optional[MemoryType] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[MemoryRecordData]:
        """Fallback text search directly in PostgreSQL."""
        with get_db_session() as session:
            query = session.query(MemoryRecord)
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
                task_id=task_id,
            )
            like_expr = f"%{query_text}%"
            rows = (
                query.filter(MemoryRecord.content.ilike(like_expr))
                .order_by(desc(MemoryRecord.timestamp))
                .limit(limit)
                .all()
            )
            return [self._to_data(row) for row in rows]

    def search_keywords(
        self,
        query_text: str,
        *,
        query_terms: List[str],
        memory_type: Optional[MemoryType] = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        min_term_hits: int = 1,
        min_rank: float = 1.0,
        limit: int = 10,
        strict_semantics: bool = True,
    ) -> List[Tuple[MemoryRecordData, float, int]]:
        """Keyword search with stricter semantics and optional full-text signal."""
        normalized_terms: List[str] = []
        seen = set()
        for raw_term in query_terms or []:
            term = self._normalize_keyword_text(raw_term)
            if len(term) < 2:
                continue
            canonical = term
            if canonical in seen:
                continue
            seen.add(canonical)
            normalized_terms.append(term)

        full_query = self._normalize_keyword_text(query_text)
        full_query_key = full_query
        if len(full_query) >= 2 and full_query_key not in seen:
            normalized_terms.insert(0, full_query)

        if not normalized_terms:
            return []

        required_term_hits = max(int(min_term_hits or 1), 1)
        required_rank = max(float(min_rank or 0.0), 0.0)
        top_k = max(int(limit or 10), 1)

        with get_db_session() as session:
            query = session.query(MemoryRecord)
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
                task_id=task_id,
            )

            match_clauses = []
            score_expr = literal(0.0)
            term_hit_expr = literal(0)
            fts_match_clause = None
            fts_rank_expr = literal(0.0)
            if len(full_query) >= 2:
                tsvector_expr = func.to_tsvector("simple", MemoryRecord.content)
                tsquery_expr = func.plainto_tsquery("simple", full_query)
                fts_match_clause = tsvector_expr.op("@@")(tsquery_expr)
                fts_rank_expr = case(
                    (fts_match_clause, func.ts_rank_cd(tsvector_expr, tsquery_expr)),
                    else_=0.0,
                )

            for term in normalized_terms:
                pattern = f"%{self._escape_like(term)}%"
                clause = MemoryRecord.content.ilike(pattern, escape="\\")
                match_clauses.append(clause)

                is_full_query = term.casefold() == full_query_key
                term_weight = 4.0 if is_full_query else (2.8 if len(term) >= 4 else 1.8)

                score_expr = score_expr + case((clause, term_weight), else_=0.0)
                term_hit_expr = term_hit_expr + case((clause, 1), else_=0)

            keyword_rank = score_expr.label("keyword_rank")
            keyword_term_hits = term_hit_expr.label("keyword_term_hits")
            keyword_fts_rank = fts_rank_expr.label("keyword_fts_rank")
            candidate_clauses = list(match_clauses)
            if fts_match_clause is not None:
                candidate_clauses.append(fts_match_clause)
            rows = (
                query.filter(or_(*candidate_clauses))
                .add_columns(keyword_rank, keyword_term_hits, keyword_fts_rank)
                .order_by(keyword_rank.desc(), desc(MemoryRecord.timestamp))
                .limit(max(top_k * 8, top_k + 16))
                .all()
            )

            ranked: List[Tuple[MemoryRecordData, float, int]] = []
            for row, raw_rank, raw_term_hits, raw_fts_rank in rows:
                rank = float(raw_rank or 0.0)
                term_hits = int(raw_term_hits or 0)
                if strict_semantics:
                    match_features = self._compute_keyword_match_features(
                        content=row.content,
                        query_terms=normalized_terms,
                        normalized_full_query=full_query,
                    )
                    strict_term_hits = int(match_features["strict_term_hits"])
                    strong_term_hits = int(match_features["strong_term_hits"])
                    phrase_hit = bool(match_features["phrase_hit"])
                    coverage_ratio = float(match_features["coverage_ratio"])

                    if not self._passes_keyword_quality_gate(
                        strict_term_hits=strict_term_hits,
                        strong_term_hits=strong_term_hits,
                        phrase_hit=phrase_hit,
                        required_term_hits=required_term_hits,
                        total_terms=len(normalized_terms),
                    ):
                        continue

                    lexical_boost = (
                        (2.2 if phrase_hit else 0.0)
                        + (1.6 * coverage_ratio)
                        + (0.4 * min(strong_term_hits, 3))
                    )
                    fts_rank = min(max(float(raw_fts_rank or 0.0), 0.0), 1.0)
                    rank = rank + lexical_boost + (3.0 * fts_rank)
                    term_hits = strict_term_hits

                if rank < required_rank or term_hits < required_term_hits:
                    continue

                ranked.append((self._to_data(row), rank, term_hits))
                if len(ranked) >= top_k:
                    break

            return ranked

    def update_record(
        self,
        memory_id: int,
        *,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        memory_type: Optional[MemoryType] = None,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        owner_user_id: Optional[str] = None,
        owner_agent_id: Optional[str] = None,
        department_id: Optional[str] = None,
        visibility: Optional[str] = None,
        sensitivity: Optional[str] = None,
        source_memory_id: Optional[int] = None,
        expires_at: Optional[datetime] = None,
        clear_expires_at: bool = False,
        mark_vector_pending: bool = True,
    ) -> Optional[MemoryRecordData]:
        """Update selected fields on a memory record."""
        with get_db_session() as session:
            row = (
                session.query(MemoryRecord)
                .filter(MemoryRecord.id == memory_id)
                .filter(MemoryRecord.is_deleted.is_(False))
                .first()
            )
            if not row:
                return None

            if content is not None:
                row.content = content
            incoming_metadata = dict(metadata) if metadata is not None else None
            if memory_type is not None:
                row.memory_type = memory_type.value
            if user_id is not None:
                row.user_id = user_id
            if agent_id is not None:
                row.agent_id = agent_id
            if task_id is not None:
                row.task_id = task_id
            if timestamp is not None:
                row.timestamp = timestamp
            if owner_user_id is not None:
                row.owner_user_id = owner_user_id
            if owner_agent_id is not None:
                row.owner_agent_id = owner_agent_id
            if department_id is not None:
                row.department_id = department_id
            if visibility is not None:
                row.visibility = visibility
            if sensitivity is not None:
                row.sensitivity = sensitivity
            if source_memory_id is not None:
                row.source_memory_id = source_memory_id
            if expires_at is not None:
                row.expires_at = expires_at
            elif clear_expires_at:
                row.expires_at = None

            # Mark as pending re-index when content/type/identity fields changed.
            if mark_vector_pending:
                row.vector_status = VECTOR_STATUS_PENDING
                row.vector_error = None
                row.vector_updated_at = None

            security_changed = any(
                value is not None
                for value in (
                    owner_user_id,
                    owner_agent_id,
                    department_id,
                    visibility,
                    sensitivity,
                    source_memory_id,
                    expires_at,
                    clear_expires_at,
                )
            )

            if incoming_metadata is not None or security_changed:
                row_type = self._parse_memory_type(row.memory_type)
                security = self._normalize_security_fields(
                    memory_type=row_type,
                    metadata=(
                        incoming_metadata
                        if incoming_metadata is not None
                        else dict(row.memory_metadata or {})
                    ),
                    user_id=row.user_id,
                    agent_id=row.agent_id,
                    owner_user_id=row.owner_user_id,
                    owner_agent_id=row.owner_agent_id,
                    department_id=row.department_id,
                    visibility=row.visibility,
                    sensitivity=row.sensitivity,
                    source_memory_id=row.source_memory_id,
                    expires_at=row.expires_at,
                )
                row.memory_metadata = security["metadata"]
                row.owner_user_id = security["owner_user_id"]
                row.owner_agent_id = security["owner_agent_id"]
                row.department_id = security["department_id"]
                row.visibility = security["visibility"]
                row.sensitivity = security["sensitivity"]
                row.source_memory_id = security["source_memory_id"]
                row.expires_at = security["expires_at"]

            session.flush()
            session.refresh(row)
            return self._to_data(row)

    def find_recent_by_content_hash(
        self,
        *,
        memory_type: MemoryType,
        content_hash: str,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        within_minutes: int = 10080,
    ) -> Optional[MemoryRecordData]:
        """Find the latest active memory that matches the same normalized content hash."""
        normalized_hash = str(content_hash or "").strip()
        if not normalized_hash:
            return None

        with get_db_session() as session:
            query = session.query(MemoryRecord)
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
            )
            query = query.filter(
                MemoryRecord.memory_metadata["content_hash"].astext == normalized_hash
            )

            if within_minutes and within_minutes > 0:
                cutoff = _utc_now() - timedelta(minutes=int(within_minutes))
                query = query.filter(MemoryRecord.timestamp >= cutoff)

            row = query.order_by(desc(MemoryRecord.timestamp)).first()
            return self._to_data(row) if row else None

    def list_scope_candidates(
        self,
        *,
        memory_type: MemoryType,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[MemoryRecordData]:
        """Return recent records in the same scope for merge/dedup decisions."""
        safe_limit = max(int(limit), 1)
        return self.list_memories(
            memory_type=memory_type,
            agent_id=agent_id,
            user_id=user_id,
            limit=safe_limit,
        )

    def mark_vector_synced(self, memory_id: int, milvus_id: int) -> Optional[MemoryRecordData]:
        """Persist successful vector sync status."""
        with get_db_session() as session:
            row = session.query(MemoryRecord).filter(MemoryRecord.id == memory_id).first()
            if not row:
                return None

            row.milvus_id = milvus_id
            row.vector_status = VECTOR_STATUS_SYNCED
            row.vector_error = None
            row.vector_updated_at = _utc_now()
            session.flush()
            session.refresh(row)
            return self._to_data(row)

    def mark_vector_failed(self, memory_id: int, error: str) -> Optional[MemoryRecordData]:
        """Persist failed vector sync status for retry visibility."""
        with get_db_session() as session:
            row = session.query(MemoryRecord).filter(MemoryRecord.id == memory_id).first()
            if not row:
                return None

            row.vector_status = VECTOR_STATUS_FAILED
            row.vector_error = (error or "")[:2000] or None
            row.vector_updated_at = _utc_now()
            session.flush()
            session.refresh(row)
            return self._to_data(row)

    def clear_milvus_link(self, memory_id: int) -> Optional[MemoryRecordData]:
        """Clear Milvus link when vector row is deleted/replaced."""
        with get_db_session() as session:
            row = session.query(MemoryRecord).filter(MemoryRecord.id == memory_id).first()
            if not row:
                return None

            row.milvus_id = None
            row.vector_status = VECTOR_STATUS_PENDING
            row.vector_error = None
            row.vector_updated_at = _utc_now()
            session.flush()
            session.refresh(row)
            return self._to_data(row)

    def count_memories(
        self,
        memory_type: MemoryType,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> int:
        """Count active memories matching the given scope."""
        with get_db_session() as session:
            query = session.query(func.count(MemoryRecord.id))
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
            )
            return query.scalar() or 0

    def evict_oldest(
        self,
        memory_type: MemoryType,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        count: int = 1,
    ) -> List[MemoryRecordData]:
        """Soft-delete the oldest N memories and return their data for vector cleanup."""
        with get_db_session() as session:
            query = session.query(MemoryRecord)
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
            )
            oldest_rows = query.order_by(MemoryRecord.timestamp.asc()).limit(count).all()

            evicted = []
            for row in oldest_rows:
                evicted.append(self._to_data(row))
                row.is_deleted = True
                row.updated_at = _utc_now()

            return evicted

    def evict_low_value(
        self,
        *,
        memory_type: MemoryType,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        count: int = 1,
        protect_core: bool = True,
    ) -> List[MemoryRecordData]:
        """Soft-delete lowest-value memories first (importance/mentions/tier aware)."""
        safe_count = max(int(count), 0)
        if safe_count <= 0:
            return []

        with get_db_session() as session:
            query = session.query(MemoryRecord)
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
            )
            rows = query.all()
            if not rows:
                return []

            non_core_rows: List[MemoryRecord] = []
            core_rows: List[MemoryRecord] = []
            for row in rows:
                tier = str((row.memory_metadata or {}).get("memory_tier") or "").strip().lower()
                if tier == "core":
                    core_rows.append(row)
                else:
                    non_core_rows.append(row)

            non_core_rows.sort(
                key=lambda row: (
                    self._metadata_utility_score(row),
                    row.timestamp or _utc_now(),
                )
            )
            core_rows.sort(
                key=lambda row: (
                    self._metadata_utility_score(row),
                    row.timestamp or _utc_now(),
                )
            )

            ordered_rows = (
                non_core_rows + core_rows
                if protect_core
                else sorted(
                    rows,
                    key=lambda row: (
                        self._metadata_utility_score(row),
                        row.timestamp or _utc_now(),
                    ),
                )
            )

            selected_rows = ordered_rows[:safe_count]
            evicted: List[MemoryRecordData] = []
            for row in selected_rows:
                evicted.append(self._to_data(row))
                row.is_deleted = True
                row.updated_at = _utc_now()

            return evicted

    def evict_older_than(
        self,
        *,
        memory_type: MemoryType,
        older_than: datetime,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: Optional[int] = None,
        protect_core: bool = True,
    ) -> List[MemoryRecordData]:
        """Soft-delete memories older than cutoff (optionally preserving core tier)."""
        with get_db_session() as session:
            query = session.query(MemoryRecord)
            query = self._build_filters(
                query,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
            )
            query = query.filter(MemoryRecord.timestamp < older_than)
            rows = query.order_by(MemoryRecord.timestamp.asc()).all()

            selected_rows: List[MemoryRecord] = []
            for row in rows:
                if protect_core:
                    tier = str((row.memory_metadata or {}).get("memory_tier") or "").strip().lower()
                    if tier == "core":
                        continue
                selected_rows.append(row)
                if limit is not None and len(selected_rows) >= max(int(limit), 0):
                    break

            evicted: List[MemoryRecordData] = []
            for row in selected_rows:
                evicted.append(self._to_data(row))
                row.is_deleted = True
                row.updated_at = _utc_now()

            return evicted

    def soft_delete(self, memory_id: int) -> bool:
        """Soft delete memory record."""
        with get_db_session() as session:
            row = (
                session.query(MemoryRecord)
                .filter(MemoryRecord.id == memory_id)
                .filter(MemoryRecord.is_deleted.is_(False))
                .first()
            )
            if not row:
                return False

            row.is_deleted = True
            row.updated_at = _utc_now()
            return True

    def purge_by_type(self, memory_type: MemoryType, *, agent_id: Optional[str] = None) -> int:
        """Soft delete all memories of a given type (optionally by agent)."""
        with get_db_session() as session:
            query = (
                session.query(MemoryRecord)
                .filter(MemoryRecord.is_deleted.is_(False))
                .filter(MemoryRecord.memory_type == memory_type.value)
            )
            if agent_id:
                query = query.filter(MemoryRecord.agent_id == agent_id)

            rows = query.all()
            for row in rows:
                row.is_deleted = True
                row.updated_at = _utc_now()

            return len(rows)

    def list_shared_children(self, source_memory_id: int) -> List[MemoryRecordData]:
        """List active shared copies created from a source memory."""
        with get_db_session() as session:
            rows = (
                session.query(MemoryRecord)
                .filter(MemoryRecord.is_deleted.is_(False))
                .filter(MemoryRecord.memory_metadata["shared_from"].astext == str(source_memory_id))
                .order_by(desc(MemoryRecord.timestamp))
                .all()
            )
            return [self._to_data(row) for row in rows]

    def replace_acl_entries(
        self,
        memory_id: int,
        entries: List[Dict[str, Any]],
        *,
        created_by: Optional[str] = None,
    ) -> int:
        """Replace memory ACL entries for a record."""
        now = _utc_now()
        with get_db_session() as session:
            (
                session.query(MemoryACL)
                .filter(MemoryACL.memory_id == memory_id)
                .delete(synchronize_session=False)
            )

            created = 0
            for entry in entries:
                effect = str(entry.get("effect") or "").strip().lower()
                principal_type = str(entry.get("principal_type") or "").strip().lower()
                principal_id = str(entry.get("principal_id") or "").strip()
                if effect not in {"allow", "deny"}:
                    continue
                if principal_type not in {"user", "agent", "department", "role"}:
                    continue
                if not principal_id:
                    continue

                acl = MemoryACL(
                    memory_id=memory_id,
                    effect=effect,
                    principal_type=principal_type,
                    principal_id=principal_id,
                    reason=entry.get("reason"),
                    expires_at=self._parse_datetime(entry.get("expires_at")),
                    created_by=created_by,
                    acl_metadata=(
                        entry.get("metadata") if isinstance(entry.get("metadata"), dict) else None
                    ),
                    created_at=now,
                )
                session.add(acl)
                created += 1

            return created

    def list_active_acl_entries(
        self,
        memory_ids: List[int],
        *,
        now: Optional[datetime] = None,
    ) -> Dict[int, List[Dict[str, Any]]]:
        """List non-expired ACL entries keyed by memory_id."""
        if not memory_ids:
            return {}

        as_of = now or _utc_now()
        unique_ids = sorted({int(mid) for mid in memory_ids})
        with get_db_session() as session:
            rows = (
                session.query(MemoryACL)
                .filter(MemoryACL.memory_id.in_(unique_ids))
                .filter((MemoryACL.expires_at.is_(None)) | (MemoryACL.expires_at > as_of))
                .order_by(MemoryACL.created_at.asc())
                .all()
            )

        grouped: Dict[int, List[Dict[str, Any]]] = {mid: [] for mid in unique_ids}
        for row in rows:
            grouped.setdefault(int(row.memory_id), []).append(
                {
                    "effect": row.effect,
                    "principal_type": row.principal_type,
                    "principal_id": row.principal_id,
                    "reason": row.reason,
                    "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                    "created_by": row.created_by,
                    "metadata": row.acl_metadata if isinstance(row.acl_metadata, dict) else None,
                }
            )

        return grouped


_memory_repository: Optional[MemoryRepository] = None


def get_memory_repository() -> MemoryRepository:
    """Get singleton memory repository."""
    global _memory_repository
    if _memory_repository is None:
        _memory_repository = MemoryRepository()
    return _memory_repository
