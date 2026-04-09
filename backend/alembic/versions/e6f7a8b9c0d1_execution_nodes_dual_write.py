"""execution nodes dual write

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-04-08 20:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "execution_nodes" not in tables:
        op.create_table(
            "execution_nodes",
            sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("node_type", sa.String(length=50), nullable=False, server_default="task"),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
            sa.Column("sequence_number", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "dependency_node_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "node_payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "result_payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_task_id"], ["project_tasks.project_task_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["run_step_id"], ["project_run_steps.run_step_id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("node_id"),
            sa.UniqueConstraint("run_step_id", name="uq_execution_nodes_run_step_id"),
        )
        op.create_index(
            "idx_execution_node_run_status",
            "execution_nodes",
            ["run_id", "status"],
        )
        op.create_index(
            "idx_execution_node_task_sequence",
            "execution_nodes",
            ["project_task_id", "sequence_number"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "execution_nodes" in tables:
        op.drop_index("idx_execution_node_task_sequence", table_name="execution_nodes")
        op.drop_index("idx_execution_node_run_status", table_name="execution_nodes")
        op.drop_table("execution_nodes")
