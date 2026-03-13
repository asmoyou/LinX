"""Database module for Digital Workforce Platform."""

from .connection import (
    DatabaseConnectionPool,
    close_connection_pool,
    get_connection_pool,
    get_db_session,
)
from .migrations import (
    MigrationRunner,
    get_migration_runner,
    run_migrations_on_startup,
)
from .mission_models import (
    Mission,
    MissionAgent,
    MissionAttachment,
    MissionEvent,
    UserNotification,
)
from .models import (
    ABACPolicyModel,
    Agent,
    AuditLog,
    Base,
    KnowledgeItem,
    Permission,
    ResourceQuota,
    SessionLedger,
    SessionLedgerEvent,
    Skill,
    SkillProposal,
    Task,
    UserMemoryEntry,
    UserMemoryLink,
    UserMemoryView,
    User,
)

__all__ = [
    # Models
    "Base",
    "User",
    "Agent",
    "Task",
    "Skill",
    "Permission",
    "SessionLedger",
    "SessionLedgerEvent",
    "UserMemoryEntry",
    "UserMemoryLink",
    "UserMemoryView",
    "SkillProposal",
    "KnowledgeItem",
    "ResourceQuota",
    "AuditLog",
    "ABACPolicyModel",
    # Mission Models
    "Mission",
    "MissionAttachment",
    "MissionAgent",
    "MissionEvent",
    "UserNotification",
    # Connection Pool
    "DatabaseConnectionPool",
    "get_connection_pool",
    "close_connection_pool",
    "get_db_session",
    # Migrations
    "MigrationRunner",
    "get_migration_runner",
    "run_migrations_on_startup",
]
