"""Database module for Digital Workforce Platform."""

from .models import (
    Base,
    User,
    Agent,
    Task,
    Skill,
    Permission,
    KnowledgeItem,
    ResourceQuota,
    AuditLog,
    ABACPolicyModel,
)
from .connection import (
    DatabaseConnectionPool,
    get_connection_pool,
    close_connection_pool,
    get_db_session,
)
from .migrations import (
    MigrationRunner,
    get_migration_runner,
    run_migrations_on_startup,
)

__all__ = [
    # Models
    'Base',
    'User',
    'Agent',
    'Task',
    'Skill',
    'Permission',
    'KnowledgeItem',
    'ResourceQuota',
    'AuditLog',
    'ABACPolicyModel',
    # Connection Pool
    'DatabaseConnectionPool',
    'get_connection_pool',
    'close_connection_pool',
    'get_db_session',
    # Migrations
    'MigrationRunner',
    'get_migration_runner',
    'run_migrations_on_startup',
]
