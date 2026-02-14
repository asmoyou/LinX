"""add_mission_tables

Revision ID: m1a2b3c4d5e6
Revises: 91c4e2b8a5d1
Create Date: 2026-02-15 10:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "m1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "91c4e2b8a5d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create mission tables and add mission columns to tasks."""
    # --- missions ---
    op.create_table(
        "missions",
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("requirements_doc", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("container_id", sa.String(length=255), nullable=True),
        sa.Column("workspace_bucket", sa.String(length=255), nullable=True),
        sa.Column(
            "mission_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("total_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.department_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("mission_id"),
    )
    op.create_index(op.f("ix_missions_title"), "missions", ["title"], unique=False)
    op.create_index(op.f("ix_missions_status"), "missions", ["status"], unique=False)
    op.create_index(
        op.f("ix_missions_created_by_user_id"),
        "missions",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_missions_department_id"), "missions", ["department_id"], unique=False
    )
    op.create_index(
        "idx_mission_user_status",
        "missions",
        ["created_by_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_mission_created_at", "missions", ["created_at"], unique=False
    )

    # Remove server_default after table creation (match existing pattern)
    op.alter_column("missions", "status", server_default=None)
    op.alter_column("missions", "total_tasks", server_default=None)
    op.alter_column("missions", "completed_tasks", server_default=None)
    op.alter_column("missions", "failed_tasks", server_default=None)

    # --- mission_attachments ---
    op.create_table(
        "mission_attachments",
        sa.Column("attachment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("file_reference", sa.String(length=500), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.mission_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attachment_id"),
    )
    op.create_index(
        op.f("ix_mission_attachments_mission_id"),
        "mission_attachments",
        ["mission_id"],
        unique=False,
    )

    # --- mission_agents ---
    op.create_table(
        "mission_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="assigned",
        ),
        sa.Column("is_temporary", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.mission_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.agent_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_mission_agents_mission_id"),
        "mission_agents",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mission_agents_agent_id"),
        "mission_agents",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        "idx_mission_agent_unique",
        "mission_agents",
        ["mission_id", "agent_id"],
        unique=True,
    )

    # Remove server_defaults after table creation
    op.alter_column("mission_agents", "status", server_default=None)
    op.alter_column("mission_agents", "is_temporary", server_default=None)

    # --- mission_events ---
    op.create_table(
        "mission_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "event_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["mission_id"],
            ["missions.mission_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["agents.agent_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["tasks.task_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        op.f("ix_mission_events_mission_id"),
        "mission_events",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mission_events_event_type"),
        "mission_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mission_events_agent_id"),
        "mission_events",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mission_events_task_id"),
        "mission_events",
        ["task_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mission_events_created_at"),
        "mission_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "idx_event_mission_type",
        "mission_events",
        ["mission_id", "event_type"],
        unique=False,
    )
    op.create_index(
        "idx_event_mission_created",
        "mission_events",
        ["mission_id", "created_at"],
        unique=False,
    )

    # --- Add mission columns to tasks ---
    op.add_column(
        "tasks",
        sa.Column("mission_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
    )
    op.add_column(
        "tasks",
        sa.Column(
            "task_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_tasks_mission_id",
        "tasks",
        "missions",
        ["mission_id"],
        ["mission_id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_task_mission", "tasks", ["mission_id"], unique=False)


def downgrade() -> None:
    """Drop mission tables and remove mission columns from tasks."""
    # Remove mission columns from tasks
    op.drop_index("idx_task_mission", table_name="tasks")
    op.drop_constraint("fk_tasks_mission_id", "tasks", type_="foreignkey")
    op.drop_column("tasks", "task_metadata")
    op.drop_column("tasks", "acceptance_criteria")
    op.drop_column("tasks", "mission_id")

    # Drop mission_events
    op.drop_index("idx_event_mission_created", table_name="mission_events")
    op.drop_index("idx_event_mission_type", table_name="mission_events")
    op.drop_index(op.f("ix_mission_events_created_at"), table_name="mission_events")
    op.drop_index(op.f("ix_mission_events_task_id"), table_name="mission_events")
    op.drop_index(op.f("ix_mission_events_agent_id"), table_name="mission_events")
    op.drop_index(op.f("ix_mission_events_event_type"), table_name="mission_events")
    op.drop_index(op.f("ix_mission_events_mission_id"), table_name="mission_events")
    op.drop_table("mission_events")

    # Drop mission_agents
    op.drop_index("idx_mission_agent_unique", table_name="mission_agents")
    op.drop_index(op.f("ix_mission_agents_agent_id"), table_name="mission_agents")
    op.drop_index(op.f("ix_mission_agents_mission_id"), table_name="mission_agents")
    op.drop_table("mission_agents")

    # Drop mission_attachments
    op.drop_index(
        op.f("ix_mission_attachments_mission_id"), table_name="mission_attachments"
    )
    op.drop_table("mission_attachments")

    # Drop missions
    op.drop_index("idx_mission_created_at", table_name="missions")
    op.drop_index("idx_mission_user_status", table_name="missions")
    op.drop_index(op.f("ix_missions_department_id"), table_name="missions")
    op.drop_index(op.f("ix_missions_created_by_user_id"), table_name="missions")
    op.drop_index(op.f("ix_missions_status"), table_name="missions")
    op.drop_index(op.f("ix_missions_title"), table_name="missions")
    op.drop_table("missions")
