"""Error Handling for API Gateway.

This module provides structured error responses and exception handlers.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Task 2.1.12: Implement error handling with structured responses
"""

from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from access_control.permissions import PermissionDeniedError
from shared.logging import get_logger

logger = get_logger(__name__)


class APIError(Exception):
    """Base exception for API errors."""
    
    def __init__(
        self,
        message: str,
        error_code: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Dict[str, Any] = None
    ):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class ResourceNotFoundError(APIError):
    """Raised when a requested resource is not found."""
    
    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            error_code="resource_not_found",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"resource_type": resource_type, "resource_id": resource_id}
        )


class ValidationError(APIError):
    """Raised when request validation fails."""
    
    def __init__(self, message: str, field: str = None):
        details = {"field": field} if field else {}
        super().__init__(
            message=message,
            error_code="validation_error",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details
        )


class ConflictError(APIError):
    """Raised when a resource conflict occurs."""
    
    def __init__(self, message: str):
        super().__init__(
            message=message,
            error_code="conflict",
            status_code=status.HTTP_409_CONFLICT
        )


def create_error_response(
    message: str,
    error_code: str,
    status_code: int,
    details: Dict[str, Any] = None
) -> JSONResponse:
    """Create a structured error response.
    
    Args:
        message: Human-readable error message
        error_code: Machine-readable error code
        status_code: HTTP status code
        details: Optional additional error details
        
    Returns:
        JSONResponse with structured error
    """
    content = {
        "error": error_code,
        "message": message,
    }
    
    if details:
        content["details"] = details
    
    return JSONResponse(
        status_code=status_code,
        content=content
    )


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """Handle APIError exceptions.
    
    Args:
        request: HTTP request
        exc: APIError exception
        
    Returns:
        Structured error response
    """
    logger.warning(
        f"API error: {exc.message}",
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "details": exc.details,
            "path": request.url.path,
            "method": request.method,
        }
    )
    
    return create_error_response(
        message=exc.message,
        error_code=exc.error_code,
        status_code=exc.status_code,
        details=exc.details
    )


async def permission_denied_handler(
    request: Request,
    exc: PermissionDeniedError
) -> JSONResponse:
    """Handle PermissionDeniedError exceptions.
    
    Args:
        request: HTTP request
        exc: PermissionDeniedError exception
        
    Returns:
        Structured error response
    """
    logger.warning(
        f"Permission denied: {exc.message}",
        extra={
            "user_id": exc.user_id,
            "resource_type": exc.resource_type,
            "action": exc.action,
            "path": request.url.path,
            "method": request.method,
        }
    )
    
    return create_error_response(
        message=exc.message,
        error_code="permission_denied",
        status_code=status.HTTP_403_FORBIDDEN,
        details={
            "resource_type": exc.resource_type,
            "action": exc.action,
        }
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
) -> JSONResponse:
    """Handle HTTP exceptions.
    
    Args:
        request: HTTP request
        exc: HTTP exception
        
    Returns:
        Structured error response
    """
    logger.warning(
        f"HTTP exception: {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
        }
    )
    
    return create_error_response(
        message=str(exc.detail),
        error_code="http_error",
        status_code=exc.status_code
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """Handle request validation errors.
    
    Args:
        request: HTTP request
        exc: Validation error
        
    Returns:
        Structured error response
    """
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        })
    
    logger.warning(
        "Request validation failed",
        extra={
            "errors": errors,
            "path": request.url.path,
            "method": request.method,
        }
    )
    
    return create_error_response(
        message="Request validation failed",
        error_code="validation_error",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors}
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions.
    
    Args:
        request: HTTP request
        exc: Exception
        
    Returns:
        Structured error response
    """
    logger.error(
        f"Unexpected error: {str(exc)}",
        extra={
            "error_type": type(exc).__name__,
            "path": request.url.path,
            "method": request.method,
        },
        exc_info=True
    )
    
    return create_error_response(
        message="An unexpected error occurred",
        error_code="internal_server_error",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
    )


def setup_error_handlers(app: FastAPI) -> None:
    """Setup error handlers for the FastAPI application.
    
    Args:
        app: FastAPI application instance
    """
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(PermissionDeniedError, permission_denied_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("Error handlers configured")
