"""Add agent schedule tables.

Revision ID: g1h2i3j4k5l6
Revises: a9b8c7d6e5f4
Create Date: 2026-04-18 09:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op


revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_schedules",
        sa.Column("schedule_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.agent_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "bound_conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_conversations.conversation_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("prompt_template", sa.Text(), nullable=False),
        sa.Column("schedule_type", sa.String(length=16), nullable=False),
        sa.Column("cron_expression", sa.String(length=100), nullable=True),
        sa.Column("run_at_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(length=100), nullable=False, server_default="UTC"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column(
            "created_via",
            sa.String(length=32),
            nullable=False,
            server_default="manual_ui",
        ),
        sa.Column(
            "origin_surface",
            sa.String(length=32),
            nullable=False,
            server_default="schedule_page",
        ),
        sa.Column(
            "origin_message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_conversation_messages.message_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_status", sa.String(length=16), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "schedule_type IN ('once', 'recurring')",
            name="ck_agent_schedules_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'failed')",
            name="ck_agent_schedules_status",
        ),
        sa.CheckConstraint(
            "(schedule_type <> 'once') OR (run_at_utc IS NOT NULL)",
            name="ck_agent_schedules_once_requires_run_at",
        ),
        sa.CheckConstraint(
            "(schedule_type <> 'recurring') OR (cron_expression IS NOT NULL)",
            name="ck_agent_schedules_recurring_requires_cron",
        ),
    )

    op.create_index("ix_agent_schedules_owner_user_id", "agent_schedules", ["owner_user_id"])
    op.create_index("ix_agent_schedules_agent_id", "agent_schedules", ["agent_id"])
    op.create_index(
        "ix_agent_schedules_bound_conversation_id",
        "agent_schedules",
        ["bound_conversation_id"],
    )
    op.create_index("ix_agent_schedules_schedule_type", "agent_schedules", ["schedule_type"])
    op.create_index("ix_agent_schedules_run_at_utc", "agent_schedules", ["run_at_utc"])
    op.create_index("ix_agent_schedules_status", "agent_schedules", ["status"])
    op.create_index("ix_agent_schedules_created_via", "agent_schedules", ["created_via"])
    op.create_index("ix_agent_schedules_origin_surface", "agent_schedules", ["origin_surface"])
    op.create_index("ix_agent_schedules_origin_message_id", "agent_schedules", ["origin_message_id"])
    op.create_index("ix_agent_schedules_next_run_at", "agent_schedules", ["next_run_at"])
    op.create_index(
        "idx_agent_schedules_owner_status",
        "agent_schedules",
        ["owner_user_id", "status"],
    )
    op.create_index(
        "idx_agent_schedules_next_run_status",
        "agent_schedules",
        ["next_run_at", "status"],
    )
    op.create_index(
        "idx_agent_schedules_agent_status",
        "agent_schedules",
        ["agent_id", "status"],
    )

    op.create_table(
        "agent_schedule_runs",
        sa.Column("run_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "schedule_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_schedules.schedule_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("skip_reason", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "assistant_message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_conversation_messages.message_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "conversation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_conversations.conversation_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("delivery_channel", sa.String(length=16), nullable=False, server_default="web"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped')",
            name="ck_agent_schedule_runs_status",
        ),
    )

    op.create_index("ix_agent_schedule_runs_schedule_id", "agent_schedule_runs", ["schedule_id"])
    op.create_index(
        "ix_agent_schedule_runs_scheduled_for",
        "agent_schedule_runs",
        ["scheduled_for"],
    )
    op.create_index("ix_agent_schedule_runs_status", "agent_schedule_runs", ["status"])
    op.create_index(
        "ix_agent_schedule_runs_assistant_message_id",
        "agent_schedule_runs",
        ["assistant_message_id"],
    )
    op.create_index(
        "ix_agent_schedule_runs_conversation_id",
        "agent_schedule_runs",
        ["conversation_id"],
    )
    op.create_index(
        "ux_agent_schedule_runs_schedule_scheduled_for",
        "agent_schedule_runs",
        ["schedule_id", "scheduled_for"],
        unique=True,
    )
    op.create_index(
        "idx_agent_schedule_runs_status_scheduled",
        "agent_schedule_runs",
        ["status", "scheduled_for", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_agent_schedule_runs_status_scheduled", table_name="agent_schedule_runs")
    op.drop_index(
        "ux_agent_schedule_runs_schedule_scheduled_for",
        table_name="agent_schedule_runs",
    )
    op.drop_index("ix_agent_schedule_runs_conversation_id", table_name="agent_schedule_runs")
    op.drop_index("ix_agent_schedule_runs_assistant_message_id", table_name="agent_schedule_runs")
    op.drop_index("ix_agent_schedule_runs_status", table_name="agent_schedule_runs")
    op.drop_index("ix_agent_schedule_runs_scheduled_for", table_name="agent_schedule_runs")
    op.drop_index("ix_agent_schedule_runs_schedule_id", table_name="agent_schedule_runs")
    op.drop_table("agent_schedule_runs")

    op.drop_index("idx_agent_schedules_agent_status", table_name="agent_schedules")
    op.drop_index("idx_agent_schedules_next_run_status", table_name="agent_schedules")
    op.drop_index("idx_agent_schedules_owner_status", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_next_run_at", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_origin_message_id", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_origin_surface", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_created_via", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_status", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_run_at_utc", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_schedule_type", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_bound_conversation_id", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_agent_id", table_name="agent_schedules")
    op.drop_index("ix_agent_schedules_owner_user_id", table_name="agent_schedules")
    op.drop_table("agent_schedules")
