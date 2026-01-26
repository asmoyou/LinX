"""add_dynamic_skill_fields

Revision ID: 13be0d1967af
Revises: change_avatar_002
Create Date: 2026-01-24 14:18:05.927149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13be0d1967af'
down_revision: Union[str, Sequence[str], None] = 'change_avatar_002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns to skills table
    op.add_column('skills', sa.Column('skill_type', sa.String(50), nullable=False, server_default='python_function'))
    op.add_column('skills', sa.Column('code', sa.Text(), nullable=True))
    op.add_column('skills', sa.Column('config', sa.dialects.postgresql.JSONB(), nullable=True))
    op.add_column('skills', sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('skills', sa.Column('is_system', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('skills', sa.Column('execution_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('skills', sa.Column('last_executed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('skills', sa.Column('average_execution_time', sa.Float(), nullable=True))
    op.add_column('skills', sa.Column('created_by', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('skills', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    
    # Add foreign key for created_by
    op.create_foreign_key('fk_skills_created_by', 'skills', 'users', ['created_by'], ['user_id'], ondelete='SET NULL')
    
    # Create indexes for performance
    op.create_index('idx_skills_type', 'skills', ['skill_type'])
    op.create_index('idx_skills_active', 'skills', ['is_active'])
    op.create_index('idx_skills_system', 'skills', ['is_system'])
    op.create_index('idx_skills_created_by', 'skills', ['created_by'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_skills_created_by', 'skills')
    op.drop_index('idx_skills_system', 'skills')
    op.drop_index('idx_skills_active', 'skills')
    op.drop_index('idx_skills_type', 'skills')
    
    # Drop foreign key
    op.drop_constraint('fk_skills_created_by', 'skills', type_='foreignkey')
    
    # Drop columns
    op.drop_column('skills', 'updated_at')
    op.drop_column('skills', 'created_by')
    op.drop_column('skills', 'average_execution_time')
    op.drop_column('skills', 'last_executed_at')
    op.drop_column('skills', 'execution_count')
    op.drop_column('skills', 'is_system')
    op.drop_column('skills', 'is_active')
    op.drop_column('skills', 'config')
    op.drop_column('skills', 'code')
    op.drop_column('skills', 'skill_type')
