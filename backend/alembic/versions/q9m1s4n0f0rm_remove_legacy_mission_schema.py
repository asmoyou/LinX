"""remove_legacy_mission_schema

Revision ID: q9m1s4n0f0rm
Revises: p1r0j3e6x8c
Create Date: 2026-04-04 20:15:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "q9m1s4n0f0rm"
down_revision: Union[str, Sequence[str], None] = "p1r0j3e6x8c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE IF EXISTS user_notifications DROP COLUMN IF EXISTS mission_id CASCADE")
    op.execute("ALTER TABLE IF EXISTS tasks DROP COLUMN IF EXISTS mission_id CASCADE")
    op.execute("DROP TABLE IF EXISTS mission_events CASCADE")
    op.execute("DROP TABLE IF EXISTS mission_agents CASCADE")
    op.execute("DROP TABLE IF EXISTS mission_attachments CASCADE")
    op.execute("DROP TABLE IF EXISTS mission_settings CASCADE")
    op.execute("DROP TABLE IF EXISTS missions CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "Legacy mission schema removal is irreversible; restore from backup if needed."
    )
