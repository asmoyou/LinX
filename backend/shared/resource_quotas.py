"""Resource Quota Management System.

Implements resource quota tracking and enforcement for users.

References:
- Requirements 19: Resource Quotas
- Design Section 8: Access Control and Security
- Task 5.3: Resource Quotas
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Dict, Any
from uuid import UUID

from database.connection import get_db_session
from database.models import ResourceQuota, User, Agent
from sqlalchemy import func

logger = logging.getLogger(__name__)


@dataclass
class QuotaUsage:
    """Current quota usage for a user."""
    
    user_id: UUID
    max_agents: int
    current_agents: int
    max_storage_gb: int
    current_storage_gb: Decimal
    max_cpu_cores: int
    max_memory_gb: int
    
    @property
    def agents_available(self) -> int:
        """Get number of agents that can still be created."""
        return max(0, self.max_agents - self.current_agents)
    
    @property
    def storage_available_gb(self) -> Decimal:
        """Get storage space available in GB."""
        return max(Decimal('0'), Decimal(str(self.max_storage_gb)) - self.current_storage_gb)
    
    @property
    def agents_usage_percent(self) -> float:
        """Get agent usage as percentage."""
        if self.max_agents == 0:
            return 0.0
        return (self.current_agents / self.max_agents) * 100
    
    @property
    def storage_usage_percent(self) -> float:
        """Get storage usage as percentage."""
        if self.max_storage_gb == 0:
            return 0.0
        return (float(self.current_storage_gb) / self.max_storage_gb) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses.
        
        Returns:
            Dictionary representation
        """
        return {
            "user_id": str(self.user_id),
            "agents": {
                "max": self.max_agents,
                "current": self.current_agents,
                "available": self.agents_available,
                "usage_percent": round(self.agents_usage_percent, 2),
            },
            "storage_gb": {
                "max": self.max_storage_gb,
                "current": float(self.current_storage_gb),
                "available": float(self.storage_available_gb),
                "usage_percent": round(self.storage_usage_percent, 2),
            },
            "compute": {
                "max_cpu_cores": self.max_cpu_cores,
                "max_memory_gb": self.max_memory_gb,
            },
        }


class QuotaExceededException(Exception):
    """Exception raised when quota is exceeded."""
    
    def __init__(self, message: str, quota_type: str, current: Any, limit: Any):
        """Initialize exception.
        
        Args:
            message: Error message
            quota_type: Type of quota exceeded
            current: Current usage
            limit: Quota limit
        """
        super().__init__(message)
        self.quota_type = quota_type
        self.current = current
        self.limit = limit


class ResourceQuotaManager:
    """Manages resource quotas for users."""
    
    def __init__(self):
        """Initialize resource quota manager."""
        self.alert_thresholds = {
            "warning": 80.0,  # 80% usage
            "critical": 95.0,  # 95% usage
        }
        
        logger.info("ResourceQuotaManager initialized")
    
    def get_quota_usage(self, user_id: UUID) -> QuotaUsage:
        """Get current quota usage for a user.
        
        Args:
            user_id: User ID
        
        Returns:
            QuotaUsage object
        
        Raises:
            ValueError: If user not found
        """
        with get_db_session() as session:
            quota = session.query(ResourceQuota).filter(
                ResourceQuota.user_id == user_id
            ).first()
            
            if not quota:
                raise ValueError(f"No quota found for user {user_id}")
            
            return QuotaUsage(
                user_id=user_id,
                max_agents=quota.max_agents,
                current_agents=quota.current_agents,
                max_storage_gb=quota.max_storage_gb,
                current_storage_gb=quota.current_storage_gb,
                max_cpu_cores=quota.max_cpu_cores,
                max_memory_gb=quota.max_memory_gb,
            )
    
    def check_agent_quota(self, user_id: UUID) -> bool:
        """Check if user can create another agent.
        
        Args:
            user_id: User ID
        
        Returns:
            True if user can create agent
        
        Raises:
            QuotaExceededException: If quota exceeded
        """
        usage = self.get_quota_usage(user_id)
        
        if usage.current_agents >= usage.max_agents:
            raise QuotaExceededException(
                f"Agent quota exceeded: {usage.current_agents}/{usage.max_agents}",
                quota_type="agents",
                current=usage.current_agents,
                limit=usage.max_agents,
            )
        
        logger.debug(
            "Agent quota check passed",
            extra={
                "user_id": str(user_id),
                "current": usage.current_agents,
                "max": usage.max_agents,
            },
        )
        
        return True
    
    def check_storage_quota(self, user_id: UUID, size_bytes: int) -> bool:
        """Check if user has enough storage quota.
        
        Args:
            user_id: User ID
            size_bytes: Size of file in bytes
        
        Returns:
            True if user has enough storage
        
        Raises:
            QuotaExceededException: If quota exceeded
        """
        usage = self.get_quota_usage(user_id)
        
        size_gb = Decimal(str(size_bytes)) / Decimal('1073741824')  # Convert to GB
        new_usage = usage.current_storage_gb + size_gb
        
        if new_usage > Decimal(str(usage.max_storage_gb)):
            raise QuotaExceededException(
                f"Storage quota exceeded: {float(new_usage):.2f}GB/{usage.max_storage_gb}GB",
                quota_type="storage",
                current=float(new_usage),
                limit=usage.max_storage_gb,
            )
        
        logger.debug(
            "Storage quota check passed",
            extra={
                "user_id": str(user_id),
                "size_gb": float(size_gb),
                "current_gb": float(usage.current_storage_gb),
                "max_gb": usage.max_storage_gb,
            },
        )
        
        return True
    
    def increment_agent_count(self, user_id: UUID) -> None:
        """Increment agent count for user.
        
        Args:
            user_id: User ID
        """
        with get_db_session() as session:
            quota = session.query(ResourceQuota).filter(
                ResourceQuota.user_id == user_id
            ).first()
            
            if quota:
                quota.current_agents += 1
                session.commit()
                
                logger.info(
                    "Agent count incremented",
                    extra={
                        "user_id": str(user_id),
                        "current_agents": quota.current_agents,
                    },
                )
                
                # Check for threshold alerts
                self._check_threshold_alert(user_id, "agents")
    
    def decrement_agent_count(self, user_id: UUID) -> None:
        """Decrement agent count for user.
        
        Args:
            user_id: User ID
        """
        with get_db_session() as session:
            quota = session.query(ResourceQuota).filter(
                ResourceQuota.user_id == user_id
            ).first()
            
            if quota and quota.current_agents > 0:
                quota.current_agents -= 1
                session.commit()
                
                logger.info(
                    "Agent count decremented",
                    extra={
                        "user_id": str(user_id),
                        "current_agents": quota.current_agents,
                    },
                )
    
    def add_storage_usage(self, user_id: UUID, size_bytes: int) -> None:
        """Add storage usage for user.
        
        Args:
            user_id: User ID
            size_bytes: Size in bytes
        """
        size_gb = Decimal(str(size_bytes)) / Decimal('1073741824')
        
        with get_db_session() as session:
            quota = session.query(ResourceQuota).filter(
                ResourceQuota.user_id == user_id
            ).first()
            
            if quota:
                quota.current_storage_gb += size_gb
                session.commit()
                
                logger.info(
                    "Storage usage added",
                    extra={
                        "user_id": str(user_id),
                        "added_gb": float(size_gb),
                        "current_gb": float(quota.current_storage_gb),
                    },
                )
                
                # Check for threshold alerts
                self._check_threshold_alert(user_id, "storage")
    
    def remove_storage_usage(self, user_id: UUID, size_bytes: int) -> None:
        """Remove storage usage for user.
        
        Args:
            user_id: User ID
            size_bytes: Size in bytes
        """
        size_gb = Decimal(str(size_bytes)) / Decimal('1073741824')
        
        with get_db_session() as session:
            quota = session.query(ResourceQuota).filter(
                ResourceQuota.user_id == user_id
            ).first()
            
            if quota:
                quota.current_storage_gb = max(
                    Decimal('0'),
                    quota.current_storage_gb - size_gb
                )
                session.commit()
                
                logger.info(
                    "Storage usage removed",
                    extra={
                        "user_id": str(user_id),
                        "removed_gb": float(size_gb),
                        "current_gb": float(quota.current_storage_gb),
                    },
                )
    
    def update_quota_limits(
        self,
        user_id: UUID,
        max_agents: Optional[int] = None,
        max_storage_gb: Optional[int] = None,
        max_cpu_cores: Optional[int] = None,
        max_memory_gb: Optional[int] = None,
    ) -> None:
        """Update quota limits for user.
        
        Args:
            user_id: User ID
            max_agents: Maximum agents (optional)
            max_storage_gb: Maximum storage in GB (optional)
            max_cpu_cores: Maximum CPU cores (optional)
            max_memory_gb: Maximum memory in GB (optional)
        """
        with get_db_session() as session:
            quota = session.query(ResourceQuota).filter(
                ResourceQuota.user_id == user_id
            ).first()
            
            if not quota:
                raise ValueError(f"No quota found for user {user_id}")
            
            if max_agents is not None:
                quota.max_agents = max_agents
            if max_storage_gb is not None:
                quota.max_storage_gb = max_storage_gb
            if max_cpu_cores is not None:
                quota.max_cpu_cores = max_cpu_cores
            if max_memory_gb is not None:
                quota.max_memory_gb = max_memory_gb
            
            session.commit()
            
            logger.info(
                "Quota limits updated",
                extra={
                    "user_id": str(user_id),
                    "max_agents": quota.max_agents,
                    "max_storage_gb": quota.max_storage_gb,
                },
            )
    
    def create_default_quota(self, user_id: UUID) -> ResourceQuota:
        """Create default quota for new user.
        
        Args:
            user_id: User ID
        
        Returns:
            Created ResourceQuota
        """
        with get_db_session() as session:
            # Check if quota already exists
            existing = session.query(ResourceQuota).filter(
                ResourceQuota.user_id == user_id
            ).first()
            
            if existing:
                logger.warning(
                    "Quota already exists for user",
                    extra={"user_id": str(user_id)},
                )
                return existing
            
            quota = ResourceQuota(
                user_id=user_id,
                max_agents=10,
                max_storage_gb=100,
                max_cpu_cores=10,
                max_memory_gb=20,
                current_agents=0,
                current_storage_gb=Decimal('0'),
            )
            
            session.add(quota)
            session.commit()
            session.refresh(quota)
            
            logger.info(
                "Default quota created",
                extra={"user_id": str(user_id)},
            )
            
            return quota
    
    def _check_threshold_alert(self, user_id: UUID, quota_type: str) -> None:
        """Check if quota usage exceeds alert thresholds.
        
        Args:
            user_id: User ID
            quota_type: Type of quota (agents, storage)
        """
        try:
            usage = self.get_quota_usage(user_id)
            
            if quota_type == "agents":
                usage_percent = usage.agents_usage_percent
            elif quota_type == "storage":
                usage_percent = usage.storage_usage_percent
            else:
                return
            
            if usage_percent >= self.alert_thresholds["critical"]:
                logger.critical(
                    f"CRITICAL: {quota_type} quota at {usage_percent:.1f}%",
                    extra={
                        "user_id": str(user_id),
                        "quota_type": quota_type,
                        "usage_percent": usage_percent,
                    },
                )
            elif usage_percent >= self.alert_thresholds["warning"]:
                logger.warning(
                    f"WARNING: {quota_type} quota at {usage_percent:.1f}%",
                    extra={
                        "user_id": str(user_id),
                        "quota_type": quota_type,
                        "usage_percent": usage_percent,
                    },
                )
        except Exception as e:
            logger.error(
                f"Failed to check threshold alert: {str(e)}",
                extra={"user_id": str(user_id)},
            )
    
    def get_all_quotas_summary(self) -> Dict[str, Any]:
        """Get summary of all quotas in the system.
        
        Returns:
            Dictionary with quota statistics
        """
        with get_db_session() as session:
            quotas = session.query(ResourceQuota).all()
            
            total_users = len(quotas)
            total_agents = sum(q.current_agents for q in quotas)
            total_storage_gb = sum(float(q.current_storage_gb) for q in quotas)
            
            # Users near limits
            agents_near_limit = sum(
                1 for q in quotas
                if q.max_agents > 0 and (q.current_agents / q.max_agents) >= 0.8
            )
            
            storage_near_limit = sum(
                1 for q in quotas
                if q.max_storage_gb > 0 and (float(q.current_storage_gb) / q.max_storage_gb) >= 0.8
            )
            
            return {
                "total_users": total_users,
                "total_agents": total_agents,
                "total_storage_gb": round(total_storage_gb, 2),
                "users_near_agent_limit": agents_near_limit,
                "users_near_storage_limit": storage_near_limit,
            }


# Global quota manager instance
_quota_manager_instance: Optional[ResourceQuotaManager] = None


def get_quota_manager() -> ResourceQuotaManager:
    """Get global quota manager instance.
    
    Returns:
        ResourceQuotaManager instance
    """
    global _quota_manager_instance
    
    if _quota_manager_instance is None:
        _quota_manager_instance = ResourceQuotaManager()
    
    return _quota_manager_instance
