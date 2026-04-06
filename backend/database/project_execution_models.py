"""SQLAlchemy models for the project execution platform skeleton.

Defines DB-backed entities for projects, plans, runs, steps, nodes,
project spaces, extensions, skill packages, and audit events.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from database.models import Base


class Project(Base):
    """Top-level project record for execution workflows."""

    __tablename__ = "projects"

    project_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="draft", index=True)
    configuration = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    creator = relationship("User")
    tasks = relationship(
        "ProjectTask",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    plans = relationship(
        "ProjectPlan",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    runs = relationship(
        "ProjectRun",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    project_space = relationship(
        "ProjectSpace",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
    execution_nodes = relationship(
        "ExecutionNode",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    skill_packages = relationship(
        "ProjectSkillPackage",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    extension_packages = relationship(
        "ProjectExtensionPackage",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_events = relationship("ProjectAuditEvent", back_populates="project")
    agent_bindings = relationship(
        "ProjectAgentBinding",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    provisioning_profiles = relationship(
        "AgentProvisioningProfile",
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_project_creator_status", "created_by_user_id", "status"),
        Index("idx_project_created_at", "created_at"),
    )


class ProjectPlan(Base):
    """Execution plan versions for a project."""

    __tablename__ = "project_plans"

    plan_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="SET NULL"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False, index=True)
    goal = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="draft", index=True)
    version = Column(Integer, nullable=False, default=1)
    definition = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="plans")
    creator = relationship("User")
    tasks = relationship("ProjectTask", back_populates="plan")
    runs = relationship("ProjectRun", back_populates="plan")
    nodes = relationship("ExecutionNode", back_populates="plan")

    __table_args__ = (
        Index("idx_project_plan_project_status", "project_id", "status"),
        Index("idx_project_plan_project_version", "project_id", "version"),
    )


class ProjectRun(Base):
    """Project execution run instances."""

    __tablename__ = "project_runs"

    run_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_plans.plan_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(50), nullable=False, default="queued", index=True)
    trigger_source = Column(String(50), nullable=False, default="manual")
    runtime_context = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    requested_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="runs")
    plan = relationship("ProjectPlan", back_populates="runs")
    requester = relationship("User")
    steps = relationship(
        "ProjectRunStep",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_events = relationship("ProjectAuditEvent", back_populates="run")
    tasks = relationship("ProjectTask", back_populates="run")
    leases = relationship("ExecutionLease", back_populates="run", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (
        Index("idx_project_run_project_status", "project_id", "status"),
        Index("idx_project_run_created_at", "created_at"),
    )


class ProjectTask(Base):
    """Task records scoped to a project and optionally to a plan/run."""

    __tablename__ = "project_tasks"

    project_task_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_plans.plan_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    assignee_agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=False, default="pending", index=True)
    priority = Column(String(50), nullable=False, default="normal")
    sort_order = Column(Integer, nullable=False, default=0)
    input_payload = Column(JSONB, nullable=False, default=dict)
    output_payload = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="tasks")
    plan = relationship("ProjectPlan", back_populates="tasks")
    run = relationship("ProjectRun", back_populates="tasks")
    assigned_agent = relationship("Agent")
    creator = relationship("User")
    steps = relationship("ProjectRunStep", back_populates="project_task")

    __table_args__ = (
        Index("idx_project_task_project_status", "project_id", "status"),
        Index("idx_project_task_project_sort", "project_id", "sort_order"),
    )


class ProjectRunStep(Base):
    """Step-level records within a run."""

    __tablename__ = "project_run_steps"

    run_step_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(255), nullable=False)
    step_type = Column(String(50), nullable=False, default="task")
    status = Column(String(50), nullable=False, default="pending", index=True)
    sequence_number = Column(Integer, nullable=False, default=0)
    input_payload = Column(JSONB, nullable=False, default=dict)
    output_payload = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    run = relationship("ProjectRun", back_populates="steps")
    project_task = relationship("ProjectTask", back_populates="steps")
    node = relationship("ExecutionNode", back_populates="steps")
    leases = relationship("ExecutionLease", back_populates="step")

    __table_args__ = (
        Index("idx_project_run_step_run_status", "run_id", "status"),
        Index("idx_project_run_step_run_sequence", "run_id", "sequence_number"),
    )


class ProjectSpace(Base):
    """Workspace or repo context associated with a project."""

    __tablename__ = "project_spaces"

    project_space_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    storage_uri = Column(String(500), nullable=True)
    branch_name = Column(String(255), nullable=True)
    status = Column(String(50), nullable=False, default="provisioning", index=True)
    root_path = Column(String(500), nullable=True)
    space_metadata = Column(JSONB, nullable=False, default=dict)
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="project_space")


class ExecutionNode(Base):
    """Execution-capable node metadata for project runs."""

    __tablename__ = "execution_nodes"

    node_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_plans.plan_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(255), nullable=False, index=True)
    node_type = Column(String(50), nullable=False, default="worker")
    status = Column(String(50), nullable=False, default="available", index=True)
    capabilities = Column(ARRAY(String()), nullable=False, default=list)
    config = Column(JSONB, nullable=False, default=dict)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="execution_nodes")
    plan = relationship("ProjectPlan", back_populates="nodes")
    steps = relationship("ProjectRunStep", back_populates="node")
    leases = relationship("ExecutionLease", back_populates="node", cascade="all, delete-orphan", passive_deletes=True)
    external_agent_sessions = relationship("ExternalAgentSession", back_populates="node", cascade="all, delete-orphan", passive_deletes=True)

    __table_args__ = (Index("idx_execution_node_project_status", "project_id", "status"),)


class ExecutionLease(Base):
    """Lease for dispatching one run step to an execution node."""

    __tablename__ = "execution_leases"

    lease_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_step_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_run_steps.run_step_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String(32), nullable=False, default="pending", index=True)
    lease_payload = Column(JSONB, nullable=False, default=dict)
    result_payload = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    acked_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    project = relationship("Project")
    node = relationship("ExecutionNode", back_populates="leases")
    run = relationship("ProjectRun", back_populates="leases")
    step = relationship("ProjectRunStep", back_populates="leases")

    __table_args__ = (
        Index("idx_execution_lease_node_status", "node_id", "status"),
        Index("idx_execution_lease_run_step", "run_step_id", unique=True),
    )


class ProjectAgentBinding(Base):
    """Project-scoped pool of agents eligible for automatic assignment."""

    __tablename__ = "project_agent_bindings"

    binding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role_hint = Column(String(100), nullable=True)
    priority = Column(Integer, nullable=False, default=0, index=True)
    status = Column(String(32), nullable=False, default="active", index=True)
    allowed_step_kinds = Column(ARRAY(String), nullable=False, default=list)
    preferred_skills = Column(ARRAY(String), nullable=False, default=list)
    preferred_runtime_types = Column(ARRAY(String), nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="agent_bindings")
    agent = relationship("Agent")

    __table_args__ = (
        Index("idx_project_agent_binding_project_status", "project_id", "status"),
        Index("idx_project_agent_binding_project_agent", "project_id", "agent_id", unique=True),
    )


class AgentProvisioningProfile(Base):
    """Project-scoped defaults for automatic ephemeral agent provisioning."""

    __tablename__ = "agent_provisioning_profiles"

    profile_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_kind = Column(String(50), nullable=False, index=True)
    agent_type = Column(String(100), nullable=False)
    template_id = Column(String(255), nullable=True)
    default_skill_ids = Column(ARRAY(String), nullable=False, default=list)
    default_provider = Column(String(100), nullable=True)
    default_model = Column(String(255), nullable=True)
    temperature = Column(Float, nullable=True, default=0.2)
    max_tokens = Column(Integer, nullable=True, default=4000)
    sandbox_mode = Column(String(50), nullable=False, default="run_shared")
    ephemeral = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="provisioning_profiles")

    __table_args__ = (
        Index("idx_agent_provisioning_project_step_kind", "project_id", "step_kind", unique=True),
    )


class AgentRuntimeBinding(Base):
    """Runtime binding that determines where/how an agent executes."""

    __tablename__ = "agent_runtime_bindings"

    runtime_binding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_type = Column(String(50), nullable=False, index=True)
    execution_node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    workspace_strategy = Column(String(50), nullable=True)
    path_allowlist = Column(ARRAY(String), nullable=False, default=list)
    status = Column(String(32), nullable=False, default="active", index=True)
    config = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    agent = relationship("Agent")
    execution_node = relationship("ExecutionNode")

    __table_args__ = (
        Index("idx_agent_runtime_binding_agent_status", "agent_id", "status"),
    )


class ExternalAgentSession(Base):
    """One external-agent execution session backed by an execution node."""

    __tablename__ = "external_agent_sessions"

    session_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    execution_node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_step_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_run_steps.run_step_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    runtime_type = Column(String(50), nullable=False, index=True)
    workdir = Column(String(500), nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    lease_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_leases.lease_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    session_metadata = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    agent = relationship("Agent")
    node = relationship("ExecutionNode", back_populates="external_agent_sessions")
    project = relationship("Project")
    run = relationship("ProjectRun")
    step = relationship("ProjectRunStep")
    lease = relationship("ExecutionLease")

    __table_args__ = (
        Index("idx_external_agent_session_node_status", "execution_node_id", "status"),
        Index("idx_external_agent_session_run_step", "run_step_id"),
    )


class ProjectSkillPackage(Base):
    """Imported skill packages for project execution."""

    __tablename__ = "project_skill_packages"

    skill_package_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name = Column(String(255), nullable=False, index=True)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    source_uri = Column(String(500), nullable=True)
    status = Column(String(50), nullable=False, default="imported", index=True)
    manifest = Column(JSONB, nullable=False, default=dict)
    test_result = Column(JSONB, nullable=False, default=dict)
    imported_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_tested_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="skill_packages")
    importer = relationship("User")

    __table_args__ = (Index("idx_project_skill_package_project_status", "project_id", "status"),)


class ProjectExtensionPackage(Base):
    """Installed extension packages supporting project execution."""

    __tablename__ = "project_extension_packages"

    extension_package_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False, index=True)
    package_type = Column(String(50), nullable=False, default="tooling")
    source_uri = Column(String(500), nullable=True)
    status = Column(String(50), nullable=False, default="installed", index=True)
    manifest = Column(JSONB, nullable=False, default=dict)
    installed_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project", back_populates="extension_packages")
    installer = relationship("User")

    __table_args__ = (Index("idx_project_extension_project_status", "project_id", "status"),)


class ProjectAuditEvent(Base):
    """Append-only audit trail for the project execution slice."""

    __tablename__ = "project_audit_events"

    audit_event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resource_type = Column(String(100), nullable=False, index=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    actor_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    project = relationship("Project", back_populates="audit_events")
    run = relationship("ProjectRun", back_populates="audit_events")
    actor = relationship("User")

    __table_args__ = (
        Index("idx_project_audit_project_created", "project_id", "created_at"),
        Index("idx_project_audit_resource", "resource_type", "resource_id"),
    )


class UserNotification(Base):
    """User notifications for the project execution platform."""

    __tablename__ = "user_notifications"

    notification_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
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

    user = relationship("User")

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
