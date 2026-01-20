# Memory System - Milvus Vector Database

This module implements the vector database layer for the Digital Workforce Platform using Milvus.

## Overview

The memory system provides multi-tiered memory management with semantic search capabilities:

- **Agent Memory**: Private memories for individual agents
- **Company Memory**: Shared memories across agents
- **User Context**: User-specific information accessible to all user's agents
- **Knowledge Embeddings**: Knowledge base document embeddings

## Components

### 1. Connection Manager (`milvus_connection.py`)

Manages connections to Milvus with connection pooling and health checks.

**Features:**
- Singleton connection manager
- Automatic reconnection on failure
- Health checks
- Collection management
- Connection status monitoring

**Usage:**
```python
from memory_system import get_milvus_connection, close_milvus_connection

# Get connection
manager = get_milvus_connection()

# Check health
is_healthy = manager.health_check()

# Get collection
collection = manager.get_collection("agent_memories")

# Close connection (on shutdown)
close_milvus_connection()
```

### 2. Collection Schemas (`collections.py`)

Defines schemas for all Milvus collections according to the design document.

**Collections:**

#### agent_memories
- `id` (INT64, PK, auto-increment): Primary key
- `agent_id` (VARCHAR): Agent identifier for filtering
- `embedding` (FLOAT_VECTOR, dim=768): Memory embedding vector
- `content` (VARCHAR): Memory content text
- `timestamp` (INT64): Unix timestamp in milliseconds
- `metadata` (JSON): Additional metadata (task_id, importance, tags)

**Partitions**: By agent_id for efficient filtering  
**Indexes**: IVF_FLAT or HNSW for similarity search

#### company_memories
- `id` (INT64, PK, auto-increment): Primary key
- `user_id` (VARCHAR): User identifier for User Context filtering
- `embedding` (FLOAT_VECTOR, dim=768): Memory embedding vector
- `content` (VARCHAR): Memory content text
- `memory_type` (VARCHAR): Type of memory (user_context, task_context, general)
- `timestamp` (INT64): Unix timestamp in milliseconds
- `metadata` (JSON): Additional metadata (task_id, shared_with, tags)

**Partitions**: By user_id and memory_type  
**Indexes**: IVF_FLAT or HNSW for similarity search

#### knowledge_embeddings
- `id` (INT64, PK, auto-increment): Primary key
- `knowledge_id` (VARCHAR): References PostgreSQL knowledge_items
- `chunk_index` (INT32): Index of the chunk within the document
- `embedding` (FLOAT_VECTOR, dim=768): Knowledge embedding vector
- `content` (VARCHAR): Chunk content text
- `owner_user_id` (VARCHAR): Owner user identifier
- `access_level` (VARCHAR): Access level (private, team, public)
- `metadata` (JSON): Additional metadata (document_title, page_number, section)

**Partitions**: By access_level for permission filtering  
**Indexes**: IVF_FLAT or HNSW for similarity search

**Usage:**
```python
from memory_system import initialize_all_collections

# Initialize all collections with schemas and indexes
collections = initialize_all_collections(drop_if_exists=False)

# Access individual collections
agent_memories = collections['agent_memories']
company_memories = collections['company_memories']
knowledge_embeddings = collections['knowledge_embeddings']
```

### 3. Partition Manager (`partitions.py`)

Manages partitions for efficient data organization and filtering.

**Features:**
- Create partitions by agent_id, user_id, memory_type, access_level
- List and drop partitions
- Get partition statistics
- Initialize default partitions
- Get partitions for search based on filters

**Usage:**
```python
from memory_system import get_partition_manager

manager = get_partition_manager()

# Create agent partition
partition_name = manager.create_agent_partition("agent_123")

# Create user partition
partition_name = manager.create_user_partition("user_456")

# Initialize default partitions
manager.initialize_default_partitions()

# Get partitions for search
partitions = manager.get_partitions_for_search(
    collection_name="company_memories",
    user_id="user_456",
    memory_type="user_context"
)
```

## Configuration

Configuration is loaded from `backend/config.yaml`:

```yaml
database:
  milvus:
    host: "localhost"
    port: 19530
    user: ""
    password: ""
    collection_prefix: "workforce_"
    index_type: "IVF_FLAT"  # or "HNSW"
    metric_type: "L2"  # or "IP", "COSINE"
    nlist: 1024
    nprobe: 16
    hnsw_m: 16
    hnsw_ef_construction: 200
    hnsw_ef: 64
    timeout: 30
    enable_partitioning: true
    partition_by: "user_id"

memory:
  embedding:
    model: "embedding"
    dimension: 768
    batch_size: 32
```

## Index Types

### IVF_FLAT
- **Description**: Inverted File with Flat compression
- **Use Case**: Balance between speed and accuracy
- **Parameters**:
  - `nlist`: Number of cluster units (default: 1024)
  - `nprobe`: Number of units to query (default: 16)

### HNSW
- **Description**: Hierarchical Navigable Small World
- **Use Case**: High accuracy, faster search
- **Parameters**:
  - `M`: Number of bi-directional links (default: 16)
  - `efConstruction`: Size of dynamic candidate list (default: 200)
  - `ef`: Search scope (default: 64)

## Metric Types

- **L2**: Euclidean distance (default)
- **IP**: Inner product
- **COSINE**: Cosine similarity

## Testing

Run the test script to verify the implementation:

```bash
cd backend
python -m memory_system.test_milvus
```

**Note**: Requires Milvus to be running on localhost:19530 (or configured host/port).

## Docker Setup

Start Milvus using Docker:

```bash
# Standalone mode
docker run -d --name milvus-standalone \
  -p 19530:19530 \
  -p 9091:9091 \
  -v milvus_data:/var/lib/milvus \
  milvusdb/milvus:latest
```

Or use docker-compose (see `infrastructure/docker-compose.yml`).

## Implementation Status

### Completed Tasks

- ✅ 1.3.1: Create Milvus connection manager
- ✅ 1.3.2: Define agent_memories collection schema
- ✅ 1.3.3: Define company_memories collection schema
- ✅ 1.3.4: Define knowledge_embeddings collection schema
- ✅ 1.3.5: Create indexes (IVF_FLAT/HNSW) for each collection
- ✅ 1.3.6: Implement partition management by agent_id and user_id
- ✅ 1.3.7: Add collection initialization on startup
- ✅ 1.3.8: Implement connection pooling for Milvus

### Files Created

1. `backend/memory_system/__init__.py` - Module exports
2. `backend/memory_system/milvus_connection.py` - Connection manager
3. `backend/memory_system/collections.py` - Collection schemas and management
4. `backend/memory_system/partitions.py` - Partition management
5. `backend/memory_system/test_milvus.py` - Test script
6. `backend/memory_system/README.md` - This documentation

## References

- **Requirements**: 3.2 (Vector Database for Semantic Search)
- **Design**: Section 3.1 (Milvus Collections)
- **Tasks**: Section 1.3 (Vector Database Setup - Milvus)

## Next Steps

1. Install pymilvus dependency (requires fixing grpcio compilation on macOS)
2. Run tests to verify implementation
3. Integrate with Memory System (task 2.4)
4. Implement embedding generation service (task 2.3.11)
5. Implement semantic similarity search (task 2.4.6)

## Dependencies

- `pymilvus==2.3.5` - Milvus Python SDK
- `numpy` - For embedding vectors (test only)

## Troubleshooting

### Connection Issues

If you encounter connection errors:

1. Verify Milvus is running: `docker ps | grep milvus`
2. Check Milvus logs: `docker logs milvus-standalone`
3. Verify host/port in config.yaml
4. Test connection: `telnet localhost 19530`

### Collection Creation Issues

If collections fail to create:

1. Check Milvus version compatibility
2. Verify embedding dimension matches configuration
3. Check Milvus disk space
4. Review Milvus logs for errors

### Performance Issues

If searches are slow:

1. Ensure collections are loaded: `collection.load()`
2. Adjust index parameters (nprobe, ef)
3. Consider using HNSW instead of IVF_FLAT
4. Enable partitioning for large datasets
5. Monitor Milvus resource usage

## Architecture Notes

### Connection Pooling

The connection manager uses a singleton pattern to ensure only one connection instance exists. Milvus connections are lightweight and reused across requests.

### Partition Strategy

Partitions are used to improve query performance by reducing the search space:

- **agent_memories**: Partitioned by agent_id
- **company_memories**: Partitioned by user_id and memory_type
- **knowledge_embeddings**: Partitioned by access_level

### Index Selection

- **IVF_FLAT**: Recommended for datasets < 1M vectors
- **HNSW**: Recommended for datasets > 1M vectors or when accuracy is critical

### Embedding Dimension

Default dimension is 768 (compatible with most embedding models). Can be configured in config.yaml under `memory.embedding.dimension`.
