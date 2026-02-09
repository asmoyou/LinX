"""FastAPI Application - API Gateway for LinX (灵枢).

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
from fastapi.staticfiles import StaticFiles

from api_gateway.errors import setup_error_handlers
from api_gateway.middleware.auth import JWTAuthMiddleware
from api_gateway.middleware.logging import RequestLoggingMiddleware
from api_gateway.middleware.rate_limit import RateLimitMiddleware
from api_gateway.routers import (
    agents,
    auth,
    departments,
    knowledge,
    llm,
    monitoring,
    skills,
    tasks,
    users,
)
from api_gateway.websocket import router as websocket_router
from shared.config import get_config
from shared.logging import get_logger, setup_logging

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

    # Sync config.yaml providers to database
    try:
        from database.connection import get_db_session
        from llm_providers.db_manager import ProviderDBManager

        llm_config = config.get_section("llm")
        providers_config = llm_config.get("providers", {})

        with get_db_session() as db:
            db_manager = ProviderDBManager(db)

            for provider_name, provider_config in providers_config.items():
                if not provider_config.get("enabled", False):
                    continue

                # Check if provider exists in database
                existing = db_manager.get_provider(provider_name)

                if existing:
                    logger.info(
                        f"Provider '{provider_name}' already exists in database, skipping sync"
                    )
                    continue

                # Determine protocol
                protocol = "ollama" if provider_name == "ollama" else "openai_compatible"

                # Get models
                models = []
                if "models" in provider_config:
                    models_dict = provider_config["models"]
                    if isinstance(models_dict, dict):
                        # Extract unique models from dict
                        models = list(set(models_dict.values()))
                    elif isinstance(models_dict, list):
                        models = models_dict

                # Create provider in database
                try:
                    from llm_providers.models import ProviderProtocol

                    # Convert protocol string to enum
                    protocol_enum = (
                        ProviderProtocol.OLLAMA
                        if protocol == "ollama"
                        else ProviderProtocol.OPENAI_COMPATIBLE
                    )

                    db_manager.create_provider(
                        name=provider_name,
                        protocol=protocol_enum,
                        base_url=provider_config.get("base_url", ""),
                        models=models,
                        timeout=provider_config.get("timeout", 30),
                        max_retries=provider_config.get("max_retries", 3),
                    )
                    logger.info(f"Synced provider '{provider_name}' from config.yaml to database")
                except Exception as create_error:
                    logger.error(f"Failed to sync provider '{provider_name}': {create_error}")

        logger.info("Config.yaml provider sync completed")

    except Exception as sync_error:
        logger.error(f"Failed to sync config.yaml providers: {sync_error}", exc_info=True)

    logger.info("API Gateway started successfully")

    # Initialize session manager for persistent code execution
    try:
        from agent_framework.session_manager import initialize_session_manager

        await initialize_session_manager()
        logger.info("SessionManager initialized with background cleanup")
    except Exception as e:
        logger.warning(f"Failed to initialize SessionManager: {e}")

    # Start document processing worker
    try:
        from knowledge_base.document_processor_worker import start_worker

        start_worker()
        logger.info("Document processor worker started")
    except Exception as e:
        logger.warning(f"Failed to start document processor worker: {e}")

    yield

    # Shutdown
    logger.info("Shutting down API Gateway")

    # Stop document processor worker
    try:
        from knowledge_base.document_processor_worker import stop_worker

        stop_worker()
        logger.info("Document processor worker stopped")
    except Exception as e:
        logger.error(f"Failed to stop document processor worker: {e}")

    # Shutdown session manager (clean up all sessions and workdirs)
    try:
        from agent_framework.session_manager import shutdown_session_manager

        await shutdown_session_manager()
        logger.info("SessionManager shutdown complete")
    except Exception as e:
        logger.error(f"Failed to shutdown SessionManager: {e}")

    # Final Docker sandbox cleanup (catch anything SessionManager missed)
    try:
        from virtualization.container_manager import get_docker_cleanup_manager

        cleanup_manager = get_docker_cleanup_manager()
        stats = cleanup_manager.run_full_cleanup()
        logger.info("Docker sandbox cleanup completed", extra=stats)
    except Exception as e:
        logger.error(f"Failed to run Docker cleanup: {e}")

    # Close database connections
    try:
        from database.connection import close_connection_pool

        close_connection_pool()
        logger.info("Database connection pool closed")
    except Exception as e:
        logger.error(f"Failed to close database connection pool: {e}")

    # Close Redis connections
    try:
        from message_bus.redis_manager import close_redis_manager

        close_redis_manager()
        logger.info("Redis connection manager closed")
    except Exception as e:
        logger.error(f"Failed to close Redis connection manager: {e}")

    # Close Milvus connections
    try:
        from memory_system.milvus_connection import close_milvus_connection

        close_milvus_connection()
        logger.info("Milvus connection closed")
    except Exception as e:
        logger.error(f"Failed to close Milvus connection: {e}")

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
        title="LinX Platform API",
        description="API Gateway for managing AI agents and tasks",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Add custom middleware (order matters - last added is executed first)
    # These are added first so they execute after CORS
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(JWTAuthMiddleware)

    # Configure CORS - added last so it executes first
    # This ensures CORS headers are added before any other processing
    cors_origins = config.get(
        "api.cors.origins", default=["http://localhost:3000", "http://localhost:5173"]
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
        },
    )

    # Setup error handlers
    setup_error_handlers(app)

    # Mount static files for uploads
    from pathlib import Path

    uploads_dir = Path("uploads")
    uploads_dir.mkdir(exist_ok=True)
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
    logger.info("Static file serving configured for /uploads")

    # Include routers
    app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
    app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
    app.include_router(departments.router, prefix="/api/v1/departments", tags=["Departments"])
    app.include_router(agents.router, prefix="/api/v1/agents", tags=["Agents"])
    app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["Tasks"])
    app.include_router(knowledge.router, prefix="/api/v1/knowledge", tags=["Knowledge"])
    app.include_router(skills.router, prefix="/api/v1/skills", tags=["Skills"])
    app.include_router(llm.router, prefix="/api/v1/llm", tags=["LLM Providers"])
    app.include_router(monitoring.router, tags=["Monitoring"])
    app.include_router(websocket_router, prefix="/api/v1/ws", tags=["WebSocket"])

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root():
        """Root endpoint with API information."""
        return JSONResponse(
            content={
                "service": "LinX Platform API",
                "version": "1.0.0",
                "docs": "/docs",
                "health": "/api/v1/health",
                "metrics": "/api/v1/metrics",
            }
        )

    logger.info("FastAPI application created successfully")

    return app


# Create application instance
app = create_app()
