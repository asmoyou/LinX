"""Dedicated user-memory endpoints for the reset architecture."""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from access_control.permissions import CurrentUser, get_current_user
from user_memory.retriever import get_user_memory_retriever

from .memory_access import (
    _memory_item_to_response,
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
        )
    except Exception as exc:
        logger.error("Failed to list user memory: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list user memory: {exc}",
        ) from exc

    results = await asyncio.to_thread(lambda: [_memory_item_to_response(item) for item in results])
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
        )
    except Exception as exc:
        logger.error("Failed to list user memory profile: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list user memory profile: {exc}",
        ) from exc

    results = await asyncio.to_thread(lambda: [_memory_item_to_response(item) for item in results])
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
        )
    except Exception as exc:
        logger.error("Failed to list user memory episodes: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list user memory episodes: {exc}",
        ) from exc

    results = await asyncio.to_thread(lambda: [_memory_item_to_response(item) for item in results])
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
