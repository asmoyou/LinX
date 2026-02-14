"""Add mission_settings table.

Revision ID: n2b3c4d5e6f7
Revises: m1a2b3c4d5e6
Create Date: 2026-02-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "n2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "m1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mission_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            unique=True,
            nullable=False,
        ),
        sa.Column("leader_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("supervisor_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("qa_config", JSONB, nullable=False, server_default="{}"),
        sa.Column("execution_config", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_mission_settings_user", "mission_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("idx_mission_settings_user")
    op.drop_table("mission_settings")
