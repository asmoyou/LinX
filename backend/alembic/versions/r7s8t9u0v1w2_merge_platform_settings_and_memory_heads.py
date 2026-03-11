"""Merge platform settings and memory heads.

Revision ID: r7s8t9u0v1w2
Revises: ab4c5d6e7f81, q1r2s3t4u5v6
Create Date: 2026-03-11
"""

from typing import Sequence, Union

from alembic import op

revision: str = "r7s8t9u0v1w2"
down_revision: Union[str, Sequence[str], None] = ("ab4c5d6e7f81", "q1r2s3t4u5v6")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge divergent migration heads."""
    pass


def downgrade() -> None:
    """Unmerge divergent migration heads."""
    pass
