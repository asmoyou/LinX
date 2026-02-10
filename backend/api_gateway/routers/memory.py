"""Memory System API Endpoints.

Provides CRUD operations for memories, semantic search, and sharing.

All blocking operations (Milvus, embedding, PostgreSQL) are run via
asyncio.to_thread() to avoid blocking the FastAPI event loop.

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 6: Memory System Design
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# ─── Pydantic Schemas ───────────────────────────────────────────────────────


class MemoryCreate(BaseModel):
    """Create memory request."""

    type: str = Field(..., pattern=r"^(agent|company|user_context|task_context)$")
    content: str = Field(..., min_length=1)
    summary: Optional[str] = None
    agent_id: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class MemoryUpdate(BaseModel):
    """Update memory request."""

    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class MemorySearchRequest(BaseModel):
    """Search memories request."""

    query: str = Field(..., min_length=1)
    type: Optional[str] = Field(None, pattern=r"^(agent|company|user_context|task_context)$")
    limit: Optional[int] = Field(10, ge=1, le=100)
    filters: Optional[Dict[str, Any]] = None


class MemoryShareRequest(BaseModel):
    """Share memory request."""

    user_ids: List[str] = Field(..., min_length=1)


class MemoryResponse(BaseModel):
    """Memory response model."""

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    id: str
    type: str
    content: str
    summary: Optional[str] = None
    agent_id: Optional[str] = Field(None, alias="agentId")
    agent_name: Optional[str] = Field(None, alias="agentName")
    user_id: Optional[str] = Field(None, alias="userId")
    user_name: Optional[str] = Field(None, alias="userName")
    created_at: str = Field(..., alias="createdAt")
    tags: List[str] = []
    relevance_score: Optional[float] = Field(None, alias="relevanceScore")
    metadata: Optional[Dict[str, Any]] = None
    is_shared: bool = Field(False, alias="isShared")
    shared_with: List[str] = Field(default_factory=list, alias="sharedWith")


# ─── Helpers (all synchronous, called via asyncio.to_thread) ───────────────


def _memory_item_to_response(item, agent_name: Optional[str] = None,
                             user_name: Optional[str] = None) -> dict:
    """Convert a MemoryItem to a response dict."""
    meta = item.metadata or {}
    tags = meta.pop("tags", []) if meta else []
    summary = meta.pop("summary", None) if meta else None
    shared_with = meta.pop("shared_with", []) if meta else []
    is_shared = bool(meta.pop("shared_from", None)) if meta else False

    # Remove internal scoring fields
    meta.pop("_combined_score", None)
    meta.pop("_recency_score", None)

    return {
        "id": str(item.id) if item.id is not None else "",
        "type": item.memory_type.value if hasattr(item.memory_type, "value") else str(item.memory_type),
        "content": item.content,
        "summary": summary,
        "agentId": item.agent_id,
        "agentName": agent_name,
        "userId": item.user_id,
        "userName": user_name,
        "createdAt": item.timestamp.isoformat() if item.timestamp else datetime.utcnow().isoformat(),
        "tags": tags if isinstance(tags, list) else [],
        "relevanceScore": item.similarity_score,
        "metadata": meta if meta else None,
        "isShared": is_shared or bool(shared_with),
        "sharedWith": shared_with if isinstance(shared_with, list) else [],
    }


def _lookup_agent_name(session, agent_id: Optional[str]) -> Optional[str]:
    """Look up agent name by ID."""
    if not agent_id:
        return None
    from database.models import Agent

    agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
    return agent.name if agent else None


def _lookup_user_name(session, user_id: Optional[str]) -> Optional[str]:
    """Look up user display name by ID."""
    if not user_id:
        return None
    from database.models import User

    user = session.query(User).filter(User.user_id == user_id).first()
    if not user:
        return None
    attrs = user.attributes or {}
    return attrs.get("display_name") or user.username


def _items_to_responses(items) -> List[dict]:
    """Convert memory items to response dicts with name lookups. Runs in thread."""
    from database.connection import get_db_session

    with get_db_session() as session:
        results = []
        for item in items:
            agent_name = _lookup_agent_name(session, item.agent_id)
            user_name = _lookup_user_name(session, item.user_id)
            results.append(_memory_item_to_response(item, agent_name, user_name))
    return results


def _retrieve_memories_sync(query):
    """Retrieve memories synchronously (embedding + Milvus + DB lookups)."""
    from memory_system.memory_system import get_memory_system

    memory_system = get_memory_system()
    try:
        items = memory_system.retrieve_memories(query)
    except Exception as e:
        logger.error(f"Failed to retrieve memories: {e}")
        items = []
    return _items_to_responses(items)


def _retrieve_shared_sync(user_id: str):
    """Retrieve shared memories synchronously."""
    from memory_system.memory_interface import MemoryType, SearchQuery
    from memory_system.memory_system import get_memory_system

    memory_system = get_memory_system()
    query = SearchQuery(
        query_text="*",
        memory_type=MemoryType.COMPANY,
        user_id=user_id,
        top_k=100,
    )
    try:
        items = memory_system.retrieve_memories(query)
    except Exception:
        items = []

    shared_items = [
        item for item in items
        if item.metadata and item.metadata.get("shared_from")
    ]
    return _items_to_responses(shared_items)


def _store_memory_sync(memory_item):
    """Store a memory synchronously (embedding + Milvus insert)."""
    from memory_system.memory_system import get_memory_system

    memory_system = get_memory_system()
    memory_id = memory_system.store_memory(memory_item)
    memory_item.id = memory_id

    from database.connection import get_db_session

    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, memory_item.agent_id)
        user_name = _lookup_user_name(session, memory_item.user_id)

    return _memory_item_to_response(memory_item, agent_name, user_name)


def _detect_memory_type(memory_id: int) -> Optional[str]:
    """Search both Milvus collections to find which one contains the memory ID."""
    from memory_system.collections import CollectionName
    from memory_system.milvus_connection import get_milvus_connection

    milvus = get_milvus_connection()
    # Check agent_memories first
    try:
        collection = milvus.get_collection(CollectionName.AGENT_MEMORIES)
        results = collection.query(expr=f"id == {memory_id}", output_fields=["id"])
        if results:
            return "agent"
    except Exception:
        pass

    # Check company_memories
    try:
        collection = milvus.get_collection(CollectionName.COMPANY_MEMORIES)
        results = collection.query(expr=f"id == {memory_id}", output_fields=["id"])
        if results:
            # Determine actual type from memory_type field
            full = collection.query(
                expr=f"id == {memory_id}", output_fields=["memory_type"]
            )
            if full and full[0].get("memory_type"):
                return full[0]["memory_type"]
            return "company"
    except Exception:
        pass

    return None


def _get_memory_by_id_sync(memory_id: int, type_str: Optional[str] = None):
    """Get a single memory by Milvus ID synchronously."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryItem, MemoryType
    from memory_system.milvus_connection import get_milvus_connection

    if not type_str:
        type_str = _detect_memory_type(memory_id)
        if not type_str:
            return None

    mem_type = MemoryType(type_str)

    if mem_type == MemoryType.AGENT:
        collection_name = CollectionName.AGENT_MEMORIES
        output_fields = ["agent_id", "content", "timestamp", "metadata"]
    else:
        collection_name = CollectionName.COMPANY_MEMORIES
        output_fields = ["user_id", "content", "memory_type", "timestamp", "metadata"]

    milvus = get_milvus_connection()
    collection = milvus.get_collection(collection_name)

    results = collection.query(
        expr=f"id == {memory_id}",
        output_fields=output_fields,
    )

    if not results:
        return None

    row = results[0]
    timestamp = datetime.fromtimestamp(row["timestamp"] / 1000.0) if row.get("timestamp") else None

    item = MemoryItem(
        id=row.get("id", memory_id),
        content=row["content"],
        memory_type=mem_type,
        agent_id=row.get("agent_id"),
        user_id=row.get("user_id"),
        timestamp=timestamp,
        metadata=row.get("metadata"),
    )

    from database.connection import get_db_session

    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, item.agent_id)
        user_name = _lookup_user_name(session, item.user_id)

    return _memory_item_to_response(item, agent_name, user_name)


def _delete_memory_sync(memory_id: int, type_str: Optional[str] = None) -> bool:
    """Delete a memory synchronously."""
    from memory_system.memory_interface import MemoryType
    from memory_system.memory_system import get_memory_system

    if not type_str:
        type_str = _detect_memory_type(memory_id)
        if not type_str:
            return False

    mem_type = MemoryType(type_str)
    memory_system = get_memory_system()
    return memory_system.delete_memory(memory_id, mem_type)


def _update_memory_sync(memory_id: int, type_str: Optional[str], request: MemoryUpdate,
                        user_id: str):
    """Update a memory synchronously (fetch, delete, re-insert)."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryItem, MemoryType
    from memory_system.memory_system import get_memory_system
    from memory_system.milvus_connection import get_milvus_connection

    if not type_str:
        type_str = _detect_memory_type(memory_id)
        if not type_str:
            return None

    mem_type = MemoryType(type_str)
    memory_system = get_memory_system()

    if mem_type == MemoryType.AGENT:
        collection_name = CollectionName.AGENT_MEMORIES
        output_fields = ["agent_id", "content", "timestamp", "metadata"]
    else:
        collection_name = CollectionName.COMPANY_MEMORIES
        output_fields = ["user_id", "content", "memory_type", "timestamp", "metadata"]

    milvus = get_milvus_connection()
    collection = milvus.get_collection(collection_name)

    results = collection.query(
        expr=f"id == {memory_id}",
        output_fields=output_fields,
    )

    if not results:
        return None

    row = results[0]

    memory_system.delete_memory(memory_id, mem_type)

    old_meta = row.get("metadata") or {}
    new_meta = old_meta.copy()
    if request.tags is not None:
        new_meta["tags"] = request.tags
    if request.summary is not None:
        new_meta["summary"] = request.summary
    if request.metadata is not None:
        new_meta.update(request.metadata)

    new_content = request.content if request.content else row["content"]

    new_item = MemoryItem(
        content=new_content,
        memory_type=mem_type,
        agent_id=row.get("agent_id"),
        user_id=row.get("user_id", user_id),
        metadata=new_meta,
    )

    new_id = memory_system.store_memory(new_item)
    new_item.id = new_id

    from database.connection import get_db_session

    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, new_item.agent_id)
        user_name = _lookup_user_name(session, new_item.user_id)

    return _memory_item_to_response(new_item, agent_name, user_name)


def _share_memory_sync(memory_id: int, type_str: Optional[str], user_ids: List[str]):
    """Share a memory synchronously."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryItem, MemoryType
    from memory_system.memory_system import get_memory_system
    from memory_system.milvus_connection import get_milvus_connection

    if not type_str:
        type_str = _detect_memory_type(memory_id)
        if not type_str:
            return None

    mem_type = MemoryType(type_str)
    memory_system = get_memory_system()

    success = memory_system.share_memory(memory_id, mem_type, user_ids)
    if not success:
        return None

    # Re-fetch to return updated data
    if mem_type == MemoryType.AGENT:
        collection_name = CollectionName.AGENT_MEMORIES
        output_fields = ["agent_id", "content", "timestamp", "metadata"]
    else:
        collection_name = CollectionName.COMPANY_MEMORIES
        output_fields = ["user_id", "content", "memory_type", "timestamp", "metadata"]

    milvus = get_milvus_connection()
    collection = milvus.get_collection(collection_name)

    results = collection.query(
        expr=f"id == {memory_id}",
        output_fields=output_fields,
    )

    if not results:
        return {
            "id": str(memory_id),
            "type": type_str,
            "content": "",
            "createdAt": datetime.utcnow().isoformat(),
            "tags": [],
            "isShared": True,
            "sharedWith": user_ids,
        }

    row = results[0]
    timestamp = datetime.fromtimestamp(row["timestamp"] / 1000.0) if row.get("timestamp") else None

    item = MemoryItem(
        id=memory_id,
        content=row["content"],
        memory_type=mem_type,
        agent_id=row.get("agent_id"),
        user_id=row.get("user_id"),
        timestamp=timestamp,
        metadata=row.get("metadata"),
    )

    if not item.metadata:
        item.metadata = {}
    item.metadata["shared_with"] = user_ids

    from database.connection import get_db_session

    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, item.agent_id)
        user_name = _lookup_user_name(session, item.user_id)

    return _memory_item_to_response(item, agent_name, user_name)


def _purge_memories_sync(memory_type: str, agent_id: Optional[str]):
    """Purge memories synchronously."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryType
    from memory_system.milvus_connection import get_milvus_connection

    mem_type = MemoryType(memory_type)

    if mem_type == MemoryType.AGENT:
        collection_name = CollectionName.AGENT_MEMORIES
        if agent_id:
            expr = f'agent_id == "{agent_id}"'
        else:
            expr = "id >= 0"
    else:
        collection_name = CollectionName.COMPANY_MEMORIES
        if agent_id:
            expr = f'memory_type == "{memory_type}" && agent_id == "{agent_id}"'
        else:
            expr = f'memory_type == "{memory_type}"'

    milvus = get_milvus_connection()
    collection = milvus.get_collection(collection_name)

    try:
        existing = collection.query(expr=expr, output_fields=["id"])
        count = len(existing)
    except Exception:
        count = 0

    if count == 0:
        return {"deleted": 0, "type": memory_type, "message": "No memories found to purge"}

    ids = [row["id"] for row in existing]
    collection.delete(expr=f"id in {ids}")

    return {"deleted": count, "type": memory_type, "message": f"Purged {count} memories"}


# ─── Endpoints (all use asyncio.to_thread for blocking ops) ────────────────


@router.get("", response_model=List[MemoryResponse])
async def list_memories(
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
    agent_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, alias="dateFrom"),
    date_to: Optional[str] = Query(None, alias="dateTo"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List memories with optional filters."""
    from memory_system.memory_interface import MemoryType, SearchQuery

    memory_type = MemoryType(type) if type else None
    effective_user_id = user_id or current_user.user_id

    query = SearchQuery(
        query_text="*",
        memory_type=memory_type,
        agent_id=agent_id,
        user_id=effective_user_id,
        top_k=100,
    )

    results = await asyncio.to_thread(_retrieve_memories_sync, query)
    return [MemoryResponse(**r) for r in results]


@router.get("/stats")
async def get_memory_stats(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get memory system statistics."""
    from memory_system.memory_system import get_memory_system

    memory_system = get_memory_system()
    stats = await asyncio.to_thread(memory_system.get_memory_stats)
    return stats


@router.get("/shared", response_model=List[MemoryResponse])
async def get_shared_memories(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get memories shared with the current user."""
    results = await asyncio.to_thread(_retrieve_shared_sync, current_user.user_id)
    return [MemoryResponse(**r) for r in results]


@router.get("/type/{memory_type}", response_model=List[MemoryResponse])
async def get_memories_by_type(
    memory_type: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get memories filtered by type."""
    from memory_system.memory_interface import MemoryType, SearchQuery

    try:
        mem_type = MemoryType(memory_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory type: {memory_type}",
        )

    query = SearchQuery(
        query_text="*",
        memory_type=mem_type,
        user_id=current_user.user_id if mem_type != MemoryType.AGENT else None,
        top_k=100,
    )

    results = await asyncio.to_thread(_retrieve_memories_sync, query)
    return [MemoryResponse(**r) for r in results]


@router.get("/agent/{agent_id}", response_model=List[MemoryResponse])
async def get_memories_by_agent(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get memories for a specific agent."""
    from memory_system.memory_interface import MemoryType, SearchQuery

    query = SearchQuery(
        query_text="*",
        memory_type=MemoryType.AGENT,
        agent_id=agent_id,
        top_k=100,
    )

    results = await asyncio.to_thread(_retrieve_memories_sync, query)
    return [MemoryResponse(**r) for r in results]


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: int,
    type: Optional[str] = Query(
        None, pattern=r"^(agent|company|user_context|task_context)$"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a single memory by Milvus ID. Type is auto-detected if not provided."""
    result = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, type)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    return MemoryResponse(**result)


@router.post("", response_model=MemoryResponse, status_code=status.HTTP_201_CREATED)
async def create_memory(
    request: MemoryCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new memory."""
    from memory_system.memory_interface import MemoryItem, MemoryType

    mem_type = MemoryType(request.type)

    meta = request.metadata or {}
    if request.tags:
        meta["tags"] = request.tags
    if request.summary:
        meta["summary"] = request.summary

    memory_item = MemoryItem(
        content=request.content,
        memory_type=mem_type,
        agent_id=request.agent_id,
        user_id=current_user.user_id,
        metadata=meta,
    )

    try:
        result = await asyncio.to_thread(_store_memory_sync, memory_item)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )

    logger.info(
        "Memory created",
        extra={"type": request.type},
    )

    return MemoryResponse(**result)


@router.post("/search", response_model=List[MemoryResponse])
async def search_memories(
    request: MemorySearchRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Semantic search across memories."""
    from memory_system.memory_interface import MemoryType, SearchQuery

    memory_type = MemoryType(request.type) if request.type else None

    query = SearchQuery(
        query_text=request.query,
        memory_type=memory_type,
        user_id=current_user.user_id,
        top_k=request.limit or 10,
    )

    try:
        results = await asyncio.to_thread(_retrieve_memories_sync, query)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return [MemoryResponse(**r) for r in results]


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: int,
    request: MemoryUpdate,
    type: Optional[str] = Query(
        None, pattern=r"^(agent|company|user_context|task_context)$"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a memory (delete + re-insert in Milvus). Type is auto-detected if not provided."""
    try:
        result = await asyncio.to_thread(
            _update_memory_sync, memory_id, type, request, current_user.user_id
        )
    except (ValueError, RuntimeError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update memory: {e}",
        )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    logger.info(
        "Memory updated",
        extra={"memory_id": memory_id, "type": type},
    )

    return MemoryResponse(**result)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: int,
    type: Optional[str] = Query(
        None, pattern=r"^(agent|company|user_context|task_context)$"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a memory by Milvus ID. Type is auto-detected if not provided."""
    success = await asyncio.to_thread(_delete_memory_sync, memory_id, type)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found or deletion failed",
        )

    logger.info(
        "Memory deleted",
        extra={"memory_id": memory_id, "type": type},
    )


@router.post("/{memory_id}/share", response_model=MemoryResponse)
async def share_memory(
    memory_id: int,
    request: MemoryShareRequest,
    type: Optional[str] = Query(
        None, pattern=r"^(agent|company|user_context|task_context)$"
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Share a memory with specific users."""
    result = await asyncio.to_thread(
        _share_memory_sync, memory_id, type, request.user_ids
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found or sharing failed",
        )

    logger.info(
        "Memory shared",
        extra={"memory_id": memory_id, "shared_with": request.user_ids},
    )

    return MemoryResponse(**result)


@router.delete("/purge/{memory_type}", status_code=status.HTTP_200_OK)
async def purge_memories(
    memory_type: str,
    agent_id: Optional[str] = Query(None, description="Only purge memories for this agent"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Purge (delete all) memories of a given type. Optionally filter by agent_id."""
    from memory_system.memory_interface import MemoryType

    try:
        MemoryType(memory_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory type: {memory_type}",
        )

    try:
        result = await asyncio.to_thread(_purge_memories_sync, memory_type, agent_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Purge failed: {e}",
        )

    logger.info(
        f"Purged memories",
        extra={"type": memory_type, "agent_id": agent_id, "result": result},
    )

    return result
