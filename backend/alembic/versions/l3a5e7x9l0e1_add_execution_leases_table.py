"""ensure execution_leases table exists

Revision ID: l3a5e7x9l0e1
Revises: r4n5c6h7e8d9
Create Date: 2026-04-06 10:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "l3a5e7x9l0e1"
down_revision: Union[str, Sequence[str], None] = "r4n5c6h7e8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "execution_leases" in inspector.get_table_names():
        return

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


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "execution_leases" not in inspector.get_table_names():
        return
    op.drop_index("idx_execution_lease_run_step", table_name="execution_leases")
    op.drop_index("idx_execution_lease_node_status", table_name="execution_leases")
    op.drop_table("execution_leases")
