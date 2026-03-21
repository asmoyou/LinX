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
    CheckConstraint,
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
    agent_conversations = relationship(
        "AgentConversation", back_populates="owner", cascade="all, delete-orphan"
    )
    schedules = relationship("AgentSchedule", back_populates="owner", cascade="all, delete-orphan")
    user_binding_codes = relationship(
        "UserBindingCode", back_populates="user", cascade="all, delete-orphan"
    )
    external_bindings = relationship(
        "UserExternalBinding", back_populates="user", cascade="all, delete-orphan"
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
    conversations = relationship(
        "AgentConversation", back_populates="agent", cascade="all, delete-orphan"
    )
    channel_publications = relationship(
        "AgentChannelPublication", back_populates="agent", cascade="all, delete-orphan"
    )
    schedules = relationship("AgentSchedule", back_populates="agent", cascade="all, delete-orphan")
    skill_bindings = relationship(
        "AgentSkillBinding", back_populates="agent", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_agent_owner_status", "owner_user_id", "status"),
        Index("idx_agent_type_status", "agent_type", "status"),
    )

    def __repr__(self):
        return f"<Agent(agent_id={self.agent_id}, name={self.name}, type={self.agent_type}, status={self.status})>"


class AgentConversation(Base):
    """Durable user-owned conversation threads for one agent."""

    __tablename__ = "agent_conversations"

    conversation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False, default="active", index=True)
    source = Column(String(32), nullable=False, default="web", index=True)
    latest_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversation_snapshots.snapshot_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    storage_tier = Column(String(32), nullable=False, default="hot", index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True, index=True)
    delete_after = Column(DateTime(timezone=True), nullable=True, index=True)
    last_message_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_workspace_decay_at = Column(DateTime(timezone=True), nullable=True)
    last_history_compaction_at = Column(DateTime(timezone=True), nullable=True)
    workspace_bytes_estimate = Column(BigInteger, nullable=False, default=0)
    workspace_file_count_estimate = Column(Integer, nullable=False, default=0)
    compacted_message_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent = relationship("Agent", back_populates="conversations", foreign_keys=[agent_id])
    owner = relationship("User", back_populates="agent_conversations", foreign_keys=[owner_user_id])
    messages = relationship(
        "AgentConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="AgentConversationMessage.conversation_id",
    )
    snapshots = relationship(
        "AgentConversationSnapshot",
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="AgentConversationSnapshot.conversation_id",
    )
    latest_snapshot = relationship(
        "AgentConversationSnapshot",
        foreign_keys=[latest_snapshot_id],
        post_update=True,
    )
    external_links = relationship(
        "ExternalConversationLink",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    memory_state = relationship(
        "AgentConversationMemoryState",
        back_populates="conversation",
        cascade="all, delete-orphan",
        uselist=False,
    )
    history_summary = relationship(
        "AgentConversationHistorySummary",
        back_populates="conversation",
        cascade="all, delete-orphan",
        uselist=False,
    )
    message_archives = relationship(
        "AgentConversationMessageArchive",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )
    schedules = relationship(
        "AgentSchedule",
        back_populates="bound_conversation",
        cascade="all, delete-orphan",
        foreign_keys="AgentSchedule.bound_conversation_id",
    )
    schedule_runs = relationship(
        "AgentScheduleRun",
        back_populates="conversation",
        foreign_keys="AgentScheduleRun.conversation_id",
    )

    __table_args__ = (
        Index("idx_agent_conversations_owner_agent", "owner_user_id", "agent_id", "status"),
        Index("idx_agent_conversations_agent_updated", "agent_id", "updated_at"),
        Index(
            "idx_agent_conversations_owner_agent_status_updated_cursor",
            "owner_user_id",
            "agent_id",
            "status",
            "updated_at",
            "conversation_id",
        ),
    )

    def __repr__(self):
        return (
            f"<AgentConversation(conversation_id={self.conversation_id}, agent_id={self.agent_id}, "
            f"owner_user_id={self.owner_user_id}, status={self.status})>"
        )


class AgentConversationMemoryState(Base):
    """Cursor and lease state for segmented memory extraction on one conversation."""

    __tablename__ = "agent_conversation_memory_states"

    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        primary_key=True,
    )
    last_processed_assistant_message_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    last_processed_assistant_created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_processed_turn_count = Column(Integer, nullable=False, default=0)
    last_run_sequence = Column(Integer, nullable=False, default=0)
    run_state = Column(String(16), nullable=False, default="idle", index=True)
    run_token = Column(String(64), nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True, index=True)
    target_assistant_message_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    target_assistant_created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_extraction_started_at = Column(DateTime(timezone=True), nullable=True)
    last_extraction_completed_at = Column(DateTime(timezone=True), nullable=True)
    last_extraction_reason = Column(String(64), nullable=True)
    last_successful_session_ledger_id = Column(
        BigInteger,
        ForeignKey("session_ledgers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    consecutive_failures = Column(Integer, nullable=False, default=0)
    retry_after = Column(DateTime(timezone=True), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conversation = relationship("AgentConversation", back_populates="memory_state")

    __table_args__ = (
        CheckConstraint(
            "(run_state <> 'running') OR "
            "(run_token IS NOT NULL AND lease_until IS NOT NULL AND "
            "target_assistant_message_id IS NOT NULL)",
            name="ck_agent_conversation_memory_states_running_fields",
        ),
        Index(
            "idx_agent_conversation_memory_states_claim",
            "run_state",
            "retry_after",
            "lease_until",
        ),
    )

    def __repr__(self):
        return (
            "<AgentConversationMemoryState("
            f"conversation_id={self.conversation_id}, run_state={self.run_state}, "
            f"last_processed_turn_count={self.last_processed_turn_count})>"
        )


class AgentConversationMessage(Base):
    """Persisted chat message for one conversation."""

    __tablename__ = "agent_conversation_messages"

    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(32), nullable=False, index=True)
    content_text = Column(Text, nullable=False, default="")
    content_json = Column(JSONB, nullable=True)
    attachments_json = Column(JSONB, nullable=True)
    source = Column(String(32), nullable=False, default="web", index=True)
    external_event_id = Column(String(255), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("AgentConversation", back_populates="messages")

    __table_args__ = (
        Index(
            "idx_agent_conversation_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
        Index(
            "idx_agent_conversation_messages_conversation_created_message",
            "conversation_id",
            "created_at",
            "message_id",
        ),
        Index(
            "idx_agent_conversation_messages_external_event",
            "conversation_id",
            "external_event_id",
        ),
    )

    def __repr__(self):
        return (
            f"<AgentConversationMessage(message_id={self.message_id}, "
            f"conversation_id={self.conversation_id}, role={self.role})>"
        )


class AgentConversationSnapshot(Base):
    """Latest restorable workspace snapshot for one conversation."""

    __tablename__ = "agent_conversation_snapshots"

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generation = Column(Integer, nullable=False)
    archive_ref = Column(Text, nullable=True)
    manifest_ref = Column(Text, nullable=True)
    size_bytes = Column(BigInteger, nullable=False, default=0)
    checksum = Column(String(128), nullable=True)
    snapshot_status = Column(String(32), nullable=False, default="ready", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship(
        "AgentConversation",
        back_populates="snapshots",
        foreign_keys=[conversation_id],
    )

    __table_args__ = (
        Index(
            "ux_agent_conversation_snapshots_generation",
            "conversation_id",
            "generation",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<AgentConversationSnapshot(snapshot_id={self.snapshot_id}, "
            f"conversation_id={self.conversation_id}, generation={self.generation})>"
        )


class AgentConversationHistorySummary(Base):
    """Rolling summary for compacted persistent conversation history."""

    __tablename__ = "agent_conversation_history_summaries"

    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        primary_key=True,
    )
    covers_until_message_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    covers_until_created_at = Column(DateTime(timezone=True), nullable=True, index=True)
    raw_message_count = Column(Integer, nullable=False, default=0)
    summary_text = Column(Text, nullable=False, default="")
    summary_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    conversation = relationship("AgentConversation", back_populates="history_summary")

    def __repr__(self):
        return (
            "<AgentConversationHistorySummary("
            f"conversation_id={self.conversation_id}, raw_message_count={self.raw_message_count})>"
        )


class AgentConversationMessageArchive(Base):
    """Archived raw message batches compacted out of a persistent conversation."""

    __tablename__ = "agent_conversation_message_archives"

    archive_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    start_message_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    end_message_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    message_count = Column(Integer, nullable=False, default=0)
    archive_ref = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="ready", index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("AgentConversation", back_populates="message_archives")

    __table_args__ = (
        Index(
            "idx_agent_conversation_message_archives_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )

    def __repr__(self):
        return (
            "<AgentConversationMessageArchive("
            f"archive_id={self.archive_id}, conversation_id={self.conversation_id}, "
            f"message_count={self.message_count})>"
        )


class UserBindingCode(Base):
    """Reusable binding code for linking external identities back to a platform user."""

    __tablename__ = "user_binding_codes"

    code_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash = Column(String(128), nullable=False, unique=True, index=True)
    code_encrypted = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="active", index=True)
    rotated_at = Column(DateTime(timezone=True), nullable=True)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user = relationship("User", back_populates="user_binding_codes")

    __table_args__ = (Index("idx_user_binding_codes_user_status", "user_id", "status"),)

    def __repr__(self):
        return f"<UserBindingCode(code_id={self.code_id}, user_id={self.user_id}, status={self.status})>"


class AgentChannelPublication(Base):
    """External channel publication for an agent."""

    __tablename__ = "agent_channel_publications"

    publication_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    channel_identity = Column(String(255), nullable=True)
    config_json = Column(JSONB, nullable=True)
    secret_encrypted_json = Column(JSONB, nullable=True)
    webhook_path = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent = relationship("Agent", back_populates="channel_publications")
    external_bindings = relationship(
        "UserExternalBinding",
        back_populates="publication",
        cascade="all, delete-orphan",
    )
    external_links = relationship(
        "ExternalConversationLink",
        back_populates="publication",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ux_agent_channel_publications_agent_channel",
            "agent_id",
            "channel_type",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<AgentChannelPublication(publication_id={self.publication_id}, "
            f"agent_id={self.agent_id}, channel_type={self.channel_type}, status={self.status})>"
        )


class UserExternalBinding(Base):
    """Mapping between a platform user and an external channel identity."""

    __tablename__ = "user_external_bindings"

    binding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_type = Column(String(32), nullable=False, index=True)
    publication_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_channel_publications.publication_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_user_id = Column(String(255), nullable=True, index=True)
    external_open_id = Column(String(255), nullable=True, index=True)
    external_union_id = Column(String(255), nullable=True, index=True)
    tenant_key = Column(String(255), nullable=True, index=True)
    metadata_json = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="external_bindings")
    publication = relationship("AgentChannelPublication", back_populates="external_bindings")

    __table_args__ = (
        Index(
            "ux_user_external_bindings_publication_open_id",
            "publication_id",
            "external_open_id",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<UserExternalBinding(binding_id={self.binding_id}, user_id={self.user_id}, "
            f"publication_id={self.publication_id}, channel_type={self.channel_type})>"
        )


class ExternalConversationLink(Base):
    """Maps one external chat/thread identity to one LinX conversation."""

    __tablename__ = "external_conversation_links"

    link_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    publication_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_channel_publications.publication_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_chat_key = Column(String(255), nullable=False)
    external_thread_key = Column(String(255), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    publication = relationship("AgentChannelPublication", back_populates="external_links")
    conversation = relationship("AgentConversation", back_populates="external_links")

    __table_args__ = (
        Index(
            "ux_external_conversation_links_publication_chat_thread",
            "publication_id",
            "external_chat_key",
            "external_thread_key",
            unique=True,
        ),
    )

    def __repr__(self):
        return (
            f"<ExternalConversationLink(link_id={self.link_id}, publication_id={self.publication_id}, "
            f"conversation_id={self.conversation_id})>"
        )


class AgentSchedule(Base):
    """User-managed or agent-created schedules bound to one agent conversation."""

    __tablename__ = "agent_schedules"

    schedule_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    bound_conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    prompt_template = Column(Text, nullable=False)
    schedule_type = Column(String(16), nullable=False, index=True)  # once, recurring
    cron_expression = Column(String(100), nullable=True)
    run_at_utc = Column(DateTime(timezone=True), nullable=True, index=True)
    timezone = Column(String(100), nullable=False, default="UTC")
    status = Column(String(16), nullable=False, default="active", index=True)
    created_via = Column(String(32), nullable=False, default="manual_ui", index=True)
    origin_surface = Column(String(32), nullable=False, default="schedule_page", index=True)
    origin_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversation_messages.message_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    next_run_at = Column(DateTime(timezone=True), nullable=True, index=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_status = Column(String(16), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner = relationship("User", back_populates="schedules")
    agent = relationship("Agent", back_populates="schedules")
    bound_conversation = relationship(
        "AgentConversation",
        back_populates="schedules",
        foreign_keys=[bound_conversation_id],
    )
    origin_message = relationship("AgentConversationMessage", foreign_keys=[origin_message_id])
    runs = relationship(
        "AgentScheduleRun",
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="AgentScheduleRun.scheduled_for.desc()",
    )

    __table_args__ = (
        CheckConstraint(
            "schedule_type IN ('once', 'recurring')",
            name="ck_agent_schedules_type",
        ),
        CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'failed')",
            name="ck_agent_schedules_status",
        ),
        CheckConstraint(
            "(schedule_type <> 'once') OR (run_at_utc IS NOT NULL)",
            name="ck_agent_schedules_once_requires_run_at",
        ),
        CheckConstraint(
            "(schedule_type <> 'recurring') OR (cron_expression IS NOT NULL)",
            name="ck_agent_schedules_recurring_requires_cron",
        ),
        Index("idx_agent_schedules_owner_status", "owner_user_id", "status"),
        Index("idx_agent_schedules_next_run_status", "next_run_at", "status"),
        Index("idx_agent_schedules_agent_status", "agent_id", "status"),
    )

    def __repr__(self):
        return (
            f"<AgentSchedule(schedule_id={self.schedule_id}, agent_id={self.agent_id}, "
            f"status={self.status}, schedule_type={self.schedule_type})>"
        )


class AgentScheduleRun(Base):
    """One concrete execution attempt for a schedule."""

    __tablename__ = "agent_schedule_runs"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_schedules.schedule_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scheduled_for = Column(DateTime(timezone=True), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, default="queued", index=True)
    skip_reason = Column(String(255), nullable=True)
    error_message = Column(Text, nullable=True)
    assistant_message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversation_messages.message_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    conversation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_conversations.conversation_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    delivery_channel = Column(String(16), nullable=False, default="web")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    schedule = relationship("AgentSchedule", back_populates="runs")
    assistant_message = relationship("AgentConversationMessage", foreign_keys=[assistant_message_id])
    conversation = relationship("AgentConversation", back_populates="schedule_runs")

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_agent_schedule_runs_status",
        ),
        Index(
            "ux_agent_schedule_runs_schedule_scheduled_for",
            "schedule_id",
            "scheduled_for",
            unique=True,
        ),
        Index(
            "idx_agent_schedule_runs_status_scheduled",
            "status",
            "scheduled_for",
            "created_at",
        ),
    )

    def __repr__(self):
        return (
            f"<AgentScheduleRun(run_id={self.run_id}, schedule_id={self.schedule_id}, "
            f"status={self.status}, scheduled_for={self.scheduled_for})>"
        )


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
    skill_slug = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=False)
    source_kind = Column(String(32), nullable=False, default="manual", index=True)
    artifact_kind = Column(String(32), nullable=False, default="tool", index=True)
    runtime_mode = Column(String(32), nullable=False, default="tool", index=True)
    lifecycle_state = Column(String(32), nullable=False, default="active", index=True)

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
    access_level = Column(String(50), nullable=False, default="private", index=True)
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

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
    updated_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    active_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skill_revisions.revision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    department = relationship("Department")
    revisions = relationship(
        "SkillRevision",
        back_populates="skill",
        cascade="all, delete-orphan",
        foreign_keys="SkillRevision.skill_id",
    )
    active_revision = relationship(
        "SkillRevision",
        foreign_keys=[active_revision_id],
        post_update=True,
    )
    bindings = relationship("AgentSkillBinding", back_populates="skill")

    __table_args__ = (
        Index("idx_skills_access_level", "access_level"),
        Index("idx_skills_department_access", "department_id", "access_level"),
        Index("idx_skills_created_by_access", "created_by", "access_level"),
    )

    @property
    def name(self):
        return self.skill_slug

    @name.setter
    def name(self, value):
        self.skill_slug = value

    @property
    def slug(self):
        return self.skill_slug

    @slug.setter
    def slug(self, value):
        self.skill_slug = value

    @property
    def visibility(self):
        return self.access_level

    @visibility.setter
    def visibility(self, value):
        self.access_level = value

    @property
    def owner_user_id(self):
        return self.created_by

    @owner_user_id.setter
    def owner_user_id(self, value):
        self.created_by = value

    def __repr__(self):
        return (
            f"<Skill(skill_id={self.skill_id}, skill_slug={self.skill_slug}, "
            f"type={self.skill_type}, storage={self.storage_type}, version={self.version})>"
        )


class SkillRevision(Base):
    """Immutable skill revisions for canonical runtime loading."""

    __tablename__ = "skill_revisions"

    revision_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(String(50), nullable=False, default="1.0.0")
    review_state = Column(String(32), nullable=False, default="approved", index=True)
    instruction_md = Column(Text, nullable=True)
    tool_code = Column(Text, nullable=True)
    interface_definition = Column(JSONB, nullable=True)
    artifact_storage_kind = Column(String(32), nullable=False, default="inline")
    artifact_ref = Column(String(500), nullable=True)
    manifest = Column(JSONB, nullable=True)
    config = Column(JSONB, nullable=True)
    search_document = Column(Text, nullable=True)
    checksum = Column(String(128), nullable=True, index=True)
    change_note = Column(Text, nullable=True)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    skill = relationship(
        "Skill",
        back_populates="revisions",
        foreign_keys=[skill_id],
    )
    pinned_bindings = relationship("AgentSkillBinding", back_populates="revision_pin")

    __table_args__ = (
        Index("idx_skill_revisions_skill_created", "skill_id", "created_at"),
        Index("ux_skill_revisions_skill_version", "skill_id", "version", unique=True),
    )

    def __repr__(self):
        return (
            f"<SkillRevision(revision_id={self.revision_id}, skill_id={self.skill_id}, "
            f"version={self.version}, review_state={self.review_state})>"
        )


class AgentSkillBinding(Base):
    """Agent-to-skill binding metadata for canonical skill runtime selection."""

    __tablename__ = "agent_skill_bindings"

    binding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_pin_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skill_revisions.revision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    binding_mode = Column(String(32), nullable=False, default="doc", index=True)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    priority = Column(Integer, nullable=False, default=0)
    source = Column(String(32), nullable=False, default="manual", index=True)
    auto_update_policy = Column(String(32), nullable=False, default="follow_active")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent = relationship("Agent", back_populates="skill_bindings")
    skill = relationship("Skill", back_populates="bindings")
    revision_pin = relationship("SkillRevision", back_populates="pinned_bindings")

    __table_args__ = (
        Index("idx_agent_skill_bindings_agent_enabled", "agent_id", "enabled", "priority"),
        Index("ux_agent_skill_bindings_agent_skill", "agent_id", "skill_id", unique=True),
    )

    def __repr__(self):
        return (
            f"<AgentSkillBinding(binding_id={self.binding_id}, agent_id={self.agent_id}, "
            f"skill_id={self.skill_id}, mode={self.binding_mode}, enabled={self.enabled})>"
        )


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


class SessionLedger(Base):
    """Internal session provenance for extraction and rebuild."""

    __tablename__ = "session_ledgers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(String(255), nullable=False, unique=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    agent_id = Column(String(255), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ended_at = Column(DateTime(timezone=True), nullable=True, index=True)
    status = Column(String(32), nullable=False, default="completed", index=True)
    end_reason = Column(String(64), nullable=True, index=True)
    ledger_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_session_ledgers_agent_status", "agent_id", "status"),
        Index("idx_session_ledgers_user_started", "user_id", "started_at"),
    )

    @property
    def session_metadata(self):
        return self.ledger_metadata

    @session_metadata.setter
    def session_metadata(self, value):
        self.ledger_metadata = value

    def __repr__(self):
        return (
            f"<SessionLedger(id={self.id}, session_id={self.session_id}, "
            f"agent_id={self.agent_id}, user_id={self.user_id})>"
        )


class SessionLedgerEvent(Base):
    """Ordered event rows for one session ledger."""

    __tablename__ = "session_ledger_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_ledger_id = Column(
        BigInteger,
        ForeignKey("session_ledgers.id", ondelete="CASCADE"),
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
        Index("idx_session_ledger_events_session_order", "session_ledger_id", "event_index"),
    )

    @property
    def memory_session_id(self):
        return self.session_ledger_id

    @memory_session_id.setter
    def memory_session_id(self, value):
        self.session_ledger_id = value

    def __repr__(self):
        return (
            f"<SessionLedgerEvent(id={self.id}, session_ledger_id={self.session_ledger_id}, "
            f"kind={self.event_kind}, index={self.event_index})>"
        )


class UserMemoryEntry(Base):
    """Durable atomic user-memory facts."""

    __tablename__ = "user_memory_entries"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    entry_key = Column(String(255), nullable=False)
    fact_kind = Column(String(64), nullable=False, index=True)
    canonical_text = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    predicate = Column(String(255), nullable=True)
    object_text = Column(Text, nullable=True)
    event_time = Column(String(255), nullable=True)
    event_time_start = Column(DateTime(timezone=True), nullable=True, index=True)
    event_time_end = Column(DateTime(timezone=True), nullable=True, index=True)
    location = Column(String(255), nullable=True)
    persons = Column(JSONB, nullable=True)
    entities = Column(JSONB, nullable=True)
    topic = Column(String(255), nullable=True)
    confidence = Column(Float, nullable=False, default=0.7)
    importance = Column(Float, nullable=False, default=0.5)
    status = Column(String(32), nullable=False, default="active", index=True)
    source_session_ledger_id = Column(
        BigInteger,
        ForeignKey("session_ledgers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_event_indexes = Column(JSONB, nullable=True)
    entry_data = Column(JSONB, nullable=True)
    search_vector = Column(TSVector(), nullable=True)
    vector_sync_state = Column(String(32), nullable=False, default="pending", index=True)
    vector_document_hash = Column(String(64), nullable=True)
    vector_collection_name = Column(String(255), nullable=True)
    vector_indexed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    vector_error = Column(Text, nullable=True)
    superseded_by_id = Column(
        BigInteger,
        ForeignKey("user_memory_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_user_memory_entries_user_fact_status", "user_id", "fact_kind", "status"),
        Index("idx_user_memory_entries_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "idx_user_memory_entries_canonical_text_trgm",
            "canonical_text",
            postgresql_using="gin",
            postgresql_ops={"canonical_text": "gin_trgm_ops"},
        ),
        Index(
            "idx_user_memory_entries_vector_sync",
            "user_id",
            "status",
            "vector_sync_state",
            "vector_indexed_at",
        ),
        Index(
            "idx_user_memory_entries_vector_collection",
            "vector_collection_name",
            "vector_sync_state",
        ),
        Index("ux_user_memory_entries_user_key", "user_id", "entry_key", unique=True),
    )

    @property
    def owner_type(self):
        return "user"

    @property
    def owner_id(self):
        return self.user_id

    @owner_id.setter
    def owner_id(self, value):
        self.user_id = str(value) if value is not None else None

    @property
    def entry_type(self):
        return "user_fact"

    @property
    def details(self):
        payload = self.entry_data if isinstance(self.entry_data, dict) else {}
        return str(payload.get("details") or "").strip() or None

    @details.setter
    def details(self, value):
        payload = dict(self.entry_data or {})
        if value:
            payload["details"] = value
        else:
            payload.pop("details", None)
        self.entry_data = payload

    @property
    def source_session_id(self):
        return self.source_session_ledger_id

    @source_session_id.setter
    def source_session_id(self, value):
        self.source_session_ledger_id = value

    @property
    def source_observation_id(self):
        return None

    @source_observation_id.setter
    def source_observation_id(self, value):
        return None

    def __repr__(self):
        return (
            f"<UserMemoryEntry(id={self.id}, user_id={self.user_id}, "
            f"fact_kind={self.fact_kind}, key={self.entry_key})>"
        )


class UserMemoryLink(Base):
    """Lineage and supersession links across user-memory entries."""

    __tablename__ = "user_memory_links"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    source_entry_id = Column(
        BigInteger,
        ForeignKey("user_memory_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_entry_id = Column(
        BigInteger,
        ForeignKey("user_memory_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    link_type = Column(String(64), nullable=False, index=True)
    link_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("idx_user_memory_links_source", "user_id", "source_entry_id", "link_type"),
        Index("idx_user_memory_links_target", "user_id", "target_entry_id", "link_type"),
        Index(
            "ux_user_memory_links_identity",
            "user_id",
            "source_entry_id",
            "target_entry_id",
            "link_type",
            unique=True,
        ),
    )

    @property
    def source_kind(self):
        return "entry"

    @property
    def source_id(self):
        return self.source_entry_id

    @source_id.setter
    def source_id(self, value):
        self.source_entry_id = value

    @property
    def target_kind(self):
        return "entry"

    @property
    def target_id(self):
        return self.target_entry_id

    @target_id.setter
    def target_id(self, value):
        self.target_entry_id = value

    @property
    def source_session_id(self):
        return None

    @source_session_id.setter
    def source_session_id(self, value):
        return None

    def __repr__(self):
        return (
            f"<UserMemoryLink(id={self.id}, user_id={self.user_id}, "
            f"source={self.source_entry_id}, target={self.target_entry_id}, type={self.link_type})>"
        )


class UserMemoryRelation(Base):
    """Typed user-memory relationship edges stored independently from fact entries."""

    __tablename__ = "user_memory_relations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    relation_key = Column(String(255), nullable=False)
    predicate = Column(String(64), nullable=False, index=True)
    subject_type = Column(String(32), nullable=False, default="user")
    subject_text = Column(String(255), nullable=True)
    object_text = Column(Text, nullable=False)
    canonical_text = Column(Text, nullable=False)
    event_time = Column(String(255), nullable=True)
    event_time_start = Column(DateTime(timezone=True), nullable=True, index=True)
    event_time_end = Column(DateTime(timezone=True), nullable=True, index=True)
    location = Column(String(255), nullable=True)
    persons = Column(JSONB, nullable=True)
    entities = Column(JSONB, nullable=True)
    confidence = Column(Float, nullable=False, default=0.7)
    importance = Column(Float, nullable=False, default=0.5)
    status = Column(String(32), nullable=False, default="active", index=True)
    source_entry_id = Column(
        BigInteger,
        ForeignKey("user_memory_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_session_ledger_id = Column(
        BigInteger,
        ForeignKey("session_ledgers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    relation_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_user_memory_relations_user_predicate", "user_id", "predicate", "status"),
        Index("ux_user_memory_relations_user_key", "user_id", "relation_key", unique=True),
        Index(
            "idx_user_memory_relations_object_text_trgm",
            "object_text",
            postgresql_using="gin",
            postgresql_ops={"object_text": "gin_trgm_ops"},
        ),
    )

    def __repr__(self):
        return (
            f"<UserMemoryRelation(id={self.id}, user_id={self.user_id}, "
            f"predicate={self.predicate}, key={self.relation_key})>"
        )


class UserMemoryView(Base):
    """Stable user-memory projections for profile and episode surfaces."""

    __tablename__ = "user_memory_views"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    view_type = Column(String(64), nullable=False, index=True)
    view_key = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    view_data = Column(JSONB, nullable=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    search_vector = Column(TSVector(), nullable=True)
    vector_sync_state = Column(String(32), nullable=False, default="pending", index=True)
    vector_document_hash = Column(String(64), nullable=True)
    vector_collection_name = Column(String(255), nullable=True)
    vector_indexed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    vector_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_user_memory_views_user_type", "user_id", "view_type", "status"),
        Index("idx_user_memory_views_search_vector", "search_vector", postgresql_using="gin"),
        Index(
            "idx_user_memory_views_content_trgm",
            "content",
            postgresql_using="gin",
            postgresql_ops={"content": "gin_trgm_ops"},
        ),
        Index(
            "idx_user_memory_views_vector_sync",
            "user_id",
            "view_type",
            "status",
            "vector_sync_state",
            "vector_indexed_at",
        ),
        Index(
            "idx_user_memory_views_vector_collection",
            "vector_collection_name",
            "vector_sync_state",
        ),
        Index("ux_user_memory_views_user_key", "user_id", "view_type", "view_key", unique=True),
    )

    @property
    def owner_type(self):
        return "user"

    @property
    def owner_id(self):
        return self.user_id

    @owner_id.setter
    def owner_id(self, value):
        self.user_id = str(value) if value is not None else None

    @property
    def summary(self):
        return self.content

    @summary.setter
    def summary(self, value):
        self.content = str(value) if value is not None else ""

    @property
    def details(self):
        payload = self.view_data if isinstance(self.view_data, dict) else {}
        return str(payload.get("details") or "").strip() or None

    @details.setter
    def details(self, value):
        payload = dict(self.view_data or {})
        if value:
            payload["details"] = value
        else:
            payload.pop("details", None)
        self.view_data = payload

    @property
    def source_session_id(self):
        return None

    @source_session_id.setter
    def source_session_id(self, value):
        return None

    @property
    def source_observation_id(self):
        return None

    @source_observation_id.setter
    def source_observation_id(self, value):
        return None

    def __repr__(self):
        return (
            f"<UserMemoryView(id={self.id}, user_id={self.user_id}, "
            f"view_type={self.view_type}, key={self.view_key})>"
        )


class UserMemoryEmbeddingJob(Base):
    """DB-backed background jobs for user-memory vector indexing."""

    __tablename__ = "user_memory_embedding_jobs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    job_key = Column(String(255), nullable=False, unique=True, index=True)
    source_kind = Column(String(16), nullable=False, index=True)
    source_id = Column(BigInteger, nullable=True, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    operation = Column(String(16), nullable=False)
    collection_name = Column(String(255), nullable=False)
    embedding_signature = Column(String(255), nullable=False)
    payload = Column(JSONB, nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by = Column(String(128), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index(
            "idx_user_memory_embedding_jobs_claim",
            "status",
            "available_at",
            "id",
        ),
        Index(
            "idx_user_memory_embedding_jobs_user_status",
            "user_id",
            "status",
            "created_at",
        ),
        Index(
            "idx_user_memory_embedding_jobs_source_status",
            "source_kind",
            "source_id",
            "status",
        ),
    )

    def __repr__(self):
        return (
            f"<UserMemoryEmbeddingJob(id={self.id}, key={self.job_key}, "
            f"status={self.status}, user_id={self.user_id})>"
        )


class SkillCandidate(Base):
    """Learned skill candidates extracted from successful sessions."""

    __tablename__ = "skill_candidates"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    agent_id = Column(String(255), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)
    cluster_key = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    goal = Column(Text, nullable=False)
    successful_path = Column(JSONB, nullable=False)
    why_it_worked = Column(Text, nullable=True)
    applicability = Column(Text, nullable=True)
    avoid = Column(Text, nullable=True)
    evidence_session_ledger_id = Column(
        BigInteger,
        ForeignKey("session_ledgers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    confidence = Column(Float, nullable=False, default=0.72)
    review_status = Column(String(32), nullable=False, default="pending", index=True)
    candidate_status = Column(String(32), nullable=False, default="new", index=True)
    review_note = Column(Text, nullable=True)
    promoted_skill_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skills.skill_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    promoted_revision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skill_revisions.revision_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    candidate_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_skill_candidates_agent_review", "agent_id", "review_status"),
        Index("idx_skill_candidates_agent_status", "agent_id", "candidate_status"),
        Index("idx_skill_candidates_user_created", "user_id", "created_at"),
        Index("ux_skill_candidates_agent_key", "agent_id", "cluster_key", unique=True),
    )

    @property
    def owner_type(self):
        return "agent"

    @property
    def owner_id(self):
        return self.agent_id

    @owner_id.setter
    def owner_id(self, value):
        self.agent_id = str(value) if value is not None else None

    @property
    def summary(self):
        return self.why_it_worked

    @summary.setter
    def summary(self, value):
        self.why_it_worked = str(value) if value else None

    @property
    def details(self):
        payload = self.candidate_data if isinstance(self.candidate_data, dict) else {}
        return str(payload.get("review_content") or "").strip() or None

    @details.setter
    def details(self, value):
        payload = dict(self.candidate_data or {})
        if value:
            payload["review_content"] = value
        else:
            payload.pop("review_content", None)
        self.candidate_data = payload

    @property
    def candidate_payload(self):
        payload = dict(self.candidate_data or {})
        payload.setdefault("goal", self.goal)
        payload.setdefault("successful_path", list(self.successful_path or []))
        payload.setdefault("why_it_worked", self.why_it_worked)
        payload.setdefault("applicability", self.applicability)
        payload.setdefault("avoid", self.avoid)
        payload.setdefault("confidence", self.confidence)
        payload.setdefault("review_status", self.review_status)
        payload.setdefault("candidate_status", self.candidate_status)
        if self.promoted_skill_id is not None:
            payload.setdefault("promoted_skill_id", str(self.promoted_skill_id))
        if self.promoted_revision_id is not None:
            payload.setdefault("promoted_revision_id", str(self.promoted_revision_id))
        return payload

    @candidate_payload.setter
    def candidate_payload(self, value):
        payload = dict(value or {})
        self.goal = str(payload.get("goal") or self.goal or self.title)
        self.successful_path = list(payload.get("successful_path") or self.successful_path or [])
        why = payload.get("why_it_worked")
        self.why_it_worked = str(why) if why else None
        applicability = payload.get("applicability")
        self.applicability = str(applicability) if applicability else None
        avoid = payload.get("avoid")
        self.avoid = str(avoid) if avoid else None
        confidence = payload.get("confidence")
        if confidence is not None:
            try:
                self.confidence = float(confidence)
            except (TypeError, ValueError):
                pass
        review_status = str(payload.get("review_status") or "").strip().lower()
        if review_status in {"pending", "published", "rejected"}:
            self.review_status = review_status
        candidate_status = str(payload.get("candidate_status") or "").strip().lower()
        if candidate_status in {"new", "merged", "promoted", "rejected", "expired"}:
            self.candidate_status = candidate_status
        self.candidate_data = payload

    @property
    def status(self):
        return self.candidate_status or "new"

    @status.setter
    def status(self, value):
        normalized = str(value or "").strip().lower()
        if normalized in {"promoted", "active"}:
            self.review_status = "published"
            self.candidate_status = "promoted"
        elif normalized == "merged":
            self.review_status = "pending"
            self.candidate_status = "merged"
        elif normalized == "rejected":
            self.review_status = "rejected"
            self.candidate_status = "rejected"
        elif normalized == "expired":
            self.review_status = "pending"
            self.candidate_status = "expired"
        else:
            self.review_status = "pending"
            self.candidate_status = "new"

    @property
    def candidate_id(self):
        return self.id

    @property
    def source_agent_id(self):
        return self.agent_id

    @source_agent_id.setter
    def source_agent_id(self, value):
        self.agent_id = str(value) if value is not None else None

    @property
    def source_session_id(self):
        return self.evidence_session_ledger_id

    @source_session_id.setter
    def source_session_id(self, value):
        self.evidence_session_ledger_id = value

    @property
    def source_observation_id(self):
        return None

    @source_observation_id.setter
    def source_observation_id(self, value):
        return None

    def __repr__(self):
        return (
            f"<SkillCandidate(id={self.id}, agent_id={self.agent_id}, "
            f"cluster_key={self.cluster_key}, candidate_status={self.candidate_status})>"
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
