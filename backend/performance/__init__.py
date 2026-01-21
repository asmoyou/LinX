"""Performance optimization module.

References:
- Requirements 8: Scalability and Performance
- Design Section 10: Scalability and Performance

This module provides performance optimization features:
- Database query optimization
- Redis caching layer
- Vector search optimization
- Connection pooling
- Performance monitoring
"""

from performance.query_optimizer import QueryOptimizer
from performance.cache_manager import CacheManager
from performance.vector_optimizer import VectorSearchOptimizer
from performance.connection_pool import ConnectionPoolManager

__all__ = [
    "QueryOptimizer",
    "CacheManager",
    "VectorSearchOptimizer",
    "ConnectionPoolManager",
]
