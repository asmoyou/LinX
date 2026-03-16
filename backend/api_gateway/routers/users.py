"""User Management Endpoints for API Gateway.

References:
- Requirements 15: API and Integration Layer
- Task 2.1.6: Create user endpoints
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field

from access_control import blacklist_session_id, blacklist_token_jti
from access_control.permissions import CurrentUser, get_current_user, require_role
from access_control.rbac import Role
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _resolve_user_avatar(attributes: dict, request: Request | None = None) -> dict:
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
            public_endpoint, public_secure = minio_client.resolve_public_endpoint(
                origin_url=request.headers.get("origin") if request else None,
                referer_url=request.headers.get("referer") if request else None,
                forwarded_host=request.headers.get("x-forwarded-host") if request else None,
            )
            avatar_url = minio_client.resolve_avatar_url(
                avatar_ref,
                public_endpoint=public_endpoint,
                public_secure=public_secure,
            )
            if avatar_url:
                result["avatar_url"] = avatar_url
        except Exception as e:
            logger.warning(f"Failed to resolve avatar URL: {e}")

    # Refresh legacy avatar URLs when they still point at MinIO directly.
    legacy_avatar_url = result.get("avatar_url")
    if not avatar_ref and legacy_avatar_url:
        try:
            from object_storage.minio_client import get_minio_client

            minio_client = get_minio_client()
            public_endpoint, public_secure = minio_client.resolve_public_endpoint(
                origin_url=request.headers.get("origin") if request else None,
                referer_url=request.headers.get("referer") if request else None,
                forwarded_host=request.headers.get("x-forwarded-host") if request else None,
            )
            refreshed_avatar_url = minio_client.resolve_avatar_url(
                legacy_avatar_url,
                public_endpoint=public_endpoint,
                public_secure=public_secure,
            )
            if refreshed_avatar_url:
                result["avatar_url"] = refreshed_avatar_url
        except Exception as e:
            logger.warning(f"Failed to refresh legacy avatar URL: {e}")

    return result


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _as_attrs(attributes: dict | None) -> dict[str, Any]:
    """Return a mutable copy of user attributes JSON."""
    if not attributes or not isinstance(attributes, dict):
        return {}
    return dict(attributes)


def _touch_security_session(
    attributes: dict[str, Any],
    current_user: CurrentUser,
    request: Request | None = None,
) -> tuple[dict[str, Any], bool]:
    """Upsert the current JWT session metadata into user attributes."""
    session_id = current_user.session_id
    if not session_id:
        return attributes, False

    sessions = list(attributes.get("security_sessions", []))
    ip_address = request.client.host if request and request.client else None
    user_agent = request.headers.get("user-agent") if request else None
    now = _utc_now_iso()
    updated = False

    next_sessions = []
    found = False
    for item in sessions:
        if item.get("session_id") == session_id:
            found = True
            next_item = dict(item)
            next_item["last_seen_at"] = now
            next_item["user_agent"] = user_agent or next_item.get("user_agent") or "Unknown"
            next_item["ip_address"] = ip_address or next_item.get("ip_address")
            next_sessions.append(next_item)
            updated = True
        else:
            next_sessions.append(item)

    if not found:
        next_sessions.append(
            {
                "session_id": session_id,
                "user_agent": user_agent or "Unknown",
                "ip_address": ip_address,
                "created_at": now,
                "last_seen_at": now,
            }
        )
        updated = True

    next_sessions = sorted(
        next_sessions,
        key=lambda item: item.get("last_seen_at") or item.get("created_at") or "",
        reverse=True,
    )[:20]
    attributes["security_sessions"] = next_sessions
    return attributes, updated


class UserProfile(BaseModel):
    """User profile model."""

    user_id: str
    username: str
    email: str
    role: str
    attributes: dict = None
    display_name: str | None = None  # User's custom display name (optional)


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    current_password: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8)


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


class UserApiKey(BaseModel):
    """User API key metadata (secret value is never returned here)."""

    key_id: str
    name: str
    prefix: str
    created_at: str
    last_used_at: str | None = None


class CreateApiKeyRequest(BaseModel):
    """Create API key request."""

    name: str = Field(..., min_length=1, max_length=100)


class CreateApiKeyResponse(BaseModel):
    """Create API key response (plaintext key is returned once)."""

    key_id: str
    name: str
    key: str
    prefix: str
    created_at: str


class UserSession(BaseModel):
    """User session metadata."""

    session_id: str
    user_agent: str
    ip_address: str | None = None
    created_at: str
    last_seen_at: str
    is_current: bool


class SessionListResponse(BaseModel):
    sessions: list[UserSession]
    total: int


class TwoFactorStatus(BaseModel):
    enabled: bool
    configured_at: str | None = None
    backup_codes_remaining: int = 0
    setup_pending: bool = False


class TwoFactorSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    backup_codes: list[str]


class TwoFactorEnableRequest(BaseModel):
    verification_code: str = Field(..., min_length=6, max_length=6)


class TwoFactorDisableRequest(BaseModel):
    current_password: str = Field(..., min_length=8)


class PrivacySettings(BaseModel):
    profile_visibility: Literal["private", "team", "organization"] = "organization"
    searchable_profile: bool = True
    allow_telemetry: bool = True
    allow_training: bool = False
    data_retention_days: int = Field(default=365, ge=30, le=3650)


class UserDataExportResponse(BaseModel):
    filename: str
    data: dict[str, Any]


class DeleteAccountRequest(BaseModel):
    current_password: str = Field(..., min_length=8)
    confirmation: str = Field(..., min_length=6, max_length=6)


@router.get("/me", response_model=UserProfile)
async def get_current_user_profile(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get current user's profile."""
    try:
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
            resolved_attributes = _resolve_user_avatar(user.attributes, request)

            return UserProfile(
                user_id=str(user.user_id),
                username=user.username,
                email=user.email,
                role=user.role,
                attributes=resolved_attributes,
                display_name=display_name,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to fetch current user profile",
            extra={"user_id": str(current_user.user_id), "error": str(e)},
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User profile service unavailable",
        )


@router.put("/me", response_model=UserProfile)
async def update_current_user_profile(
    request: Request,
    payload: UpdateProfileRequest,
    current_user: CurrentUser = Depends(get_current_user),
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
        if payload.email:
            # Check if email is already taken by another user
            existing = (
                session.query(User)
                .filter(User.email == payload.email, User.user_id != current_user.user_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="Email already in use"
                )
            user.email = payload.email

        # Update display_name if provided
        if payload.display_name is not None:
            # Create new dict to trigger SQLAlchemy update
            if user.attributes is None:
                user.attributes = {"display_name": payload.display_name}
            else:
                new_attributes = dict(user.attributes)
                new_attributes["display_name"] = payload.display_name
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
        resolved_attributes = _resolve_user_avatar(user.attributes, request)

        return UserProfile(
            user_id=str(user.user_id),
            username=user.username,
            email=user.email,
            role=user.role,
            attributes=resolved_attributes,
            display_name=display_name,
        )


@router.put("/me/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    request: ChangePasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Change current user's password. Requires current password verification."""
    from access_control.models import hash_password, verify_password
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        # Verify current password
        if not verify_password(request.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Set new password
        user.password_hash = hash_password(request.new_password)
        session.commit()

        logger.info(
            "User changed password",
            extra={"user_id": str(current_user.user_id)},
        )

        return {"message": "Password changed successfully"}


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
    request: Request,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
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
            },
        )

        # Store avatar reference (not presigned URL) for on-demand URL generation
        avatar_ref = minio_client.create_avatar_reference(bucket_name, object_key)

        # Generate presigned URL for immediate response (valid for 7 days)
        public_endpoint, public_secure = minio_client.resolve_public_endpoint(
            origin_url=request.headers.get("origin"),
            referer_url=request.headers.get("referer"),
            forwarded_host=request.headers.get("x-forwarded-host"),
        )
        avatar_url = minio_client.get_presigned_url(
            bucket_name=bucket_name,
            object_key=object_key,
            expires=timedelta(days=7),
            public_endpoint=public_endpoint,
            public_secure=public_secure,
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


@router.get("/me/api-keys", response_model=list[UserApiKey])
async def list_user_api_keys(current_user: CurrentUser = Depends(get_current_user)):
    """List current user's API key metadata."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        api_keys = list(attrs.get("api_keys", []))

        items = [
            UserApiKey(
                key_id=item.get("key_id", ""),
                name=item.get("name", "API Key"),
                prefix=item.get("prefix", "lxk_***"),
                created_at=item.get("created_at", _utc_now_iso()),
                last_used_at=item.get("last_used_at"),
            )
            for item in api_keys
            if item.get("key_id")
        ]

        return sorted(items, key=lambda item: item.created_at, reverse=True)


@router.post(
    "/me/api-keys", response_model=CreateApiKeyResponse, status_code=status.HTTP_201_CREATED
)
async def create_user_api_key(
    request: CreateApiKeyRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new API key for current user.

    The plaintext key is returned only once.
    """
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    raw_key = f"lxk_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    created_at = _utc_now_iso()
    key_id = str(uuid.uuid4())

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        api_keys = list(attrs.get("api_keys", []))
        api_keys.append(
            {
                "key_id": key_id,
                "name": request.name.strip(),
                "prefix": raw_key[:12],
                "key_hash": key_hash,
                "created_at": created_at,
                "last_used_at": None,
            }
        )

        attrs["api_keys"] = api_keys
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

    logger.info(
        "User API key created", extra={"user_id": str(current_user.user_id), "key_id": key_id}
    )

    return CreateApiKeyResponse(
        key_id=key_id,
        name=request.name.strip(),
        key=raw_key,
        prefix=raw_key[:12],
        created_at=created_at,
    )


@router.delete("/me/api-keys/{key_id}", status_code=status.HTTP_200_OK)
async def delete_user_api_key(key_id: str, current_user: CurrentUser = Depends(get_current_user)):
    """Delete an API key by key_id."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        api_keys = list(attrs.get("api_keys", []))
        next_api_keys = [item for item in api_keys if item.get("key_id") != key_id]
        if len(next_api_keys) == len(api_keys):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

        attrs["api_keys"] = next_api_keys
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

    logger.info(
        "User API key deleted", extra={"user_id": str(current_user.user_id), "key_id": key_id}
    )
    return {"message": "API key deleted"}


@router.get("/me/sessions", response_model=SessionListResponse)
async def list_user_sessions(
    http_request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List current user's active sessions."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        attrs, touched = _touch_security_session(attrs, current_user, http_request)

        revoked_ids = set(attrs.get("revoked_session_ids", []))
        raw_sessions = list(attrs.get("security_sessions", []))
        sessions = [
            item
            for item in raw_sessions
            if item.get("session_id") and item.get("session_id") not in revoked_ids
        ]
        attrs["security_sessions"] = sessions

        if touched or len(raw_sessions) != len(sessions):
            user.attributes = attrs
            flag_modified(user, "attributes")
            session.commit()

        mapped = [
            UserSession(
                session_id=item.get("session_id"),
                user_agent=item.get("user_agent", "Unknown"),
                ip_address=item.get("ip_address"),
                created_at=item.get("created_at", item.get("last_seen_at", _utc_now_iso())),
                last_seen_at=item.get("last_seen_at", item.get("created_at", _utc_now_iso())),
                is_current=item.get("session_id") == current_user.session_id,
            )
            for item in sessions
        ]
        mapped = sorted(mapped, key=lambda item: item.last_seen_at, reverse=True)
        return SessionListResponse(sessions=mapped, total=len(mapped))


@router.post("/me/sessions/revoke-others", status_code=status.HTTP_200_OK)
async def revoke_other_sessions(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Revoke all sessions except the current one."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        sessions = list(attrs.get("security_sessions", []))
        current_id = current_user.session_id
        revoked_ids = set(attrs.get("revoked_session_ids", []))

        next_sessions: list[dict[str, Any]] = []
        revoked_count = 0
        for item in sessions:
            session_id = item.get("session_id")
            if not session_id:
                continue

            if current_id and session_id == current_id:
                next_sessions.append(item)
                continue

            blacklist_session_id(session_id)
            revoked_ids.add(session_id)
            revoked_count += 1

        attrs["security_sessions"] = next_sessions
        attrs["revoked_session_ids"] = list(revoked_ids)[-200:]
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

    logger.info(
        "User revoked other sessions",
        extra={"user_id": str(current_user.user_id), "revoked_count": revoked_count},
    )
    return {"message": "Other sessions revoked", "revoked_count": revoked_count}


@router.delete("/me/sessions/{session_id}", status_code=status.HTTP_200_OK)
async def revoke_user_session(
    session_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Revoke one specific session."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    if session_id == current_user.session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot revoke current session from this endpoint",
        )

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        sessions = list(attrs.get("security_sessions", []))
        next_sessions = [item for item in sessions if item.get("session_id") != session_id]
        if len(next_sessions) == len(sessions):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        revoked_ids = set(attrs.get("revoked_session_ids", []))
        revoked_ids.add(session_id)
        attrs["revoked_session_ids"] = list(revoked_ids)[-200:]
        attrs["security_sessions"] = next_sessions
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

    blacklist_session_id(session_id)
    logger.info(
        "User session revoked",
        extra={"user_id": str(current_user.user_id), "session_id": session_id},
    )
    return {"message": "Session revoked"}


@router.get("/me/two-factor", response_model=TwoFactorStatus)
async def get_two_factor_status(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user's two-factor authentication status."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        two_factor = dict(attrs.get("two_factor", {}))
        return TwoFactorStatus(
            enabled=bool(two_factor.get("enabled", False)),
            configured_at=two_factor.get("configured_at"),
            backup_codes_remaining=len(two_factor.get("backup_codes", [])),
            setup_pending=bool(two_factor.get("pending_secret")),
        )


@router.post(
    "/me/two-factor/setup", response_model=TwoFactorSetupResponse, status_code=status.HTTP_200_OK
)
async def setup_two_factor(current_user: CurrentUser = Depends(get_current_user)):
    """Create a pending two-factor setup payload."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    secret = secrets.token_hex(10).upper()
    backup_codes = [f"{secrets.randbelow(10**8):08d}" for _ in range(8)]

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        two_factor = dict(attrs.get("two_factor", {}))
        if two_factor.get("enabled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-factor authentication is already enabled",
            )

        two_factor["pending_secret"] = secret
        two_factor["pending_backup_codes"] = backup_codes
        attrs["two_factor"] = two_factor
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

        otpauth_uri = f"otpauth://totp/LinX:{user.email}?secret={secret}&issuer=LinX"
        return TwoFactorSetupResponse(
            secret=secret,
            otpauth_uri=otpauth_uri,
            backup_codes=backup_codes,
        )


@router.post(
    "/me/two-factor/enable", response_model=TwoFactorStatus, status_code=status.HTTP_200_OK
)
async def enable_two_factor(
    request: TwoFactorEnableRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Enable two-factor authentication after verification."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    if not request.verification_code.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code"
        )

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        two_factor = dict(attrs.get("two_factor", {}))
        pending_secret = two_factor.get("pending_secret")
        pending_backup_codes = list(two_factor.get("pending_backup_codes", []))
        if not pending_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="No pending 2FA setup found"
            )

        two_factor["enabled"] = True
        two_factor["secret"] = pending_secret
        two_factor["backup_codes"] = pending_backup_codes
        two_factor["configured_at"] = _utc_now_iso()
        two_factor.pop("pending_secret", None)
        two_factor.pop("pending_backup_codes", None)

        attrs["two_factor"] = two_factor
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

        return TwoFactorStatus(
            enabled=True,
            configured_at=two_factor.get("configured_at"),
            backup_codes_remaining=len(two_factor.get("backup_codes", [])),
            setup_pending=False,
        )


@router.post(
    "/me/two-factor/disable", response_model=TwoFactorStatus, status_code=status.HTTP_200_OK
)
async def disable_two_factor(
    request: TwoFactorDisableRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Disable two-factor authentication."""
    from access_control.models import verify_password
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if not verify_password(request.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
            )

        attrs = _as_attrs(user.attributes)
        two_factor = dict(attrs.get("two_factor", {}))
        if not two_factor.get("enabled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Two-factor authentication is not enabled",
            )

        two_factor["enabled"] = False
        two_factor["disabled_at"] = _utc_now_iso()
        two_factor.pop("secret", None)
        two_factor.pop("backup_codes", None)
        two_factor.pop("pending_secret", None)
        two_factor.pop("pending_backup_codes", None)

        attrs["two_factor"] = two_factor
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

        return TwoFactorStatus(enabled=False, configured_at=two_factor.get("configured_at"))


@router.get("/me/privacy", response_model=PrivacySettings)
async def get_privacy_settings(current_user: CurrentUser = Depends(get_current_user)):
    """Get current user's privacy settings."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        privacy = dict(attrs.get("privacy", {}))
        return PrivacySettings(
            profile_visibility=privacy.get("profile_visibility", "organization"),
            searchable_profile=privacy.get("searchable_profile", True),
            allow_telemetry=privacy.get("allow_telemetry", True),
            allow_training=privacy.get("allow_training", False),
            data_retention_days=privacy.get("data_retention_days", 365),
        )


@router.put("/me/privacy", response_model=PrivacySettings)
async def update_privacy_settings(
    request: PrivacySettings,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update current user's privacy settings."""
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy.orm.attributes import flag_modified

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        attrs = _as_attrs(user.attributes)
        attrs["privacy"] = request.dict()
        user.attributes = attrs
        flag_modified(user, "attributes")
        session.commit()

        return request


@router.post(
    "/me/privacy/export", response_model=UserDataExportResponse, status_code=status.HTTP_200_OK
)
async def export_user_data(current_user: CurrentUser = Depends(get_current_user)):
    """Export user data for GDPR/data portability workflows."""
    from database.connection import get_db_session
    from database.models import (
        Agent,
        KnowledgeItem,
        ResourceQuota as ResourceQuotaModel,
        Task,
        User,
        UserMemoryEntry,
    )
    from sqlalchemy import func

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        user_id_str = str(user.user_id)
        attrs = _as_attrs(user.attributes)
        preferences = dict(attrs.get("preferences", {}))
        privacy = dict(attrs.get("privacy", {}))
        two_factor = dict(attrs.get("two_factor", {}))
        api_keys = [
            {
                "key_id": item.get("key_id"),
                "name": item.get("name"),
                "prefix": item.get("prefix"),
                "created_at": item.get("created_at"),
                "last_used_at": item.get("last_used_at"),
            }
            for item in list(attrs.get("api_keys", []))
        ]

        quota = (
            session.query(ResourceQuotaModel)
            .filter(ResourceQuotaModel.user_id == current_user.user_id)
            .first()
        )
        quota_data = (
            {
                "max_agents": quota.max_agents,
                "max_storage_gb": quota.max_storage_gb,
                "max_cpu_cores": quota.max_cpu_cores,
                "max_memory_gb": quota.max_memory_gb,
                "current_agents": quota.current_agents,
                "current_storage_gb": float(quota.current_storage_gb),
            }
            if quota
            else {}
        )

        agents_count = (
            session.query(func.count(Agent.agent_id))
            .filter(Agent.owner_user_id == current_user.user_id)
            .scalar()
            or 0
        )
        tasks_count = (
            session.query(func.count(Task.task_id))
            .filter(Task.created_by_user_id == current_user.user_id)
            .scalar()
            or 0
        )
        knowledge_count = (
            session.query(func.count(KnowledgeItem.knowledge_id))
            .filter(KnowledgeItem.owner_user_id == current_user.user_id)
            .scalar()
            or 0
        )
        memory_count = (
            session.query(func.count(UserMemoryEntry.id))
            .filter(UserMemoryEntry.user_id == user_id_str)
            .scalar()
            or 0
        )

        export_data = {
            "generated_at": _utc_now_iso(),
            "user_profile": {
                "user_id": user_id_str,
                "username": user.username,
                "email": user.email,
                "role": user.role,
                "display_name": attrs.get("display_name"),
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            },
            "preferences": preferences,
            "privacy_settings": {
                "profile_visibility": privacy.get("profile_visibility", "organization"),
                "searchable_profile": privacy.get("searchable_profile", True),
                "allow_telemetry": privacy.get("allow_telemetry", True),
                "allow_training": privacy.get("allow_training", False),
                "data_retention_days": privacy.get("data_retention_days", 365),
            },
            "security": {
                "two_factor_enabled": bool(two_factor.get("enabled", False)),
                "api_keys": api_keys,
            },
            "resource_quota": quota_data,
            "usage_summary": {
                "agents_count": agents_count,
                "tasks_count": tasks_count,
                "knowledge_items_count": knowledge_count,
                "user_memory_entries_count": memory_count,
            },
        }

        timestamp = _utc_now().strftime("%Y%m%dT%H%M%SZ")
        filename = f"linx-user-export-{user.username}-{timestamp}.json"
        return UserDataExportResponse(filename=filename, data=export_data)


@router.delete("/me", status_code=status.HTTP_200_OK)
async def delete_current_user_account(
    request: DeleteAccountRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete current user account and associated data."""
    from access_control.models import verify_password
    from database.connection import get_db_session
    from database.models import User

    if request.confirmation != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid delete confirmation",
        )

    user_memory_cleanup = None
    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if not verify_password(request.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        from user_memory.storage_cleanup import prepare_user_memory_rows_for_user_deletion

        user_memory_cleanup = prepare_user_memory_rows_for_user_deletion(
            session,
            user_id=str(current_user.user_id),
        )

        session.delete(user)
        session.commit()

    entry_ids = list((user_memory_cleanup or {}).get("entry_ids") or [])
    if entry_ids:
        try:
            from user_memory.storage_cleanup import delete_user_memory_entry_vectors

            delete_user_memory_entry_vectors(entry_ids)
        except Exception as exc:
            logger.warning(
                "Failed to delete legacy user-memory vectors after account deletion: %s",
                exc,
                extra={
                    "user_id": str(current_user.user_id),
                    "entry_count": len(entry_ids),
                },
            )

    if current_user.token_jti:
        blacklist_token_jti(current_user.token_jti)
    if current_user.session_id:
        blacklist_session_id(current_user.session_id)

    logger.warning(
        "User account deleted",
        extra={
            "user_id": str(current_user.user_id),
            "user_memory_entries_deleted": len(entry_ids),
            "user_memory_views_deleted": (user_memory_cleanup or {}).get("memory_views"),
            "skill_proposals_deleted": (user_memory_cleanup or {}).get("skill_proposals"),
            "session_ledgers_deleted": (user_memory_cleanup or {}).get("session_ledgers"),
        },
    )
    return {"message": "Account deleted"}
