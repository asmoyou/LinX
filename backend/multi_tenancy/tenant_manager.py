"""Tenant management API.

References:
- Requirements 14: Access Control and Security
- Design Section 8: Security and Access Control
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from multi_tenancy.tenant_isolation import TenantIsolation
from multi_tenancy.tenant_model import Tenant, TenantPlan, TenantStatus
from multi_tenancy.tenant_quotas import TenantQuota, TenantQuotaManager

logger = logging.getLogger(__name__)


class TenantManager:
    """Tenant management system.

    Manages tenant lifecycle:
    - Tenant creation and deletion
    - Tenant updates
    - Tenant status management
    - Tenant listing and search
    """

    def __init__(
        self,
        database=None,
        isolation: Optional[TenantIsolation] = None,
        quota_manager: Optional[TenantQuotaManager] = None,
    ):
        """Initialize tenant manager.

        Args:
            database: Database connection
            isolation: Tenant isolation manager
            quota_manager: Quota manager
        """
        self.database = database
        self.isolation = isolation or TenantIsolation(database)
        self.quota_manager = quota_manager or TenantQuotaManager(database)
        self.tenants: Dict[UUID, Tenant] = {}

        logger.info("TenantManager initialized")

    def create_tenant(
        self,
        name: str,
        admin_email: str,
        plan: TenantPlan,
        admin_name: Optional[str] = None,
        trial_days: int = 0,
    ) -> Tenant:
        """Create a new tenant.

        Args:
            name: Tenant name
            admin_email: Admin email
            plan: Subscription plan
            admin_name: Admin name
            trial_days: Trial period in days

        Returns:
            Created tenant
        """
        # Generate slug from name
        slug = self._generate_slug(name)

        # Validate slug uniqueness
        if self._slug_exists(slug):
            raise ValueError(f"Tenant slug already exists: {slug}")

        # Determine status
        status = TenantStatus.TRIAL if trial_days > 0 else TenantStatus.ACTIVE
        trial_ends_at = datetime.now() + timedelta(days=trial_days) if trial_days > 0 else None

        # Create tenant
        tenant = Tenant(
            tenant_id=uuid4(),
            name=name,
            slug=slug,
            status=status,
            admin_email=admin_email,
            admin_name=admin_name,
            plan=plan,
            trial_ends_at=trial_ends_at,
        )

        self.tenants[tenant.tenant_id] = tenant

        # Create quota
        quota = TenantQuota(
            tenant_id=tenant.tenant_id,
            max_users=plan.max_users,
            max_agents=plan.max_agents,
            max_storage_gb=plan.max_storage_gb,
            max_compute_hours=plan.max_compute_hours,
        )
        self.quota_manager.set_quota(quota)

        logger.info(f"Created tenant: {tenant.tenant_id} ({tenant.name})")
        return tenant

    def get_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """Get tenant by ID.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant or None
        """
        return self.tenants.get(tenant_id)

    def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get tenant by slug.

        Args:
            slug: Tenant slug

        Returns:
            Tenant or None
        """
        for tenant in self.tenants.values():
            if tenant.slug == slug:
                return tenant
        return None

    def list_tenants(
        self,
        status: Optional[TenantStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Tenant]:
        """List tenants.

        Args:
            status: Filter by status
            limit: Maximum number of results
            offset: Offset for pagination

        Returns:
            List of tenants
        """
        tenants = list(self.tenants.values())

        if status:
            tenants = [t for t in tenants if t.status == status]

        return tenants[offset : offset + limit]

    def update_tenant(
        self,
        tenant_id: UUID,
        name: Optional[str] = None,
        admin_email: Optional[str] = None,
        admin_name: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tenant]:
        """Update tenant.

        Args:
            tenant_id: Tenant ID
            name: New name
            admin_email: New admin email
            admin_name: New admin name
            settings: New settings

        Returns:
            Updated tenant or None
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            logger.warning(f"Tenant not found: {tenant_id}")
            return None

        if name:
            tenant.name = name
            tenant.slug = self._generate_slug(name)

        if admin_email:
            tenant.admin_email = admin_email

        if admin_name:
            tenant.admin_name = admin_name

        if settings:
            tenant.settings.update(settings)

        tenant.updated_at = datetime.now()

        logger.info(f"Updated tenant: {tenant_id}")
        return tenant

    def update_tenant_status(
        self,
        tenant_id: UUID,
        status: TenantStatus,
    ) -> Optional[Tenant]:
        """Update tenant status.

        Args:
            tenant_id: Tenant ID
            status: New status

        Returns:
            Updated tenant or None
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            logger.warning(f"Tenant not found: {tenant_id}")
            return None

        old_status = tenant.status
        tenant.status = status
        tenant.updated_at = datetime.now()

        logger.info(f"Updated tenant {tenant_id} status: {old_status.value} -> {status.value}")
        return tenant

    def suspend_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """Suspend a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Updated tenant or None
        """
        return self.update_tenant_status(tenant_id, TenantStatus.SUSPENDED)

    def activate_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """Activate a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Updated tenant or None
        """
        return self.update_tenant_status(tenant_id, TenantStatus.ACTIVE)

    def delete_tenant(self, tenant_id: UUID) -> bool:
        """Delete a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            True if deleted
        """
        if tenant_id in self.tenants:
            del self.tenants[tenant_id]
            logger.info(f"Deleted tenant: {tenant_id}")
            return True

        logger.warning(f"Tenant not found for deletion: {tenant_id}")
        return False

    def update_tenant_plan(
        self,
        tenant_id: UUID,
        plan: TenantPlan,
    ) -> Optional[Tenant]:
        """Update tenant subscription plan.

        Args:
            tenant_id: Tenant ID
            plan: New plan

        Returns:
            Updated tenant or None
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            logger.warning(f"Tenant not found: {tenant_id}")
            return None

        tenant.plan = plan
        tenant.updated_at = datetime.now()

        # Update quota
        quota = self.quota_manager.get_quota(tenant_id)
        if quota:
            quota.max_users = plan.max_users
            quota.max_agents = plan.max_agents
            quota.max_storage_gb = plan.max_storage_gb
            quota.max_compute_hours = plan.max_compute_hours

        logger.info(f"Updated tenant {tenant_id} plan to: {plan.name}")
        return tenant

    def _generate_slug(self, name: str) -> str:
        """Generate URL-friendly slug from name.

        Args:
            name: Tenant name

        Returns:
            Slug
        """
        # Convert to lowercase and replace spaces with hyphens
        slug = name.lower().strip()
        slug = re.sub(r"[^\w\s-]", "", slug)
        slug = re.sub(r"[-\s]+", "-", slug)

        return slug

    def _slug_exists(self, slug: str) -> bool:
        """Check if slug already exists.

        Args:
            slug: Slug to check

        Returns:
            True if exists
        """
        return any(t.slug == slug for t in self.tenants.values())

    def get_tenant_stats(self, tenant_id: UUID) -> Dict[str, Any]:
        """Get tenant statistics.

        Args:
            tenant_id: Tenant ID

        Returns:
            Dictionary with tenant stats
        """
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            return {"error": "Tenant not found"}

        quota_status = self.quota_manager.get_quota_status(tenant_id)

        return {
            "tenant": tenant.to_dict(),
            "quota": quota_status,
            "is_active": tenant.is_active(),
        }
