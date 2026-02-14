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
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from shared.config import get_config

logger = logging.getLogger(__name__)
router = APIRouter()


_COLLECTION_RETRY_ATTEMPTS = 3
_COLLECTION_RETRY_DELAY_SECONDS = 0.35


class CollectionLoadingError(RuntimeError):
    """Raised when Milvus collection remains unavailable after retries."""


def _iter_exception_chain(exc: Exception):
    """Yield exception + nested causes/contexts."""
    current = exc
    seen = set()
    while current and id(current) not in seen:
        seen.add(id(current))
        yield current
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__context__ is not None:
            current = current.__context__
        else:
            current = None


def _is_collection_not_loaded_error(exc: Exception) -> bool:
    """Detect Milvus transient error when collection has not finished loading."""
    for current in _iter_exception_chain(exc):
        code = getattr(current, "code", None)
        if code == 101:
            return True
        message = str(current).lower()
        if "collection not loaded" in message:
            return True
        if "not loaded" in message and "collection" in message:
            return True
    return False


def _query_collection_with_retry(
    milvus,
    collection_name: str,
    operation: Callable[[Any], Any],
):
    """Run a Milvus operation with short retries for transient load-state failures."""
    last_error: Optional[Exception] = None
    for attempt in range(1, _COLLECTION_RETRY_ATTEMPTS + 1):
        collection = milvus.get_collection(collection_name)
        try:
            return operation(collection)
        except Exception as exc:
            if not _is_collection_not_loaded_error(exc):
                raise
            last_error = exc
            try:
                collection.load(timeout=1.0, _async=True)
            except Exception as load_exc:
                logger.debug(
                    "Failed to trigger async load after query failure: %s",
                    load_exc,
                )
            if attempt < _COLLECTION_RETRY_ATTEMPTS:
                delay = _COLLECTION_RETRY_DELAY_SECONDS * attempt
                logger.warning(
                    "Collection '%s' not loaded yet (attempt %d/%d), retrying in %.2fs",
                    collection_name,
                    attempt,
                    _COLLECTION_RETRY_ATTEMPTS,
                    delay,
                )
                time.sleep(delay)

    raise CollectionLoadingError(
        f"Memory collection '{collection_name}' is still loading. Please retry shortly."
    ) from last_error


def _build_memory_filter_expression(collection_name: str, query) -> Optional[str]:
    """Build Milvus filter expression for direct query mode."""
    from memory_system.collections import CollectionName

    filters = []
    if collection_name == CollectionName.AGENT_MEMORIES:
        if query.agent_id:
            filters.append(f'agent_id == "{query.agent_id}"')
        if query.user_id:
            filters.append(f'metadata["user_id"] == "{query.user_id}"')
    else:
        if query.user_id:
            filters.append(f'user_id == "{query.user_id}"')
        if query.memory_type:
            filters.append(f'memory_type == "{query.memory_type.value}"')
        if query.task_id:
            filters.append(f'metadata["task_id"] == "{query.task_id}"')
    return " && ".join(filters) if filters else None


def _determine_memory_collections(query) -> List[str]:
    """Determine target collections without invoking embedding pipeline."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryType

    collections = []
    if query.memory_type == MemoryType.AGENT:
        collections.append(CollectionName.AGENT_MEMORIES)
    elif query.memory_type in [
        MemoryType.COMPANY,
        MemoryType.USER_CONTEXT,
        MemoryType.TASK_CONTEXT,
    ]:
        collections.append(CollectionName.COMPANY_MEMORIES)
    else:
        if query.agent_id:
            collections.append(CollectionName.AGENT_MEMORIES)
        if query.user_id:
            collections.append(CollectionName.COMPANY_MEMORIES)
        if not query.agent_id and not query.user_id:
            collections.extend([CollectionName.AGENT_MEMORIES, CollectionName.COMPANY_MEMORIES])

    return collections


def _get_memory_repository():
    """Lazy-load memory repository to avoid import side effects at module load."""
    from memory_system.memory_repository import get_memory_repository

    return get_memory_repository()


def _sync_record_to_milvus_sync(memory_id: int):
    """Best-effort vector sync from PostgreSQL source-of-truth into Milvus index."""
    from memory_system.memory_interface import MemoryItem
    from memory_system.memory_system import get_memory_system

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if not record:
        return None

    memory_system = get_memory_system()

    # Replace stale vector row when re-indexing an existing record.
    if record.milvus_id is not None:
        try:
            memory_system.delete_memory(record.milvus_id, record.memory_type)
        except Exception as exc:
            logger.warning("Failed deleting stale vector row for memory %s: %s", memory_id, exc)
        repo.clear_milvus_link(record.id)
        record = repo.get(memory_id)
        if not record:
            return None

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
        return repo.mark_vector_synced(memory_id, milvus_id)
    except Exception as exc:
        repo.mark_vector_failed(memory_id, str(exc))
        logger.warning("Vector sync failed for memory %s: %s", memory_id, exc)
        return repo.get(memory_id)


def _list_memories_from_db_sync(query) -> List[dict]:
    """Wildcard list path backed by PostgreSQL source-of-truth."""
    repo = _get_memory_repository()
    rows = repo.list_memories(
        memory_type=query.memory_type,
        agent_id=query.agent_id,
        user_id=query.user_id,
        task_id=query.task_id,
        limit=query.top_k or 100,
    )
    items = [row.to_memory_item() for row in rows]
    return _items_to_responses(items)


def _list_memories_from_milvus_sync(query) -> List[dict]:
    """Legacy fallback path for wildcard list queries using Milvus only."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryItem, MemoryType
    from memory_system.milvus_connection import get_milvus_connection

    milvus = get_milvus_connection()
    collections_to_search = _determine_memory_collections(query)

    items = []
    loading_errors = []
    for collection_name in collections_to_search:
        expr = _build_memory_filter_expression(collection_name, query)
        query_expr = expr if expr else "id >= 0"

        try:
            if collection_name == CollectionName.AGENT_MEMORIES:
                rows = _query_collection_with_retry(
                    milvus,
                    collection_name,
                    lambda col: col.query(
                        expr=query_expr,
                        output_fields=["id", "agent_id", "content", "timestamp", "metadata"],
                        limit=query.top_k or 100,
                    ),
                )
                for row in rows:
                    timestamp_ms = row.get("timestamp")
                    timestamp = (
                        datetime.fromtimestamp(timestamp_ms / 1000.0)
                        if timestamp_ms
                        else datetime.utcnow()
                    )
                    items.append(
                        MemoryItem(
                            id=row.get("id"),
                            content=row.get("content", ""),
                            memory_type=MemoryType.AGENT,
                            agent_id=row.get("agent_id"),
                            metadata=row.get("metadata") or {},
                            timestamp=timestamp,
                            similarity_score=None,
                        )
                    )
            else:
                rows = _query_collection_with_retry(
                    milvus,
                    collection_name,
                    lambda col: col.query(
                        expr=query_expr,
                        output_fields=[
                            "id",
                            "user_id",
                            "content",
                            "memory_type",
                            "timestamp",
                            "metadata",
                        ],
                        limit=query.top_k or 100,
                    ),
                )
                for row in rows:
                    timestamp_ms = row.get("timestamp")
                    timestamp = (
                        datetime.fromtimestamp(timestamp_ms / 1000.0)
                        if timestamp_ms
                        else datetime.utcnow()
                    )
                    memory_type_str = row.get("memory_type", "company")
                    try:
                        memory_type = MemoryType(memory_type_str)
                    except ValueError:
                        memory_type = MemoryType.COMPANY
                    items.append(
                        MemoryItem(
                            id=row.get("id"),
                            content=row.get("content", ""),
                            memory_type=memory_type,
                            user_id=row.get("user_id"),
                            metadata=row.get("metadata") or {},
                            timestamp=timestamp,
                            similarity_score=None,
                        )
                    )
        except CollectionLoadingError as e:
            loading_errors.append((collection_name, str(e)))
            logger.warning("Skipping loading collection during list: %s", collection_name)
            continue

    # Match previous semantics: latest first, then apply top_k.
    if loading_errors and not items:
        logger.warning(
            "All target memory collections unavailable during wildcard list, returning empty result"
        )

    items.sort(key=lambda x: x.timestamp or datetime.utcnow(), reverse=True)
    top_k = query.top_k or 100
    return _items_to_responses(items[:top_k])


def _list_memories_without_embedding_sync(query) -> List[dict]:
    """Wildcard list path with DB-first and Milvus fallback."""
    try:
        return _list_memories_from_db_sync(query)
    except Exception as db_exc:
        logger.warning("DB list path failed, fallback to Milvus: %s", db_exc)
        return _list_memories_from_milvus_sync(query)


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
    min_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    filters: Optional[Dict[str, Any]] = None


class MemoryShareRequest(BaseModel):
    """Share memory request."""

    user_ids: List[str] = Field(default_factory=list)
    agent_ids: List[str] = Field(default_factory=list)


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
    shared_with_names: List[str] = Field(default_factory=list, alias="sharedWithNames")
    index_status: Optional[str] = Field(None, alias="indexStatus")
    index_error: Optional[str] = Field(None, alias="indexError")


class MemoryIndexInspectResponse(BaseModel):
    """Detailed vector index inspection response."""

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    memory_id: str = Field(..., alias="memoryId")
    milvus_id: Optional[int] = Field(None, alias="milvusId")
    collection: Optional[str] = None
    vector_status: Optional[str] = Field(None, alias="vectorStatus")
    vector_error: Optional[str] = Field(None, alias="vectorError")
    vector_updated_at: Optional[str] = Field(None, alias="vectorUpdatedAt")
    exists_in_milvus: bool = Field(False, alias="existsInMilvus")
    indexed_content: Optional[str] = Field(None, alias="indexedContent")
    indexed_timestamp: Optional[str] = Field(None, alias="indexedTimestamp")
    indexed_metadata: Optional[Dict[str, Any]] = Field(None, alias="indexedMetadata")
    embedding_dimension: Optional[int] = Field(None, alias="embeddingDimension")
    embedding_preview: Optional[List[float]] = Field(None, alias="embeddingPreview")
    milvus_error: Optional[str] = Field(None, alias="milvusError")


class MemoryConfigResponse(BaseModel):
    """Memory retrieval and embedding configuration."""

    embedding: dict
    retrieval: dict
    runtime: dict
    recommended: Optional[dict] = None


class MemoryConfigUpdateRequest(BaseModel):
    """Request to update memory retrieval configuration."""

    embedding: Optional[dict] = None
    retrieval: Optional[dict] = None
    runtime: Optional[dict] = None


_MEMORY_RUNTIME_KEYS = (
    "collection_retry_attempts",
    "collection_retry_delay_seconds",
    "search_timeout_seconds",
    "delete_timeout_seconds",
)


_MEMORY_RECOMMENDED_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "embedding": {
        "provider": "",
        "model": "",
        "dimension": 1024,
        "inherit_from_knowledge_base": True,
    },
    "retrieval": {
        "top_k": 10,
        "similarity_threshold": 0.0,
        "similarity_weight": 0.7,
        "recency_weight": 0.3,
        "enable_reranking": True,
        "rerank_weight": 0.75,
        "rerank_provider": "",
        "rerank_model": "",
        "rerank_top_k": 30,
        "rerank_timeout_seconds": 8,
        "rerank_failure_backoff_seconds": 30,
        "rerank_doc_max_chars": 1200,
    },
    "runtime": {
        "collection_retry_attempts": 3,
        "collection_retry_delay_seconds": 0.35,
        "search_timeout_seconds": 2.0,
        "delete_timeout_seconds": 2.0,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_memory_config_payload(memory_section: dict, kb_section: Optional[dict] = None) -> dict:
    """Build memory config payload with effective resolved settings and source hints."""
    from memory_system.embedding_service import resolve_embedding_settings

    kb_section = kb_section if isinstance(kb_section, dict) else {}
    kb_search = kb_section.get("search", {}) if isinstance(kb_section.get("search"), dict) else {}

    embedding_cfg = (
        memory_section.get("embedding", {})
        if isinstance(memory_section.get("embedding"), dict)
        else {}
    )
    retrieval_cfg = (
        memory_section.get("retrieval", {})
        if isinstance(memory_section.get("retrieval"), dict)
        else {}
    )
    runtime_cfg = (
        memory_section.get("runtime", {})
        if isinstance(memory_section.get("runtime"), dict)
        else {}
    )

    embedding_merged = _deep_merge(_MEMORY_RECOMMENDED_DEFAULTS["embedding"], embedding_cfg)
    retrieval_merged = _deep_merge(_MEMORY_RECOMMENDED_DEFAULTS["retrieval"], retrieval_cfg)
    runtime_merged = _deep_merge(_MEMORY_RECOMMENDED_DEFAULTS["runtime"], runtime_cfg)
    for key in _MEMORY_RUNTIME_KEYS:
        if key in memory_section:
            runtime_merged[key] = memory_section.get(key)

    effective_embedding = resolve_embedding_settings(scope="memory")
    effective_rerank_provider = (
        str(retrieval_cfg.get("rerank_provider") or "").strip()
        or str(kb_search.get("rerank_provider") or "").strip()
    )
    effective_rerank_model = (
        str(retrieval_cfg.get("rerank_model") or "").strip()
        or str(kb_search.get("rerank_model") or "").strip()
    )
    rerank_provider_source = (
        "memory.retrieval.rerank_provider"
        if str(retrieval_cfg.get("rerank_provider") or "").strip()
        else (
            "knowledge_base.search.rerank_provider"
            if str(kb_search.get("rerank_provider") or "").strip()
            else "none"
        )
    )
    rerank_model_source = (
        "memory.retrieval.rerank_model"
        if str(retrieval_cfg.get("rerank_model") or "").strip()
        else (
            "knowledge_base.search.rerank_model"
            if str(kb_search.get("rerank_model") or "").strip()
            else "none"
        )
    )

    retrieval_effective = {
        **retrieval_merged,
        "rerank_provider": effective_rerank_provider,
        "rerank_model": effective_rerank_model,
        "sources": {
            "rerank_provider": rerank_provider_source,
            "rerank_model": rerank_model_source,
        },
    }

    embedding_payload = {
        **embedding_merged,
        "effective": {
            "provider": effective_embedding.get("provider"),
            "model": effective_embedding.get("model"),
            "dimension": effective_embedding.get("dimension"),
        },
        "sources": {
            "provider": effective_embedding.get("provider_source"),
            "model": effective_embedding.get("model_source"),
            "dimension": effective_embedding.get("dimension_source"),
        },
    }

    return {
        "embedding": embedding_payload,
        "retrieval": retrieval_effective,
        "runtime": runtime_merged,
        "recommended": _MEMORY_RECOMMENDED_DEFAULTS,
    }


# ─── Helpers (all synchronous, called via asyncio.to_thread) ───────────────


def _memory_item_to_response(
    item,
    agent_name: Optional[str] = None,
    user_name: Optional[str] = None,
    shared_with_names: Optional[List[str]] = None,
) -> dict:
    """Convert a MemoryItem to a response dict."""
    meta = dict(item.metadata or {})
    tags = meta.pop("tags", [])
    summary = meta.pop("summary", None)
    shared_with = meta.get("shared_with", [])
    stored_shared_names = meta.get("shared_with_names", [])
    shared_from = meta.get("shared_from", None)
    index_status = meta.pop("vector_status", None)
    index_error = meta.pop("vector_error", None)

    if not isinstance(shared_with, list):
        shared_with = []

    if shared_with_names is not None:
        final_shared_names = shared_with_names
    elif isinstance(stored_shared_names, list):
        final_shared_names = stored_shared_names
    else:
        final_shared_names = []

    # Remove internal scoring fields
    meta.pop("_combined_score", None)
    meta.pop("_recency_score", None)
    meta.pop("_rerank_score", None)
    meta.pop("_rerank_blended_score", None)
    meta.pop("_rerank_provider", None)
    meta.pop("_rerank_model", None)

    return {
        "id": str(item.id) if item.id is not None else "",
        "type": (
            item.memory_type.value if hasattr(item.memory_type, "value") else str(item.memory_type)
        ),
        "content": item.content,
        "summary": summary,
        "agentId": item.agent_id,
        "agentName": agent_name,
        "userId": item.user_id,
        "userName": user_name,
        "createdAt": (
            item.timestamp.isoformat() if item.timestamp else datetime.utcnow().isoformat()
        ),
        "tags": tags if isinstance(tags, list) else [],
        "relevanceScore": item.similarity_score,
        "metadata": meta if meta else None,
        "isShared": bool(shared_from) or bool(shared_with),
        "sharedWith": shared_with,
        "sharedWithNames": final_shared_names,
        "indexStatus": index_status,
        "indexError": index_error,
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


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    """Deduplicate while keeping first-seen order."""
    seen = set()
    result = []
    for value in values:
        key = str(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _resolve_share_targets(agent_ids: List[str], user_ids: List[str]) -> Dict[str, List[str]]:
    """Resolve share targets into user IDs and human-readable names."""
    from uuid import UUID

    from database.connection import get_db_session
    from database.models import Agent

    normalized_agent_ids = _dedupe_preserve_order([str(v) for v in (agent_ids or []) if str(v)])
    normalized_user_ids = _dedupe_preserve_order([str(v) for v in (user_ids or []) if str(v)])

    target_user_ids: List[str] = []
    target_entity_ids: List[str] = []
    target_entity_names: List[str] = []

    with get_db_session() as session:
        if normalized_agent_ids:
            parsed_agent_ids = []
            for raw_agent_id in normalized_agent_ids:
                try:
                    parsed_agent_ids.append(UUID(raw_agent_id))
                except Exception:
                    continue

            agent_rows = []
            if parsed_agent_ids:
                agent_rows = session.query(Agent).filter(Agent.agent_id.in_(parsed_agent_ids)).all()
            rows_by_id = {str(row.agent_id): row for row in agent_rows}

            for raw_agent_id in normalized_agent_ids:
                row = rows_by_id.get(raw_agent_id)
                if not row:
                    continue
                target_user_ids.append(str(row.owner_user_id))
                target_entity_ids.append(str(row.agent_id))
                target_entity_names.append(row.name or str(row.agent_id))

        for raw_user_id in normalized_user_ids:
            target_user_ids.append(raw_user_id)
            target_entity_ids.append(raw_user_id)
            target_entity_names.append(_lookup_user_name(session, raw_user_id) or raw_user_id)

    return {
        "target_user_ids": _dedupe_preserve_order(target_user_ids),
        "target_entity_ids": _dedupe_preserve_order(target_entity_ids),
        "target_entity_names": _dedupe_preserve_order(target_entity_names),
    }


def _is_agent_scoped_query(memory_type, agent_id: Optional[str] = None) -> bool:
    """Whether the query should be treated as agent-memory scoped."""
    from memory_system.memory_interface import MemoryType

    return memory_type == MemoryType.AGENT or (memory_type is None and bool(agent_id))


def _resolve_effective_user_id(
    memory_type,
    current_user: CurrentUser,
    requested_user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Optional[str]:
    """Resolve user scope for search/list queries.

    Agent memories are scoped by agent ownership checks, not user_id field filtering, because
    many historical rows have null user_id while still belonging to a specific agent.
    """
    if _is_agent_scoped_query(memory_type, agent_id=agent_id):
        return None
    return requested_user_id or current_user.user_id


def _filter_agent_memory_access_sync(
    responses: List[dict],
    current_user: CurrentUser,
) -> List[dict]:
    """Filter agent-memory responses by agent ownership + RBAC rules."""
    from uuid import UUID

    from access_control.memory_filter import can_access_agent_memory
    from access_control.rbac import Action
    from database.connection import get_db_session
    from database.models import Agent

    agent_ids = {
        str(item.get("agentId"))
        for item in responses
        if item.get("type") == "agent" and item.get("agentId")
    }
    if not agent_ids:
        return responses

    parsed_agent_ids = []
    for raw_agent_id in agent_ids:
        try:
            parsed_agent_ids.append(UUID(raw_agent_id))
        except Exception:
            continue

    owner_by_agent_id: Dict[str, str] = {}
    if parsed_agent_ids:
        with get_db_session() as session:
            rows = (
                session.query(Agent.agent_id, Agent.owner_user_id)
                .filter(Agent.agent_id.in_(parsed_agent_ids))
                .all()
            )
        owner_by_agent_id = {str(row.agent_id): str(row.owner_user_id) for row in rows}

    filtered: List[dict] = []
    for item in responses:
        if item.get("type") != "agent":
            filtered.append(item)
            continue

        agent_id = str(item.get("agentId") or "").strip()
        if not agent_id:
            continue

        agent_owner_id = owner_by_agent_id.get(agent_id, "")
        if can_access_agent_memory(current_user, agent_id, agent_owner_id, Action.READ):
            filtered.append(item)

    return filtered


def _require_agent_read_access_sync(agent_id: str, current_user: CurrentUser) -> None:
    """Ensure current user can read this agent's memories."""
    from uuid import UUID

    from access_control.memory_filter import can_access_agent_memory
    from access_control.rbac import Action
    from database.connection import get_db_session
    from database.models import Agent

    try:
        parsed_agent_id = UUID(str(agent_id))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid agent_id: {agent_id}",
        ) from exc

    with get_db_session() as session:
        agent = session.query(Agent).filter(Agent.agent_id == parsed_agent_id).first()

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    allowed = can_access_agent_memory(
        current_user=current_user,
        agent_id=str(agent.agent_id),
        agent_owner_id=str(agent.owner_user_id),
        action=Action.READ,
    )

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this agent memory",
        )


def _infer_agent_memory_diagnostic_hints(
    *,
    active_db_count: int,
    without_user_id_count: int,
    vector_status_counts: Dict[str, int],
    milvus_count: Optional[int],
    milvus_error: Optional[str],
) -> Dict[str, Any]:
    """Infer likely root causes when agent-memory visibility looks abnormal."""
    hints: List[str] = []
    if active_db_count <= 0:
        hints.append("no_agent_memory_in_db")

    if active_db_count > 0 and without_user_id_count > 0:
        hints.append("agent_memory_rows_missing_user_id")

    if int(vector_status_counts.get("failed", 0) or 0) > 0:
        hints.append("vector_sync_failures_present")

    if milvus_error:
        hints.append("milvus_query_error")
    elif active_db_count > 0 and milvus_count == 0:
        hints.append("milvus_has_no_rows_for_agent")

    primary = hints[0] if hints else "healthy_or_no_obvious_issue"
    return {
        "primary": primary,
        "hints": hints,
    }


def _build_agent_memory_diagnostics_sync(
    agent_id: str,
    include_samples: bool = True,
    sample_limit: int = 5,
    milvus_scan_limit: int = 10000,
) -> Optional[Dict[str, Any]]:
    """Build diagnostic report for one agent's memories."""
    from uuid import UUID

    from sqlalchemy import func

    from database.connection import get_db_session
    from database.models import Agent, MemoryRecord
    from memory_system.collections import CollectionName
    from memory_system.milvus_connection import get_milvus_connection

    try:
        parsed_agent_id = UUID(str(agent_id))
    except Exception as exc:
        raise ValueError(f"Invalid agent_id: {agent_id}") from exc

    sample_limit = max(1, min(int(sample_limit or 5), 20))
    milvus_scan_limit = max(100, min(int(milvus_scan_limit or 10000), 50000))

    with get_db_session() as session:
        agent = session.query(Agent).filter(Agent.agent_id == parsed_agent_id).first()
        if not agent:
            return None

        active_query = session.query(MemoryRecord).filter(
            MemoryRecord.agent_id == str(agent.agent_id),
            MemoryRecord.memory_type == "agent",
            MemoryRecord.is_deleted.is_(False),
        )
        total_active = int(active_query.count() or 0)

        total_deleted = int(
            session.query(func.count(MemoryRecord.id))
            .filter(
                MemoryRecord.agent_id == str(agent.agent_id),
                MemoryRecord.memory_type == "agent",
                MemoryRecord.is_deleted.is_(True),
            )
            .scalar()
            or 0
        )

        with_user_id = int(
            active_query.filter(MemoryRecord.user_id.isnot(None)).count() or 0
        )
        without_user_id = max(total_active - with_user_id, 0)

        with_milvus_id = int(
            active_query.filter(MemoryRecord.milvus_id.isnot(None)).count() or 0
        )
        without_milvus_id = max(total_active - with_milvus_id, 0)

        raw_vector_status_rows = (
            session.query(MemoryRecord.vector_status, func.count(MemoryRecord.id))
            .filter(
                MemoryRecord.agent_id == str(agent.agent_id),
                MemoryRecord.memory_type == "agent",
                MemoryRecord.is_deleted.is_(False),
            )
            .group_by(MemoryRecord.vector_status)
            .all()
        )
        vector_status_counts: Dict[str, int] = {
            "pending": 0,
            "synced": 0,
            "failed": 0,
            "unknown": 0,
        }
        for status_value, status_count in raw_vector_status_rows:
            key = (status_value or "").strip().lower() or "unknown"
            if key in vector_status_counts:
                vector_status_counts[key] = int(status_count or 0)
            else:
                vector_status_counts["unknown"] += int(status_count or 0)

        latest_row = active_query.order_by(MemoryRecord.timestamp.desc()).first()

        sample_rows: List[Dict[str, Any]] = []
        if include_samples:
            rows = active_query.order_by(MemoryRecord.timestamp.desc()).limit(sample_limit).all()
            for row in rows:
                meta = row.memory_metadata if isinstance(row.memory_metadata, dict) else {}
                content = (row.content or "").strip()
                sample_rows.append(
                    {
                        "id": int(row.id),
                        "milvus_id": int(row.milvus_id) if row.milvus_id is not None else None,
                        "user_id": row.user_id,
                        "vector_status": row.vector_status,
                        "vector_error": row.vector_error,
                        "timestamp": row.timestamp.isoformat() if row.timestamp else None,
                        "content_preview": content[:160] + ("..." if len(content) > 160 else ""),
                        "metadata_keys": sorted(str(k) for k in meta.keys())[:20],
                    }
                )

    milvus_count: Optional[int] = None
    milvus_error: Optional[str] = None
    milvus_truncated = False
    try:
        milvus = get_milvus_connection()
        rows = _query_collection_with_retry(
            milvus,
            CollectionName.AGENT_MEMORIES,
            lambda col: col.query(
                expr=f'agent_id == "{str(parsed_agent_id)}"',
                output_fields=["id"],
                limit=milvus_scan_limit,
            ),
        )
        milvus_count = len(rows or [])
        milvus_truncated = bool(milvus_count >= milvus_scan_limit)
    except Exception as exc:
        milvus_error = str(exc)

    diagnosis = _infer_agent_memory_diagnostic_hints(
        active_db_count=total_active,
        without_user_id_count=without_user_id,
        vector_status_counts=vector_status_counts,
        milvus_count=milvus_count,
        milvus_error=milvus_error,
    )

    return {
        "agent_id": str(agent.agent_id),
        "agent_name": agent.name,
        "owner_user_id": str(agent.owner_user_id),
        "db": {
            "active_count": total_active,
            "deleted_count": total_deleted,
            "with_user_id_count": with_user_id,
            "without_user_id_count": without_user_id,
            "with_milvus_id_count": with_milvus_id,
            "without_milvus_id_count": without_milvus_id,
            "vector_status": vector_status_counts,
            "latest_memory_id": int(latest_row.id) if latest_row else None,
            "latest_timestamp": latest_row.timestamp.isoformat()
            if latest_row and latest_row.timestamp
            else None,
        },
        "milvus": {
            "collection": CollectionName.AGENT_MEMORIES,
            "count_for_agent": milvus_count,
            "scan_limit": milvus_scan_limit,
            "scan_truncated": milvus_truncated,
            "error": milvus_error,
        },
        "samples": sample_rows,
        "diagnosis": diagnosis,
    }


def _items_to_responses(items) -> List[dict]:
    """Convert memory items to response dicts with name lookups. Runs in thread."""
    from database.connection import get_db_session

    with get_db_session() as session:
        results = []
        target_name_cache: Dict[str, Optional[str]] = {}

        def _resolve_target_name(target_id: str) -> str:
            key = str(target_id)
            if key in target_name_cache:
                cached = target_name_cache[key]
                return cached or key

            name = _lookup_agent_name(session, key)
            if not name:
                name = _lookup_user_name(session, key)
            target_name_cache[key] = name
            return name or key

        for item in items:
            agent_name = _lookup_agent_name(session, item.agent_id)
            user_name = _lookup_user_name(session, item.user_id)
            raw_shared_with = (item.metadata or {}).get("shared_with", [])
            shared_with_names = (
                [_resolve_target_name(str(target_id)) for target_id in raw_shared_with]
                if isinstance(raw_shared_with, list)
                else []
            )
            results.append(
                _memory_item_to_response(
                    item,
                    agent_name=agent_name,
                    user_name=user_name,
                    shared_with_names=shared_with_names,
                )
            )
    return results


def _parse_datetime_safe(raw: Optional[str]) -> Optional[datetime]:
    """Parse date/datetime input used by list filters."""
    if not raw:
        return None
    candidate = str(raw).strip()
    if not candidate:
        return None
    try:
        if "T" not in candidate:
            candidate = f"{candidate}T00:00:00"
        candidate = candidate.replace("Z", "+00:00")
        return datetime.fromisoformat(candidate)
    except Exception:
        return None


def _apply_response_filters(
    responses: List[dict],
    *,
    date_from: Optional[str],
    date_to: Optional[str],
    tags: Optional[str],
) -> List[dict]:
    """Apply lightweight response filters (date/tags) on list endpoints."""

    def _normalize(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    start_dt = _normalize(_parse_datetime_safe(date_from))
    end_dt = _normalize(_parse_datetime_safe(date_to))
    expected_tags = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]

    if not start_dt and not end_dt and not expected_tags:
        return responses

    filtered = []
    for item in responses:
        created_at = _normalize(_parse_datetime_safe(item.get("createdAt")))
        if start_dt and created_at and created_at < start_dt:
            continue
        if end_dt and created_at and created_at > end_dt:
            continue

        if expected_tags:
            item_tags = item.get("tags") or []
            if not isinstance(item_tags, list):
                continue
            if not all(tag in item_tags for tag in expected_tags):
                continue

        filtered.append(item)

    return filtered


def _retrieve_memories_sync(query):
    """Retrieve memories synchronously (DB-first with semantic/vector fallback)."""
    from memory_system.memory_system import get_memory_system

    if query.query_text == "*":
        return _list_memories_without_embedding_sync(query)

    repo = _get_memory_repository()
    memory_system = get_memory_system()
    items = []
    try:
        semantic_items = memory_system.retrieve_memories(query)

        # Map Milvus ids back to PostgreSQL records so API ids remain business ids.
        milvus_ids = []
        for semantic_item in semantic_items:
            if semantic_item.id is None:
                continue
            try:
                milvus_ids.append(int(semantic_item.id))
            except (TypeError, ValueError):
                continue

        mapped_by_milvus = repo.get_by_milvus_ids(milvus_ids)
        for semantic_item in semantic_items:
            mapped = None
            try:
                mapped = mapped_by_milvus.get(int(semantic_item.id))
            except (TypeError, ValueError):
                mapped = None

            if mapped:
                # Enforce user isolation at source-of-truth layer.
                if query.user_id and str(mapped.user_id or "") != str(query.user_id):
                    continue
                db_item = mapped.to_memory_item(similarity_score=semantic_item.similarity_score)
                if semantic_item.metadata:
                    db_item.metadata = db_item.metadata or {}
                    # Preserve debug scores from ranking pipeline.
                    db_item.metadata.update(
                        {k: v for k, v in semantic_item.metadata.items() if str(k).startswith("_")}
                    )
                items.append(db_item)
            else:
                # Fail-closed for unmapped legacy vector rows when user scope is present.
                if query.user_id:
                    continue
                items.append(semantic_item)
    except Exception as exc:
        logger.warning("Semantic memory search failed, falling back to text search: %s", exc)

    if items:
        return _items_to_responses(items)

    fallback_rows = repo.search_text(
        query.query_text,
        memory_type=query.memory_type,
        agent_id=query.agent_id,
        user_id=query.user_id,
        task_id=query.task_id,
        limit=query.top_k or 10,
    )
    fallback_items = [row.to_memory_item() for row in fallback_rows]
    return _items_to_responses(fallback_items)


def _retrieve_shared_sync(user_id: str):
    """Retrieve shared memories synchronously."""
    from memory_system.memory_interface import MemoryType, SearchQuery
    from memory_system.memory_system import get_memory_system

    query = SearchQuery(
        query_text="*",
        memory_type=MemoryType.COMPANY,
        user_id=user_id,
        top_k=100,
    )
    try:
        responses = _list_memories_without_embedding_sync(query)
    except Exception:
        memory_system = get_memory_system()
        try:
            items = memory_system.retrieve_memories(query)
        except Exception:
            items = []
        responses = _items_to_responses(items)

    return [r for r in responses if r.get("metadata") and r["metadata"].get("shared_from")]


def _store_memory_sync(memory_item):
    """Store memory with PostgreSQL as source-of-truth and best-effort Milvus indexing."""
    from memory_system.memory_interface import MemoryType

    from database.connection import get_db_session

    if memory_item.memory_type == MemoryType.AGENT and not memory_item.agent_id:
        raise ValueError("agent_id required for agent memories")
    if memory_item.memory_type != MemoryType.AGENT and not memory_item.user_id:
        raise ValueError("user_id required for company/user_context memories")

    repo = _get_memory_repository()
    created = repo.create(memory_item)
    synced = _sync_record_to_milvus_sync(created.id)
    final_record = synced or repo.get(created.id) or created
    item = final_record.to_memory_item()

    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, item.agent_id)
        user_name = _lookup_user_name(session, item.user_id)

    return _memory_item_to_response(item, agent_name, user_name)


def _detect_memory_type(memory_id: int) -> Optional[str]:
    """Detect memory type by DB id first, then Milvus fallback for legacy rows."""
    from memory_system.collections import CollectionName
    from memory_system.milvus_connection import get_milvus_connection

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if record:
        return record.memory_type.value

    by_milvus = repo.get_by_milvus_id(memory_id)
    if by_milvus:
        return by_milvus.memory_type.value

    milvus = get_milvus_connection()
    # Check agent_memories first
    try:
        results = _query_collection_with_retry(
            milvus,
            CollectionName.AGENT_MEMORIES,
            lambda col: col.query(expr=f"id == {memory_id}", output_fields=["id"]),
        )
        if results:
            return "agent"
    except Exception:
        pass

    # Check company_memories
    try:
        results = _query_collection_with_retry(
            milvus,
            CollectionName.COMPANY_MEMORIES,
            lambda col: col.query(expr=f"id == {memory_id}", output_fields=["id"]),
        )
        if results:
            # Determine actual type from memory_type field
            full = _query_collection_with_retry(
                milvus,
                CollectionName.COMPANY_MEMORIES,
                lambda col: col.query(expr=f"id == {memory_id}", output_fields=["memory_type"]),
            )
            if full and full[0].get("memory_type"):
                return full[0]["memory_type"]
            return "company"
    except Exception:
        pass

    return None


def _get_memory_by_id_sync(memory_id: int, type_str: Optional[str] = None):
    """Get a single memory by business id (DB) with legacy Milvus fallback."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryItem, MemoryType
    from memory_system.milvus_connection import get_milvus_connection

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if not record:
        record = repo.get_by_milvus_id(memory_id)

    if record:
        if type_str and record.memory_type.value != type_str:
            return None

        item = record.to_memory_item()
        from database.connection import get_db_session

        with get_db_session() as session:
            agent_name = _lookup_agent_name(session, item.agent_id)
            user_name = _lookup_user_name(session, item.user_id)

        return _memory_item_to_response(item, agent_name, user_name)

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
    results = _query_collection_with_retry(
        milvus,
        collection_name,
        lambda col: col.query(
            expr=f"id == {memory_id}",
            output_fields=output_fields,
        ),
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
    """Delete memory from DB source-of-truth and best-effort vector index."""
    from memory_system.memory_interface import MemoryType
    from memory_system.memory_system import get_memory_system

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if not record:
        record = repo.get_by_milvus_id(memory_id)

    if record:
        if type_str and record.memory_type.value != type_str:
            return False

        memory_system = get_memory_system()
        if record.milvus_id is not None:
            try:
                memory_system.delete_memory(record.milvus_id, record.memory_type)
            except Exception as exc:
                logger.warning("Failed deleting vector index for memory %s: %s", record.id, exc)

        return repo.soft_delete(record.id)

    if not type_str:
        type_str = _detect_memory_type(memory_id)
        if not type_str:
            return False

    mem_type = MemoryType(type_str)
    memory_system = get_memory_system()
    return memory_system.delete_memory(memory_id, mem_type)


def _update_memory_sync(
    memory_id: int, type_str: Optional[str], request: MemoryUpdate, user_id: str
):
    """Update a memory synchronously (fetch, delete, re-insert)."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryItem, MemoryType
    from memory_system.memory_system import get_memory_system
    from memory_system.milvus_connection import get_milvus_connection

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if not record:
        record = repo.get_by_milvus_id(memory_id)

    if record:
        if type_str and record.memory_type.value != type_str:
            return None

        new_meta = dict(record.metadata or {})
        if request.tags is not None:
            new_meta["tags"] = request.tags
        if request.summary is not None:
            new_meta["summary"] = request.summary
        if request.metadata is not None:
            new_meta.update(request.metadata)

        new_content = request.content if request.content else record.content
        updated = repo.update_record(
            record.id,
            content=new_content,
            metadata=new_meta,
            user_id=record.user_id or user_id,
            agent_id=record.agent_id,
            task_id=record.task_id or new_meta.get("task_id"),
        )
        if not updated:
            return None

        synced = _sync_record_to_milvus_sync(updated.id)
        final_record = synced or repo.get(updated.id) or updated
        item = final_record.to_memory_item()

        from database.connection import get_db_session

        with get_db_session() as session:
            agent_name = _lookup_agent_name(session, item.agent_id)
            user_name = _lookup_user_name(session, item.user_id)

        return _memory_item_to_response(item, agent_name, user_name)

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
    results = _query_collection_with_retry(
        milvus,
        collection_name,
        lambda col: col.query(
            expr=f"id == {memory_id}",
            output_fields=output_fields,
        ),
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


def _numeric_timestamp_to_iso(raw_timestamp: float) -> Optional[str]:
    """Convert unix timestamp expressed in seconds or milliseconds to ISO string."""
    absolute = abs(raw_timestamp)
    if absolute >= 1e11:
        seconds = raw_timestamp / 1000.0
    elif absolute >= 1e9:
        seconds = raw_timestamp
    else:
        return None

    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _to_iso_timestamp(raw: Any) -> Optional[str]:
    """Convert timestamp-like value to ISO string."""
    if raw is None:
        return None

    if isinstance(raw, datetime):
        if raw.tzinfo is None:
            return raw.replace(tzinfo=timezone.utc).isoformat()
        return raw.isoformat()

    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        converted = _numeric_timestamp_to_iso(float(raw))
        if converted is not None:
            return converted

    if isinstance(raw, str):
        value = raw.strip()
        if not value:
            return None
        try:
            converted = _numeric_timestamp_to_iso(float(value))
            if converted is not None:
                return converted
        except ValueError:
            pass
        return value

    if hasattr(raw, "isoformat"):
        return raw.isoformat()

    try:
        return str(raw)
    except Exception:
        return None


def _inspect_memory_index_sync(memory_id: int, type_str: Optional[str] = None):
    """Inspect vector index payload for one memory record."""
    from memory_system.collections import CollectionName
    from memory_system.milvus_connection import get_milvus_connection

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if not record:
        record = repo.get_by_milvus_id(memory_id)
    if not record:
        return None
    if type_str and record.memory_type.value != type_str:
        return None

    if record.memory_type.value == "agent":
        collection_name = CollectionName.AGENT_MEMORIES
        output_fields = ["id", "agent_id", "content", "timestamp", "metadata", "embedding"]
    else:
        collection_name = CollectionName.COMPANY_MEMORIES
        output_fields = [
            "id",
            "user_id",
            "memory_type",
            "content",
            "timestamp",
            "metadata",
            "embedding",
        ]

    response = {
        "memoryId": str(record.id),
        "milvusId": record.milvus_id,
        "collection": collection_name,
        "vectorStatus": record.vector_status,
        "vectorError": record.vector_error,
        "vectorUpdatedAt": _to_iso_timestamp(record.vector_updated_at),
        "existsInMilvus": False,
        "indexedContent": None,
        "indexedTimestamp": None,
        "indexedMetadata": None,
        "embeddingDimension": None,
        "embeddingPreview": None,
        "milvusError": None,
    }

    if record.milvus_id is None:
        return response

    milvus = get_milvus_connection()
    try:
        rows = _query_collection_with_retry(
            milvus,
            collection_name,
            lambda col: col.query(
                expr=f"id == {record.milvus_id}",
                output_fields=output_fields,
            ),
        )
    except Exception as exc:
        response["milvusError"] = str(exc)
        return response

    if not rows:
        return response

    row = rows[0]
    embedding = row.get("embedding")
    embedding_preview = None
    embedding_dimension = None
    if isinstance(embedding, list):
        embedding_dimension = len(embedding)
        embedding_preview = [float(v) for v in embedding[:8]]

    response.update(
        {
            "existsInMilvus": True,
            "indexedContent": row.get("content"),
            "indexedTimestamp": _to_iso_timestamp(row.get("timestamp")),
            "indexedMetadata": row.get("metadata"),
            "embeddingDimension": embedding_dimension,
            "embeddingPreview": embedding_preview,
        }
    )
    return response


def _reindex_memory_sync(memory_id: int, type_str: Optional[str] = None):
    """Trigger manual vector re-index for a memory record."""
    from database.connection import get_db_session

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if not record:
        record = repo.get_by_milvus_id(memory_id)
    if not record:
        return None
    if type_str and record.memory_type.value != type_str:
        return None

    synced = _sync_record_to_milvus_sync(record.id)
    final_record = synced or repo.get(record.id) or record
    item = final_record.to_memory_item()

    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, item.agent_id)
        user_name = _lookup_user_name(session, item.user_id)
        raw_shared_with = (item.metadata or {}).get("shared_with", [])
        if isinstance(raw_shared_with, list):
            shared_with_names = [
                _lookup_agent_name(session, str(target_id))
                or _lookup_user_name(session, str(target_id))
                or str(target_id)
                for target_id in raw_shared_with
            ]
        else:
            shared_with_names = []

    return _memory_item_to_response(
        item,
        agent_name=agent_name,
        user_name=user_name,
        shared_with_names=shared_with_names,
    )


def _share_memory_sync(
    memory_id: int,
    type_str: Optional[str],
    user_ids: List[str],
    agent_ids: List[str],
):
    """Share a memory synchronously."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryItem, MemoryType
    from memory_system.memory_system import get_memory_system
    from memory_system.milvus_connection import get_milvus_connection

    repo = _get_memory_repository()
    source_record = repo.get(memory_id)
    if not source_record:
        source_record = repo.get_by_milvus_id(memory_id)

    if source_record:
        if type_str and source_record.memory_type.value != type_str:
            return None

        share_targets = _resolve_share_targets(agent_ids=agent_ids, user_ids=user_ids)
        target_user_ids = share_targets["target_user_ids"]
        target_entity_ids = share_targets["target_entity_ids"]
        target_entity_names = share_targets["target_entity_names"]

        existing_shared_records = repo.list_shared_children(source_record.id)
        existing_by_user_id = {}
        for shared_record in existing_shared_records:
            if shared_record.user_id and shared_record.user_id not in existing_by_user_id:
                existing_by_user_id[shared_record.user_id] = shared_record

        current_user_ids = set(existing_by_user_id.keys())
        desired_user_ids = set(target_user_ids)

        users_to_add = sorted(desired_user_ids - current_user_ids)
        users_to_remove = sorted(current_user_ids - desired_user_ids)

        memory_system = get_memory_system()

        for user_id_to_remove in users_to_remove:
            shared_record = existing_by_user_id.get(user_id_to_remove)
            if not shared_record:
                continue
            if shared_record.milvus_id is not None:
                try:
                    memory_system.delete_memory(shared_record.milvus_id, shared_record.memory_type)
                except Exception as exc:
                    logger.warning(
                        "Failed deleting shared vector row source=%s child=%s: %s",
                        source_record.id,
                        shared_record.id,
                        exc,
                    )
            repo.soft_delete(shared_record.id)

        for target_user_id in users_to_add:
            shared_meta = {
                **(source_record.metadata or {}),
                "shared_from": source_record.id,
                "shared_at": datetime.utcnow().isoformat(),
                "shared_to_user_id": target_user_id,
            }
            shared_item = MemoryItem(
                content=source_record.content,
                memory_type=MemoryType.COMPANY,
                user_id=target_user_id,
                timestamp=datetime.utcnow(),
                metadata=shared_meta,
            )
            created = repo.create(shared_item)
            _sync_record_to_milvus_sync(created.id)

        source_meta = dict(source_record.metadata or {})
        if target_entity_ids:
            source_meta["shared_with"] = target_entity_ids
            source_meta["shared_with_names"] = target_entity_names
        else:
            source_meta.pop("shared_with", None)
            source_meta.pop("shared_with_names", None)

        updated = repo.update_record(
            source_record.id,
            metadata=source_meta,
            mark_vector_pending=False,
        )
        if not updated:
            return None

        item = updated.to_memory_item()
        from database.connection import get_db_session

        with get_db_session() as session:
            agent_name = _lookup_agent_name(session, item.agent_id)
            user_name = _lookup_user_name(session, item.user_id)

        return _memory_item_to_response(
            item,
            agent_name=agent_name,
            user_name=user_name,
            shared_with_names=target_entity_names,
        )

    if not type_str:
        type_str = _detect_memory_type(memory_id)
        if not type_str:
            return None

    mem_type = MemoryType(type_str)
    memory_system = get_memory_system()

    target_ids = agent_ids or user_ids
    success = memory_system.share_memory(memory_id, mem_type, target_ids)
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
    results = _query_collection_with_retry(
        milvus,
        collection_name,
        lambda col: col.query(
            expr=f"id == {memory_id}",
            output_fields=output_fields,
        ),
    )

    if not results:
        return {
            "id": str(memory_id),
            "type": type_str,
            "content": "",
            "createdAt": datetime.utcnow().isoformat(),
            "tags": [],
            "isShared": True,
            "sharedWith": target_ids,
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
    item.metadata["shared_with"] = target_ids

    from database.connection import get_db_session

    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, item.agent_id)
        user_name = _lookup_user_name(session, item.user_id)
        shared_with_names = [
            _lookup_agent_name(session, str(target_id))
            or _lookup_user_name(session, str(target_id))
            or str(target_id)
            for target_id in target_ids
        ]

    return _memory_item_to_response(
        item,
        agent_name=agent_name,
        user_name=user_name,
        shared_with_names=shared_with_names,
    )


def _purge_memories_sync(memory_type: str, agent_id: Optional[str]):
    """Purge memories synchronously (DB-first soft delete + vector cleanup)."""
    from memory_system.collections import CollectionName
    from memory_system.memory_interface import MemoryType
    from memory_system.memory_system import get_memory_system
    from memory_system.milvus_connection import get_milvus_connection

    mem_type = MemoryType(memory_type)
    repo = _get_memory_repository()

    db_rows = repo.list_memories(memory_type=mem_type, agent_id=agent_id, limit=None)
    if db_rows:
        deleted = repo.purge_by_type(mem_type, agent_id=agent_id)
        memory_system = get_memory_system()
        vector_deleted = 0
        for row in db_rows:
            if row.milvus_id is None:
                continue
            try:
                if memory_system.delete_memory(row.milvus_id, row.memory_type):
                    vector_deleted += 1
            except Exception as exc:
                logger.warning(
                    "Failed deleting vector row during purge memory_id=%s milvus_id=%s: %s",
                    row.id,
                    row.milvus_id,
                    exc,
                )

        return {
            "deleted": deleted,
            "type": memory_type,
            "message": f"Purged {deleted} memories",
            "vectorDeleted": vector_deleted,
        }

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
    try:
        existing = _query_collection_with_retry(
            milvus,
            collection_name,
            lambda col: col.query(expr=expr, output_fields=["id"]),
        )
        count = len(existing)
    except Exception:
        count = 0

    if count == 0:
        return {"deleted": 0, "type": memory_type, "message": "No memories found to purge"}

    ids = [row["id"] for row in existing]
    collection = milvus.get_collection(collection_name)
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
    effective_user_id = _resolve_effective_user_id(
        memory_type,
        current_user,
        requested_user_id=user_id,
        agent_id=agent_id,
    )

    query = SearchQuery(
        query_text="*",
        memory_type=memory_type,
        agent_id=agent_id,
        user_id=effective_user_id,
        top_k=100,
    )

    try:
        results = await asyncio.to_thread(_retrieve_memories_sync, query)
    except CollectionLoadingError as e:
        logger.warning(f"Memory collection is still loading during list: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to list memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list memories: {e}",
        )

    results = _apply_response_filters(
        results,
        date_from=date_from,
        date_to=date_to,
        tags=tags,
    )
    if _is_agent_scoped_query(memory_type, agent_id=agent_id):
        results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)

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


@router.get("/config", response_model=MemoryConfigResponse)
async def get_memory_config(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get memory retrieval configuration and effective model sources."""
    try:
        config = get_config()
        memory_section = config.get_section("memory")
        kb_section = config.get_section("knowledge_base")
        return MemoryConfigResponse(**_build_memory_config_payload(memory_section, kb_section))
    except Exception as e:
        logger.error("Failed to get memory config: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory configuration: {str(e)}",
        )


@router.put("/config", response_model=MemoryConfigResponse)
async def update_memory_config(
    update_data: MemoryConfigUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update memory retrieval configuration. Requires admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update memory configuration",
        )

    try:
        import os

        import yaml

        from shared.config import reload_config

        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
        config_path = os.path.abspath(config_path)

        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)

        memory_cfg = raw_config.setdefault("memory", {})
        if update_data.embedding is not None:
            memory_cfg["embedding"] = {
                **(memory_cfg.get("embedding", {}) or {}),
                **update_data.embedding,
            }
        if update_data.retrieval is not None:
            memory_cfg["retrieval"] = {
                **(memory_cfg.get("retrieval", {}) or {}),
                **update_data.retrieval,
            }
        if update_data.runtime is not None:
            for key in _MEMORY_RUNTIME_KEYS:
                if key in update_data.runtime:
                    memory_cfg[key] = update_data.runtime[key]

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        reloaded = reload_config(config_path)
        updated_memory = reloaded.get_section("memory")
        updated_kb = reloaded.get_section("knowledge_base")
        return MemoryConfigResponse(**_build_memory_config_payload(updated_memory, updated_kb))

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update memory config: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update memory configuration: {str(e)}",
        )


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
        user_id=_resolve_effective_user_id(mem_type, current_user),
        top_k=100,
    )

    try:
        results = await asyncio.to_thread(_retrieve_memories_sync, query)
    except CollectionLoadingError as e:
        logger.warning(f"Memory collection is still loading during type query: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to retrieve memories by type: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve memories: {e}",
        )
    if mem_type == MemoryType.AGENT:
        results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)

    return [MemoryResponse(**r) for r in results]


@router.get("/agent/{agent_id}", response_model=List[MemoryResponse])
async def get_memories_by_agent(
    agent_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get memories for a specific agent."""
    from memory_system.memory_interface import MemoryType, SearchQuery

    await asyncio.to_thread(_require_agent_read_access_sync, agent_id, current_user)

    query = SearchQuery(
        query_text="*",
        memory_type=MemoryType.AGENT,
        agent_id=agent_id,
        user_id=_resolve_effective_user_id(MemoryType.AGENT, current_user, agent_id=agent_id),
        top_k=100,
    )

    try:
        results = await asyncio.to_thread(_retrieve_memories_sync, query)
    except CollectionLoadingError as e:
        logger.warning(f"Memory collection is still loading during agent query: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)
    return [MemoryResponse(**r) for r in results]


@router.get("/diagnostics/agent/{agent_id}")
async def diagnose_agent_memory(
    agent_id: str,
    include_samples: bool = Query(True, description="Include sample memory rows"),
    sample_limit: int = Query(5, ge=1, le=20),
    milvus_scan_limit: int = Query(
        10000,
        ge=100,
        le=50000,
        description="Max number of Milvus rows to scan for this agent",
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Diagnose one agent's memory visibility and indexing health."""
    await asyncio.to_thread(_require_agent_read_access_sync, agent_id, current_user)

    try:
        report = await asyncio.to_thread(
            _build_agent_memory_diagnostics_sync,
            agent_id,
            include_samples,
            sample_limit,
            milvus_scan_limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to build agent memory diagnostics: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to diagnose agent memory: {exc}",
        ) from exc

    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    report["requested_by"] = {
        "user_id": current_user.user_id,
        "role": current_user.role,
    }
    return report


@router.get("/{memory_id}", response_model=MemoryResponse)
async def get_memory(
    memory_id: int,
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get a single memory by Milvus ID. Type is auto-detected if not provided."""
    try:
        result = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, type)
    except CollectionLoadingError as e:
        logger.warning(f"Memory collection is still loading during get by id: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

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
    effective_user_id = _resolve_effective_user_id(memory_type, current_user)

    query = SearchQuery(
        query_text=request.query,
        memory_type=memory_type,
        user_id=effective_user_id,
        top_k=request.limit or 10,
        min_similarity=request.min_score or 0.0,
    )

    try:
        results = await asyncio.to_thread(_retrieve_memories_sync, query)
    except CollectionLoadingError as e:
        logger.warning(f"Memory collection is still loading during search: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to search memories: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to search memories: {e}",
        )
    if memory_type == MemoryType.AGENT:
        results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)

    return [MemoryResponse(**r) for r in results]


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: int,
    request: MemoryUpdate,
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
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


@router.post("/{memory_id}/reindex", response_model=MemoryResponse)
async def reindex_memory(
    memory_id: int,
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Manually rebuild vector index for one memory."""
    result = await asyncio.to_thread(_reindex_memory_sync, memory_id, type)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    logger.info(
        "Memory reindexed",
        extra={"memory_id": memory_id, "type": type},
    )
    return MemoryResponse(**result)


@router.get("/{memory_id}/index", response_model=MemoryIndexInspectResponse)
async def inspect_memory_index(
    memory_id: int,
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Inspect vector index record for one memory."""
    result = await asyncio.to_thread(_inspect_memory_index_sync, memory_id, type)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    return MemoryIndexInspectResponse(**result)


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: int,
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
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
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Share a memory with specific users/agents (full replacement)."""
    result = await asyncio.to_thread(
        _share_memory_sync,
        memory_id,
        type,
        request.user_ids or [],
        request.agent_ids or [],
    )

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found or sharing failed",
        )

    logger.info(
        "Memory shared",
        extra={
            "memory_id": memory_id,
            "shared_user_ids": request.user_ids,
            "shared_agent_ids": request.agent_ids,
        },
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


@router.post("/admin/backfill-agent-user-ids")
async def backfill_agent_user_ids(
    dry_run: bool = Query(True, description="If true, only report affected rows"),
    agent_id: Optional[str] = Query(
        None,
        description="Optional agent UUID to scope this operation",
    ),
    limit: Optional[int] = Query(
        None,
        ge=1,
        le=50000,
        description="Optional max rows to process in this run",
    ),
    reindex_vectors: bool = Query(
        False,
        description="Rebuild Milvus vectors for updated rows (requires dry_run=false)",
    ),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Admin maintenance endpoint to backfill missing user_id for agent memories."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can run agent-memory user_id backfill",
        )

    if reindex_vectors and dry_run:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="reindex_vectors requires dry_run=false",
        )

    from memory_system.agent_memory_backfill import backfill_agent_memory_user_ids

    try:
        result = await asyncio.to_thread(
            backfill_agent_memory_user_ids,
            dry_run=dry_run,
            agent_id=agent_id,
            limit=limit,
            reindex_vectors=reindex_vectors,
        )
    except Exception as exc:
        logger.error("Agent-memory user_id backfill failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Backfill failed: {exc}",
        ) from exc

    result["requested_by"] = {
        "user_id": current_user.user_id,
        "role": current_user.role,
    }
    return result


def _find_orphan_vectors_sync(
    collection_name: str,
    batch_size: int = 1000,
    dry_run: bool = True,
) -> dict:
    """Scan Milvus for vectors without matching PostgreSQL milvus_id records.

    Args:
        collection_name: Milvus collection to scan
        batch_size: Number of vectors to scan per batch
        dry_run: If True, only report orphans; if False, delete them

    Returns:
        dict with scan results
    """
    from memory_system.orphan_vector_cleanup import (
        load_orphan_cleanup_settings,
        scan_orphan_vectors,
    )

    settings = load_orphan_cleanup_settings()

    return scan_orphan_vectors(
        collection_name,
        batch_size=batch_size,
        dry_run=dry_run,
        max_scan=settings.max_scan_per_collection,
        max_delete=settings.max_delete_per_collection,
        query_timeout_seconds=settings.query_timeout_seconds,
    )


@router.post("/admin/cleanup-orphans")
async def cleanup_orphan_vectors(
    dry_run: bool = Query(True, description="If true, only report orphans without deleting"),
    collection: Optional[str] = Query(
        None, description="Specific collection to scan (default: scan all memory collections)"
    ),
    batch_size: int = Query(1000, ge=100, le=10000),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Scan Milvus for orphan vectors not linked to any PostgreSQL record.

    Requires admin role. Use dry_run=true (default) to preview before deleting.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can run orphan cleanup",
        )

    from memory_system.collections import CollectionName

    if collection:
        collections_to_scan = [collection]
    else:
        collections_to_scan = [
            CollectionName.AGENT_MEMORIES,
            CollectionName.COMPANY_MEMORIES,
        ]

    results = []
    for coll_name in collections_to_scan:
        result = await asyncio.to_thread(
            _find_orphan_vectors_sync, coll_name, batch_size, dry_run
        )
        results.append(result)

    total_orphans = sum(r.get("orphan_count", 0) for r in results)
    total_deleted = sum(r.get("deleted", 0) for r in results)
    total_scanned = sum(r.get("scanned", 0) for r in results)

    return {
        "dry_run": dry_run,
        "total_scanned": total_scanned,
        "total_orphans": total_orphans,
        "total_deleted": total_deleted,
        "collections": results,
    }
