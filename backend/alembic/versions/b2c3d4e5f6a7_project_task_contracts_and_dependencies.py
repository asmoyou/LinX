"""project task contracts and dependencies

Revision ID: b2c3d4e5f6a7
Revises: a8f9c0d1e2f3
Create Date: 2026-04-08 15:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a8f9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "project_task_contracts" not in tables:
        op.create_table(
            "project_task_contracts",
            sa.Column("contract_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("goal", sa.Text(), nullable=True),
            sa.Column(
                "scope",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "constraints",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "deliverables",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "acceptance_criteria",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "assumptions",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "evidence_required",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "allowed_surface",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("source_description_hash", sa.String(length=64), nullable=True),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["project_task_id"], ["project_tasks.project_task_id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("contract_id"),
        )
        op.create_index(
            "idx_project_task_contract_task_version",
            "project_task_contracts",
            ["project_task_id", "version"],
            unique=True,
        )
        op.create_index(
            "idx_project_task_contract_task_created",
            "project_task_contracts",
            ["project_task_id", "created_at"],
        )
        op.create_index(
            "ix_project_task_contracts_source_description_hash",
            "project_task_contracts",
            ["source_description_hash"],
        )

    if "project_task_dependencies" not in tables:
        op.create_table(
            "project_task_dependencies",
            sa.Column("dependency_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("depends_on_project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column(
                "required_state",
                sa.String(length=32),
                nullable=False,
                server_default="approved",
            ),
            sa.Column(
                "dependency_type",
                sa.String(length=32),
                nullable=False,
                server_default="hard",
            ),
            sa.Column(
                "artifact_selector",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["depends_on_project_task_id"],
                ["project_tasks.project_task_id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["project_task_id"], ["project_tasks.project_task_id"], ondelete="CASCADE"
            ),
            sa.PrimaryKeyConstraint("dependency_id"),
        )
        op.create_index(
            "idx_project_task_dependency_edge",
            "project_task_dependencies",
            ["project_task_id", "depends_on_project_task_id"],
            unique=True,
        )
        op.create_index(
            "idx_project_task_dependency_task",
            "project_task_dependencies",
            ["project_task_id", "required_state"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "project_task_dependencies" in tables:
        op.drop_index("idx_project_task_dependency_task", table_name="project_task_dependencies")
        op.drop_index("idx_project_task_dependency_edge", table_name="project_task_dependencies")
        op.drop_table("project_task_dependencies")

    if "project_task_contracts" in tables:
        op.drop_index(
            "ix_project_task_contracts_source_description_hash",
            table_name="project_task_contracts",
        )
        op.drop_index(
            "idx_project_task_contract_task_created",
            table_name="project_task_contracts",
        )
        op.drop_index(
            "idx_project_task_contract_task_version",
            table_name="project_task_contracts",
        )
        op.drop_table("project_task_contracts")
