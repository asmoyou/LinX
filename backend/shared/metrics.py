"""Prometheus Metrics Collection System.

Implements comprehensive metrics collection for monitoring system health,
application performance, and business KPIs.

References:
- Requirements 11: Monitoring and Observability
- Design Section 11: Monitoring and Observability Design
- Task 5.4: Monitoring and Metrics
"""

import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional

import psutil
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Summary,
    generate_latest,
)

logger = logging.getLogger(__name__)


# Create custom registry for better control
registry = CollectorRegistry()

# ============================================================================
# System Metrics
# ============================================================================

# CPU Metrics
cpu_usage_percent = Gauge("system_cpu_usage_percent", "CPU usage percentage", registry=registry)

cpu_count = Gauge("system_cpu_count", "Number of CPU cores", registry=registry)

# Memory Metrics
memory_usage_bytes = Gauge("system_memory_usage_bytes", "Memory usage in bytes", registry=registry)

memory_total_bytes = Gauge("system_memory_total_bytes", "Total memory in bytes", registry=registry)

memory_usage_percent = Gauge(
    "system_memory_usage_percent", "Memory usage percentage", registry=registry
)

# Disk Metrics
disk_usage_bytes = Gauge(
    "system_disk_usage_bytes", "Disk usage in bytes", ["path"], registry=registry
)

disk_total_bytes = Gauge(
    "system_disk_total_bytes", "Total disk space in bytes", ["path"], registry=registry
)

disk_usage_percent = Gauge(
    "system_disk_usage_percent", "Disk usage percentage", ["path"], registry=registry
)

# Network Metrics
network_bytes_sent = Counter(
    "system_network_bytes_sent_total", "Total bytes sent over network", registry=registry
)

network_bytes_recv = Counter(
    "system_network_bytes_recv_total", "Total bytes received over network", registry=registry
)

# ============================================================================
# Application Metrics - API
# ============================================================================

# API Request Metrics
api_requests_total = Counter(
    "api_requests_total", "Total API requests", ["method", "endpoint", "status"], registry=registry
)

api_request_duration_seconds = Histogram(
    "api_request_duration_seconds",
    "API request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

api_request_size_bytes = Summary(
    "api_request_size_bytes", "API request size in bytes", ["method", "endpoint"], registry=registry
)

api_response_size_bytes = Summary(
    "api_response_size_bytes",
    "API response size in bytes",
    ["method", "endpoint"],
    registry=registry,
)

# ============================================================================
# Application Metrics - Tasks
# ============================================================================

# Task Metrics
tasks_created_total = Counter(
    "tasks_created_total", "Total tasks created", ["user_id"], registry=registry
)

tasks_completed_total = Counter(
    "tasks_completed_total", "Total tasks completed", ["user_id", "status"], registry=registry
)

tasks_failed_total = Counter(
    "tasks_failed_total", "Total tasks failed", ["user_id", "error_type"], registry=registry
)

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Task execution duration in seconds",
    ["task_type"],
    buckets=(1, 5, 10, 30, 60, 300, 600, 1800, 3600),
    registry=registry,
)

tasks_active = Gauge("tasks_active", "Number of currently active tasks", registry=registry)

tasks_queued = Gauge("tasks_queued", "Number of tasks in queue", registry=registry)

# ============================================================================
# Application Metrics - Agents
# ============================================================================

# Agent Metrics
agents_total = Gauge("agents_total", "Total number of agents", ["status"], registry=registry)

agents_created_total = Counter(
    "agents_created_total", "Total agents created", ["user_id", "template"], registry=registry
)

agents_terminated_total = Counter(
    "agents_terminated_total", "Total agents terminated", ["user_id", "reason"], registry=registry
)

agent_execution_duration_seconds = Histogram(
    "agent_execution_duration_seconds",
    "Agent task execution duration in seconds",
    ["agent_id", "agent_type"],
    buckets=(0.1, 0.5, 1, 5, 10, 30, 60, 300),
    registry=registry,
)

agent_success_rate = Gauge(
    "agent_success_rate", "Agent task success rate", ["agent_id"], registry=registry
)

# ============================================================================
# Application Metrics - LLM
# ============================================================================

# LLM Metrics
llm_requests_total = Counter(
    "llm_requests_total", "Total LLM requests", ["provider", "model"], registry=registry
)

llm_request_duration_seconds = Histogram(
    "llm_request_duration_seconds",
    "LLM request duration in seconds",
    ["provider", "model"],
    buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
    registry=registry,
)

llm_tokens_used_total = Counter(
    "llm_tokens_used_total", "Total tokens used", ["provider", "model", "type"], registry=registry
)

llm_errors_total = Counter(
    "llm_errors_total", "Total LLM errors", ["provider", "model", "error_type"], registry=registry
)

# ============================================================================
# Application Metrics - Memory System
# ============================================================================

# Memory System Metrics
memory_queries_total = Counter(
    "memory_queries_total",
    "Total memory system queries",
    ["memory_type", "operation"],
    registry=registry,
)

memory_query_duration_seconds = Histogram(
    "memory_query_duration_seconds",
    "Memory query duration in seconds",
    ["memory_type", "operation"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2, 5),
    registry=registry,
)

memory_items_stored_total = Counter(
    "memory_items_stored_total", "Total memory items stored", ["memory_type"], registry=registry
)

memory_items_retrieved_total = Counter(
    "memory_items_retrieved_total",
    "Total memory items retrieved",
    ["memory_type"],
    registry=registry,
)

# ============================================================================
# Application Metrics - Knowledge Base
# ============================================================================

# Knowledge Base Metrics
documents_uploaded_total = Counter(
    "documents_uploaded_total",
    "Total documents uploaded",
    ["user_id", "file_type"],
    registry=registry,
)

documents_processed_total = Counter(
    "documents_processed_total",
    "Total documents processed",
    ["file_type", "status"],
    registry=registry,
)

document_processing_duration_seconds = Histogram(
    "document_processing_duration_seconds",
    "Document processing duration in seconds",
    ["file_type"],
    buckets=(1, 5, 10, 30, 60, 300, 600),
    registry=registry,
)

knowledge_search_queries_total = Counter(
    "knowledge_search_queries_total",
    "Total knowledge base search queries",
    ["user_id"],
    registry=registry,
)

knowledge_search_duration_seconds = Histogram(
    "knowledge_search_duration_seconds",
    "Knowledge search duration in seconds",
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2),
    registry=registry,
)

# ============================================================================
# Application Metrics - Database
# ============================================================================

# Database Metrics
db_connections_active = Gauge(
    "db_connections_active", "Number of active database connections", registry=registry
)

db_connections_idle = Gauge(
    "db_connections_idle", "Number of idle database connections", registry=registry
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5),
    registry=registry,
)

# ============================================================================
# Business Metrics
# ============================================================================

# User Metrics
users_active = Gauge("users_active", "Number of active users", registry=registry)

users_registered_total = Counter(
    "users_registered_total", "Total users registered", registry=registry
)

# Goal Metrics
goals_submitted_total = Counter(
    "goals_submitted_total", "Total goals submitted", ["user_id"], registry=registry
)

goals_completed_total = Counter(
    "goals_completed_total", "Total goals completed", ["user_id"], registry=registry
)

goal_completion_rate = Gauge(
    "goal_completion_rate", "Goal completion rate percentage", registry=registry
)

# Resource Quota Metrics
quota_usage_percent = Gauge(
    "quota_usage_percent",
    "Resource quota usage percentage",
    ["user_id", "resource_type"],
    registry=registry,
)

quota_exceeded_total = Counter(
    "quota_exceeded_total",
    "Total quota exceeded events",
    ["user_id", "resource_type"],
    registry=registry,
)


# ============================================================================
# Metrics Collection Functions
# ============================================================================


def collect_system_metrics() -> None:
    """Collect system-level metrics (CPU, memory, disk, network)."""
    try:
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_usage_percent.set(cpu_percent)
        cpu_count.set(psutil.cpu_count())

        # Memory metrics
        memory = psutil.virtual_memory()
        memory_usage_bytes.set(memory.used)
        memory_total_bytes.set(memory.total)
        memory_usage_percent.set(memory.percent)

        # Disk metrics
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_usage_bytes.labels(path=partition.mountpoint).set(usage.used)
                disk_total_bytes.labels(path=partition.mountpoint).set(usage.total)
                disk_usage_percent.labels(path=partition.mountpoint).set(usage.percent)
            except PermissionError:
                # Skip partitions we can't access
                pass

        # Network metrics
        net_io = psutil.net_io_counters()
        network_bytes_sent.inc(net_io.bytes_sent)
        network_bytes_recv.inc(net_io.bytes_recv)

        logger.debug("System metrics collected successfully")

    except Exception as e:
        logger.error(f"Failed to collect system metrics: {str(e)}")


def get_metrics() -> bytes:
    """Get all metrics in Prometheus format.

    Returns:
        Metrics in Prometheus text format
    """
    # Collect system metrics before generating output
    collect_system_metrics()

    return generate_latest(registry)


def get_metrics_content_type() -> str:
    """Get the content type for Prometheus metrics.

    Returns:
        Content type string
    """
    return CONTENT_TYPE_LATEST


# ============================================================================
# Decorator for Timing Functions
# ============================================================================


def track_time(metric: Histogram):
    """Decorator to track execution time of a function.

    Args:
        metric: Histogram metric to record duration

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                metric.observe(duration)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                metric.observe(duration)

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# ============================================================================
# Health Check
# ============================================================================


class HealthStatus:
    """Health status for a component."""

    def __init__(self, name: str, healthy: bool, message: str = ""):
        """Initialize health status.

        Args:
            name: Component name
            healthy: Whether component is healthy
            message: Optional status message
        """
        self.name = name
        self.healthy = healthy
        self.message = message

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "name": self.name,
            "healthy": self.healthy,
            "message": self.message,
        }


def get_health_status() -> Dict[str, Any]:
    """Get overall system health status.

    Returns:
        Dictionary with health status
    """
    checks = []

    # System health
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_percent = psutil.virtual_memory().percent

        checks.append(
            HealthStatus(
                "system",
                cpu_percent < 95 and memory_percent < 95,
                f"CPU: {cpu_percent}%, Memory: {memory_percent}%",
            )
        )
    except Exception as e:
        checks.append(HealthStatus("system", False, str(e)))

    # Overall status
    all_healthy = all(check.healthy for check in checks)

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": [check.to_dict() for check in checks],
        "timestamp": time.time(),
    }


# ============================================================================
# Metrics Manager
# ============================================================================


class MetricsManager:
    """Centralized metrics management."""

    def __init__(self):
        """Initialize metrics manager."""
        self._last_collection = 0
        self._collection_interval = 15  # seconds

        logger.info("MetricsManager initialized")

    def should_collect(self) -> bool:
        """Check if it's time to collect metrics.

        Returns:
            True if should collect
        """
        now = time.time()
        if now - self._last_collection >= self._collection_interval:
            self._last_collection = now
            return True
        return False

    def collect_all_metrics(self) -> None:
        """Collect all metrics."""
        if self.should_collect():
            collect_system_metrics()


# Global metrics manager instance
_metrics_manager: Optional[MetricsManager] = None


def get_metrics_manager() -> MetricsManager:
    """Get global metrics manager instance.

    Returns:
        MetricsManager instance
    """
    global _metrics_manager

    if _metrics_manager is None:
        _metrics_manager = MetricsManager()

    return _metrics_manager
