"""project task delivery records

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-08 16:05:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "project_task_handoffs" not in tables:
        op.create_table(
            "project_task_handoffs",
            sa.Column("handoff_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("stage", sa.String(length=64), nullable=False),
            sa.Column("from_actor", sa.String(length=128), nullable=False),
            sa.Column("to_actor", sa.String(length=128), nullable=True),
            sa.Column("status_from", sa.String(length=50), nullable=True),
            sa.Column("status_to", sa.String(length=50), nullable=True),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column(
                "payload",
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
                ["project_task_id"], ["project_tasks.project_task_id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["run_step_id"], ["project_run_steps.run_step_id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("handoff_id"),
        )
        op.create_index(
            "idx_project_task_handoff_task_created",
            "project_task_handoffs",
            ["project_task_id", "created_at"],
        )
        op.create_index(
            "idx_project_task_handoff_task_stage",
            "project_task_handoffs",
            ["project_task_id", "stage"],
        )

    if "project_task_change_bundles" not in tables:
        op.create_table(
            "project_task_change_bundles",
            sa.Column("change_bundle_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column(
                "bundle_kind",
                sa.String(length=32),
                nullable=False,
                server_default="patchset",
            ),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
            sa.Column("base_ref", sa.String(length=255), nullable=True),
            sa.Column("head_ref", sa.String(length=255), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("commit_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column(
                "changed_files",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "artifact_manifest",
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
                ["project_task_id"], ["project_tasks.project_task_id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["run_step_id"], ["project_run_steps.run_step_id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("change_bundle_id"),
        )
        op.create_index(
            "idx_project_task_change_bundle_task_created",
            "project_task_change_bundles",
            ["project_task_id", "created_at"],
        )
        op.create_index(
            "idx_project_task_change_bundle_task_status",
            "project_task_change_bundles",
            ["project_task_id", "status"],
        )

    if "project_task_evidence_bundles" not in tables:
        op.create_table(
            "project_task_evidence_bundles",
            sa.Column("evidence_bundle_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.String(length=32),
                nullable=False,
                server_default="collected",
            ),
            sa.Column(
                "bundle",
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
                ["project_task_id"], ["project_tasks.project_task_id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["run_step_id"], ["project_run_steps.run_step_id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("evidence_bundle_id"),
        )
        op.create_index(
            "idx_project_task_evidence_task_created",
            "project_task_evidence_bundles",
            ["project_task_id", "created_at"],
        )
        op.create_index(
            "idx_project_task_evidence_task_status",
            "project_task_evidence_bundles",
            ["project_task_id", "status"],
        )

    if "project_task_review_issues" not in tables:
        op.create_table(
            "project_task_review_issues",
            sa.Column("review_issue_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("change_bundle_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("evidence_bundle_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("handoff_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("issue_key", sa.String(length=128), nullable=True),
            sa.Column("severity", sa.String(length=32), nullable=False, server_default="medium"),
            sa.Column("category", sa.String(length=32), nullable=False, server_default="other"),
            sa.Column("acceptance_ref", sa.String(length=128), nullable=True),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("suggestion", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
                ["project_task_id"], ["project_tasks.project_task_id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(
                ["change_bundle_id"],
                ["project_task_change_bundles.change_bundle_id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["evidence_bundle_id"],
                ["project_task_evidence_bundles.evidence_bundle_id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["handoff_id"], ["project_task_handoffs.handoff_id"], ondelete="SET NULL"
            ),
            sa.ForeignKeyConstraint(
                ["created_by_user_id"], ["users.user_id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("review_issue_id"),
        )
        op.create_index(
            "idx_project_task_review_issue_task_created",
            "project_task_review_issues",
            ["project_task_id", "created_at"],
        )
        op.create_index(
            "idx_project_task_review_issue_task_status",
            "project_task_review_issues",
            ["project_task_id", "status"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "project_task_review_issues" in tables:
        op.drop_index(
            "idx_project_task_review_issue_task_status",
            table_name="project_task_review_issues",
        )
        op.drop_index(
            "idx_project_task_review_issue_task_created",
            table_name="project_task_review_issues",
        )
        op.drop_table("project_task_review_issues")

    if "project_task_evidence_bundles" in tables:
        op.drop_index(
            "idx_project_task_evidence_task_status",
            table_name="project_task_evidence_bundles",
        )
        op.drop_index(
            "idx_project_task_evidence_task_created",
            table_name="project_task_evidence_bundles",
        )
        op.drop_table("project_task_evidence_bundles")

    if "project_task_change_bundles" in tables:
        op.drop_index(
            "idx_project_task_change_bundle_task_status",
            table_name="project_task_change_bundles",
        )
        op.drop_index(
            "idx_project_task_change_bundle_task_created",
            table_name="project_task_change_bundles",
        )
        op.drop_table("project_task_change_bundles")

    if "project_task_handoffs" in tables:
        op.drop_index(
            "idx_project_task_handoff_task_stage",
            table_name="project_task_handoffs",
        )
        op.drop_index(
            "idx_project_task_handoff_task_created",
            table_name="project_task_handoffs",
        )
        op.drop_table("project_task_handoffs")
