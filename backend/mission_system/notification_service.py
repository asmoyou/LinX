"""Notification service.

Transforms mission events into persisted user notifications.
"""

from typing import Any, Dict, Optional
from uuid import UUID

from mission_system.mission_repository import get_mission
from mission_system.notification_repository import create_user_notification


def _safe_text(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _extract_error_message(data: Optional[Dict[str, Any]], message: Optional[str]) -> str:
    payload = data or {}
    for key in ("error", "summary", "reason"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(message, str) and message.strip():
        return message.strip()
    return "任务执行出现异常，请查看详情。"


def _extract_clarification_message(data: Optional[Dict[str, Any]], message: Optional[str]) -> str:
    payload = data or {}
    questions = payload.get("questions")
    if isinstance(questions, str) and questions.strip():
        return questions.strip()
    if isinstance(message, str) and message.strip():
        return message.strip()
    return "任务需要进一步澄清，请回复后继续执行。"


def create_notifications_for_mission_event(
    *,
    event_id: UUID,
    mission_id: UUID,
    event_type: str,
    data: Optional[Dict[str, Any]] = None,
    message: Optional[str] = None,
) -> None:
    """Create user notifications for mission events that matter to operators."""
    event_type_normalized = str(event_type or "").strip()
    if not event_type_normalized:
        return
    if event_type_normalized not in {
        "USER_CLARIFICATION_REQUESTED",
        "clarification_request",
        "MISSION_FAILED",
        "MISSION_COMPLETED",
        "QA_VERDICT",
    }:
        return

    event_payload = data or {}
    if (
        event_type_normalized == "QA_VERDICT"
        and _safe_text(event_payload.get("verdict")).upper() != "FAIL"
    ):
        return

    mission = get_mission(mission_id)
    if mission is None:
        return

    owner_user_id = mission.created_by_user_id
    mission_title = _safe_text(mission.title, fallback=f"任务 {str(mission_id)[:8]}")
    mission_short_id = str(mission_id)[:8]
    base_action_url = f"/tasks?missionId={mission_id}"
    dedupe_key = f"mission-event:{event_id}"

    if event_type_normalized in {"USER_CLARIFICATION_REQUESTED", "clarification_request"}:
        create_user_notification(
            user_id=owner_user_id,
            mission_id=mission_id,
            notification_type="mission_clarification_required",
            severity="warning",
            title=f"{mission_title} 需要澄清",
            message=_extract_clarification_message(event_payload, message),
            action_url=f"{base_action_url}&focus=clarification",
            action_label="去处理",
            notification_metadata={
                "mission_id": str(mission_id),
                "mission_short_id": mission_short_id,
                "event_id": str(event_id),
                "event_type": event_type_normalized,
            },
            dedupe_key=dedupe_key,
        )
        return

    if event_type_normalized == "MISSION_FAILED":
        create_user_notification(
            user_id=owner_user_id,
            mission_id=mission_id,
            notification_type="mission_failed",
            severity="error",
            title=f"{mission_title} 执行失败",
            message=_extract_error_message(event_payload, message),
            action_url=base_action_url,
            action_label="查看详情",
            notification_metadata={
                "mission_id": str(mission_id),
                "mission_short_id": mission_short_id,
                "event_id": str(event_id),
                "event_type": event_type_normalized,
            },
            dedupe_key=dedupe_key,
        )
        return

    if event_type_normalized == "MISSION_COMPLETED":
        create_user_notification(
            user_id=owner_user_id,
            mission_id=mission_id,
            notification_type="mission_completed",
            severity="success",
            title=f"{mission_title} 已完成",
            message=_safe_text(message, fallback="任务已完成，可查看交付物。"),
            action_url=base_action_url,
            action_label="查看交付物",
            notification_metadata={
                "mission_id": str(mission_id),
                "mission_short_id": mission_short_id,
                "event_id": str(event_id),
                "event_type": event_type_normalized,
            },
            dedupe_key=dedupe_key,
        )
        return

    if (
        event_type_normalized == "QA_VERDICT"
        and _safe_text(event_payload.get("verdict")).upper() == "FAIL"
    ):
        create_user_notification(
            user_id=owner_user_id,
            mission_id=mission_id,
            notification_type="mission_qa_failed",
            severity="warning",
            title=f"{mission_title} QA 未通过",
            message=_extract_error_message(event_payload, message),
            action_url=base_action_url,
            action_label="查看详情",
            notification_metadata={
                "mission_id": str(mission_id),
                "mission_short_id": mission_short_id,
                "event_id": str(event_id),
                "event_type": event_type_normalized,
                "verdict": _safe_text(event_payload.get("verdict")),
            },
            dedupe_key=dedupe_key,
        )
