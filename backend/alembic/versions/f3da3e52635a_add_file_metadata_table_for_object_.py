"""Add file_metadata table for object storage

Revision ID: f3da3e52635a
Revises: 066e30212dbb
Create Date: 2026-01-20 16:11:40.946699

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSON


# revision identifiers, used by Alembic.
revision: str = 'f3da3e52635a'
down_revision: Union[str, Sequence[str], None] = '066e30212dbb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create file_metadata table
    op.create_table(
        'file_metadata',
        sa.Column('file_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('bucket_name', sa.String(255), nullable=False, index=True),
        sa.Column('object_key', sa.String(1024), nullable=False, index=True),
        sa.Column('version_id', sa.String(255), nullable=True),
        sa.Column('original_filename', sa.String(512), nullable=False),
        sa.Column('file_size', sa.Integer, nullable=False),
        sa.Column('content_type', sa.String(255), nullable=True),
        sa.Column('file_extension', sa.String(50), nullable=True, index=True),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False, index=True),
        sa.Column('task_id', UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('agent_id', UUID(as_uuid=True), nullable=True, index=True),
        sa.Column('processing_status', sa.String(50), nullable=False, server_default='uploaded', index=True),
        sa.Column('processing_error', sa.String(1024), nullable=True),
        sa.Column('extracted_text', sa.Text, nullable=True),
        sa.Column('ocr_status', sa.String(50), nullable=True),
        sa.Column('transcription_status', sa.String(50), nullable=True),
        sa.Column('custom_metadata', JSON, nullable=True),
        sa.Column('access_level', sa.String(50), nullable=False, server_default='private', index=True),
        sa.Column('is_temporary', sa.Boolean, nullable=False, server_default='false', index=True),
        sa.Column('is_deleted', sa.Boolean, nullable=False, server_default='false', index=True),
        sa.Column('created_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime, nullable=False, server_default=sa.text('NOW()')),
        sa.Column('deleted_at', sa.DateTime, nullable=True),
    )
    
    # Create composite indexes
    op.create_index('idx_file_user_task', 'file_metadata', ['user_id', 'task_id'])
    op.create_index('idx_file_bucket_key', 'file_metadata', ['bucket_name', 'object_key'])
    op.create_index('idx_file_status', 'file_metadata', ['processing_status', 'is_deleted'])
    op.create_index('idx_file_temporary', 'file_metadata', ['is_temporary', 'created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_file_temporary', 'file_metadata')
    op.drop_index('idx_file_status', 'file_metadata')
    op.drop_index('idx_file_bucket_key', 'file_metadata')
    op.drop_index('idx_file_user_task', 'file_metadata')
    
    # Drop table
    op.drop_table('file_metadata')
