"""Milvus collection helpers for the knowledge base."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pymilvus import Collection, CollectionSchema, DataType, FieldSchema

from memory_system.embedding_service import resolve_embedding_settings
from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config

logger = logging.getLogger(__name__)

KNOWLEDGE_EMBEDDINGS_COLLECTION = "knowledge_embeddings"


def get_knowledge_embedding_dimension() -> int:
    settings = resolve_embedding_settings(scope="knowledge_base")
    try:
        dimension = int(settings.get("dimension") or 0)
    except (TypeError, ValueError):
        dimension = 0
    return dimension if dimension > 0 else 768


def _get_index_type() -> str:
    return str(get_config().get("database.milvus.index_type", "IVF_FLAT") or "IVF_FLAT")


def _get_metric_type() -> str:
    return str(get_config().get("database.milvus.metric_type", "L2") or "L2")


def create_knowledge_embeddings_schema() -> CollectionSchema:
    embedding_dim = get_knowledge_embedding_dimension()
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True,
            description="Primary key",
        ),
        FieldSchema(
            name="knowledge_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="References PostgreSQL knowledge_items",
        ),
        FieldSchema(
            name="chunk_index",
            dtype=DataType.INT32,
            description="Index of the chunk within the document",
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=embedding_dim,
            description="Knowledge embedding vector",
        ),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=65535,
            description="Chunk content text",
        ),
        FieldSchema(
            name="owner_user_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="Owner user identifier",
        ),
        FieldSchema(
            name="access_level",
            dtype=DataType.VARCHAR,
            max_length=50,
            description="Access level (private, team, public)",
        ),
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
            description="Additional metadata (document_title, page_number, section)",
        ),
    ]
    return CollectionSchema(
        fields=fields,
        description="Knowledge base document embeddings",
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


def ensure_knowledge_embeddings_collection(drop_if_exists: bool = False) -> Collection:
    manager = get_milvus_connection()

    if manager.collection_exists(KNOWLEDGE_EMBEDDINGS_COLLECTION):
        if drop_if_exists:
            logger.warning("Dropping existing collection: %s", KNOWLEDGE_EMBEDDINGS_COLLECTION)
            manager.drop_collection(KNOWLEDGE_EMBEDDINGS_COLLECTION)
        else:
            collection = manager.get_collection(KNOWLEDGE_EMBEDDINGS_COLLECTION)
            collection.load()
            return collection

    collection = Collection(
        name=KNOWLEDGE_EMBEDDINGS_COLLECTION,
        schema=create_knowledge_embeddings_schema(),
        using=manager.connection_alias,
    )
    _create_index(collection)
    collection.load()
    return collection


def recreate_knowledge_embeddings_collection() -> Collection:
    return ensure_knowledge_embeddings_collection(drop_if_exists=True)


__all__ = [
    "KNOWLEDGE_EMBEDDINGS_COLLECTION",
    "create_knowledge_embeddings_schema",
    "ensure_knowledge_embeddings_collection",
    "get_knowledge_embedding_dimension",
    "recreate_knowledge_embeddings_collection",
]
