"""Rate limiting for all APIs.

References:
- All requirements
- Design Section 10: Scalability and Performance
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    
    requests_per_second: int = 10
    requests_per_minute: int = 100
    requests_per_hour: int = 1000
    burst_size: int = 20  # Allow bursts up to this size


@dataclass
class RateLimitResult:
    """Rate limit check result."""
    
    allowed: bool
    limit: int
    remaining: int
    reset_at: datetime
    retry_after_seconds: Optional[int] = None


class RateLimiter:
    """Rate limiter using token bucket algorithm.
    
    Implements rate limiting with:
    - Requests per second/minute/hour limits
    - Burst handling
    - Per-user/per-IP tracking
    """
    
    def __init__(
        self,
        identifier: str,
        config: Optional[RateLimitConfig] = None,
    ):
        """Initialize rate limiter.
        
        Args:
            identifier: Unique identifier (user_id, IP, etc.)
            config: Rate limit configuration
        """
        self.identifier = identifier
        self.config = config or RateLimitConfig()
        
        # Token buckets for different time windows
        self.second_bucket = deque(maxlen=self.config.requests_per_second)
        self.minute_bucket = deque(maxlen=self.config.requests_per_minute)
        self.hour_bucket = deque(maxlen=self.config.requests_per_hour)
        
        logger.debug(f"RateLimiter initialized for: {identifier}")
    
    def check_rate_limit(self) -> RateLimitResult:
        """Check if request is allowed.
        
        Returns:
            Rate limit result
        """
        now = time.time()
        
        # Clean old entries
        self._clean_buckets(now)
        
        # Check each time window
        second_check = self._check_window(
            self.second_bucket,
            self.config.requests_per_second,
            now,
            1,
        )
        
        minute_check = self._check_window(
            self.minute_bucket,
            self.config.requests_per_minute,
            now,
            60,
        )
        
        hour_check = self._check_window(
            self.hour_bucket,
            self.config.requests_per_hour,
            now,
            3600,
        )
        
        # Request is allowed if all windows allow it
        allowed = second_check[0] and minute_check[0] and hour_check[0]
        
        if allowed:
            # Add request to buckets
            self.second_bucket.append(now)
            self.minute_bucket.append(now)
            self.hour_bucket.append(now)
        
        # Use most restrictive limit for response
        if not second_check[0]:
            limit, remaining, reset_at = second_check[1:]
            retry_after = 1
        elif not minute_check[0]:
            limit, remaining, reset_at = minute_check[1:]
            retry_after = int(reset_at - now)
        elif not hour_check[0]:
            limit, remaining, reset_at = hour_check[1:]
            retry_after = int(reset_at - now)
        else:
            # Use minute window for response
            limit, remaining, reset_at = minute_check[1:]
            retry_after = None
        
        return RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=datetime.fromtimestamp(reset_at),
            retry_after_seconds=retry_after,
        )
    
    def _check_window(
        self,
        bucket: deque,
        limit: int,
        now: float,
        window_seconds: int,
    ) -> Tuple[bool, int, int, float]:
        """Check rate limit for a time window.
        
        Args:
            bucket: Request bucket
            limit: Request limit
            now: Current timestamp
            window_seconds: Window size in seconds
            
        Returns:
            (allowed, limit, remaining, reset_at)
        """
        # Count requests in window
        window_start = now - window_seconds
        requests_in_window = sum(1 for ts in bucket if ts > window_start)
        
        allowed = requests_in_window < limit
        remaining = max(0, limit - requests_in_window - (0 if allowed else 1))
        reset_at = now + window_seconds
        
        return allowed, limit, remaining, reset_at
    
    def _clean_buckets(self, now: float):
        """Remove old entries from buckets.
        
        Args:
            now: Current timestamp
        """
        # Clean second bucket (keep last 1 second)
        while self.second_bucket and self.second_bucket[0] < now - 1:
            self.second_bucket.popleft()
        
        # Clean minute bucket (keep last 60 seconds)
        while self.minute_bucket and self.minute_bucket[0] < now - 60:
            self.minute_bucket.popleft()
        
        # Clean hour bucket (keep last 3600 seconds)
        while self.hour_bucket and self.hour_bucket[0] < now - 3600:
            self.hour_bucket.popleft()
    
    def reset(self):
        """Reset rate limiter."""
        self.second_bucket.clear()
        self.minute_bucket.clear()
        self.hour_bucket.clear()
        
        logger.info(f"Rate limiter reset for: {self.identifier}")


class RateLimiterManager:
    """Rate limiter manager.
    
    Manages rate limiters for multiple identifiers.
    """
    
    def __init__(self, default_config: Optional[RateLimitConfig] = None):
        """Initialize rate limiter manager.
        
        Args:
            default_config: Default rate limit configuration
        """
        self.default_config = default_config or RateLimitConfig()
        self.limiters: Dict[str, RateLimiter] = {}
        
        logger.info("RateLimiterManager initialized")
    
    def get_limiter(
        self,
        identifier: str,
        config: Optional[RateLimitConfig] = None,
    ) -> RateLimiter:
        """Get or create rate limiter.
        
        Args:
            identifier: Unique identifier
            config: Custom configuration (optional)
            
        Returns:
            Rate limiter
        """
        if identifier not in self.limiters:
            self.limiters[identifier] = RateLimiter(
                identifier,
                config or self.default_config,
            )
        
        return self.limiters[identifier]
    
    def check_rate_limit(
        self,
        identifier: str,
        config: Optional[RateLimitConfig] = None,
    ) -> RateLimitResult:
        """Check rate limit for identifier.
        
        Args:
            identifier: Unique identifier
            config: Custom configuration (optional)
            
        Returns:
            Rate limit result
        """
        limiter = self.get_limiter(identifier, config)
        result = limiter.check_rate_limit()
        
        if not result.allowed:
            logger.warning(
                f"Rate limit exceeded for: {identifier}",
                extra={
                    "limit": result.limit,
                    "retry_after": result.retry_after_seconds,
                },
            )
        
        return result
    
    def reset_limiter(self, identifier: str):
        """Reset rate limiter for identifier.
        
        Args:
            identifier: Unique identifier
        """
        if identifier in self.limiters:
            self.limiters[identifier].reset()
    
    def reset_all(self):
        """Reset all rate limiters."""
        for limiter in self.limiters.values():
            limiter.reset()
        
        logger.info("All rate limiters reset")
    
    def cleanup_inactive(self, inactive_seconds: int = 3600):
        """Remove inactive rate limiters.
        
        Args:
            inactive_seconds: Seconds of inactivity before cleanup
        """
        now = time.time()
        to_remove = []
        
        for identifier, limiter in self.limiters.items():
            # Check if limiter has any recent requests
            if limiter.hour_bucket:
                last_request = limiter.hour_bucket[-1]
                if now - last_request > inactive_seconds:
                    to_remove.append(identifier)
            else:
                to_remove.append(identifier)
        
        for identifier in to_remove:
            del self.limiters[identifier]
        
        if to_remove:
            logger.info(f"Cleaned up {len(to_remove)} inactive rate limiters")


# Global rate limiter manager instance
_manager: Optional[RateLimiterManager] = None


def get_rate_limiter_manager() -> RateLimiterManager:
    """Get global rate limiter manager.
    
    Returns:
        Rate limiter manager
    """
    global _manager
    
    if _manager is None:
        _manager = RateLimiterManager()
    
    return _manager
