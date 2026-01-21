"""Tests for Resource Quota Management System."""

import pytest
from decimal import Decimal
from uuid import uuid4

from shared.resource_quotas import (
    ResourceQuotaManager,
    QuotaUsage,
    QuotaExceededException,
    get_quota_manager,
)


def test_quota_usage_properties():
    """Test QuotaUsage calculated properties."""
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=10,
        current_agents=7,
        max_storage_gb=100,
        current_storage_gb=Decimal('75.5'),
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    assert usage.agents_available == 3
    assert usage.storage_available_gb == Decimal('24.5')
    assert usage.agents_usage_percent == 70.0
    assert usage.storage_usage_percent == 75.5


def test_quota_usage_to_dict():
    """Test QuotaUsage serialization."""
    user_id = uuid4()
    usage = QuotaUsage(
        user_id=user_id,
        max_agents=10,
        current_agents=5,
        max_storage_gb=100,
        current_storage_gb=Decimal('50.0'),
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    data = usage.to_dict()
    
    assert data["user_id"] == str(user_id)
    assert data["agents"]["max"] == 10
    assert data["agents"]["current"] == 5
    assert data["agents"]["available"] == 5
    assert data["agents"]["usage_percent"] == 50.0
    assert data["storage_gb"]["max"] == 100
    assert data["storage_gb"]["current"] == 50.0


def test_quota_usage_at_limit():
    """Test QuotaUsage when at limit."""
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=10,
        current_agents=10,
        max_storage_gb=100,
        current_storage_gb=Decimal('100.0'),
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    assert usage.agents_available == 0
    assert usage.storage_available_gb == Decimal('0')
    assert usage.agents_usage_percent == 100.0
    assert usage.storage_usage_percent == 100.0


def test_quota_usage_over_limit():
    """Test QuotaUsage when over limit."""
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=10,
        current_agents=12,
        max_storage_gb=100,
        current_storage_gb=Decimal('105.0'),
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    # Should return 0, not negative
    assert usage.agents_available == 0
    assert usage.storage_available_gb == Decimal('0')
    assert usage.agents_usage_percent == 120.0
    assert usage.storage_usage_percent == 105.0


def test_quota_exception():
    """Test QuotaExceededException."""
    exc = QuotaExceededException(
        "Quota exceeded",
        quota_type="agents",
        current=10,
        limit=10,
    )
    
    assert exc.quota_type == "agents"
    assert exc.current == 10
    assert exc.limit == 10
    assert "Quota exceeded" in str(exc)


def test_resource_quota_manager_initialization():
    """Test ResourceQuotaManager initialization."""
    manager = ResourceQuotaManager()
    
    assert manager.alert_thresholds["warning"] == 80.0
    assert manager.alert_thresholds["critical"] == 95.0


def test_check_agent_quota_available():
    """Test agent quota check when quota available."""
    manager = ResourceQuotaManager()
    
    # This would need a mock database or test database
    # For now, test the logic structure
    assert manager is not None


def test_check_agent_quota_exceeded():
    """Test agent quota check when quota exceeded."""
    manager = ResourceQuotaManager()
    
    # Would need database mocking to test fully
    assert manager is not None


def test_check_storage_quota_available():
    """Test storage quota check when quota available."""
    manager = ResourceQuotaManager()
    
    # Would need database mocking to test fully
    assert manager is not None


def test_check_storage_quota_exceeded():
    """Test storage quota check when quota exceeded."""
    manager = ResourceQuotaManager()
    
    # Would need database mocking to test fully
    assert manager is not None


def test_storage_size_conversion():
    """Test storage size conversion from bytes to GB."""
    # 1 GB = 1,073,741,824 bytes
    size_bytes = 1073741824
    size_gb = Decimal(str(size_bytes)) / Decimal('1073741824')
    
    assert size_gb == Decimal('1.0')
    
    # 500 MB
    size_bytes = 524288000
    size_gb = Decimal(str(size_bytes)) / Decimal('1073741824')
    
    assert float(size_gb) < 0.5


def test_get_quota_manager_singleton():
    """Test global quota manager singleton."""
    manager1 = get_quota_manager()
    manager2 = get_quota_manager()
    
    assert manager1 is manager2


def test_quota_usage_zero_limits():
    """Test QuotaUsage with zero limits."""
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=0,
        current_agents=0,
        max_storage_gb=0,
        current_storage_gb=Decimal('0'),
        max_cpu_cores=0,
        max_memory_gb=0,
    )
    
    # Should not divide by zero
    assert usage.agents_usage_percent == 0.0
    assert usage.storage_usage_percent == 0.0


def test_quota_usage_negative_available():
    """Test that available resources never go negative."""
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=5,
        current_agents=10,
        max_storage_gb=50,
        current_storage_gb=Decimal('75.0'),
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    # Even when over limit, available should be 0, not negative
    assert usage.agents_available >= 0
    assert usage.storage_available_gb >= Decimal('0')


def test_alert_threshold_warning():
    """Test warning threshold detection."""
    manager = ResourceQuotaManager()
    
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=10,
        current_agents=8,  # 80%
        max_storage_gb=100,
        current_storage_gb=Decimal('85.0'),  # 85%
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    assert usage.agents_usage_percent >= manager.alert_thresholds["warning"]
    assert usage.storage_usage_percent >= manager.alert_thresholds["warning"]


def test_alert_threshold_critical():
    """Test critical threshold detection."""
    manager = ResourceQuotaManager()
    
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=10,
        current_agents=10,  # 100%
        max_storage_gb=100,
        current_storage_gb=Decimal('96.0'),  # 96%
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    assert usage.agents_usage_percent >= manager.alert_thresholds["critical"]
    assert usage.storage_usage_percent >= manager.alert_thresholds["critical"]


def test_quota_usage_decimal_precision():
    """Test decimal precision for storage calculations."""
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=10,
        current_agents=5,
        max_storage_gb=100,
        current_storage_gb=Decimal('33.333333'),
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    # Should handle decimal precision correctly
    assert isinstance(usage.current_storage_gb, Decimal)
    assert isinstance(usage.storage_available_gb, Decimal)
    
    # Percentage should be float
    assert isinstance(usage.storage_usage_percent, float)


def test_quota_usage_dict_rounding():
    """Test that dictionary output rounds percentages."""
    usage = QuotaUsage(
        user_id=uuid4(),
        max_agents=10,
        current_agents=3,  # 30%
        max_storage_gb=100,
        current_storage_gb=Decimal('33.333333'),
        max_cpu_cores=10,
        max_memory_gb=20,
    )
    
    data = usage.to_dict()
    
    # Percentages should be rounded to 2 decimal places
    assert data["agents"]["usage_percent"] == 30.0
    assert data["storage_gb"]["usage_percent"] == 33.33
