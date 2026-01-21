"""Redis caching layer for hot data.

References:
- Requirements 8: Scalability and Performance
- Design Section 10: Scalability and Performance
"""

import logging
import json
import time
from typing import Any, Optional, Dict, List
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Cache statistics."""
    
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0


class CacheManager:
    """Redis cache manager.
    
    Provides caching for hot data:
    - User sessions
    - Agent configurations
    - Task metadata
    - Knowledge base queries
    - API responses
    """
    
    def __init__(self, default_ttl: int = 3600):
        """Initialize cache manager.
        
        Args:
            default_ttl: Default time-to-live in seconds
        """
        self.default_ttl = default_ttl
        self.cache: Dict[str, tuple] = {}  # Mock cache: key -> (value, expiry)
        self.stats = CacheStats()
        
        logger.info("CacheManager initialized")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if key in self.cache:
            value, expiry = self.cache[key]
            
            # Check if expired
            if expiry and time.time() > expiry:
                del self.cache[key]
                self.stats.misses += 1
                self.stats.evictions += 1
                return None
            
            self.stats.hits += 1
            logger.debug(f"Cache hit: {key}")
            return value
        
        self.stats.misses += 1
        logger.debug(f"Cache miss: {key}")
        return None
    
    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ):
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if not specified)
        """
        ttl = ttl if ttl is not None else self.default_ttl
        expiry = time.time() + ttl if ttl > 0 else None
        
        self.cache[key] = (value, expiry)
        self.stats.sets += 1
        
        logger.debug(f"Cache set: {key} (TTL: {ttl}s)")
    
    def delete(self, key: str) -> bool:
        """Delete value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if deleted
        """
        if key in self.cache:
            del self.cache[key]
            self.stats.deletes += 1
            logger.debug(f"Cache delete: {key}")
            return True
        return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if exists
        """
        if key in self.cache:
            value, expiry = self.cache[key]
            if expiry and time.time() > expiry:
                del self.cache[key]
                return False
            return True
        return False
    
    def clear(self):
        """Clear all cache entries."""
        self.cache.clear()
        logger.info("Cache cleared")
    
    def get_or_set(
        self,
        key: str,
        factory,
        ttl: Optional[int] = None,
    ) -> Any:
        """Get value from cache or set it using factory function.
        
        Args:
            key: Cache key
            factory: Function to generate value if not cached
            ttl: Time-to-live in seconds
            
        Returns:
            Cached or generated value
        """
        value = self.get(key)
        
        if value is None:
            value = factory()
            self.set(key, value, ttl)
        
        return value
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "sets": self.stats.sets,
            "deletes": self.stats.deletes,
            "evictions": self.stats.evictions,
            "hit_rate": f"{self.stats.hit_rate:.2f}%",
            "total_keys": len(self.cache),
        }
    
    def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern.
        
        Args:
            pattern: Key pattern (supports * wildcard)
        """
        import re
        
        # Convert glob pattern to regex
        regex_pattern = pattern.replace("*", ".*")
        regex = re.compile(f"^{regex_pattern}$")
        
        keys_to_delete = [
            key for key in self.cache.keys()
            if regex.match(key)
        ]
        
        for key in keys_to_delete:
            self.delete(key)
        
        logger.info(f"Invalidated {len(keys_to_delete)} keys matching: {pattern}")
    
    # Convenience methods for common cache patterns
    
    def cache_user_session(self, user_id: str, session_data: Dict[str, Any]):
        """Cache user session data.
        
        Args:
            user_id: User ID
            session_data: Session data
        """
        key = f"session:{user_id}"
        self.set(key, session_data, ttl=1800)  # 30 minutes
    
    def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user session data.
        
        Args:
            user_id: User ID
            
        Returns:
            Session data or None
        """
        key = f"session:{user_id}"
        return self.get(key)
    
    def cache_agent_config(self, agent_id: str, config: Dict[str, Any]):
        """Cache agent configuration.
        
        Args:
            agent_id: Agent ID
            config: Agent configuration
        """
        key = f"agent:config:{agent_id}"
        self.set(key, config, ttl=3600)  # 1 hour
    
    def get_agent_config(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent configuration.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent configuration or None
        """
        key = f"agent:config:{agent_id}"
        return self.get(key)
    
    def cache_api_response(
        self,
        endpoint: str,
        params: Dict[str, Any],
        response: Any,
    ):
        """Cache API response.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            response: Response data
        """
        import hashlib
        params_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
        key = f"api:{endpoint}:{params_hash}"
        self.set(key, response, ttl=300)  # 5 minutes
    
    def get_api_response(
        self,
        endpoint: str,
        params: Dict[str, Any],
    ) -> Optional[Any]:
        """Get cached API response.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            Cached response or None
        """
        import hashlib
        params_hash = hashlib.md5(json.dumps(params, sort_keys=True).encode()).hexdigest()[:8]
        key = f"api:{endpoint}:{params_hash}"
        return self.get(key)


# Global cache manager instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get global cache manager instance.
    
    Returns:
        Cache manager
    """
    global _cache_manager
    
    if _cache_manager is None:
        _cache_manager = CacheManager()
    
    return _cache_manager
