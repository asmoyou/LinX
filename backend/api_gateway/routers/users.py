"""User Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.6: Create user endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from access_control.permissions import CurrentUser, get_current_user, require_role
from access_control.rbac import Role
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class UserProfile(BaseModel):
    """User profile model."""

    user_id: str
    username: str
    email: str
    role: str


class UpdateProfileRequest(BaseModel):
    """Update profile request."""

    email: str = None


class UserPreferences(BaseModel):
    """User preferences model."""

    language: str = "zh"  # 'en' or 'zh'
    theme: str = "system"  # 'light', 'dark', or 'system'
    sidebar_collapsed: bool = False
    dashboard_layout: str = "default"  # 'default', 'compact', or 'detailed'
    notifications_enabled: bool = True
    sound_enabled: bool = False
    auto_refresh: bool = True
    refresh_interval: int = 30  # in seconds


class ResourceQuota(BaseModel):
    """Resource quota model."""

    max_agents: int
    max_storage_gb: int
    current_agents: int
    current_storage_gb: float


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user's profile."""
    # TODO: Query from database
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Requires database integration"
    )


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    request: UpdateProfileRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """Update current user's profile."""
    # TODO: Update in database
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Requires database integration"
    )


@router.get("/{user_id}/quotas", response_model=ResourceQuota)
@require_role([Role.ADMIN, Role.MANAGER])
async def get_user_quotas(user_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get user's resource quotas (admin/manager only)."""
    # TODO: Query from database
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Requires database integration"
    )


@router.get("/me/preferences", response_model=UserPreferences)
async def get_user_preferences(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user's preferences."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Get preferences from attributes JSONB field
        preferences = user.attributes.get("preferences", {}) if user.attributes else {}
        
        # Return with defaults for missing fields
        return UserPreferences(
            language=preferences.get("language", "zh"),
            theme=preferences.get("theme", "system"),
            sidebar_collapsed=preferences.get("sidebar_collapsed", False),
            dashboard_layout=preferences.get("dashboard_layout", "default"),
            notifications_enabled=preferences.get("notifications_enabled", True),
            sound_enabled=preferences.get("sound_enabled", False),
            auto_refresh=preferences.get("auto_refresh", True),
            refresh_interval=preferences.get("refresh_interval", 30),
        )


@router.put("/me/preferences", response_model=UserPreferences)
async def update_user_preferences(
    preferences: UserPreferences, current_user: CurrentUser = Depends(get_current_user)
):
    """Update current user's preferences."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Update preferences in attributes JSONB field
        if user.attributes is None:
            user.attributes = {}
        
        user.attributes["preferences"] = preferences.dict()
        session.commit()
        
        logger.info(
            "User preferences updated",
            extra={"user_id": str(current_user.user_id), "preferences": preferences.dict()},
        )
        
        return preferences
