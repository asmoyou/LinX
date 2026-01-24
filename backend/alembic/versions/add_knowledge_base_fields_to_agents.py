"""add knowledge base fields to agents

Revision ID: add_kb_fields_001
Revises: add_llm_config_001
Create Date: 2026-01-24

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_kb_fields_001'
down_revision = 'add_llm_config_001'
branch_labels = None
depends_on = None


def upgrade():
    """Add knowledge base configuration fields to agents table."""
    # Add embedding_model column
    op.add_column('agents', sa.Column('embedding_model', sa.String(length=255), nullable=True))
    
    # Add embedding_provider column
    op.add_column('agents', sa.Column('embedding_provider', sa.String(length=100), nullable=True))
    
    # Add vector_dimension column
    op.add_column('agents', sa.Column('vector_dimension', sa.Integer(), nullable=True))
    
    # Add top_k column
    op.add_column('agents', sa.Column('top_k', sa.Integer(), nullable=True))
    
    # Add similarity_threshold column
    op.add_column('agents', sa.Column('similarity_threshold', sa.Float(), nullable=True))


def downgrade():
    """Remove knowledge base configuration fields from agents table."""
    op.drop_column('agents', 'similarity_threshold')
    op.drop_column('agents', 'top_k')
    op.drop_column('agents', 'vector_dimension')
    op.drop_column('agents', 'embedding_provider')
    op.drop_column('agents', 'embedding_model')
