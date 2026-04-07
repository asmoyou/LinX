"""Helpers for storing platform-wide settings in the database."""

from typing import Any

from sqlalchemy.orm import Session

from database.models import PlatformSetting

PLATFORM_BOOTSTRAP_SETTINGS_KEY = "platform_bootstrap"
PLATFORM_UI_EXPERIENCE_SETTINGS_KEY = "ui_experience"
PLATFORM_PROJECT_EXECUTION_SETTINGS_KEY = "project_execution"

MOTION_PREFERENCES = {"auto", "full", "reduced", "off"}
DEFAULT_UI_EXPERIENCE_SETTINGS: dict[str, Any] = {
    "default_motion_preference": "auto",
    "emergency_disable_motion": False,
    "telemetry_sample_rate": 0.2,
}


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default
    if value is None:
        return default
    return bool(value)


def normalize_motion_preference(value: Any, default: str = "auto") -> str:
    candidate = str(value or "").strip().lower()
    if candidate in MOTION_PREFERENCES:
        return candidate
    return default


def clamp_telemetry_sample_rate(value: Any, default: float = 0.2) -> float:
    try:
        candidate = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(candidate, 0.0), 1.0)


def merge_ui_experience_settings(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "default_motion_preference": normalize_motion_preference(
            payload.get("default_motion_preference"),
            default=str(DEFAULT_UI_EXPERIENCE_SETTINGS["default_motion_preference"]),
        ),
        "emergency_disable_motion": _coerce_bool(
            payload.get("emergency_disable_motion"),
            default=bool(DEFAULT_UI_EXPERIENCE_SETTINGS["emergency_disable_motion"]),
        ),
        "telemetry_sample_rate": clamp_telemetry_sample_rate(
            payload.get("telemetry_sample_rate"),
            default=float(DEFAULT_UI_EXPERIENCE_SETTINGS["telemetry_sample_rate"]),
        ),
    }


def get_platform_setting(session: Session, key: str) -> dict[str, Any] | None:
    """Return a copy of the stored JSON value for the given setting key."""
    record = (
        session.query(PlatformSetting)
        .filter(PlatformSetting.setting_key == key)
        .first()
    )
    if not record:
        return None
    if not isinstance(record.setting_value, dict):
        return {}
    return dict(record.setting_value)


def upsert_platform_setting(
    session: Session,
    key: str,
    value: dict[str, Any],
) -> PlatformSetting:
    """Create or replace a platform setting."""
    record = (
        session.query(PlatformSetting)
        .filter(PlatformSetting.setting_key == key)
        .first()
    )
    next_value = dict(value)

    if record is None:
        record = PlatformSetting(setting_key=key, setting_value=next_value)
        session.add(record)
    else:
        record.setting_value = next_value

    session.flush()
    return record


def get_ui_experience_settings(session: Session) -> dict[str, Any]:
    return merge_ui_experience_settings(
        get_platform_setting(session, PLATFORM_UI_EXPERIENCE_SETTINGS_KEY)
    )


def upsert_ui_experience_settings(
    session: Session,
    value: dict[str, Any],
) -> PlatformSetting:
    return upsert_platform_setting(
        session=session,
        key=PLATFORM_UI_EXPERIENCE_SETTINGS_KEY,
        value=merge_ui_experience_settings(value),
    )


DEFAULT_PROJECT_EXECUTION_SETTINGS: dict[str, Any] = {
    "default_launch_command_template": "",
}


def merge_project_execution_settings(value: dict[str, Any] | None) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    legacy_template = str(payload.get("external_agent_command_template") or "").strip()
    return {
        "default_launch_command_template": str(
            payload.get("default_launch_command_template") or legacy_template
        ).strip(),
    }


def get_project_execution_settings(session: Session) -> dict[str, Any]:
    return merge_project_execution_settings(
        get_platform_setting(session, PLATFORM_PROJECT_EXECUTION_SETTINGS_KEY)
    )


def upsert_project_execution_settings(
    session: Session,
    value: dict[str, Any],
) -> PlatformSetting:
    return upsert_platform_setting(
        session=session,
        key=PLATFORM_PROJECT_EXECUTION_SETTINGS_KEY,
        value=merge_project_execution_settings(value),
    )
