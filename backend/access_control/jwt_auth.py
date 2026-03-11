"""JWT Token Generation and Validation for Access Control System.

This module provides JWT (JSON Web Token) functionality for user authentication
including token generation, validation, and refresh token support.

References:
- Requirements 14: User-Based Access Control
- Requirements 15: API and Integration Layer
- Design Section 8.1: Authentication (JWT-Based Authentication)
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from pydantic import BaseModel, Field

from shared.config import get_config

logger = logging.getLogger(__name__)


class TokenData(BaseModel):
    """Data structure for JWT token payload.

    Attributes:
        user_id: Unique user identifier
        username: Username
        role: User role for RBAC
        token_type: Type of token (access or refresh)
        exp: Expiration timestamp
        iat: Issued at timestamp
        jti: JWT ID for token blacklist support
        session_id: Shared logical session identifier across access/refresh tokens
    """

    user_id: str
    username: str
    role: str
    token_type: str = Field(default="access")  # access or refresh
    exp: Optional[int] = None
    iat: Optional[int] = None
    jti: Optional[str] = None
    session_id: Optional[str] = None


class TokenPair(BaseModel):
    """Access and refresh token pair.

    Attributes:
        access_token: JWT access token
        refresh_token: JWT refresh token
        token_type: Token type (always "bearer")
        expires_in: Access token expiration in seconds
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class JWTAuthenticationError(Exception):
    """Raised when JWT authentication fails."""

    pass


class JWTTokenExpiredError(JWTAuthenticationError):
    """Raised when JWT token has expired."""

    pass


class JWTTokenInvalidError(JWTAuthenticationError):
    """Raised when JWT token is invalid."""

    pass


# Token blacklist for logout support (in-memory for now, should use Redis in production)
_token_blacklist: set = set()
_session_blacklist: set = set()


def get_jwt_config() -> Dict[str, Any]:
    """Get JWT configuration from config file.

    Returns:
        Dictionary containing JWT configuration
    """
    config = get_config()
    return {
        "secret_key": config.get(
            "api.jwt.secret_key", default="dev-secret-key-change-in-production"
        ),
        "algorithm": config.get("api.jwt.algorithm", default="HS256"),
        "access_token_expire_hours": config.get("api.jwt.expiration_hours", default=24),
        "refresh_token_expire_days": config.get("api.jwt.refresh_expiration_days", default=7),
    }


def create_access_token(
    user_id: uuid.UUID,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    session_id: Optional[str] = None,
) -> str:
    """Create a JWT access token.

    Args:
        user_id: User's unique identifier
        username: User's username
        role: User's role for RBAC
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string

    Example:
        >>> token = create_access_token(
        ...     user_id=uuid.uuid4(),
        ...     username="john_doe",
        ...     role="user"
        ... )
        >>> len(token) > 0
        True
    """
    config = get_jwt_config()

    # Set expiration time
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=config["access_token_expire_hours"])

    # Create token payload
    issued_at = datetime.utcnow()
    token_id = str(uuid.uuid4())
    resolved_session_id = session_id or token_id

    payload = {
        "user_id": str(user_id),
        "username": username,
        "role": role,
        "token_type": "access",
        "exp": expire,
        "iat": issued_at,
        "jti": token_id,
        "session_id": resolved_session_id,
    }

    # Encode token
    encoded_jwt = jwt.encode(payload, config["secret_key"], algorithm=config["algorithm"])

    logger.info(
        "Access token created",
        extra={
            "user_id": str(user_id),
            "username": username,
            "role": role,
            "expires_at": expire.isoformat(),
            "jti": token_id,
            "session_id": resolved_session_id,
        },
    )

    return encoded_jwt


def create_refresh_token(
    user_id: uuid.UUID,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
    session_id: Optional[str] = None,
) -> str:
    """Create a JWT refresh token.

    Refresh tokens have longer expiration times and are used to obtain
    new access tokens without requiring re-authentication.

    Args:
        user_id: User's unique identifier
        username: User's username
        role: User's role for RBAC
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT refresh token string
    """
    config = get_jwt_config()

    # Set expiration time (longer than access token)
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=config["refresh_token_expire_days"])

    # Create token payload
    issued_at = datetime.utcnow()
    token_id = str(uuid.uuid4())
    resolved_session_id = session_id or token_id

    payload = {
        "user_id": str(user_id),
        "username": username,
        "role": role,
        "token_type": "refresh",
        "exp": expire,
        "iat": issued_at,
        "jti": token_id,
        "session_id": resolved_session_id,
    }

    # Encode token
    encoded_jwt = jwt.encode(payload, config["secret_key"], algorithm=config["algorithm"])

    logger.info(
        "Refresh token created",
        extra={
            "user_id": str(user_id),
            "username": username,
            "expires_at": expire.isoformat(),
            "jti": token_id,
            "session_id": resolved_session_id,
        },
    )

    return encoded_jwt


def create_token_pair(user_id: uuid.UUID, username: str, role: str) -> TokenPair:
    """Create both access and refresh tokens.

    Args:
        user_id: User's unique identifier
        username: User's username
        role: User's role for RBAC

    Returns:
        TokenPair containing both access and refresh tokens

    Example:
        >>> tokens = create_token_pair(
        ...     user_id=uuid.uuid4(),
        ...     username="john_doe",
        ...     role="user"
        ... )
        >>> tokens.token_type
        'bearer'
    """
    config = get_jwt_config()
    session_id = str(uuid.uuid4())

    access_token = create_access_token(user_id, username, role, session_id=session_id)
    refresh_token = create_refresh_token(user_id, username, role, session_id=session_id)

    expires_in = config["access_token_expire_hours"] * 3600  # Convert to seconds

    return TokenPair(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT token.

    Args:
        token: JWT token string to decode

    Returns:
        TokenData containing the decoded payload

    Raises:
        JWTTokenExpiredError: If token has expired
        JWTTokenInvalidError: If token is invalid or blacklisted

    Example:
        >>> token = create_access_token(uuid.uuid4(), "john", "user")
        >>> data = decode_token(token)
        >>> data.username
        'john'
    """
    config = get_jwt_config()

    try:
        # Decode token
        payload = jwt.decode(token, config["secret_key"], algorithms=[config["algorithm"]])

        # Check if token is blacklisted
        token_id = payload.get("jti")
        session_id = payload.get("session_id") or token_id
        if token_id and token_id in _token_blacklist:
            logger.warning("Attempted to use blacklisted token", extra={"jti": token_id})
            raise JWTTokenInvalidError("Token has been revoked")
        if session_id and session_id in _session_blacklist:
            logger.warning("Attempted to use revoked session", extra={"session_id": session_id})
            raise JWTTokenInvalidError("Session has been revoked")

        # Extract token data
        token_data = TokenData(
            user_id=payload.get("user_id"),
            username=payload.get("username"),
            role=payload.get("role"),
            token_type=payload.get("token_type", "access"),
            exp=payload.get("exp"),
            iat=payload.get("iat"),
            jti=token_id,
            session_id=session_id,
        )

        logger.debug(
            "Token decoded successfully",
            extra={
                "user_id": token_data.user_id,
                "username": token_data.username,
                "token_type": token_data.token_type,
                "session_id": token_data.session_id,
            },
        )

        return token_data

    except jwt.ExpiredSignatureError as e:
        logger.warning("Token has expired", extra={"error": str(e)})
        raise JWTTokenExpiredError("Token has expired") from e

    except JWTError as e:
        logger.warning("Invalid token", extra={"error": str(e)})
        raise JWTTokenInvalidError(f"Invalid token: {str(e)}") from e


def verify_token(token: str, expected_type: str = "access") -> TokenData:
    """Verify a JWT token and check its type.

    Args:
        token: JWT token string to verify
        expected_type: Expected token type ("access" or "refresh")

    Returns:
        TokenData if token is valid

    Raises:
        JWTTokenInvalidError: If token type doesn't match expected type
        JWTTokenExpiredError: If token has expired
    """
    token_data = decode_token(token)

    if token_data.token_type != expected_type:
        raise JWTTokenInvalidError(
            f"Invalid token type. Expected '{expected_type}', got '{token_data.token_type}'"
        )

    return token_data


def refresh_access_token(refresh_token: str) -> str:
    """Generate a new access token using a refresh token.

    Args:
        refresh_token: Valid refresh token

    Returns:
        New access token string

    Raises:
        JWTTokenInvalidError: If refresh token is invalid or wrong type
        JWTTokenExpiredError: If refresh token has expired
    """
    # Verify refresh token
    token_data = verify_token(refresh_token, expected_type="refresh")

    # Create new access token with same user data
    new_access_token = create_access_token(
        user_id=uuid.UUID(token_data.user_id),
        username=token_data.username,
        role=token_data.role,
        session_id=token_data.session_id,
    )

    logger.info(
        "Access token refreshed",
        extra={
            "user_id": token_data.user_id,
            "username": token_data.username,
            "session_id": token_data.session_id,
        },
    )

    return new_access_token


def blacklist_token(token: str) -> None:
    """Add a token to the blacklist (for logout).

    Blacklisted tokens cannot be used even if they haven't expired yet.
    In production, this should use Redis with TTL set to token expiration.

    Args:
        token: JWT token to blacklist

    Raises:
        JWTTokenInvalidError: If token cannot be decoded
    """
    try:
        token_data = decode_token(token)

        if token_data.jti:
            _token_blacklist.add(token_data.jti)

            logger.info(
                "Token blacklisted",
                extra={
                    "jti": token_data.jti,
                    "user_id": token_data.user_id,
                    "username": token_data.username,
                },
            )
    except JWTTokenExpiredError:
        # Already expired tokens don't need to be blacklisted
        logger.debug("Attempted to blacklist expired token")
        pass


def blacklist_token_jti(token_jti: str) -> None:
    """Add a token JTI directly to the blacklist.

    This is used by session management flows where only the session/token ID is known.

    Args:
        token_jti: JWT ID (jti) to blacklist
    """
    if not token_jti:
        return
    _token_blacklist.add(token_jti)
    logger.info("Token JTI blacklisted", extra={"jti": token_jti})


def blacklist_session_id(session_id: str) -> None:
    """Revoke all tokens that belong to the given logical session."""
    if not session_id:
        return

    _session_blacklist.add(session_id)
    logger.info("Session ID blacklisted", extra={"session_id": session_id})


def is_token_blacklisted(token: str) -> bool:
    """Check if a token is blacklisted.

    Args:
        token: JWT token to check

    Returns:
        True if token is blacklisted, False otherwise
    """
    try:
        config = get_jwt_config()
        # Decode without checking blacklist to avoid recursion
        payload = jwt.decode(token, config["secret_key"], algorithms=[config["algorithm"]])
        token_id = payload.get("jti")
        session_id = payload.get("session_id") or token_id
        return bool(
            (token_id and token_id in _token_blacklist)
            or (session_id and session_id in _session_blacklist)
        )
    except (jwt.ExpiredSignatureError, JWTError):
        return False


def clear_blacklist() -> None:
    """Clear the token blacklist.

    This is primarily for testing purposes. In production with Redis,
    tokens would expire naturally based on their TTL.
    """
    _token_blacklist.clear()
    _session_blacklist.clear()
    logger.info("Token blacklist cleared")


def get_token_expiration(token: str) -> Optional[datetime]:
    """Get the expiration time of a token.

    Args:
        token: JWT token string

    Returns:
        Expiration datetime if token is valid, None otherwise
    """
    try:
        token_data = decode_token(token)
        if token_data.exp:
            return datetime.utcfromtimestamp(token_data.exp)
        return None
    except (JWTTokenExpiredError, JWTTokenInvalidError):
        return None


def get_token_remaining_time(token: str) -> Optional[timedelta]:
    """Get the remaining time until token expiration.

    Args:
        token: JWT token string

    Returns:
        Timedelta representing remaining time, None if expired or invalid
    """
    expiration = get_token_expiration(token)
    if expiration:
        remaining = expiration - datetime.utcnow()
        return remaining if remaining.total_seconds() > 0 else None
    return None
