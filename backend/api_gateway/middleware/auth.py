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

from access_control.jwt_auth import decode_token, JWTTokenExpiredError, JWTTokenInvalidError
from shared.logging import get_logger

logger = get_logger(__name__)

# Public endpoints that don't require authentication
PUBLIC_ENDPOINTS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
    "/api/v1/auth/refresh",
}


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
                extra={"path": request.url.path, "method": request.method}
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Missing authentication credentials",
                    "error": "unauthorized"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Validate Bearer token format
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(
                "Invalid Authorization header format",
                extra={"path": request.url.path, "method": request.method}
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid authentication credentials format",
                    "error": "unauthorized"
                },
                headers={"WWW-Authenticate": "Bearer"},
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
                }
            )
            
            # Continue to next middleware/handler
            return await call_next(request)
            
        except JWTTokenExpiredError:
            logger.warning(
                "Expired token",
                extra={"path": request.url.path, "method": request.method}
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Token has expired",
                    "error": "token_expired"
                },
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        except JWTTokenInvalidError as e:
            logger.warning(
                "Invalid token",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "error": str(e)
                }
            )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid authentication credentials",
                    "error": "invalid_token"
                },
                headers={"WWW-Authenticate": "Bearer"},
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
