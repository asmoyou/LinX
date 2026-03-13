"""Milvus collection helpers for reset-era user memory."""

from __future__ import annotations

import logging
from typing import Any, Dict

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema

from memory_system.embedding_service import resolve_embedding_settings
from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config

logger = logging.getLogger(__name__)

USER_MEMORY_ENTRIES_COLLECTION = "user_memory_entries"


def get_user_memory_embedding_dimension() -> int:
    settings = resolve_embedding_settings(scope="user_memory")
    try:
        dimension = int(settings.get("dimension") or 0)
    except (TypeError, ValueError):
        dimension = 0
    return dimension if dimension > 0 else 1024


def _get_index_type() -> str:
    return str(get_config().get("database.milvus.index_type", "IVF_FLAT") or "IVF_FLAT")


def _get_metric_type() -> str:
    metric = str(get_config().get("database.milvus.metric_type", "L2") or "L2")
    return metric if metric else "L2"


def create_user_memory_entries_schema() -> CollectionSchema:
    embedding_dim = get_user_memory_embedding_dimension()
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True,
            description="Primary key",
        ),
        FieldSchema(
            name="entry_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="References PostgreSQL user_memory_entries.id",
        ),
        FieldSchema(
            name="user_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="Owner user identifier",
        ),
        FieldSchema(
            name="fact_kind",
            dtype=DataType.VARCHAR,
            max_length=64,
            description="Fact kind for filtering",
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=embedding_dim,
            description="User memory embedding vector",
        ),
        FieldSchema(
            name="canonical_text",
            dtype=DataType.VARCHAR,
            max_length=65535,
            description="Canonical user-memory statement",
        ),
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
            description="Additional metadata for retrieval and debugging",
        ),
    ]
    return CollectionSchema(
        fields=fields,
        description="User memory entry embeddings",
        enable_dynamic_field=False,
    )


def _create_index(collection: Collection) -> None:
    config = get_config()
    milvus_config = config.get_section("database.milvus")
    index_type = _get_index_type()
    metric_type = _get_metric_type()

    if index_type == "IVF_FLAT":
        params: Dict[str, Any] = {"nlist": milvus_config.get("nlist", 1024)}
    elif index_type == "HNSW":
        params = {
            "M": milvus_config.get("hnsw_m", 16),
            "efConstruction": milvus_config.get("hnsw_ef_construction", 200),
        }
    elif index_type == "IVF_SQ8":
        params = {"nlist": milvus_config.get("nlist", 1024)}
    elif index_type == "IVF_PQ":
        params = {
            "nlist": milvus_config.get("nlist", 1024),
            "m": 8,
            "nbits": 8,
        }
    else:
        params = {}

    collection.create_index(
        field_name="embedding",
        index_params={
            "index_type": index_type,
            "metric_type": metric_type,
            "params": params,
        },
    )


def ensure_user_memory_entries_collection(drop_if_exists: bool = False) -> Collection:
    manager = get_milvus_connection()

    if manager.collection_exists(USER_MEMORY_ENTRIES_COLLECTION):
        if drop_if_exists:
            logger.warning("Dropping existing collection: %s", USER_MEMORY_ENTRIES_COLLECTION)
            manager.drop_collection(USER_MEMORY_ENTRIES_COLLECTION)
        else:
            collection = manager.get_collection(USER_MEMORY_ENTRIES_COLLECTION)
            collection.load()
            return collection

    collection = Collection(
        name=USER_MEMORY_ENTRIES_COLLECTION,
        schema=create_user_memory_entries_schema(),
        using=manager.connection_alias,
    )
    _create_index(collection)
    collection.load()
    return collection


def recreate_user_memory_entries_collection() -> Collection:
    return ensure_user_memory_entries_collection(drop_if_exists=True)


__all__ = [
    "USER_MEMORY_ENTRIES_COLLECTION",
    "create_user_memory_entries_schema",
    "ensure_user_memory_entries_collection",
    "get_user_memory_embedding_dimension",
    "recreate_user_memory_entries_collection",
]
