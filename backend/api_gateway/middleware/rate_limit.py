"""Rate Limiting Middleware for API Gateway.

This middleware implements rate limiting to prevent API abuse using a
sliding window algorithm with in-memory storage (should use Redis in production).

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Task 2.1.3: Implement rate limiting middleware
"""

import time
from collections import defaultdict, deque
from typing import Callable, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from shared.config import get_config
from shared.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Sliding window rate limiter using in-memory storage.

    In production, this should use Redis for distributed rate limiting.
    """

    def __init__(self, requests_per_minute: int = 60, window_size: int = 60):
        """Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests allowed per minute
            window_size: Time window in seconds
        """
        self.requests_per_minute = requests_per_minute
        self.window_size = window_size
        # Store request timestamps per client: {client_id: deque([timestamp, ...])}
        self.requests: Dict[str, deque] = defaultdict(lambda: deque())

    def is_allowed(self, client_id: str) -> Tuple[bool, int]:
        """Check if request is allowed for client.

        Args:
            client_id: Client identifier (user_id or IP address)

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        current_time = time.time()
        window_start = current_time - self.window_size

        # Get client's request history
        client_requests = self.requests[client_id]

        # Remove requests outside the current window
        while client_requests and client_requests[0] < window_start:
            client_requests.popleft()

        # Check if limit exceeded
        if len(client_requests) >= self.requests_per_minute:
            remaining = 0
            return False, remaining

        # Add current request
        client_requests.append(current_time)

        remaining = self.requests_per_minute - len(client_requests)
        return True, remaining

    def get_retry_after(self, client_id: str) -> int:
        """Get seconds until client can make another request.

        Args:
            client_id: Client identifier

        Returns:
            Seconds until next request allowed
        """
        client_requests = self.requests[client_id]
        if not client_requests:
            return 0

        oldest_request = client_requests[0]
        current_time = time.time()
        window_start = current_time - self.window_size

        if oldest_request < window_start:
            return 0

        return int(oldest_request + self.window_size - current_time) + 1


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting on API requests."""

    def __init__(self, app, requests_per_minute: int = None):
        """Initialize rate limit middleware.

        Args:
            app: FastAPI application
            requests_per_minute: Override default rate limit
        """
        super().__init__(app)

        # Load configuration
        config = get_config()
        if requests_per_minute is None:
            requests_per_minute = config.get("api.rate_limit.requests_per_minute", default=60)

        self.rate_limiter = RateLimiter(requests_per_minute=requests_per_minute)

        logger.info("Rate limiting initialized", extra={"requests_per_minute": requests_per_minute})

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request and enforce rate limiting.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware or route handler

        Returns:
            HTTP response
        """
        # Get client identifier (user_id if authenticated, otherwise IP)
        client_id = self._get_client_id(request)

        # Check rate limit
        is_allowed, remaining = self.rate_limiter.is_allowed(client_id)

        if not is_allowed:
            retry_after = self.rate_limiter.get_retry_after(client_id)

            logger.warning(
                "Rate limit exceeded",
                extra={
                    "client_id": client_id,
                    "path": request.url.path,
                    "method": request.method,
                    "retry_after": retry_after,
                },
            )

            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "error": "too_many_requests",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.rate_limiter.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)

        return response

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting.

        Args:
            request: HTTP request

        Returns:
            Client identifier (user_id or IP address)
        """
        # Use user_id if authenticated
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"

        # Otherwise use IP address
        client_ip = request.client.host if request.client else "unknown"

        # Check for forwarded IP (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()

        return f"ip:{client_ip}"
