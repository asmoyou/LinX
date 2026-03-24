import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add the backend directory to the path so we can import our modules
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Import our configuration loader
from shared.config import get_config
from shared.runtime_env import bootstrap_runtime_env

bootstrap_runtime_env()

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

DEFAULT_ALEMBIC_URL = "postgresql://platform_user:dev_password@localhost:5432/workforce_platform"


def _normalize_database_url(url: str) -> str:
    return (
        str(url)
        .replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )


def _resolve_database_url() -> str:
    override_url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if override_url:
        return _normalize_database_url(override_url)

    configured_url = config.get_main_option("sqlalchemy.url")
    if configured_url and configured_url != DEFAULT_ALEMBIC_URL:
        return _normalize_database_url(configured_url)

    app_config = get_config()
    db_config = app_config.get_section("database.postgres")
    return (
        f"postgresql://{db_config['username']}:{db_config['password']}"
        f"@{db_config['host']}:{db_config['port']}/{db_config['database']}"
    )


config.set_main_option("sqlalchemy.url", _resolve_database_url())

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
from database.models import Base
from object_storage.file_metadata import FileMetadata  # noqa: F401

target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
