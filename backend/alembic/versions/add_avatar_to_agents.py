"""add avatar to agents

Revision ID: add_avatar_001
Revises: add_kb_fields_001
Create Date: 2026-01-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_avatar_001'
down_revision = 'add_kb_fields_001'
branch_labels = None
depends_on = None


def upgrade():
    """Add avatar column to agents table."""
    op.add_column('agents', sa.Column('avatar', sa.String(length=500), nullable=True))


def downgrade():
    """Remove avatar column from agents table."""
    op.drop_column('agents', 'avatar')
