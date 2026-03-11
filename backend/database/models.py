"""SQLAlchemy models for Digital Workforce Platform.

This module defines all database tables according to the design document
section 3.1 (PostgreSQL Schema).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
from sqlalchemy.types import UserDefinedType

Base = declarative_base()


class TSVector(UserDefinedType):
    """Custom type for PostgreSQL tsvector."""

    cache_ok = True

    def get_col_spec(self):
        return "TSVECTOR"


class Department(Base):
    """Departments table.

    Stores organizational department structure with tree hierarchy support.
    """

    __tablename__ = "departments"

    department_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False, index=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    parent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    manager_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(20), nullable=False, default="active", index=True)  # active, archived
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    parent = relationship("Department", remote_side=[department_id], backref="children")
    manager = relationship("User", foreign_keys=[manager_id])
    members = relationship("User", back_populates="department", foreign_keys="User.department_id")
    agents = relationship("Agent", back_populates="department")
    knowledge_items = relationship("KnowledgeItem", back_populates="department")

    # Indexes
    __table_args__ = (Index("idx_department_parent_status", "parent_id", "status"),)

    def __repr__(self):
        return (
            f"<Department(department_id={self.department_id}, "
            f"name={self.name}, code={self.code})>"
        )


class User(Base):
    """User accounts table.

    Stores user authentication and profile information.
    """

    __tablename__ = "users"

    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="user", index=True)  # for RBAC
    attributes = Column(JSONB, nullable=True)  # for ABAC
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    department = relationship("Department", back_populates="members", foreign_keys=[department_id])
    agents = relationship("Agent", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="creator", cascade="all, delete-orphan")
    permissions = relationship("Permission", back_populates="user", cascade="all, delete-orphan")
    knowledge_items = relationship(
        "KnowledgeItem", back_populates="owner", cascade="all, delete-orphan"
    )
    resource_quota = relationship(
        "ResourceQuota", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    audit_logs = relationship("AuditLog", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(user_id={self.user_id}, username={self.username}, role={self.role})>"


class PlatformSetting(Base):
    """Platform-wide configuration stored in the database."""

    __tablename__ = "platform_settings"

    setting_key = Column(String(100), primary_key=True)
    setting_value = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self):
        return f"<PlatformSetting(setting_key={self.setting_key})>"


class Agent(Base):
    """Agents table.

    Stores agent metadata and configuration.
    """

    __tablename__ = "agents"

    agent_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    agent_type = Column(String(100), nullable=False, index=True)  # template type
    avatar = Column(Text, nullable=True)  # avatar image URL or path
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    capabilities = Column(JSONB, nullable=False)  # list of skills
    status = Column(
        String(50), nullable=False, default="idle", index=True
    )  # active, idle, terminated
    container_id = Column(String(255), nullable=True)

    # LLM Configuration
    llm_provider = Column(String(100), nullable=True)  # provider name (ollama, openai, etc.)
    llm_model = Column(String(255), nullable=True)  # model name
    system_prompt = Column(Text, nullable=True)  # custom system prompt
    temperature = Column(Float, nullable=True, default=0.7)
    max_tokens = Column(Integer, nullable=True, default=2000)
    top_p = Column(Float, nullable=True, default=0.9)

    # Access Control
    access_level = Column(String(50), nullable=True, default="private")  # private, team, public
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    allowed_knowledge = Column(JSONB, nullable=True)  # list of knowledge collection IDs
    allowed_memory = Column(
        JSONB, nullable=True
    )  # list of memory scopes (agent/company/user_context)

    # Knowledge Base Configuration
    top_k = Column(Integer, nullable=True)  # top K results for retrieval
    similarity_threshold = Column(Float, nullable=True)  # similarity threshold (0.0-1.0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    owner = relationship("User", back_populates="agents")
    department = relationship("Department", back_populates="agents")
    tasks = relationship("Task", back_populates="assigned_agent")
    audit_logs = relationship("AuditLog", back_populates="agent")

    # Indexes
    __table_args__ = (
        Index("idx_agent_owner_status", "owner_user_id", "status"),
        Index("idx_agent_type_status", "agent_type", "status"),
    )

    def __repr__(self):
        return f"<Agent(agent_id={self.agent_id}, name={self.name}, type={self.agent_type}, status={self.status})>"


class Task(Base):
    """Tasks table.

    Stores task information with hierarchical structure support.
    """

    __tablename__ = "tasks"

    task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    goal_text = Column(Text, nullable=False)
    parent_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    assigned_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(
        String(50), nullable=False, default="pending", index=True
    )  # pending, in_progress, completed, failed
    priority = Column(Integer, nullable=False, default=0, index=True)
    dependencies = Column(JSONB, nullable=True)  # array of task_ids
    result = Column(JSONB, nullable=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("missions.mission_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    acceptance_criteria = Column(Text, nullable=True)
    task_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    creator = relationship("User", back_populates="tasks")
    assigned_agent = relationship("Agent", back_populates="tasks")
    parent_task = relationship("Task", remote_side=[task_id], backref="subtasks")
    mission = relationship("Mission", back_populates="tasks")

    # Indexes
    __table_args__ = (
        Index("idx_task_user_status", "created_by_user_id", "status"),
        Index("idx_task_agent_status", "assigned_agent_id", "status"),
        Index("idx_task_created_at", "created_at"),
        Index("idx_task_parent", "parent_task_id"),
        Index("idx_task_mission", "mission_id"),
    )

    def __repr__(self):
        return f"<Task(task_id={self.task_id}, status={self.status}, priority={self.priority})>"


class Skill(Base):
    """Skills table.

    Stores skill library definitions with executable code and metadata.
    Enhanced to support Claude Code style dynamic skills with full project support.
    """

    __tablename__ = "skills"

    skill_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=False)

    # Skill type and implementation
    skill_type = Column(String(50), nullable=False, default="python_function", index=True)
    code = Column(Text, nullable=True)  # Python code for inline skills
    config = Column(JSONB, nullable=True)  # YAML/JSON config for API/DB skills

    # Storage location (for flexible architecture)
    storage_type = Column(String(50), nullable=False, default="inline", index=True)
    # inline (code field) | minio (package in MinIO)
    storage_path = Column(String(500), nullable=True)
    # MinIO path: skills-storage/{skill_id}/

    # Manifest (parsed from skill.yaml for packages)
    manifest = Column(JSONB, nullable=True)

    # Agent skill specific fields (added for agent_skill support)
    skill_md_content = Column(Text, nullable=True)  # SKILL.md content for agent_skill
    homepage = Column(String(500), nullable=True)  # Homepage URL
    skill_metadata = Column(
        JSONB, nullable=True
    )  # Additional metadata (emoji, tags, etc.) - renamed from 'metadata' to avoid SQLAlchemy conflict
    gating_status = Column(JSONB, nullable=True)  # Gating check results

    # Auto-extracted from code/config/manifest
    interface_definition = Column(JSONB, nullable=False)
    dependencies = Column(JSONB, nullable=True)

    # Metadata
    version = Column(String(50), nullable=False, default="1.0.0")
    is_active = Column(Boolean, nullable=False, default=True, index=True)
    is_system = Column(Boolean, nullable=False, default=False, index=True)

    # Execution stats
    execution_count = Column(Integer, nullable=False, default=0)
    last_executed_at = Column(DateTime(timezone=True), nullable=True)
    average_execution_time = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Owner (for custom skills)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    def __repr__(self):
        return f"<Skill(skill_id={self.skill_id}, name={self.name}, type={self.skill_type}, storage={self.storage_type}, version={self.version})>"


class Permission(Base):
    """Permissions table.

    Stores access control permissions for users.
    """

    __tablename__ = "permissions"

    permission_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_type = Column(String(100), nullable=False, index=True)  # knowledge, memory, agent
    resource_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    access_level = Column(String(50), nullable=False)  # read, write, admin
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="permissions")

    # Indexes
    __table_args__ = (
        Index("idx_permission_user_resource", "user_id", "resource_type", "resource_id"),
    )

    def __repr__(self):
        return f"<Permission(permission_id={self.permission_id}, user_id={self.user_id}, resource_type={self.resource_type}, access_level={self.access_level})>"


class MemoryRecord(Base):
    """Memory records table.

    PostgreSQL is the source of truth for memory business data.
    Milvus stores only vector indexes and is referenced by milvus_id.
    """

    __tablename__ = "memory_records"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    milvus_id = Column(BigInteger, nullable=True, unique=True, index=True)
    memory_type = Column(String(50), nullable=False, index=True)
    content = Column(Text, nullable=False)
    user_id = Column(String(255), nullable=True, index=True)
    agent_id = Column(String(255), nullable=True, index=True)
    task_id = Column(String(255), nullable=True, index=True)
    owner_user_id = Column(String(255), nullable=True, index=True)
    owner_agent_id = Column(String(255), nullable=True, index=True)
    department_id = Column(String(255), nullable=True, index=True)
    visibility = Column(String(50), nullable=False, default="account", index=True)
    sensitivity = Column(String(50), nullable=False, default="internal", index=True)
    source_memory_id = Column(
        BigInteger,
        ForeignKey("memory_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    memory_metadata = Column(JSONB, nullable=True)
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    vector_status = Column(String(20), nullable=False, default="pending", index=True)
    vector_error = Column(Text, nullable=True)
    vector_updated_at = Column(DateTime(timezone=True), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    acl_entries = relationship(
        "MemoryACL",
        cascade="all, delete-orphan",
        passive_deletes=True,
        backref="memory_record",
    )

    __table_args__ = (
        Index("idx_memory_type_user", "memory_type", "user_id"),
        Index("idx_memory_type_agent", "memory_type", "agent_id"),
        Index("idx_memory_visibility_scope", "visibility", "department_id"),
    )

    def __repr__(self):
        return (
            f"<MemoryRecord(id={self.id}, type={self.memory_type}, "
            f"milvus_id={self.milvus_id}, status={self.vector_status})>"
        )


class MemoryACL(Base):
    """Explicit allow/deny access control entries for memory records."""

    __tablename__ = "memory_acl"

    acl_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    memory_id = Column(
        BigInteger,
        ForeignKey("memory_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    effect = Column(String(20), nullable=False, index=True)  # allow, deny
    principal_type = Column(String(50), nullable=False, index=True)  # user, agent, department, role
    principal_id = Column(String(255), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_by = Column(String(255), nullable=True)
    acl_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_memory_acl_principal", "principal_type", "principal_id"),
        Index("idx_memory_acl_memory_effect", "memory_id", "effect"),
    )

    def __repr__(self):
        return (
            f"<MemoryACL(acl_id={self.acl_id}, memory_id={self.memory_id}, "
            f"effect={self.effect}, principal={self.principal_type}:{self.principal_id})>"
        )


class MemorySession(Base):
    """Session-level ledger for conversation memory extraction and replay."""

    __tablename__ = "memory_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    agent_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="completed", index=True)
    end_reason = Column(String(64), nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True, index=True)
    session_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_memory_sessions_agent_status", "agent_id", "status"),
        Index("idx_memory_sessions_user_started", "user_id", "started_at"),
    )

    def __repr__(self):
        return (
            f"<MemorySession(id={self.id}, session_id={self.session_id}, "
            f"agent_id={self.agent_id}, user_id={self.user_id})>"
        )


class MemorySessionEvent(Base):
    """Structured event ledger for one conversation session."""

    __tablename__ = "memory_session_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    memory_session_id = Column(
        BigInteger,
        ForeignKey("memory_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_index = Column(Integer, nullable=False)
    event_kind = Column(String(32), nullable=False, index=True)
    role = Column(String(32), nullable=True, index=True)
    content = Column(Text, nullable=False)
    event_timestamp = Column(DateTime(timezone=True), nullable=True, index=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_memory_session_events_session_order", "memory_session_id", "event_index"),
    )

    def __repr__(self):
        return (
            f"<MemorySessionEvent(id={self.id}, memory_session_id={self.memory_session_id}, "
            f"kind={self.event_kind}, index={self.event_index})>"
        )


class MemoryObservation(Base):
    """Extracted observations derived from a session ledger."""

    __tablename__ = "memory_observations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    memory_session_id = Column(
        BigInteger,
        ForeignKey("memory_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    observation_key = Column(String(255), nullable=False, index=True)
    observation_type = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    source_event_indexes = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=False, default=0.7)
    importance = Column(Float, nullable=False, default=0.5)
    observation_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_memory_observations_session_type",
            "memory_session_id",
            "observation_type",
        ),
        Index(
            "idx_memory_observations_type_key",
            "observation_type",
            "observation_key",
        ),
    )

    def __repr__(self):
        return (
            f"<MemoryObservation(id={self.id}, memory_session_id={self.memory_session_id}, "
            f"type={self.observation_type}, key={self.observation_key})>"
        )


class MemoryMaterialization(Base):
    """Stable projection built from observations for retrieval and skill reuse."""

    __tablename__ = "memory_materializations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_type = Column(String(32), nullable=False, index=True)
    owner_id = Column(String(255), nullable=False, index=True)
    materialization_type = Column(String(64), nullable=False, index=True)
    materialization_key = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    materialized_data = Column(JSONB, nullable=True)
    source_session_id = Column(
        BigInteger,
        ForeignKey("memory_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_observation_id = Column(
        BigInteger,
        ForeignKey("memory_observations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_memory_materializations_owner_type",
            "owner_type",
            "owner_id",
            "materialization_type",
        ),
        Index(
            "ux_memory_materializations_owner_key",
            "owner_type",
            "owner_id",
            "materialization_type",
            "materialization_key",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<MemoryMaterialization(id={self.id}, owner={self.owner_type}:{self.owner_id}, "
            f"type={self.materialization_type}, key={self.materialization_key})>"
        )


class MemoryEntry(Base):
    """Atomic memory entry derived from one or more observations."""

    __tablename__ = "memory_entries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_type = Column(String(32), nullable=False, index=True)
    owner_id = Column(String(255), nullable=False, index=True)
    entry_type = Column(String(64), nullable=False, index=True)
    entry_key = Column(String(255), nullable=False)
    canonical_text = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    confidence = Column(Float, nullable=False, default=0.7)
    importance = Column(Float, nullable=False, default=0.5)
    status = Column(String(32), nullable=False, default="active", index=True)
    entry_data = Column(JSONB, nullable=True)
    source_session_id = Column(
        BigInteger,
        ForeignKey("memory_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_observation_id = Column(
        BigInteger,
        ForeignKey("memory_observations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_memory_entries_owner_type",
            "owner_type",
            "owner_id",
            "entry_type",
        ),
        Index(
            "ux_memory_entries_owner_key",
            "owner_type",
            "owner_id",
            "entry_type",
            "entry_key",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<MemoryEntry(id={self.id}, owner={self.owner_type}:{self.owner_id}, "
            f"type={self.entry_type}, key={self.entry_key})>"
        )


class MemoryLink(Base):
    """Cross-layer lineage links between observations, entries, and materializations."""

    __tablename__ = "memory_links"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_session_id = Column(
        BigInteger,
        ForeignKey("memory_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_kind = Column(String(32), nullable=False, index=True)
    source_id = Column(BigInteger, nullable=False, index=True)
    target_kind = Column(String(32), nullable=False, index=True)
    target_id = Column(BigInteger, nullable=False, index=True)
    link_type = Column(String(64), nullable=False, index=True)
    link_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index(
            "idx_memory_links_source",
            "source_kind",
            "source_id",
            "link_type",
        ),
        Index(
            "idx_memory_links_target",
            "target_kind",
            "target_id",
            "link_type",
        ),
        Index(
            "ux_memory_links_identity",
            "source_kind",
            "source_id",
            "target_kind",
            "target_id",
            "link_type",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<MemoryLink(id={self.id}, source={self.source_kind}:{self.source_id}, "
            f"target={self.target_kind}:{self.target_id}, type={self.link_type})>"
        )


class KnowledgeCollection(Base):
    """Knowledge collections table.

    Groups related knowledge items (e.g., files extracted from a ZIP archive).
    Collections are flat (non-nesting, one level only).
    """

    __tablename__ = "knowledge_collections"

    collection_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_level = Column(
        String(50), nullable=False, default="private", index=True
    )  # private, team, public
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    item_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    owner = relationship("User")
    department = relationship("Department")
    items = relationship(
        "KnowledgeItem",
        back_populates="collection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Indexes
    __table_args__ = (Index("idx_collection_owner_access", "owner_user_id", "access_level"),)

    def __repr__(self):
        return (
            f"<KnowledgeCollection(collection_id={self.collection_id}, "
            f"name={self.name}, item_count={self.item_count})>"
        )


class KnowledgeItem(Base):
    """Knowledge items table.

    Stores metadata for knowledge base documents.
    """

    __tablename__ = "knowledge_items"

    knowledge_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False, index=True)
    content_type = Column(
        String(100), nullable=False, index=True
    )  # document, policy, domain_knowledge
    file_reference = Column(String(500), nullable=True)  # MinIO object key
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    access_level = Column(
        String(50), nullable=False, default="private", index=True
    )  # private, team, public
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    collection_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_collections.collection_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    item_metadata = Column(
        JSONB, nullable=True
    )  # Renamed from 'metadata' to avoid SQLAlchemy conflict
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    owner = relationship("User", back_populates="knowledge_items")
    department = relationship("Department", back_populates="knowledge_items")
    collection = relationship("KnowledgeCollection", back_populates="items")
    chunks = relationship(
        "KnowledgeChunk",
        back_populates="knowledge_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Indexes
    __table_args__ = (
        Index("idx_knowledge_owner_access", "owner_user_id", "access_level"),
        Index("idx_knowledge_type_access", "content_type", "access_level"),
    )

    def __repr__(self):
        return f"<KnowledgeItem(knowledge_id={self.knowledge_id}, title={self.title}, content_type={self.content_type})>"


class KnowledgeChunk(Base):
    """Knowledge chunks table.

    Stores individual document chunks with full-text search support (BM25 via tsvector).
    Each chunk belongs to a KnowledgeItem and contains enrichment metadata.
    """

    __tablename__ = "knowledge_chunks"

    chunk_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_id = Column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_items.knowledge_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    keywords = Column(ARRAY(String), nullable=True)
    questions = Column(ARRAY(String), nullable=True)
    summary = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)
    search_vector = Column(TSVector(), nullable=True)
    chunk_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    knowledge_item = relationship("KnowledgeItem", back_populates="chunks")

    # Indexes
    __table_args__ = (
        Index("idx_chunk_knowledge_index", "knowledge_id", "chunk_index"),
        Index("idx_chunk_search_vector", "search_vector", postgresql_using="gin"),
    )

    def __repr__(self):
        return (
            f"<KnowledgeChunk(chunk_id={self.chunk_id}, "
            f"knowledge_id={self.knowledge_id}, chunk_index={self.chunk_index})>"
        )


# AgentTemplate model is defined in agent_framework/agent_template.py
# to avoid circular imports and keep agent-specific models with agent code


class ResourceQuota(Base):
    """Resource quotas table.

    Stores resource limits and usage for users.
    """

    __tablename__ = "resource_quotas"

    quota_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    max_agents = Column(Integer, nullable=False, default=10)
    max_storage_gb = Column(Integer, nullable=False, default=100)
    max_cpu_cores = Column(Integer, nullable=False, default=10)
    max_memory_gb = Column(Integer, nullable=False, default=20)
    current_agents = Column(Integer, nullable=False, default=0)
    current_storage_gb = Column(Numeric(10, 2), nullable=False, default=0.0)

    # Relationships
    user = relationship("User", back_populates="resource_quota")

    def __repr__(self):
        return f"<ResourceQuota(quota_id={self.quota_id}, user_id={self.user_id}, current_agents={self.current_agents}/{self.max_agents})>"


class AuditLog(Base):
    """Audit logs table.

    Stores audit trail of all actions in the system.
    """

    __tablename__ = "audit_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = Column(String(255), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    details = Column(JSONB, nullable=True)
    timestamp = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user = relationship("User", back_populates="audit_logs")
    agent = relationship("Agent", back_populates="audit_logs")

    # Indexes
    __table_args__ = (
        Index("idx_audit_user_timestamp", "user_id", "timestamp"),
        Index("idx_audit_action_timestamp", "action", "timestamp"),
        Index("idx_audit_resource", "resource_type", "resource_id"),
    )

    def __repr__(self):
        return f"<AuditLog(log_id={self.log_id}, action={self.action}, resource_type={self.resource_type}, timestamp={self.timestamp})>"


class ABACPolicyModel(Base):
    """ABAC policies table.

    Stores ABAC (Attribute-Based Access Control) policies for fine-grained
    permission evaluation.
    """

    __tablename__ = "abac_policies"

    policy_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    effect = Column(String(50), nullable=False, index=True)  # allow, deny
    resource_type = Column(String(100), nullable=False, index=True)
    actions = Column(JSONB, nullable=False)  # array of action strings
    conditions = Column(JSONB, nullable=False)  # condition group structure
    priority = Column(Integer, nullable=False, default=0, index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Indexes
    __table_args__ = (
        Index("idx_policy_resource_enabled", "resource_type", "enabled"),
        Index("idx_policy_priority", "priority"),
    )

    def __repr__(self):
        return f"<ABACPolicyModel(policy_id={self.policy_id}, name={self.name}, effect={self.effect}, enabled={self.enabled})>"


class LLMProvider(Base):
    """LLM Provider configurations table.

    Stores dynamically configured LLM providers.
    """

    __tablename__ = "llm_providers"

    provider_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), unique=True, nullable=False, index=True)
    protocol = Column(String(50), nullable=False)  # ollama, openai_compatible
    base_url = Column(String(500), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)  # Encrypted API key
    timeout = Column(Integer, nullable=False, default=30)
    max_retries = Column(Integer, nullable=False, default=3)
    models = Column(JSONB, nullable=False)  # List of model names
    model_metadata = Column(JSONB, nullable=True)  # Dict[model_name, ModelMetadata]
    enabled = Column(Boolean, nullable=False, default=True, index=True)

    # Last test connection result
    last_test_status = Column(String(20), nullable=True)  # 'success', 'failed', 'untested'
    last_test_time = Column(DateTime(timezone=True), nullable=True)
    last_test_error = Column(Text, nullable=True)  # Error message if test failed

    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Indexes
    __table_args__ = (
        Index("idx_provider_enabled", "enabled"),
        Index("idx_provider_protocol", "protocol"),
    )

    def __repr__(self):
        return f"<LLMProvider(provider_id={self.provider_id}, name={self.name}, protocol={self.protocol}, enabled={self.enabled})>"
