"""Helpers for storing platform-wide settings in the database."""

from typing import Any

from sqlalchemy.orm import Session

from database.models import PlatformSetting

PLATFORM_BOOTSTRAP_SETTINGS_KEY = "platform_bootstrap"


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
