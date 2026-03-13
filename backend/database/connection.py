"""Database connection pool management.

This module provides database connection pooling for PostgreSQL using SQLAlchemy.
It supports:
- Connection pooling with configurable pool size
- Automatic connection recycling
- Health checks
- Graceful shutdown

References:
- Requirements 3.3: Primary Database for Operational Data
- Design Section 3.1: Database Design
- Design Section 10.3: Resource Management
"""

import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, event, pool, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from shared.config import get_config

logger = logging.getLogger(__name__)


class DatabaseConnectionPool:
    """
    Database connection pool manager.

    This class manages a connection pool to PostgreSQL using SQLAlchemy.
    It provides:
    - Connection pooling with configurable size
    - Automatic connection recycling
    - Health checks
    - Session management
    - Graceful shutdown

    Example:
        >>> pool = DatabaseConnectionPool()
        >>> pool.initialize()
        >>> with pool.get_session() as session:
        ...     users = session.query(User).all()
        >>> pool.close()
    """

    def __init__(self):
        """Initialize the connection pool manager."""
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._config = get_config()

    def initialize(self) -> None:
        """
        Initialize the database connection pool.

        This method creates the SQLAlchemy engine with connection pooling
        configured according to the application configuration.

        Raises:
            Exception: If the connection pool cannot be initialized
        """
        if self._engine is not None:
            logger.warning("Database connection pool already initialized")
            return

        try:
            database_url, db_config = self._resolve_database_url()

            # Create engine with connection pooling
            self._engine = create_engine(
                database_url,
                poolclass=QueuePool,
                pool_size=db_config.get("pool_size", 20),
                max_overflow=db_config.get("max_overflow", 10),
                pool_timeout=db_config.get("pool_timeout", 30),
                pool_recycle=db_config.get("pool_recycle", 3600),
                pool_pre_ping=True,  # Enable connection health checks
                echo=db_config.get("echo", False),
                echo_pool=db_config.get("echo_pool", False),
                connect_args={
                    "connect_timeout": 10,
                    "options": f"-c timezone=UTC",
                },
            )

            # Set up event listeners
            self._setup_event_listeners()

            # Create session factory
            self._session_factory = sessionmaker(
                bind=self._engine,
                autocommit=False,
                autoflush=False,
                expire_on_commit=False,
            )

            # Test connection
            self.health_check()

            logger.info(
                f"Database connection pool initialized: "
                f"pool_size={db_config.get('pool_size', 20)}, "
                f"max_overflow={db_config.get('max_overflow', 10)}"
            )

        except Exception as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            raise

    def _setup_event_listeners(self) -> None:
        """Set up SQLAlchemy event listeners for connection management."""

        @event.listens_for(self._engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """Event listener for new connections."""
            logger.debug("New database connection established")

        @event.listens_for(self._engine, "checkout")
        def receive_checkout(dbapi_conn, connection_record, connection_proxy):
            """Event listener for connection checkout from pool."""
            logger.debug("Connection checked out from pool")

        @event.listens_for(self._engine, "checkin")
        def receive_checkin(dbapi_conn, connection_record):
            """Event listener for connection checkin to pool."""
            logger.debug("Connection checked in to pool")

    def _resolve_database_url(self) -> tuple[str, dict]:
        """Resolve database URL with test/runtime overrides when present."""
        override_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if override_url:
            normalized_url = (
                override_url.replace("postgresql+asyncpg://", "postgresql://")
                .replace("postgresql+psycopg://", "postgresql://")
            )
            logger.info("Using database URL override from environment")
            return normalized_url, {}

        db_config = self._config.get_section("database.postgres")
        database_url = (
            f"postgresql://{db_config['username']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        )
        return database_url, db_config

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a database session from the pool.

        This is a context manager that provides a database session and
        automatically handles commit/rollback and session cleanup.

        Yields:
            Session: SQLAlchemy session

        Example:
            >>> with pool.get_session() as session:
            ...     user = session.query(User).first()
            ...     session.commit()
        """
        if self._session_factory is None:
            raise RuntimeError("Database connection pool not initialized")

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            session.close()

    def get_raw_session(self) -> Session:
        """
        Get a raw database session without context manager.

        Note: The caller is responsible for closing the session.

        Returns:
            Session: SQLAlchemy session
        """
        if self._session_factory is None:
            raise RuntimeError("Database connection pool not initialized")

        return self._session_factory()

    def health_check(self) -> bool:
        """
        Perform a health check on the database connection.

        Returns:
            bool: True if the database is accessible, False otherwise
        """
        try:
            with self._engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.debug("Database health check passed")
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

    def get_pool_status(self) -> dict:
        """
        Get the current status of the connection pool.

        Returns:
            dict: Pool status information
        """
        if self._engine is None:
            return {"status": "not_initialized"}

        pool = self._engine.pool
        return {
            "status": "active",
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.size() + pool.overflow(),
        }

    def close(self) -> None:
        """
        Close the database connection pool.

        This method should be called during application shutdown to
        gracefully close all database connections.
        """
        if self._engine is not None:
            logger.info("Closing database connection pool")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            logger.info("Database connection pool closed")

    @property
    def engine(self) -> Engine:
        """Get the SQLAlchemy engine."""
        if self._engine is None:
            raise RuntimeError("Database connection pool not initialized")
        return self._engine

    def __repr__(self) -> str:
        """String representation of the connection pool."""
        status = self.get_pool_status()
        return f"DatabaseConnectionPool(status={status['status']})"


# Global connection pool instance
_connection_pool: Optional[DatabaseConnectionPool] = None


def get_connection_pool() -> DatabaseConnectionPool:
    """
    Get the global database connection pool instance.

    This function returns the singleton connection pool instance.
    If the pool is not initialized, it will be created and initialized.

    Returns:
        DatabaseConnectionPool: Global connection pool instance
    """
    global _connection_pool

    if _connection_pool is None:
        _connection_pool = DatabaseConnectionPool()
        _connection_pool.initialize()

    return _connection_pool


def close_connection_pool() -> None:
    """
    Close the global database connection pool.

    This function should be called during application shutdown.
    """
    global _connection_pool

    if _connection_pool is not None:
        _connection_pool.close()
        _connection_pool = None


# Convenience function for getting a session
@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Convenience function to get a database session.

    This is a shorthand for get_connection_pool().get_session().

    Yields:
        Session: SQLAlchemy session

    Example:
        >>> from database.connection import get_db_session
        >>> with get_db_session() as session:
        ...     users = session.query(User).all()
    """
    pool = get_connection_pool()
    with pool.get_session() as session:
        yield session
