"""Cron parsing, schedule preview, and timezone helpers for agent schedules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ScheduleValidationError(ValueError):
    """Raised when schedule input is invalid."""


_WEEKDAY_LABELS = {
    "0": "Sun",
    "1": "Mon",
    "2": "Tue",
    "3": "Wed",
    "4": "Thu",
    "5": "Fri",
    "6": "Sat",
    "7": "Sun",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_croniter():
    try:
        from croniter import croniter as croniter_impl
    except ModuleNotFoundError as exc:
        raise ScheduleValidationError(
            "croniter is not installed; schedule features are unavailable until dependencies are updated"
        ) from exc
    return croniter_impl


def resolve_timezone_name(timezone_name: Optional[str], fallback: str = "UTC") -> str:
    candidate = str(timezone_name or "").strip() or str(fallback or "UTC").strip() or "UTC"
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise ScheduleValidationError(f"Invalid timezone: {candidate}") from exc
    return candidate


def get_timezone(timezone_name: Optional[str], fallback: str = "UTC") -> ZoneInfo:
    return ZoneInfo(resolve_timezone_name(timezone_name, fallback=fallback))


def normalize_cron_expression(expression: Optional[str]) -> str:
    normalized = " ".join(str(expression or "").strip().split())
    if not normalized:
        raise ScheduleValidationError("Cron expression is required for recurring schedules")

    fields = normalized.split(" ")
    if len(fields) != 5:
        raise ScheduleValidationError("Cron expression must contain exactly 5 fields")

    base = datetime.now(get_timezone("UTC"))
    croniter = _get_croniter()
    try:
        croniter(normalized, base)
    except (ValueError, KeyError) as exc:
        raise ScheduleValidationError(f"Invalid cron expression: {normalized}") from exc
    return normalized


def parse_run_at(value: Any, timezone_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        raw = str(value or "").strip()
        if not raw:
            raise ScheduleValidationError("run_at is required for one-time schedules")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ScheduleValidationError("run_at must be a valid ISO datetime") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=get_timezone(timezone_name))
    return parsed.astimezone(timezone.utc)


def compute_next_run_at(
    *,
    schedule_type: str,
    timezone_name: str,
    cron_expression: Optional[str] = None,
    run_at_utc: Optional[datetime] = None,
    base_time_utc: Optional[datetime] = None,
) -> Optional[datetime]:
    schedule_kind = str(schedule_type or "").strip().lower()
    base_utc = base_time_utc or utcnow()
    if base_utc.tzinfo is None:
        base_utc = base_utc.replace(tzinfo=timezone.utc)

    if schedule_kind == "once":
        if run_at_utc is None:
            raise ScheduleValidationError("run_at is required for one-time schedules")
        if run_at_utc.tzinfo is None:
            run_at_utc = run_at_utc.replace(tzinfo=timezone.utc)
        return run_at_utc

    if schedule_kind != "recurring":
        raise ScheduleValidationError(f"Unsupported schedule type: {schedule_type}")

    normalized_cron = normalize_cron_expression(cron_expression)
    localized_base = base_utc.astimezone(get_timezone(timezone_name))
    croniter = _get_croniter()
    iterator = croniter(normalized_cron, localized_base)
    next_value = iterator.get_next(datetime)
    if next_value.tzinfo is None:
        next_value = next_value.replace(tzinfo=get_timezone(timezone_name))
    return next_value.astimezone(timezone.utc)


def describe_cron(expression: str) -> str:
    minute, hour, day_of_month, month, day_of_week = normalize_cron_expression(expression).split(" ")

    if minute.startswith("*/") and hour == "*" and day_of_month == "*" and month == "*" and day_of_week == "*":
        return f"Every {minute[2:]} minutes"

    if hour.startswith("*/") and minute.isdigit() and day_of_month == "*" and month == "*" and day_of_week == "*":
        return f"Every {hour[2:]} hours at minute {int(minute):02d}"

    if (
        minute.isdigit()
        and hour.isdigit()
        and day_of_month == "*"
        and month == "*"
        and day_of_week == "*"
    ):
        return f"Every day at {int(hour):02d}:{int(minute):02d}"

    if (
        minute.isdigit()
        and hour.isdigit()
        and day_of_month == "*"
        and month == "*"
        and day_of_week == "1-5"
    ):
        return f"Every weekday at {int(hour):02d}:{int(minute):02d}"

    if (
        minute.isdigit()
        and hour.isdigit()
        and day_of_month == "*"
        and month == "*"
        and day_of_week not in {"*", "1-5"}
    ):
        labels = [
            _WEEKDAY_LABELS.get(part, part)
            for part in day_of_week.split(",")
            if str(part).strip()
        ]
        if labels:
            return f"Every {'/'.join(labels)} at {int(hour):02d}:{int(minute):02d}"

    if (
        minute.isdigit()
        and hour.isdigit()
        and day_of_month.isdigit()
        and month == "*"
        and day_of_week == "*"
    ):
        return f"Day {int(day_of_month)} of every month at {int(hour):02d}:{int(minute):02d}"

    return f"Cron: {expression}"


@dataclass(frozen=True)
class SchedulePreview:
    is_valid: bool
    human_summary: str
    normalized_cron: Optional[str]
    next_occurrences: list[str]


def preview_schedule(
    *,
    schedule_type: str,
    timezone_name: str,
    cron_expression: Optional[str] = None,
    run_at: Any = None,
    count: int = 5,
    now: Optional[datetime] = None,
) -> SchedulePreview:
    effective_timezone = resolve_timezone_name(timezone_name)
    base_now = now or utcnow()
    if base_now.tzinfo is None:
        base_now = base_now.replace(tzinfo=timezone.utc)

    if str(schedule_type).strip().lower() == "once":
        parsed_run_at = parse_run_at(run_at, effective_timezone)
        summary = (
            f"Run once at "
            f"{parsed_run_at.astimezone(get_timezone(effective_timezone)).strftime('%Y-%m-%d %H:%M')}"
            f" ({effective_timezone})"
        )
        return SchedulePreview(
            is_valid=True,
            human_summary=summary,
            normalized_cron=None,
            next_occurrences=[parsed_run_at.isoformat()],
        )

    normalized_cron = normalize_cron_expression(cron_expression)
    croniter = _get_croniter()
    iterator = croniter(normalized_cron, base_now.astimezone(get_timezone(effective_timezone)))
    occurrences: list[str] = []
    for _ in range(max(int(count), 1)):
        item = iterator.get_next(datetime)
        if item.tzinfo is None:
            item = item.replace(tzinfo=get_timezone(effective_timezone))
        occurrences.append(item.astimezone(timezone.utc).isoformat())
    return SchedulePreview(
        is_valid=True,
        human_summary=f"{describe_cron(normalized_cron)} ({effective_timezone})",
        normalized_cron=normalized_cron,
        next_occurrences=occurrences,
    )
