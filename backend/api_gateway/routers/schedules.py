"""Agent schedule management endpoints."""

from __future__ import annotations

from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user
from agent_scheduling.cron_utils import ScheduleValidationError
from agent_scheduling.service import (
    ScheduleAccessError,
    ScheduleNotFoundError,
    build_schedule_created_event,
    create_schedule,
    delete_schedule,
    get_schedule_detail,
    list_schedule_runs,
    list_schedules,
    pause_schedule,
    preview_schedule_payload,
    resume_schedule,
    run_schedule_now,
    update_schedule,
)

router = APIRouter()


class ScheduleRunResponse(BaseModel):
    id: str
    scheduleId: str
    scheduledFor: Optional[str] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    status: str
    skipReason: Optional[str] = None
    errorMessage: Optional[str] = None
    assistantMessageId: Optional[str] = None
    conversationId: Optional[str] = None
    deliveryChannel: str
    createdAt: Optional[str] = None


class AgentScheduleResponse(BaseModel):
    id: str
    ownerUserId: str
    ownerUsername: Optional[str] = None
    agentId: str
    agentName: Optional[str] = None
    boundConversationId: str
    boundConversationTitle: Optional[str] = None
    boundConversationSource: Optional[str] = None
    name: str
    promptTemplate: str
    scheduleType: str
    cronExpression: Optional[str] = None
    runAtUtc: Optional[str] = None
    timezone: str
    status: str
    createdVia: str
    originSurface: str
    originMessageId: Optional[str] = None
    nextRunAt: Optional[str] = None
    lastRunAt: Optional[str] = None
    lastRunStatus: Optional[str] = None
    lastError: Optional[str] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None
    latestRun: Optional[ScheduleRunResponse] = None


class ScheduleListResponse(BaseModel):
    items: List[AgentScheduleResponse]
    total: int


class ScheduleRunListResponse(BaseModel):
    items: List[ScheduleRunResponse]
    total: int


class SchedulePreviewRequest(BaseModel):
    scheduleType: Literal["once", "recurring"]
    timezone: str = Field(..., min_length=1, max_length=100)
    cronExpression: Optional[str] = Field(default=None, max_length=100)
    runAt: Optional[str] = None


class SchedulePreviewResponse(BaseModel):
    is_valid: bool
    human_summary: str
    normalized_cron: Optional[str] = None
    next_occurrences: List[str]


class CreateScheduleRequest(BaseModel):
    agentId: str
    name: str = Field(..., min_length=1, max_length=255)
    promptTemplate: str = Field(..., min_length=1, max_length=10000)
    scheduleType: Literal["once", "recurring"]
    cronExpression: Optional[str] = Field(default=None, max_length=100)
    runAt: Optional[str] = None
    timezone: Optional[str] = Field(default=None, max_length=100)


class UpdateScheduleRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    promptTemplate: Optional[str] = Field(default=None, min_length=1, max_length=10000)
    scheduleType: Optional[Literal["once", "recurring"]] = None
    cronExpression: Optional[str] = Field(default=None, max_length=100)
    runAt: Optional[str] = None
    timezone: Optional[str] = Field(default=None, max_length=100)


class ScheduleCreatedEventResponse(BaseModel):
    schedule_id: str
    agent_id: str
    name: str
    status: str
    next_run_at: Optional[str] = None
    timezone: str
    created_via: str
    bound_conversation_id: str
    bound_conversation_title: Optional[str] = None
    origin_surface: str


class ScheduleCreateResponse(BaseModel):
    schedule: AgentScheduleResponse
    createdEvent: ScheduleCreatedEventResponse


def _translate_schedule_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ScheduleValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    if isinstance(exc, ScheduleAccessError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, ScheduleNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/preview", response_model=SchedulePreviewResponse)
async def preview_schedule_config(payload: SchedulePreviewRequest):
    try:
        return preview_schedule_payload(
            schedule_type=payload.scheduleType,
            timezone_name=payload.timezone,
            cron_expression=payload.cronExpression,
            run_at=payload.runAt,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.get("", response_model=ScheduleListResponse)
async def list_agent_schedules(
    scope: Literal["mine", "all"] = Query(default="mine"),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    schedule_type: Optional[str] = Query(default=None, alias="type"),
    created_via: Optional[str] = Query(default=None, alias="createdVia"),
    agent_id: Optional[str] = Query(default=None, alias="agentId"),
    query_text: Optional[str] = Query(default=None, alias="query"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        items, total = list_schedules(
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
            scope=scope,
            status_filter=status_filter,
            schedule_type=schedule_type,
            created_via=created_via,
            agent_id=agent_id,
            query_text=query_text,
            limit=limit,
            offset=offset,
        )
        return ScheduleListResponse(items=items, total=total)
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.post("", response_model=ScheduleCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_agent_schedule(
    payload: CreateScheduleRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        schedule_payload = create_schedule(
            owner_user_id=current_user.user_id,
            owner_role=current_user.role,
            agent_id=payload.agentId,
            name=payload.name,
            prompt_template=payload.promptTemplate,
            schedule_type=payload.scheduleType,
            cron_expression=payload.cronExpression,
            run_at=payload.runAt,
            timezone=payload.timezone,
            created_via="manual_ui",
            origin_surface="schedule_page",
            bound_conversation_id=None,
            origin_message_id=None,
        )
        return ScheduleCreateResponse(
            schedule=schedule_payload,
            createdEvent=build_schedule_created_event(schedule_payload),
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.get("/{schedule_id}", response_model=AgentScheduleResponse)
async def get_agent_schedule(
    schedule_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        payload = get_schedule_detail(
            schedule_id=schedule_id,
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
        )
        return AgentScheduleResponse(**payload)
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.patch("/{schedule_id}", response_model=AgentScheduleResponse)
async def patch_agent_schedule(
    schedule_id: str,
    payload: UpdateScheduleRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    if not any(value is not None for value in payload.model_dump().values()):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided",
        )
    try:
        updated = update_schedule(
            schedule_id=schedule_id,
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
            name=payload.name,
            prompt_template=payload.promptTemplate,
            schedule_type=payload.scheduleType,
            cron_expression=payload.cronExpression,
            run_at=payload.runAt,
            timezone=payload.timezone,
        )
        return AgentScheduleResponse(**updated)
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_agent_schedule(
    schedule_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        delete_schedule(
            schedule_id=schedule_id,
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
        )
        return None
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.post("/{schedule_id}/pause", response_model=AgentScheduleResponse)
async def pause_agent_schedule(
    schedule_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        payload = pause_schedule(
            schedule_id=schedule_id,
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
        )
        return AgentScheduleResponse(**payload)
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.post("/{schedule_id}/resume", response_model=AgentScheduleResponse)
async def resume_agent_schedule(
    schedule_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        payload = resume_schedule(
            schedule_id=schedule_id,
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
        )
        return AgentScheduleResponse(**payload)
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.post("/{schedule_id}/run-now", response_model=ScheduleRunResponse)
async def run_agent_schedule_now(
    schedule_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        payload = run_schedule_now(
            schedule_id=schedule_id,
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
        )
        return ScheduleRunResponse(**payload)
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc


@router.get("/{schedule_id}/runs", response_model=ScheduleRunListResponse)
async def list_agent_schedule_runs(
    schedule_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    try:
        items, total = list_schedule_runs(
            schedule_id=schedule_id,
            viewer_user_id=current_user.user_id,
            viewer_role=current_user.role,
            limit=limit,
            offset=offset,
        )
        return ScheduleRunListResponse(items=items, total=total)
    except Exception as exc:  # noqa: BLE001
        raise _translate_schedule_error(exc) from exc
