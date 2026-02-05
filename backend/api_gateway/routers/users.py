"""User Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.6: Create user endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile
from pydantic import BaseModel

from access_control.permissions import CurrentUser, get_current_user, require_role
from access_control.rbac import Role
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _resolve_user_avatar(attributes: dict) -> dict:
    """
    Resolve avatar reference in user attributes to a presigned URL.

    Args:
        attributes: User attributes dict

    Returns:
        New attributes dict with avatar_url resolved from avatar_ref
    """
    if not attributes or not isinstance(attributes, dict):
        return attributes or {}

    result = dict(attributes)

    # Check for avatar_ref (new format)
    avatar_ref = result.get("avatar_ref")
    if avatar_ref:
        try:
            from object_storage.minio_client import get_minio_client
            minio_client = get_minio_client()
            avatar_url = minio_client.resolve_avatar_url(avatar_ref)
            if avatar_url:
                result["avatar_url"] = avatar_url
        except Exception as e:
            logger.warning(f"Failed to resolve avatar URL: {e}")

    # Also handle legacy avatar_url (might be expired presigned URL)
    # If there's no avatar_ref but there is avatar_url, keep it (backward compat)

    return result


class UserProfile(BaseModel):
    """User profile model."""

    user_id: str
    username: str
    email: str
    role: str
    attributes: dict = None
    display_name: str | None = None  # User's custom display name (optional)


class UpdateProfileRequest(BaseModel):
    """Update profile request."""

    email: str = None
    display_name: str = None  # User's custom display name


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
    max_cpu_cores: int
    max_memory_gb: int
    current_agents: int
    current_storage_gb: float


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user's profile."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Safely get display_name from attributes
        display_name = None
        if user.attributes and isinstance(user.attributes, dict):
            display_name = user.attributes.get("display_name")

        # Resolve avatar reference to presigned URL
        resolved_attributes = _resolve_user_avatar(user.attributes)

        return UserProfile(
            user_id=str(user.user_id),
            username=user.username,
            email=user.email,
            role=user.role,
            attributes=resolved_attributes,
            display_name=display_name,
        )


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    request: UpdateProfileRequest, current_user: CurrentUser = Depends(get_current_user)
):
    """Update current user's profile."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Update email if provided
        if request.email:
            # Check if email is already taken by another user
            existing = (
                session.query(User)
                .filter(User.email == request.email, User.user_id != current_user.user_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use"
                )
            user.email = request.email

        # Update display_name if provided
        if request.display_name is not None:
            # Create new dict to trigger SQLAlchemy update
            if user.attributes is None:
                user.attributes = {"display_name": request.display_name}
            else:
                new_attributes = dict(user.attributes)
                new_attributes["display_name"] = request.display_name
                user.attributes = new_attributes
            
            flag_modified(user, "attributes")

        session.commit()
        session.refresh(user)

        logger.info(
            "User profile updated",
            extra={"user_id": str(current_user.user_id), "email": user.email},
        )

        # Safely get display_name from attributes
        display_name = None
        if user.attributes and isinstance(user.attributes, dict):
            display_name = user.attributes.get("display_name")

        # Resolve avatar reference to presigned URL
        resolved_attributes = _resolve_user_avatar(user.attributes)

        return UserProfile(
            user_id=str(user.user_id),
            username=user.username,
            email=user.email,
            role=user.role,
            attributes=resolved_attributes,
            display_name=display_name,
        )


@router.get("/me/quotas", response_model=ResourceQuota)
async def get_current_user_quotas(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user's resource quotas."""
    from database.connection import get_db_session
    from database.models import ResourceQuota as ResourceQuotaModel

    with get_db_session() as session:
        quota = (
            session.query(ResourceQuotaModel)
            .filter(ResourceQuotaModel.user_id == current_user.user_id)
            .first()
        )

        if not quota:
            # Create default quota if not exists
            quota = ResourceQuotaModel(
                user_id=current_user.user_id,
                max_agents=10,
                max_storage_gb=100,
                max_cpu_cores=10,
                max_memory_gb=20,
                current_agents=0,
                current_storage_gb=0.0,
            )
            session.add(quota)
            session.commit()
            session.refresh(quota)

        return ResourceQuota(
            max_agents=quota.max_agents,
            max_storage_gb=quota.max_storage_gb,
            max_cpu_cores=quota.max_cpu_cores,
            max_memory_gb=quota.max_memory_gb,
            current_agents=quota.current_agents,
            current_storage_gb=float(quota.current_storage_gb),
        )


@router.get("/{user_id}/quotas", response_model=ResourceQuota)
@require_role([Role.ADMIN, Role.MANAGER])
async def get_user_quotas(user_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Get user's resource quotas (admin/manager only)."""
    from database.connection import get_db_session
    from database.models import ResourceQuota as ResourceQuotaModel
    from uuid import UUID

    try:
        user_uuid = UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user ID")

    with get_db_session() as session:
        quota = (
            session.query(ResourceQuotaModel)
            .filter(ResourceQuotaModel.user_id == user_uuid)
            .first()
        )

        if not quota:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User quotas not found"
            )

        return ResourceQuota(
            max_agents=quota.max_agents,
            max_storage_gb=quota.max_storage_gb,
            max_cpu_cores=quota.max_cpu_cores,
            max_memory_gb=quota.max_memory_gb,
            current_agents=quota.current_agents,
            current_storage_gb=float(quota.current_storage_gb),
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
        # IMPORTANT: For JSONB fields, we need to create a new dict to trigger SQLAlchemy update
        if user.attributes is None:
            user.attributes = {"preferences": preferences.dict()}
        else:
            # Create a new dict to ensure SQLAlchemy detects the change
            new_attributes = dict(user.attributes)
            new_attributes["preferences"] = preferences.dict()
            user.attributes = new_attributes
        
        # Mark the field as modified
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, "attributes")
        
        session.commit()
        
        logger.info(
            "User preferences updated",
            extra={"user_id": str(current_user.user_id), "preferences": preferences.dict()},
        )
        
        return preferences


@router.post("/me/avatar", status_code=status.HTTP_200_OK)
async def upload_user_avatar(
    file: UploadFile = File(...), current_user: CurrentUser = Depends(get_current_user)
):
    """Upload user avatar image to MinIO."""
    from database.connection import get_db_session
    from database.models import User
    from object_storage.minio_client import get_minio_client
    from sqlalchemy.orm.attributes import flag_modified
    from datetime import timedelta
    import io

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp"]
    if not file.content_type or file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
        )

    # Validate file size (max 5MB)
    file_data = await file.read()
    if len(file_data) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="File size must be less than 5MB"
        )

    try:
        # Upload to MinIO
        file_stream = io.BytesIO(file_data)
        minio_client = get_minio_client()
        
        bucket_name, object_key = minio_client.upload_file(
            bucket_type="images",
            file_data=file_stream,
            filename=f"avatar_{current_user.user_id}.webp",
            user_id=current_user.user_id,
            task_id=None,
            agent_id=None,
            content_type=file.content_type,
            metadata={
                "user_id": current_user.user_id,
                "type": "user_avatar",
            }
        )

        # Store avatar reference (not presigned URL) for on-demand URL generation
        avatar_ref = minio_client.create_avatar_reference(bucket_name, object_key)

        # Generate presigned URL for immediate response (valid for 7 days)
        avatar_url = minio_client.get_presigned_url(
            bucket_name=bucket_name,
            object_key=object_key,
            expires=timedelta(days=7)
        )

        # Update user avatar reference in database (store ref, not URL)
        with get_db_session() as session:
            user = session.query(User).filter(User.user_id == current_user.user_id).first()
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

            # Update avatar reference in attributes
            if user.attributes is None:
                user.attributes = {"avatar_ref": avatar_ref}
            else:
                new_attributes = dict(user.attributes)
                new_attributes["avatar_ref"] = avatar_ref
                # Remove legacy avatar_url if present
                new_attributes.pop("avatar_url", None)
                user.attributes = new_attributes

            flag_modified(user, "attributes")
            session.commit()
            session.refresh(user)

            logger.info(
                "User avatar uploaded to MinIO",
                extra={
                    "user_id": str(current_user.user_id),
                    "bucket": bucket_name,
                    "key": object_key,
                },
            )

        return {
            "avatar_url": avatar_url,
            "bucket": bucket_name,
            "key": object_key,
        }
        
    except Exception as e:
        logger.error(f"Failed to upload avatar: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload avatar: {str(e)}",
        )
