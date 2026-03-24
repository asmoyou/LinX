"""Authentication Endpoints for API Gateway.

This module provides authentication endpoints for login, logout, and token refresh.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Task 2.1.5: Create authentication endpoints (login, logout, refresh)
"""

import re
import unicodedata
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from access_control import (
    blacklist_session_id,
    blacklist_token,
    create_token_pair,
    decode_token,
    refresh_access_token,
    verify_password,
    verify_token,
)
from access_control.audit_logger import log_authentication_event
from access_control.permissions import CurrentUser, ensure_session_not_revoked, get_current_user
from access_control.registration import (
    DuplicateUserError,
)
from access_control.registration import ValidationError as RegistrationValidationError
from access_control.registration import (
    register_user_admin,
    register_user_self,
)
from shared.logging import get_logger
from shared.platform_settings import (
    PLATFORM_BOOTSTRAP_SETTINGS_KEY,
    get_platform_setting,
    upsert_platform_setting,
)

logger = get_logger(__name__)

router = APIRouter()

DEFAULT_BOOTSTRAP_ADMIN_USERNAME = "admin"
DEFAULT_PLATFORM_LANGUAGE = "zh"
DEFAULT_PLATFORM_THEME = "system"


def _append_login_session(
    attributes: dict[str, Any] | None,
    session_id: str,
    user_agent: str | None,
    ip_address: str | None,
) -> dict[str, Any]:
    """Record the current login session metadata in user attributes."""
    next_attrs: dict[str, Any] = dict(attributes or {})
    sessions = list(next_attrs.get("security_sessions", []))
    now = datetime.now(timezone.utc).isoformat()

    sessions = [item for item in sessions if item.get("session_id") != session_id]
    sessions.append(
        {
            "session_id": session_id,
            "user_agent": user_agent or "Unknown",
            "ip_address": ip_address,
            "created_at": now,
            "last_seen_at": now,
        }
    )
    sessions = sorted(sessions, key=lambda item: item.get("last_seen_at", ""), reverse=True)[:20]
    next_attrs["security_sessions"] = sessions
    return next_attrs


def _revoke_login_session(
    attributes: dict[str, Any] | None, session_id: str | None
) -> dict[str, Any]:
    """Remove a login session from active session metadata and mark it revoked."""
    next_attrs: dict[str, Any] = dict(attributes or {})
    if not session_id:
        return next_attrs

    sessions = list(next_attrs.get("security_sessions", []))
    revoked_ids = set(next_attrs.get("revoked_session_ids", []))
    next_attrs["security_sessions"] = [
        item for item in sessions if item.get("session_id") != session_id
    ]
    revoked_ids.add(session_id)
    next_attrs["revoked_session_ids"] = list(revoked_ids)[-200:]
    return next_attrs


class LoginRequest(BaseModel):
    """Login request model."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)


class LoginResponse(BaseModel):
    """Login response model."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict


class RefreshRequest(BaseModel):
    """Token refresh request model."""

    refresh_token: str


class RegisterRequest(BaseModel):
    """User registration request model for API."""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(..., min_length=8)
    attributes: Optional[dict] = None


class RegisterResponse(BaseModel):
    """User registration response model for API."""

    user_id: str
    username: str
    email: str
    role: str
    attributes: Optional[dict] = None
    resource_quotas: dict
    created_at: str


class RefreshResponse(BaseModel):
    """Token refresh response model."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class SetupStatusResponse(BaseModel):
    """Public platform setup state."""

    requires_setup: bool
    has_admin_account: bool
    default_admin_username: str = DEFAULT_BOOTSTRAP_ADMIN_USERNAME
    initialized_at: str | None = None
    organization_name: str | None = None
    language: str | None = None
    timezone: str | None = None


class InitializePlatformRequest(BaseModel):
    """First-run platform initialization request."""

    email: str = Field(..., pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(..., min_length=8)
    organization_name: str = Field(..., min_length=1, max_length=100)
    language: Literal["zh", "en"] = DEFAULT_PLATFORM_LANGUAGE
    timezone: str = Field(..., min_length=1, max_length=100)
    theme: Literal["light", "dark", "system"] = DEFAULT_PLATFORM_THEME


def _has_admin_account(session) -> bool:
    """Return whether at least one administrator exists."""
    from database.models import User

    return session.query(User.user_id).filter(User.role == "admin").first() is not None


def _validate_timezone_name(timezone_name: str) -> str:
    """Validate an IANA timezone name."""
    candidate = (timezone_name or "").strip()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Timezone is required",
        )

    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid timezone",
        ) from exc

    return candidate


def _validate_organization_name(organization_name: str) -> str:
    """Validate and normalize the initial organization name."""
    candidate = (organization_name or "").strip()
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Organization name is required",
        )

    return candidate


def _slugify_department_code(name: str) -> str:
    """Build a safe department code from a display name."""
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    return (slug or "root")[:50].rstrip("_") or "root"


def _build_unique_department_code(session, organization_name: str) -> str:
    """Generate a unique department code for the setup root department."""
    from database.models import Department

    base_code = _slugify_department_code(organization_name)
    candidate = base_code
    suffix = 1

    while (
        session.query(Department.department_id).filter(Department.code == candidate).first()
        is not None
    ):
        suffix += 1
        suffix_text = f"_{suffix}"
        candidate = f"{base_code[: 50 - len(suffix_text)]}{suffix_text}"

    return candidate


def _create_root_department(session, organization_name: str, manager_id):
    """Create the initial root department during first-run setup."""
    from database.models import Department

    department = Department(
        name=organization_name,
        code=_build_unique_department_code(session, organization_name),
        description="Initial organization root created during platform setup.",
        manager_id=manager_id,
    )
    session.add(department)
    session.flush()
    return department


def _build_setup_status(session) -> SetupStatusResponse:
    """Build the public platform setup status payload."""
    has_admin_account = _has_admin_account(session)
    bootstrap_settings = get_platform_setting(session, PLATFORM_BOOTSTRAP_SETTINGS_KEY) or {}

    return SetupStatusResponse(
        requires_setup=not has_admin_account,
        has_admin_account=has_admin_account,
        default_admin_username=bootstrap_settings.get(
            "default_admin_username", DEFAULT_BOOTSTRAP_ADMIN_USERNAME
        ),
        initialized_at=bootstrap_settings.get("initialized_at"),
        organization_name=bootstrap_settings.get("organization_name"),
        language=bootstrap_settings.get("language"),
        timezone=bootstrap_settings.get("timezone"),
    )


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, http_request: Request):
    """Authenticate user and return JWT tokens.

    Supports login with either username or email.

    Args:
        payload: Login credentials (username or email + password)
        http_request: HTTP request context

    Returns:
        JWT token pair and user information

    Raises:
        HTTPException: If credentials are invalid
    """
    from sqlalchemy import or_
    from sqlalchemy.orm.attributes import flag_modified

    from database.connection import get_db_session
    from database.models import User

    try:
        with get_db_session() as session:
            # Query user by username OR email
            user = (
                session.query(User)
                .filter(
                    or_(
                        User.username == payload.username,
                        User.email == payload.username,  # Allow email as username
                    )
                )
                .first()
            )

            if not user or not verify_password(payload.password, user.password_hash):
                log_authentication_event(
                    session=session,
                    event_type="login_failed",
                    username=payload.username,
                    success=False,
                    reason="invalid_credentials",
                )
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username/email or password",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Check if user is disabled
            attrs = user.attributes or {}
            if attrs.get("is_disabled", False):
                log_authentication_event(
                    session=session,
                    event_type="login_failed",
                    username=payload.username,
                    user_id=str(user.user_id),
                    success=False,
                    reason="account_disabled",
                )
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is disabled. Contact administrator.",
                )

            # Create token pair
            tokens = create_token_pair(
                user_id=str(user.user_id), username=user.username, role=user.role
            )
            token_data = decode_token(tokens.access_token)
            session_id = token_data.session_id or token_data.jti

            if session_id:
                user.attributes = _append_login_session(
                    user.attributes,
                    session_id=session_id,
                    user_agent=http_request.headers.get("user-agent"),
                    ip_address=http_request.client.host if http_request.client else None,
                )
                flag_modified(user, "attributes")

            log_authentication_event(
                session=session,
                event_type="login_success",
                user_id=str(user.user_id),
                username=user.username,
                success=True,
            )
            session.commit()

            logger.info(
                "User logged in", extra={"user_id": str(user.user_id), "username": user.username}
            )

            return LoginResponse(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_type=tokens.token_type,
                expires_in=tokens.expires_in,
                user={
                    "user_id": str(user.user_id),
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                },
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed. Please try again.",
        )


@router.get("/setup/status", response_model=SetupStatusResponse, status_code=status.HTTP_200_OK)
async def get_setup_status():
    """Return whether the platform still needs first-run initialization."""
    from database.connection import get_db_session

    with get_db_session() as session:
        return _build_setup_status(session)


@router.post("/setup/initialize", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
async def initialize_platform(request: InitializePlatformRequest, http_request: Request):
    """Create the first administrator account and persist bootstrap settings."""
    from sqlalchemy.orm.attributes import flag_modified

    from database.connection import get_db_session
    from database.models import User

    organization_name = _validate_organization_name(request.organization_name)
    timezone_name = _validate_timezone_name(request.timezone)
    initialized_at = datetime.now(timezone.utc).isoformat()
    attributes = {
        "created_by": "setup_wizard",
        "bootstrap": {
            "source": "web_setup",
            "initialized_at": initialized_at,
            "organization_name": organization_name,
        },
        "preferences": {
            "language": request.language,
            "theme": request.theme,
            "timezone": timezone_name,
            "sidebar_collapsed": False,
            "dashboard_layout": "default",
            "notifications_enabled": True,
            "sound_enabled": False,
            "auto_refresh": True,
            "refresh_interval": 30,
        },
    }

    try:
        with get_db_session() as session:
            if _has_admin_account(session):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Platform has already been initialized",
                )

            registration = register_user_admin(
                session=session,
                username=DEFAULT_BOOTSTRAP_ADMIN_USERNAME,
                email=request.email,
                password=request.password,
                role="admin",
                attributes=attributes,
                resource_quotas={
                    "max_agents": 100,
                    "max_storage_gb": 1000,
                    "max_cpu_cores": 50,
                    "max_memory_gb": 100,
                },
            )

            user = (
                session.query(User)
                .filter(User.username == DEFAULT_BOOTSTRAP_ADMIN_USERNAME)
                .first()
            )
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to create administrator account",
                )

            root_department = _create_root_department(
                session=session,
                organization_name=organization_name,
                manager_id=user.user_id,
            )
            user.department_id = root_department.department_id

            upsert_platform_setting(
                session=session,
                key=PLATFORM_BOOTSTRAP_SETTINGS_KEY,
                value={
                    "initialized_at": initialized_at,
                    "default_admin_username": DEFAULT_BOOTSTRAP_ADMIN_USERNAME,
                    "admin_user_id": registration.user_id,
                    "organization_name": organization_name,
                    "root_department_id": str(root_department.department_id),
                    "language": request.language,
                    "timezone": timezone_name,
                    "theme": request.theme,
                },
            )

            tokens = create_token_pair(
                user_id=str(user.user_id),
                username=user.username,
                role=user.role,
            )
            token_data = decode_token(tokens.access_token)
            session_id = token_data.session_id or token_data.jti
            if session_id:
                user.attributes = _append_login_session(
                    user.attributes,
                    session_id=session_id,
                    user_agent=http_request.headers.get("user-agent"),
                    ip_address=http_request.client.host if http_request.client else None,
                )
                flag_modified(user, "attributes")

            log_authentication_event(
                session=session,
                event_type="login_success",
                user_id=str(user.user_id),
                username=user.username,
                success=True,
            )
            session.commit()

            logger.info(
                "Platform initialized",
                extra={
                    "user_id": str(user.user_id),
                    "username": user.username,
                    "organization_name": organization_name,
                    "department_id": str(root_department.department_id),
                    "language": request.language,
                    "timezone": timezone_name,
                },
            )

            return LoginResponse(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                token_type=tokens.token_type,
                expires_in=tokens.expires_in,
                user={
                    "user_id": str(user.user_id),
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                },
            )

    except HTTPException:
        raise
    except DuplicateUserError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except RegistrationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.error(f"Platform initialization error: {str(exc)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Platform initialization failed. Please try again.",
        ) from exc


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest):
    """Register a new user account.

    Args:
        request: Registration information

    Returns:
        Registration response with user information

    Raises:
        HTTPException: If registration fails
    """
    from database.connection import get_db_session

    try:
        with get_db_session() as session:
            response = register_user_self(
                session=session,
                username=request.username,
                email=request.email,
                password=request.password,
                attributes=request.attributes,
            )
            session.commit()

        logger.info(
            "User registered", extra={"user_id": response.user_id, "username": response.username}
        )

        # Convert dataclass to Pydantic model
        return RegisterResponse(
            user_id=response.user_id,
            username=response.username,
            email=response.email,
            role=response.role,
            attributes=response.attributes,
            resource_quotas=response.resource_quotas,
            created_at=response.created_at,
        )

    except DuplicateUserError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except RegistrationValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
    except Exception as e:
        logger.error(f"Registration error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed. Please try again.",
        )


@router.post("/refresh", response_model=RefreshResponse, status_code=status.HTTP_200_OK)
async def refresh(request: RefreshRequest):
    """Refresh access token using refresh token.

    Args:
        request: Refresh token

    Returns:
        New access token

    Raises:
        HTTPException: If refresh token is invalid or expired
    """
    try:
        token_data = verify_token(request.refresh_token, expected_type="refresh")
        ensure_session_not_revoked(token_data.user_id, token_data.session_id)
        new_access_token = refresh_access_token(request.refresh_token)

        # Get token expiration from config
        from shared.config import get_config

        config = get_config()
        expires_in = config.get("api.jwt.expiration_hours", default=24) * 3600

        logger.info("Access token refreshed")

        return RefreshResponse(
            access_token=new_access_token, token_type="bearer", expires_in=expires_in
        )

    except Exception as e:
        logger.warning(f"Token refresh failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    http_request: Request,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Logout user by blacklisting their token.

    Args:
        current_user: Current authenticated user

    Returns:
        No content
    """
    from sqlalchemy.orm.attributes import flag_modified

    from database.connection import get_db_session
    from database.models import User

    # Best effort token blacklist (immediate invalidation for current process)
    auth_header = http_request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            blacklist_token(token)
    if current_user.session_id:
        blacklist_session_id(current_user.session_id)

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == current_user.user_id).first()
        if user:
            user.attributes = _revoke_login_session(user.attributes, current_user.session_id)
            flag_modified(user, "attributes")

        log_authentication_event(
            session=session,
            event_type="logout",
            user_id=current_user.user_id,
            username=current_user.username,
            success=True,
        )
        session.commit()

    logger.info(
        "User logged out",
        extra={"user_id": current_user.user_id, "username": current_user.username},
    )

    return None
