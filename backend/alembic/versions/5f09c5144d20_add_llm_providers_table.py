"""Add LLM providers table

Revision ID: 5f09c5144d20
Revises: b2c3d4e5f6g7
Create Date: 2026-01-22 21:58:55.935622

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5f09c5144d20'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6g7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # This migration historically re-created abac_policies even though the
    # previous revision had already added the table. Guard it so a clean
    # bootstrap can proceed through the full revision chain.
    if 'abac_policies' not in existing_tables:
        op.create_table('abac_policies',
        sa.Column('policy_id', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('effect', sa.String(length=50), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('actions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('conditions', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('policy_id')
        )
        op.create_index('idx_policy_priority', 'abac_policies', ['priority'], unique=False)
        op.create_index('idx_policy_resource_enabled', 'abac_policies', ['resource_type', 'enabled'], unique=False)
        op.create_index(op.f('ix_abac_policies_effect'), 'abac_policies', ['effect'], unique=False)
        op.create_index(op.f('ix_abac_policies_enabled'), 'abac_policies', ['enabled'], unique=False)
        op.create_index(op.f('ix_abac_policies_name'), 'abac_policies', ['name'], unique=False)
        op.create_index(op.f('ix_abac_policies_priority'), 'abac_policies', ['priority'], unique=False)
        op.create_index(op.f('ix_abac_policies_resource_type'), 'abac_policies', ['resource_type'], unique=False)

    if 'llm_providers' not in existing_tables:
        op.create_table('llm_providers',
        sa.Column('provider_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('protocol', sa.String(length=50), nullable=False),
        sa.Column('base_url', sa.String(length=500), nullable=False),
        sa.Column('api_key_encrypted', sa.Text(), nullable=True),
        sa.Column('timeout', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('models', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.user_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('provider_id')
        )
        op.create_index('idx_provider_enabled', 'llm_providers', ['enabled'], unique=False)
        op.create_index('idx_provider_protocol', 'llm_providers', ['protocol'], unique=False)
        op.create_index(op.f('ix_llm_providers_created_by'), 'llm_providers', ['created_by'], unique=False)
        op.create_index(op.f('ix_llm_providers_enabled'), 'llm_providers', ['enabled'], unique=False)
        op.create_index(op.f('ix_llm_providers_name'), 'llm_providers', ['name'], unique=True)
    op.drop_index(op.f('idx_file_bucket_key'), table_name='file_metadata')
    op.drop_index(op.f('idx_file_status'), table_name='file_metadata')
    op.drop_index(op.f('idx_file_temporary'), table_name='file_metadata')
    op.drop_index(op.f('idx_file_user_task'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_access_level'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_agent_id'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_bucket_name'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_file_extension'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_is_deleted'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_is_temporary'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_object_key'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_processing_status'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_task_id'), table_name='file_metadata')
    op.drop_index(op.f('ix_file_metadata_user_id'), table_name='file_metadata')
    op.drop_table('file_metadata')
    op.drop_index(op.f('ix_agent_templates_name'), table_name='agent_templates')
    op.drop_table('agent_templates')
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('agent_templates',
    sa.Column('template_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
    sa.Column('description', sa.TEXT(), autoincrement=False, nullable=False),
    sa.Column('default_skills', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('default_config', postgresql.JSONB(astext_type=sa.Text()), autoincrement=False, nullable=False),
    sa.Column('version', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.PrimaryKeyConstraint('template_id', name=op.f('agent_templates_pkey'))
    )
    op.create_index(op.f('ix_agent_templates_name'), 'agent_templates', ['name'], unique=True)
    op.create_table('file_metadata',
    sa.Column('file_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('bucket_name', sa.VARCHAR(length=255), autoincrement=False, nullable=False),
    sa.Column('object_key', sa.VARCHAR(length=1024), autoincrement=False, nullable=False),
    sa.Column('version_id', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
    sa.Column('original_filename', sa.VARCHAR(length=512), autoincrement=False, nullable=False),
    sa.Column('file_size', sa.INTEGER(), autoincrement=False, nullable=False),
    sa.Column('content_type', sa.VARCHAR(length=255), autoincrement=False, nullable=True),
    sa.Column('file_extension', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('user_id', sa.UUID(), autoincrement=False, nullable=False),
    sa.Column('task_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('agent_id', sa.UUID(), autoincrement=False, nullable=True),
    sa.Column('processing_status', sa.VARCHAR(length=50), server_default=sa.text("'uploaded'::character varying"), autoincrement=False, nullable=False),
    sa.Column('processing_error', sa.VARCHAR(length=1024), autoincrement=False, nullable=True),
    sa.Column('extracted_text', sa.TEXT(), autoincrement=False, nullable=True),
    sa.Column('ocr_status', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('transcription_status', sa.VARCHAR(length=50), autoincrement=False, nullable=True),
    sa.Column('custom_metadata', postgresql.JSON(astext_type=sa.Text()), autoincrement=False, nullable=True),
    sa.Column('access_level', sa.VARCHAR(length=50), server_default=sa.text("'private'::character varying"), autoincrement=False, nullable=False),
    sa.Column('is_temporary', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('is_deleted', sa.BOOLEAN(), server_default=sa.text('false'), autoincrement=False, nullable=False),
    sa.Column('created_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('updated_at', postgresql.TIMESTAMP(), server_default=sa.text('now()'), autoincrement=False, nullable=False),
    sa.Column('deleted_at', postgresql.TIMESTAMP(), autoincrement=False, nullable=True),
    sa.PrimaryKeyConstraint('file_id', name=op.f('file_metadata_pkey'))
    )
    op.create_index(op.f('ix_file_metadata_user_id'), 'file_metadata', ['user_id'], unique=False)
    op.create_index(op.f('ix_file_metadata_task_id'), 'file_metadata', ['task_id'], unique=False)
    op.create_index(op.f('ix_file_metadata_processing_status'), 'file_metadata', ['processing_status'], unique=False)
    op.create_index(op.f('ix_file_metadata_object_key'), 'file_metadata', ['object_key'], unique=False)
    op.create_index(op.f('ix_file_metadata_is_temporary'), 'file_metadata', ['is_temporary'], unique=False)
    op.create_index(op.f('ix_file_metadata_is_deleted'), 'file_metadata', ['is_deleted'], unique=False)
    op.create_index(op.f('ix_file_metadata_file_extension'), 'file_metadata', ['file_extension'], unique=False)
    op.create_index(op.f('ix_file_metadata_bucket_name'), 'file_metadata', ['bucket_name'], unique=False)
    op.create_index(op.f('ix_file_metadata_agent_id'), 'file_metadata', ['agent_id'], unique=False)
    op.create_index(op.f('ix_file_metadata_access_level'), 'file_metadata', ['access_level'], unique=False)
    op.create_index(op.f('idx_file_user_task'), 'file_metadata', ['user_id', 'task_id'], unique=False)
    op.create_index(op.f('idx_file_temporary'), 'file_metadata', ['is_temporary', 'created_at'], unique=False)
    op.create_index(op.f('idx_file_status'), 'file_metadata', ['processing_status', 'is_deleted'], unique=False)
    op.create_index(op.f('idx_file_bucket_key'), 'file_metadata', ['bucket_name', 'object_key'], unique=False)
    op.drop_index(op.f('ix_llm_providers_name'), table_name='llm_providers')
    op.drop_index(op.f('ix_llm_providers_enabled'), table_name='llm_providers')
    op.drop_index(op.f('ix_llm_providers_created_by'), table_name='llm_providers')
    op.drop_index('idx_provider_protocol', table_name='llm_providers')
    op.drop_index('idx_provider_enabled', table_name='llm_providers')
    op.drop_table('llm_providers')
    op.drop_index(op.f('ix_abac_policies_resource_type'), table_name='abac_policies')
    op.drop_index(op.f('ix_abac_policies_priority'), table_name='abac_policies')
    op.drop_index(op.f('ix_abac_policies_name'), table_name='abac_policies')
    op.drop_index(op.f('ix_abac_policies_enabled'), table_name='abac_policies')
    op.drop_index(op.f('ix_abac_policies_effect'), table_name='abac_policies')
    op.drop_index('idx_policy_resource_enabled', table_name='abac_policies')
    op.drop_index('idx_policy_priority', table_name='abac_policies')
    op.drop_table('abac_policies')
    # ### end Alembic commands ###
