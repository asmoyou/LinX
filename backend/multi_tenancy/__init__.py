"""Multi-tenancy support module.

References:
- Requirements 14: Access Control and Security
- Design Section 8: Security and Access Control

This module provides multi-tenant capabilities for the platform:
- Tenant isolation in database
- Tenant-specific resource quotas
- Tenant management API
- Tenant-specific branding
- Cross-tenant analytics
"""

from multi_tenancy.cross_tenant_analytics import CrossTenantAnalytics
from multi_tenancy.tenant_branding import TenantBranding
from multi_tenancy.tenant_isolation import TenantIsolation
from multi_tenancy.tenant_manager import TenantManager
from multi_tenancy.tenant_model import Tenant, TenantStatus
from multi_tenancy.tenant_quotas import TenantQuotaManager

__all__ = [
    "Tenant",
    "TenantStatus",
    "TenantIsolation",
    "TenantQuotaManager",
    "TenantManager",
    "TenantBranding",
    "CrossTenantAnalytics",
]
