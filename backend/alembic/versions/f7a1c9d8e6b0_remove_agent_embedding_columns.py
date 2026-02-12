"""remove_agent_embedding_columns

Revision ID: f7a1c9d8e6b0
Revises: e4f8a1b2c3d4
Create Date: 2026-02-12 23:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a1c9d8e6b0"
down_revision: Union[str, Sequence[str], None] = "e4f8a1b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("agents", "vector_dimension")
    op.drop_column("agents", "embedding_provider")
    op.drop_column("agents", "embedding_model")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("agents", sa.Column("embedding_model", sa.String(length=255), nullable=True))
    op.add_column("agents", sa.Column("embedding_provider", sa.String(length=100), nullable=True))
    op.add_column("agents", sa.Column("vector_dimension", sa.Integer(), nullable=True))
