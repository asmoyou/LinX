"""JWT Authentication Middleware for API Gateway.

This middleware validates JWT tokens for protected endpoints and adds user
information to the request state.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Task 2.1.2: Implement JWT authentication middleware
"""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from access_control.jwt_auth import JWTTokenExpiredError, JWTTokenInvalidError, decode_token
from shared.logging import get_logger

logger = get_logger(__name__)

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = {
    "/",
    "/health",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
}


def create_auth_error_response(
    message: str, error_code: str, status_code: int = 401
) -> JSONResponse:
    """Create a structured authentication error response.

    Args:
        message: Human-readable error message
        error_code: Machine-readable error code
        status_code: HTTP status code

    Returns:
        JSONResponse with structured error
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_code,
            "message": message,
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to validate JWT tokens and add user info to request state."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and validate JWT token if required.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            HTTP response
        """
        # Check if endpoint is public
        if self._is_public_endpoint(request.url.path):
            return await call_next(request)

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")

        if not auth_header:
            logger.warning(
                "Missing Authorization header",
                extra={"path": request.url.path, "method": request.method},
            )
            return create_auth_error_response(
                message="Missing authentication credentials", error_code="missing_credentials"
            )

        # Validate Bearer token format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(
                "Invalid Authorization header format",
                extra={"path": request.url.path, "method": request.method},
            )
            return create_auth_error_response(
                message="Invalid authentication credentials format", error_code="invalid_format"
            )

        token = parts[1]

        # Validate token
        try:
            token_data = decode_token(token)

            # Add user info to request state
            request.state.user_id = token_data.user_id
            request.state.username = token_data.username
            request.state.user_role = token_data.role
            request.state.token_jti = token_data.jti

            logger.debug(
                "Request authenticated",
                extra={
                    "user_id": token_data.user_id,
                    "username": token_data.username,
                    "path": request.url.path,
                    "method": request.method,
                },
            )

            # Continue to next middleware/handler
            return await call_next(request)

        except JWTTokenExpiredError:
            logger.warning(
                "Expired token", extra={"path": request.url.path, "method": request.method}
            )
            return create_auth_error_response(
                message="Token has expired", error_code="token_expired"
            )

        except JWTTokenInvalidError as e:
            logger.warning(
                "Invalid token",
                extra={"path": request.url.path, "method": request.method, "error": str(e)},
            )
            return create_auth_error_response(
                message="Invalid authentication credentials", error_code="invalid_token"
            )

    def _is_public_endpoint(self, path: str) -> bool:
        """Check if endpoint is public (doesn't require authentication).

        Args:
            path: Request path

        Returns:
            True if endpoint is public, False otherwise
        """
        # Exact match
        if path in PUBLIC_ENDPOINTS:
            return True

        # Prefix match for public paths
        public_prefixes = ["/docs", "/redoc", "/openapi.json"]
        for prefix in public_prefixes:
            if path.startswith(prefix):
                return True

        return False
