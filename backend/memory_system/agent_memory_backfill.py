"""Utilities for backfilling missing user_id on agent memories."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import Agent, MemoryRecord
from memory_system.memory_interface import MemoryItem, MemoryType
from memory_system.memory_repository import get_memory_repository
from memory_system.memory_system import get_memory_system

logger = logging.getLogger(__name__)


def _safe_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    return dt.isoformat()


def _parse_uuid(value: Optional[str]) -> Optional[UUID]:
    if not value:
        return None
    try:
        return UUID(str(value))
    except Exception:
        return None


def _collect_candidates(
    *,
    agent_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    parsed_filter_agent_id = _parse_uuid(agent_id) if agent_id else None
    filter_agent_id_str = str(parsed_filter_agent_id) if parsed_filter_agent_id else None

    with get_db_session() as session:
        base_query = session.query(MemoryRecord).filter(
            MemoryRecord.memory_type == MemoryType.AGENT.value,
            MemoryRecord.is_deleted.is_(False),
            MemoryRecord.user_id.is_(None),
        )
        if filter_agent_id_str:
            base_query = base_query.filter(MemoryRecord.agent_id == filter_agent_id_str)

        total_missing = int(base_query.count() or 0)

        rows_query = base_query.order_by(MemoryRecord.timestamp.desc())
        if limit is not None:
            rows_query = rows_query.limit(max(1, int(limit)))
        rows = rows_query.all()

        row_ids = [int(row.id) for row in rows]
        agent_id_set = {str(row.agent_id) for row in rows if row.agent_id}
        parsed_agent_ids = [_parse_uuid(aid) for aid in agent_id_set]
        parsed_agent_ids = [aid for aid in parsed_agent_ids if aid is not None]

        owner_by_agent_id: Dict[str, str] = {}
        if parsed_agent_ids:
            owner_rows = (
                session.query(Agent.agent_id, Agent.owner_user_id)
                .filter(Agent.agent_id.in_(parsed_agent_ids))
                .all()
            )
            owner_by_agent_id = {str(r.agent_id): str(r.owner_user_id) for r in owner_rows}

        resolvable_ids: List[int] = []
        unresolved: List[Dict[str, Any]] = []
        preview: List[Dict[str, Any]] = []

        for row in rows:
            row_agent_id = str(row.agent_id) if row.agent_id else ""
            owner_user_id = owner_by_agent_id.get(row_agent_id)
            if owner_user_id:
                resolvable_ids.append(int(row.id))
            else:
                unresolved.append(
                    {
                        "memory_id": int(row.id),
                        "agent_id": row_agent_id or None,
                    }
                )

            preview.append(
                {
                    "memory_id": int(row.id),
                    "agent_id": row_agent_id or None,
                    "resolved_user_id": owner_user_id,
                    "timestamp": _safe_iso(row.timestamp),
                    "vector_status": row.vector_status,
                    "milvus_id": int(row.milvus_id) if row.milvus_id is not None else None,
                }
            )

    return {
        "filter_agent_id": filter_agent_id_str,
        "total_missing_user_id": total_missing,
        "scanned": len(rows),
        "resolvable_count": len(resolvable_ids),
        "unresolved_count": len(unresolved),
        "resolvable_ids": resolvable_ids,
        "unresolved": unresolved,
        "owner_by_agent_id": owner_by_agent_id,
        "preview": preview[:20],
    }


def _apply_user_id_updates(
    *,
    row_ids: List[int],
    owner_by_agent_id: Dict[str, str],
    reindex_vectors: bool,
) -> int:
    if not row_ids:
        return 0

    updated = 0
    with get_db_session() as session:
        rows = (
            session.query(MemoryRecord)
            .filter(MemoryRecord.id.in_(row_ids))
            .filter(MemoryRecord.memory_type == MemoryType.AGENT.value)
            .filter(MemoryRecord.is_deleted.is_(False))
            .all()
        )

        for row in rows:
            row_agent_id = str(row.agent_id) if row.agent_id else ""
            owner_user_id = owner_by_agent_id.get(row_agent_id)
            if not owner_user_id:
                continue

            row.user_id = owner_user_id
            metadata = row.memory_metadata if isinstance(row.memory_metadata, dict) else {}
            metadata = dict(metadata)
            metadata["user_id"] = owner_user_id
            row.memory_metadata = metadata

            if reindex_vectors:
                row.vector_status = "pending"
                row.vector_error = None
                row.vector_updated_at = None

            updated += 1

    return updated


def _reindex_rows(row_ids: List[int]) -> Dict[str, Any]:
    if not row_ids:
        return {"requested": 0, "reindexed": 0, "failed": 0, "failures": []}

    repo = get_memory_repository()
    memory_system = get_memory_system()

    reindexed = 0
    failed = 0
    failures: List[Dict[str, Any]] = []

    for memory_id in row_ids:
        record = repo.get(memory_id)
        if not record:
            failed += 1
            failures.append({"memory_id": int(memory_id), "error": "record_not_found"})
            continue

        if record.memory_type != MemoryType.AGENT:
            failed += 1
            failures.append({"memory_id": int(memory_id), "error": "memory_type_not_agent"})
            continue

        if record.milvus_id is not None:
            try:
                memory_system.delete_memory(record.milvus_id, record.memory_type)
            except Exception as exc:
                logger.warning(
                    "Failed deleting old vector for memory_id=%s milvus_id=%s: %s",
                    memory_id,
                    record.milvus_id,
                    exc,
                )
            repo.clear_milvus_link(memory_id)
            record = repo.get(memory_id)
            if not record:
                failed += 1
                failures.append({"memory_id": int(memory_id), "error": "record_missing_after_clear"})
                continue

        try:
            memory_item = MemoryItem(
                content=record.content,
                memory_type=record.memory_type,
                agent_id=record.agent_id,
                user_id=record.user_id,
                task_id=record.task_id,
                timestamp=record.timestamp,
                metadata=record.metadata,
            )
            milvus_id = int(memory_system._insert_into_milvus(memory_item))
            repo.mark_vector_synced(memory_id, milvus_id)
            reindexed += 1
        except Exception as exc:
            repo.mark_vector_failed(memory_id, str(exc))
            failed += 1
            failures.append({"memory_id": int(memory_id), "error": str(exc)})

    return {
        "requested": len(row_ids),
        "reindexed": reindexed,
        "failed": failed,
        "failures": failures[:50],
    }


def backfill_agent_memory_user_ids(
    *,
    dry_run: bool = True,
    agent_id: Optional[str] = None,
    limit: Optional[int] = None,
    reindex_vectors: bool = False,
) -> Dict[str, Any]:
    """Backfill missing user_id on agent memory rows using agent.owner_user_id mapping."""
    candidates = _collect_candidates(agent_id=agent_id, limit=limit)

    result: Dict[str, Any] = {
        "dry_run": bool(dry_run),
        "agent_id_filter": candidates.get("filter_agent_id"),
        "summary": {
            "total_missing_user_id": int(candidates.get("total_missing_user_id") or 0),
            "scanned": int(candidates.get("scanned") or 0),
            "resolvable": int(candidates.get("resolvable_count") or 0),
            "unresolved": int(candidates.get("unresolved_count") or 0),
            "updated": 0,
        },
        "preview": candidates.get("preview") or [],
        "unresolved": (candidates.get("unresolved") or [])[:50],
        "reindex": {
            "requested": bool(reindex_vectors and not dry_run),
            "requested_rows": int(candidates.get("resolvable_count") or 0)
            if (reindex_vectors and not dry_run)
            else 0,
            "reindexed": 0,
            "failed": 0,
            "failures": [],
        },
    }

    if dry_run:
        return result

    updated = _apply_user_id_updates(
        row_ids=list(candidates.get("resolvable_ids") or []),
        owner_by_agent_id=dict(candidates.get("owner_by_agent_id") or {}),
        reindex_vectors=reindex_vectors,
    )
    result["summary"]["updated"] = updated

    if reindex_vectors and updated > 0:
        reindex_result = _reindex_rows(list(candidates.get("resolvable_ids") or []))
        result["reindex"] = {
            "requested": True,
            "requested_rows": int(reindex_result.get("requested") or 0),
            "reindexed": int(reindex_result.get("reindexed") or 0),
            "failed": int(reindex_result.get("failed") or 0),
            "failures": reindex_result.get("failures") or [],
        }

    return result

