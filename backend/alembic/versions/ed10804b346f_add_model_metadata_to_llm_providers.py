"""add_model_metadata_to_llm_providers

Revision ID: ed10804b346f
Revises: 57fe33834201
Create Date: 2026-01-23 17:50:17.172866

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ed10804b346f'
down_revision: Union[str, Sequence[str], None] = '57fe33834201'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add model_metadata JSONB column to store detailed model information
    op.add_column(
        'llm_providers',
        sa.Column('model_metadata', sa.dialects.postgresql.JSONB, nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove model_metadata column
    op.drop_column('llm_providers', 'model_metadata')
