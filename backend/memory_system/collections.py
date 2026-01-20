"""Milvus collection schemas and management.

This module defines the schemas for all Milvus collections and provides
functions to create and manage them.

Collections:
- agent_memories: Private memories for individual agents
- company_memories: Shared memories across agents
- knowledge_embeddings: Knowledge base document embeddings

References:
- Requirements 3.2: Vector Database for Semantic Search
- Design Section 3.1: Milvus Collections (Vector Database)
"""

import logging
from typing import Dict, Any, List, Optional
from enum import Enum

from pymilvus import (
    Collection,
    CollectionSchema,
    FieldSchema,
    DataType,
    utility,
)

from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config

logger = logging.getLogger(__name__)


class CollectionName(str, Enum):
    """Enum for collection names."""
    AGENT_MEMORIES = "agent_memories"
    COMPANY_MEMORIES = "company_memories"
    KNOWLEDGE_EMBEDDINGS = "knowledge_embeddings"


class IndexType(str, Enum):
    """Enum for index types."""
    IVF_FLAT = "IVF_FLAT"
    HNSW = "HNSW"
    IVF_SQ8 = "IVF_SQ8"
    IVF_PQ = "IVF_PQ"


class MetricType(str, Enum):
    """Enum for similarity metric types."""
    L2 = "L2"  # Euclidean distance
    IP = "IP"  # Inner product
    COSINE = "COSINE"  # Cosine similarity


def get_embedding_dimension() -> int:
    """
    Get the embedding dimension from configuration.
    
    Returns:
        int: Embedding dimension (default: 768)
    """
    config = get_config()
    return config.get('memory.embedding.dimension', 768)


def get_index_type() -> str:
    """
    Get the index type from configuration.
    
    Returns:
        str: Index type (IVF_FLAT or HNSW)
    """
    config = get_config()
    return config.get('database.milvus.index_type', 'IVF_FLAT')


def get_metric_type() -> str:
    """
    Get the metric type from configuration.
    
    Returns:
        str: Metric type (L2, IP, or COSINE)
    """
    config = get_config()
    return config.get('database.milvus.metric_type', 'L2')


def create_agent_memories_schema() -> CollectionSchema:
    """
    Create schema for agent_memories collection.
    
    Schema:
    - id (INT64, PK, auto-increment): Primary key
    - agent_id (VARCHAR): Agent identifier for filtering
    - embedding (FLOAT_VECTOR): Memory embedding vector
    - content (VARCHAR): Memory content text
    - timestamp (INT64): Unix timestamp in milliseconds
    - metadata (JSON): Additional metadata (task_id, importance, tags)
    
    Partitions: By agent_id for efficient filtering
    Indexes: IVF_FLAT or HNSW for similarity search
    
    Returns:
        CollectionSchema: Schema for agent_memories collection
    """
    embedding_dim = get_embedding_dimension()
    
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True,
            description="Primary key"
        ),
        FieldSchema(
            name="agent_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="Agent identifier for filtering"
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=embedding_dim,
            description="Memory embedding vector"
        ),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=65535,
            description="Memory content text"
        ),
        FieldSchema(
            name="timestamp",
            dtype=DataType.INT64,
            description="Unix timestamp in milliseconds"
        ),
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
            description="Additional metadata (task_id, importance, tags)"
        ),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Agent private memories for individual agents",
        enable_dynamic_field=False
    )
    
    return schema


def create_company_memories_schema() -> CollectionSchema:
    """
    Create schema for company_memories collection.
    
    Schema:
    - id (INT64, PK, auto-increment): Primary key
    - user_id (VARCHAR): User identifier for User Context filtering
    - embedding (FLOAT_VECTOR): Memory embedding vector
    - content (VARCHAR): Memory content text
    - memory_type (VARCHAR): Type of memory (user_context, task_context, general)
    - timestamp (INT64): Unix timestamp in milliseconds
    - metadata (JSON): Additional metadata (task_id, shared_with, tags)
    
    Partitions: By user_id and memory_type
    Indexes: IVF_FLAT or HNSW for similarity search
    
    Returns:
        CollectionSchema: Schema for company_memories collection
    """
    embedding_dim = get_embedding_dimension()
    
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True,
            description="Primary key"
        ),
        FieldSchema(
            name="user_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="User identifier for User Context filtering"
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=embedding_dim,
            description="Memory embedding vector"
        ),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=65535,
            description="Memory content text"
        ),
        FieldSchema(
            name="memory_type",
            dtype=DataType.VARCHAR,
            max_length=50,
            description="Type of memory (user_context, task_context, general)"
        ),
        FieldSchema(
            name="timestamp",
            dtype=DataType.INT64,
            description="Unix timestamp in milliseconds"
        ),
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
            description="Additional metadata (task_id, shared_with, tags)"
        ),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Company shared memories accessible to all agents",
        enable_dynamic_field=False
    )
    
    return schema


def create_knowledge_embeddings_schema() -> CollectionSchema:
    """
    Create schema for knowledge_embeddings collection.
    
    Schema:
    - id (INT64, PK, auto-increment): Primary key
    - knowledge_id (VARCHAR): References PostgreSQL knowledge_items
    - chunk_index (INT32): Index of the chunk within the document
    - embedding (FLOAT_VECTOR): Knowledge embedding vector
    - content (VARCHAR): Chunk content text
    - owner_user_id (VARCHAR): Owner user identifier
    - access_level (VARCHAR): Access level (private, team, public)
    - metadata (JSON): Additional metadata (document_title, page_number, section)
    
    Partitions: By access_level for permission filtering
    Indexes: IVF_FLAT or HNSW for similarity search
    
    Returns:
        CollectionSchema: Schema for knowledge_embeddings collection
    """
    embedding_dim = get_embedding_dimension()
    
    fields = [
        FieldSchema(
            name="id",
            dtype=DataType.INT64,
            is_primary=True,
            auto_id=True,
            description="Primary key"
        ),
        FieldSchema(
            name="knowledge_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="References PostgreSQL knowledge_items"
        ),
        FieldSchema(
            name="chunk_index",
            dtype=DataType.INT32,
            description="Index of the chunk within the document"
        ),
        FieldSchema(
            name="embedding",
            dtype=DataType.FLOAT_VECTOR,
            dim=embedding_dim,
            description="Knowledge embedding vector"
        ),
        FieldSchema(
            name="content",
            dtype=DataType.VARCHAR,
            max_length=65535,
            description="Chunk content text"
        ),
        FieldSchema(
            name="owner_user_id",
            dtype=DataType.VARCHAR,
            max_length=255,
            description="Owner user identifier"
        ),
        FieldSchema(
            name="access_level",
            dtype=DataType.VARCHAR,
            max_length=50,
            description="Access level (private, team, public)"
        ),
        FieldSchema(
            name="metadata",
            dtype=DataType.JSON,
            description="Additional metadata (document_title, page_number, section)"
        ),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Knowledge base document embeddings",
        enable_dynamic_field=False
    )
    
    return schema


def create_collection(
    collection_name: str,
    schema: CollectionSchema,
    drop_if_exists: bool = False
) -> Collection:
    """
    Create a Milvus collection with the given schema.
    
    Args:
        collection_name: Name of the collection
        schema: Collection schema
        drop_if_exists: Whether to drop the collection if it already exists
        
    Returns:
        Collection: Created collection object
    """
    manager = get_milvus_connection()
    
    try:
        # Check if collection exists
        if manager.collection_exists(collection_name):
            if drop_if_exists:
                logger.warning(f"Dropping existing collection: {collection_name}")
                manager.drop_collection(collection_name)
            else:
                logger.info(f"Collection already exists: {collection_name}")
                return manager.get_collection(collection_name)
        
        # Create collection
        collection = Collection(
            name=collection_name,
            schema=schema,
            using=manager.connection_alias
        )
        
        logger.info(f"Created collection: {collection_name}")
        return collection
        
    except Exception as e:
        logger.error(f"Failed to create collection '{collection_name}': {e}")
        raise


def create_index(
    collection: Collection,
    field_name: str = "embedding",
    index_type: Optional[str] = None,
    metric_type: Optional[str] = None,
    index_params: Optional[Dict[str, Any]] = None
) -> None:
    """
    Create an index on a collection field.
    
    Args:
        collection: Collection object
        field_name: Name of the field to index (default: "embedding")
        index_type: Type of index (IVF_FLAT, HNSW, etc.)
        metric_type: Similarity metric (L2, IP, COSINE)
        index_params: Additional index parameters
    """
    config = get_config()
    milvus_config = config.get_section('database.milvus')
    
    # Use provided values or fall back to config
    if index_type is None:
        index_type = get_index_type()
    
    if metric_type is None:
        metric_type = get_metric_type()
    
    # Build index parameters based on index type
    if index_params is None:
        if index_type == IndexType.IVF_FLAT:
            index_params = {
                "nlist": milvus_config.get('nlist', 1024)
            }
        elif index_type == IndexType.HNSW:
            index_params = {
                "M": milvus_config.get('hnsw_m', 16),
                "efConstruction": milvus_config.get('hnsw_ef_construction', 200)
            }
        elif index_type == IndexType.IVF_SQ8:
            index_params = {
                "nlist": milvus_config.get('nlist', 1024)
            }
        elif index_type == IndexType.IVF_PQ:
            index_params = {
                "nlist": milvus_config.get('nlist', 1024),
                "m": 8,  # Number of sub-quantizers
                "nbits": 8  # Number of bits per sub-quantizer
            }
        else:
            index_params = {}
    
    try:
        # Create index
        index_config = {
            "index_type": index_type,
            "metric_type": metric_type,
            "params": index_params
        }
        
        collection.create_index(
            field_name=field_name,
            index_params=index_config
        )
        
        logger.info(
            f"Created index on {collection.name}.{field_name}: "
            f"type={index_type}, metric={metric_type}, params={index_params}"
        )
        
    except Exception as e:
        logger.error(f"Failed to create index on {collection.name}.{field_name}: {e}")
        raise


def create_partition(
    collection: Collection,
    partition_name: str
) -> None:
    """
    Create a partition in a collection.
    
    Args:
        collection: Collection object
        partition_name: Name of the partition
    """
    try:
        # Check if partition already exists
        if collection.has_partition(partition_name):
            logger.info(f"Partition already exists: {collection.name}.{partition_name}")
            return
        
        # Create partition
        collection.create_partition(partition_name)
        
        logger.info(f"Created partition: {collection.name}.{partition_name}")
        
    except Exception as e:
        logger.error(f"Failed to create partition '{partition_name}' in {collection.name}: {e}")
        raise


def load_collection(collection: Collection) -> None:
    """
    Load a collection into memory for searching.
    
    Args:
        collection: Collection object
    """
    try:
        collection.load()
        logger.info(f"Loaded collection into memory: {collection.name}")
    except Exception as e:
        logger.error(f"Failed to load collection {collection.name}: {e}")
        raise


def initialize_all_collections(drop_if_exists: bool = False) -> Dict[str, Collection]:
    """
    Initialize all Milvus collections with schemas and indexes.
    
    This function creates all required collections, indexes, and partitions
    according to the design document.
    
    Args:
        drop_if_exists: Whether to drop existing collections
        
    Returns:
        dict: Dictionary mapping collection names to Collection objects
    """
    logger.info("Initializing Milvus collections...")
    
    collections = {}
    
    try:
        # 1. Create agent_memories collection
        logger.info("Creating agent_memories collection...")
        agent_memories_schema = create_agent_memories_schema()
        agent_memories = create_collection(
            CollectionName.AGENT_MEMORIES,
            agent_memories_schema,
            drop_if_exists=drop_if_exists
        )
        create_index(agent_memories, field_name="embedding")
        load_collection(agent_memories)
        collections[CollectionName.AGENT_MEMORIES] = agent_memories
        
        # 2. Create company_memories collection
        logger.info("Creating company_memories collection...")
        company_memories_schema = create_company_memories_schema()
        company_memories = create_collection(
            CollectionName.COMPANY_MEMORIES,
            company_memories_schema,
            drop_if_exists=drop_if_exists
        )
        create_index(company_memories, field_name="embedding")
        load_collection(company_memories)
        collections[CollectionName.COMPANY_MEMORIES] = company_memories
        
        # 3. Create knowledge_embeddings collection
        logger.info("Creating knowledge_embeddings collection...")
        knowledge_embeddings_schema = create_knowledge_embeddings_schema()
        knowledge_embeddings = create_collection(
            CollectionName.KNOWLEDGE_EMBEDDINGS,
            knowledge_embeddings_schema,
            drop_if_exists=drop_if_exists
        )
        create_index(knowledge_embeddings, field_name="embedding")
        load_collection(knowledge_embeddings)
        collections[CollectionName.KNOWLEDGE_EMBEDDINGS] = knowledge_embeddings
        
        logger.info(f"Successfully initialized {len(collections)} collections")
        return collections
        
    except Exception as e:
        logger.error(f"Failed to initialize collections: {e}")
        raise


def get_collection_info(collection_name: str) -> Dict[str, Any]:
    """
    Get detailed information about a collection.
    
    Args:
        collection_name: Name of the collection
        
    Returns:
        dict: Collection information
    """
    manager = get_milvus_connection()
    return manager.get_collection_stats(collection_name)
