"""
Redis Connection Manager

Manages Redis connections with connection pooling for the message bus.

Task: 1.5.1 Create Redis connection manager with connection pooling
References:
- Requirements 17: Inter-Agent Communication
- Design Section 15.1: Message Bus Architecture
"""

import logging
from typing import Optional
import redis
from redis.connection import ConnectionPool
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError

from shared.config import get_config

logger = logging.getLogger(__name__)


class RedisConnectionManager:
    """
    Manages Redis connections with connection pooling.
    
    Features:
    - Connection pooling for efficient resource usage
    - Automatic reconnection on failure
    - Health checking
    - Support for both standalone and cluster modes
    """
    
    def __init__(self):
        """Initialize the Redis connection manager."""
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._config = get_config()
        
    def initialize(self) -> None:
        """
        Initialize Redis connection pool.
        
        Raises:
            RedisConnectionError: If connection to Redis fails
        """
        try:
            redis_config = self._config.get_section("database.redis")
            
            # Create connection pool
            self._pool = ConnectionPool(
                host=redis_config["host"],
                port=redis_config["port"],
                password=redis_config.get("password") or None,
                db=redis_config["db"],
                max_connections=redis_config["max_connections"],
                socket_timeout=redis_config["socket_timeout"],
                socket_connect_timeout=redis_config["socket_connect_timeout"],
                retry_on_timeout=redis_config["retry_on_timeout"],
                decode_responses=True,  # Automatically decode responses to strings
                encoding="utf-8",
            )
            
            # Create Redis client
            self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            self._client.ping()
            
            logger.info(
                f"Redis connection pool initialized: "
                f"host={redis_config['host']}, "
                f"port={redis_config['port']}, "
                f"db={redis_config['db']}, "
                f"max_connections={redis_config['max_connections']}"
            )
            
        except RedisConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        except Exception as e:
            logger.error(f"Error initializing Redis connection manager: {e}")
            raise
    
    def get_client(self) -> redis.Redis:
        """
        Get Redis client instance.
        
        Returns:
            redis.Redis: Redis client with connection pooling
            
        Raises:
            RuntimeError: If connection manager not initialized
        """
        if self._client is None:
            raise RuntimeError(
                "Redis connection manager not initialized. "
                "Call initialize() first."
            )
        return self._client
    
    def health_check(self) -> bool:
        """
        Check if Redis connection is healthy.
        
        Returns:
            bool: True if connection is healthy, False otherwise
        """
        try:
            if self._client is None:
                return False
            self._client.ping()
            return True
        except RedisError as e:
            logger.warning(f"Redis health check failed: {e}")
            return False
    
    def get_pool_stats(self) -> dict:
        """
        Get connection pool statistics.
        
        Returns:
            dict: Pool statistics including created and available connections
        """
        if self._pool is None:
            return {
                "initialized": False,
                "created_connections": 0,
                "available_connections": 0,
                "in_use_connections": 0,
            }
        
        return {
            "initialized": True,
            "created_connections": self._pool._created_connections,
            "available_connections": len(self._pool._available_connections),
            "in_use_connections": (
                self._pool._created_connections - 
                len(self._pool._available_connections)
            ),
            "max_connections": self._pool.max_connections,
        }
    
    def close(self) -> None:
        """Close all connections in the pool."""
        try:
            if self._client:
                self._client.close()
                logger.info("Redis client closed")
            
            if self._pool:
                self._pool.disconnect()
                logger.info("Redis connection pool closed")
                
        except Exception as e:
            logger.error(f"Error closing Redis connections: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Global instance
_redis_manager: Optional[RedisConnectionManager] = None


def get_redis_manager() -> RedisConnectionManager:
    """
    Get global Redis connection manager instance.
    
    Returns:
        RedisConnectionManager: Global Redis manager instance
    """
    global _redis_manager
    if _redis_manager is None:
        _redis_manager = RedisConnectionManager()
        _redis_manager.initialize()
    return _redis_manager


def close_redis_manager() -> None:
    """Close global Redis connection manager."""
    global _redis_manager
    if _redis_manager is not None:
        _redis_manager.close()
        _redis_manager = None
