"""merge project execution heads

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8, c4d5e6f7a8b9
Create Date: 2026-04-08 17:40:00.000000
"""

from typing import Sequence, Union


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = ("c3d4e5f6a7b8", "c4d5e6f7a8b9")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
