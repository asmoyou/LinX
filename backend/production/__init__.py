"""Production hardening module.

References:
- All requirements
- Design Section 10: Scalability and Performance

This module provides production-ready features:
- Database backup and restore
- Disaster recovery procedures
- Graceful shutdown
- Circuit breakers
- Rate limiting
- Request deduplication
- Maintenance mode
"""

from production.backup_restore import BackupManager, RestoreManager
from production.circuit_breaker import CircuitBreaker, CircuitBreakerManager
from production.disaster_recovery import DisasterRecoveryManager
from production.graceful_shutdown import GracefulShutdownManager
from production.maintenance_mode import MaintenanceMode
from production.rate_limiter import RateLimiter, RateLimiterManager
from production.request_deduplication import RequestDeduplicator

__all__ = [
    "BackupManager",
    "RestoreManager",
    "DisasterRecoveryManager",
    "GracefulShutdownManager",
    "CircuitBreaker",
    "CircuitBreakerManager",
    "RateLimiter",
    "RateLimiterManager",
    "RequestDeduplicator",
    "MaintenanceMode",
]
