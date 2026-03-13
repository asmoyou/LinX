"""Database migration runner.

This module provides utilities for running database migrations using Alembic.
It can be called on application startup to ensure the database schema is up to date.

References:
- Requirements 3.3: Primary Database for Operational Data
- Design Section 3.1: Database Design
- Tasks 1.2.12: Implement database migration runner
"""

import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine, text

from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from shared.config import get_config

logger = logging.getLogger(__name__)


class MigrationRunner:
    """
    Database migration runner using Alembic.

    This class provides methods to:
    - Check current database version
    - Run migrations to upgrade database schema
    - Downgrade database schema
    - Generate new migrations

    Example:
        >>> runner = MigrationRunner()
        >>> runner.upgrade()  # Upgrade to latest version
        >>> current = runner.get_current_version()
        >>> print(f"Current version: {current}")
    """

    def __init__(self, alembic_ini_path: Optional[str] = None):
        """
        Initialize the migration runner.

        Args:
            alembic_ini_path: Path to alembic.ini file (default: auto-detect)
        """
        self._config = get_config()

        # Auto-detect alembic.ini path if not provided
        if alembic_ini_path is None:
            backend_dir = Path(__file__).parent.parent
            alembic_ini_path = str(backend_dir / "alembic.ini")

        self._alembic_ini_path = alembic_ini_path
        self._alembic_config: Optional[AlembicConfig] = None

    def _get_alembic_config(self) -> AlembicConfig:
        """
        Get the Alembic configuration.

        Returns:
            AlembicConfig: Alembic configuration object
        """
        if self._alembic_config is None:
            self._alembic_config = AlembicConfig(self._alembic_ini_path)

            # Override database URL from our config
            database_url = self._resolve_database_url()
            self._alembic_config.set_main_option("sqlalchemy.url", database_url)

        return self._alembic_config

    def _resolve_database_url(self) -> str:
        """Resolve database URL with test/runtime overrides when present."""
        override_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
        if override_url:
            return override_url.replace("postgresql+asyncpg://", "postgresql://").replace(
                "postgresql+psycopg://", "postgresql://"
            )

        db_config = self._config.get_section("database.postgres")
        return (
            f"postgresql://{db_config['username']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
        )

    def get_current_version(self) -> Optional[str]:
        """
        Get the current database schema version.

        Returns:
            str: Current revision ID, or None if no migrations have been applied
        """
        try:
            engine = create_engine(self._resolve_database_url())
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                current_rev = context.get_current_revision()

            engine.dispose()
            return current_rev

        except Exception as e:
            logger.error(f"Failed to get current database version: {e}")
            return None

    def get_head_version(self) -> Optional[str]:
        """
        Get the latest available migration version.

        Returns:
            str: Head revision ID, or None if no migrations exist
        """
        try:
            alembic_config = self._get_alembic_config()
            script = ScriptDirectory.from_config(alembic_config)
            head_rev = script.get_current_head()
            return head_rev
        except Exception as e:
            logger.error(f"Failed to get head version: {e}")
            return None

    def is_up_to_date(self) -> bool:
        """
        Check if the database schema is up to date.

        Returns:
            bool: True if database is at the latest version, False otherwise
        """
        current = self.get_current_version()
        head = self.get_head_version()

        if current is None or head is None:
            return False

        return current == head

    def upgrade(self, revision: str = "head") -> bool:
        """
        Upgrade the database schema to a specific revision.

        Args:
            revision: Target revision (default: "head" for latest)

        Returns:
            bool: True if upgrade succeeded, False otherwise
        """
        try:
            current = self.get_current_version()
            logger.info(f"Current database version: {current}")

            if revision == "head":
                head = self.get_head_version()
                logger.info(f"Upgrading database to version: {head}")
            else:
                logger.info(f"Upgrading database to version: {revision}")

            alembic_config = self._get_alembic_config()
            command.upgrade(alembic_config, revision)

            new_version = self.get_current_version()
            logger.info(f"Database upgraded successfully to version: {new_version}")
            return True

        except Exception as e:
            logger.error(f"Failed to upgrade database: {e}")
            return False

    def downgrade(self, revision: str) -> bool:
        """
        Downgrade the database schema to a specific revision.

        Args:
            revision: Target revision (use "-1" for previous version)

        Returns:
            bool: True if downgrade succeeded, False otherwise
        """
        try:
            current = self.get_current_version()
            logger.info(f"Current database version: {current}")
            logger.info(f"Downgrading database to version: {revision}")

            alembic_config = self._get_alembic_config()
            command.downgrade(alembic_config, revision)

            new_version = self.get_current_version()
            logger.info(f"Database downgraded successfully to version: {new_version}")
            return True

        except Exception as e:
            logger.error(f"Failed to downgrade database: {e}")
            return False

    def get_migration_history(self) -> list:
        """
        Get the migration history.

        Returns:
            list: List of migration revisions
        """
        try:
            alembic_config = self._get_alembic_config()
            script = ScriptDirectory.from_config(alembic_config)

            history = []
            for revision in script.walk_revisions():
                history.append(
                    {
                        "revision": revision.revision,
                        "down_revision": revision.down_revision,
                        "description": revision.doc,
                    }
                )

            return history

        except Exception as e:
            logger.error(f"Failed to get migration history: {e}")
            return []

    def check_database_connection(self) -> bool:
        """
        Check if the database is accessible.

        Returns:
            bool: True if database is accessible, False otherwise
        """
        try:
            engine = create_engine(self._resolve_database_url())
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            engine.dispose()
            logger.info("Database connection check passed")
            return True

        except Exception as e:
            logger.error(f"Database connection check failed: {e}")
            return False

    def run_migrations_on_startup(self, auto_upgrade: bool = True) -> bool:
        """
        Run migrations on application startup.

        This method checks if the database schema is up to date and
        optionally runs migrations to upgrade to the latest version.

        Args:
            auto_upgrade: If True, automatically upgrade to latest version

        Returns:
            bool: True if database is ready, False otherwise
        """
        try:
            # Check database connection
            if not self.check_database_connection():
                logger.error("Cannot connect to database")
                return False

            # Get current and head versions
            current = self.get_current_version()
            head = self.get_head_version()

            logger.info(f"Database schema version: current={current}, head={head}")

            # Check if up to date
            if current == head:
                logger.info("Database schema is up to date")
                return True

            # Auto-upgrade if enabled
            if auto_upgrade:
                logger.info("Database schema is outdated, running migrations...")
                return self.upgrade()
            else:
                logger.warning(
                    "Database schema is outdated but auto_upgrade is disabled. "
                    "Please run migrations manually."
                )
                return False

        except Exception as e:
            logger.error(f"Failed to run migrations on startup: {e}")
            return False


# Global migration runner instance
_migration_runner: Optional[MigrationRunner] = None


def get_migration_runner() -> MigrationRunner:
    """
    Get the global migration runner instance.

    Returns:
        MigrationRunner: Global migration runner instance
    """
    global _migration_runner

    if _migration_runner is None:
        _migration_runner = MigrationRunner()

    return _migration_runner


def run_migrations_on_startup(auto_upgrade: bool = True) -> bool:
    """
    Convenience function to run migrations on application startup.

    Args:
        auto_upgrade: If True, automatically upgrade to latest version

    Returns:
        bool: True if database is ready, False otherwise

    Example:
        >>> from database.migrations import run_migrations_on_startup
        >>> if run_migrations_on_startup():
        ...     print("Database is ready")
        ... else:
        ...     print("Database migration failed")
    """
    runner = get_migration_runner()
    return runner.run_migrations_on_startup(auto_upgrade=auto_upgrade)
