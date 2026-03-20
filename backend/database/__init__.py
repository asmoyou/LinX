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
    AgentConversationMemoryState,
    AuditLog,
    Base,
    KnowledgeItem,
    Permission,
    ResourceQuota,
    AgentSkillBinding,
    AgentSchedule,
    AgentScheduleRun,
    SessionLedger,
    SessionLedgerEvent,
    Skill,
    SkillCandidate,
    SkillRevision,
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
    "AgentConversationMemoryState",
    "Task",
    "Skill",
    "Permission",
    "AgentSkillBinding",
    "AgentSchedule",
    "AgentScheduleRun",
    "SessionLedger",
    "SessionLedgerEvent",
    "UserMemoryEntry",
    "UserMemoryLink",
    "UserMemoryView",
    "SkillCandidate",
    "SkillRevision",
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
