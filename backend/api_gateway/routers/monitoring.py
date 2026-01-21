"""Monitoring and Health Check Endpoints.

Provides endpoints for Prometheus metrics collection and health checks.

References:
- Requirements 11: Monitoring and Observability
- Design Section 11: Monitoring and Observability Design
- Task 5.4: Monitoring and Metrics
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Response

from shared.metrics import (
    get_health_status,
    get_metrics,
    get_metrics_content_type,
    get_metrics_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["monitoring"])


@router.get("/metrics")
async def metrics_endpoint() -> Response:
    """Prometheus metrics endpoint.

    Returns:
        Prometheus metrics in text format
    """
    # Collect latest metrics
    metrics_manager = get_metrics_manager()
    metrics_manager.collect_all_metrics()

    # Return metrics in Prometheus format
    metrics_data = get_metrics()

    return Response(
        content=metrics_data,
        media_type=get_metrics_content_type(),
    )


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint.

    Returns:
        Health status of the system
    """
    return get_health_status()


@router.get("/health/live")
async def liveness_probe() -> Dict[str, str]:
    """Kubernetes liveness probe endpoint.

    Returns:
        Simple alive status
    """
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_probe() -> Dict[str, Any]:
    """Kubernetes readiness probe endpoint.

    Returns:
        Readiness status with component checks
    """
    health = get_health_status()

    if health["status"] == "healthy":
        return {"status": "ready", "checks": health["checks"]}
    else:
        return {"status": "not_ready", "checks": health["checks"]}
