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
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

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
    # Backward compatibility only: agent_ids are mapped to owner user IDs.
    agent_ids: List[str] = Field(default_factory=list)
    scope: Optional[str] = Field(
        None,
        pattern=r"^(explicit|department|department_tree|account|private|public)$",
    )
    expires_at: Optional[str] = None
    reason: Optional[str] = None


class AgentCandidateReviewRequest(BaseModel):
    """Review action for auto-extracted agent memory candidates."""

    action: str = Field(..., pattern=r"^(publish|reject|revise)$")
    content: Optional[str] = Field(None, min_length=1)
    summary: Optional[str] = None
    note: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


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


class MemoryPageResponse(BaseModel):
    """Paginated memory list response model."""

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    items: List[MemoryResponse]
    total: int
    offset: int
    limit: int
    has_more: bool = Field(False, alias="hasMore")


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
    fact_extraction: dict
    runtime: dict
    recommended: Optional[dict] = None


class MemoryConfigUpdateRequest(BaseModel):
    """Request to update memory retrieval configuration."""

    embedding: Optional[dict] = None
    retrieval: Optional[dict] = None
    fact_extraction: Optional[dict] = None
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
    "fact_extraction": {
        "enabled": True,
        "model_enabled": False,
        "provider": "",
        "model": "",
        "timeout_seconds": 4,
        "max_facts": 8,
        "failure_backoff_seconds": 60,
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


def _resolve_provider_default_chat_model(llm_section: dict, provider: str) -> str:
    providers_cfg = llm_section.get("providers", {}) if isinstance(llm_section, dict) else {}
    if not isinstance(providers_cfg, dict):
        return ""
    provider_cfg = providers_cfg.get(provider, {})
    if not isinstance(provider_cfg, dict):
        return ""
    raw_models = provider_cfg.get("models")
    if isinstance(raw_models, dict):
        for preferred_key in ("chat", "default", "completion", "instruct"):
            candidate = str(raw_models.get(preferred_key) or "").strip()
            if candidate:
                return candidate
        for value in raw_models.values():
            candidate = str(value or "").strip()
            if candidate:
                return candidate
        return ""
    if isinstance(raw_models, list):
        for value in raw_models:
            candidate = str(value or "").strip()
            if candidate:
                return candidate
        return ""
    return str(raw_models or "").strip()


def _build_memory_config_payload(
    memory_section: dict,
    kb_section: Optional[dict] = None,
    llm_section: Optional[dict] = None,
) -> dict:
    """Build memory config payload with effective resolved settings and source hints."""
    from memory_system.embedding_service import resolve_embedding_settings

    kb_section = kb_section if isinstance(kb_section, dict) else {}
    llm_section = llm_section if isinstance(llm_section, dict) else {}
    kb_search = kb_section.get("search", {}) if isinstance(kb_section.get("search"), dict) else {}
    llm_default_provider = str(llm_section.get("default_provider") or "").strip()

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
        memory_section.get("runtime", {}) if isinstance(memory_section.get("runtime"), dict) else {}
    )
    enhanced_cfg = (
        memory_section.get("enhanced_memory", {})
        if isinstance(memory_section.get("enhanced_memory"), dict)
        else {}
    )
    fact_cfg = (
        enhanced_cfg.get("fact_extraction", {})
        if isinstance(enhanced_cfg.get("fact_extraction"), dict)
        else {}
    )

    embedding_merged = _deep_merge(_MEMORY_RECOMMENDED_DEFAULTS["embedding"], embedding_cfg)
    retrieval_merged = _deep_merge(_MEMORY_RECOMMENDED_DEFAULTS["retrieval"], retrieval_cfg)
    fact_merged = _deep_merge(_MEMORY_RECOMMENDED_DEFAULTS["fact_extraction"], fact_cfg)
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

    configured_fact_provider = str(fact_cfg.get("provider") or "").strip()
    configured_fact_model = str(fact_cfg.get("model") or "").strip()
    effective_fact_provider = configured_fact_provider or llm_default_provider
    effective_fact_model = configured_fact_model or _resolve_provider_default_chat_model(
        llm_section,
        effective_fact_provider,
    )
    fact_provider_source = (
        "memory.enhanced_memory.fact_extraction.provider"
        if configured_fact_provider
        else ("llm.default_provider" if llm_default_provider else "none")
    )
    fact_model_source = (
        "memory.enhanced_memory.fact_extraction.model"
        if configured_fact_model
        else (
            f"llm.providers.{effective_fact_provider}.models.chat"
            if effective_fact_model and effective_fact_provider
            else "none"
        )
    )
    fact_extraction_payload = {
        **fact_merged,
        "effective": {
            "provider": effective_fact_provider,
            "model": effective_fact_model,
        },
        "sources": {
            "provider": fact_provider_source,
            "model": fact_model_source,
        },
    }

    return {
        "embedding": embedding_payload,
        "retrieval": retrieval_effective,
        "fact_extraction": fact_extraction_payload,
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

    memory_type_value = (
        item.memory_type.value if hasattr(item.memory_type, "value") else str(item.memory_type)
    )
    visibility = _resolve_memory_visibility(str(memory_type_value), meta)
    meta["visibility"] = visibility
    is_published_scope = visibility in {"explicit", "department", "department_tree", "public"}
    publish_mode = str(meta.get("publish_mode") or "").strip().lower()
    shared_with_user_ids = meta.get("shared_with_user_ids", [])
    if not isinstance(shared_with_user_ids, list):
        shared_with_user_ids = []
    has_promotion_backlink = bool(meta.get("last_promoted_memory_id"))

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
        "isShared": (
            bool(shared_from)
            or bool(shared_with)
            or bool(shared_with_user_ids)
            or is_published_scope
            or publish_mode == "promote"
            or has_promotion_backlink
        ),
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


_MEMORY_QUERY_STOP_TERMS = {
    "如何",
    "怎么",
    "怎样",
    "请问",
    "一下",
    "一下子",
    "可以",
    "是否",
    "这个",
    "那个",
    "是谁",
    "什么",
    "为什么",
    "where",
    "when",
    "who",
    "what",
    "how",
    "is",
    "are",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "to",
    "of",
    "in",
    "on",
}

_MEMORY_CJK_QUESTION_TERMS = {"如何", "怎么", "怎样", "请问", "是谁", "什么"}
_MEMORY_CJK_QUESTION_CHARS = {"如", "何", "怎", "样", "请", "问", "谁", "什", "么"}


def _extract_memory_query_terms(query_text: str, *, max_terms: int = 16) -> List[str]:
    """Extract normalized query terms for keyword fallback retrieval."""
    normalized = unicodedata.normalize("NFKC", str(query_text or "")).strip().lower()
    if len(normalized) < 2:
        return []

    terms = set()

    for token in re.findall(r"[a-z0-9][a-z0-9._-]{1,}", normalized):
        if token not in _MEMORY_QUERY_STOP_TERMS:
            terms.add(token)

    split_terms = re.split(
        r"[\s,，。！？!?;；:：/\\|()\[\]{}【】\"'“”‘’]+",
        normalized,
    )
    for token in split_terms:
        token = token.strip()
        if len(token) >= 2 and token not in _MEMORY_QUERY_STOP_TERMS:
            terms.add(token)

    cjk_fragments = re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", normalized)
    for fragment in cjk_fragments:
        if len(fragment) >= 2 and fragment not in _MEMORY_QUERY_STOP_TERMS:
            terms.add(fragment)

        for n in (2, 3):
            if len(fragment) < n:
                continue
            for idx in range(len(fragment) - n + 1):
                gram = fragment[idx: idx + n]
                if not gram or gram in _MEMORY_QUERY_STOP_TERMS:
                    continue
                if any(question in gram for question in _MEMORY_CJK_QUESTION_TERMS):
                    continue
                if gram[0] in _MEMORY_CJK_QUESTION_CHARS:
                    continue
                terms.add(gram)

    if normalized not in _MEMORY_QUERY_STOP_TERMS and len(normalized) >= 2:
        terms.add(normalized)

    return sorted(terms, key=lambda item: (-len(item), item))[: max(int(max_terms), 1)]


def _keyword_min_term_hits(query_terms: List[str]) -> int:
    """Require more lexical agreement for longer queries to reduce noisy matches."""
    term_count = len([term for term in query_terms if len(str(term).strip()) >= 2])
    if term_count <= 2:
        return 1
    if term_count <= 6:
        return 2
    return 3


def _keyword_rank_to_similarity(rank: float) -> float:
    """Normalize keyword rank to [0, 1] for API relevance display and threshold filtering."""
    safe_rank = max(float(rank or 0.0), 0.0)
    return min(max(safe_rank / (safe_rank + 4.0), 0.0), 1.0)


def _resolve_share_targets(agent_ids: List[str], user_ids: List[str]) -> Dict[str, List[str]]:
    """Resolve share targets into explicit user IDs and human-readable names.

    `agent_ids` are compatibility input only and are mapped to agent owners.
    """
    from database.connection import get_db_session
    from database.models import Agent

    normalized_agent_ids = _dedupe_preserve_order([str(v) for v in (agent_ids or []) if str(v)])
    normalized_user_ids = _dedupe_preserve_order([str(v) for v in (user_ids or []) if str(v)])

    target_user_ids: List[str] = []
    target_entity_ids: List[str] = []
    entity_name_map: Dict[str, str] = {}

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
                owner_user_id = str(row.owner_user_id) if row.owner_user_id else ""
                if not owner_user_id:
                    continue
                target_user_ids.append(owner_user_id)
                target_entity_ids.append(owner_user_id)
                if owner_user_id not in entity_name_map:
                    entity_name_map[owner_user_id] = (
                        _lookup_user_name(session, owner_user_id)
                        or row.name
                        or owner_user_id
                    )

        for raw_user_id in normalized_user_ids:
            target_user_ids.append(raw_user_id)
            target_entity_ids.append(raw_user_id)
            if raw_user_id not in entity_name_map:
                entity_name_map[raw_user_id] = _lookup_user_name(session, raw_user_id) or raw_user_id

    deduped_entity_ids = _dedupe_preserve_order(target_entity_ids)

    return {
        "target_user_ids": _dedupe_preserve_order(target_user_ids),
        "target_entity_ids": deduped_entity_ids,
        "target_entity_names": [entity_name_map.get(entity_id, entity_id) for entity_id in deduped_entity_ids],
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
    """
    from memory_system.memory_interface import MemoryType

    requested = str(requested_user_id).strip() if requested_user_id else None

    if memory_type == MemoryType.AGENT or agent_id:
        return requested or current_user.user_id
    if memory_type == MemoryType.USER_CONTEXT:
        return requested or current_user.user_id

    # For company/org discovery, avoid hard user_id constraint so policy-based
    # sharing (department/publish/ACL) can be evaluated in application layer.
    if requested and requested == str(current_user.user_id):
        return requested
    if requested and current_user.role in {"admin", "manager"}:
        return requested
    return None


def _parse_uuid(raw_value: Optional[str]) -> Optional[UUID]:
    if not raw_value:
        return None
    try:
        return UUID(str(raw_value))
    except Exception:
        return None


def _is_admin_or_manager(current_user: CurrentUser) -> bool:
    return str(current_user.role).strip().lower() in {"admin", "manager"}


def _resolve_memory_visibility(memory_type_value: str, metadata: Dict[str, Any]) -> str:
    normalized_type = str(memory_type_value or "").strip().lower()
    configured = str(metadata.get("visibility") or "").strip().lower()

    if normalized_type == "user_context":
        if configured in {"private", "explicit"}:
            return configured
        return "private"

    if configured:
        return configured
    if normalized_type == "agent":
        return "private"
    # Company/org memory defaults to department hierarchy inheritance.
    return "department_tree"


def _resolve_user_department_id_sync(user_id: Optional[str]) -> Optional[str]:
    from database.connection import get_db_session
    from database.models import User

    parsed_user_id = _parse_uuid(user_id)
    if parsed_user_id is None:
        return None

    with get_db_session() as session:
        row = session.query(User.department_id).filter(User.user_id == parsed_user_id).first()
    return str(row[0]) if row and row[0] else None


def _resolve_agent_department_id_sync(agent_id: Optional[str]) -> Optional[str]:
    from database.connection import get_db_session
    from database.models import Agent

    parsed_agent_id = _parse_uuid(agent_id)
    if parsed_agent_id is None:
        return None

    with get_db_session() as session:
        row = session.query(Agent.department_id).filter(Agent.agent_id == parsed_agent_id).first()
    return str(row[0]) if row and row[0] else None


def _build_user_department_context_sync(current_user: CurrentUser) -> Dict[str, Any]:
    from collections import defaultdict, deque

    from database.connection import get_db_session
    from database.models import Department, User

    context: Dict[str, Any] = {
        "department_id": None,
        "managed_department_ids": set(),
    }
    parsed_user_id = _parse_uuid(current_user.user_id)
    if parsed_user_id is None:
        return context

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == parsed_user_id).first()
        if not user:
            return context

        context["department_id"] = str(user.department_id) if user.department_id else None
        rows = (
            session.query(Department.department_id, Department.parent_id, Department.manager_id)
            .filter(Department.status == "active")
            .all()
        )

    children: Dict[str, List[str]] = defaultdict(list)
    managed_roots: List[str] = []
    for department_id, parent_id, manager_id in rows:
        dep_id = str(department_id)
        if parent_id:
            children[str(parent_id)].append(dep_id)
        if manager_id and str(manager_id) == str(current_user.user_id):
            managed_roots.append(dep_id)

    managed_ids = set()
    queue = deque(managed_roots)
    while queue:
        dep_id = queue.popleft()
        if dep_id in managed_ids:
            continue
        managed_ids.add(dep_id)
        for child in children.get(dep_id, []):
            queue.append(child)

    context["managed_department_ids"] = managed_ids
    return context


def _load_memory_acl_map_sync(memory_ids: List[int]) -> Dict[int, List[Dict[str, Any]]]:
    repo = _get_memory_repository()
    return repo.list_active_acl_entries(memory_ids)


def _matches_acl_principal(
    entry: Dict[str, Any],
    current_user: CurrentUser,
    user_department_context: Dict[str, Any],
) -> bool:
    principal_type = str(entry.get("principal_type") or "").strip().lower()
    principal_id = str(entry.get("principal_id") or "").strip()
    if not principal_type or not principal_id:
        return False

    if principal_type == "user":
        return principal_id == str(current_user.user_id)
    if principal_type == "agent":
        active_agent_id = str(
            getattr(current_user, "agent_id", None)
            or user_department_context.get("active_agent_id")
            or ""
        ).strip()
        if active_agent_id and principal_id == active_agent_id:
            return True
        return _agent_owned_by_user_sync(principal_id, current_user.user_id)
    if principal_type == "role":
        return principal_id == str(current_user.role)
    if principal_type == "department":
        return principal_id == str(user_department_context.get("department_id") or "")
    return False


def _evaluate_acl_decision(
    entries: List[Dict[str, Any]],
    current_user: CurrentUser,
    user_department_context: Dict[str, Any],
) -> Optional[bool]:
    matched_deny = False
    matched_allow = False
    for entry in entries:
        if not _matches_acl_principal(entry, current_user, user_department_context):
            continue
        effect = str(entry.get("effect") or "").strip().lower()
        if effect == "deny":
            matched_deny = True
            break
        if effect == "allow":
            matched_allow = True

    if matched_deny:
        return False
    if matched_allow:
        return True
    return None


def _is_explicit_metadata_allow(metadata: Dict[str, Any], current_user: CurrentUser) -> bool:
    target_user_ids = metadata.get("shared_with_user_ids")
    if isinstance(target_user_ids, list):
        normalized = {str(raw_id) for raw_id in target_user_ids if str(raw_id).strip()}
        if str(current_user.user_id) in normalized:
            return True

    # Backward compatibility with old metadata shapes.
    direct_target = str(metadata.get("shared_to_user_id") or "").strip()
    if direct_target and direct_target == str(current_user.user_id):
        return True
    return False


def _company_visibility_allows(
    *,
    visibility: str,
    owner_user_id: str,
    resource_department_id: Optional[str],
    current_user: CurrentUser,
    user_department_context: Dict[str, Any],
) -> bool:
    current_user_id = str(current_user.user_id)
    user_department_id = str(user_department_context.get("department_id") or "")

    if visibility == "private":
        return owner_user_id == current_user_id
    if visibility == "account":
        if not resource_department_id:
            return owner_user_id == current_user_id
        if str(resource_department_id) == user_department_id:
            return True
        managed = user_department_context.get("managed_department_ids") or set()
        return str(resource_department_id) in managed
    if visibility == "department":
        if not resource_department_id or not user_department_id:
            return False
        return str(resource_department_id) == user_department_id
    if visibility == "department_tree":
        if not resource_department_id:
            return False
        if str(resource_department_id) == user_department_id:
            return True
        managed = user_department_context.get("managed_department_ids") or set()
        return str(resource_department_id) in managed
    if visibility == "public":
        return True
    if visibility == "explicit":
        return False
    return owner_user_id == current_user_id


def _can_read_company_memory_item_sync(
    item: Dict[str, Any],
    current_user: CurrentUser,
    user_department_context: Dict[str, Any],
    acl_entries: List[Dict[str, Any]],
) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    memory_type_value = str(item.get("type") or "").strip().lower()

    # Priority #1: explicit deny in ACL.
    acl_decision = _evaluate_acl_decision(acl_entries, current_user, user_department_context)
    if acl_decision is False:
        return False

    # Priority #2: explicit allow in ACL or metadata share target.
    if acl_decision is True or _is_explicit_metadata_allow(metadata, current_user):
        return True

    owner_user_id = str(
        metadata.get("owner_user_id")
        or item.get("userId")
        or item.get("user_id")
        or ""
    ).strip()
    owner_agent_id = str(
        metadata.get("owner_agent_id")
        or item.get("agentId")
        or item.get("agent_id")
        or ""
    ).strip()
    resource_department_id = str(metadata.get("department_id") or "").strip() or None
    visibility = _resolve_memory_visibility(memory_type_value, metadata)

    # Priority #3: owner(user/agent) check.
    if owner_user_id and owner_user_id == str(current_user.user_id):
        return True
    if owner_agent_id and _agent_owned_by_user_sync(owner_agent_id, current_user.user_id):
        return True

    # User profile memory remains private by default.
    if memory_type_value == "user_context":
        return False

    # Priority #4: department inheritance scope.
    if _company_visibility_allows(
        visibility=visibility,
        owner_user_id=owner_user_id,
        resource_department_id=resource_department_id,
        current_user=current_user,
        user_department_context=user_department_context,
    ):
        return True

    # Priority #5: role override.
    if _is_admin_or_manager(current_user):
        return True

    return False


def _filter_company_memory_access_sync(
    responses: List[dict],
    current_user: CurrentUser,
) -> List[dict]:
    """Filter non-agent memories using ACL + ownership + department inheritance."""
    memory_ids = []
    for item in responses:
        if str(item.get("type") or "").strip().lower() == "agent":
            continue
        try:
            memory_ids.append(int(item.get("id")))
        except (TypeError, ValueError):
            continue

    acl_map = _load_memory_acl_map_sync(memory_ids)
    user_department_context = _build_user_department_context_sync(current_user)

    filtered: List[dict] = []
    for item in responses:
        item_type = str(item.get("type") or "").strip().lower()
        if item_type == "agent":
            filtered.append(item)
            continue

        item_id: Optional[int] = None
        try:
            item_id = int(item.get("id"))
        except (TypeError, ValueError):
            item_id = None

        acl_entries = acl_map.get(item_id or -1, [])
        if _can_read_company_memory_item_sync(
            item,
            current_user=current_user,
            user_department_context=user_department_context,
            acl_entries=acl_entries,
        ):
            filtered.append(item)

    return filtered


def _agent_owned_by_user_sync(agent_id: Optional[str], user_id: str) -> bool:
    from database.connection import get_db_session
    from database.models import Agent

    parsed_agent_id = _parse_uuid(agent_id)
    if parsed_agent_id is None:
        return False

    with get_db_session() as session:
        row = session.query(Agent.owner_user_id).filter(Agent.agent_id == parsed_agent_id).first()
    return bool(row and str(row[0]) == str(user_id))


def _can_manage_memory_item_sync(item: Dict[str, Any], current_user: CurrentUser) -> bool:
    if _is_admin_or_manager(current_user):
        return True

    item_type = str(item.get("type") or "").strip().lower()
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    owner_user_id = str(
        metadata.get("owner_user_id")
        or item.get("userId")
        or item.get("user_id")
        or ""
    ).strip()
    owner_agent_id = str(
        metadata.get("owner_agent_id")
        or item.get("agentId")
        or item.get("agent_id")
        or ""
    ).strip()
    if owner_user_id and owner_user_id == str(current_user.user_id):
        return True
    if owner_agent_id and _agent_owned_by_user_sync(owner_agent_id, current_user.user_id):
        return True

    if item_type == "agent":
        agent_id = str(item.get("agentId") or item.get("agent_id") or "").strip()
        if agent_id and _agent_owned_by_user_sync(agent_id, current_user.user_id):
            return True

    return False


def _require_memory_read_access_sync(item: Dict[str, Any], current_user: CurrentUser) -> None:
    item_type = str(item.get("type") or "").strip().lower()
    if item_type == "agent":
        agent_id = str(item.get("agentId") or item.get("agent_id") or "").strip()
        _require_agent_read_access_sync(agent_id, current_user)
        return

    allowed_items = _filter_company_memory_access_sync([item], current_user)
    if not allowed_items:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this memory",
        )


def _require_memory_manage_access_sync(item: Dict[str, Any], current_user: CurrentUser) -> None:
    if not _can_manage_memory_item_sync(item, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this memory",
        )


def _enrich_memory_security_metadata_sync(memory_item) -> None:
    """Normalize ownership/visibility metadata before storing memory records."""
    memory_type_value = (
        memory_item.memory_type.value
        if hasattr(memory_item.memory_type, "value")
        else str(memory_item.memory_type)
    )
    metadata = dict(memory_item.metadata or {})

    owner_user_id = str(metadata.get("owner_user_id") or memory_item.user_id or "").strip() or None
    owner_agent_id = (
        str(metadata.get("owner_agent_id") or memory_item.agent_id or "").strip() or None
    )
    visibility = _resolve_memory_visibility(memory_type_value, metadata)
    sensitivity = str(metadata.get("sensitivity") or "internal").strip().lower() or "internal"
    department_id = str(metadata.get("department_id") or "").strip() or None
    if not department_id:
        if memory_type_value == "agent":
            department_id = _resolve_agent_department_id_sync(memory_item.agent_id)
        else:
            department_id = _resolve_user_department_id_sync(owner_user_id)

    metadata["owner_user_id"] = owner_user_id
    metadata["owner_agent_id"] = owner_agent_id
    metadata["department_id"] = department_id
    metadata["visibility"] = visibility
    metadata["sensitivity"] = sensitivity
    memory_item.metadata = metadata


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

        with_user_id = int(active_query.filter(MemoryRecord.user_id.isnot(None)).count() or 0)
        without_user_id = max(total_active - with_user_id, 0)

        with_milvus_id = int(active_query.filter(MemoryRecord.milvus_id.isnot(None)).count() or 0)
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
            "latest_timestamp": (
                latest_row.timestamp.isoformat() if latest_row and latest_row.timestamp else None
            ),
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
    query_text: Optional[str] = None,
) -> List[dict]:
    """Apply lightweight response filters (date/tags) on list endpoints."""

    def _normalize(dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    start_dt = _normalize(_parse_datetime_safe(date_from))
    end_dt = _normalize(_parse_datetime_safe(date_to))
    expected_tags = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    normalized_query = str(query_text or "").strip().lower()

    if not start_dt and not end_dt and not expected_tags and not normalized_query:
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

        if normalized_query:
            content = str(item.get("content") or "").lower()
            summary = str(item.get("summary") or "").lower()
            item_tags = item.get("tags") or []
            has_matching_tag = (
                isinstance(item_tags, list)
                and any(normalized_query in str(tag).lower() for tag in item_tags)
            )
            if (
                normalized_query not in content
                and normalized_query not in summary
                and not has_matching_tag
            ):
                continue

        filtered.append(item)

    return filtered


def _build_paginated_memory_response(
    responses: List[dict],
    *,
    offset: int,
    limit: int,
) -> MemoryPageResponse:
    """Build a paginated response from full result list."""
    safe_offset = max(int(offset or 0), 0)
    safe_limit = max(min(int(limit or 20), 100), 1)
    total = len(responses)
    items = responses[safe_offset : safe_offset + safe_limit]
    has_more = safe_offset + len(items) < total
    return MemoryPageResponse(
        items=[MemoryResponse(**item) for item in items],
        total=total,
        offset=safe_offset,
        limit=safe_limit,
        has_more=has_more,
    )


def _retrieve_memories_sync(query):
    """Retrieve memories synchronously (semantic first, then strict keyword fallback)."""
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
        logger.warning("Semantic memory search failed, attempting keyword fallback: %s", exc)

    if items:
        return _items_to_responses(items)

    try:
        effective_min_similarity = max(float(query.min_similarity or 0.0), 0.0)
    except (TypeError, ValueError):
        effective_min_similarity = 0.0

    query_terms = _extract_memory_query_terms(query.query_text)
    fallback_rows = repo.search_keywords(
        query.query_text,
        query_terms=query_terms,
        memory_type=query.memory_type,
        agent_id=query.agent_id,
        user_id=query.user_id,
        task_id=query.task_id,
        min_term_hits=_keyword_min_term_hits(query_terms),
        min_rank=1.8,
        limit=query.top_k or 10,
    )
    fallback_items = []
    for row, keyword_rank, term_hits in fallback_rows:
        score = _keyword_rank_to_similarity(keyword_rank)
        if score < effective_min_similarity:
            continue
        item = row.to_memory_item(similarity_score=score)
        item.metadata = dict(item.metadata or {})
        item.metadata["search_method"] = "keyword"
        item.metadata["keyword_rank"] = round(float(keyword_rank), 4)
        item.metadata["keyword_term_hits"] = int(term_hits)
        fallback_items.append(item)

    if fallback_items:
        logger.info(
            "Memory keyword fallback matched results",
            extra={
                "query": query.query_text,
                "result_count": len(fallback_items),
                "term_count": len(query_terms),
                "min_similarity": effective_min_similarity,
            },
        )

    return _items_to_responses(fallback_items)


def _retrieve_shared_sync(current_user: CurrentUser):
    """Retrieve accessible memories that are shared/published by others."""
    from memory_system.memory_interface import MemoryType, SearchQuery
    from memory_system.memory_system import get_memory_system

    query = SearchQuery(
        query_text="*",
        memory_type=MemoryType.COMPANY,
        user_id=None,
        top_k=300,
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

    visible = _filter_company_memory_access_sync(responses, current_user)
    shared: List[dict] = []
    for item in visible:
        if str(item.get("type") or "").strip().lower() == "agent":
            continue
        owner_user_id = str(
            ((item.get("metadata") or {}).get("owner_user_id") if isinstance(item.get("metadata"), dict) else "")
            or item.get("userId")
            or ""
        ).strip()
        if owner_user_id and owner_user_id == str(current_user.user_id):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        visibility = _resolve_memory_visibility(str(item.get("type") or ""), metadata)
        if visibility in {"explicit", "department", "department_tree", "public", "account"} or metadata.get(
            "shared_with_user_ids"
        ):
            shared.append(item)
    return shared


def _list_memories_by_type_sync(memory_type, user_id: Optional[str]) -> List[dict]:
    """List all memories of one type from PostgreSQL source-of-truth."""
    repo = _get_memory_repository()
    rows = repo.list_memories(
        memory_type=memory_type,
        user_id=user_id,
        limit=None,
    )
    items = [row.to_memory_item() for row in rows]
    return _items_to_responses(items)


def _is_agent_candidate_response(item: dict) -> bool:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    signal_type = str(metadata.get("signal_type") or "").strip().lower()
    return signal_type == "agent_memory_candidate"


def _list_agent_candidate_memories_sync(
    *,
    current_user: CurrentUser,
    agent_id: Optional[str],
    review_status: str,
    limit: int,
) -> List[dict]:
    """List auto-extracted agent memory candidates for review."""
    from memory_system.memory_interface import MemoryType, SearchQuery

    normalized_review_status = str(review_status or "pending").strip().lower()
    effective_user_id = _resolve_effective_user_id(
        MemoryType.AGENT,
        current_user,
        agent_id=agent_id,
    )
    query = SearchQuery(
        query_text="*",
        memory_type=MemoryType.AGENT,
        agent_id=agent_id,
        user_id=effective_user_id,
        top_k=max(int(limit), 1),
    )

    responses = _list_memories_without_embedding_sync(query)
    responses = _filter_agent_memory_access_sync(responses, current_user)

    candidate_items: List[dict] = []
    for item in responses:
        if str(item.get("type") or "").strip().lower() != "agent":
            continue
        if not _is_agent_candidate_response(item):
            continue

        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        item_status = str(metadata.get("review_status") or "pending").strip().lower()
        if normalized_review_status != "all" and item_status != normalized_review_status:
            continue
        candidate_items.append(item)

    candidate_items.sort(
        key=lambda item: str(item.get("createdAt") or ""),
        reverse=True,
    )
    return candidate_items[:limit]


def _review_agent_candidate_sync(
    *,
    memory_id: int,
    request: AgentCandidateReviewRequest,
    reviewer_user_id: str,
) -> Optional[dict]:
    """Apply review action to one agent memory candidate."""
    from database.connection import get_db_session

    repo = _get_memory_repository()
    record = repo.get(memory_id)
    if not record:
        record = repo.get_by_milvus_id(memory_id)
    if not record:
        return None

    memory_type = str(getattr(record.memory_type, "value", record.memory_type) or "").strip().lower()
    if memory_type != "agent":
        raise ValueError("Only agent memories support candidate review")

    metadata = dict(record.metadata or {})
    signal_type = str(metadata.get("signal_type") or "").strip().lower()
    if signal_type != "agent_memory_candidate":
        raise ValueError("Memory is not an agent candidate")

    action = str(request.action or "").strip().lower()
    if action not in {"publish", "reject", "revise"}:
        raise ValueError("Unsupported review action")

    now_iso = datetime.utcnow().isoformat() + "Z"
    review_status = {
        "publish": "published",
        "reject": "rejected",
        "revise": "pending",
    }[action]

    metadata.update(
        {
            "review_status": review_status,
            "reviewed_at": now_iso,
            "reviewed_by": str(reviewer_user_id),
            "is_active": action != "reject",
        }
    )
    if request.note is not None:
        metadata["review_note"] = request.note
    if request.summary is not None:
        metadata["summary"] = request.summary
    if request.metadata and isinstance(request.metadata, dict):
        metadata.update(request.metadata)

    if action == "publish":
        metadata["published_at"] = now_iso
    elif action == "reject":
        metadata["rejected_at"] = now_iso

    new_content = str(request.content or "").strip() if request.content else None
    content_changed = bool(new_content and new_content != str(record.content or ""))

    updated = repo.update_record(
        int(record.id),
        content=new_content if content_changed else None,
        metadata=metadata,
        user_id=record.user_id,
        agent_id=record.agent_id,
        task_id=record.task_id,
        mark_vector_pending=content_changed,
    )
    if not updated:
        return None

    final_record = updated
    if content_changed:
        synced = _sync_record_to_milvus_sync(int(updated.id))
        final_record = synced or repo.get(int(updated.id)) or updated

    item = final_record.to_memory_item()
    with get_db_session() as session:
        agent_name = _lookup_agent_name(session, item.agent_id)
        user_name = _lookup_user_name(session, item.user_id)

    return _memory_item_to_response(item, agent_name=agent_name, user_name=user_name)


def _store_memory_sync(memory_item):
    """Store memory via MemorySystem to apply normalization/dedup/merge policies."""
    from memory_system.memory_interface import MemoryType
    from memory_system.memory_system import get_memory_system

    from database.connection import get_db_session

    if memory_item.memory_type == MemoryType.AGENT and not memory_item.agent_id:
        raise ValueError("agent_id required for agent memories")
    if memory_item.memory_type != MemoryType.AGENT and not memory_item.user_id:
        raise ValueError("user_id required for company/user_context memories")

    _enrich_memory_security_metadata_sync(memory_item)

    memory_system = get_memory_system()
    repo = _get_memory_repository()
    memory_id = memory_system.store_memory(memory_item)
    final_record = repo.get(memory_id)
    if final_record:
        item = final_record.to_memory_item()
    else:
        item = memory_item
        item.id = memory_id

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
    scope: Optional[str],
    expires_at: Optional[str],
    reason: Optional[str],
    shared_by_user_id: Optional[str],
):
    """Apply publish/share policy on a memory and upsert explicit ACL entries."""
    from memory_system.memory_interface import MemoryItem, MemoryType

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
        normalized_scope = str(scope or "").strip().lower()
        normalized_reason = str(reason or "").strip() or None
        if not normalized_scope:
            if target_user_ids:
                normalized_scope = "explicit"
            elif source_record.memory_type == MemoryType.USER_CONTEXT:
                normalized_scope = "private"
            else:
                normalized_scope = "department_tree"
        if target_user_ids and not normalized_reason:
            raise ValueError("reason is required when explicit user exceptions are configured")
        if source_record.memory_type == MemoryType.USER_CONTEXT:
            if normalized_scope not in {"private", "explicit"}:
                raise ValueError(
                    "User-context memories only support private or explicit visibility",
                )
            if normalized_scope == "explicit" and not target_user_ids:
                normalized_scope = "private"
        elif normalized_scope == "explicit" and not target_user_ids:
            normalized_scope = "department_tree"

        expires_dt = _parse_datetime_safe(expires_at)
        if expires_at and expires_dt is None:
            raise ValueError("Invalid expires_at format, expected ISO date/datetime")

        # Phase out legacy copy-based shares by cleaning child copies.
        for shared_record in repo.list_shared_children(source_record.id):
            repo.soft_delete(shared_record.id)

        source_meta = dict(source_record.metadata or {})
        source_meta["visibility"] = normalized_scope
        source_meta["shared_with"] = target_entity_ids
        source_meta["shared_with_user_ids"] = target_user_ids
        source_meta["shared_with_names"] = target_entity_names
        source_meta["share_reason"] = normalized_reason
        source_meta["shared_updated_at"] = datetime.utcnow().isoformat()
        source_meta["shared_updated_by"] = shared_by_user_id
        source_meta["expires_at"] = expires_dt.isoformat() if expires_dt else None

        # publish/promote: agent_working_memory -> team/org(company) memory
        # when scope goes beyond private.
        if (
            source_record.memory_type == MemoryType.AGENT
            and normalized_scope in {"explicit", "department", "department_tree", "public", "account"}
        ):
            owner_user_id = source_record.owner_user_id or source_record.user_id
            promoted_meta = dict(source_meta)
            promoted_meta["source_memory_id"] = source_record.id
            promoted_meta["publish_mode"] = "promote"
            promoted_memory = MemoryItem(
                content=source_record.content,
                memory_type=MemoryType.COMPANY,
                user_id=owner_user_id,
                timestamp=datetime.utcnow(),
                metadata=promoted_meta,
            )
            _enrich_memory_security_metadata_sync(promoted_memory)
            created = repo.create(promoted_memory)
            _sync_record_to_milvus_sync(created.id)
            target_memory_id = int(created.id)

            # Keep backlink on source agent memory for traceability.
            source_meta["last_promoted_memory_id"] = target_memory_id
            repo.update_record(
                source_record.id,
                metadata=source_meta,
                mark_vector_pending=False,
            )
        else:
            updated = repo.update_record(
                source_record.id,
                metadata=source_meta,
                visibility=normalized_scope,
                expires_at=expires_dt,
                clear_expires_at=expires_dt is None,
                mark_vector_pending=False,
            )
            if not updated:
                return None
            target_memory_id = int(updated.id)

        acl_entries = []
        for target_user_id in target_user_ids:
            acl_entries.append(
                {
                    "effect": "allow",
                    "principal_type": "user",
                    "principal_id": target_user_id,
                    "reason": normalized_reason,
                    "expires_at": expires_dt.isoformat() if expires_dt else None,
                }
            )
        repo.replace_acl_entries(
            target_memory_id,
            acl_entries,
            created_by=shared_by_user_id,
        )

        refreshed = repo.get(target_memory_id)
        if not refreshed:
            return None

        item = refreshed.to_memory_item()
        from database.connection import get_db_session
        from database.models import AuditLog

        with get_db_session() as session:
            agent_name = _lookup_agent_name(session, item.agent_id)
            user_name = _lookup_user_name(session, item.user_id)

            session.add(
                AuditLog(
                    user_id=_parse_uuid(shared_by_user_id),
                    agent_id=_parse_uuid(item.agent_id),
                    action="memory.publish" if source_record.memory_type == MemoryType.AGENT else "memory.share",
                    resource_type="memory",
                    resource_id=None,
                    details={
                        "memory_id": target_memory_id,
                        "source_memory_id": source_record.id,
                        "scope": normalized_scope,
                        "target_user_ids": target_user_ids,
                        "reason": normalized_reason,
                        "expires_at": expires_dt.isoformat() if expires_dt else None,
                    },
                )
            )

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

    return None


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
    results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)
    results = await asyncio.to_thread(_filter_company_memory_access_sync, results, current_user)

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
        llm_section = config.get_section("llm")
        return MemoryConfigResponse(
            **_build_memory_config_payload(memory_section, kb_section, llm_section)
        )
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
        if update_data.fact_extraction is not None:
            enhanced_cfg = memory_cfg.get("enhanced_memory", {})
            if not isinstance(enhanced_cfg, dict):
                enhanced_cfg = {}
            enhanced_cfg["fact_extraction"] = {
                **(enhanced_cfg.get("fact_extraction", {}) or {}),
                **update_data.fact_extraction,
            }
            memory_cfg["enhanced_memory"] = enhanced_cfg
        if update_data.runtime is not None:
            for key in _MEMORY_RUNTIME_KEYS:
                if key in update_data.runtime:
                    memory_cfg[key] = update_data.runtime[key]

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        reloaded = reload_config(config_path)
        updated_memory = reloaded.get_section("memory")
        updated_kb = reloaded.get_section("knowledge_base")
        updated_llm = reloaded.get_section("llm")
        return MemoryConfigResponse(
            **_build_memory_config_payload(updated_memory, updated_kb, updated_llm)
        )

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
    results = await asyncio.to_thread(_retrieve_shared_sync, current_user)
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
    results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)
    results = await asyncio.to_thread(_filter_company_memory_access_sync, results, current_user)

    return [MemoryResponse(**r) for r in results]


@router.get("/type/{memory_type}/paged", response_model=MemoryPageResponse)
async def get_memories_by_type_paged(
    memory_type: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    query_text: Optional[str] = Query(None, alias="query"),
    date_from: Optional[str] = Query(None, alias="dateFrom"),
    date_to: Optional[str] = Query(None, alias="dateTo"),
    tags: Optional[str] = Query(None, description="Comma-separated tags"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get paginated memories filtered by type with optional lightweight filters."""
    from memory_system.memory_interface import MemoryType

    try:
        mem_type = MemoryType(memory_type)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid memory type: {memory_type}",
        )

    effective_user_id = _resolve_effective_user_id(mem_type, current_user)

    try:
        results = await asyncio.to_thread(
            _list_memories_by_type_sync,
            mem_type,
            effective_user_id,
        )
    except Exception as e:
        logger.error(f"Failed to retrieve paged memories by type: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve memories: {e}",
        )

    results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)
    results = await asyncio.to_thread(_filter_company_memory_access_sync, results, current_user)
    results = _apply_response_filters(
        results,
        date_from=date_from,
        date_to=date_to,
        tags=tags,
        query_text=query_text,
    )
    return _build_paginated_memory_response(results, offset=offset, limit=limit)


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
    results = await asyncio.to_thread(_filter_company_memory_access_sync, results, current_user)
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
    await asyncio.to_thread(_require_memory_read_access_sync, result, current_user)
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
    results = await asyncio.to_thread(_filter_agent_memory_access_sync, results, current_user)
    results = await asyncio.to_thread(_filter_company_memory_access_sync, results, current_user)

    return [MemoryResponse(**r) for r in results]


@router.get("/agent-candidates", response_model=List[MemoryResponse])
async def list_agent_memory_candidates(
    agent_id: Optional[str] = Query(None),
    review_status: str = Query("pending", pattern=r"^(pending|published|rejected|all)$"),
    limit: int = Query(50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List auto-extracted agent memory candidates for manual review."""
    try:
        results = await asyncio.to_thread(
            _list_agent_candidate_memories_sync,
            current_user=current_user,
            agent_id=agent_id,
            review_status=review_status,
            limit=limit,
        )
    except Exception as exc:
        logger.error("Failed to list agent memory candidates: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agent memory candidates: {exc}",
        ) from exc

    return [MemoryResponse(**item) for item in results]


@router.post("/agent-candidates/{memory_id}/review", response_model=MemoryResponse)
async def review_agent_memory_candidate(
    memory_id: int,
    request: AgentCandidateReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Review and publish/reject/revise an auto-extracted agent memory candidate."""
    existing = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, "agent")
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await asyncio.to_thread(_require_memory_manage_access_sync, existing, current_user)
    if not _is_agent_candidate_response(existing):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Memory is not an agent candidate",
        )

    try:
        result = await asyncio.to_thread(
            _review_agent_candidate_sync,
            memory_id=memory_id,
            request=request,
            reviewer_user_id=current_user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error("Failed to review agent memory candidate: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to review agent memory candidate: {exc}",
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )

    return MemoryResponse(**result)


@router.put("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: int,
    request: MemoryUpdate,
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a memory (delete + re-insert in Milvus). Type is auto-detected if not provided."""
    existing = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, type)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await asyncio.to_thread(_require_memory_manage_access_sync, existing, current_user)

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
    existing = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, type)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await asyncio.to_thread(_require_memory_manage_access_sync, existing, current_user)

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
    existing = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, type)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await asyncio.to_thread(_require_memory_manage_access_sync, existing, current_user)

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
    """Apply share policy with optional explicit user exceptions (full replacement)."""
    existing = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, type)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await asyncio.to_thread(_require_memory_manage_access_sync, existing, current_user)

    try:
        result = await asyncio.to_thread(
            _share_memory_sync,
            memory_id,
            type,
            request.user_ids or [],
            request.agent_ids or [],
            request.scope,
            request.expires_at,
            request.reason,
            current_user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found or sharing failed",
        )

    logger.info(
        "Memory shared",
        extra={
            "memory_id": memory_id,
            "shared_target_user_ids": request.user_ids,
            "scope": request.scope,
        },
    )

    return MemoryResponse(**result)


@router.post("/{memory_id}/publish", response_model=MemoryResponse)
async def publish_memory(
    memory_id: int,
    request: MemoryShareRequest,
    type: Optional[str] = Query(None, pattern=r"^(agent|company|user_context|task_context)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Publish/promote memory to team/org scopes (scope-first semantics)."""
    existing = await asyncio.to_thread(_get_memory_by_id_sync, memory_id, type)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found",
        )
    await asyncio.to_thread(_require_memory_manage_access_sync, existing, current_user)

    scope = request.scope or "department_tree"
    try:
        result = await asyncio.to_thread(
            _share_memory_sync,
            memory_id,
            type,
            request.user_ids or [],
            request.agent_ids or [],
            scope,
            request.expires_at,
            request.reason,
            current_user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Memory not found or publish failed",
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
        result = await asyncio.to_thread(_find_orphan_vectors_sync, coll_name, batch_size, dry_run)
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
