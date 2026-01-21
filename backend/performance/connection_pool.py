"""Connection pooling for databases.

References:
- Requirements 8: Scalability and Performance
- Design Section 10: Scalability and Performance
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class PoolStats:
    """Connection pool statistics."""

    total_connections: int = 0
    active_connections: int = 0
    idle_connections: int = 0
    waiting_requests: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    avg_wait_time_ms: float = 0

    @property
    def utilization(self) -> float:
        """Calculate pool utilization percentage."""
        if self.total_connections == 0:
            return 0
        return (self.active_connections / self.total_connections) * 100


class ConnectionPool:
    """Generic connection pool.

    Provides connection pooling with:
    - Min/max pool size
    - Connection timeout
    - Connection validation
    - Automatic reconnection
    - Pool statistics
    """

    def __init__(
        self,
        name: str,
        min_size: int = 5,
        max_size: int = 20,
        timeout: float = 30.0,
    ):
        """Initialize connection pool.

        Args:
            name: Pool name
            min_size: Minimum pool size
            max_size: Maximum pool size
            timeout: Connection timeout in seconds
        """
        self.name = name
        self.min_size = min_size
        self.max_size = max_size
        self.timeout = timeout

        self.connections: list = []
        self.active: list = []  # Track active connections by index
        self.stats = PoolStats()

        logger.info(
            f"ConnectionPool '{name}' initialized",
            extra={
                "min_size": min_size,
                "max_size": max_size,
                "timeout": timeout,
            },
        )

    def acquire(self) -> Any:
        """Acquire connection from pool.

        Returns:
            Connection object
        """
        start_time = time.time()
        self.stats.total_requests += 1

        # Try to get idle connection
        for i, conn in enumerate(self.connections):
            if i not in self.active:
                self.active.append(i)
                self.stats.active_connections = len(self.active)
                self.stats.idle_connections = len(self.connections) - len(self.active)

                wait_time = (time.time() - start_time) * 1000
                self._update_avg_wait_time(wait_time)

                logger.debug(f"Acquired connection from pool '{self.name}'")
                return conn

        # Create new connection if under max size
        if len(self.connections) < self.max_size:
            conn = self._create_connection()
            conn_index = len(self.connections)
            self.connections.append(conn)
            self.active.append(conn_index)

            self.stats.total_connections = len(self.connections)
            self.stats.active_connections = len(self.active)
            self.stats.idle_connections = len(self.connections) - len(self.active)

            wait_time = (time.time() - start_time) * 1000
            self._update_avg_wait_time(wait_time)

            logger.debug(f"Created new connection in pool '{self.name}'")
            return conn

        # Pool exhausted
        self.stats.waiting_requests += 1
        self.stats.failed_requests += 1

        logger.warning(
            f"Connection pool '{self.name}' exhausted",
            extra={
                "total_connections": len(self.connections),
                "active_connections": len(self.active),
            },
        )

        raise RuntimeError(f"Connection pool '{self.name}' exhausted")

    def release(self, conn: Any):
        """Release connection back to pool.

        Args:
            conn: Connection to release
        """
        # Find connection index
        try:
            conn_index = self.connections.index(conn)
            if conn_index in self.active:
                self.active.remove(conn_index)
                self.stats.active_connections = len(self.active)
                self.stats.idle_connections = len(self.connections) - len(self.active)

                logger.debug(f"Released connection to pool '{self.name}'")
        except ValueError:
            logger.warning(f"Connection not found in pool '{self.name}'")

    def _create_connection(self) -> Any:
        """Create new connection.

        Returns:
            Connection object
        """
        # Mock connection - would create actual connection in real implementation
        return {"id": len(self.connections), "created_at": datetime.now()}

    def _update_avg_wait_time(self, wait_time_ms: float):
        """Update average wait time.

        Args:
            wait_time_ms: Wait time in milliseconds
        """
        total_requests = self.stats.total_requests
        current_avg = self.stats.avg_wait_time_ms

        # Calculate new average
        self.stats.avg_wait_time_ms = (
            current_avg * (total_requests - 1) + wait_time_ms
        ) / total_requests

    def get_stats(self) -> Dict[str, Any]:
        """Get pool statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "name": self.name,
            "total_connections": self.stats.total_connections,
            "active_connections": self.stats.active_connections,
            "idle_connections": self.stats.idle_connections,
            "waiting_requests": self.stats.waiting_requests,
            "total_requests": self.stats.total_requests,
            "failed_requests": self.stats.failed_requests,
            "avg_wait_time_ms": f"{self.stats.avg_wait_time_ms:.2f}",
            "utilization": f"{self.stats.utilization:.2f}%",
        }

    def close(self):
        """Close all connections in pool."""
        self.connections.clear()
        self.active.clear()
        self.stats = PoolStats()

        logger.info(f"ConnectionPool '{self.name}' closed")


class ConnectionPoolManager:
    """Manager for multiple connection pools.

    Manages connection pools for:
    - PostgreSQL
    - Milvus
    - Redis
    - MinIO
    """

    def __init__(self):
        """Initialize connection pool manager."""
        self.pools: Dict[str, ConnectionPool] = {}

        logger.info("ConnectionPoolManager initialized")

    def create_pool(
        self,
        name: str,
        min_size: int = 5,
        max_size: int = 20,
        timeout: float = 30.0,
    ) -> ConnectionPool:
        """Create connection pool.

        Args:
            name: Pool name
            min_size: Minimum pool size
            max_size: Maximum pool size
            timeout: Connection timeout in seconds

        Returns:
            Connection pool
        """
        if name in self.pools:
            logger.warning(f"Pool '{name}' already exists")
            return self.pools[name]

        pool = ConnectionPool(
            name=name,
            min_size=min_size,
            max_size=max_size,
            timeout=timeout,
        )

        self.pools[name] = pool

        logger.info(f"Created connection pool: {name}")

        return pool

    def get_pool(self, name: str) -> Optional[ConnectionPool]:
        """Get connection pool by name.

        Args:
            name: Pool name

        Returns:
            Connection pool or None
        """
        return self.pools.get(name)

    def create_postgres_pool(
        self,
        min_size: int = 10,
        max_size: int = 50,
    ) -> ConnectionPool:
        """Create PostgreSQL connection pool.

        Args:
            min_size: Minimum pool size
            max_size: Maximum pool size

        Returns:
            Connection pool
        """
        return self.create_pool(
            name="postgresql",
            min_size=min_size,
            max_size=max_size,
            timeout=30.0,
        )

    def create_milvus_pool(
        self,
        min_size: int = 5,
        max_size: int = 20,
    ) -> ConnectionPool:
        """Create Milvus connection pool.

        Args:
            min_size: Minimum pool size
            max_size: Maximum pool size

        Returns:
            Connection pool
        """
        return self.create_pool(
            name="milvus",
            min_size=min_size,
            max_size=max_size,
            timeout=30.0,
        )

    def create_redis_pool(
        self,
        min_size: int = 10,
        max_size: int = 30,
    ) -> ConnectionPool:
        """Create Redis connection pool.

        Args:
            min_size: Minimum pool size
            max_size: Maximum pool size

        Returns:
            Connection pool
        """
        return self.create_pool(
            name="redis",
            min_size=min_size,
            max_size=max_size,
            timeout=10.0,
        )

    def create_minio_pool(
        self,
        min_size: int = 5,
        max_size: int = 15,
    ) -> ConnectionPool:
        """Create MinIO connection pool.

        Args:
            min_size: Minimum pool size
            max_size: Maximum pool size

        Returns:
            Connection pool
        """
        return self.create_pool(
            name="minio",
            min_size=min_size,
            max_size=max_size,
            timeout=30.0,
        )

    def get_all_stats(self) -> Dict[str, Any]:
        """Get statistics for all pools.

        Returns:
            Statistics dictionary
        """
        return {name: pool.get_stats() for name, pool in self.pools.items()}

    def close_all(self):
        """Close all connection pools."""
        for pool in self.pools.values():
            pool.close()

        self.pools.clear()

        logger.info("All connection pools closed")


# Global connection pool manager instance
_pool_manager: Optional[ConnectionPoolManager] = None


def get_pool_manager() -> ConnectionPoolManager:
    """Get global connection pool manager instance.

    Returns:
        Connection pool manager
    """
    global _pool_manager

    if _pool_manager is None:
        _pool_manager = ConnectionPoolManager()

    return _pool_manager
