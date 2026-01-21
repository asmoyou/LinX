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
