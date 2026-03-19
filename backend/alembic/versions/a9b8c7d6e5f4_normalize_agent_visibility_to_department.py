"""Normalize agent visibility to department scope.

Revision ID: a9b8c7d6e5f4
Revises: z1a2b3c4d5e6
Create Date: 2026-04-16 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "a9b8c7d6e5f4"
down_revision = "b6c7d8e9f0g1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE agents
        SET access_level = 'department'
        WHERE lower(coalesce(access_level, 'private')) = 'team'
        """
    )

    op.execute(
        """
        UPDATE agents AS agent
        SET department_id = owner.department_id
        FROM users AS owner
        WHERE agent.owner_user_id = owner.user_id
          AND agent.department_id IS NULL
          AND owner.department_id IS NOT NULL
        """
    )

    op.execute(
        """
        UPDATE agents
        SET access_level = 'private'
        WHERE lower(coalesce(access_level, 'private')) = 'department'
          AND department_id IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE agents
        SET access_level = 'team'
        WHERE lower(coalesce(access_level, 'private')) = 'department'
        """
    )
