"""Add pagination indexes for persistent conversation lists.

Revision ID: z4y5x6w7v8u9
Revises: y3z4a5b6c7d8
Create Date: 2026-04-20 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "z4y5x6w7v8u9"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_agent_conversation_messages_conversation_created_message",
        "agent_conversation_messages",
        ["conversation_id", "created_at", "message_id"],
        unique=False,
    )
    op.create_index(
        "idx_agent_conversations_owner_agent_status_updated_cursor",
        "agent_conversations",
        ["owner_user_id", "agent_id", "status", "updated_at", "conversation_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_agent_conversations_owner_agent_status_updated_cursor",
        table_name="agent_conversations",
    )
    op.drop_index(
        "idx_agent_conversation_messages_conversation_created_message",
        table_name="agent_conversation_messages",
    )
