"""Add ABAC policies table

Revision ID: a1b2c3d4e5f6
Revises: f3da3e52635a
Create Date: 2024-01-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f3da3e52635a'
branch_labels = None
depends_on = None


def upgrade():
    """Create abac_policies table."""
    op.create_table(
        'abac_policies',
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('effect', sa.String(length=50), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('actions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('policy_id')
    )
    
    # Create indexes
    op.create_index('idx_policy_name', 'abac_policies', ['name'])
    op.create_index('idx_policy_effect', 'abac_policies', ['effect'])
    op.create_index('idx_policy_resource_type', 'abac_policies', ['resource_type'])
    op.create_index('idx_policy_resource_enabled', 'abac_policies', ['resource_type', 'enabled'])
    op.create_index('idx_policy_priority', 'abac_policies', ['priority'])
    op.create_index('idx_policy_enabled', 'abac_policies', ['enabled'])


def downgrade():
    """Drop abac_policies table."""
    op.drop_index('idx_policy_enabled', table_name='abac_policies')
    op.drop_index('idx_policy_priority', table_name='abac_policies')
    op.drop_index('idx_policy_resource_enabled', table_name='abac_policies')
    op.drop_index('idx_policy_resource_type', table_name='abac_policies')
    op.drop_index('idx_policy_effect', table_name='abac_policies')
    op.drop_index('idx_policy_name', table_name='abac_policies')
    op.drop_table('abac_policies')
