"""Milvus vector index helpers for user-memory hybrid retrieval."""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema

from database.connection import get_db_session
from memory_system.embedding_service import get_embedding_service, resolve_embedding_settings
from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config
from shared.platform_settings import get_platform_setting, upsert_platform_setting

logger = logging.getLogger(__name__)

USER_MEMORY_VECTOR_INDEX_STATE_KEY = "user_memory_vector_index_state"
DEFAULT_USER_MEMORY_COLLECTION_PREFIX = "user_memory_embeddings_v2"


@dataclass(frozen=True)
class UserMemoryVectorSearchHit:
    """One Milvus hit resolved back to user-memory identity."""

    source_kind: str
    source_id: int
    user_id: str
    status: str
    distance: float
    rank: int
    entry_type: Optional[str] = None
    fact_kind: Optional[str] = None
    view_type: Optional[str] = None
    importance: Optional[float] = None
    confidence: Optional[float] = None
    updated_at_ts: Optional[int] = None
    content: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _collection_prefix() -> str:
    cfg = get_config().get("user_memory.retrieval.vector.collection_prefix")
    value = str(cfg or DEFAULT_USER_MEMORY_COLLECTION_PREFIX).strip()
    return value or DEFAULT_USER_MEMORY_COLLECTION_PREFIX


def _metric_type() -> str:
    value = str(get_config().get("user_memory.retrieval.vector.metric_type", "IP") or "IP").strip()
    return value or "IP"


def _nprobe() -> int:
    try:
        value = int(get_config().get("user_memory.retrieval.vector.nprobe", 16) or 16)
    except (TypeError, ValueError):
        value = 16
    return max(value, 1)


def build_user_memory_embedding_signature() -> str:
    """Build a stable signature for the active user-memory embedding configuration."""

    settings = resolve_embedding_settings(scope="user_memory")
    payload = {
        "provider": settings.get("provider"),
        "model": settings.get("model"),
        "dimension": settings.get("dimension"),
        "provider_source": settings.get("provider_source"),
        "model_source": settings.get("model_source"),
        "dimension_source": settings.get("dimension_source"),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=True)


def build_user_memory_collection_name(signature: Optional[str] = None) -> str:
    """Return the physical Milvus collection name for one embedding signature."""

    raw_signature = signature or build_user_memory_embedding_signature()
    suffix = hashlib.sha1(raw_signature.encode("utf-8")).hexdigest()[:12]
    return f"{_collection_prefix()}_{suffix}"


def get_user_memory_vector_index_state(*, session=None) -> Dict[str, Any]:
    """Load the persisted active user-memory vector index state."""

    if session is not None:
        state = get_platform_setting(session, USER_MEMORY_VECTOR_INDEX_STATE_KEY)
        return dict(state or {})

    with get_db_session() as db:
        state = get_platform_setting(db, USER_MEMORY_VECTOR_INDEX_STATE_KEY)
        return dict(state or {})


def set_user_memory_vector_index_state(
    state: Mapping[str, Any],
    *,
    session=None,
) -> Dict[str, Any]:
    """Persist active user-memory vector index state."""

    payload = dict(state or {})
    if session is not None:
        upsert_platform_setting(session, USER_MEMORY_VECTOR_INDEX_STATE_KEY, payload)
        return payload

    with get_db_session() as db:
        upsert_platform_setting(db, USER_MEMORY_VECTOR_INDEX_STATE_KEY, payload)
        return payload


def _build_state_payload(
    *,
    collection_name: str,
    signature: str,
    build_state: str,
    previous: Optional[Mapping[str, Any]] = None,
    started_at: Optional[str] = None,
    completed_at: Optional[str] = None,
    reconciled_at: Optional[str] = None,
) -> Dict[str, Any]:
    payload = dict(previous or {})
    payload["active_collection"] = collection_name
    payload["active_signature"] = signature
    payload["build_state"] = str(build_state or "ready")
    payload["last_backfill_started_at"] = started_at or payload.get("last_backfill_started_at")
    payload["last_backfill_completed_at"] = (
        completed_at or payload.get("last_backfill_completed_at")
    )
    payload["last_reconcile_at"] = reconciled_at or payload.get("last_reconcile_at")
    return payload


def get_user_memory_embedding_dimension() -> int:
    settings = resolve_embedding_settings(scope="user_memory")
    try:
        dimension = int(settings.get("dimension") or 0)
    except (TypeError, ValueError):
        dimension = 0
    return dimension if dimension > 0 else 1024


def create_user_memory_embeddings_schema() -> CollectionSchema:
    """Build the Milvus schema for entry/view hybrid retrieval."""

    embedding_dim = get_user_memory_embedding_dimension()
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="source_kind", dtype=DataType.VARCHAR, max_length=16),
        FieldSchema(name="source_id", dtype=DataType.INT64),
        FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=255),
        FieldSchema(name="status", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="entry_type", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="fact_kind", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="view_type", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="importance", dtype=DataType.FLOAT),
        FieldSchema(name="confidence", dtype=DataType.FLOAT),
        FieldSchema(name="updated_at_ts", dtype=DataType.INT64),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=embedding_dim),
        FieldSchema(name="metadata", dtype=DataType.JSON),
    ]
    return CollectionSchema(
        fields=fields,
        description="User memory entry/view embeddings for hybrid retrieval",
        enable_dynamic_field=False,
    )


def _create_index(collection: Collection) -> None:
    milvus_config = get_config().get_section("database.milvus")
    index_type = str(milvus_config.get("index_type", "IVF_FLAT") or "IVF_FLAT")
    if index_type == "IVF_FLAT":
        params: Dict[str, Any] = {"nlist": int(milvus_config.get("nlist", 1024) or 1024)}
    elif index_type == "HNSW":
        params = {
            "M": int(milvus_config.get("hnsw_m", 16) or 16),
            "efConstruction": int(milvus_config.get("hnsw_ef_construction", 200) or 200),
        }
    elif index_type == "IVF_SQ8":
        params = {"nlist": int(milvus_config.get("nlist", 1024) or 1024)}
    else:
        params = {}

    collection.create_index(
        field_name="embedding",
        index_params={
            "index_type": index_type,
            "metric_type": _metric_type(),
            "params": params,
        },
    )


def bootstrap_user_memory_vector_index(
    *,
    session=None,
    build_state: str = "ready",
) -> Dict[str, Any]:
    """Ensure the active user-memory Milvus collection exists and persist state."""

    signature = build_user_memory_embedding_signature()
    collection_name = build_user_memory_collection_name(signature)
    manager = get_milvus_connection()

    if not manager.collection_exists(collection_name):
        collection = Collection(
            name=collection_name,
            schema=create_user_memory_embeddings_schema(),
            using=manager.connection_alias,
        )
        _create_index(collection)
        collection.load()
        logger.info(
            "Created user-memory vector collection",
            extra={"collection_name": collection_name, "build_state": build_state},
        )
    else:
        manager.get_collection(collection_name).load()

    previous = get_user_memory_vector_index_state(session=session)
    payload = _build_state_payload(
        collection_name=collection_name,
        signature=signature,
        build_state=build_state,
        previous=previous,
        started_at=previous.get("last_backfill_started_at") or _utc_now_iso(),
        completed_at=_utc_now_iso() if build_state == "ready" else None,
    )
    set_user_memory_vector_index_state(payload, session=session)
    return payload


def resolve_active_user_memory_collection(*, session=None, auto_bootstrap: bool = True) -> str:
    """Resolve the active physical collection name for user-memory retrieval."""

    state = get_user_memory_vector_index_state(session=session)
    active_collection = str(state.get("active_collection") or "").strip()
    if active_collection:
        return active_collection
    if not auto_bootstrap:
        raise RuntimeError("User-memory vector index has not been bootstrapped")
    state = bootstrap_user_memory_vector_index(session=session, build_state="ready")
    return str(state["active_collection"])


def user_memory_vector_reindex_required(*, session=None) -> bool:
    """Return True when the active collection signature no longer matches config."""

    state = get_user_memory_vector_index_state(session=session)
    active_signature = str(state.get("active_signature") or "")
    return active_signature != build_user_memory_embedding_signature()


def build_user_memory_vector_metadata(
    *,
    source_kind: str,
    source_id: int,
    user_id: str,
    status: str,
    entry_type: Optional[str] = None,
    fact_kind: Optional[str] = None,
    view_type: Optional[str] = None,
    importance: Optional[float] = None,
    confidence: Optional[float] = None,
    updated_at_ts: Optional[int] = None,
    content: Optional[str] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build one Milvus payload document."""

    return {
        "source_kind": str(source_kind),
        "source_id": int(source_id),
        "user_id": str(user_id),
        "status": str(status or "active"),
        "entry_type": str(entry_type or ""),
        "fact_kind": str(fact_kind or ""),
        "view_type": str(view_type or ""),
        "importance": float(importance or 0.0),
        "confidence": float(confidence or 0.0),
        "updated_at_ts": int(updated_at_ts or 0),
        "content": str(content or ""),
        "metadata": dict(metadata or {}),
    }


def _expr_quote(value: object) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def delete_user_memory_vector(
    *,
    source_kind: str,
    source_id: int,
    collection_name: Optional[str] = None,
) -> None:
    """Delete one vector document by source identity."""

    target_collection = collection_name or resolve_active_user_memory_collection()
    manager = get_milvus_connection()
    if not manager.collection_exists(target_collection):
        return
    collection = manager.get_collection(target_collection)
    collection.delete(
        f'source_kind == "{_expr_quote(source_kind)}" and source_id == {int(source_id)}'
    )
    collection.flush()


def delete_user_memory_vectors_for_user(
    *,
    user_id: str,
    collection_name: Optional[str] = None,
) -> None:
    """Delete all vectors owned by one user."""

    target_collection = collection_name or resolve_active_user_memory_collection()
    manager = get_milvus_connection()
    if not manager.collection_exists(target_collection):
        return
    collection = manager.get_collection(target_collection)
    collection.delete(f'user_id == "{_expr_quote(user_id)}"')
    collection.flush()


def upsert_user_memory_vectors(
    documents: Sequence[Mapping[str, Any]],
    *,
    collection_name: Optional[str] = None,
) -> int:
    """Insert or replace one or more user-memory vector documents."""

    if not documents:
        return 0

    target_collection = collection_name or resolve_active_user_memory_collection()
    manager = get_milvus_connection()
    collection = manager.get_collection(target_collection)

    for document in documents:
        delete_user_memory_vector(
            source_kind=str(document["source_kind"]),
            source_id=int(document["source_id"]),
            collection_name=target_collection,
        )

    entities = [
        [str(document.get("source_kind") or "") for document in documents],
        [int(document.get("source_id") or 0) for document in documents],
        [str(document.get("user_id") or "") for document in documents],
        [str(document.get("status") or "active") for document in documents],
        [str(document.get("entry_type") or "") for document in documents],
        [str(document.get("fact_kind") or "") for document in documents],
        [str(document.get("view_type") or "") for document in documents],
        [float(document.get("importance") or 0.0) for document in documents],
        [float(document.get("confidence") or 0.0) for document in documents],
        [int(document.get("updated_at_ts") or 0) for document in documents],
        [str(document.get("content") or "") for document in documents],
        [list(document.get("embedding") or []) for document in documents],
        [dict(document.get("metadata") or {}) for document in documents],
    ]
    collection.insert(entities)
    collection.flush()
    return len(documents)


def upsert_user_memory_vector(
    document: Mapping[str, Any],
    *,
    collection_name: Optional[str] = None,
) -> None:
    """Insert or replace a single user-memory vector document."""

    upsert_user_memory_vectors([document], collection_name=collection_name)


def _build_search_expr(
    *,
    user_id: str,
    statuses: Optional[Sequence[str]] = None,
    source_kinds: Optional[Sequence[str]] = None,
    fact_kinds: Optional[Sequence[str]] = None,
    view_types: Optional[Sequence[str]] = None,
) -> str:
    clauses = [f'user_id == "{_expr_quote(user_id)}"']
    if statuses:
        quoted = ", ".join(f'"{_expr_quote(status)}"' for status in statuses if str(status).strip())
        if quoted:
            clauses.append(f"status in [{quoted}]")
    if source_kinds:
        quoted = ", ".join(
            f'"{_expr_quote(kind)}"' for kind in source_kinds if str(kind).strip()
        )
        if quoted:
            clauses.append(f"source_kind in [{quoted}]")
    if fact_kinds:
        quoted = ", ".join(f'"{_expr_quote(kind)}"' for kind in fact_kinds if str(kind).strip())
        if quoted:
            clauses.append(f"fact_kind in [{quoted}]")
    if view_types:
        quoted = ", ".join(f'"{_expr_quote(kind)}"' for kind in view_types if str(kind).strip())
        if quoted:
            clauses.append(f"view_type in [{quoted}]")
    return " and ".join(clauses)


def search_user_memory_vectors(
    *,
    user_id: str,
    query: str,
    top_k: int,
    collection_name: Optional[str] = None,
    statuses: Optional[Sequence[str]] = None,
    source_kinds: Optional[Sequence[str]] = None,
    fact_kinds: Optional[Sequence[str]] = None,
    view_types: Optional[Sequence[str]] = None,
) -> List[UserMemoryVectorSearchHit]:
    """Run a semantic search against the active user-memory collection."""

    if not str(query or "").strip():
        return []

    target_collection = collection_name or resolve_active_user_memory_collection()
    manager = get_milvus_connection()
    if not manager.collection_exists(target_collection):
        return []

    embedding = get_embedding_service(scope="user_memory").generate_embedding(str(query))
    collection = manager.get_collection(target_collection)
    expr = _build_search_expr(
        user_id=str(user_id),
        statuses=statuses,
        source_kinds=source_kinds,
        fact_kinds=fact_kinds,
        view_types=view_types,
    )
    raw_results = collection.search(
        data=[embedding],
        anns_field="embedding",
        param={"metric_type": _metric_type(), "params": {"nprobe": _nprobe()}},
        limit=max(int(top_k), 1),
        expr=expr or None,
        output_fields=[
            "source_kind",
            "source_id",
            "user_id",
            "status",
            "entry_type",
            "fact_kind",
            "view_type",
            "importance",
            "confidence",
            "updated_at_ts",
            "content",
            "metadata",
        ],
    )

    hits: List[UserMemoryVectorSearchHit] = []
    for rank, hit in enumerate(raw_results[0] if raw_results else []):
        entity = hit.entity
        hits.append(
            UserMemoryVectorSearchHit(
                source_kind=str(entity.get("source_kind") or ""),
                source_id=int(entity.get("source_id") or 0),
                user_id=str(entity.get("user_id") or ""),
                status=str(entity.get("status") or ""),
                distance=float(hit.distance),
                rank=rank,
                entry_type=str(entity.get("entry_type") or "") or None,
                fact_kind=str(entity.get("fact_kind") or "") or None,
                view_type=str(entity.get("view_type") or "") or None,
                importance=float(entity.get("importance") or 0.0),
                confidence=float(entity.get("confidence") or 0.0),
                updated_at_ts=int(entity.get("updated_at_ts") or 0),
                content=str(entity.get("content") or "") or None,
                metadata=dict(entity.get("metadata") or {}),
            )
        )
    return hits


def iterate_user_memory_vectors(
    *,
    collection_name: Optional[str] = None,
    batch_size: int = 500,
) -> Iterable[Dict[str, Any]]:
    """Yield vector documents from the active collection for reconcile scripts."""

    target_collection = collection_name or resolve_active_user_memory_collection()
    manager = get_milvus_connection()
    if not manager.collection_exists(target_collection):
        return []

    collection = manager.get_collection(target_collection)
    offset = 0
    items: List[Dict[str, Any]] = []
    while True:
        batch = collection.query(
            expr="source_id >= 0",
            offset=offset,
            limit=max(int(batch_size), 1),
            output_fields=[
                "source_kind",
                "source_id",
                "user_id",
                "status",
                "entry_type",
                "fact_kind",
                "view_type",
                "importance",
                "confidence",
                "updated_at_ts",
                "content",
                "metadata",
            ],
        )
        if not batch:
            break
        items.extend(batch)
        offset += len(batch)
        if len(batch) < batch_size:
            break
    return items


def compact_user_memory_vectors(*, collection_name: Optional[str] = None) -> None:
    """Trigger Milvus compaction for the active user-memory collection."""

    target_collection = collection_name or resolve_active_user_memory_collection()
    manager = get_milvus_connection()
    if not manager.collection_exists(target_collection):
        return
    manager.get_collection(target_collection).compact()


__all__ = [
    "DEFAULT_USER_MEMORY_COLLECTION_PREFIX",
    "USER_MEMORY_VECTOR_INDEX_STATE_KEY",
    "UserMemoryVectorSearchHit",
    "bootstrap_user_memory_vector_index",
    "build_user_memory_collection_name",
    "build_user_memory_embedding_signature",
    "build_user_memory_vector_metadata",
    "compact_user_memory_vectors",
    "create_user_memory_embeddings_schema",
    "delete_user_memory_vector",
    "delete_user_memory_vectors_for_user",
    "get_user_memory_embedding_dimension",
    "get_user_memory_vector_index_state",
    "iterate_user_memory_vectors",
    "resolve_active_user_memory_collection",
    "search_user_memory_vectors",
    "set_user_memory_vector_index_state",
    "upsert_user_memory_vector",
    "upsert_user_memory_vectors",
    "user_memory_vector_reindex_required",
]
