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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

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

memory_blocked_writes_total = Counter(
    "memory_blocked_writes_total",
    "Total memory writes blocked by quality/policy gates",
    ["memory_type", "reason"],
    registry=registry,
)

memory_planner_actions_total = Counter(
    "memory_planner_actions_total",
    "Total memory action-planner decisions",
    ["memory_type", "action", "source"],
    registry=registry,
)

memory_retrieval_source_quality_total = Counter(
    "memory_retrieval_source_quality_total",
    "Memory retrieval source quality outcomes",
    ["memory_type", "source", "quality"],
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


@dataclass
class DependencyCheckDefinition:
    """Static definition for a dependency health check."""

    dependency_id: str
    name: str
    required: bool
    enabled: bool
    impact: str
    source: str
    disabled_message: str
    checker: Callable[[int], Tuple[bool, str, Optional[float]]]


@dataclass
class DependencyHealthStatus:
    """Runtime status for one dependency."""

    dependency_id: str
    name: str
    required: bool
    enabled: bool
    healthy: bool
    status: str
    message: str
    impact: str
    source: str
    latency_ms: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert dependency status to dictionary."""
        return {
            "id": self.dependency_id,
            "name": self.name,
            "required": self.required,
            "enabled": self.enabled,
            "healthy": self.healthy,
            "status": self.status,
            "message": self.message,
            "impact": self.impact,
            "source": self.source,
            "latency_ms": self.latency_ms,
        }


def _elapsed_ms(start_time: float) -> float:
    """Get elapsed milliseconds since start time."""
    return round((time.perf_counter() - start_time) * 1000, 2)


def _truncate_error(error: Exception, max_length: int = 220) -> str:
    """Render a compact one-line error message."""
    message = " ".join(str(error).split()).strip() or error.__class__.__name__
    if len(message) <= max_length:
        return message
    return f"{message[:max_length]}..."


def _check_postgres(timeout_seconds: int) -> Tuple[bool, str, Optional[float]]:
    """Check PostgreSQL availability."""
    start_time = time.perf_counter()
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.pool import NullPool
        from shared.config import get_config

        config = get_config()
        db_config = config.get_section("database.postgres")
        database_url = (
            f"postgresql://{db_config['username']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        )
        engine = create_engine(
            database_url,
            poolclass=NullPool,
            connect_args={
                "connect_timeout": max(1, timeout_seconds),
                "options": "-c timezone=UTC",
            },
        )

        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        finally:
            engine.dispose()

        return True, "PostgreSQL connection is healthy", _elapsed_ms(start_time)
    except Exception as error:
        return (
            False,
            f"PostgreSQL check error: {_truncate_error(error)}",
            _elapsed_ms(start_time),
        )


def _check_redis(timeout_seconds: int) -> Tuple[bool, str, Optional[float]]:
    """Check Redis availability."""
    start_time = time.perf_counter()
    try:
        import redis
        from shared.config import get_config

        config = get_config()
        redis_config = config.get_section("database.redis")
        client = redis.Redis(
            host=redis_config["host"],
            port=redis_config["port"],
            password=redis_config.get("password") or None,
            db=redis_config.get("db", 0),
            socket_timeout=max(1, timeout_seconds),
            socket_connect_timeout=max(1, timeout_seconds),
            decode_responses=True,
        )

        try:
            client.ping()
        finally:
            client.close()

        return True, "Redis connection is healthy", _elapsed_ms(start_time)
    except Exception as error:
        details = _truncate_error(error)
        details_upper = details.upper()
        if "NOAUTH" in details_upper or "WRONGPASS" in details_upper:
            return (
                False,
                "Redis authentication failed. Check database.redis.password against the "
                "Redis server requirepass setting.",
                _elapsed_ms(start_time),
            )
        return (
            False,
            f"Redis check error: {details}",
            _elapsed_ms(start_time),
        )


def _check_minio(timeout_seconds: int) -> Tuple[bool, str, Optional[float]]:
    """Check MinIO availability."""
    start_time = time.perf_counter()
    try:
        import requests
        from shared.config import get_config

        config = get_config()
        minio_config = config.get_section("storage.minio")
        protocol = "https" if minio_config.get("secure", False) else "http"
        endpoint = str(minio_config.get("endpoint", "")).strip()
        if not endpoint:
            return False, "MinIO endpoint is empty", _elapsed_ms(start_time)

        health_url = f"{protocol}://{endpoint}/minio/health/live"
        response = requests.get(health_url, timeout=max(1, timeout_seconds))

        if 200 <= response.status_code < 300:
            return True, "MinIO connection is healthy", _elapsed_ms(start_time)

        return (
            False,
            f"MinIO health endpoint returned HTTP {response.status_code}",
            _elapsed_ms(start_time),
        )
    except Exception as error:
        return (
            False,
            f"MinIO check error: {_truncate_error(error)}",
            _elapsed_ms(start_time),
        )


def _check_milvus(timeout_seconds: int) -> Tuple[bool, str, Optional[float]]:
    """Check Milvus availability."""
    start_time = time.perf_counter()
    alias = f"healthcheck_{uuid4().hex[:8]}"
    try:
        from pymilvus import connections, utility
        from shared.config import get_config

        config = get_config()
        milvus_config = config.get_section("database.milvus")

        connect_args: Dict[str, Any] = {
            "alias": alias,
            "host": milvus_config.get("host", "localhost"),
            "port": str(milvus_config.get("port", 19530)),
            "timeout": max(1, timeout_seconds),
        }
        user = milvus_config.get("user", "")
        password = milvus_config.get("password", "")
        if user and password:
            connect_args["user"] = user
            connect_args["password"] = password

        connections.connect(**connect_args)
        utility.list_collections(using=alias)

        return True, "Milvus connection is healthy", _elapsed_ms(start_time)
    except Exception as error:
        return (
            False,
            f"Milvus check error: {_truncate_error(error)}",
            _elapsed_ms(start_time),
        )
    finally:
        try:
            from pymilvus import connections

            connections.disconnect(alias=alias)
        except Exception:
            pass


def _check_funasr_service(
    timeout_seconds: int,
    service_url: str,
    service_api_key: str,
) -> Tuple[bool, str, Optional[float]]:
    """Check external FunASR service availability."""
    start_time = time.perf_counter()
    endpoint = f"{service_url.rstrip('/')}/health"
    headers: Dict[str, str] = {}
    if service_api_key:
        headers["Authorization"] = f"Bearer {service_api_key}"

    try:
        import requests

        response = requests.get(
            endpoint,
            headers=headers,
            timeout=max(1, timeout_seconds),
        )
        if 200 <= response.status_code < 300:
            return (
                True,
                f"FunASR service is healthy ({response.status_code})",
                _elapsed_ms(start_time),
            )

        body = response.text.replace("\n", " ").strip()[:120]
        details = f": {body}" if body else ""
        return (
            False,
            f"FunASR service returned HTTP {response.status_code}{details}",
            _elapsed_ms(start_time),
        )
    except Exception as error:
        return (
            False,
            f"FunASR check error: {_truncate_error(error)}",
            _elapsed_ms(start_time),
        )


def _build_dependency_definitions() -> List[DependencyCheckDefinition]:
    """Build dependency definitions from compose-driven defaults and runtime config."""
    from shared.config import get_config

    config = get_config()
    health_config = config.get("monitoring.health", default={}) or {}
    transcription_config = (
        config.get(
            "knowledge_base.processing.transcription",
            default={},
        )
        or {}
    )

    transcription_enabled = bool(transcription_config.get("enabled", True))
    transcription_engine = str(transcription_config.get("engine", "funasr")).strip().lower()
    check_funasr_enabled = bool(health_config.get("check_funasr", True))

    funasr_enabled = (
        check_funasr_enabled and transcription_enabled and transcription_engine == "funasr"
    )
    if not check_funasr_enabled:
        funasr_disabled_message = "Health check disabled by monitoring.health.check_funasr"
    elif not transcription_enabled:
        funasr_disabled_message = (
            "Transcription is disabled in knowledge_base.processing.transcription"
        )
    elif transcription_engine != "funasr":
        funasr_disabled_message = (
            f"Transcription engine is '{transcription_engine}', FunASR health check skipped"
        )
    else:
        funasr_disabled_message = "FunASR health check enabled"

    funasr_service_url = str(transcription_config.get("funasr_service_url", "")).strip()
    funasr_service_api_key = str(transcription_config.get("funasr_service_api_key", "")).strip()

    return [
        DependencyCheckDefinition(
            dependency_id="postgres",
            name="PostgreSQL",
            required=True,
            enabled=bool(health_config.get("check_database", True)),
            impact="Core APIs, authentication, and metadata operations are unavailable",
            source="docker-compose: api-gateway.depends_on",
            disabled_message="Health check disabled by monitoring.health.check_database",
            checker=_check_postgres,
        ),
        DependencyCheckDefinition(
            dependency_id="redis",
            name="Redis",
            required=True,
            enabled=bool(health_config.get("check_redis", True)),
            impact="Message bus, queues, and async workflow coordination are unavailable",
            source="docker-compose: api-gateway.depends_on",
            disabled_message="Health check disabled by monitoring.health.check_redis",
            checker=_check_redis,
        ),
        DependencyCheckDefinition(
            dependency_id="minio",
            name="MinIO",
            required=True,
            enabled=bool(health_config.get("check_minio", True)),
            impact="File upload/download and artifact storage are unavailable",
            source="docker-compose: api-gateway.depends_on",
            disabled_message="Health check disabled by monitoring.health.check_minio",
            checker=_check_minio,
        ),
        DependencyCheckDefinition(
            dependency_id="milvus",
            name="Milvus",
            required=True,
            enabled=bool(health_config.get("check_milvus", True)),
            impact="Vector memory and semantic retrieval features are unavailable",
            source="docker-compose: api-gateway.depends_on",
            disabled_message="Health check disabled by monitoring.health.check_milvus",
            checker=_check_milvus,
        ),
        DependencyCheckDefinition(
            dependency_id="funasr",
            name="FunASR",
            required=False,
            enabled=funasr_enabled,
            impact="Audio/video transcription features are unavailable",
            source="docker-compose: funasr-service (optional)",
            disabled_message=funasr_disabled_message,
            checker=lambda timeout_seconds: _check_funasr_service(
                timeout_seconds=timeout_seconds,
                service_url=funasr_service_url,
                service_api_key=funasr_service_api_key,
            ),
        ),
    ]


def _run_dependency_check(
    definition: DependencyCheckDefinition,
    timeout_seconds: int,
) -> DependencyHealthStatus:
    """Execute one dependency check and normalize the result."""
    if not definition.enabled:
        return DependencyHealthStatus(
            dependency_id=definition.dependency_id,
            name=definition.name,
            required=definition.required,
            enabled=False,
            healthy=True,
            status="disabled",
            message=definition.disabled_message,
            impact=definition.impact,
            source=definition.source,
            latency_ms=None,
        )

    healthy, message, latency_ms = definition.checker(timeout_seconds)
    return DependencyHealthStatus(
        dependency_id=definition.dependency_id,
        name=definition.name,
        required=definition.required,
        enabled=True,
        healthy=healthy,
        status="up" if healthy else "down",
        message=message,
        impact=definition.impact,
        source=definition.source,
        latency_ms=latency_ms,
    )


def _collect_dependency_health(timeout_seconds: int) -> List[DependencyHealthStatus]:
    """Collect all dependency checks concurrently."""
    definitions = _build_dependency_definitions()
    results: Dict[str, DependencyHealthStatus] = {}

    runnable = [definition for definition in definitions if definition.enabled]
    for definition in definitions:
        if not definition.enabled:
            results[definition.dependency_id] = _run_dependency_check(definition, timeout_seconds)

    if runnable:
        max_workers = min(8, len(runnable))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_run_dependency_check, definition, timeout_seconds): definition
                for definition in runnable
            }

            for future in as_completed(future_map):
                definition = future_map[future]
                try:
                    results[definition.dependency_id] = future.result()
                except Exception as error:
                    results[definition.dependency_id] = DependencyHealthStatus(
                        dependency_id=definition.dependency_id,
                        name=definition.name,
                        required=definition.required,
                        enabled=definition.enabled,
                        healthy=False,
                        status="down",
                        message=f"Dependency check crashed: {_truncate_error(error)}",
                        impact=definition.impact,
                        source=definition.source,
                        latency_ms=None,
                    )

    return [results[definition.dependency_id] for definition in definitions]


def get_health_status() -> Dict[str, Any]:
    """Get overall system health status.

    Returns:
        Dictionary with health status
    """
    checks: List[HealthStatus] = []
    system_healthy = False
    dependencies: List[DependencyHealthStatus] = []

    # System health
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_percent = psutil.virtual_memory().percent

        system_healthy = cpu_percent < 95 and memory_percent < 95
        checks.append(
            HealthStatus(
                "system",
                system_healthy,
                f"CPU: {cpu_percent}%, Memory: {memory_percent}%",
            )
        )
    except Exception as e:
        checks.append(HealthStatus("system", False, str(e)))
        system_healthy = False

    # Dependency health
    timeout_seconds = 5
    try:
        from shared.config import get_config

        config = get_config()
        timeout_seconds = int(config.get("monitoring.health.timeout_seconds", default=5))
    except Exception:
        timeout_seconds = 5

    try:
        dependencies = _collect_dependency_health(timeout_seconds=max(1, timeout_seconds))
        checks.extend(
            [
                HealthStatus(
                    dependency.name.lower(),
                    dependency.healthy,
                    dependency.message,
                )
                for dependency in dependencies
                if dependency.enabled
            ]
        )
    except Exception as error:
        checks.append(
            HealthStatus(
                "dependencies",
                False,
                f"Failed to collect dependency health: {_truncate_error(error)}",
            )
        )

    required_dependencies = [
        dependency for dependency in dependencies if dependency.required and dependency.enabled
    ]
    optional_dependencies = [
        dependency for dependency in dependencies if not dependency.required and dependency.enabled
    ]

    required_unhealthy = [
        dependency for dependency in required_dependencies if not dependency.healthy
    ]
    optional_unhealthy = [
        dependency for dependency in optional_dependencies if not dependency.healthy
    ]
    required_blockers = (not system_healthy) or bool(required_unhealthy)
    overall_status = (
        "critical" if required_blockers else "degraded" if optional_unhealthy else "optimal"
    )

    # Keep compatibility: overall status remains healthy/unhealthy.
    status = "healthy" if not required_blockers else "unhealthy"

    return {
        "status": status,
        "overall": overall_status,
        "checks": [check.to_dict() for check in checks],
        "dependencies": [dependency.to_dict() for dependency in dependencies],
        "summary": {
            "required_total": len(required_dependencies),
            "required_healthy": len(required_dependencies) - len(required_unhealthy),
            "required_unhealthy": len(required_unhealthy),
            "optional_total": len(optional_dependencies),
            "optional_healthy": len(optional_dependencies) - len(optional_unhealthy),
            "optional_unhealthy": len(optional_unhealthy),
            "disabled_checks": len(
                [dependency for dependency in dependencies if not dependency.enabled]
            ),
        },
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
