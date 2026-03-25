"""Frontend telemetry ingestion endpoints."""

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from database.connection import get_db_session
from database.models import User
from shared.logging import get_logger
from shared.metrics import (
    frontend_motion_avg_fps,
    frontend_motion_downgrades_total,
    frontend_motion_long_tasks_total,
    frontend_motion_p95_frame_ms,
    frontend_motion_reports_total,
)

router = APIRouter()
logger = get_logger(__name__)


class FrontendMotionSummary(BaseModel):
    route_group: str = Field(..., min_length=1, max_length=120)
    effective_tier: str = Field(..., pattern="^(auto|full|reduced|off)$")
    motion_preference: str = Field(..., pattern="^(auto|full|reduced|off)$")
    os_reduced_motion: bool
    save_data: bool
    device_class: str = Field(..., pattern="^(low|standard)$")
    avg_fps: float = Field(..., ge=0.0, le=240.0)
    p95_frame_ms: float = Field(..., ge=0.0, le=1000.0)
    long_task_count: int = Field(..., ge=0, le=10000)
    downgrade_count: int = Field(..., ge=0, le=10000)
    sampled_at: str = Field(..., min_length=1, max_length=64)
    app_version: str = Field(default="unknown", min_length=1, max_length=64)


@router.post("/frontend-motion-summary", status_code=status.HTTP_202_ACCEPTED)
async def ingest_frontend_motion_summary(
    request: FrontendMotionSummary,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Record one aggregated frontend animation telemetry sample."""
    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            return Response(status_code=status.HTTP_202_ACCEPTED)

        attrs = user.attributes if isinstance(user.attributes, dict) else {}
        privacy = attrs.get("privacy", {}) if isinstance(attrs.get("privacy", {}), dict) else {}
        if not privacy.get("allow_telemetry", True):
            logger.info(
                "Frontend motion telemetry suppressed by privacy settings",
                extra={"user_id": current_user.user_id, "route_group": request.route_group},
            )
            return Response(status_code=status.HTTP_202_ACCEPTED)

    frontend_motion_reports_total.labels(
        route_group=request.route_group,
        effective_tier=request.effective_tier,
        device_class=request.device_class,
    ).inc()
    frontend_motion_avg_fps.labels(
        route_group=request.route_group,
        effective_tier=request.effective_tier,
    ).observe(request.avg_fps)
    frontend_motion_p95_frame_ms.labels(
        route_group=request.route_group,
        effective_tier=request.effective_tier,
    ).observe(request.p95_frame_ms)
    frontend_motion_long_tasks_total.labels(
        route_group=request.route_group,
        effective_tier=request.effective_tier,
    ).inc(request.long_task_count)
    frontend_motion_downgrades_total.labels(
        route_group=request.route_group,
        effective_tier=request.effective_tier,
    ).inc(request.downgrade_count)

    logger.info(
        "Frontend motion telemetry recorded",
        extra={
            "user_id": current_user.user_id,
            "route_group": request.route_group,
            "effective_tier": request.effective_tier,
            "motion_preference": request.motion_preference,
            "device_class": request.device_class,
            "os_reduced_motion": request.os_reduced_motion,
            "save_data": request.save_data,
            "avg_fps": request.avg_fps,
            "p95_frame_ms": request.p95_frame_ms,
            "long_task_count": request.long_task_count,
            "downgrade_count": request.downgrade_count,
            "sampled_at": request.sampled_at,
            "app_version": request.app_version,
            "session_id": current_user.session_id,
        },
    )

    return Response(status_code=status.HTTP_202_ACCEPTED)
