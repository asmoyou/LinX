"""Add LLM configuration fields to agents table

Revision ID: add_llm_config_001
Revises: 
Create Date: 2026-01-23

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_llm_config_001'
down_revision = 'ed10804b346f'  # add_model_metadata_to_llm_providers
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add LLM configuration fields to agents table."""
    # Add LLM configuration columns
    op.add_column('agents', sa.Column('llm_provider', sa.String(length=100), nullable=True))
    op.add_column('agents', sa.Column('llm_model', sa.String(length=255), nullable=True))
    op.add_column('agents', sa.Column('system_prompt', sa.Text(), nullable=True))
    op.add_column('agents', sa.Column('temperature', sa.Float(), nullable=True, server_default='0.7'))
    op.add_column('agents', sa.Column('max_tokens', sa.Integer(), nullable=True, server_default='2000'))
    op.add_column('agents', sa.Column('top_p', sa.Float(), nullable=True, server_default='0.9'))
    
    # Add access control columns
    op.add_column('agents', sa.Column('access_level', sa.String(length=50), nullable=True, server_default='private'))
    op.add_column('agents', sa.Column('allowed_knowledge', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('agents', sa.Column('allowed_memory', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    """Remove LLM configuration fields from agents table."""
    op.drop_column('agents', 'allowed_memory')
    op.drop_column('agents', 'allowed_knowledge')
    op.drop_column('agents', 'access_level')
    op.drop_column('agents', 'top_p')
    op.drop_column('agents', 'max_tokens')
    op.drop_column('agents', 'temperature')
    op.drop_column('agents', 'system_prompt')
    op.drop_column('agents', 'llm_model')
    op.drop_column('agents', 'llm_provider')
