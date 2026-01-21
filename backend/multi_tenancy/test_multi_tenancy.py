"""Tests for multi-tenancy module.

References:
- Requirements 14: Access Control and Security
- Design Section 8: Security and Access Control
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from multi_tenancy.cross_tenant_analytics import (
    CrossTenantAnalytics,
    TenantMetrics,
)
from multi_tenancy.tenant_branding import (
    BrandAssets,
    BrandColors,
    TenantBrandConfig,
    TenantBranding,
)
from multi_tenancy.tenant_isolation import TenantIsolation
from multi_tenancy.tenant_manager import TenantManager
from multi_tenancy.tenant_model import (
    Tenant,
    TenantPlan,
    TenantStatus,
)
from multi_tenancy.tenant_quotas import (
    TenantQuota,
    TenantQuotaManager,
)


class TestTenantModel:
    """Tests for tenant model."""

    def test_tenant_creation(self):
        """Test creating a tenant."""
        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
            features=["feature1", "feature2"],
            price_per_month=99.0,
        )

        tenant = Tenant(
            tenant_id=uuid4(),
            name="Test Company",
            slug="test-company",
            status=TenantStatus.ACTIVE,
            admin_email="admin@test.com",
            plan=plan,
        )

        assert tenant.name == "Test Company"
        assert tenant.slug == "test-company"
        assert tenant.is_active()

    def test_tenant_trial_status(self):
        """Test tenant trial status."""
        plan = TenantPlan(
            plan_id="trial",
            name="Trial",
            max_users=5,
            max_agents=2,
            max_storage_gb=10,
            max_compute_hours=100,
        )

        tenant = Tenant(
            tenant_id=uuid4(),
            name="Trial Company",
            slug="trial-company",
            status=TenantStatus.TRIAL,
            admin_email="admin@trial.com",
            plan=plan,
            trial_ends_at=datetime.now() + timedelta(days=14),
        )

        assert tenant.is_active()
        assert tenant.status == TenantStatus.TRIAL

    def test_tenant_feature_check(self):
        """Test checking if feature is enabled."""
        plan = TenantPlan(
            plan_id="premium",
            name="Premium",
            max_users=50,
            max_agents=20,
            max_storage_gb=500,
            max_compute_hours=5000,
            features=["advanced_analytics", "custom_branding"],
        )

        tenant = Tenant(
            tenant_id=uuid4(),
            name="Premium Company",
            slug="premium-company",
            status=TenantStatus.ACTIVE,
            admin_email="admin@premium.com",
            plan=plan,
        )

        assert tenant.is_feature_enabled("advanced_analytics")
        assert tenant.is_feature_enabled("custom_branding")
        assert not tenant.is_feature_enabled("nonexistent_feature")


class TestTenantIsolation:
    """Tests for tenant isolation."""

    def test_tenant_context(self):
        """Test setting tenant context."""
        isolation = TenantIsolation()
        tenant_id = uuid4()

        with isolation.tenant_context(tenant_id):
            assert isolation.get_current_tenant_id() == tenant_id

        assert isolation.get_current_tenant_id() is None

    def test_validate_tenant_access(self):
        """Test validating tenant access."""
        isolation = TenantIsolation()
        tenant_id = uuid4()
        other_tenant_id = uuid4()

        # Same tenant - should allow
        assert isolation.validate_tenant_access(tenant_id, tenant_id)

        # Different tenant - should deny
        assert not isolation.validate_tenant_access(tenant_id, other_tenant_id)

    def test_create_rls_policies(self):
        """Test creating RLS policies."""
        isolation = TenantIsolation()
        policies = isolation.create_rls_policies()

        assert "users" in policies
        assert "agents" in policies
        assert "tasks" in policies
        assert "knowledge_items" in policies
        assert "audit_logs" in policies

    def test_milvus_collection_isolation(self):
        """Test Milvus collection isolation."""
        isolation = TenantIsolation()
        tenant_id = uuid4()

        partition = isolation.isolate_milvus_collection("memories", tenant_id)
        assert f"tenant_{tenant_id}" == partition

    def test_minio_bucket_isolation(self):
        """Test MinIO bucket isolation."""
        isolation = TenantIsolation()
        tenant_id = uuid4()

        prefix = isolation.isolate_minio_bucket("documents", tenant_id)
        assert prefix == f"tenant-{tenant_id}/"


class TestTenantQuotas:
    """Tests for tenant quotas."""

    def test_quota_creation(self):
        """Test creating a quota."""
        tenant_id = uuid4()
        quota = TenantQuota(
            tenant_id=tenant_id,
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
        )

        assert quota.tenant_id == tenant_id
        assert quota.max_users == 10
        assert not quota.is_user_limit_reached()

    def test_quota_limits(self):
        """Test quota limit checks."""
        quota = TenantQuota(
            tenant_id=uuid4(),
            max_users=10,
            current_users=10,
            max_agents=5,
            current_agents=5,
            max_storage_gb=100,
            current_storage_gb=100.0,
            max_compute_hours=1000,
            current_compute_hours=1000.0,
        )

        assert quota.is_user_limit_reached()
        assert quota.is_agent_limit_reached()
        assert quota.is_storage_limit_reached()
        assert quota.is_compute_limit_reached()

    def test_quota_usage_percentage(self):
        """Test calculating usage percentage."""
        quota = TenantQuota(
            tenant_id=uuid4(),
            max_users=10,
            current_users=5,
            max_agents=10,
            current_agents=3,
            max_storage_gb=100,
            current_storage_gb=25.0,
            max_compute_hours=1000,
            current_compute_hours=500.0,
        )

        assert quota.get_usage_percentage("users") == 50.0
        assert quota.get_usage_percentage("agents") == 30.0
        assert quota.get_usage_percentage("storage") == 25.0
        assert quota.get_usage_percentage("compute") == 50.0

    def test_quota_manager(self):
        """Test quota manager."""
        manager = TenantQuotaManager()
        tenant_id = uuid4()

        quota = TenantQuota(
            tenant_id=tenant_id,
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
        )

        manager.set_quota(quota)

        assert manager.check_user_quota(tenant_id)
        assert manager.check_agent_quota(tenant_id)

        # Increment counts
        manager.increment_user_count(tenant_id)
        manager.increment_agent_count(tenant_id)

        retrieved_quota = manager.get_quota(tenant_id)
        assert retrieved_quota.current_users == 1
        assert retrieved_quota.current_agents == 1


class TestTenantManager:
    """Tests for tenant manager."""

    def test_create_tenant(self):
        """Test creating a tenant."""
        manager = TenantManager()

        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
        )

        tenant = manager.create_tenant(
            name="Test Company",
            admin_email="admin@test.com",
            plan=plan,
        )

        assert tenant.name == "Test Company"
        assert tenant.slug == "test-company"
        assert tenant.status == TenantStatus.ACTIVE

    def test_create_trial_tenant(self):
        """Test creating a trial tenant."""
        manager = TenantManager()

        plan = TenantPlan(
            plan_id="trial",
            name="Trial",
            max_users=5,
            max_agents=2,
            max_storage_gb=10,
            max_compute_hours=100,
        )

        tenant = manager.create_tenant(
            name="Trial Company",
            admin_email="admin@trial.com",
            plan=plan,
            trial_days=14,
        )

        assert tenant.status == TenantStatus.TRIAL
        assert tenant.trial_ends_at is not None

    def test_get_tenant(self):
        """Test getting a tenant."""
        manager = TenantManager()

        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
        )

        tenant = manager.create_tenant(
            name="Test Company",
            admin_email="admin@test.com",
            plan=plan,
        )

        retrieved = manager.get_tenant(tenant.tenant_id)
        assert retrieved.tenant_id == tenant.tenant_id

    def test_update_tenant(self):
        """Test updating a tenant."""
        manager = TenantManager()

        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
        )

        tenant = manager.create_tenant(
            name="Test Company",
            admin_email="admin@test.com",
            plan=plan,
        )

        updated = manager.update_tenant(
            tenant.tenant_id,
            name="Updated Company",
        )

        assert updated.name == "Updated Company"

    def test_suspend_tenant(self):
        """Test suspending a tenant."""
        manager = TenantManager()

        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
        )

        tenant = manager.create_tenant(
            name="Test Company",
            admin_email="admin@test.com",
            plan=plan,
        )

        suspended = manager.suspend_tenant(tenant.tenant_id)
        assert suspended.status == TenantStatus.SUSPENDED


class TestTenantBranding:
    """Tests for tenant branding."""

    def test_branding_creation(self):
        """Test creating branding configuration."""
        tenant_id = uuid4()

        config = TenantBrandConfig(
            tenant_id=tenant_id,
            company_name="Test Company",
            tagline="We test things",
        )

        assert config.tenant_id == tenant_id
        assert config.company_name == "Test Company"

    def test_update_colors(self):
        """Test updating brand colors."""
        branding = TenantBranding()
        tenant_id = uuid4()

        config = TenantBrandConfig(
            tenant_id=tenant_id,
            company_name="Test Company",
        )

        branding.set_branding(config)

        new_colors = BrandColors(
            primary="#FF0000",
            secondary="#00FF00",
        )

        updated = branding.update_colors(tenant_id, new_colors)
        assert updated.colors.primary == "#FF0000"

    def test_generate_theme_css(self):
        """Test generating theme CSS."""
        branding = TenantBranding()
        tenant_id = uuid4()

        config = TenantBrandConfig(
            tenant_id=tenant_id,
            company_name="Test Company",
        )

        branding.set_branding(config)

        css = branding.generate_theme_css(tenant_id)
        assert "--color-primary" in css
        assert "--color-secondary" in css


class TestCrossTenantAnalytics:
    """Tests for cross-tenant analytics."""

    def test_collect_tenant_metrics(self):
        """Test collecting tenant metrics."""
        analytics = CrossTenantAnalytics()

        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
            price_per_month=99.0,
        )

        tenant = Tenant(
            tenant_id=uuid4(),
            name="Test Company",
            slug="test-company",
            status=TenantStatus.ACTIVE,
            admin_email="admin@test.com",
            plan=plan,
        )

        metrics = analytics.collect_tenant_metrics(tenant)

        assert metrics.tenant_id == tenant.tenant_id
        assert metrics.tenant_name == tenant.name

    def test_get_platform_metrics(self):
        """Test getting platform metrics."""
        analytics = CrossTenantAnalytics()

        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
            price_per_month=99.0,
        )

        tenants = [
            Tenant(
                tenant_id=uuid4(),
                name=f"Company {i}",
                slug=f"company-{i}",
                status=TenantStatus.ACTIVE,
                admin_email=f"admin{i}@test.com",
                plan=plan,
            )
            for i in range(5)
        ]

        platform_metrics = analytics.get_platform_metrics(tenants)

        assert platform_metrics.total_tenants == 5
        assert platform_metrics.active_tenants == 5

    def test_generate_platform_report(self):
        """Test generating platform report."""
        analytics = CrossTenantAnalytics()

        plan = TenantPlan(
            plan_id="standard",
            name="Standard",
            max_users=10,
            max_agents=5,
            max_storage_gb=100,
            max_compute_hours=1000,
            price_per_month=99.0,
        )

        tenants = [
            Tenant(
                tenant_id=uuid4(),
                name=f"Company {i}",
                slug=f"company-{i}",
                status=TenantStatus.ACTIVE,
                admin_email=f"admin{i}@test.com",
                plan=plan,
            )
            for i in range(3)
        ]

        report = analytics.generate_platform_report(tenants)

        assert "platform_metrics" in report
        assert "top_tenants" in report
        assert "usage_distribution" in report
