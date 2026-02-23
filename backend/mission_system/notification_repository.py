"""Notification repository for persisted user notifications.

This module provides CRUD helpers for the user notification center.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from sqlalchemy import desc

from database.connection import get_db_session
from database.mission_models import UserNotification


def create_user_notification(
    *,
    user_id: UUID,
    notification_type: str,
    severity: str,
    title: str,
    message: str,
    mission_id: Optional[UUID] = None,
    action_url: Optional[str] = None,
    action_label: Optional[str] = None,
    notification_metadata: Optional[Dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> UserNotification:
    """Create a new user notification."""
    with get_db_session() as session:
        notification = UserNotification(
            notification_id=uuid4(),
            user_id=user_id,
            mission_id=mission_id,
            notification_type=notification_type,
            severity=severity,
            title=title,
            message=message,
            action_url=action_url,
            action_label=action_label,
            notification_metadata=notification_metadata or {},
            dedupe_key=dedupe_key,
            is_read=False,
        )
        session.add(notification)
        session.flush()
        session.refresh(notification)
        session.expunge(notification)
        return notification


def list_user_notifications(
    *,
    user_id: UUID,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[UserNotification], int, int]:
    """List notifications for a user with pagination.

    Returns:
        tuple: (items, total_count, unread_count)
    """
    with get_db_session() as session:
        base_query = session.query(UserNotification).filter(UserNotification.user_id == user_id)
        if unread_only:
            base_query = base_query.filter(UserNotification.is_read.is_(False))

        items = (
            base_query.order_by(desc(UserNotification.created_at)).offset(offset).limit(limit).all()
        )
        total = base_query.count()
        unread_count = (
            session.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.is_read.is_(False),
            )
            .count()
        )
        for item in items:
            session.expunge(item)
        return items, total, unread_count


def get_user_notification(
    *,
    user_id: UUID,
    notification_id: UUID,
) -> Optional[UserNotification]:
    """Get a single notification owned by the given user."""
    with get_db_session() as session:
        item = (
            session.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.notification_id == notification_id,
            )
            .first()
        )
        if item:
            session.expunge(item)
        return item


def mark_user_notification_read(
    *,
    user_id: UUID,
    notification_id: UUID,
) -> Optional[UserNotification]:
    """Mark a notification as read and return updated record."""
    with get_db_session() as session:
        item = (
            session.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.notification_id == notification_id,
            )
            .first()
        )
        if item is None:
            return None
        if not item.is_read:
            item.is_read = True
            item.read_at = datetime.utcnow()
        session.flush()
        session.refresh(item)
        session.expunge(item)
        return item


def mark_all_user_notifications_read(*, user_id: UUID) -> int:
    """Mark all unread notifications as read for a user."""
    with get_db_session() as session:
        unread_items = (
            session.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.is_read.is_(False),
            )
            .all()
        )
        if not unread_items:
            return 0

        now = datetime.utcnow()
        for item in unread_items:
            item.is_read = True
            item.read_at = now
        session.flush()
        return len(unread_items)


def delete_user_notification(*, user_id: UUID, notification_id: UUID) -> bool:
    """Delete a single notification owned by a user."""
    with get_db_session() as session:
        item = (
            session.query(UserNotification)
            .filter(
                UserNotification.user_id == user_id,
                UserNotification.notification_id == notification_id,
            )
            .first()
        )
        if item is None:
            return False
        session.delete(item)
        return True


def clear_user_notifications(*, user_id: UUID, scope: str = "read") -> int:
    """Clear notifications for a user.

    Args:
        user_id: Owner user id.
        scope: "read" clears read notifications only; "all" clears all notifications.
    """
    if scope not in {"read", "all"}:
        raise ValueError("scope must be either 'read' or 'all'")

    with get_db_session() as session:
        query = session.query(UserNotification).filter(UserNotification.user_id == user_id)
        if scope == "read":
            query = query.filter(UserNotification.is_read.is_(True))
        items = query.all()
        if not items:
            return 0
        deleted_count = len(items)
        for item in items:
            session.delete(item)
        return deleted_count
