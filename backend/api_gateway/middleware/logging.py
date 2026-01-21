"""Request Logging Middleware for API Gateway.

This middleware logs all API requests with timing, status codes, and correlation IDs.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Task 2.1.4: Add request logging middleware
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from shared.logging import clear_correlation_id, get_logger, set_correlation_id

logger = get_logger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log all API requests with timing and correlation IDs."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and log details.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            HTTP response
        """
        # Generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = f"req-{uuid.uuid4().hex[:16]}"

        # Set correlation ID for logging context
        set_correlation_id(correlation_id)

        # Get user info if authenticated
        user_id = getattr(request.state, "user_id", None)
        username = getattr(request.state, "username", None)

        # Record start time
        start_time = time.time()

        # Log request
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "event_type": "request_started",
                "http_method": request.method,
                "http_path": request.url.path,
                "http_query": str(request.url.query) if request.url.query else None,
                "user_id": user_id,
                "username": username,
                "client_ip": request.client.host if request.client else None,
                "user_agent": request.headers.get("User-Agent"),
            },
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Add correlation ID to response headers
            response.headers["X-Correlation-ID"] = correlation_id

            # Log response
            logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                extra={
                    "event_type": "request_completed",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "user_id": user_id,
                    "username": username,
                },
            )

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "event_type": "request_failed",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "user_id": user_id,
                    "username": username,
                },
                exc_info=True,
            )

            raise

        finally:
            # Clear correlation ID
            clear_correlation_id()
