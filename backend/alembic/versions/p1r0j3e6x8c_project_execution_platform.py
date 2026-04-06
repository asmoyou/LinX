"""project_execution_platform

Revision ID: p1r0j3e6x8c
Revises: m1c2p3s4e5r6
Create Date: 2026-03-24 09:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "p1r0j3e6x8c"
down_revision: Union[str, Sequence[str], None] = "m1c2p3s4e5r6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "projects",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )
    op.create_index(op.f("ix_projects_name"), "projects", ["name"], unique=False)
    op.create_index(op.f("ix_projects_status"), "projects", ["status"], unique=False)
    op.create_index(
        op.f("ix_projects_created_by_user_id"), "projects", ["created_by_user_id"], unique=False
    )
    op.create_index(
        "idx_project_creator_status", "projects", ["created_by_user_id", "status"], unique=False
    )
    op.create_index("idx_project_created_at", "projects", ["created_at"], unique=False)

    op.create_table(
        "project_plans",
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id"),
    )
    op.create_index(op.f("ix_project_plans_name"), "project_plans", ["name"], unique=False)
    op.create_index(op.f("ix_project_plans_status"), "project_plans", ["status"], unique=False)
    op.create_index(
        op.f("ix_project_plans_project_id"), "project_plans", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_plans_created_by_user_id"),
        "project_plans",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "idx_project_plan_project_status", "project_plans", ["project_id", "status"], unique=False
    )
    op.create_index(
        "idx_project_plan_project_version", "project_plans", ["project_id", "version"], unique=False
    )

    op.create_table(
        "project_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("trigger_source", sa.String(length=50), nullable=False),
        sa.Column("runtime_context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["plan_id"], ["project_plans.plan_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index(op.f("ix_project_runs_status"), "project_runs", ["status"], unique=False)
    op.create_index(
        op.f("ix_project_runs_project_id"), "project_runs", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_project_runs_plan_id"), "project_runs", ["plan_id"], unique=False)
    op.create_index(
        op.f("ix_project_runs_requested_by_user_id"),
        "project_runs",
        ["requested_by_user_id"],
        unique=False,
    )
    op.create_index(
        "idx_project_run_project_status", "project_runs", ["project_id", "status"], unique=False
    )
    op.create_index("idx_project_run_created_at", "project_runs", ["created_at"], unique=False)

    op.create_table(
        "execution_nodes",
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("node_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("capabilities", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["plan_id"], ["project_plans.plan_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("node_id"),
    )
    op.create_index(op.f("ix_execution_nodes_name"), "execution_nodes", ["name"], unique=False)
    op.create_index(op.f("ix_execution_nodes_status"), "execution_nodes", ["status"], unique=False)
    op.create_index(
        op.f("ix_execution_nodes_project_id"), "execution_nodes", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_execution_nodes_plan_id"), "execution_nodes", ["plan_id"], unique=False
    )
    op.create_index(
        "idx_execution_node_project_status",
        "execution_nodes",
        ["project_id", "status"],
        unique=False,
    )

    op.create_table(
        "project_tasks",
        sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("assignee_agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["assignee_agent_id"], ["agents.agent_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["plan_id"], ["project_plans.plan_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("project_task_id"),
    )
    op.create_index(op.f("ix_project_tasks_title"), "project_tasks", ["title"], unique=False)
    op.create_index(op.f("ix_project_tasks_status"), "project_tasks", ["status"], unique=False)
    op.create_index(
        op.f("ix_project_tasks_project_id"), "project_tasks", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_project_tasks_plan_id"), "project_tasks", ["plan_id"], unique=False)
    op.create_index(op.f("ix_project_tasks_run_id"), "project_tasks", ["run_id"], unique=False)
    op.create_index(
        op.f("ix_project_tasks_assignee_agent_id"),
        "project_tasks",
        ["assignee_agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_tasks_created_by_user_id"),
        "project_tasks",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "idx_project_task_project_status", "project_tasks", ["project_id", "status"], unique=False
    )
    op.create_index(
        "idx_project_task_project_sort", "project_tasks", ["project_id", "sort_order"], unique=False
    )

    op.create_table(
        "project_run_steps",
        sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("step_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
        sa.ForeignKeyConstraint(["node_id"], ["execution_nodes.node_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["project_task_id"], ["project_tasks.project_task_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_step_id"),
    )
    op.create_index(
        op.f("ix_project_run_steps_status"), "project_run_steps", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_project_run_steps_run_id"), "project_run_steps", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_run_steps_project_task_id"),
        "project_run_steps",
        ["project_task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_run_steps_node_id"), "project_run_steps", ["node_id"], unique=False
    )
    op.create_index(
        "idx_project_run_step_run_status", "project_run_steps", ["run_id", "status"], unique=False
    )
    op.create_index(
        "idx_project_run_step_run_sequence",
        "project_run_steps",
        ["run_id", "sequence_number"],
        unique=False,
    )

    op.create_table(
        "project_spaces",
        sa.Column("project_space_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_uri", sa.String(length=500), nullable=True),
        sa.Column("branch_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("root_path", sa.String(length=500), nullable=True),
        sa.Column("space_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.PrimaryKeyConstraint("project_space_id"),
        sa.UniqueConstraint("project_id"),
    )
    op.create_index(
        op.f("ix_project_spaces_project_id"), "project_spaces", ["project_id"], unique=True
    )
    op.create_index(op.f("ix_project_spaces_status"), "project_spaces", ["status"], unique=False)

    op.create_table(
        "project_skill_packages",
        sa.Column("skill_package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("test_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("imported_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["imported_by_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("skill_package_id"),
    )
    op.create_index(
        op.f("ix_project_skill_packages_name"), "project_skill_packages", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_project_skill_packages_slug"), "project_skill_packages", ["slug"], unique=True
    )
    op.create_index(
        op.f("ix_project_skill_packages_status"), "project_skill_packages", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_project_skill_packages_project_id"),
        "project_skill_packages",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_skill_packages_imported_by_user_id"),
        "project_skill_packages",
        ["imported_by_user_id"],
        unique=False,
    )
    op.create_index(
        "idx_project_skill_package_project_status",
        "project_skill_packages",
        ["project_id", "status"],
        unique=False,
    )

    op.create_table(
        "project_extension_packages",
        sa.Column("extension_package_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("package_type", sa.String(length=50), nullable=False),
        sa.Column("source_uri", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("installed_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.ForeignKeyConstraint(["installed_by_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("extension_package_id"),
    )
    op.create_index(
        op.f("ix_project_extension_packages_name"),
        "project_extension_packages",
        ["name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_extension_packages_status"),
        "project_extension_packages",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_extension_packages_project_id"),
        "project_extension_packages",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_extension_packages_installed_by_user_id"),
        "project_extension_packages",
        ["installed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "idx_project_extension_project_status",
        "project_extension_packages",
        ["project_id", "status"],
        unique=False,
    )

    op.create_table(
        "project_audit_events",
        sa.Column("audit_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resource_type", sa.String(length=100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.user_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("audit_event_id"),
    )
    op.create_index(
        op.f("ix_project_audit_events_project_id"),
        "project_audit_events",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_audit_events_run_id"), "project_audit_events", ["run_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_audit_events_resource_type"),
        "project_audit_events",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_audit_events_resource_id"),
        "project_audit_events",
        ["resource_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_audit_events_action"), "project_audit_events", ["action"], unique=False
    )
    op.create_index(
        op.f("ix_project_audit_events_actor_user_id"),
        "project_audit_events",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_audit_events_created_at"),
        "project_audit_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "idx_project_audit_project_created",
        "project_audit_events",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_project_audit_resource",
        "project_audit_events",
        ["resource_type", "resource_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_project_audit_resource", table_name="project_audit_events")
    op.drop_index("idx_project_audit_project_created", table_name="project_audit_events")
    op.drop_index(op.f("ix_project_audit_events_created_at"), table_name="project_audit_events")
    op.drop_index(op.f("ix_project_audit_events_actor_user_id"), table_name="project_audit_events")
    op.drop_index(op.f("ix_project_audit_events_action"), table_name="project_audit_events")
    op.drop_index(op.f("ix_project_audit_events_resource_id"), table_name="project_audit_events")
    op.drop_index(op.f("ix_project_audit_events_resource_type"), table_name="project_audit_events")
    op.drop_index(op.f("ix_project_audit_events_run_id"), table_name="project_audit_events")
    op.drop_index(op.f("ix_project_audit_events_project_id"), table_name="project_audit_events")
    op.drop_table("project_audit_events")

    op.drop_index("idx_project_extension_project_status", table_name="project_extension_packages")
    op.drop_index(
        op.f("ix_project_extension_packages_installed_by_user_id"),
        table_name="project_extension_packages",
    )
    op.drop_index(
        op.f("ix_project_extension_packages_project_id"), table_name="project_extension_packages"
    )
    op.drop_index(
        op.f("ix_project_extension_packages_status"), table_name="project_extension_packages"
    )
    op.drop_index(
        op.f("ix_project_extension_packages_name"), table_name="project_extension_packages"
    )
    op.drop_table("project_extension_packages")

    op.drop_index("idx_project_skill_package_project_status", table_name="project_skill_packages")
    op.drop_index(
        op.f("ix_project_skill_packages_imported_by_user_id"), table_name="project_skill_packages"
    )
    op.drop_index(op.f("ix_project_skill_packages_project_id"), table_name="project_skill_packages")
    op.drop_index(op.f("ix_project_skill_packages_status"), table_name="project_skill_packages")
    op.drop_index(op.f("ix_project_skill_packages_slug"), table_name="project_skill_packages")
    op.drop_index(op.f("ix_project_skill_packages_name"), table_name="project_skill_packages")
    op.drop_table("project_skill_packages")

    op.drop_index(op.f("ix_project_spaces_status"), table_name="project_spaces")
    op.drop_index(op.f("ix_project_spaces_project_id"), table_name="project_spaces")
    op.drop_table("project_spaces")

    op.drop_index("idx_project_run_step_run_sequence", table_name="project_run_steps")
    op.drop_index("idx_project_run_step_run_status", table_name="project_run_steps")
    op.drop_index(op.f("ix_project_run_steps_node_id"), table_name="project_run_steps")
    op.drop_index(op.f("ix_project_run_steps_project_task_id"), table_name="project_run_steps")
    op.drop_index(op.f("ix_project_run_steps_run_id"), table_name="project_run_steps")
    op.drop_index(op.f("ix_project_run_steps_status"), table_name="project_run_steps")
    op.drop_table("project_run_steps")

    op.drop_index("idx_project_task_project_sort", table_name="project_tasks")
    op.drop_index("idx_project_task_project_status", table_name="project_tasks")
    op.drop_index(op.f("ix_project_tasks_created_by_user_id"), table_name="project_tasks")
    op.drop_index(op.f("ix_project_tasks_assignee_agent_id"), table_name="project_tasks")
    op.drop_index(op.f("ix_project_tasks_run_id"), table_name="project_tasks")
    op.drop_index(op.f("ix_project_tasks_plan_id"), table_name="project_tasks")
    op.drop_index(op.f("ix_project_tasks_project_id"), table_name="project_tasks")
    op.drop_index(op.f("ix_project_tasks_status"), table_name="project_tasks")
    op.drop_index(op.f("ix_project_tasks_title"), table_name="project_tasks")
    op.drop_table("project_tasks")

    op.drop_index("idx_execution_node_project_status", table_name="execution_nodes")
    op.drop_index(op.f("ix_execution_nodes_plan_id"), table_name="execution_nodes")
    op.drop_index(op.f("ix_execution_nodes_project_id"), table_name="execution_nodes")
    op.drop_index(op.f("ix_execution_nodes_status"), table_name="execution_nodes")
    op.drop_index(op.f("ix_execution_nodes_name"), table_name="execution_nodes")
    op.drop_table("execution_nodes")

    op.drop_index("idx_project_run_created_at", table_name="project_runs")
    op.drop_index("idx_project_run_project_status", table_name="project_runs")
    op.drop_index(op.f("ix_project_runs_requested_by_user_id"), table_name="project_runs")
    op.drop_index(op.f("ix_project_runs_plan_id"), table_name="project_runs")
    op.drop_index(op.f("ix_project_runs_project_id"), table_name="project_runs")
    op.drop_index(op.f("ix_project_runs_status"), table_name="project_runs")
    op.drop_table("project_runs")

    op.drop_index("idx_project_plan_project_version", table_name="project_plans")
    op.drop_index("idx_project_plan_project_status", table_name="project_plans")
    op.drop_index(op.f("ix_project_plans_created_by_user_id"), table_name="project_plans")
    op.drop_index(op.f("ix_project_plans_project_id"), table_name="project_plans")
    op.drop_index(op.f("ix_project_plans_status"), table_name="project_plans")
    op.drop_index(op.f("ix_project_plans_name"), table_name="project_plans")
    op.drop_table("project_plans")

    op.drop_index("idx_project_created_at", table_name="projects")
    op.drop_index("idx_project_creator_status", table_name="projects")
    op.drop_index(op.f("ix_projects_created_by_user_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_status"), table_name="projects")
    op.drop_index(op.f("ix_projects_name"), table_name="projects")
    op.drop_table("projects")
