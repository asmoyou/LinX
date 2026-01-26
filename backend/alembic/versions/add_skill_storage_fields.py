"""add_skill_storage_fields

Revision ID: add_skill_storage
Revises: 13be0d1967af
Create Date: 2026-01-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_skill_storage'
down_revision: Union[str, Sequence[str], None] = '13be0d1967af'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add storage fields for skill packages."""
    # Add storage_type column (inline or minio)
    op.add_column(
        'skills',
        sa.Column(
            'storage_type',
            sa.String(50),
            nullable=False,
            server_default='inline'
        )
    )
    
    # Add storage_path column (MinIO path for packages)
    op.add_column(
        'skills',
        sa.Column(
            'storage_path',
            sa.String(500),
            nullable=True
        )
    )
    
    # Add manifest column (parsed from skill.yaml for packages)
    op.add_column(
        'skills',
        sa.Column(
            'manifest',
            sa.dialects.postgresql.JSONB(),
            nullable=True
        )
    )
    
    # Create index for storage_type
    op.create_index('idx_skills_storage_type', 'skills', ['storage_type'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index
    op.drop_index('idx_skills_storage_type', 'skills')
    
    # Drop columns
    op.drop_column('skills', 'manifest')
    op.drop_column('skills', 'storage_path')
    op.drop_column('skills', 'storage_type')
