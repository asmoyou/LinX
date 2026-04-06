"""unified agent runtime model

Revision ID: u2n1f1e5d6m7
Revises: l3a5e7x9l0e1
Create Date: 2026-04-06 18:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "u2n1f1e5d6m7"
down_revision: Union[str, Sequence[str], None] = "l3a5e7x9l0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    agent_columns = {col["name"] for col in inspector.get_columns("agents")}
    if "is_ephemeral" not in agent_columns:
        op.add_column("agents", sa.Column("is_ephemeral", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        op.create_index("ix_agents_is_ephemeral", "agents", ["is_ephemeral"])
    if "lifecycle_scope" not in agent_columns:
        op.add_column("agents", sa.Column("lifecycle_scope", sa.String(length=50), nullable=True))
        op.create_index("ix_agents_lifecycle_scope", "agents", ["lifecycle_scope"])
    if "runtime_preference" not in agent_columns:
        op.add_column("agents", sa.Column("runtime_preference", sa.String(length=50), nullable=True))
        op.create_index("ix_agents_runtime_preference", "agents", ["runtime_preference"])
    if "project_scope_id" not in agent_columns:
        op.add_column(
            "agents",
            sa.Column("project_scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            "fk_agents_project_scope_id_projects",
            "agents",
            "projects",
            ["project_scope_id"],
            ["project_id"],
            ondelete="SET NULL",
        )
        op.create_index("ix_agents_project_scope_id", "agents", ["project_scope_id"])
    if "retired_at" not in agent_columns:
        op.add_column("agents", sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_agents_retired_at", "agents", ["retired_at"])

    binding_columns = {col["name"] for col in inspector.get_columns("project_agent_bindings")}
    if "preferred_runtime_types" not in binding_columns:
        op.add_column(
            "project_agent_bindings",
            sa.Column("preferred_runtime_types", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        )

    profile_columns = {col["name"] for col in inspector.get_columns("agent_provisioning_profiles")}
    if "runtime_type" not in profile_columns:
        op.add_column(
            "agent_provisioning_profiles",
            sa.Column("runtime_type", sa.String(length=50), nullable=False, server_default="project_sandbox"),
        )
    if "preferred_node_selector" not in profile_columns:
        op.add_column(
            "agent_provisioning_profiles",
            sa.Column("preferred_node_selector", sa.String(length=255), nullable=True),
        )

    tables = set(inspector.get_table_names())
    if "agent_runtime_bindings" not in tables:
        op.create_table(
            "agent_runtime_bindings",
            sa.Column("runtime_binding_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("runtime_type", sa.String(length=50), nullable=False),
            sa.Column("execution_node_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("workspace_strategy", sa.String(length=50), nullable=True),
            sa.Column("path_allowlist", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["execution_node_id"], ["execution_nodes.node_id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("runtime_binding_id"),
        )
        op.create_index("idx_agent_runtime_binding_agent_status", "agent_runtime_bindings", ["agent_id", "status"])

    if "external_agent_sessions" not in tables:
        op.create_table(
            "external_agent_sessions",
            sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("execution_node_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("runtime_type", sa.String(length=50), nullable=False),
            sa.Column("workdir", sa.String(length=500), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("session_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["execution_node_id"], ["execution_nodes.node_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_step_id"], ["project_run_steps.run_step_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["lease_id"], ["execution_leases.lease_id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("session_id"),
        )
        op.create_index("idx_external_agent_session_node_status", "external_agent_sessions", ["execution_node_id", "status"])
        op.create_index("idx_external_agent_session_run_step", "external_agent_sessions", ["run_step_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "external_agent_sessions" in tables:
        op.drop_index("idx_external_agent_session_run_step", table_name="external_agent_sessions")
        op.drop_index("idx_external_agent_session_node_status", table_name="external_agent_sessions")
        op.drop_table("external_agent_sessions")
    if "agent_runtime_bindings" in tables:
        op.drop_index("idx_agent_runtime_binding_agent_status", table_name="agent_runtime_bindings")
        op.drop_table("agent_runtime_bindings")

    columns = {col["name"] for col in inspector.get_columns("agent_provisioning_profiles")}
    if "preferred_node_selector" in columns:
        op.drop_column("agent_provisioning_profiles", "preferred_node_selector")
    if "runtime_type" in columns:
        op.drop_column("agent_provisioning_profiles", "runtime_type")

    columns = {col["name"] for col in inspector.get_columns("project_agent_bindings")}
    if "preferred_runtime_types" in columns:
        op.drop_column("project_agent_bindings", "preferred_runtime_types")

    columns = {col["name"] for col in inspector.get_columns("agents")}
    if "retired_at" in columns:
        op.drop_index("ix_agents_retired_at", table_name="agents")
        op.drop_column("agents", "retired_at")
    if "project_scope_id" in columns:
        op.drop_index("ix_agents_project_scope_id", table_name="agents")
        op.drop_constraint("fk_agents_project_scope_id_projects", "agents", type_="foreignkey")
        op.drop_column("agents", "project_scope_id")
    if "runtime_preference" in columns:
        op.drop_index("ix_agents_runtime_preference", table_name="agents")
        op.drop_column("agents", "runtime_preference")
    if "lifecycle_scope" in columns:
        op.drop_index("ix_agents_lifecycle_scope", table_name="agents")
        op.drop_column("agents", "lifecycle_scope")
    if "is_ephemeral" in columns:
        op.drop_index("ix_agents_is_ephemeral", table_name="agents")
        op.drop_column("agents", "is_ephemeral")
