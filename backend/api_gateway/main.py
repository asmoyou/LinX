"""FastAPI Application - API Gateway for Digital Workforce Platform.

This module implements the main FastAPI application serving as the API Gateway
for the platform, providing RESTful endpoints and WebSocket support.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
- Task 2.1.1: Create FastAPI application with CORS configuration
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.config import get_config
from shared.logging import setup_logging, get_logger
from api_gateway.middleware.auth import JWTAuthMiddleware
from api_gateway.middleware.rate_limit import RateLimitMiddleware
from api_gateway.middleware.logging import RequestLoggingMiddleware
from api_gateway.routers import auth, users, agents, tasks, knowledge
from api_gateway.websocket import router as websocket_router
from api_gateway.errors import setup_error_handlers

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan manager for startup and shutdown events.
    
    Args:
        app: FastAPI application instance
        
    Yields:
        Control during application lifetime
    """
    # Startup
    logger.info("Starting API Gateway")
    
    # Load configuration
    config = get_config()
    logger.info("Configuration loaded successfully")
    
    # Initialize logging
    setup_logging(config)
    logger.info("Logging system initialized")
    
    # TODO: Initialize database connections
    # TODO: Initialize Redis connections
    # TODO: Load ABAC policies
    
    logger.info("API Gateway started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API Gateway")
    
    # TODO: Close database connections
    # TODO: Close Redis connections
    
    logger.info("API Gateway shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.
    
    Returns:
        Configured FastAPI application instance
    """
    # Load configuration
    config = get_config()
    
    # Create FastAPI app
    app = FastAPI(
        title="Digital Workforce Platform API",
        description="API Gateway for managing AI agents and tasks",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    
    # Configure CORS
    cors_origins = config.get(
        "api.cors.origins",
        default=["http://localhost:3000", "http://localhost:5173"]
    )
    cors_allow_credentials = config.get("api.cors.allow_credentials", default=True)
    cors_allow_methods = config.get("api.cors.allow_methods", default=["*"])
    cors_allow_headers = config.get("api.cors.allow_headers", default=["*"])
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=cors_allow_credentials,
        allow_methods=cors_allow_methods,
        allow_headers=cors_allow_headers,
    )
    
    logger.info(
        "CORS configured",
        extra={
            "origins": cors_origins,
            "allow_credentials": cors_allow_credentials,
        }
    )
    
    # Add custom middleware (order matters - last added is executed first)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(JWTAuthMiddleware)
    
    # Setup error handlers
    setup_error_handlers(app)
    
    # Include routers
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
    app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
    app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["Knowledge"])
    app.include_router(websocket_router, prefix="/api/v1/ws", tags=["WebSocket"])
    
    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint for monitoring."""
        return JSONResponse(
            content={
                "status": "healthy",
                "service": "api-gateway",
                "version": "1.0.0"
            }
        )
    
    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API information."""
        return JSONResponse(
            content={
                "service": "Digital Workforce Platform API",
                "version": "1.0.0",
                "docs": "/docs",
                "health": "/health"
            }
        )
    
    logger.info("FastAPI application created successfully")
    
    return app


# Create application instance
app = create_app()
