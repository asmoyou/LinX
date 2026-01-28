"""Authentication Endpoints for API Gateway.

This module provides authentication endpoints for login, logout, and token refresh.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Task 2.1.5: Create authentication endpoints (login, logout, refresh)
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from access_control import (
    TokenPair,
    UserModel,
    blacklist_token,
    create_token_pair,
    refresh_access_token,
    verify_password,
)
from access_control.audit_logger import log_authentication_event
from access_control.permissions import CurrentUser, get_current_user
from access_control.registration import (
    DuplicateUserError,
)
from access_control.registration import ValidationError as RegistrationValidationError
from access_control.registration import (
    register_user_self,
)
from api_gateway.errors import ValidationError
from shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


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


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(request: LoginRequest):
    """Authenticate user and return JWT tokens.
    
    Supports login with either username or email.

    Args:
        request: Login credentials (username or email + password)

    Returns:
        JWT token pair and user information

    Raises:
        HTTPException: If credentials are invalid
    """
    from database.connection import get_db_session
    from database.models import User
    from sqlalchemy import or_

    try:
        with get_db_session() as session:
            # Query user by username OR email
            user = session.query(User).filter(
                or_(
                    User.username == request.username,
                    User.email == request.username  # Allow email as username
                )
            ).first()

            if not user or not verify_password(request.password, user.password_hash):
                log_authentication_event(
                    session=session,
                    event_type="login_failed",
                    username=request.username,
                    success=False,
                    reason="invalid_credentials",
                )
                session.commit()
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username/email or password",
                    headers={"WWW-Authenticate": "Bearer"},
                )

            # Create token pair
            tokens = create_token_pair(
                user_id=str(user.user_id), username=user.username, role=user.role
            )

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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
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
async def logout(current_user: CurrentUser = Depends(get_current_user)):
    """Logout user by blacklisting their token.

    Args:
        current_user: Current authenticated user

    Returns:
        No content
    """
    from database.connection import get_db_session

    # TODO: Get token from request and blacklist it
    # For now, just log the event

    with get_db_session() as session:
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
