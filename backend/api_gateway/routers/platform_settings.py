"""Platform-level settings endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from access_control.permissions import CurrentUser, get_current_user
from api_gateway.ui_experience import UiExperienceSettings
from database.connection import get_db_session
from shared.platform_settings import get_ui_experience_settings, upsert_ui_experience_settings

router = APIRouter()


def _ensure_platform_settings_access(current_user: CurrentUser) -> None:
    if current_user.role not in {"admin", "manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to manage platform UI settings",
        )


@router.get("/settings/ui-experience", response_model=UiExperienceSettings)
async def get_ui_experience(current_user: CurrentUser = Depends(get_current_user)):
    """Return platform-wide UI experience settings."""
    _ensure_platform_settings_access(current_user)

    with get_db_session() as session:
        return UiExperienceSettings.from_mapping(get_ui_experience_settings(session))


@router.put("/settings/ui-experience", response_model=UiExperienceSettings)
async def update_ui_experience(
    request: UiExperienceSettings,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update platform-wide UI experience settings."""
    _ensure_platform_settings_access(current_user)

    with get_db_session() as session:
        upsert_ui_experience_settings(session, request.dict())
        session.commit()

    return request
