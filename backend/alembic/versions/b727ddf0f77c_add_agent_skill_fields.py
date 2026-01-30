"""add_agent_skill_fields

Revision ID: b727ddf0f77c
Revises: add_skill_storage
Create Date: 2026-01-29 11:56:47.749794

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b727ddf0f77c'
down_revision: Union[str, Sequence[str], None] = 'add_skill_storage'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns for agent_skill
    op.add_column('skills', sa.Column('skill_md_content', sa.Text(), nullable=True))
    op.add_column('skills', sa.Column('homepage', sa.String(500), nullable=True))
    op.add_column('skills', sa.Column('skill_metadata', sa.JSON(), nullable=True))
    op.add_column('skills', sa.Column('gating_status', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('skills', 'gating_status')
    op.drop_column('skills', 'skill_metadata')
    op.drop_column('skills', 'homepage')
    op.drop_column('skills', 'skill_md_content')
