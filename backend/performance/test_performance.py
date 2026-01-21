"""Tests for performance optimization module.

References:
- Requirements 8: Scalability and Performance
- Design Section 10: Scalability and Performance
"""

import pytest

from performance.cache_manager import CacheManager, CacheStats, get_cache_manager
from performance.connection_pool import (
    ConnectionPool,
    ConnectionPoolManager,
    PoolStats,
    get_pool_manager,
)
from performance.query_optimizer import IndexRecommendation, QueryOptimizer, QueryStats
from performance.vector_optimizer import (
    IndexConfig,
    IndexType,
    SearchConfig,
    VectorSearchOptimizer,
)

# Query Optimizer Tests


def test_query_optimizer_initialization():
    """Test query optimizer initialization."""
    optimizer = QueryOptimizer(slow_query_threshold_ms=500)

    assert optimizer.slow_query_threshold_ms == 500
    assert len(optimizer.query_stats) == 0
    assert len(optimizer.slow_queries) == 0


def test_analyze_query_missing_where():
    """Test query analysis detects missing WHERE clause."""
    optimizer = QueryOptimizer()

    query = "SELECT * FROM users"
    analysis = optimizer.analyze_query(query)

    assert "Missing WHERE clause" in str(analysis["issues"])
    assert "Using SELECT *" in str(analysis["issues"])


def test_analyze_query_with_subqueries():
    """Test query analysis detects subqueries."""
    optimizer = QueryOptimizer()

    query = "SELECT * FROM users WHERE id IN (SELECT user_id FROM orders)"
    analysis = optimizer.analyze_query(query)

    assert "subqueries" in str(analysis["issues"]).lower()


def test_track_query_execution():
    """Test query execution tracking."""
    optimizer = QueryOptimizer()

    query = "SELECT * FROM users WHERE id = 1"
    optimizer.track_query_execution(query, 150.0)
    optimizer.track_query_execution(query, 200.0)

    assert len(optimizer.query_stats) == 1
    stats = list(optimizer.query_stats.values())[0]
    assert stats.execution_count == 2
    assert stats.avg_time_ms == 175.0


def test_track_slow_query():
    """Test slow query detection."""
    optimizer = QueryOptimizer(slow_query_threshold_ms=100)

    query = "SELECT * FROM large_table"
    optimizer.track_query_execution(query, 500.0)

    assert len(optimizer.slow_queries) == 1
    assert optimizer.slow_queries[0].avg_time_ms == 500.0


def test_get_slow_queries():
    """Test getting slowest queries."""
    optimizer = QueryOptimizer(slow_query_threshold_ms=100)

    optimizer.track_query_execution("SELECT * FROM table1", 500.0)
    optimizer.track_query_execution("SELECT * FROM table2", 300.0)
    optimizer.track_query_execution("SELECT * FROM table3", 200.0)

    slow_queries = optimizer.get_slow_queries(limit=2)

    assert len(slow_queries) == 2
    assert slow_queries[0].avg_time_ms >= slow_queries[1].avg_time_ms


def test_get_most_frequent_queries():
    """Test getting most frequent queries."""
    optimizer = QueryOptimizer()

    query1 = "SELECT * FROM users WHERE id = 1"
    query2 = "SELECT * FROM orders WHERE user_id = 1"

    for _ in range(5):
        optimizer.track_query_execution(query1, 50.0)

    for _ in range(3):
        optimizer.track_query_execution(query2, 50.0)

    frequent = optimizer.get_most_frequent_queries(limit=2)

    assert len(frequent) == 2
    assert frequent[0].execution_count == 5
    assert frequent[1].execution_count == 3


def test_recommend_indexes():
    """Test index recommendations."""
    optimizer = QueryOptimizer()

    query = "SELECT * FROM users WHERE email = 'test@example.com'"
    optimizer.track_query_execution(query, 100.0)

    recommendations = optimizer.recommend_indexes("users")

    assert len(recommendations) > 0
    assert all(isinstance(rec, IndexRecommendation) for rec in recommendations)


def test_get_optimization_report():
    """Test optimization report generation."""
    optimizer = QueryOptimizer()

    optimizer.track_query_execution("SELECT * FROM users", 100.0)
    optimizer.track_query_execution("SELECT * FROM orders", 200.0)

    report = optimizer.get_optimization_report()

    assert "summary" in report
    assert "slow_queries" in report
    assert "frequent_queries" in report
    assert report["summary"]["total_queries"] == 2


# Cache Manager Tests


def test_cache_manager_initialization():
    """Test cache manager initialization."""
    cache = CacheManager(default_ttl=3600)

    assert cache.default_ttl == 3600
    assert len(cache.cache) == 0
    assert cache.stats.hits == 0


def test_cache_set_and_get():
    """Test cache set and get operations."""
    cache = CacheManager()

    cache.set("key1", "value1")
    value = cache.get("key1")

    assert value == "value1"
    assert cache.stats.sets == 1
    assert cache.stats.hits == 1


def test_cache_miss():
    """Test cache miss."""
    cache = CacheManager()

    value = cache.get("nonexistent")

    assert value is None
    assert cache.stats.misses == 1


def test_cache_delete():
    """Test cache delete operation."""
    cache = CacheManager()

    cache.set("key1", "value1")
    deleted = cache.delete("key1")

    assert deleted is True
    assert cache.get("key1") is None
    assert cache.stats.deletes == 1


def test_cache_exists():
    """Test cache exists check."""
    cache = CacheManager()

    cache.set("key1", "value1")

    assert cache.exists("key1") is True
    assert cache.exists("nonexistent") is False


def test_cache_clear():
    """Test cache clear operation."""
    cache = CacheManager()

    cache.set("key1", "value1")
    cache.set("key2", "value2")
    cache.clear()

    assert len(cache.cache) == 0


def test_cache_get_or_set():
    """Test cache get_or_set operation."""
    cache = CacheManager()

    def factory():
        return "generated_value"

    # First call should generate value
    value1 = cache.get_or_set("key1", factory)
    assert value1 == "generated_value"
    assert cache.stats.sets == 1

    # Second call should use cached value
    value2 = cache.get_or_set("key1", factory)
    assert value2 == "generated_value"
    assert cache.stats.hits == 1


def test_cache_stats():
    """Test cache statistics."""
    cache = CacheManager()

    cache.set("key1", "value1")
    cache.get("key1")
    cache.get("nonexistent")

    stats = cache.get_stats()

    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["sets"] == 1
    assert "hit_rate" in stats


def test_cache_invalidate_pattern():
    """Test cache pattern invalidation."""
    cache = CacheManager()

    cache.set("user:1:profile", "data1")
    cache.set("user:2:profile", "data2")
    cache.set("order:1:details", "data3")

    cache.invalidate_pattern("user:*")

    assert cache.get("user:1:profile") is None
    assert cache.get("user:2:profile") is None
    assert cache.get("order:1:details") == "data3"


def test_cache_user_session():
    """Test user session caching."""
    cache = CacheManager()

    session_data = {"user_id": "123", "token": "abc"}
    cache.cache_user_session("123", session_data)

    retrieved = cache.get_user_session("123")

    assert retrieved == session_data


def test_cache_agent_config():
    """Test agent configuration caching."""
    cache = CacheManager()

    config = {"model": "gpt-4", "temperature": 0.7}
    cache.cache_agent_config("agent-1", config)

    retrieved = cache.get_agent_config("agent-1")

    assert retrieved == config


def test_cache_api_response():
    """Test API response caching."""
    cache = CacheManager()

    params = {"page": 1, "limit": 10}
    response = {"data": [1, 2, 3]}

    cache.cache_api_response("/api/users", params, response)
    retrieved = cache.get_api_response("/api/users", params)

    assert retrieved == response


def test_get_cache_manager_singleton():
    """Test cache manager singleton."""
    manager1 = get_cache_manager()
    manager2 = get_cache_manager()

    assert manager1 is manager2


# Vector Search Optimizer Tests


def test_vector_optimizer_initialization():
    """Test vector search optimizer initialization."""
    optimizer = VectorSearchOptimizer()

    assert len(optimizer.index_configs) == 0
    assert len(optimizer.search_configs) == 0


def test_recommend_index_type_small_collection():
    """Test index type recommendation for small collection."""
    optimizer = VectorSearchOptimizer()

    index_type = optimizer.recommend_index_type(
        collection_size=5000,
        vector_dim=768,
        accuracy_requirement=0.95,
    )

    assert index_type == IndexType.FLAT


def test_recommend_index_type_medium_collection():
    """Test index type recommendation for medium collection."""
    optimizer = VectorSearchOptimizer()

    index_type = optimizer.recommend_index_type(
        collection_size=500000,
        vector_dim=768,
        accuracy_requirement=0.96,
    )

    assert index_type == IndexType.IVF_FLAT


def test_recommend_index_type_large_collection():
    """Test index type recommendation for large collection."""
    optimizer = VectorSearchOptimizer()

    index_type = optimizer.recommend_index_type(
        collection_size=5000000,
        vector_dim=768,
        accuracy_requirement=0.96,
    )

    assert index_type == IndexType.HNSW


def test_create_index_config_ivf():
    """Test IVF index configuration creation."""
    optimizer = VectorSearchOptimizer()

    config = optimizer.create_index_config(
        collection_name="test_collection",
        index_type=IndexType.IVF_FLAT,
        collection_size=1000000,
    )

    assert config.index_type == IndexType.IVF_FLAT
    assert config.nlist > 0


def test_create_index_config_hnsw():
    """Test HNSW index configuration creation."""
    optimizer = VectorSearchOptimizer()

    config = optimizer.create_index_config(
        collection_name="test_collection",
        index_type=IndexType.HNSW,
        collection_size=1000000,
    )

    assert config.index_type == IndexType.HNSW
    assert config.M == 16
    assert config.ef_construction == 200


def test_create_search_config():
    """Test search configuration creation."""
    optimizer = VectorSearchOptimizer()

    # Create index config first
    optimizer.create_index_config(
        collection_name="test_collection",
        index_type=IndexType.IVF_FLAT,
        collection_size=1000000,
    )

    # Create search config
    search_config = optimizer.create_search_config(
        collection_name="test_collection",
        accuracy_requirement=0.95,
    )

    assert search_config.nprobe > 0


def test_optimize_batch_size():
    """Test batch size optimization."""
    optimizer = VectorSearchOptimizer()

    # Small dimension
    batch_size = optimizer.optimize_batch_size(num_queries=200, vector_dim=64)
    assert batch_size == 100

    # Medium dimension
    batch_size = optimizer.optimize_batch_size(num_queries=200, vector_dim=256)
    assert batch_size == 50

    # Large dimension
    batch_size = optimizer.optimize_batch_size(num_queries=200, vector_dim=1024)
    assert batch_size == 20


def test_get_optimization_recommendations():
    """Test optimization recommendations."""
    optimizer = VectorSearchOptimizer()

    optimizer.create_index_config(
        collection_name="test_collection",
        index_type=IndexType.FLAT,
        collection_size=1000000,
    )

    recommendations = optimizer.get_optimization_recommendations(
        collection_name="test_collection",
        current_qps=150,
        current_latency_ms=500,
        target_latency_ms=100,
    )

    assert len(recommendations) > 0
    assert any("FLAT" in rec for rec in recommendations)


def test_get_performance_report():
    """Test performance report generation."""
    optimizer = VectorSearchOptimizer()

    optimizer.create_index_config(
        collection_name="test_collection",
        index_type=IndexType.IVF_FLAT,
        collection_size=1000000,
    )

    optimizer.create_search_config(
        collection_name="test_collection",
        accuracy_requirement=0.95,
    )

    report = optimizer.get_performance_report()

    assert report["collections"] == 1
    assert "test_collection" in report["index_configs"]
    assert "test_collection" in report["search_configs"]


# Connection Pool Tests


def test_connection_pool_initialization():
    """Test connection pool initialization."""
    pool = ConnectionPool(name="test_pool", min_size=5, max_size=20)

    assert pool.name == "test_pool"
    assert pool.min_size == 5
    assert pool.max_size == 20
    assert len(pool.connections) == 0


def test_connection_pool_acquire():
    """Test connection acquisition."""
    pool = ConnectionPool(name="test_pool", max_size=10)

    conn = pool.acquire()

    assert conn is not None
    assert len(pool.connections) == 1
    assert len(pool.active) == 1


def test_connection_pool_release():
    """Test connection release."""
    pool = ConnectionPool(name="test_pool", max_size=10)

    conn = pool.acquire()
    pool.release(conn)

    assert len(pool.active) == 0
    assert len(pool.connections) == 1


def test_connection_pool_reuse():
    """Test connection reuse."""
    pool = ConnectionPool(name="test_pool", max_size=10)

    conn1 = pool.acquire()
    pool.release(conn1)

    conn2 = pool.acquire()

    assert conn1 == conn2
    assert len(pool.connections) == 1


def test_connection_pool_exhaustion():
    """Test connection pool exhaustion."""
    pool = ConnectionPool(name="test_pool", max_size=2)

    conn1 = pool.acquire()
    conn2 = pool.acquire()

    with pytest.raises(RuntimeError, match="exhausted"):
        pool.acquire()


def test_connection_pool_stats():
    """Test connection pool statistics."""
    pool = ConnectionPool(name="test_pool", max_size=10)

    conn1 = pool.acquire()
    conn2 = pool.acquire()
    pool.release(conn1)

    stats = pool.get_stats()

    assert stats["total_connections"] == 2
    assert stats["active_connections"] == 1
    assert stats["idle_connections"] == 1


def test_connection_pool_close():
    """Test connection pool close."""
    pool = ConnectionPool(name="test_pool", max_size=10)

    pool.acquire()
    pool.acquire()
    pool.close()

    assert len(pool.connections) == 0
    assert len(pool.active) == 0


def test_connection_pool_manager_initialization():
    """Test connection pool manager initialization."""
    manager = ConnectionPoolManager()

    assert len(manager.pools) == 0


def test_connection_pool_manager_create_pool():
    """Test creating pool via manager."""
    manager = ConnectionPoolManager()

    pool = manager.create_pool(name="test_pool", min_size=5, max_size=20)

    assert pool.name == "test_pool"
    assert "test_pool" in manager.pools


def test_connection_pool_manager_get_pool():
    """Test getting pool from manager."""
    manager = ConnectionPoolManager()

    manager.create_pool(name="test_pool")
    pool = manager.get_pool("test_pool")

    assert pool is not None
    assert pool.name == "test_pool"


def test_connection_pool_manager_create_postgres_pool():
    """Test creating PostgreSQL pool."""
    manager = ConnectionPoolManager()

    pool = manager.create_postgres_pool(min_size=10, max_size=50)

    assert pool.name == "postgresql"
    assert pool.min_size == 10
    assert pool.max_size == 50


def test_connection_pool_manager_create_milvus_pool():
    """Test creating Milvus pool."""
    manager = ConnectionPoolManager()

    pool = manager.create_milvus_pool(min_size=5, max_size=20)

    assert pool.name == "milvus"
    assert pool.min_size == 5
    assert pool.max_size == 20


def test_connection_pool_manager_create_redis_pool():
    """Test creating Redis pool."""
    manager = ConnectionPoolManager()

    pool = manager.create_redis_pool(min_size=10, max_size=30)

    assert pool.name == "redis"
    assert pool.min_size == 10
    assert pool.max_size == 30


def test_connection_pool_manager_create_minio_pool():
    """Test creating MinIO pool."""
    manager = ConnectionPoolManager()

    pool = manager.create_minio_pool(min_size=5, max_size=15)

    assert pool.name == "minio"
    assert pool.min_size == 5
    assert pool.max_size == 15


def test_connection_pool_manager_get_all_stats():
    """Test getting all pool statistics."""
    manager = ConnectionPoolManager()

    manager.create_postgres_pool()
    manager.create_redis_pool()

    stats = manager.get_all_stats()

    assert "postgresql" in stats
    assert "redis" in stats


def test_connection_pool_manager_close_all():
    """Test closing all pools."""
    manager = ConnectionPoolManager()

    manager.create_postgres_pool()
    manager.create_redis_pool()
    manager.close_all()

    assert len(manager.pools) == 0


def test_get_pool_manager_singleton():
    """Test pool manager singleton."""
    manager1 = get_pool_manager()
    manager2 = get_pool_manager()

    assert manager1 is manager2
