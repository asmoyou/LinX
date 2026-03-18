"""Add persistent conversation lifecycle metadata and archive tables.

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "y3z4a5b6c7d8"
down_revision = "x2y3z4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_conversations",
        sa.Column("storage_tier", sa.String(length=32), nullable=False, server_default="hot"),
    )
    op.add_column(
        "agent_conversations",
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_conversations",
        sa.Column("delete_after", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_conversations",
        sa.Column("last_workspace_decay_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_conversations",
        sa.Column("last_history_compaction_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "agent_conversations",
        sa.Column(
            "workspace_bytes_estimate",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_conversations",
        sa.Column(
            "workspace_file_count_estimate",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agent_conversations",
        sa.Column(
            "compacted_message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        op.f("ix_agent_conversations_storage_tier"),
        "agent_conversations",
        ["storage_tier"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_archived_at"),
        "agent_conversations",
        ["archived_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_delete_after"),
        "agent_conversations",
        ["delete_after"],
        unique=False,
    )

    op.create_table(
        "agent_conversation_history_summaries",
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("covers_until_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("covers_until_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("summary_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        op.f("ix_agent_conversation_history_summaries_covers_until_message_id"),
        "agent_conversation_history_summaries",
        ["covers_until_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_history_summaries_covers_until_created_at"),
        "agent_conversation_history_summaries",
        ["covers_until_created_at"],
        unique=False,
    )

    op.create_table(
        "agent_conversation_message_archives",
        sa.Column(
            "archive_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("start_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("end_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archive_ref", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("archive_id"),
    )
    op.create_index(
        "idx_agent_conversation_message_archives_conversation_created",
        "agent_conversation_message_archives",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_message_archives_conversation_id"),
        "agent_conversation_message_archives",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_message_archives_start_message_id"),
        "agent_conversation_message_archives",
        ["start_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_message_archives_end_message_id"),
        "agent_conversation_message_archives",
        ["end_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_message_archives_expires_at"),
        "agent_conversation_message_archives",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_message_archives_status"),
        "agent_conversation_message_archives",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_conversation_message_archives_status"),
        table_name="agent_conversation_message_archives",
    )
    op.drop_index(
        op.f("ix_agent_conversation_message_archives_expires_at"),
        table_name="agent_conversation_message_archives",
    )
    op.drop_index(
        op.f("ix_agent_conversation_message_archives_end_message_id"),
        table_name="agent_conversation_message_archives",
    )
    op.drop_index(
        op.f("ix_agent_conversation_message_archives_start_message_id"),
        table_name="agent_conversation_message_archives",
    )
    op.drop_index(
        op.f("ix_agent_conversation_message_archives_conversation_id"),
        table_name="agent_conversation_message_archives",
    )
    op.drop_index(
        "idx_agent_conversation_message_archives_conversation_created",
        table_name="agent_conversation_message_archives",
    )
    op.drop_table("agent_conversation_message_archives")

    op.drop_index(
        op.f("ix_agent_conversation_history_summaries_covers_until_created_at"),
        table_name="agent_conversation_history_summaries",
    )
    op.drop_index(
        op.f("ix_agent_conversation_history_summaries_covers_until_message_id"),
        table_name="agent_conversation_history_summaries",
    )
    op.drop_table("agent_conversation_history_summaries")

    op.drop_index(op.f("ix_agent_conversations_delete_after"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_archived_at"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_storage_tier"), table_name="agent_conversations")
    op.drop_column("agent_conversations", "compacted_message_count")
    op.drop_column("agent_conversations", "workspace_file_count_estimate")
    op.drop_column("agent_conversations", "workspace_bytes_estimate")
    op.drop_column("agent_conversations", "last_history_compaction_at")
    op.drop_column("agent_conversations", "last_workspace_decay_at")
    op.drop_column("agent_conversations", "delete_after")
    op.drop_column("agent_conversations", "archived_at")
    op.drop_column("agent_conversations", "storage_tier")
