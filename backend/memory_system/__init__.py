"""Memory System module for Digital Workforce Platform.

This module provides multi-tiered memory management including:
- Agent Memory (private to each agent)
- Company Memory (shared across agents)
- User Context (user-specific information accessible to all user's agents)
- Vector database integration with Milvus for semantic search

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 3.1: Milvus Collections
- Design Section 6: Memory System Architecture
"""

from memory_system.collections import (
    CollectionName,
    IndexType,
    MetricType,
    create_agent_memories_schema,
    create_collection,
    create_company_memories_schema,
    create_index,
    create_knowledge_embeddings_schema,
    create_partition,
    get_collection_info,
    initialize_all_collections,
    load_collection,
)
from memory_system.embedding_service import (
    OllamaEmbeddingService,
    VLLMEmbeddingService,
    get_embedding_service,
    set_embedding_service,
)
from memory_system.memory_interface import (
    EmbeddingServiceInterface,
    MemoryItem,
    MemorySystemInterface,
    MemoryType,
    SearchQuery,
)
from memory_system.memory_system import (
    MemorySystem,
    get_memory_system,
)
from memory_system.milvus_connection import (
    MilvusConnectionManager,
    close_milvus_connection,
    get_milvus_connection,
)
from memory_system.partitions import (
    PartitionManager,
    get_partition_manager,
)

__all__ = [
    # Connection management
    "MilvusConnectionManager",
    "get_milvus_connection",
    "close_milvus_connection",
    # Collection management
    "CollectionName",
    "IndexType",
    "MetricType",
    "create_agent_memories_schema",
    "create_company_memories_schema",
    "create_knowledge_embeddings_schema",
    "create_collection",
    "create_index",
    "create_partition",
    "load_collection",
    "initialize_all_collections",
    "get_collection_info",
    # Partition management
    "PartitionManager",
    "get_partition_manager",
    # Memory System interface
    "MemorySystemInterface",
    "EmbeddingServiceInterface",
    "MemoryItem",
    "MemoryType",
    "SearchQuery",
    # Embedding service
    "OllamaEmbeddingService",
    "VLLMEmbeddingService",
    "get_embedding_service",
    "set_embedding_service",
    # Memory System implementation
    "MemorySystem",
    "get_memory_system",
]
