"""Change avatar column to Text type

Revision ID: change_avatar_002
Revises: add_avatar_001
Create Date: 2024-01-24 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'change_avatar_002'
down_revision = 'add_avatar_001'
branch_labels = None
depends_on = None


def upgrade():
    """Change avatar column from VARCHAR(500) to TEXT."""
    # PostgreSQL allows ALTER COLUMN TYPE
    op.alter_column('agents', 'avatar',
                    existing_type=sa.String(length=500),
                    type_=sa.Text(),
                    existing_nullable=True)


def downgrade():
    """Revert avatar column back to VARCHAR(500)."""
    op.alter_column('agents', 'avatar',
                    existing_type=sa.Text(),
                    type_=sa.String(length=500),
                    existing_nullable=True)
