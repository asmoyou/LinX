"""Tooling for agent-driven schedule management."""

from __future__ import annotations

import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from langchain_core.tools import StructuredTool

from agent_scheduling.cron_utils import ScheduleValidationError
from agent_scheduling.service import (
    ScheduleAccessError,
    ScheduleNotFoundError,
    create_schedule,
    delete_schedule,
    get_schedule_detail,
    list_schedules,
    pause_schedule,
    resume_schedule,
    run_schedule_now,
    update_schedule,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScheduleToolContext:
    owner_user_id: str
    owner_role: str
    agent_id: str
    origin_surface: str
    bound_conversation_id: Optional[str] = None
    origin_message_id: Optional[str] = None


_schedule_context_var: ContextVar[Optional[ScheduleToolContext]] = ContextVar(
    "agent_schedule_tool_context",
    default=None,
)
_created_schedule_events_var: ContextVar[list[dict[str, Any]]] = ContextVar(
    "agent_schedule_tool_events",
    default=[],
)


def set_schedule_tool_context(context: ScheduleToolContext) -> None:
    _schedule_context_var.set(context)
    _created_schedule_events_var.set([])


def clear_schedule_tool_context() -> None:
    _schedule_context_var.set(None)
    _created_schedule_events_var.set([])


def consume_created_schedule_events() -> list[dict[str, Any]]:
    events = list(_created_schedule_events_var.get() or [])
    _created_schedule_events_var.set([])
    return events


def _append_created_schedule_event(event: dict[str, Any]) -> None:
    events = list(_created_schedule_events_var.get() or [])
    events.append(dict(event))
    _created_schedule_events_var.set(events)


def _normalize_schedule_lookup(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _normalize_action(value: Any) -> str:
    normalized = str(value or "create").strip().lower().replace("-", "_")
    aliases = {
        "add": "create",
        "show": "get",
        "detail": "get",
        "search": "list",
        "edit": "update",
        "modify": "update",
        "remove": "delete",
        "disable": "pause",
        "enable": "resume",
        "trigger": "run_now",
    }
    return aliases.get(normalized, normalized or "create")


def _normalize_limit(value: Optional[int], default: int = 10) -> int:
    try:
        if value is None:
            return default
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 20))


def _format_schedule_line(schedule: dict[str, Any]) -> str:
    next_run = str(schedule.get("nextRunAt") or schedule.get("runAtUtc") or "not scheduled")
    return (
        f"- {schedule.get('name')} "
        f"(id={schedule.get('id')}, status={schedule.get('status')}, "
        f"type={schedule.get('scheduleType')}, next={next_run}, timezone={schedule.get('timezone')})"
    )


def _format_schedule_detail(schedule: dict[str, Any]) -> str:
    next_run = str(schedule.get("nextRunAt") or schedule.get("runAtUtc") or "not scheduled")
    prompt_template = str(schedule.get("promptTemplate") or "").strip() or "<empty>"
    return (
        f"Schedule details: {schedule.get('name')} "
        f"(id={schedule.get('id')}, status={schedule.get('status')}, "
        f"type={schedule.get('scheduleType')}, timezone={schedule.get('timezone')}, "
        f"next run={next_run}, conversation={schedule.get('boundConversationTitle') or schedule.get('boundConversationId')}). "
        f"Prompt: {prompt_template}"
    )


def _schedule_matches_query(schedule: dict[str, Any], query: str) -> bool:
    normalized_query = _normalize_schedule_lookup(query)
    if not normalized_query:
        return True

    haystack = " ".join(
        [
            str(schedule.get("id") or ""),
            str(schedule.get("name") or ""),
            str(schedule.get("promptTemplate") or ""),
            str(schedule.get("status") or ""),
            str(schedule.get("scheduleType") or ""),
            str(schedule.get("timezone") or ""),
            str(schedule.get("boundConversationTitle") or ""),
        ]
    )
    return normalized_query in _normalize_schedule_lookup(haystack)


def _load_agent_schedules(
    *,
    context: ScheduleToolContext,
    query_text: Optional[str] = None,
    status_filter: Optional[str] = None,
    schedule_type: Optional[str] = None,
    created_via: Optional[str] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    items, _ = list_schedules(
        viewer_user_id=context.owner_user_id,
        viewer_role=context.owner_role,
        scope="mine",
        status_filter=status_filter,
        schedule_type=schedule_type,
        created_via=created_via,
        agent_id=context.agent_id,
        query_text=query_text,
        limit=limit,
        offset=0,
    )
    return items


def _prefer_current_conversation_matches(
    schedules: list[dict[str, Any]],
    *,
    context: ScheduleToolContext,
) -> list[dict[str, Any]]:
    if not context.bound_conversation_id:
        return schedules

    conversation_matches = [
        schedule
        for schedule in schedules
        if str(schedule.get("boundConversationId") or "") == context.bound_conversation_id
    ]
    return conversation_matches or schedules


def _resolve_schedule_target(
    *,
    context: ScheduleToolContext,
    schedule_id: Optional[str],
    target_name: Optional[str],
    query: Optional[str],
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    if str(schedule_id or "").strip():
        try:
            return (
                get_schedule_detail(
                    schedule_id=str(schedule_id).strip(),
                    viewer_user_id=context.owner_user_id,
                    viewer_role=context.owner_role,
                ),
                None,
            )
        except (ScheduleValidationError, ScheduleAccessError, ScheduleNotFoundError) as exc:
            return None, f"Needs clarification: {exc}"

    schedules = _load_agent_schedules(context=context, limit=100)
    schedules = _prefer_current_conversation_matches(schedules, context=context)
    if not schedules:
        return None, "Needs clarification: no schedules are available for this agent yet."

    normalized_target_name = _normalize_schedule_lookup(target_name)
    if normalized_target_name:
        exact_matches = [
            schedule
            for schedule in schedules
            if _normalize_schedule_lookup(schedule.get("name")) == normalized_target_name
        ]
        if len(exact_matches) == 1:
            return exact_matches[0], None
        if len(exact_matches) > 1:
            candidates = "\n".join(_format_schedule_line(schedule) for schedule in exact_matches[:5])
            return (
                None,
                "Needs clarification: multiple schedules have that name. "
                f"Please use schedule_id.\n{candidates}",
            )

    normalized_query = _normalize_schedule_lookup(query or target_name)
    if normalized_query:
        fuzzy_matches = [
            schedule for schedule in schedules if _schedule_matches_query(schedule, normalized_query)
        ]
        if len(fuzzy_matches) == 1:
            return fuzzy_matches[0], None
        if len(fuzzy_matches) > 1:
            candidates = "\n".join(_format_schedule_line(schedule) for schedule in fuzzy_matches[:5])
            return (
                None,
                "Needs clarification: multiple schedules match that request. "
                f"Please use schedule_id.\n{candidates}",
            )

    if not str(target_name or "").strip() and not str(query or "").strip():
        if len(schedules) == 1:
            return schedules[0], None
        if context.bound_conversation_id:
            conversation_only = [
                schedule
                for schedule in schedules
                if str(schedule.get("boundConversationId") or "") == context.bound_conversation_id
            ]
            if len(conversation_only) == 1:
                return conversation_only[0], None

    return None, (
        "Needs clarification: specify schedule_id or an exact target_name. "
        "Use action='list' first if you need to inspect available schedules."
    )


def create_manage_schedule_tool(agent_id: UUID, user_id: UUID) -> StructuredTool:
    """Create the schedule-management tool available to chat agents."""

    def manage_schedule(
        action: str = "create",
        schedule_id: Optional[str] = None,
        target_name: Optional[str] = None,
        query: Optional[str] = None,
        name: Optional[str] = None,
        prompt_template: Optional[str] = None,
        schedule_type: Optional[str] = None,
        cron_expression: Optional[str] = None,
        run_at: Optional[str] = None,
        timezone: Optional[str] = None,
        status: Optional[str] = None,
        created_via: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> str:
        """Manage schedules for the current user and agent.

        Actions:
        - create: create a schedule. Requires name, prompt_template, schedule_type, and run_at/cron_expression.
        - list: inspect schedules. Optional filters: query, status, schedule_type, created_via, limit.
        - get: inspect one schedule. Requires schedule_id or target_name.
        - update: modify one schedule. Requires schedule_id or target_name plus at least one editable field.
        - pause/resume/delete/run_now: operate on one schedule. Requires schedule_id or target_name.

        Rules:
        - Only create when the user explicitly asks for future execution.
        - For update/delete/pause/resume/run_now, list first when the target is ambiguous.
        - Do not guess missing fields. Return a clarification request instead.
        """

        _ = (agent_id, user_id)
        context = _schedule_context_var.get()
        if context is None:
            return "Error: schedule tool context is unavailable for this execution."

        normalized_action = _normalize_action(action)

        try:
            if normalized_action == "create":
                if not str(name or "").strip():
                    return "Needs clarification: schedule name is required."
                if not str(prompt_template or "").strip():
                    return "Needs clarification: execution prompt_template is required."
                if not str(schedule_type or "").strip():
                    return "Needs clarification: schedule_type must be once or recurring."

                event_payload = create_schedule(
                    owner_user_id=context.owner_user_id,
                    owner_role=context.owner_role,
                    agent_id=context.agent_id,
                    name=str(name),
                    prompt_template=str(prompt_template),
                    schedule_type=str(schedule_type),
                    cron_expression=cron_expression,
                    run_at=run_at,
                    timezone=timezone,
                    created_via="agent_auto",
                    origin_surface=context.origin_surface,
                    bound_conversation_id=context.bound_conversation_id,
                    origin_message_id=context.origin_message_id,
                )
                _append_created_schedule_event(event_payload)
                next_run_label = str(event_payload.get("nextRunAt") or "not scheduled")
                return (
                    f"Schedule created successfully: {event_payload.get('name')} "
                    f"(id={event_payload.get('id')}, next run: {next_run_label}, "
                    f"timezone: {event_payload.get('timezone')})."
                )

            if normalized_action == "list":
                limit_value = _normalize_limit(limit)
                items = _load_agent_schedules(
                    context=context,
                    status_filter=status,
                    schedule_type=schedule_type,
                    created_via=created_via,
                    limit=100,
                )
                if str(query or "").strip():
                    items = [schedule for schedule in items if _schedule_matches_query(schedule, str(query))]
                if not items:
                    return "No schedules found for this agent."
                lines = "\n".join(_format_schedule_line(schedule) for schedule in items[:limit_value])
                return f"Found {len(items[:limit_value])} schedule(s):\n{lines}"

            resolved_schedule, resolution_error = _resolve_schedule_target(
                context=context,
                schedule_id=schedule_id,
                target_name=target_name,
                query=query,
            )
            if resolution_error:
                return resolution_error
            if resolved_schedule is None:
                return "Needs clarification: unable to resolve the target schedule."

            if normalized_action == "get":
                return _format_schedule_detail(resolved_schedule)

            if normalized_action == "update":
                if not any(
                    value is not None
                    for value in (
                        name,
                        prompt_template,
                        schedule_type,
                        cron_expression,
                        run_at,
                        timezone,
                    )
                ):
                    return (
                        "Needs clarification: provide at least one field to update "
                        "(name, prompt_template, schedule_type, cron_expression, run_at, timezone)."
                    )

                updated_payload = update_schedule(
                    schedule_id=str(resolved_schedule["id"]),
                    viewer_user_id=context.owner_user_id,
                    viewer_role=context.owner_role,
                    name=name,
                    prompt_template=prompt_template,
                    schedule_type=schedule_type,
                    cron_expression=cron_expression,
                    run_at=run_at,
                    timezone=timezone,
                )
                return (
                    f"Schedule updated successfully: {updated_payload.get('name')} "
                    f"(id={updated_payload.get('id')}, status={updated_payload.get('status')}, "
                    f"next run: {updated_payload.get('nextRunAt') or updated_payload.get('runAtUtc') or 'not scheduled'})."
                )

            if normalized_action == "pause":
                paused_payload = pause_schedule(
                    schedule_id=str(resolved_schedule["id"]),
                    viewer_user_id=context.owner_user_id,
                    viewer_role=context.owner_role,
                )
                return f"Schedule paused successfully: {_format_schedule_line(paused_payload)}"

            if normalized_action == "resume":
                resumed_payload = resume_schedule(
                    schedule_id=str(resolved_schedule["id"]),
                    viewer_user_id=context.owner_user_id,
                    viewer_role=context.owner_role,
                )
                return f"Schedule resumed successfully: {_format_schedule_line(resumed_payload)}"

            if normalized_action == "delete":
                delete_schedule(
                    schedule_id=str(resolved_schedule["id"]),
                    viewer_user_id=context.owner_user_id,
                    viewer_role=context.owner_role,
                )
                return (
                    f"Schedule deleted successfully: {resolved_schedule.get('name')} "
                    f"(id={resolved_schedule.get('id')})."
                )

            if normalized_action == "run_now":
                run_payload = run_schedule_now(
                    schedule_id=str(resolved_schedule["id"]),
                    viewer_user_id=context.owner_user_id,
                    viewer_role=context.owner_role,
                )
                return (
                    f"Schedule queued for immediate execution: {resolved_schedule.get('name')} "
                    f"(id={resolved_schedule.get('id')}, run_id={run_payload.get('id')}, "
                    f"scheduled_for={run_payload.get('scheduledFor')})."
                )

            return (
                "Error: unsupported action. Use one of create, list, get, update, "
                "pause, resume, delete, or run_now."
            )
        except ScheduleValidationError as exc:
            return f"Needs clarification: {exc}"
        except (ScheduleAccessError, ScheduleNotFoundError) as exc:
            return f"Error: {exc}"
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to manage schedule via agent tool: %s", exc, exc_info=True)
            return f"Error: failed to manage schedule because {exc}"

    return StructuredTool.from_function(
        name="manage_schedule",
        description=(
            "Manage schedules for the current user and current agent. "
            "Supported actions: create, list, get, update, pause, resume, delete, run_now. "
            "For create, provide name, prompt_template, schedule_type, and run_at or cron_expression. "
            "For non-create actions, provide schedule_id when possible; otherwise use target_name "
            "or call list first to inspect schedules and disambiguate."
        ),
        func=manage_schedule,
    )
