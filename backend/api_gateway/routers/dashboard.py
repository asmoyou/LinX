"""Dashboard analytics endpoints.

Provides aggregated, user-scoped metrics for the dashboard page.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Literal
from uuid import UUID

import psutil
from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from pydantic import BaseModel

from access_control.permissions import CurrentUser, get_current_user
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()

_NON_TERMINAL_TASK_STATUSES = {"draft", "planning", "pending", "running", "reviewing"}
_ACTIVE_RUN_STATUSES = {"queued", "planning", "provisioning", "running", "reviewing"}


class DashboardStats(BaseModel):
    active_agents: int
    idle_agents: int
    offline_agents: int
    total_agents: int
    goals_completed: int
    goals_completed_in_window: int
    runs_in_progress: int
    tasks_completed: int
    tasks_completed_24h: int
    tasks_failed: int
    tasks_in_progress: int
    throughput_per_hour: float
    success_rate: float
    compute_load: float
    memory_load: float


class DashboardTaskDistributionPoint(BaseModel):
    date: str
    tasks: int


class DashboardEvent(BaseModel):
    id: str
    type: Literal["success", "error", "info"]
    event_type: str
    message: str
    timestamp: str


class DashboardOverviewResponse(BaseModel):
    stats: DashboardStats
    task_distribution: List[DashboardTaskDistributionPoint]
    task_completion_distribution: List[DashboardTaskDistributionPoint]
    recent_events: List[DashboardEvent]
    generated_at: str


def _normalize_status_key(value: str | None) -> str:
    return str(value or "").strip().lower()


def _classify_event_type(event_type: str) -> Literal["success", "error", "info"]:
    normalized = str(event_type or "").strip().upper()
    if "FAILED" in normalized or "ERROR" in normalized:
        return "error"
    if "COMPLETED" in normalized or "SUCCESS" in normalized:
        return "success"
    return "info"


def _humanize_event_type(event_type: str) -> str:
    normalized = str(event_type or "").strip().replace("_", " ").lower()
    return normalized.capitalize() if normalized else "Event updated"


def _build_event_message(
    event_type: str,
    message: str | None,
    project_title: str | None = None,
    mission_title: str | None = None,
) -> str:
    if message and message.strip():
        return message.strip()

    event_label = _humanize_event_type(event_type)
    resolved_title = project_title or mission_title
    if resolved_title and resolved_title.strip():
        return f"{resolved_title.strip()}: {event_label}"
    return event_label


def _format_utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        utc_value = value.replace(tzinfo=timezone.utc)
    else:
        utc_value = value.astimezone(timezone.utc)
    return utc_value.isoformat().replace("+00:00", "Z")


def _round_metric(value: float) -> float:
    return round(max(float(value), 0.0), 2)


def _safe_system_load() -> tuple[float, float]:
    try:
        cpu_percent = float(psutil.cpu_percent(interval=0.1))
    except Exception:
        logger.warning("Failed to read CPU load for dashboard", exc_info=True)
        cpu_percent = 0.0

    try:
        memory_percent = float(psutil.virtual_memory().percent)
    except Exception:
        logger.warning("Failed to read memory load for dashboard", exc_info=True)
        memory_percent = 0.0

    return _round_metric(cpu_percent), _round_metric(memory_percent)


@router.get("/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    days: int = Query(default=7, ge=3, le=30),
    event_limit: int = Query(default=8, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get user-scoped dashboard metrics and recent activity."""
    from database.connection import get_db_session
    from database.models import Agent
    from database.project_execution_models import Project, ProjectAuditEvent, ProjectRun, ProjectTask
    from sqlalchemy import func

    user_id = UUID(current_user.user_id)
    now_utc = datetime.now(timezone.utc)

    # Window for chart series: [today - (days-1), today]
    start_day = now_utc.date() - timedelta(days=days - 1)
    start_ts = datetime.combine(start_day, time.min, tzinfo=timezone.utc)

    # Window for throughput: last 24h
    throughput_boundary = now_utc - timedelta(hours=24)

    try:
        with get_db_session() as session:
            agent_status_rows = (
                session.query(Agent.status, func.count(Agent.agent_id))
                .filter(Agent.owner_user_id == user_id)
                .group_by(Agent.status)
                .all()
            )
            task_status_rows = (
                session.query(ProjectTask.status, func.count(ProjectTask.project_task_id))
                .filter(ProjectTask.created_by_user_id == user_id)
                .group_by(ProjectTask.status)
                .all()
            )
            goals_completed = (
                session.query(func.count(ProjectRun.run_id))
                .filter(
                    ProjectRun.requested_by_user_id == user_id,
                    ProjectRun.status == "completed",
                )
                .scalar()
                or 0
            )
            goals_completed_in_window = (
                session.query(func.count(ProjectRun.run_id))
                .filter(
                    ProjectRun.requested_by_user_id == user_id,
                    ProjectRun.status == "completed",
                    ProjectRun.completed_at.isnot(None),
                    ProjectRun.completed_at >= start_ts,
                )
                .scalar()
                or 0
            )
            runs_in_progress = (
                session.query(func.count(ProjectRun.run_id))
                .filter(
                    ProjectRun.requested_by_user_id == user_id,
                    ProjectRun.status.in_(_ACTIVE_RUN_STATUSES),
                )
                .scalar()
                or 0
            )
            tasks_completed_24h = (
                session.query(func.count(ProjectTask.project_task_id))
                .filter(
                    ProjectTask.created_by_user_id == user_id,
                    ProjectTask.status == "completed",
                    ProjectTask.updated_at >= throughput_boundary,
                )
                .scalar()
                or 0
            )
            task_distribution_rows = (
                session.query(func.date(ProjectTask.created_at), func.count(ProjectTask.project_task_id))
                .filter(
                    ProjectTask.created_by_user_id == user_id,
                    ProjectTask.created_at >= start_ts,
                )
                .group_by(func.date(ProjectTask.created_at))
                .all()
            )
            task_completion_distribution_rows = (
                session.query(func.date(ProjectTask.updated_at), func.count(ProjectTask.project_task_id))
                .filter(
                    ProjectTask.created_by_user_id == user_id,
                    ProjectTask.status == "completed",
                    ProjectTask.updated_at >= start_ts,
                )
                .group_by(func.date(ProjectTask.updated_at))
                .all()
            )
            recent_event_rows = (
                session.query(
                    ProjectAuditEvent.audit_event_id,
                    ProjectAuditEvent.action,
                    func.cast(None, Project.name.type),
                    ProjectAuditEvent.created_at,
                    Project.name,
                )
                .outerjoin(Project, Project.project_id == ProjectAuditEvent.project_id)
                .filter(ProjectAuditEvent.actor_user_id == user_id)
                .order_by(ProjectAuditEvent.created_at.desc())
                .limit(event_limit)
                .all()
            )
    except Exception as exc:
        logger.exception("Failed to load dashboard overview for user %s", current_user.user_id)
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Dashboard data is temporarily unavailable",
        ) from exc

    agent_counts: Dict[str, int] = {}
    for status, count in agent_status_rows:
        key = _normalize_status_key(status)
        agent_counts[key] = agent_counts.get(key, 0) + int(count or 0)

    total_agents = sum(agent_counts.values())
    active_agents = agent_counts.get("active", 0)
    idle_agents = agent_counts.get("idle", 0)
    offline_agents = max(total_agents - active_agents - idle_agents, 0)

    task_counts: Dict[str, int] = {}
    for status, count in task_status_rows:
        key = _normalize_status_key(status)
        task_counts[key] = task_counts.get(key, 0) + int(count or 0)

    tasks_completed = task_counts.get("completed", 0)
    tasks_failed = task_counts.get("failed", 0)
    tasks_in_progress = sum(task_counts.get(status, 0) for status in _NON_TERMINAL_TASK_STATUSES)

    success_denominator = tasks_completed + tasks_failed
    success_rate = (
        _round_metric((tasks_completed / success_denominator) * 100.0)
        if success_denominator > 0
        else 0.0
    )
    throughput_per_hour = _round_metric(float(tasks_completed_24h) / 24.0)
    compute_load, memory_load = _safe_system_load()

    task_distribution_map: Dict[date, int] = {}
    for day_value, count in task_distribution_rows:
        day_key = day_value.date() if isinstance(day_value, datetime) else day_value
        if isinstance(day_key, date):
            task_distribution_map[day_key] = int(count or 0)

    task_completion_distribution_map: Dict[date, int] = {}
    for day_value, count in task_completion_distribution_rows:
        day_key = day_value.date() if isinstance(day_value, datetime) else day_value
        if isinstance(day_key, date):
            task_completion_distribution_map[day_key] = int(count or 0)

    task_distribution = []
    task_completion_distribution = []
    for offset in range(days):
        point_day = start_day + timedelta(days=offset)
        task_distribution.append(
            DashboardTaskDistributionPoint(
                date=point_day.isoformat(),
                tasks=task_distribution_map.get(point_day, 0),
            )
        )
        task_completion_distribution.append(
            DashboardTaskDistributionPoint(
                date=point_day.isoformat(),
                tasks=task_completion_distribution_map.get(point_day, 0),
            )
        )

    recent_events = [
        DashboardEvent(
            id=str(event_id),
            type=_classify_event_type(str(event_type or "")),
            event_type=str(event_type or ""),
            message=_build_event_message(
                event_type=str(event_type or ""),
                message=message,
                project_title=project_title,
            ),
            timestamp=_format_utc_iso(created_at or now_utc),
        )
        for event_id, event_type, message, created_at, project_title in recent_event_rows
    ]

    return DashboardOverviewResponse(
        stats=DashboardStats(
            active_agents=active_agents,
            idle_agents=idle_agents,
            offline_agents=offline_agents,
            total_agents=total_agents,
            goals_completed=int(goals_completed),
            goals_completed_in_window=int(goals_completed_in_window),
            runs_in_progress=int(runs_in_progress),
            tasks_completed=tasks_completed,
            tasks_completed_24h=int(tasks_completed_24h),
            tasks_failed=tasks_failed,
            tasks_in_progress=tasks_in_progress,
            throughput_per_hour=throughput_per_hour,
            success_rate=success_rate,
            compute_load=compute_load,
            memory_load=memory_load,
        ),
        task_distribution=task_distribution,
        task_completion_distribution=task_completion_distribution,
        recent_events=recent_events,
        generated_at=_format_utc_iso(now_utc),
    )
