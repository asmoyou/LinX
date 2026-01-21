"""Circuit breakers for external dependencies.

References:
- All requirements
- Design Section 10: Scalability and Performance
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Any, Optional, Dict
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes to close from half-open
    timeout_seconds: int = 60  # Time before trying half-open
    call_timeout_seconds: int = 10  # Timeout for individual calls


@dataclass
class CircuitBreakerStats:
    """Circuit breaker statistics."""
    
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None


class CircuitBreaker:
    """Circuit breaker for external service calls.
    
    Implements circuit breaker pattern:
    - CLOSED: Normal operation, calls pass through
    - OPEN: Service failing, reject calls immediately
    - HALF_OPEN: Testing if service recovered
    """
    
    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        """Initialize circuit breaker.
        
        Args:
            name: Circuit breaker name
            config: Configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self.failure_count = 0
        self.success_count = 0
        self.opened_at: Optional[datetime] = None
        
        logger.info(f"CircuitBreaker initialized: {name}")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with circuit breaker protection.
        
        Args:
            func: Function to call
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If circuit is open or call fails
        """
        self.stats.total_calls += 1
        
        # Check if circuit is open
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                self.stats.rejected_calls += 1
                raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        try:
            # Execute call with timeout
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.config.call_timeout_seconds,
                )
            else:
                result = func(*args, **kwargs)
            
            self._on_success()
            return result
            
        except Exception as e:
            self._on_failure()
            raise e
    
    def _on_success(self):
        """Handle successful call."""
        self.stats.successful_calls += 1
        self.stats.last_success_time = datetime.now()
        self.failure_count = 0
        
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
    
    def _on_failure(self):
        """Handle failed call."""
        self.stats.failed_calls += 1
        self.stats.last_failure_time = datetime.now()
        self.success_count = 0
        
        if self.state == CircuitState.CLOSED:
            self.failure_count += 1
            
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()
        
        elif self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
    
    def _should_attempt_reset(self) -> bool:
        """Check if should attempt to reset circuit.
        
        Returns:
            True if timeout has elapsed
        """
        if not self.opened_at:
            return False
        
        elapsed = datetime.now() - self.opened_at
        return elapsed.total_seconds() >= self.config.timeout_seconds
    
    def _transition_to_open(self):
        """Transition to OPEN state."""
        self.state = CircuitState.OPEN
        self.opened_at = datetime.now()
        
        logger.warning(
            f"Circuit breaker {self.name} transitioned to OPEN",
            extra={
                "failure_count": self.failure_count,
                "stats": self.get_stats(),
            },
        )
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state."""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        
        logger.info(f"Circuit breaker {self.name} transitioned to HALF_OPEN")
    
    def _transition_to_closed(self):
        """Transition to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at = None
        
        logger.info(f"Circuit breaker {self.name} transitioned to CLOSED")
    
    def get_state(self) -> CircuitState:
        """Get current state.
        
        Returns:
            Current circuit state
        """
        return self.state
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics.
        
        Returns:
            Statistics dictionary
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self.stats.total_calls,
            "successful_calls": self.stats.successful_calls,
            "failed_calls": self.stats.failed_calls,
            "rejected_calls": self.stats.rejected_calls,
            "failure_rate": (
                self.stats.failed_calls / self.stats.total_calls
                if self.stats.total_calls > 0
                else 0
            ),
            "last_failure_time": (
                self.stats.last_failure_time.isoformat()
                if self.stats.last_failure_time
                else None
            ),
            "last_success_time": (
                self.stats.last_success_time.isoformat()
                if self.stats.last_success_time
                else None
            ),
        }
    
    def reset(self):
        """Manually reset circuit breaker."""
        self._transition_to_closed()
        logger.info(f"Circuit breaker {self.name} manually reset")


class CircuitBreakerManager:
    """Circuit breaker manager.
    
    Manages multiple circuit breakers for different services.
    """
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self.breakers: Dict[str, CircuitBreaker] = {}
        
        logger.info("CircuitBreakerManager initialized")
    
    def get_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """Get or create circuit breaker.
        
        Args:
            name: Circuit breaker name
            config: Configuration (only used if creating new)
            
        Returns:
            Circuit breaker
        """
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name, config)
        
        return self.breakers[name]
    
    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers.
        
        Returns:
            Statistics for all breakers
        """
        return {
            name: breaker.get_stats()
            for name, breaker in self.breakers.items()
        }
    
    def reset_all(self):
        """Reset all circuit breakers."""
        for breaker in self.breakers.values():
            breaker.reset()
        
        logger.info("All circuit breakers reset")


# Global circuit breaker manager instance
_manager: Optional[CircuitBreakerManager] = None


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get global circuit breaker manager.
    
    Returns:
        Circuit breaker manager
    """
    global _manager
    
    if _manager is None:
        _manager = CircuitBreakerManager()
    
    return _manager
