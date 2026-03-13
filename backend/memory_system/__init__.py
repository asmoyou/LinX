"""Shared low-level embedding and Milvus connection helpers."""

from memory_system.embedding_service import (
    EmbeddingServiceInterface,
    OllamaEmbeddingService,
    VLLMEmbeddingService,
    get_embedding_service,
    resolve_embedding_settings,
    set_embedding_service,
)
from memory_system.milvus_connection import (
    MilvusConnectionManager,
    close_milvus_connection,
    get_milvus_connection,
)

__all__ = [
    "MilvusConnectionManager",
    "get_milvus_connection",
    "close_milvus_connection",
    "EmbeddingServiceInterface",
    "OllamaEmbeddingService",
    "VLLMEmbeddingService",
    "get_embedding_service",
    "resolve_embedding_settings",
    "set_embedding_service",
]
