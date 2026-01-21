"""Cross-tenant analytics for platform admins.

References:
- Requirements 11: Monitoring and Analytics
- Requirements 14: Access Control and Security
"""

import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from multi_tenancy.tenant_model import Tenant, TenantStatus

logger = logging.getLogger(__name__)


@dataclass
class TenantMetrics:
    """Metrics for a single tenant."""

    tenant_id: UUID
    tenant_name: str

    # User metrics
    total_users: int = 0
    active_users: int = 0

    # Agent metrics
    total_agents: int = 0
    active_agents: int = 0

    # Task metrics
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_task_duration: float = 0.0

    # Resource usage
    storage_used_gb: float = 0.0
    compute_hours_used: float = 0.0

    # Financial
    monthly_revenue: float = 0.0

    # Engagement
    last_activity_at: Optional[datetime] = None
    days_since_last_activity: int = 0


@dataclass
class PlatformMetrics:
    """Platform-wide metrics."""

    # Tenant metrics
    total_tenants: int = 0
    active_tenants: int = 0
    trial_tenants: int = 0
    suspended_tenants: int = 0

    # User metrics
    total_users: int = 0
    active_users: int = 0

    # Agent metrics
    total_agents: int = 0
    active_agents: int = 0

    # Task metrics
    total_tasks_completed: int = 0
    total_tasks_failed: int = 0
    avg_task_duration: float = 0.0

    # Resource usage
    total_storage_gb: float = 0.0
    total_compute_hours: float = 0.0

    # Financial
    total_monthly_revenue: float = 0.0
    avg_revenue_per_tenant: float = 0.0

    # Growth
    new_tenants_this_month: int = 0
    churned_tenants_this_month: int = 0
    growth_rate: float = 0.0


class CrossTenantAnalytics:
    """Cross-tenant analytics for platform administrators.

    Provides platform-wide insights:
    - Tenant metrics and comparisons
    - Platform health metrics
    - Revenue analytics
    - Usage patterns
    - Churn analysis
    """

    def __init__(self, database=None):
        """Initialize cross-tenant analytics.

        Args:
            database: Database connection
        """
        self.database = database
        self.tenant_metrics: Dict[UUID, TenantMetrics] = {}

        logger.info("CrossTenantAnalytics initialized")

    def collect_tenant_metrics(
        self,
        tenant: Tenant,
    ) -> TenantMetrics:
        """Collect metrics for a tenant.

        Args:
            tenant: Tenant

        Returns:
            TenantMetrics
        """
        # In real implementation, query database for actual metrics
        # This is a mock implementation
        metrics = TenantMetrics(
            tenant_id=tenant.tenant_id,
            tenant_name=tenant.name,
            total_users=10,
            active_users=8,
            total_agents=5,
            active_agents=3,
            tasks_completed=100,
            tasks_failed=5,
            avg_task_duration=45.5,
            storage_used_gb=2.5,
            compute_hours_used=10.0,
            monthly_revenue=tenant.plan.price_per_month if tenant.plan else 0.0,
            last_activity_at=datetime.now() - timedelta(days=1),
            days_since_last_activity=1,
        )

        self.tenant_metrics[tenant.tenant_id] = metrics
        return metrics

    def get_platform_metrics(
        self,
        tenants: List[Tenant],
    ) -> PlatformMetrics:
        """Get platform-wide metrics.

        Args:
            tenants: List of all tenants

        Returns:
            PlatformMetrics
        """
        metrics = PlatformMetrics()

        # Collect metrics for all tenants
        for tenant in tenants:
            tenant_metrics = self.collect_tenant_metrics(tenant)

            # Aggregate tenant counts
            metrics.total_tenants += 1
            if tenant.status == TenantStatus.ACTIVE:
                metrics.active_tenants += 1
            elif tenant.status == TenantStatus.TRIAL:
                metrics.trial_tenants += 1
            elif tenant.status == TenantStatus.SUSPENDED:
                metrics.suspended_tenants += 1

            # Aggregate user metrics
            metrics.total_users += tenant_metrics.total_users
            metrics.active_users += tenant_metrics.active_users

            # Aggregate agent metrics
            metrics.total_agents += tenant_metrics.total_agents
            metrics.active_agents += tenant_metrics.active_agents

            # Aggregate task metrics
            metrics.total_tasks_completed += tenant_metrics.tasks_completed
            metrics.total_tasks_failed += tenant_metrics.tasks_failed

            # Aggregate resource usage
            metrics.total_storage_gb += tenant_metrics.storage_used_gb
            metrics.total_compute_hours += tenant_metrics.compute_hours_used

            # Aggregate revenue
            metrics.total_monthly_revenue += tenant_metrics.monthly_revenue

        # Calculate averages
        if metrics.total_tenants > 0:
            metrics.avg_revenue_per_tenant = metrics.total_monthly_revenue / metrics.total_tenants

        total_tasks = metrics.total_tasks_completed + metrics.total_tasks_failed
        if total_tasks > 0:
            # Calculate weighted average task duration
            durations = [m.avg_task_duration for m in self.tenant_metrics.values()]
            if durations:
                metrics.avg_task_duration = statistics.mean(durations)

        # Calculate growth metrics
        now = datetime.now()
        month_start = datetime(now.year, now.month, 1)

        for tenant in tenants:
            if tenant.created_at >= month_start:
                metrics.new_tenants_this_month += 1

            if tenant.status == TenantStatus.INACTIVE and tenant.updated_at >= month_start:
                metrics.churned_tenants_this_month += 1

        # Calculate growth rate
        if metrics.total_tenants > 0:
            metrics.growth_rate = (
                (metrics.new_tenants_this_month - metrics.churned_tenants_this_month)
                / metrics.total_tenants
                * 100
            )

        logger.info("Collected platform metrics")
        return metrics

    def get_top_tenants_by_usage(
        self,
        limit: int = 10,
    ) -> List[TenantMetrics]:
        """Get top tenants by resource usage.

        Args:
            limit: Maximum number of results

        Returns:
            List of tenant metrics
        """
        sorted_tenants = sorted(
            self.tenant_metrics.values(),
            key=lambda m: m.compute_hours_used,
            reverse=True,
        )

        return sorted_tenants[:limit]

    def get_top_tenants_by_revenue(
        self,
        limit: int = 10,
    ) -> List[TenantMetrics]:
        """Get top tenants by revenue.

        Args:
            limit: Maximum number of results

        Returns:
            List of tenant metrics
        """
        sorted_tenants = sorted(
            self.tenant_metrics.values(),
            key=lambda m: m.monthly_revenue,
            reverse=True,
        )

        return sorted_tenants[:limit]

    def get_inactive_tenants(
        self,
        days_threshold: int = 30,
    ) -> List[TenantMetrics]:
        """Get tenants with no recent activity.

        Args:
            days_threshold: Days of inactivity threshold

        Returns:
            List of inactive tenant metrics
        """
        inactive = []

        for metrics in self.tenant_metrics.values():
            if metrics.days_since_last_activity >= days_threshold:
                inactive.append(metrics)

        return sorted(inactive, key=lambda m: m.days_since_last_activity, reverse=True)

    def get_at_risk_tenants(self) -> List[TenantMetrics]:
        """Get tenants at risk of churning.

        Returns:
            List of at-risk tenant metrics
        """
        at_risk = []

        for metrics in self.tenant_metrics.values():
            # Criteria for at-risk:
            # - Low active users
            # - High failure rate
            # - No recent activity

            user_activity_rate = (
                metrics.active_users / metrics.total_users if metrics.total_users > 0 else 0
            )

            total_tasks = metrics.tasks_completed + metrics.tasks_failed
            failure_rate = metrics.tasks_failed / total_tasks if total_tasks > 0 else 0

            if (
                user_activity_rate < 0.3
                or failure_rate > 0.2
                or metrics.days_since_last_activity > 14
            ):
                at_risk.append(metrics)

        return at_risk

    def get_usage_distribution(self) -> Dict[str, Any]:
        """Get usage distribution across tenants.

        Returns:
            Dictionary with distribution data
        """
        if not self.tenant_metrics:
            return {}

        compute_hours = [m.compute_hours_used for m in self.tenant_metrics.values()]
        storage_gb = [m.storage_used_gb for m in self.tenant_metrics.values()]
        users = [m.total_users for m in self.tenant_metrics.values()]

        return {
            "compute_hours": {
                "min": min(compute_hours) if compute_hours else 0,
                "max": max(compute_hours) if compute_hours else 0,
                "avg": statistics.mean(compute_hours) if compute_hours else 0,
                "median": statistics.median(compute_hours) if compute_hours else 0,
            },
            "storage_gb": {
                "min": min(storage_gb) if storage_gb else 0,
                "max": max(storage_gb) if storage_gb else 0,
                "avg": statistics.mean(storage_gb) if storage_gb else 0,
                "median": statistics.median(storage_gb) if storage_gb else 0,
            },
            "users": {
                "min": min(users) if users else 0,
                "max": max(users) if users else 0,
                "avg": statistics.mean(users) if users else 0,
                "median": statistics.median(users) if users else 0,
            },
        }

    def get_revenue_breakdown(self) -> Dict[str, Any]:
        """Get revenue breakdown by plan.

        Returns:
            Dictionary with revenue data
        """
        revenue_by_plan: Dict[str, float] = {}
        tenant_count_by_plan: Dict[str, int] = {}

        for metrics in self.tenant_metrics.values():
            # Get plan name (would come from tenant data in real implementation)
            plan_name = "Standard"  # Mock

            if plan_name not in revenue_by_plan:
                revenue_by_plan[plan_name] = 0.0
                tenant_count_by_plan[plan_name] = 0

            revenue_by_plan[plan_name] += metrics.monthly_revenue
            tenant_count_by_plan[plan_name] += 1

        return {
            "by_plan": [
                {
                    "plan": plan,
                    "revenue": revenue,
                    "tenant_count": tenant_count_by_plan[plan],
                    "avg_revenue_per_tenant": revenue / tenant_count_by_plan[plan],
                }
                for plan, revenue in revenue_by_plan.items()
            ],
            "total_revenue": sum(revenue_by_plan.values()),
        }

    def generate_platform_report(
        self,
        tenants: List[Tenant],
    ) -> Dict[str, Any]:
        """Generate comprehensive platform report.

        Args:
            tenants: List of all tenants

        Returns:
            Dictionary with platform report
        """
        platform_metrics = self.get_platform_metrics(tenants)

        return {
            "generated_at": datetime.now().isoformat(),
            "platform_metrics": {
                "tenants": {
                    "total": platform_metrics.total_tenants,
                    "active": platform_metrics.active_tenants,
                    "trial": platform_metrics.trial_tenants,
                    "suspended": platform_metrics.suspended_tenants,
                },
                "users": {
                    "total": platform_metrics.total_users,
                    "active": platform_metrics.active_users,
                },
                "agents": {
                    "total": platform_metrics.total_agents,
                    "active": platform_metrics.active_agents,
                },
                "tasks": {
                    "completed": platform_metrics.total_tasks_completed,
                    "failed": platform_metrics.total_tasks_failed,
                    "avg_duration": platform_metrics.avg_task_duration,
                },
                "resources": {
                    "storage_gb": platform_metrics.total_storage_gb,
                    "compute_hours": platform_metrics.total_compute_hours,
                },
                "revenue": {
                    "total_monthly": platform_metrics.total_monthly_revenue,
                    "avg_per_tenant": platform_metrics.avg_revenue_per_tenant,
                },
                "growth": {
                    "new_tenants": platform_metrics.new_tenants_this_month,
                    "churned_tenants": platform_metrics.churned_tenants_this_month,
                    "growth_rate": platform_metrics.growth_rate,
                },
            },
            "top_tenants": {
                "by_usage": [
                    {
                        "tenant_id": str(m.tenant_id),
                        "name": m.tenant_name,
                        "compute_hours": m.compute_hours_used,
                    }
                    for m in self.get_top_tenants_by_usage(5)
                ],
                "by_revenue": [
                    {
                        "tenant_id": str(m.tenant_id),
                        "name": m.tenant_name,
                        "revenue": m.monthly_revenue,
                    }
                    for m in self.get_top_tenants_by_revenue(5)
                ],
            },
            "at_risk_tenants": [
                {
                    "tenant_id": str(m.tenant_id),
                    "name": m.tenant_name,
                    "days_inactive": m.days_since_last_activity,
                }
                for m in self.get_at_risk_tenants()
            ],
            "usage_distribution": self.get_usage_distribution(),
            "revenue_breakdown": self.get_revenue_breakdown(),
        }
