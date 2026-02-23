"""Notification center API endpoints."""

from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from access_control.permissions import CurrentUser, get_current_user

router = APIRouter()


class NotificationResponse(BaseModel):
    notification_id: UUID
    user_id: UUID
    mission_id: Optional[UUID] = None
    notification_type: str
    severity: str
    title: str
    message: str
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    notification_metadata: Optional[Dict[str, Any]] = None
    is_read: bool
    read_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    total: int
    unread_count: int


class MarkAllReadResponse(BaseModel):
    updated: int


class ClearNotificationsResponse(BaseModel):
    deleted: int


def _notification_to_response(notification) -> NotificationResponse:
    return NotificationResponse(
        notification_id=notification.notification_id,
        user_id=notification.user_id,
        mission_id=notification.mission_id,
        notification_type=notification.notification_type,
        severity=notification.severity,
        title=notification.title,
        message=notification.message,
        action_url=notification.action_url,
        action_label=notification.action_label,
        notification_metadata=notification.notification_metadata,
        is_read=bool(notification.is_read),
        read_at=str(notification.read_at) if notification.read_at else None,
        created_at=str(notification.created_at) if notification.created_at else None,
        updated_at=str(notification.updated_at) if notification.updated_at else None,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    status_filter: Literal["all", "unread"] = Query(default="all", alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List current user's notifications."""
    from mission_system.notification_repository import list_user_notifications

    notifications, total, unread_count = list_user_notifications(
        user_id=UUID(current_user.user_id),
        unread_only=status_filter == "unread",
        limit=limit,
        offset=offset,
    )
    return NotificationListResponse(
        items=[_notification_to_response(item) for item in notifications],
        total=total,
        unread_count=unread_count,
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(
    notification_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark a notification as read."""
    from mission_system.notification_repository import mark_user_notification_read

    item = mark_user_notification_read(
        user_id=UUID(current_user.user_id),
        notification_id=notification_id,
    )
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return _notification_to_response(item)


@router.post("/read-all", response_model=MarkAllReadResponse)
async def mark_all_notifications_read(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Mark all unread notifications as read."""
    from mission_system.notification_repository import mark_all_user_notifications_read

    updated = mark_all_user_notifications_read(user_id=UUID(current_user.user_id))
    return MarkAllReadResponse(updated=updated)


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete one notification."""
    from mission_system.notification_repository import delete_user_notification

    deleted = delete_user_notification(
        user_id=UUID(current_user.user_id),
        notification_id=notification_id,
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    return None


@router.delete("", response_model=ClearNotificationsResponse)
async def clear_notifications(
    scope: Literal["read", "all"] = Query(default="read"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Clear notifications for current user."""
    from mission_system.notification_repository import clear_user_notifications

    deleted = clear_user_notifications(
        user_id=UUID(current_user.user_id),
        scope=scope,
    )
    return ClearNotificationsResponse(deleted=deleted)
