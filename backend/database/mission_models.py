"""SQLAlchemy models for Mission Execution System.

Defines Mission, MissionAttachment, MissionAgent, and MissionEvent tables
for structured goal-to-deliverable execution with agent coordination.
"""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.models import Base


class Mission(Base):
    """Missions table.

    Stores mission definitions with lifecycle state, agent assignments,
    workspace references, and progress tracking.
    """

    __tablename__ = "missions"

    mission_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False, index=True)
    instructions = Column(Text, nullable=False)
    requirements_doc = Column(Text, nullable=True)
    status = Column(
        String(50), nullable=False, default="draft", index=True
    )  # draft/requirements/planning/executing/reviewing/qa/completed/failed/cancelled
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id = Column(
        UUID(as_uuid=True),
        ForeignKey("departments.department_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    container_id = Column(String(255), nullable=True)
    workspace_bucket = Column(String(255), nullable=True)
    mission_config = Column(JSONB, nullable=True)
    result = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    total_tasks = Column(Integer, nullable=False, default=0)
    completed_tasks = Column(Integer, nullable=False, default=0)
    failed_tasks = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    creator = relationship("User")
    department = relationship("Department")
    attachments = relationship(
        "MissionAttachment",
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    agents = relationship(
        "MissionAgent",
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    events = relationship(
        "MissionEvent",
        back_populates="mission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    tasks = relationship("Task", back_populates="mission")

    # Indexes
    __table_args__ = (
        Index("idx_mission_user_status", "created_by_user_id", "status"),
        Index("idx_mission_created_at", "created_at"),
    )

    def __repr__(self):
        return (
            f"<Mission(mission_id={self.mission_id}, "
            f"title={self.title}, status={self.status})>"
        )


class MissionAttachment(Base):
    """Mission attachments table.

    Stores file references uploaded as context for a mission.
    """

    __tablename__ = "mission_attachments"

    attachment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("missions.mission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename = Column(String(500), nullable=False)
    file_reference = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    mission = relationship("Mission", back_populates="attachments")

    def __repr__(self):
        return (
            f"<MissionAttachment(attachment_id={self.attachment_id}, "
            f"filename={self.filename})>"
        )


class MissionAgent(Base):
    """Mission agents table.

    Maps agents to missions with role and status tracking.
    """

    __tablename__ = "mission_agents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("missions.mission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(50), nullable=False)  # leader, worker, reviewer
    status = Column(String(50), nullable=False, default="assigned")  # assigned, active, completed
    is_temporary = Column(Boolean, nullable=False, default=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    mission = relationship("Mission", back_populates="agents")
    agent = relationship("Agent")

    # Indexes
    __table_args__ = (
        Index("idx_mission_agent_unique", "mission_id", "agent_id", unique=True),
    )

    def __repr__(self):
        return (
            f"<MissionAgent(id={self.id}, mission_id={self.mission_id}, "
            f"agent_id={self.agent_id}, role={self.role})>"
        )


class MissionEvent(Base):
    """Mission events table.

    Stores an append-only log of mission lifecycle events for
    real-time streaming and audit trail.
    """

    __tablename__ = "mission_events"

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mission_id = Column(
        UUID(as_uuid=True),
        ForeignKey("missions.mission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(100), nullable=False, index=True)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("tasks.task_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_data = Column(JSONB, nullable=True)
    message = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    mission = relationship("Mission", back_populates="events")
    agent = relationship("Agent")
    task = relationship("Task")

    # Indexes
    __table_args__ = (
        Index("idx_event_mission_type", "mission_id", "event_type"),
        Index("idx_event_mission_created", "mission_id", "created_at"),
    )

    def __repr__(self):
        return (
            f"<MissionEvent(event_id={self.event_id}, "
            f"event_type={self.event_type}, mission_id={self.mission_id})>"
        )


class MissionSettings(Base):
    """Per-user default settings for mission execution.

    Stores default LLM configurations for each mission role
    and execution parameters.
    """

    __tablename__ = "mission_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    leader_config = Column(JSONB, nullable=False, default=dict)
    supervisor_config = Column(JSONB, nullable=False, default=dict)
    qa_config = Column(JSONB, nullable=False, default=dict)
    execution_config = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user = relationship("User")

    def __repr__(self):
        return f"<MissionSettings(id={self.id}, user_id={self.user_id})>"


class UserNotification(Base):
    """Persisted per-user notification center records.

    This table backs a commercial-grade notification center with unread/read
    state, offline catch-up, and action deep links.
    """

    __tablename__ = "user_notifications"

    notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
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
    notification_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="info")
    title = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    action_url = Column(String(500), nullable=True)
    action_label = Column(String(100), nullable=True)
    notification_metadata = Column(JSONB, nullable=True)
    dedupe_key = Column(String(255), nullable=True, index=True)
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User")
    mission = relationship("Mission")

    __table_args__ = (
        Index("idx_user_notifications_user_created", "user_id", "created_at"),
        Index("idx_user_notifications_user_unread_created", "user_id", "is_read", "created_at"),
        Index(
            "idx_user_notifications_user_type_created",
            "user_id",
            "notification_type",
            "created_at",
        ),
    )

    def __repr__(self):
        return (
            f"<UserNotification(notification_id={self.notification_id}, "
            f"user_id={self.user_id}, type={self.notification_type}, is_read={self.is_read})>"
        )
