"""project execution scheduler core

Revision ID: r4n5c6h7e8d9
Revises: q9m1s4n0f0rm
Create Date: 2026-04-04 17:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "r4n5c6h7e8d9"
down_revision: Union[str, Sequence[str], None] = "q9m1s4n0f0rm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_agent_bindings",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_hint", sa.String(length=100), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("allowed_step_kinds", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("preferred_skills", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("binding_id"),
    )
    op.create_index("idx_project_agent_binding_project_status", "project_agent_bindings", ["project_id", "status"])
    op.create_index("idx_project_agent_binding_project_agent", "project_agent_bindings", ["project_id", "agent_id"], unique=True)

    op.create_table(
        "execution_leases",
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("lease_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["node_id"], ["execution_nodes.node_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_step_id"], ["project_run_steps.run_step_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("lease_id"),
    )
    op.create_index("idx_execution_lease_node_status", "execution_leases", ["node_id", "status"])
    op.create_index("idx_execution_lease_run_step", "execution_leases", ["run_step_id"], unique=True)

    op.create_table(
        "agent_provisioning_profiles",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_kind", sa.String(length=50), nullable=False),
        sa.Column("agent_type", sa.String(length=100), nullable=False),
        sa.Column("template_id", sa.String(length=255), nullable=True),
        sa.Column("default_skill_ids", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("default_provider", sa.String(length=100), nullable=True),
        sa.Column("default_model", sa.String(length=255), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("sandbox_mode", sa.String(length=50), nullable=False, server_default="run_shared"),
        sa.Column("ephemeral", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    op.create_index("idx_agent_provisioning_project_step_kind", "agent_provisioning_profiles", ["project_id", "step_kind"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_execution_lease_run_step", table_name="execution_leases")
    op.drop_index("idx_execution_lease_node_status", table_name="execution_leases")
    op.drop_table("execution_leases")
    op.drop_index("idx_agent_provisioning_project_step_kind", table_name="agent_provisioning_profiles")
    op.drop_table("agent_provisioning_profiles")
    op.drop_index("idx_project_agent_binding_project_agent", table_name="project_agent_bindings")
    op.drop_index("idx_project_agent_binding_project_status", table_name="project_agent_bindings")
    op.drop_table("project_agent_bindings")
