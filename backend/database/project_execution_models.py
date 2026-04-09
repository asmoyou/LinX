"""SQLAlchemy models for the project execution platform skeleton.

Defines DB-backed entities for projects, plans, runs, steps,
project spaces, extensions, skill packages, audit events, and external runtimes.
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
    status = Column(String(50), nullable=False, default="planning", index=True)
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
    execution_nodes = relationship(
        "ExecutionNode",
        back_populates="run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    audit_events = relationship("ProjectAuditEvent", back_populates="run")
    tasks = relationship("ProjectTask", back_populates="run")
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
    contracts = relationship(
        "ProjectTaskContract",
        back_populates="project_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectTaskContract.version.desc()",
    )
    dependencies = relationship(
        "ProjectTaskDependency",
        back_populates="project_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="ProjectTaskDependency.project_task_id",
    )
    reverse_dependencies = relationship(
        "ProjectTaskDependency",
        back_populates="depends_on_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="ProjectTaskDependency.depends_on_project_task_id",
    )
    handoffs = relationship(
        "ProjectTaskHandoff",
        back_populates="project_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectTaskHandoff.created_at.desc()",
    )
    change_bundles = relationship(
        "ProjectTaskChangeBundle",
        back_populates="project_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectTaskChangeBundle.created_at.desc()",
    )
    evidence_bundles = relationship(
        "ProjectTaskEvidenceBundle",
        back_populates="project_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectTaskEvidenceBundle.created_at.desc()",
    )
    review_issues = relationship(
        "ProjectTaskReviewIssue",
        back_populates="project_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProjectTaskReviewIssue.created_at.desc()",
    )
    execution_nodes = relationship(
        "ExecutionNode",
        back_populates="project_task",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("idx_project_task_project_status", "project_id", "status"),
        Index("idx_project_task_project_sort", "project_id", "sort_order"),
    )


class ProjectTaskContract(Base):
    """Compiled contract for one project task."""

    __tablename__ = "project_task_contracts"

    contract_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version = Column(Integer, nullable=False, default=1)
    goal = Column(Text, nullable=True)
    scope = Column(JSONB, nullable=False, default=list)
    constraints = Column(JSONB, nullable=False, default=list)
    deliverables = Column(JSONB, nullable=False, default=list)
    acceptance_criteria = Column(JSONB, nullable=False, default=list)
    assumptions = Column(JSONB, nullable=False, default=list)
    evidence_required = Column(JSONB, nullable=False, default=list)
    allowed_surface = Column(JSONB, nullable=False, default=dict)
    source_description_hash = Column(String(64), nullable=True, index=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project_task = relationship("ProjectTask", back_populates="contracts")
    creator = relationship("User")

    __table_args__ = (
        Index("idx_project_task_contract_task_version", "project_task_id", "version", unique=True),
        Index("idx_project_task_contract_task_created", "project_task_id", "created_at"),
    )


class ProjectTaskDependency(Base):
    """Explicit dependency edge between project tasks."""

    __tablename__ = "project_task_dependencies"

    dependency_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    depends_on_project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    required_state = Column(String(32), nullable=False, default="approved", index=True)
    dependency_type = Column(String(32), nullable=False, default="hard", index=True)
    artifact_selector = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project_task = relationship(
        "ProjectTask",
        back_populates="dependencies",
        foreign_keys=[project_task_id],
    )
    depends_on_task = relationship(
        "ProjectTask",
        back_populates="reverse_dependencies",
        foreign_keys=[depends_on_project_task_id],
    )
    creator = relationship("User")

    __table_args__ = (
        Index(
            "idx_project_task_dependency_edge",
            "project_task_id",
            "depends_on_project_task_id",
            unique=True,
        ),
        Index("idx_project_task_dependency_task", "project_task_id", "required_state"),
    )


class ProjectTaskHandoff(Base):
    """Structured handoff between stages and owners for one task."""

    __tablename__ = "project_task_handoffs"

    handoff_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    stage = Column(String(64), nullable=False, index=True)
    from_actor = Column(String(128), nullable=False, index=True)
    to_actor = Column(String(128), nullable=True, index=True)
    status_from = Column(String(50), nullable=True, index=True)
    status_to = Column(String(50), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project_task = relationship("ProjectTask", back_populates="handoffs")
    run = relationship("ProjectRun")
    execution_node = relationship("ExecutionNode")
    creator = relationship("User")

    __table_args__ = (
        Index("idx_project_task_handoff_task_created", "project_task_id", "created_at"),
        Index("idx_project_task_handoff_task_stage", "project_task_id", "stage"),
    )


class ProjectTaskChangeBundle(Base):
    """Structured change bundle representing one task delivery snapshot."""

    __tablename__ = "project_task_change_bundles"

    change_bundle_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    bundle_kind = Column(String(32), nullable=False, default="patchset", index=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    base_ref = Column(String(255), nullable=True)
    head_ref = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    commit_count = Column(Integer, nullable=False, default=0)
    changed_files = Column(JSONB, nullable=False, default=list)
    artifact_manifest = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project_task = relationship("ProjectTask", back_populates="change_bundles")
    run = relationship("ProjectRun")
    execution_node = relationship("ExecutionNode")
    creator = relationship("User")

    __table_args__ = (
        Index("idx_project_task_change_bundle_task_created", "project_task_id", "created_at"),
        Index("idx_project_task_change_bundle_task_status", "project_task_id", "status"),
    )


class ProjectTaskEvidenceBundle(Base):
    """Structured evidence collected for one task delivery/review cycle."""

    __tablename__ = "project_task_evidence_bundles"

    evidence_bundle_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    summary = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="collected", index=True)
    bundle = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project_task = relationship("ProjectTask", back_populates="evidence_bundles")
    run = relationship("ProjectRun")
    execution_node = relationship("ExecutionNode")
    creator = relationship("User")

    __table_args__ = (
        Index("idx_project_task_evidence_task_created", "project_task_id", "created_at"),
        Index("idx_project_task_evidence_task_status", "project_task_id", "status"),
    )


class ProjectTaskReviewIssue(Base):
    """Structured review issue linked to one task."""

    __tablename__ = "project_task_review_issues"

    review_issue_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_bundle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_task_change_bundles.change_bundle_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    evidence_bundle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_task_evidence_bundles.evidence_bundle_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    handoff_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_task_handoffs.handoff_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    issue_key = Column(String(128), nullable=True, index=True)
    severity = Column(String(32), nullable=False, default="medium", index=True)
    category = Column(String(32), nullable=False, default="other", index=True)
    acceptance_ref = Column(String(128), nullable=True)
    summary = Column(Text, nullable=False)
    suggestion = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="open", index=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project_task = relationship("ProjectTask", back_populates="review_issues")
    change_bundle = relationship("ProjectTaskChangeBundle")
    evidence_bundle = relationship("ProjectTaskEvidenceBundle")
    handoff = relationship("ProjectTaskHandoff")
    creator = relationship("User")

    __table_args__ = (
        Index("idx_project_task_review_issue_task_created", "project_task_id", "created_at"),
        Index("idx_project_task_review_issue_task_status", "project_task_id", "status"),
    )


class ExecutionNode(Base):
    """Persistent execution node mirrored from attempt steps."""

    __tablename__ = "execution_nodes"

    node_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    project_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_tasks.project_task_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name = Column(String(255), nullable=False)
    node_type = Column(String(50), nullable=False, default="task")
    status = Column(String(50), nullable=False, default="pending", index=True)
    sequence_number = Column(Integer, nullable=False, default=0)
    dependency_node_ids = Column(JSONB, nullable=False, default=list)
    node_payload = Column(JSONB, nullable=False, default=dict)
    result_payload = Column(JSONB, nullable=False, default=dict)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    project = relationship("Project")
    run = relationship("ProjectRun", back_populates="execution_nodes")
    project_task = relationship("ProjectTask", back_populates="execution_nodes")

    __table_args__ = (
        Index("idx_execution_node_run_status", "run_id", "status"),
        Index("idx_execution_node_task_sequence", "project_task_id", "sequence_number"),
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
    runtime_type = Column(String(50), nullable=False, default="project_sandbox")
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


class ExternalAgentProfile(Base):
    """Per-agent external runtime configuration."""

    __tablename__ = "external_agent_profiles"

    profile_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    path_allowlist = Column(ARRAY(String), nullable=False, default=list)
    launch_command_template = Column(Text, nullable=True)
    install_channel = Column(String(32), nullable=False, default="stable")
    desired_version = Column(String(64), nullable=False, default="0.1.0")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent = relationship("Agent")


class ExternalAgentBinding(Base):
    """Current host binding for one external agent."""

    __tablename__ = "external_agent_bindings"

    binding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    host_name = Column(String(255), nullable=True)
    host_os = Column(String(32), nullable=True, index=True)
    host_arch = Column(String(64), nullable=True)
    host_fingerprint = Column(String(128), nullable=True)
    machine_token_hash = Column(String(128), nullable=False, index=True)
    machine_token_prefix = Column(String(24), nullable=False)
    status = Column(String(32), nullable=False, default="offline", index=True)
    current_version = Column(String(64), nullable=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True, index=True)
    bound_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    last_error_message = Column(Text, nullable=True)
    binding_metadata = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent = relationship("Agent")


class ExternalAgentInstallToken(Base):
    """One-time install codes for binding an external host."""

    __tablename__ = "external_agent_install_tokens"

    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(String(128), nullable=False, index=True)
    token_prefix = Column(String(24), nullable=False)
    status = Column(String(32), nullable=False, default="active", index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    agent = relationship("Agent")
    creator = relationship("User")

    __table_args__ = (
        Index("idx_external_agent_install_token_agent_status", "agent_id", "status"),
    )


class ExternalAgentDispatch(Base):
    """Dispatch queue item consumed by one bound external host."""

    __tablename__ = "external_agent_dispatches"

    dispatch_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agents.agent_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    binding_id = Column(
        UUID(as_uuid=True),
        ForeignKey("external_agent_bindings.binding_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.project_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_runs.run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_id = Column(
        UUID(as_uuid=True),
        ForeignKey("execution_nodes.node_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_type = Column(String(32), nullable=False, default="manual", index=True)
    source_id = Column(String(128), nullable=False, index=True)
    runtime_type = Column(String(50), nullable=False, index=True)
    request_payload = Column(JSONB, nullable=False, default=dict)
    result_payload = Column(JSONB, nullable=False, default=dict)
    status = Column(String(32), nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)
    acked_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    agent = relationship("Agent")
    binding = relationship("ExternalAgentBinding")
    project = relationship("Project")
    run = relationship("ProjectRun")
    execution_node = relationship("ExecutionNode")

    __table_args__ = (
        Index("idx_external_agent_dispatch_binding_status", "binding_id", "status"),
        Index("idx_external_agent_dispatch_agent_status", "agent_id", "status"),
    )


class ExternalAgentDispatchEvent(Base):
    """Ordered event stream for one external runtime dispatch."""

    __tablename__ = "external_agent_dispatch_events"

    event_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dispatch_id = Column(
        UUID(as_uuid=True),
        ForeignKey("external_agent_dispatches.dispatch_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number = Column(Integer, nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    dispatch = relationship("ExternalAgentDispatch")

    __table_args__ = (
        Index(
            "ux_external_agent_dispatch_events_sequence",
            "dispatch_id",
            "sequence_number",
            unique=True,
        ),
        Index("idx_external_agent_dispatch_events_dispatch_created", "dispatch_id", "created_at"),
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
