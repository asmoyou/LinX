"""rename_metadata_to_skill_metadata

Revision ID: cefea2414350
Revises: 4d5f2fd74102
Create Date: 2026-01-30 09:35:03.344482

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cefea2414350'
down_revision: Union[str, Sequence[str], None] = '4d5f2fd74102'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Rename metadata column to skill_metadata to avoid SQLAlchemy reserved word conflict
    op.alter_column('skills', 'metadata', new_column_name='skill_metadata')


def downgrade() -> None:
    """Downgrade schema."""
    # Rename back to metadata
    op.alter_column('skills', 'skill_metadata', new_column_name='metadata')
