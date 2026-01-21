"""Skill caching and reuse mechanism.

References:
- Design Section 5.6: Dynamic Skill Generation
- Requirements 4: Skill Library
"""

import logging
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class CachedSkill:
    """Cached skill information."""
    
    skill_id: UUID
    name: str
    description: str
    code: str
    interface_definition: dict
    dependencies: List[str]
    usage_count: int
    last_used: float
    created_at: float


class SkillCache:
    """Cache for dynamically generated skills."""
    
    def __init__(self, max_size: int = 1000, ttl: int = 3600):
        """Initialize skill cache.
        
        Args:
            max_size: Maximum number of skills to cache
            ttl: Time-to-live in seconds (default: 1 hour)
        """
        self.max_size = max_size
        self.ttl = ttl
        self._cache: Dict[str, CachedSkill] = {}
        logger.info(f"SkillCache initialized (max_size={max_size}, ttl={ttl}s)")
    
    def get(self, description: str) -> Optional[CachedSkill]:
        """Get cached skill by description.
        
        Args:
            description: Skill description
            
        Returns:
            CachedSkill if found and not expired, None otherwise
        """
        cache_key = self._generate_cache_key(description)
        
        if cache_key in self._cache:
            cached_skill = self._cache[cache_key]
            
            # Check if expired
            if time.time() - cached_skill.created_at > self.ttl:
                logger.info(f"Cache expired for: {description}")
                del self._cache[cache_key]
                return None
            
            # Update usage stats
            cached_skill.usage_count += 1
            cached_skill.last_used = time.time()
            
            logger.info(f"Cache hit for: {description}")
            return cached_skill
        
        logger.info(f"Cache miss for: {description}")
        return None
    
    def put(
        self,
        description: str,
        skill_id: UUID,
        name: str,
        code: str,
        interface_definition: dict,
        dependencies: List[str],
    ) -> None:
        """Add skill to cache.
        
        Args:
            description: Skill description
            skill_id: Skill UUID
            name: Skill name
            code: Skill code
            interface_definition: Interface definition
            dependencies: List of dependencies
        """
        cache_key = self._generate_cache_key(description)
        
        # Check cache size and evict if necessary
        if len(self._cache) >= self.max_size:
            self._evict_lru()
        
        cached_skill = CachedSkill(
            skill_id=skill_id,
            name=name,
            description=description,
            code=code,
            interface_definition=interface_definition,
            dependencies=dependencies,
            usage_count=1,
            last_used=time.time(),
            created_at=time.time(),
        )
        
        self._cache[cache_key] = cached_skill
        logger.info(f"Cached skill: {name}")
    
    def invalidate(self, description: str) -> bool:
        """Invalidate cached skill.
        
        Args:
            description: Skill description
            
        Returns:
            True if skill was cached, False otherwise
        """
        cache_key = self._generate_cache_key(description)
        
        if cache_key in self._cache:
            del self._cache[cache_key]
            logger.info(f"Invalidated cache for: {description}")
            return True
        
        return False
    
    def clear(self) -> None:
        """Clear all cached skills."""
        self._cache.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_usage = sum(skill.usage_count for skill in self._cache.values())
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "total_usage": total_usage,
            "ttl": self.ttl,
        }
    
    def get_top_skills(self, limit: int = 10) -> List[CachedSkill]:
        """Get most frequently used skills.
        
        Args:
            limit: Maximum number of skills to return
            
        Returns:
            List of top skills sorted by usage count
        """
        sorted_skills = sorted(
            self._cache.values(),
            key=lambda s: s.usage_count,
            reverse=True
        )
        
        return sorted_skills[:limit]
    
    def _generate_cache_key(self, description: str) -> str:
        """Generate cache key from description.
        
        Args:
            description: Skill description
            
        Returns:
            Cache key (hash of normalized description)
        """
        # Normalize description (lowercase, strip whitespace)
        normalized = description.lower().strip()
        
        # Generate hash
        return hashlib.sha256(normalized.encode()).hexdigest()
    
    def _evict_lru(self) -> None:
        """Evict least recently used skill from cache."""
        if not self._cache:
            return
        
        # Find LRU skill
        lru_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_used
        )
        
        evicted_skill = self._cache[lru_key]
        del self._cache[lru_key]
        
        logger.info(f"Evicted LRU skill: {evicted_skill.name}")


# Singleton instance
_skill_cache: Optional[SkillCache] = None


def get_skill_cache() -> SkillCache:
    """Get or create the skill cache singleton.
    
    Returns:
        SkillCache instance
    """
    global _skill_cache
    if _skill_cache is None:
        _skill_cache = SkillCache()
    return _skill_cache
