"""PostgreSQL repository for memory business records.

Milvus remains a vector index. Business CRUD reads/writes must rely on this repository.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func

from database.connection import get_db_session
from database.models import MemoryRecord
from memory_system.memory_interface import MemoryItem, MemoryType

VECTOR_STATUS_PENDING = "pending"
VECTOR_STATUS_SYNCED = "synced"
VECTOR_STATUS_FAILED = "failed"


@dataclass
class MemoryRecordData:
    """Serializable memory record view detached from SQLAlchemy session."""

    id: int
    milvus_id: Optional[int]
    memory_type: MemoryType
    content: str
    user_id: Optional[str]
    agent_id: Optional[str]
    task_id: Optional[str]
    metadata: Dict[str, Any]
    timestamp: datetime
    vector_status: str
    vector_error: Optional[str]
    vector_updated_at: Optional[datetime]

    def to_memory_item(
        self,
        *,
        similarity_score: Optional[float] = None,
        include_vector_status: bool = True,
    ) -> MemoryItem:
        """Convert record data to API-facing MemoryItem."""
        metadata = dict(self.metadata or {})
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
        return MemoryRecordData(
            id=int(row.id),
            milvus_id=int(row.milvus_id) if row.milvus_id is not None else None,
            memory_type=cls._parse_memory_type(row.memory_type),
            content=row.content,
            user_id=row.user_id,
            agent_id=row.agent_id,
            task_id=row.task_id,
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
        timestamp = memory_item.timestamp or datetime.utcnow()
        metadata = dict(memory_item.metadata or {})
        task_id = memory_item.task_id or metadata.get("task_id")

        with get_db_session() as session:
            row = MemoryRecord(
                memory_type=memory_item.memory_type.value,
                content=memory_item.content,
                user_id=memory_item.user_id,
                agent_id=memory_item.agent_id,
                task_id=task_id,
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
            if metadata is not None:
                row.memory_metadata = metadata
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

            # Mark as pending re-index when content/type/identity fields changed.
            if mark_vector_pending:
                row.vector_status = VECTOR_STATUS_PENDING
                row.vector_error = None
                row.vector_updated_at = None

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
                cutoff = datetime.utcnow() - timedelta(minutes=int(within_minutes))
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
            row.vector_updated_at = datetime.utcnow()
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
            row.vector_updated_at = datetime.utcnow()
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
            row.vector_updated_at = datetime.utcnow()
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
                row.updated_at = datetime.utcnow()

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
                    row.timestamp or datetime.utcnow(),
                )
            )
            core_rows.sort(
                key=lambda row: (
                    self._metadata_utility_score(row),
                    row.timestamp or datetime.utcnow(),
                )
            )

            ordered_rows = (
                non_core_rows + core_rows
                if protect_core
                else sorted(
                    rows,
                    key=lambda row: (
                        self._metadata_utility_score(row),
                        row.timestamp or datetime.utcnow(),
                    ),
                )
            )

            selected_rows = ordered_rows[:safe_count]
            evicted: List[MemoryRecordData] = []
            for row in selected_rows:
                evicted.append(self._to_data(row))
                row.is_deleted = True
                row.updated_at = datetime.utcnow()

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
                row.updated_at = datetime.utcnow()

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
            row.updated_at = datetime.utcnow()
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
                row.updated_at = datetime.utcnow()

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


_memory_repository: Optional[MemoryRepository] = None


def get_memory_repository() -> MemoryRepository:
    """Get singleton memory repository."""
    global _memory_repository
    if _memory_repository is None:
        _memory_repository = MemoryRepository()
    return _memory_repository
