"""Add segmented memory extraction state for persistent conversations.

Revision ID: x2y3z4a5b6c7
Revises: w1x2y3z4a5b6
Create Date: 2026-03-21 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "x2y3z4a5b6c7"
down_revision = "w1x2y3z4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_conversation_memory_states",
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "last_processed_assistant_message_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("last_processed_assistant_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_processed_turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("run_state", sa.String(length=16), nullable=False, server_default="idle"),
        sa.Column("run_token", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_assistant_message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_assistant_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_extraction_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_extraction_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_extraction_reason", sa.String(length=64), nullable=True),
        sa.Column("last_successful_session_ledger_id", sa.BigInteger(), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["last_successful_session_ledger_id"],
            ["session_ledgers.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("conversation_id"),
        sa.CheckConstraint(
            "(run_state <> 'running') OR "
            "(run_token IS NOT NULL AND lease_until IS NOT NULL AND "
            "target_assistant_message_id IS NOT NULL)",
            name="ck_agent_conversation_memory_states_running_fields",
        ),
    )
    op.create_index(
        "idx_agent_conversation_memory_states_claim",
        "agent_conversation_memory_states",
        ["run_state", "retry_after", "lease_until"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_last_processed_assistant_message_id"),
        "agent_conversation_memory_states",
        ["last_processed_assistant_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_last_processed_assistant_created_at"),
        "agent_conversation_memory_states",
        ["last_processed_assistant_created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_lease_until"),
        "agent_conversation_memory_states",
        ["lease_until"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_retry_after"),
        "agent_conversation_memory_states",
        ["retry_after"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_run_state"),
        "agent_conversation_memory_states",
        ["run_state"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_target_assistant_message_id"),
        "agent_conversation_memory_states",
        ["target_assistant_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_target_assistant_created_at"),
        "agent_conversation_memory_states",
        ["target_assistant_created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_memory_states_last_successful_session_ledger_id"),
        "agent_conversation_memory_states",
        ["last_successful_session_ledger_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_last_successful_session_ledger_id"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_target_assistant_created_at"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_target_assistant_message_id"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_run_state"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_retry_after"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_lease_until"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_last_processed_assistant_created_at"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index(
        op.f("ix_agent_conversation_memory_states_last_processed_assistant_message_id"),
        table_name="agent_conversation_memory_states",
    )
    op.drop_index("idx_agent_conversation_memory_states_claim", table_name="agent_conversation_memory_states")
    op.drop_table("agent_conversation_memory_states")
