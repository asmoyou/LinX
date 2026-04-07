"""add external runtime binding and dispatch tables

Revision ID: x3t4r5n6a7l8
Revises: u2n1f1e5d6m7
Create Date: 2026-04-07 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision: str = "x3t4r5n6a7l8"
down_revision: Union[str, Sequence[str], None] = "u2n1f1e5d6m7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "external_agent_profiles" not in tables:
        op.create_table(
            "external_agent_profiles",
            sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("path_allowlist", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
            sa.Column("launch_command_template", sa.Text(), nullable=True),
            sa.Column("install_channel", sa.String(length=32), nullable=False, server_default="stable"),
            sa.Column("desired_version", sa.String(length=64), nullable=False, server_default="0.1.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("profile_id"),
            sa.UniqueConstraint("agent_id", name="uq_external_agent_profiles_agent_id"),
        )
        op.create_index("ix_external_agent_profiles_agent_id", "external_agent_profiles", ["agent_id"], unique=False)

    if "external_agent_bindings" not in tables:
        op.create_table(
            "external_agent_bindings",
            sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("host_name", sa.String(length=255), nullable=True),
            sa.Column("host_os", sa.String(length=32), nullable=True),
            sa.Column("host_arch", sa.String(length=64), nullable=True),
            sa.Column("host_fingerprint", sa.String(length=128), nullable=True),
            sa.Column("machine_token_hash", sa.String(length=128), nullable=False),
            sa.Column("machine_token_prefix", sa.String(length=24), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="offline"),
            sa.Column("current_version", sa.String(length=64), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("bound_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error_message", sa.Text(), nullable=True),
            sa.Column("binding_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("binding_id"),
            sa.UniqueConstraint("agent_id", name="uq_external_agent_bindings_agent_id"),
        )
        op.create_index("ix_external_agent_bindings_agent_id", "external_agent_bindings", ["agent_id"])
        op.create_index("ix_external_agent_bindings_machine_token_hash", "external_agent_bindings", ["machine_token_hash"])
        op.create_index("ix_external_agent_bindings_status", "external_agent_bindings", ["status"])
        op.create_index("ix_external_agent_bindings_last_seen_at", "external_agent_bindings", ["last_seen_at"])

    if "external_agent_install_tokens" not in tables:
        op.create_table(
            "external_agent_install_tokens",
            sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("token_hash", sa.String(length=128), nullable=False),
            sa.Column("token_prefix", sa.String(length=24), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.user_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("token_id"),
        )
        op.create_index("ix_external_agent_install_tokens_agent_id", "external_agent_install_tokens", ["agent_id"])
        op.create_index("ix_external_agent_install_tokens_token_hash", "external_agent_install_tokens", ["token_hash"])
        op.create_index("ix_external_agent_install_tokens_expires_at", "external_agent_install_tokens", ["expires_at"])
        op.create_index("idx_external_agent_install_token_agent_status", "external_agent_install_tokens", ["agent_id", "status"])

    if "external_agent_dispatches" not in tables:
        op.create_table(
            "external_agent_dispatches",
            sa.Column("dispatch_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("run_step_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("source_type", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("source_id", sa.String(length=128), nullable=False),
            sa.Column("runtime_type", sa.String(length=50), nullable=False),
            sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["binding_id"], ["external_agent_bindings.binding_id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["run_id"], ["project_runs.run_id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["run_step_id"], ["project_run_steps.run_step_id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("dispatch_id"),
        )
        op.create_index("ix_external_agent_dispatches_agent_id", "external_agent_dispatches", ["agent_id"])
        op.create_index("ix_external_agent_dispatches_binding_id", "external_agent_dispatches", ["binding_id"])
        op.create_index("ix_external_agent_dispatches_run_id", "external_agent_dispatches", ["run_id"])
        op.create_index("ix_external_agent_dispatches_run_step_id", "external_agent_dispatches", ["run_step_id"])
        op.create_index("idx_external_agent_dispatch_binding_status", "external_agent_dispatches", ["binding_id", "status"])
        op.create_index("idx_external_agent_dispatch_agent_status", "external_agent_dispatches", ["agent_id", "status"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "external_agent_dispatches" in tables:
        op.drop_index("idx_external_agent_dispatch_agent_status", table_name="external_agent_dispatches")
        op.drop_index("idx_external_agent_dispatch_binding_status", table_name="external_agent_dispatches")
        op.drop_index("ix_external_agent_dispatches_run_step_id", table_name="external_agent_dispatches")
        op.drop_index("ix_external_agent_dispatches_run_id", table_name="external_agent_dispatches")
        op.drop_index("ix_external_agent_dispatches_binding_id", table_name="external_agent_dispatches")
        op.drop_index("ix_external_agent_dispatches_agent_id", table_name="external_agent_dispatches")
        op.drop_table("external_agent_dispatches")
    if "external_agent_install_tokens" in tables:
        op.drop_index("idx_external_agent_install_token_agent_status", table_name="external_agent_install_tokens")
        op.drop_index("ix_external_agent_install_tokens_expires_at", table_name="external_agent_install_tokens")
        op.drop_index("ix_external_agent_install_tokens_token_hash", table_name="external_agent_install_tokens")
        op.drop_index("ix_external_agent_install_tokens_agent_id", table_name="external_agent_install_tokens")
        op.drop_table("external_agent_install_tokens")
    if "external_agent_bindings" in tables:
        op.drop_index("ix_external_agent_bindings_last_seen_at", table_name="external_agent_bindings")
        op.drop_index("ix_external_agent_bindings_status", table_name="external_agent_bindings")
        op.drop_index("ix_external_agent_bindings_machine_token_hash", table_name="external_agent_bindings")
        op.drop_index("ix_external_agent_bindings_agent_id", table_name="external_agent_bindings")
        op.drop_table("external_agent_bindings")
    if "external_agent_profiles" in tables:
        op.drop_index("ix_external_agent_profiles_agent_id", table_name="external_agent_profiles")
        op.drop_table("external_agent_profiles")
