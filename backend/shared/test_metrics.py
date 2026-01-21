"""Tests for Prometheus Metrics Collection System."""

import pytest
import time
from shared.metrics import (
    MetricsManager,
    get_metrics_manager,
    get_health_status,
    HealthStatus,
    track_time,
    collect_system_metrics,
    # Import some metrics to test
    api_requests_total,
    tasks_created_total,
    agents_total,
    llm_requests_total,
)


def test_health_status_creation():
    """Test HealthStatus creation."""
    status = HealthStatus("test-component", True, "All good")
    
    assert status.name == "test-component"
    assert status.healthy is True
    assert status.message == "All good"


def test_health_status_to_dict():
    """Test HealthStatus serialization."""
    status = HealthStatus("test-component", False, "Error occurred")
    
    data = status.to_dict()
    
    assert data["name"] == "test-component"
    assert data["healthy"] is False
    assert data["message"] == "Error occurred"


def test_get_health_status():
    """Test overall health status retrieval."""
    health = get_health_status()
    
    assert "status" in health
    assert "checks" in health
    assert "timestamp" in health
    assert health["status"] in ["healthy", "unhealthy"]
    assert isinstance(health["checks"], list)
    assert isinstance(health["timestamp"], float)


def test_collect_system_metrics():
    """Test system metrics collection."""
    # Should not raise any exceptions
    collect_system_metrics()


def test_metrics_manager_initialization():
    """Test MetricsManager initialization."""
    manager = MetricsManager()
    
    assert manager._collection_interval == 15
    assert manager._last_collection == 0


def test_metrics_manager_should_collect():
    """Test collection timing logic."""
    manager = MetricsManager()
    
    # First call should return True
    assert manager.should_collect() is True
    
    # Immediate second call should return False
    assert manager.should_collect() is False
    
    # After waiting, should return True again
    time.sleep(0.1)
    manager._collection_interval = 0.05  # Reduce for testing
    assert manager.should_collect() is True


def test_get_metrics_manager_singleton():
    """Test global metrics manager singleton."""
    manager1 = get_metrics_manager()
    manager2 = get_metrics_manager()
    
    assert manager1 is manager2


def test_api_metrics_increment():
    """Test API metrics can be incremented."""
    initial_value = api_requests_total.labels(
        method="GET",
        endpoint="/test",
        status="200"
    )._value.get()
    
    api_requests_total.labels(
        method="GET",
        endpoint="/test",
        status="200"
    ).inc()
    
    new_value = api_requests_total.labels(
        method="GET",
        endpoint="/test",
        status="200"
    )._value.get()
    
    assert new_value == initial_value + 1


def test_task_metrics_increment():
    """Test task metrics can be incremented."""
    tasks_created_total.labels(user_id="test-user").inc()
    
    # Should not raise exception
    assert True


def test_agent_metrics_gauge():
    """Test agent metrics gauge."""
    agents_total.labels(status="active").set(5)
    
    value = agents_total.labels(status="active")._value.get()
    assert value == 5
    
    agents_total.labels(status="active").set(10)
    value = agents_total.labels(status="active")._value.get()
    assert value == 10


def test_llm_metrics_increment():
    """Test LLM metrics can be incremented."""
    llm_requests_total.labels(
        provider="ollama",
        model="llama2"
    ).inc()
    
    # Should not raise exception
    assert True


def test_track_time_decorator_sync():
    """Test track_time decorator with synchronous function."""
    from shared.metrics import Histogram, registry
    
    test_metric = Histogram(
        'test_duration_seconds',
        'Test duration',
        registry=registry
    )
    
    @track_time(test_metric)
    def slow_function():
        time.sleep(0.01)
        return "done"
    
    result = slow_function()
    
    assert result == "done"
    # Metric should have recorded the duration
    assert test_metric._sum.get() > 0


@pytest.mark.asyncio
async def test_track_time_decorator_async():
    """Test track_time decorator with async function."""
    import asyncio
    from shared.metrics import Histogram, registry
    
    test_metric = Histogram(
        'test_async_duration_seconds',
        'Test async duration',
        registry=registry
    )
    
    @track_time(test_metric)
    async def slow_async_function():
        await asyncio.sleep(0.01)
        return "done"
    
    result = await slow_async_function()
    
    assert result == "done"
    # Metric should have recorded the duration
    assert test_metric._sum.get() > 0


def test_metrics_manager_collect_all():
    """Test collecting all metrics."""
    manager = get_metrics_manager()
    
    # Force collection
    manager._last_collection = 0
    manager.collect_all_metrics()
    
    # Should not raise exception
    assert True


def test_health_status_unhealthy():
    """Test unhealthy status creation."""
    status = HealthStatus("failing-component", False, "Connection failed")
    
    assert status.healthy is False
    assert "failed" in status.message.lower()


def test_multiple_metric_labels():
    """Test metrics with multiple label combinations."""
    # Create multiple label combinations
    api_requests_total.labels(method="GET", endpoint="/api/v1/agents", status="200").inc()
    api_requests_total.labels(method="POST", endpoint="/api/v1/agents", status="201").inc()
    api_requests_total.labels(method="GET", endpoint="/api/v1/tasks", status="200").inc()
    
    # Should not raise exception
    assert True


def test_histogram_observe():
    """Test histogram observation."""
    from shared.metrics import api_request_duration_seconds
    
    api_request_duration_seconds.labels(
        method="GET",
        endpoint="/test"
    ).observe(0.5)
    
    api_request_duration_seconds.labels(
        method="GET",
        endpoint="/test"
    ).observe(1.5)
    
    # Should not raise exception
    assert True


def test_gauge_inc_dec():
    """Test gauge increment and decrement."""
    from shared.metrics import tasks_active
    
    tasks_active.set(0)
    tasks_active.inc()
    assert tasks_active._value.get() == 1
    
    tasks_active.inc(5)
    assert tasks_active._value.get() == 6
    
    tasks_active.dec(2)
    assert tasks_active._value.get() == 4


def test_counter_increment_by_value():
    """Test counter increment by specific value."""
    from shared.metrics import llm_tokens_used_total
    
    initial = llm_tokens_used_total.labels(
        provider="ollama",
        model="llama2",
        type="input"
    )._value.get()
    
    llm_tokens_used_total.labels(
        provider="ollama",
        model="llama2",
        type="input"
    ).inc(100)
    
    new_value = llm_tokens_used_total.labels(
        provider="ollama",
        model="llama2",
        type="input"
    )._value.get()
    
    assert new_value == initial + 100
