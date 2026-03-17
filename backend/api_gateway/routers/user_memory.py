"""Dedicated user-memory endpoints for the reset architecture."""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from access_control.permissions import CurrentUser, get_current_user
from database.connection import get_db_session
from database.models import UserMemoryEntry, UserMemoryRelation, UserMemoryView
from user_memory.retriever import get_user_memory_retriever
from user_memory.session_ledger_repository import get_session_ledger_repository

from .memory_access import (
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


def _resolve_user_name(owner_id: str, current_user: CurrentUser) -> Optional[str]:
    if str(owner_id) == str(current_user.user_id):
        return str(current_user.username or "").strip() or None
    try:
        with get_db_session() as session:
            return _lookup_user_name(session, owner_id)
    except Exception:
        return str(current_user.username or "").strip() or None


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
    query_text: str = Query("*", alias="query"),
    user_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    min_score: Optional[float] = Query(None, alias="minScore", ge=0.0, le=1.0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List/search merged user memory facts and stable profile/episode views."""
    owner_id = str(user_id or current_user.user_id)
    await asyncio.to_thread(_require_user_memory_read_access_sync, owner_id, current_user)

    try:
        results = await asyncio.to_thread(
            get_user_memory_retriever().search_user_memory,
            user_id=owner_id,
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode="api_full",
            allow_reflection=True,
        )
    except Exception as exc:
        logger.error("Failed to list user memory: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list user memory: {exc}",
        ) from exc

    user_name = await asyncio.to_thread(_resolve_user_name, owner_id, current_user)
    results = await asyncio.to_thread(
        lambda: [_memory_item_to_response(item, user_name=user_name) for item in results]
    )
    return [MemoryItemResponse(**item) for item in results]


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
    memory_id: int,
    memory_source: str = Query(..., pattern=r"^(entry|user_memory_view)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Hide one user-memory record and its linked entry/view/relation surfaces."""
    deleted = await asyncio.to_thread(
        _delete_user_memory_record_sync,
        memory_id=int(memory_id),
        memory_source=memory_source,
        current_user=current_user,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User memory record not found",
        )
