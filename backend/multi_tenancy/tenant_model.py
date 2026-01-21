"""Tenant data model.

References:
- Requirements 14: Access Control and Security
- Design Section 8: Security and Access Control
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class TenantStatus(Enum):
    """Tenant status."""
    
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TRIAL = "trial"
    INACTIVE = "inactive"


@dataclass
class TenantPlan:
    """Tenant subscription plan."""
    
    plan_id: str
    name: str
    max_users: int
    max_agents: int
    max_storage_gb: int
    max_compute_hours: int
    features: list[str] = field(default_factory=list)
    price_per_month: float = 0.0


@dataclass
class Tenant:
    """Tenant entity."""
    
    tenant_id: UUID
    name: str
    slug: str  # URL-friendly identifier
    status: TenantStatus
    
    # Contact information
    admin_email: str
    admin_name: Optional[str] = None
    
    # Subscription
    plan: Optional[TenantPlan] = None
    trial_ends_at: Optional[datetime] = None
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Settings
    settings: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_active(self) -> bool:
        """Check if tenant is active.
        
        Returns:
            True if tenant is active
        """
        if self.status == TenantStatus.TRIAL:
            if self.trial_ends_at and datetime.now() > self.trial_ends_at:
                return False
        
        return self.status in [TenantStatus.ACTIVE, TenantStatus.TRIAL]
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled for this tenant.
        
        Args:
            feature: Feature name
            
        Returns:
            True if feature is enabled
        """
        if not self.plan:
            return False
        
        return feature in self.plan.features
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.
        
        Returns:
            Dictionary representation
        """
        return {
            "tenant_id": str(self.tenant_id),
            "name": self.name,
            "slug": self.slug,
            "status": self.status.value,
            "admin_email": self.admin_email,
            "admin_name": self.admin_name,
            "plan": {
                "plan_id": self.plan.plan_id,
                "name": self.plan.name,
                "max_users": self.plan.max_users,
                "max_agents": self.plan.max_agents,
                "max_storage_gb": self.plan.max_storage_gb,
                "max_compute_hours": self.plan.max_compute_hours,
                "features": self.plan.features,
            } if self.plan else None,
            "trial_ends_at": self.trial_ends_at.isoformat() if self.trial_ends_at else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "settings": self.settings,
            "metadata": self.metadata,
        }
