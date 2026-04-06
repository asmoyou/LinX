"""Dedicated user-memory endpoints for the reset architecture."""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.params import Query as QueryParam
from sqlalchemy import and_, func

from access_control.permissions import CurrentUser, get_current_user
from database.connection import get_db_session
from database.models import User, UserMemoryEntry, UserMemoryRelation, UserMemoryView
from user_memory.items import RetrievedMemoryItem
from user_memory.retriever import get_user_memory_retriever
from user_memory.session_ledger_repository import get_session_ledger_repository

from .memory_access import (
    _is_admin_or_manager,
    _memory_item_to_response,
    _lookup_user_name,
    _require_user_memory_read_access_sync,
)
from .memory_contracts import (
    MemoryConfigResponse,
    MemoryConfigUpdateRequest,
    MemoryItemResponse,
)
from .memory_pipeline_config import (
    get_memory_config,
    update_memory_config,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _coerce_query_default(value: Any) -> Any:
    """Allow direct function calls in tests to pass through FastAPI Query defaults."""
    if isinstance(value, QueryParam):
        return value.default
    return value


def _resolve_user_name(owner_id: str, current_user: CurrentUser) -> Optional[str]:
    """Resolve display name, preferring display_name from User table."""
    fallback_name = str(current_user.username or '').strip() or None
    if str(owner_id) == str(current_user.user_id):
        return fallback_name
    try:
        with get_db_session() as session:
            return _lookup_user_name(session, owner_id) or fallback_name
    except Exception:
        return fallback_name


def _batch_resolve_user_names(user_ids: Set[str]) -> Dict[str, Optional[str]]:
    """Resolve display names for a set of user IDs in one query."""
    if not user_ids:
        return {}
    result: Dict[str, Optional[str]] = {uid: None for uid in user_ids}
    try:
        with get_db_session() as session:
            rows = session.query(User.user_id, User.username, User.attributes).filter(
                User.user_id.in_(list(user_ids))
            ).all()
            for row in rows:
                attrs = row.attributes or {}
                name = attrs.get("display_name") or row.username
                result[str(row.user_id)] = name
    except Exception:
        pass
    return result


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    """Parse ISO date string to timezone-aware datetime."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def _entry_to_item(row: Any) -> RetrievedMemoryItem:
    """Convert a UserMemoryEntry row to a RetrievedMemoryItem."""
    payload = row.entry_data if isinstance(row.entry_data, dict) else {}
    metadata: Dict[str, Any] = {
        "search_method": "direct",
        "search_methods": ["direct"],
        "memory_source": "entry",
        "record_type": "user_fact",
        "entry_id": row.id,
        "entry_key": row.entry_key,
        "fact_kind": row.fact_kind,
        "status": row.status,
        "importance": float(row.importance or 0.0),
        "confidence": float(row.confidence or 0.0),
    }
    for key in ("identity_signature", "canonical_statement", "event_time",
                "location", "topic", "persons", "entities"):
        if key in payload:
            metadata[key] = payload[key]
    vs = str(row.vector_sync_state or "").strip()
    if vs:
        metadata["vector_status"] = vs
    ve = str(row.vector_error or "").strip()
    if ve:
        metadata["vector_error"] = ve
    return RetrievedMemoryItem(
        id=f"entry_{row.id}",
        content=str(row.canonical_text or "").strip(),
        summary=str(row.summary or "").strip() or None,
        memory_type="user_memory",
        user_id=str(row.user_id),
        timestamp=row.updated_at or row.created_at,
        metadata=metadata,
        similarity_score=None,
    )


def _view_to_item(row: Any) -> RetrievedMemoryItem:
    """Convert a UserMemoryView row to a RetrievedMemoryItem."""
    payload = row.view_data if isinstance(row.view_data, dict) else {}
    metadata: Dict[str, Any] = {
        "search_method": "direct",
        "search_methods": ["direct"],
        "memory_source": "user_memory_view",
        "record_type": str(row.view_type or "view"),
        "view_id": row.id,
        "view_key": row.view_key,
        "view_type": row.view_type,
        "status": row.status,
        "importance": float(payload.get("importance") or 0.0),
        "confidence": float(payload.get("confidence") or 0.0),
    }
    for key in ("identity_signature", "canonical_statement", "event_time",
                "location", "topic"):
        if key in payload:
            metadata[key] = payload[key]
    vs = str(row.vector_sync_state or "").strip()
    if vs:
        metadata["vector_status"] = vs
    ve = str(row.vector_error or "").strip()
    if ve:
        metadata["vector_error"] = ve
    return RetrievedMemoryItem(
        id=f"view_{row.id}",
        content=str(row.content or row.title or "").strip(),
        summary=str(row.content or "").strip() or None,
        memory_type="user_memory",
        user_id=str(row.user_id),
        timestamp=row.updated_at or row.created_at,
        metadata=metadata,
        similarity_score=None,
    )


def _list_user_memory_filtered_sync(
    *,
    user_id: Optional[str],
    query_text: str,
    limit: int,
    offset: int,
    fact_kind: Optional[str],
    record_type: Optional[str],
    date_from: Optional[str],
    date_to: Optional[str],
    importance_min: Optional[float],
    importance_max: Optional[float],
    status_filter: Optional[str],
) -> tuple[List[RetrievedMemoryItem], int]:
    """Direct DB query with explicit filters, bypassing the LLM planner.

    Returns (items, total_count).
    """
    statuses = ["active"]
    if status_filter == "all":
        statuses = ["active", "superseded"]
    elif status_filter == "superseded":
        statuses = ["superseded"]

    fact_kinds = (
        [k.strip() for k in fact_kind.split(",") if k.strip()] if fact_kind else []
    )
    record_types = (
        [t.strip() for t in record_type.split(",") if t.strip()] if record_type else []
    )
    parsed_from = _parse_date(date_from)
    parsed_to = _parse_date(date_to)

    entry_types = {"user_fact", "user_relation"}
    view_types_set = {"user_profile", "episode"}
    want_entries = not record_types or bool(set(record_types) & entry_types)
    want_views = not record_types or bool(set(record_types) & view_types_set)

    results: List[RetrievedMemoryItem] = []

    def _apply_entry_filters(eq):
        if user_id:
            eq = eq.filter(UserMemoryEntry.user_id == str(user_id))
        if fact_kinds:
            eq = eq.filter(UserMemoryEntry.fact_kind.in_(fact_kinds))
        if parsed_from:
            eq = eq.filter(UserMemoryEntry.created_at >= parsed_from)
        if parsed_to:
            eq = eq.filter(UserMemoryEntry.created_at <= parsed_to)
        if importance_min is not None:
            eq = eq.filter(UserMemoryEntry.importance >= importance_min)
        if importance_max is not None:
            eq = eq.filter(UserMemoryEntry.importance <= importance_max)
        if query_text and query_text != "*":
            eq = eq.filter(UserMemoryEntry.search_vector.match(query_text))
        return eq

    def _apply_view_filters(vq):
        if user_id:
            vq = vq.filter(UserMemoryView.user_id == str(user_id))
        if record_types:
            view_filter = [t for t in record_types if t in view_types_set]
            if view_filter:
                vq = vq.filter(UserMemoryView.view_type.in_(view_filter))
        if parsed_from:
            vq = vq.filter(UserMemoryView.created_at >= parsed_from)
        if parsed_to:
            vq = vq.filter(UserMemoryView.created_at <= parsed_to)
        if importance_min is not None:
            vq = vq.filter(
                UserMemoryView.view_data["importance"].as_float() >= importance_min
            )
        if importance_max is not None:
            vq = vq.filter(
                UserMemoryView.view_data["importance"].as_float() <= importance_max
            )
        if query_text and query_text != "*":
            vq = vq.filter(UserMemoryView.search_vector.match(query_text))
        return vq

    with get_db_session() as session:
        # ── 1. Fetch views first (they are the preferred display surface) ──
        view_sigs: set[str] = set()
        view_items: List[RetrievedMemoryItem] = []

        if want_views:
            vq = session.query(UserMemoryView).filter(
                UserMemoryView.status.in_(statuses)
            )
            vq = _apply_view_filters(vq)
            vq = vq.order_by(
                UserMemoryView.updated_at.desc(), UserMemoryView.id.desc()
            )
            for row in vq.all():
                item = _view_to_item(row)
                view_items.append(item)
                sig = str(item.metadata.get("identity_signature") or "").strip()
                if sig:
                    view_sigs.add(sig)

        # ── 2. Fetch entries, skipping those already covered by a view ──
        entry_items: List[RetrievedMemoryItem] = []

        if want_entries:
            eq = session.query(UserMemoryEntry).filter(
                UserMemoryEntry.status.in_(statuses)
            )
            eq = _apply_entry_filters(eq)
            eq = eq.order_by(
                UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc()
            )
            for row in eq.all():
                item = _entry_to_item(row)
                sig = str(item.metadata.get("identity_signature") or "").strip()
                if sig and sig in view_sigs:
                    continue  # view already covers this fact
                entry_items.append(item)

    results = view_items + entry_items
    results.sort(
        key=lambda item: item.timestamp or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    total_count = len(results)
    return results[offset : offset + limit], total_count


def _mark_inactive_payload(payload: Dict[str, Any], *, reason: str) -> Dict[str, Any]:
    updated = dict(payload or {})
    updated["is_active"] = False
    updated["cleanup_reason"] = reason
    return updated


def _delete_user_memory_record_sync(
    *,
    memory_id: int,
    memory_source: str,
    current_user: CurrentUser,
) -> bool:
    normalized_source = str(memory_source or "").strip().lower()
    if normalized_source not in {"entry", "user_memory_view"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported memory source: {memory_source}",
        )

    repository = get_session_ledger_repository()
    owner_id: Optional[str] = None
    identity_signature: Optional[str] = None
    source_entry_id: Optional[int] = None
    target_entry_ids: set[int] = set()
    target_view_ids: set[int] = set()
    target_relation_ids: set[int] = set()

    with get_db_session() as session:
        if normalized_source == "entry":
            row = (
                session.query(UserMemoryEntry)
                .filter(UserMemoryEntry.id == int(memory_id))
                .one_or_none()
            )
            if row is None:
                return False
            owner_id = str(row.user_id)
            payload = dict(row.entry_data or {})
            identity_signature = str(payload.get("identity_signature") or "").strip() or None
            source_entry_id = int(row.id)
            target_entry_ids.add(int(row.id))
        else:
            row = (
                session.query(UserMemoryView)
                .filter(UserMemoryView.id == int(memory_id))
                .one_or_none()
            )
            if row is None:
                return False
            owner_id = str(row.user_id)
            payload = dict(row.view_data or {})
            identity_signature = str(payload.get("identity_signature") or "").strip() or None
            source_value = payload.get("source_entry_id")
            try:
                source_entry_id = int(source_value) if source_value is not None else None
            except (TypeError, ValueError):
                source_entry_id = None
            target_view_ids.add(int(row.id))

        _require_user_memory_read_access_sync(str(owner_id), current_user)

        entry_rows = (
            session.query(UserMemoryEntry)
            .filter(UserMemoryEntry.user_id == str(owner_id))
            .all()
        )
        for entry in entry_rows:
            entry_payload = dict(entry.entry_data or {})
            entry_signature = str(entry_payload.get("identity_signature") or "").strip()
            if identity_signature and entry_signature == identity_signature:
                target_entry_ids.add(int(entry.id))
                continue
            if source_entry_id is not None and int(entry.id) == int(source_entry_id):
                target_entry_ids.add(int(entry.id))

        view_rows = (
            session.query(UserMemoryView)
            .filter(UserMemoryView.user_id == str(owner_id))
            .all()
        )
        for view in view_rows:
            view_payload = dict(view.view_data or {})
            view_signature = str(view_payload.get("identity_signature") or "").strip()
            if identity_signature and view_signature == identity_signature:
                target_view_ids.add(int(view.id))
                continue
            try:
                candidate_source_entry_id = (
                    int(view_payload.get("source_entry_id"))
                    if view_payload.get("source_entry_id") is not None
                    else None
                )
            except (TypeError, ValueError):
                candidate_source_entry_id = None
            if source_entry_id is not None and candidate_source_entry_id == int(source_entry_id):
                target_view_ids.add(int(view.id))

        relation_rows = (
            session.query(UserMemoryRelation)
            .filter(UserMemoryRelation.user_id == str(owner_id))
            .all()
        )
        for relation in relation_rows:
            relation_payload = dict(relation.relation_data or {})
            relation_signature = str(relation_payload.get("identity_signature") or "").strip()
            if identity_signature and relation_signature == identity_signature:
                target_relation_ids.add(int(relation.id))
                continue
            relation_source_entry_id = getattr(relation, "source_entry_id", None)
            if source_entry_id is not None and relation_source_entry_id == int(source_entry_id):
                target_relation_ids.add(int(relation.id))

    for entry in entry_rows:
        if int(entry.id) not in target_entry_ids:
            continue
        repository.update_entry(
            int(entry.id),
            status="superseded",
            payload=_mark_inactive_payload(dict(entry.entry_data or {}), reason="manual_delete"),
        )

    for view in view_rows:
        if int(view.id) not in target_view_ids:
            continue
        repository.update_projection(
            int(view.id),
            status="superseded",
            payload=_mark_inactive_payload(dict(view.view_data or {}), reason="manual_delete"),
        )

    for relation in relation_rows:
        if int(relation.id) not in target_relation_ids:
            continue
        repository.update_relation(
            int(relation.id),
            status="superseded",
            payload=_mark_inactive_payload(
                dict(relation.relation_data or {}),
                reason="manual_delete",
            ),
        )

    return True


@router.get("", response_model=List[MemoryItemResponse])
async def list_user_memory(
    response: Response = Response(),
    query_text: str = Query("*", alias="query"),
    user_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    min_score: Optional[float] = Query(None, alias="minScore", ge=0.0, le=1.0),
    fact_kind: Optional[str] = Query(None, alias="fact_kind"),
    record_type: Optional[str] = Query(None, alias="record_type"),
    date_from: Optional[str] = Query(None, alias="date_from"),
    date_to: Optional[str] = Query(None, alias="date_to"),
    importance_min: Optional[float] = Query(
        None, alias="importance_min", ge=0.0, le=1.0
    ),
    importance_max: Optional[float] = Query(
        None, alias="importance_max", ge=0.0, le=1.0
    ),
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List/search merged user memory facts and stable profile/episode views.

    Admin/manager users can pass ``user_id=all`` to query across all users.
    Returns ``X-Total-Count`` header for pagination.
    """
    offset = int(_coerce_query_default(offset) or 0)
    fact_kind = _coerce_query_default(fact_kind)
    record_type = _coerce_query_default(record_type)
    date_from = _coerce_query_default(date_from)
    date_to = _coerce_query_default(date_to)
    importance_min = _coerce_query_default(importance_min)
    importance_max = _coerce_query_default(importance_max)
    status_filter = _coerce_query_default(status_filter)

    is_all_users = str(user_id or "").strip().lower() == "all"
    if is_all_users:
        if not _is_admin_or_manager(current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admin or manager can view all users' memories",
            )
        owner_id: Optional[str] = None
    else:
        owner_id = str(user_id or current_user.user_id)
        await asyncio.to_thread(
            _require_user_memory_read_access_sync, owner_id, current_user
        )

    use_retriever_search = (
        str(query_text or '').strip() not in {'', '*'}
        and offset == 0
        and fact_kind is None
        and record_type is None
        and date_from is None
        and date_to is None
        and importance_min is None
        and importance_max is None
        and status_filter is None
    )

    try:
        if use_retriever_search:
            results = await asyncio.to_thread(
                get_user_memory_retriever().search_user_memory,
                user_id=owner_id,
                query_text=query_text,
                limit=limit,
                min_score=min_score,
                planner_mode='api_full',
                allow_reflection=True,
            )
            total_count = len(results)
        else:
            results, total_count = await asyncio.to_thread(
                _list_user_memory_filtered_sync,
                user_id=owner_id,
                query_text=query_text,
                limit=limit,
                offset=offset,
                fact_kind=fact_kind,
                record_type=record_type,
                date_from=date_from,
                date_to=date_to,
                importance_min=importance_min,
                importance_max=importance_max,
                status_filter=status_filter,
            )
    except Exception as exc:
        logger.error("Failed to list user memory: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list user memory: {exc}",
        ) from exc

    if response is not None:
        response.headers["X-Total-Count"] = str(total_count)

    if is_all_users:
        all_user_ids = {str(item.user_id) for item in results if item.user_id}
        user_name_map = await asyncio.to_thread(
            _batch_resolve_user_names, all_user_ids
        )
        response_items = await asyncio.to_thread(
            lambda: [
                _memory_item_to_response(
                    item,
                    user_name=user_name_map.get(str(item.user_id)),
                )
                for item in results
            ]
        )
    else:
        user_name = await asyncio.to_thread(
            _resolve_user_name, str(owner_id), current_user
        )
        response_items = await asyncio.to_thread(
            lambda: [
                _memory_item_to_response(item, user_name=user_name)
                for item in results
            ]
        )
    return [MemoryItemResponse(**item) for item in response_items]


@router.get("/profile", response_model=List[MemoryItemResponse])
async def list_user_memory_profile(
    user_id: Optional[str] = Query(None),
    query_text: str = Query("*", alias="query"),
    limit: int = Query(20, ge=1, le=100),
    min_score: Optional[float] = Query(None, alias="minScore", ge=0.0, le=1.0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Read the stable user-profile projection only."""
    owner_id = str(user_id or current_user.user_id)
    await asyncio.to_thread(_require_user_memory_read_access_sync, owner_id, current_user)
    try:
        results = await asyncio.to_thread(
            get_user_memory_retriever().list_profile,
            user_id=owner_id,
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode="api_full",
            allow_reflection=True,
        )
    except Exception as exc:
        logger.error("Failed to list user memory profile: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list user memory profile: {exc}",
        ) from exc

    user_name = await asyncio.to_thread(_resolve_user_name, owner_id, current_user)
    results = await asyncio.to_thread(
        lambda: [_memory_item_to_response(item, user_name=user_name) for item in results]
    )
    return [MemoryItemResponse(**item) for item in results]


@router.get("/episodes", response_model=List[MemoryItemResponse])
async def list_user_memory_episodes(
    user_id: Optional[str] = Query(None),
    query_text: str = Query("*", alias="query"),
    limit: int = Query(20, ge=1, le=100),
    min_score: Optional[float] = Query(None, alias="minScore", ge=0.0, le=1.0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Read user episodic facts built from time-anchored events."""

    owner_id = str(user_id or current_user.user_id)
    await asyncio.to_thread(_require_user_memory_read_access_sync, owner_id, current_user)
    try:
        results = await asyncio.to_thread(
            get_user_memory_retriever().list_episodes,
            user_id=owner_id,
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode="api_full",
            allow_reflection=True,
        )
    except Exception as exc:
        logger.error("Failed to list user memory episodes: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list user memory episodes: {exc}",
        ) from exc

    user_name = await asyncio.to_thread(_resolve_user_name, owner_id, current_user)
    results = await asyncio.to_thread(
        lambda: [_memory_item_to_response(item, user_name=user_name) for item in results]
    )
    return [MemoryItemResponse(**item) for item in results]


@router.get("/config", response_model=MemoryConfigResponse)
async def get_user_memory_config(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Expose memory-pipeline config under the new product entry."""
    return await get_memory_config(current_user=current_user)


@router.put("/config", response_model=MemoryConfigResponse)
async def update_user_memory_config(
    request: MemoryConfigUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update memory-pipeline config under the new product entry."""
    return await update_memory_config(update_data=request, current_user=current_user)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user_memory(
    memory_id: Any,
    memory_source: str = Query(..., pattern=r"^(entry|user_memory_view)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Hide one user-memory record and its linked entry/view/relation surfaces."""
    # Accept both prefixed (entry_36, view_36) and plain numeric IDs
    raw_id = str(memory_id)
    for prefix in ("entry_", "view_"):
        if raw_id.startswith(prefix):
            raw_id = raw_id[len(prefix):]
            break
    try:
        numeric_id = int(raw_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory_id: {memory_id}",
        )
    deleted = await asyncio.to_thread(
        _delete_user_memory_record_sync,
        memory_id=numeric_id,
        memory_source=memory_source,
        current_user=current_user,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User memory record not found",
        )
