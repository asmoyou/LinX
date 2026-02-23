"""Add user_notifications table.

Revision ID: p3c4d5e6f7g8
Revises: n2b3c4d5e6f7
Create Date: 2026-02-24
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "p3c4d5e6f7g8"
down_revision: Union[str, Sequence[str], None] = "n2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_notifications",
        sa.Column("notification_id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mission_id",
            UUID(as_uuid=True),
            sa.ForeignKey("missions.mission_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("notification_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("action_url", sa.String(length=500), nullable=True),
        sa.Column("action_label", sa.String(length=100), nullable=True),
        sa.Column("notification_metadata", JSONB, nullable=True, server_default="{}"),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
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
    )

    op.create_index(
        "idx_user_notifications_user_created",
        "user_notifications",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_user_notifications_user_unread_created",
        "user_notifications",
        ["user_id", "is_read", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_user_notifications_user_type_created",
        "user_notifications",
        ["user_id", "notification_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_user_notifications_notification_type",
        "user_notifications",
        ["notification_type"],
        unique=False,
    )
    op.create_index(
        "ix_user_notifications_dedupe_key",
        "user_notifications",
        ["dedupe_key"],
        unique=False,
    )
    op.create_index(
        "ix_user_notifications_is_read",
        "user_notifications",
        ["is_read"],
        unique=False,
    )
    op.create_index(
        "ix_user_notifications_user_id",
        "user_notifications",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_notifications_mission_id",
        "user_notifications",
        ["mission_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_notifications_created_at",
        "user_notifications",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_notifications_created_at", table_name="user_notifications")
    op.drop_index("ix_user_notifications_mission_id", table_name="user_notifications")
    op.drop_index("ix_user_notifications_user_id", table_name="user_notifications")
    op.drop_index("ix_user_notifications_is_read", table_name="user_notifications")
    op.drop_index("ix_user_notifications_dedupe_key", table_name="user_notifications")
    op.drop_index("ix_user_notifications_notification_type", table_name="user_notifications")
    op.drop_index("idx_user_notifications_user_type_created", table_name="user_notifications")
    op.drop_index("idx_user_notifications_user_unread_created", table_name="user_notifications")
    op.drop_index("idx_user_notifications_user_created", table_name="user_notifications")
    op.drop_table("user_notifications")
