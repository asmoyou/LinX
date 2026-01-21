"""Tenant-specific resource quotas.

References:
- Requirements 14: Access Control and Security
- Requirements 19: Resource Management
- Design Section 8: Security and Access Control
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class TenantQuota:
    """Tenant resource quota."""
    
    tenant_id: UUID
    max_users: int
    max_agents: int
    max_storage_gb: int
    max_compute_hours: int
    
    # Current usage
    current_users: int = 0
    current_agents: int = 0
    current_storage_gb: float = 0.0
    current_compute_hours: float = 0.0
    current_concurrent_tasks: int = 0
    
    # API rate limits
    max_api_requests_per_minute: int = 1000
    max_api_requests_per_day: int = 100000
    
    # Task limits
    max_concurrent_tasks: int = 100
    
    # Reset period
    compute_reset_at: Optional[datetime] = None
    api_reset_at: Optional[datetime] = None
    
    def __post_init__(self):
        """Initialize reset times."""
        if self.compute_reset_at is None:
            # Reset at start of next month
            now = datetime.now()
            if now.month == 12:
                self.compute_reset_at = datetime(now.year + 1, 1, 1)
            else:
                self.compute_reset_at = datetime(now.year, now.month + 1, 1)
        
        if self.api_reset_at is None:
            # Reset daily
            self.api_reset_at = datetime.now() + timedelta(days=1)
    
    def is_user_limit_reached(self) -> bool:
        """Check if user limit is reached."""
        return self.current_users >= self.max_users
    
    def is_agent_limit_reached(self) -> bool:
        """Check if agent limit is reached."""
        return self.current_agents >= self.max_agents
    
    def is_storage_limit_reached(self) -> bool:
        """Check if storage limit is reached."""
        return self.current_storage_gb >= self.max_storage_gb
    
    def is_compute_limit_reached(self) -> bool:
        """Check if compute limit is reached."""
        return self.current_compute_hours >= self.max_compute_hours
    
    def is_task_limit_reached(self) -> bool:
        """Check if concurrent task limit is reached."""
        return self.current_concurrent_tasks >= self.max_concurrent_tasks
    
    def get_usage_percentage(self, resource: str) -> float:
        """Get usage percentage for a resource.
        
        Args:
            resource: Resource type (users, agents, storage, compute, tasks)
            
        Returns:
            Usage percentage (0-100)
        """
        if resource == "users":
            return (self.current_users / self.max_users * 100) if self.max_users > 0 else 0
        elif resource == "agents":
            return (self.current_agents / self.max_agents * 100) if self.max_agents > 0 else 0
        elif resource == "storage":
            return (self.current_storage_gb / self.max_storage_gb * 100) if self.max_storage_gb > 0 else 0
        elif resource == "compute":
            return (self.current_compute_hours / self.max_compute_hours * 100) if self.max_compute_hours > 0 else 0
        elif resource == "tasks":
            return (self.current_concurrent_tasks / self.max_concurrent_tasks * 100) if self.max_concurrent_tasks > 0 else 0
        else:
            return 0.0


class TenantQuotaManager:
    """Tenant quota management.
    
    Manages resource quotas for tenants:
    - Quota enforcement
    - Usage tracking
    - Quota updates
    - Overage alerts
    """
    
    def __init__(self, database=None):
        """Initialize quota manager.
        
        Args:
            database: Database connection
        """
        self.database = database
        self.quotas: Dict[UUID, TenantQuota] = {}
        
        logger.info("TenantQuotaManager initialized")
    
    def get_quota(self, tenant_id: UUID) -> Optional[TenantQuota]:
        """Get quota for a tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            TenantQuota or None
        """
        return self.quotas.get(tenant_id)
    
    def set_quota(self, quota: TenantQuota):
        """Set quota for a tenant.
        
        Args:
            quota: Tenant quota
        """
        self.quotas[quota.tenant_id] = quota
        logger.info(f"Set quota for tenant: {quota.tenant_id}")
    
    def check_user_quota(self, tenant_id: UUID) -> bool:
        """Check if tenant can create more users.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            True if quota allows
        """
        quota = self.get_quota(tenant_id)
        if not quota:
            logger.warning(f"No quota found for tenant: {tenant_id}")
            return False
        
        if quota.is_user_limit_reached():
            logger.warning(f"User limit reached for tenant: {tenant_id}")
            return False
        
        return True
    
    def check_agent_quota(self, tenant_id: UUID) -> bool:
        """Check if tenant can create more agents.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            True if quota allows
        """
        quota = self.get_quota(tenant_id)
        if not quota:
            logger.warning(f"No quota found for tenant: {tenant_id}")
            return False
        
        if quota.is_agent_limit_reached():
            logger.warning(f"Agent limit reached for tenant: {tenant_id}")
            return False
        
        return True
    
    def check_storage_quota(
        self,
        tenant_id: UUID,
        additional_gb: float,
    ) -> bool:
        """Check if tenant can use more storage.
        
        Args:
            tenant_id: Tenant ID
            additional_gb: Additional storage needed (GB)
            
        Returns:
            True if quota allows
        """
        quota = self.get_quota(tenant_id)
        if not quota:
            logger.warning(f"No quota found for tenant: {tenant_id}")
            return False
        
        if quota.current_storage_gb + additional_gb > quota.max_storage_gb:
            logger.warning(f"Storage limit would be exceeded for tenant: {tenant_id}")
            return False
        
        return True
    
    def check_compute_quota(
        self,
        tenant_id: UUID,
        additional_hours: float,
    ) -> bool:
        """Check if tenant can use more compute.
        
        Args:
            tenant_id: Tenant ID
            additional_hours: Additional compute hours needed
            
        Returns:
            True if quota allows
        """
        quota = self.get_quota(tenant_id)
        if not quota:
            logger.warning(f"No quota found for tenant: {tenant_id}")
            return False
        
        # Reset if period expired
        if datetime.now() >= quota.compute_reset_at:
            quota.current_compute_hours = 0.0
            quota.compute_reset_at = quota.compute_reset_at + timedelta(days=30)
        
        if quota.current_compute_hours + additional_hours > quota.max_compute_hours:
            logger.warning(f"Compute limit would be exceeded for tenant: {tenant_id}")
            return False
        
        return True
    
    def increment_user_count(self, tenant_id: UUID):
        """Increment user count for tenant.
        
        Args:
            tenant_id: Tenant ID
        """
        quota = self.get_quota(tenant_id)
        if quota:
            quota.current_users += 1
            logger.debug(f"Incremented user count for tenant {tenant_id}: {quota.current_users}")
    
    def decrement_user_count(self, tenant_id: UUID):
        """Decrement user count for tenant.
        
        Args:
            tenant_id: Tenant ID
        """
        quota = self.get_quota(tenant_id)
        if quota and quota.current_users > 0:
            quota.current_users -= 1
            logger.debug(f"Decremented user count for tenant {tenant_id}: {quota.current_users}")
    
    def increment_agent_count(self, tenant_id: UUID):
        """Increment agent count for tenant.
        
        Args:
            tenant_id: Tenant ID
        """
        quota = self.get_quota(tenant_id)
        if quota:
            quota.current_agents += 1
            logger.debug(f"Incremented agent count for tenant {tenant_id}: {quota.current_agents}")
    
    def decrement_agent_count(self, tenant_id: UUID):
        """Decrement agent count for tenant.
        
        Args:
            tenant_id: Tenant ID
        """
        quota = self.get_quota(tenant_id)
        if quota and quota.current_agents > 0:
            quota.current_agents -= 1
            logger.debug(f"Decremented agent count for tenant {tenant_id}: {quota.current_agents}")
    
    def add_storage_usage(self, tenant_id: UUID, gb: float):
        """Add storage usage for tenant.
        
        Args:
            tenant_id: Tenant ID
            gb: Storage in GB
        """
        quota = self.get_quota(tenant_id)
        if quota:
            quota.current_storage_gb += gb
            logger.debug(f"Added storage usage for tenant {tenant_id}: {gb} GB")
    
    def add_compute_usage(self, tenant_id: UUID, hours: float):
        """Add compute usage for tenant.
        
        Args:
            tenant_id: Tenant ID
            hours: Compute hours
        """
        quota = self.get_quota(tenant_id)
        if quota:
            quota.current_compute_hours += hours
            logger.debug(f"Added compute usage for tenant {tenant_id}: {hours} hours")
    
    def get_quota_status(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get quota status for tenant.
        
        Args:
            tenant_id: Tenant ID
            
        Returns:
            Dictionary with quota status
        """
        quota = self.get_quota(tenant_id)
        if not quota:
            return {"error": "Quota not found"}
        
        return {
            "tenant_id": str(tenant_id),
            "users": {
                "current": quota.current_users,
                "max": quota.max_users,
                "percentage": quota.get_usage_percentage("users"),
                "limit_reached": quota.is_user_limit_reached(),
            },
            "agents": {
                "current": quota.current_agents,
                "max": quota.max_agents,
                "percentage": quota.get_usage_percentage("agents"),
                "limit_reached": quota.is_agent_limit_reached(),
            },
            "storage": {
                "current_gb": quota.current_storage_gb,
                "max_gb": quota.max_storage_gb,
                "percentage": quota.get_usage_percentage("storage"),
                "limit_reached": quota.is_storage_limit_reached(),
            },
            "compute": {
                "current_hours": quota.current_compute_hours,
                "max_hours": quota.max_compute_hours,
                "percentage": quota.get_usage_percentage("compute"),
                "limit_reached": quota.is_compute_limit_reached(),
                "reset_at": quota.compute_reset_at.isoformat(),
            },
            "tasks": {
                "current": quota.current_concurrent_tasks,
                "max": quota.max_concurrent_tasks,
                "percentage": quota.get_usage_percentage("tasks"),
                "limit_reached": quota.is_task_limit_reached(),
            },
        }
