"""Business logic for agent schedules and scheduled conversation runs."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from access_control.agent_access import (
    build_agent_access_context_for_user_id,
    can_execute_agent,
)
from agent_framework.conversation_execution import (
    ConversationExecutionPrincipal,
    build_conversation_execution_principal,
)
from agent_framework.persistent_conversations import build_default_conversation_title
from agent_scheduling.cron_utils import (
    SchedulePreview,
    ScheduleValidationError,
    compute_next_run_at,
    normalize_cron_expression,
    parse_run_at,
    preview_schedule,
    resolve_timezone_name,
)
from database.connection import get_db_session
from database.models import (
    Agent,
    AgentConversation,
    AgentSchedule,
    AgentScheduleRun,
    ExternalConversationLink,
    User,
)
from mission_system.notification_repository import create_user_notification
from shared.config import get_config
from shared.platform_settings import PLATFORM_BOOTSTRAP_SETTINGS_KEY, get_platform_setting

logger = logging.getLogger(__name__)

TERMINAL_ONCE_STATUSES = {"completed", "failed"}
_TIME_SENSITIVE_TASK_PATTERN = re.compile(
    r"(最新|当前|今日|今天|实时|刚刚|现价|行情|金价|股价|汇率|天气|新闻|热搜|latest|current|today|now|real[ -]?time|price|prices|quote|quotes|news|weather)",
    re.IGNORECASE,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScheduleError(RuntimeError):
    """Base schedule domain error."""


class ScheduleAccessError(ScheduleError):
    """Raised when a user cannot access a schedule or agent."""


class ScheduleNotFoundError(ScheduleError):
    """Raised when a schedule or related object does not exist."""


class InvalidScheduleBindingError(ScheduleError):
    """Raised when a schedule cannot execute because its bound resources are unavailable."""


@dataclass(frozen=True)
class ScheduleRunExecutionResult:
    run_id: str
    status: str
    delivery_channel: str
    output: str = ""
    error: Optional[str] = None


def _is_terminal_once_schedule(schedule: AgentSchedule) -> bool:
    return (
        str(schedule.schedule_type or "").strip().lower() == "once"
        and str(schedule.status or "").strip().lower() in TERMINAL_ONCE_STATUSES
    )


def _set_terminal_once_status(schedule: AgentSchedule, *, status: str) -> None:
    schedule.status = status
    schedule.next_run_at = None


def _normalize_terminal_once_schedule_state(schedule: AgentSchedule) -> None:
    if _is_terminal_once_schedule(schedule) and schedule.next_run_at is not None:
        schedule.next_run_at = None


def _role_can_view_all(role: str) -> bool:
    return str(role or "").strip().lower() in {"admin", "manager"}


def _normalize_uuid(value: Any, *, field_name: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ScheduleValidationError(f"Invalid {field_name}") from exc


def _user_timezone_from_row(user: User) -> Optional[str]:
    attributes = dict(user.attributes or {}) if isinstance(user.attributes, dict) else {}
    preferences = attributes.get("preferences")
    if isinstance(preferences, dict):
        timezone_name = str(preferences.get("timezone") or "").strip()
        if timezone_name:
            return timezone_name
    return None


def _default_platform_timezone(session) -> str:
    bootstrap_settings = get_platform_setting(session, PLATFORM_BOOTSTRAP_SETTINGS_KEY) or {}
    candidate = str(bootstrap_settings.get("timezone") or "").strip()
    if candidate:
        return candidate

    monitoring_cfg = get_config().get("monitoring.logging", {}) or {}
    configured = str(monitoring_cfg.get("timezone") or "").strip()
    if configured:
        return configured
    return "UTC"


def resolve_owner_timezone(
    *, session, owner_user_id: UUID, explicit_timezone: Optional[str]
) -> str:
    if explicit_timezone:
        return resolve_timezone_name(explicit_timezone)

    user = session.query(User).filter(User.user_id == owner_user_id).first()
    if user is not None:
        inferred = _user_timezone_from_row(user)
        if inferred:
            return resolve_timezone_name(inferred)
    return resolve_timezone_name(_default_platform_timezone(session))


def _load_agent_for_execution(session, *, agent_id: UUID, user_id: UUID, role: str) -> Agent:
    agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
    if agent is None:
        raise ScheduleNotFoundError(f"Agent {agent_id} not found")

    access_context = build_agent_access_context_for_user_id(
        session,
        user_id=str(user_id),
        role=str(role or ""),
    )
    if not can_execute_agent(agent, access_context):
        raise ScheduleAccessError("You don't have permission to use this agent")
    return agent


def _ensure_manage_access(
    schedule: AgentSchedule, *, viewer_user_id: UUID, viewer_role: str
) -> None:
    if _role_can_view_all(viewer_role):
        return
    if schedule.owner_user_id != viewer_user_id:
        raise ScheduleAccessError("You don't have permission to manage this schedule")


def _create_bound_conversation(
    session,
    *,
    agent_id: UUID,
    owner_user_id: UUID,
    source: str = "web",
) -> AgentConversation:
    conversation = AgentConversation(
        agent_id=agent_id,
        owner_user_id=owner_user_id,
        title=build_default_conversation_title(),
        status="active",
        source="feishu" if source == "feishu" else "web",
    )
    session.add(conversation)
    session.flush()
    return conversation


def _ensure_bound_conversation(
    session,
    *,
    agent_id: UUID,
    owner_user_id: UUID,
    bound_conversation_id: Optional[UUID],
    origin_surface: str,
) -> AgentConversation:
    if bound_conversation_id is None:
        return _create_bound_conversation(
            session,
            agent_id=agent_id,
            owner_user_id=owner_user_id,
            source=origin_surface,
        )

    conversation = (
        session.query(AgentConversation)
        .filter(AgentConversation.conversation_id == bound_conversation_id)
        .first()
    )
    if conversation is None:
        raise ScheduleValidationError("Bound conversation does not exist")
    if conversation.owner_user_id != owner_user_id:
        raise ScheduleAccessError("The selected conversation does not belong to this user")
    if conversation.agent_id != agent_id:
        raise ScheduleValidationError("The selected conversation belongs to a different agent")
    return conversation


def _schedule_detail_query(session):
    return session.query(AgentSchedule).options(
        joinedload(AgentSchedule.owner),
        joinedload(AgentSchedule.agent),
        joinedload(AgentSchedule.bound_conversation),
        joinedload(AgentSchedule.runs),
    )


def _serialize_run(run: AgentScheduleRun) -> dict[str, Any]:
    return {
        "id": str(run.run_id),
        "scheduleId": str(run.schedule_id),
        "scheduledFor": run.scheduled_for.isoformat() if run.scheduled_for else None,
        "startedAt": run.started_at.isoformat() if run.started_at else None,
        "completedAt": run.completed_at.isoformat() if run.completed_at else None,
        "status": str(run.status or ""),
        "skipReason": run.skip_reason,
        "errorMessage": run.error_message,
        "assistantMessageId": str(run.assistant_message_id) if run.assistant_message_id else None,
        "conversationId": str(run.conversation_id) if run.conversation_id else None,
        "deliveryChannel": str(run.delivery_channel or "web"),
        "createdAt": run.created_at.isoformat() if run.created_at else None,
    }


def _serialize_schedule(schedule: AgentSchedule) -> dict[str, Any]:
    _normalize_terminal_once_schedule_state(schedule)
    latest_run = next(iter(schedule.runs or []), None)
    return {
        "id": str(schedule.schedule_id),
        "ownerUserId": str(schedule.owner_user_id),
        "ownerUsername": getattr(schedule.owner, "username", None),
        "agentId": str(schedule.agent_id),
        "agentName": getattr(schedule.agent, "name", None),
        "boundConversationId": str(schedule.bound_conversation_id),
        "boundConversationTitle": getattr(schedule.bound_conversation, "title", None),
        "boundConversationSource": getattr(schedule.bound_conversation, "source", None),
        "name": str(schedule.name or ""),
        "promptTemplate": str(schedule.prompt_template or ""),
        "scheduleType": str(schedule.schedule_type or ""),
        "cronExpression": schedule.cron_expression,
        "runAtUtc": schedule.run_at_utc.isoformat() if schedule.run_at_utc else None,
        "timezone": str(schedule.timezone or "UTC"),
        "status": str(schedule.status or ""),
        "createdVia": str(schedule.created_via or ""),
        "originSurface": str(schedule.origin_surface or ""),
        "originMessageId": str(schedule.origin_message_id) if schedule.origin_message_id else None,
        "nextRunAt": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "lastRunAt": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "lastRunStatus": schedule.last_run_status,
        "lastError": schedule.last_error,
        "createdAt": schedule.created_at.isoformat() if schedule.created_at else None,
        "updatedAt": schedule.updated_at.isoformat() if schedule.updated_at else None,
        "latestRun": _serialize_run(latest_run) if latest_run else None,
    }


def build_schedule_created_event(schedule_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schedule_id": schedule_payload["id"],
        "agent_id": schedule_payload["agentId"],
        "name": schedule_payload["name"],
        "status": schedule_payload["status"],
        "next_run_at": schedule_payload["nextRunAt"],
        "timezone": schedule_payload["timezone"],
        "created_via": schedule_payload["createdVia"],
        "bound_conversation_id": schedule_payload["boundConversationId"],
        "bound_conversation_title": schedule_payload["boundConversationTitle"],
        "origin_surface": schedule_payload["originSurface"],
    }


def _build_schedule_trigger_message(
    *,
    schedule: AgentSchedule,
    run: AgentScheduleRun,
) -> tuple[str, dict[str, Any]]:
    schedule_name = str(schedule.name or "未命名任务").strip() or "未命名任务"
    scheduled_for = run.scheduled_for.isoformat() if run.scheduled_for else None
    return (
        f"定时任务已触发：{schedule_name}",
        {
            "eventType": "schedule_triggered",
            "scheduleId": str(schedule.schedule_id),
            "scheduleName": schedule_name,
            "scheduleType": str(schedule.schedule_type or ""),
            "timezone": str(schedule.timezone or "UTC"),
            "scheduledFor": scheduled_for,
            "runId": str(run.run_id),
        },
    )


def _build_schedule_execution_prompt(
    *,
    schedule: AgentSchedule,
    run: AgentScheduleRun,
) -> str:
    schedule_name = str(schedule.name or "未命名任务").strip() or "未命名任务"
    scheduled_for = run.scheduled_for.isoformat() if run.scheduled_for else "unknown"
    prompt_template = str(schedule.prompt_template or "").strip()
    schedule_type = str(schedule.schedule_type or "").strip() or "unknown"
    timezone_name = str(schedule.timezone or "UTC")
    live_data_guidance = ""
    if _TIME_SENSITIVE_TASK_PATTERN.search(f"{schedule_name}\n{prompt_template}"):
        live_data_guidance = (
            "如果任务涉及最新、当前、今日、实时等时效性信息，必须先调用当前 agent 已配置的网页搜索"
            "或外部数据工具核验后再回答。\n"
            "不要仅凭记忆生成价格、新闻、天气、股价、汇率等结果；如果这轮没有可用工具，"
            "请直接说明无法联网核验。\n\n"
        )
    return (
        "这是一次已经到点并且已经触发的定时任务执行，不是用户刚刚发送的新消息。\n"
        "请立即执行任务，并直接向用户汇报执行结果、提醒内容或失败原因。\n"
        "不要告诉用户“稍后再提醒”或“到时候再做”，也不要再次创建、修改或查询这个定时任务，"
        "除非用户在当前轮次明确要求这样做。\n\n"
        f"{live_data_guidance}"
        f"任务名称：{schedule_name}\n"
        f"任务类型：{schedule_type}\n"
        f"计划触发时间：{scheduled_for}\n"
        f"时区：{timezone_name}\n\n"
        "原始任务说明：\n"
        f"{prompt_template}"
    )


def _notify_schedule_event(
    *,
    user_id: UUID,
    schedule_payload: dict[str, Any],
    notification_type: str,
    severity: str,
    title: str,
    message: str,
    dedupe_key: Optional[str] = None,
) -> None:
    create_user_notification(
        user_id=user_id,
        mission_id=None,
        notification_type=notification_type,
        severity=severity,
        title=title,
        message=message,
        action_url=f"/schedules?scheduleId={schedule_payload['id']}",
        action_label="查看定时任务",
        notification_metadata={
            "schedule_id": schedule_payload["id"],
            "agent_id": schedule_payload["agentId"],
            "conversation_id": schedule_payload["boundConversationId"],
            "status": schedule_payload["status"],
        },
        dedupe_key=dedupe_key,
    )


def _compute_schedule_timing(
    *,
    schedule_type: str,
    timezone_name: str,
    cron_expression: Optional[str],
    run_at: Any,
    now: Optional[datetime] = None,
) -> tuple[Optional[str], Optional[datetime], Optional[datetime]]:
    current_time = now or _utcnow()
    schedule_kind = str(schedule_type or "").strip().lower()
    if schedule_kind == "once":
        run_at_utc = parse_run_at(run_at, timezone_name)
        if run_at_utc <= current_time:
            raise ScheduleValidationError("run_at must be in the future")
        return None, run_at_utc, run_at_utc

    if schedule_kind != "recurring":
        raise ScheduleValidationError("schedule_type must be either 'once' or 'recurring'")

    normalized_cron = normalize_cron_expression(cron_expression)
    next_run_at = compute_next_run_at(
        schedule_type="recurring",
        timezone_name=timezone_name,
        cron_expression=normalized_cron,
        base_time_utc=current_time,
    )
    return normalized_cron, None, next_run_at


def _schedule_idempotency_fingerprint(value: Any) -> str:
    """Collapse inconsequential whitespace for chat-driven schedule dedupe."""
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _is_same_agent_auto_schedule_request(
    schedule: AgentSchedule,
    *,
    bound_conversation_id: UUID,
    name: str,
    prompt_template: str,
    schedule_type: str,
    cron_expression: Optional[str],
    run_at_utc: Optional[datetime],
    timezone_name: str,
) -> bool:
    if schedule.bound_conversation_id != bound_conversation_id:
        return False
    if str(schedule.schedule_type or "").strip().lower() != schedule_type:
        return False
    if str(schedule.timezone or "").strip() != timezone_name:
        return False

    if schedule_type == "once":
        if schedule.run_at_utc != run_at_utc:
            return False
    else:
        if str(schedule.cron_expression or "").strip() != str(cron_expression or "").strip():
            return False

    return _schedule_idempotency_fingerprint(schedule.name) == _schedule_idempotency_fingerprint(
        name
    ) and _schedule_idempotency_fingerprint(
        schedule.prompt_template
    ) == _schedule_idempotency_fingerprint(
        prompt_template
    )


def create_schedule(
    *,
    owner_user_id: str,
    owner_role: str,
    agent_id: str,
    name: str,
    prompt_template: str,
    schedule_type: str,
    cron_expression: Optional[str] = None,
    run_at: Any = None,
    timezone: Optional[str] = None,
    created_via: str = "manual_ui",
    origin_surface: str = "schedule_page",
    bound_conversation_id: Optional[str] = None,
    origin_message_id: Optional[str] = None,
) -> dict[str, Any]:
    owner_uuid = _normalize_uuid(owner_user_id, field_name="owner_user_id")
    agent_uuid = _normalize_uuid(agent_id, field_name="agent_id")
    bound_conversation_uuid = (
        _normalize_uuid(bound_conversation_id, field_name="bound_conversation_id")
        if bound_conversation_id
        else None
    )
    origin_message_uuid = (
        _normalize_uuid(origin_message_id, field_name="origin_message_id")
        if origin_message_id
        else None
    )

    with get_db_session() as session:
        _load_agent_for_execution(
            session,
            agent_id=agent_uuid,
            user_id=owner_uuid,
            role=owner_role,
        )
        timezone_name = resolve_owner_timezone(
            session=session,
            owner_user_id=owner_uuid,
            explicit_timezone=timezone,
        )
        normalized_cron, run_at_utc, next_run_at = _compute_schedule_timing(
            schedule_type=schedule_type,
            timezone_name=timezone_name,
            cron_expression=cron_expression,
            run_at=run_at,
        )
        bound_conversation = _ensure_bound_conversation(
            session,
            agent_id=agent_uuid,
            owner_user_id=owner_uuid,
            bound_conversation_id=bound_conversation_uuid,
            origin_surface=origin_surface,
        )
        normalized_schedule_type = str(schedule_type or "").strip().lower()
        normalized_created_via = str(created_via or "manual_ui").strip() or "manual_ui"
        normalized_origin_surface = (
            str(origin_surface or "schedule_page").strip() or "schedule_page"
        )
        normalized_name = str(name or "").strip()
        normalized_prompt_template = str(prompt_template or "").strip()

        if normalized_created_via == "agent_auto" and origin_message_uuid is not None:
            existing_candidates = (
                session.query(AgentSchedule)
                .filter(AgentSchedule.owner_user_id == owner_uuid)
                .filter(AgentSchedule.agent_id == agent_uuid)
                .filter(AgentSchedule.bound_conversation_id == bound_conversation.conversation_id)
                .filter(AgentSchedule.created_via == "agent_auto")
                .filter(AgentSchedule.origin_message_id == origin_message_uuid)
                .filter(AgentSchedule.schedule_type == normalized_schedule_type)
                .all()
            )
            for candidate in existing_candidates:
                if _is_same_agent_auto_schedule_request(
                    candidate,
                    bound_conversation_id=bound_conversation.conversation_id,
                    name=normalized_name,
                    prompt_template=normalized_prompt_template,
                    schedule_type=normalized_schedule_type,
                    cron_expression=normalized_cron,
                    run_at_utc=run_at_utc,
                    timezone_name=timezone_name,
                ):
                    logger.info(
                        "Reusing existing agent-auto schedule for identical origin message",
                        extra={
                            "schedule_id": str(candidate.schedule_id),
                            "agent_id": str(agent_uuid),
                            "owner_user_id": str(owner_uuid),
                            "origin_message_id": str(origin_message_uuid),
                        },
                    )
                    reloaded_existing = (
                        _schedule_detail_query(session)
                        .filter(AgentSchedule.schedule_id == candidate.schedule_id)
                        .first()
                    )
                    if reloaded_existing is None:
                        raise ScheduleError("Failed to reload existing schedule during dedupe")
                    return _serialize_schedule(reloaded_existing)

        schedule = AgentSchedule(
            owner_user_id=owner_uuid,
            agent_id=agent_uuid,
            bound_conversation_id=bound_conversation.conversation_id,
            name=normalized_name,
            prompt_template=normalized_prompt_template,
            schedule_type=normalized_schedule_type,
            cron_expression=normalized_cron,
            run_at_utc=run_at_utc,
            timezone=timezone_name,
            status="active",
            created_via=normalized_created_via,
            origin_surface=normalized_origin_surface,
            origin_message_id=origin_message_uuid,
            next_run_at=next_run_at,
        )
        session.add(schedule)
        session.flush()

        reloaded = (
            _schedule_detail_query(session)
            .filter(AgentSchedule.schedule_id == schedule.schedule_id)
            .first()
        )
        if reloaded is None:
            raise ScheduleError("Failed to reload created schedule")
        payload = _serialize_schedule(reloaded)

    _notify_schedule_event(
        user_id=owner_uuid,
        schedule_payload=payload,
        notification_type="schedule_created",
        severity="success",
        title=f"{payload['name']} 已创建",
        message="定时任务已创建并开始生效。",
        dedupe_key=f"schedule-created:{payload['id']}",
    )
    return payload


def _load_schedule_for_viewer(
    session,
    *,
    schedule_id: UUID,
    viewer_user_id: UUID,
    viewer_role: str,
) -> AgentSchedule:
    query = _schedule_detail_query(session).filter(AgentSchedule.schedule_id == schedule_id)
    if not _role_can_view_all(viewer_role):
        query = query.filter(AgentSchedule.owner_user_id == viewer_user_id)
    schedule = query.first()
    if schedule is None:
        raise ScheduleNotFoundError(f"Schedule {schedule_id} not found")
    _normalize_terminal_once_schedule_state(schedule)
    return schedule


def get_schedule_detail(
    *, schedule_id: str, viewer_user_id: str, viewer_role: str
) -> dict[str, Any]:
    schedule_uuid = _normalize_uuid(schedule_id, field_name="schedule_id")
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        schedule = _load_schedule_for_viewer(
            session,
            schedule_id=schedule_uuid,
            viewer_user_id=viewer_uuid,
            viewer_role=viewer_role,
        )
        return _serialize_schedule(schedule)


def list_schedules(
    *,
    viewer_user_id: str,
    viewer_role: str,
    scope: str = "mine",
    status_filter: Optional[str] = None,
    schedule_type: Optional[str] = None,
    created_via: Optional[str] = None,
    agent_id: Optional[str] = None,
    query_text: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        query = _schedule_detail_query(session)
        if not (_role_can_view_all(viewer_role) and scope == "all"):
            query = query.filter(AgentSchedule.owner_user_id == viewer_uuid)
        if status_filter and status_filter != "all":
            query = query.filter(AgentSchedule.status == status_filter)
        if schedule_type and schedule_type != "all":
            query = query.filter(AgentSchedule.schedule_type == schedule_type)
        if created_via and created_via != "all":
            query = query.filter(AgentSchedule.created_via == created_via)
        if agent_id:
            query = query.filter(
                AgentSchedule.agent_id == _normalize_uuid(agent_id, field_name="agent_id")
            )
        if query_text:
            keyword = f"%{str(query_text).strip()}%"
            query = query.filter(
                AgentSchedule.name.ilike(keyword) | AgentSchedule.prompt_template.ilike(keyword)
            )

        total = query.count()
        rows = (
            query.order_by(
                AgentSchedule.next_run_at.asc().nullslast(),
                AgentSchedule.created_at.desc(),
            )
            .offset(offset)
            .limit(limit)
            .all()
        )
        for row in rows:
            _normalize_terminal_once_schedule_state(row)
        return [_serialize_schedule(row) for row in rows], total


def _update_schedule_fields(
    *,
    schedule: AgentSchedule,
    session,
    name: Optional[str] = None,
    prompt_template: Optional[str] = None,
    schedule_type: Optional[str] = None,
    cron_expression: Optional[str] = None,
    run_at: Any = None,
    timezone: Optional[str] = None,
) -> None:
    effective_timezone = resolve_owner_timezone(
        session=session,
        owner_user_id=schedule.owner_user_id,
        explicit_timezone=timezone or schedule.timezone,
    )
    effective_type = str(schedule_type or schedule.schedule_type or "").strip().lower()
    normalized_cron, run_at_utc, next_run_at = _compute_schedule_timing(
        schedule_type=effective_type,
        timezone_name=effective_timezone,
        cron_expression=(
            cron_expression
            if schedule_type or cron_expression is not None
            else schedule.cron_expression
        ),
        run_at=run_at if schedule_type or run_at is not None else schedule.run_at_utc,
        now=_utcnow(),
    )
    if name is not None:
        schedule.name = str(name).strip()
    if prompt_template is not None:
        schedule.prompt_template = str(prompt_template).strip()
    schedule.schedule_type = effective_type
    schedule.cron_expression = normalized_cron
    schedule.run_at_utc = run_at_utc
    schedule.timezone = effective_timezone
    schedule.next_run_at = next_run_at
    if schedule.status in {"completed", "failed"}:
        schedule.status = "active"
    schedule.last_error = None


def update_schedule(
    *,
    schedule_id: str,
    viewer_user_id: str,
    viewer_role: str,
    name: Optional[str] = None,
    prompt_template: Optional[str] = None,
    schedule_type: Optional[str] = None,
    cron_expression: Optional[str] = None,
    run_at: Any = None,
    timezone: Optional[str] = None,
) -> dict[str, Any]:
    schedule_uuid = _normalize_uuid(schedule_id, field_name="schedule_id")
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        schedule = _load_schedule_for_viewer(
            session,
            schedule_id=schedule_uuid,
            viewer_user_id=viewer_uuid,
            viewer_role=viewer_role,
        )
        _ensure_manage_access(schedule, viewer_user_id=viewer_uuid, viewer_role=viewer_role)
        _update_schedule_fields(
            schedule=schedule,
            session=session,
            name=name,
            prompt_template=prompt_template,
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            run_at=run_at,
            timezone=timezone,
        )
        session.flush()
        session.refresh(schedule)
        return _serialize_schedule(schedule)


def delete_schedule(*, schedule_id: str, viewer_user_id: str, viewer_role: str) -> None:
    schedule_uuid = _normalize_uuid(schedule_id, field_name="schedule_id")
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        schedule = _load_schedule_for_viewer(
            session,
            schedule_id=schedule_uuid,
            viewer_user_id=viewer_uuid,
            viewer_role=viewer_role,
        )
        _ensure_manage_access(schedule, viewer_user_id=viewer_uuid, viewer_role=viewer_role)
        session.delete(schedule)


def pause_schedule(*, schedule_id: str, viewer_user_id: str, viewer_role: str) -> dict[str, Any]:
    schedule_uuid = _normalize_uuid(schedule_id, field_name="schedule_id")
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        schedule = _load_schedule_for_viewer(
            session,
            schedule_id=schedule_uuid,
            viewer_user_id=viewer_uuid,
            viewer_role=viewer_role,
        )
        _ensure_manage_access(schedule, viewer_user_id=viewer_uuid, viewer_role=viewer_role)
        if _is_terminal_once_schedule(schedule):
            raise ScheduleValidationError("Terminal one-time schedules cannot be paused")
        schedule.status = "paused"
        session.flush()
        session.refresh(schedule)
        payload = _serialize_schedule(schedule)
    _notify_schedule_event(
        user_id=UUID(payload["ownerUserId"]),
        schedule_payload=payload,
        notification_type="schedule_paused",
        severity="warning",
        title=f"{payload['name']} 已暂停",
        message="定时任务已暂停，不会继续自动触发。",
        dedupe_key=f"schedule-paused:{payload['id']}",
    )
    return payload


def resume_schedule(*, schedule_id: str, viewer_user_id: str, viewer_role: str) -> dict[str, Any]:
    schedule_uuid = _normalize_uuid(schedule_id, field_name="schedule_id")
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        schedule = _load_schedule_for_viewer(
            session,
            schedule_id=schedule_uuid,
            viewer_user_id=viewer_uuid,
            viewer_role=viewer_role,
        )
        _ensure_manage_access(schedule, viewer_user_id=viewer_uuid, viewer_role=viewer_role)
        if _is_terminal_once_schedule(schedule):
            raise ScheduleValidationError("Terminal one-time schedules cannot be resumed")
        now = _utcnow()
        if schedule.schedule_type == "once":
            if schedule.run_at_utc is None:
                raise ScheduleValidationError("One-time schedule is missing run_at_utc")
            schedule.next_run_at = max(schedule.run_at_utc, now)
        else:
            base_time = (
                schedule.next_run_at if schedule.next_run_at and schedule.next_run_at > now else now
            )
            schedule.next_run_at = compute_next_run_at(
                schedule_type="recurring",
                timezone_name=schedule.timezone,
                cron_expression=schedule.cron_expression,
                base_time_utc=base_time,
            )
        schedule.status = "active"
        schedule.last_error = None
        session.flush()
        session.refresh(schedule)
        payload = _serialize_schedule(schedule)
    _notify_schedule_event(
        user_id=UUID(payload["ownerUserId"]),
        schedule_payload=payload,
        notification_type="schedule_resumed",
        severity="success",
        title=f"{payload['name']} 已恢复",
        message="定时任务已恢复自动执行。",
        dedupe_key=f"schedule-resumed:{payload['id']}",
    )
    return payload


def run_schedule_now(*, schedule_id: str, viewer_user_id: str, viewer_role: str) -> dict[str, Any]:
    schedule_uuid = _normalize_uuid(schedule_id, field_name="schedule_id")
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        schedule = _load_schedule_for_viewer(
            session,
            schedule_id=schedule_uuid,
            viewer_user_id=viewer_uuid,
            viewer_role=viewer_role,
        )
        _ensure_manage_access(schedule, viewer_user_id=viewer_uuid, viewer_role=viewer_role)
        if _is_terminal_once_schedule(schedule):
            raise ScheduleValidationError("Terminal one-time schedules cannot be run manually")
        run = AgentScheduleRun(
            schedule_id=schedule.schedule_id,
            scheduled_for=_utcnow(),
            status="queued",
            conversation_id=schedule.bound_conversation_id,
            delivery_channel="web",
        )
        session.add(run)
        session.flush()
        session.refresh(run)
        return _serialize_run(run)


def list_schedule_runs(
    *,
    schedule_id: str,
    viewer_user_id: str,
    viewer_role: str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    schedule_uuid = _normalize_uuid(schedule_id, field_name="schedule_id")
    viewer_uuid = _normalize_uuid(viewer_user_id, field_name="viewer_user_id")
    with get_db_session() as session:
        schedule = _load_schedule_for_viewer(
            session,
            schedule_id=schedule_uuid,
            viewer_user_id=viewer_uuid,
            viewer_role=viewer_role,
        )
        query = (
            session.query(AgentScheduleRun)
            .filter(AgentScheduleRun.schedule_id == schedule.schedule_id)
            .order_by(AgentScheduleRun.scheduled_for.desc(), AgentScheduleRun.created_at.desc())
        )
        total = query.count()
        rows = query.offset(offset).limit(limit).all()
        return ([_serialize_run(row) for row in rows], total)


def preview_schedule_payload(
    *,
    schedule_type: str,
    timezone_name: str,
    cron_expression: Optional[str] = None,
    run_at: Any = None,
) -> dict[str, Any]:
    preview: SchedulePreview = preview_schedule(
        schedule_type=schedule_type,
        timezone_name=timezone_name,
        cron_expression=cron_expression,
        run_at=run_at,
    )
    return {
        "is_valid": preview.is_valid,
        "human_summary": preview.human_summary,
        "normalized_cron": preview.normalized_cron,
        "next_occurrences": preview.next_occurrences,
    }


def cleanup_terminal_one_time_schedules(*, retention_days: int = 30, limit: int = 100) -> int:
    if retention_days <= 0 or limit <= 0:
        return 0

    cutoff = _utcnow() - timedelta(days=retention_days)
    with get_db_session() as session:
        candidates = (
            session.query(AgentSchedule)
            .filter(AgentSchedule.schedule_type == "once")
            .filter(AgentSchedule.status.in_(tuple(TERMINAL_ONCE_STATUSES)))
            .filter(
                or_(
                    and_(
                        AgentSchedule.last_run_at.isnot(None),
                        AgentSchedule.last_run_at < cutoff,
                    ),
                    and_(
                        AgentSchedule.last_run_at.is_(None),
                        AgentSchedule.updated_at < cutoff,
                    ),
                )
            )
            .order_by(
                AgentSchedule.last_run_at.asc().nullsfirst(),
                AgentSchedule.updated_at.asc(),
                AgentSchedule.created_at.asc(),
            )
            .limit(limit)
            .all()
        )
        for schedule in candidates:
            session.delete(schedule)
        return len(candidates)


def _advance_schedule_after_planning(schedule: AgentSchedule, *, scheduled_for: datetime) -> None:
    if schedule.schedule_type == "once":
        schedule.status = "completed"
        schedule.next_run_at = None
        return

    schedule.next_run_at = compute_next_run_at(
        schedule_type="recurring",
        timezone_name=schedule.timezone,
        cron_expression=schedule.cron_expression,
        base_time_utc=scheduled_for,
    )


def plan_due_schedule_runs(*, limit: int = 50) -> dict[str, int]:
    queued = 0
    skipped = 0
    with get_db_session() as session:
        now = _utcnow()
        due_schedules = (
            session.query(AgentSchedule)
            .filter(AgentSchedule.status == "active")
            .filter(AgentSchedule.next_run_at.isnot(None))
            .filter(AgentSchedule.next_run_at <= now)
            .order_by(AgentSchedule.next_run_at.asc())
            .limit(limit)
            .all()
        )
        for schedule in due_schedules:
            scheduled_for = schedule.next_run_at or now
            running = (
                session.query(AgentScheduleRun.run_id)
                .filter(AgentScheduleRun.schedule_id == schedule.schedule_id)
                .filter(AgentScheduleRun.status == "running")
                .first()
                is not None
            )
            duplicate = (
                session.query(AgentScheduleRun.run_id)
                .filter(AgentScheduleRun.schedule_id == schedule.schedule_id)
                .filter(AgentScheduleRun.scheduled_for == scheduled_for)
                .first()
                is not None
            )
            if duplicate:
                _advance_schedule_after_planning(schedule, scheduled_for=scheduled_for)
                continue
            if running:
                session.add(
                    AgentScheduleRun(
                        schedule_id=schedule.schedule_id,
                        scheduled_for=scheduled_for,
                        status="skipped",
                        skip_reason="overlap",
                        conversation_id=schedule.bound_conversation_id,
                        delivery_channel="web",
                    )
                )
                schedule.last_run_at = now
                schedule.last_run_status = "skipped"
                skipped += 1
                _advance_schedule_after_planning(schedule, scheduled_for=scheduled_for)
                continue
            session.add(
                AgentScheduleRun(
                    schedule_id=schedule.schedule_id,
                    scheduled_for=scheduled_for,
                    status="queued",
                    conversation_id=schedule.bound_conversation_id,
                    delivery_channel="web",
                )
            )
            queued += 1
            _advance_schedule_after_planning(schedule, scheduled_for=scheduled_for)
    return {"queued": queued, "skipped": skipped}


def claim_queued_schedule_run_ids(*, limit: int = 10) -> list[str]:
    with get_db_session() as session:
        rows = (
            session.query(AgentScheduleRun)
            .filter(AgentScheduleRun.status == "queued")
            .order_by(AgentScheduleRun.scheduled_for.asc(), AgentScheduleRun.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(limit)
            .all()
        )
        now = _utcnow()
        run_ids: list[str] = []
        for row in rows:
            row.status = "running"
            row.started_at = now
            row.error_message = None
            run_ids.append(str(row.run_id))
        return run_ids


def _load_run_for_execution(session, *, run_id: UUID) -> AgentScheduleRun:
    run = (
        session.query(AgentScheduleRun)
        .options(
            joinedload(AgentScheduleRun.schedule).joinedload(AgentSchedule.owner),
            joinedload(AgentScheduleRun.schedule).joinedload(AgentSchedule.agent),
            joinedload(AgentScheduleRun.schedule)
            .joinedload(AgentSchedule.bound_conversation)
            .joinedload(AgentConversation.external_links)
            .joinedload(ExternalConversationLink.publication),
        )
        .filter(AgentScheduleRun.run_id == run_id)
        .first()
    )
    if run is None:
        raise ScheduleNotFoundError(f"Run {run_id} not found")
    return run


def _mark_invalid_binding(
    *,
    session,
    run: AgentScheduleRun,
    schedule: AgentSchedule,
    error_message: str,
) -> dict[str, Any]:
    now = _utcnow()
    run.status = "failed"
    run.completed_at = now
    run.error_message = error_message
    schedule.last_run_at = now
    schedule.last_run_status = "failed"
    schedule.last_error = error_message
    if schedule.schedule_type == "recurring":
        schedule.status = "paused"
    else:
        _set_terminal_once_status(schedule, status="failed")
    session.flush()
    payload = _serialize_schedule(schedule)
    _notify_schedule_event(
        user_id=schedule.owner_user_id,
        schedule_payload=payload,
        notification_type="schedule_binding_invalid",
        severity="error",
        title=f"{payload['name']} 已停止",
        message=error_message,
        dedupe_key=f"schedule-binding-invalid:{payload['id']}",
    )
    return payload


async def _deliver_to_feishu_if_needed(
    *,
    schedule: AgentSchedule,
    result: dict[str, Any],
) -> str:
    conversation = schedule.bound_conversation
    if conversation is None or str(conversation.source or "") != "feishu":
        return "web"

    eligible_link = None
    for link in conversation.external_links or []:
        if (
            getattr(link, "publication", None) is not None
            and link.publication.status == "published"
        ):
            eligible_link = link
            break
    if eligible_link is None:
        raise InvalidScheduleBindingError(
            "Feishu publication is unavailable for this scheduled thread"
        )

    from api_gateway.routers.integrations import (
        _build_feishu_reply_text,
        _send_feishu_markdown_card_message,
    )

    reply_text = _build_feishu_reply_text(
        agent=schedule.agent,
        conversation=conversation,
        output_text=str(result.get("output") or ""),
        delivered_artifacts=[],
        pending_artifacts=list(result.get("artifact_delta") or []),
        base_url=None,
    )
    await asyncio.to_thread(
        _send_feishu_markdown_card_message,
        eligible_link.publication,
        chat_id=eligible_link.external_chat_key,
        markdown_text=reply_text,
    )
    return "feishu"


async def execute_schedule_run(*, run_id: str) -> ScheduleRunExecutionResult:
    run_uuid = _normalize_uuid(run_id, field_name="run_id")

    with get_db_session() as session:
        run = _load_run_for_execution(session, run_id=run_uuid)
        schedule = run.schedule
        if schedule is None:
            raise ScheduleNotFoundError(f"Schedule for run {run_id} not found")
        conversation = schedule.bound_conversation
        owner = schedule.owner
        if owner is None:
            payload = _mark_invalid_binding(
                session=session,
                run=run,
                schedule=schedule,
                error_message="Schedule owner is unavailable.",
            )
            return ScheduleRunExecutionResult(
                run_id=run_id,
                status="failed",
                delivery_channel="web",
                error=payload["lastError"],
            )
        if conversation is None or conversation.status != "active":
            payload = _mark_invalid_binding(
                session=session,
                run=run,
                schedule=schedule,
                error_message="Bound conversation is unavailable.",
            )
            return ScheduleRunExecutionResult(
                run_id=run_id,
                status="failed",
                delivery_channel="web",
                error=payload["lastError"],
            )
        principal: ConversationExecutionPrincipal = build_conversation_execution_principal(
            user_id=owner.user_id,
            role=owner.role,
            username=owner.username,
        )
        trigger_message_text, trigger_message_payload = _build_schedule_trigger_message(
            schedule=schedule,
            run=run,
        )
        execution_prompt = _build_schedule_execution_prompt(
            schedule=schedule,
            run=run,
        )
        title_seed_text = str(schedule.name or schedule.prompt_template or "").strip()
        context_origin_surface = "feishu" if conversation.source == "feishu" else "persistent_chat"

    try:
        from api_gateway.routers.agent_conversations import execute_persistent_conversation_turn

        result = await execute_persistent_conversation_turn(
            conversation=conversation,
            principal=principal,
            message=schedule.prompt_template,
            files=[],
            source="schedule",
            external_event_id=None,
            chunk_callback=None,
            persist_input_message=True,
            input_message_role="system",
            input_message_text=trigger_message_text,
            input_message_content_json=trigger_message_payload,
            ephemeral_system_messages=[execution_prompt],
            execution_intent_text=schedule.prompt_template,
            title_seed_text=title_seed_text or schedule.prompt_template,
            context_origin_surface=context_origin_surface,
            extra_execution_context={
                "schedule_triggered": True,
                "schedule_id": str(schedule.schedule_id),
                "schedule_run_id": str(run.run_id),
                "schedule_name": str(schedule.name or ""),
                "schedule_timezone": str(schedule.timezone or "UTC"),
                "schedule_type": str(schedule.schedule_type or ""),
                "schedule_scheduled_for": (
                    run.scheduled_for.isoformat() if run.scheduled_for else None
                ),
            },
        )
        delivery_channel = await _deliver_to_feishu_if_needed(schedule=schedule, result=result)
    except InvalidScheduleBindingError as exc:
        with get_db_session() as session:
            run = _load_run_for_execution(session, run_id=run_uuid)
            payload = _mark_invalid_binding(
                session=session,
                run=run,
                schedule=run.schedule,
                error_message=str(exc),
            )
            return ScheduleRunExecutionResult(
                run_id=run_id,
                status="failed",
                delivery_channel="web",
                error=payload["lastError"],
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Scheduled run %s failed: %s", run_id, exc, exc_info=True)
        payload: dict[str, Any]
        with get_db_session() as session:
            run = _load_run_for_execution(session, run_id=run_uuid)
            schedule = run.schedule
            now = _utcnow()
            run.status = "failed"
            run.completed_at = now
            run.error_message = str(exc)
            schedule.last_run_at = now
            schedule.last_run_status = "failed"
            schedule.last_error = str(exc)
            if schedule.schedule_type == "once":
                _set_terminal_once_status(schedule, status="failed")
            session.flush()
            payload = _serialize_schedule(schedule)
        if payload["status"] == "failed":
            _notify_schedule_event(
                user_id=UUID(payload["ownerUserId"]),
                schedule_payload=payload,
                notification_type="schedule_failed",
                severity="error",
                title=f"{payload['name']} 执行失败",
                message=str(exc),
                dedupe_key=f"schedule-failed:{payload['id']}:{run_id}",
            )
        return ScheduleRunExecutionResult(
            run_id=run_id,
            status="failed",
            delivery_channel="web",
            error=str(exc),
        )

    with get_db_session() as session:
        run = _load_run_for_execution(session, run_id=run_uuid)
        schedule = run.schedule
        now = _utcnow()
        run.status = "succeeded"
        run.completed_at = now
        run.error_message = None
        run.conversation_id = schedule.bound_conversation_id
        assistant_message_id = result.get("assistant_message_id")
        if assistant_message_id:
            run.assistant_message_id = _normalize_uuid(
                assistant_message_id,
                field_name="assistant_message_id",
            )
        run.delivery_channel = delivery_channel
        schedule.last_run_at = now
        schedule.last_run_status = "succeeded"
        schedule.last_error = None
        if schedule.schedule_type == "once" and schedule.status not in {"failed"}:
            _set_terminal_once_status(schedule, status="completed")

    return ScheduleRunExecutionResult(
        run_id=run_id,
        status="succeeded",
        delivery_channel=delivery_channel,
        output=str(result.get("output") or ""),
    )
