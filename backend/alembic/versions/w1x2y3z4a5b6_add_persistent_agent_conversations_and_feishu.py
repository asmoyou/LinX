"""Add persistent agent conversations and external channel tables.

Revision ID: w1x2y3z4a5b6
Revises: v9w8x7y6z5a4
Create Date: 2026-02-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "w1x2y3z4a5b6"
down_revision = "v9w8x7y6z5a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_conversations",
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="web"),
        sa.Column("latest_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conversation_id"),
    )
    op.create_index(
        "idx_agent_conversations_owner_agent",
        "agent_conversations",
        ["owner_user_id", "agent_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_agent_conversations_agent_updated",
        "agent_conversations",
        ["agent_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_agent_id"),
        "agent_conversations",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_owner_user_id"),
        "agent_conversations",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_status"),
        "agent_conversations",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_source"),
        "agent_conversations",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_latest_snapshot_id"),
        "agent_conversations",
        ["latest_snapshot_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversations_last_message_at"),
        "agent_conversations",
        ["last_message_at"],
        unique=False,
    )

    op.create_table(
        "agent_conversation_snapshots",
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("archive_ref", sa.Text(), nullable=True),
        sa.Column("manifest_ref", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("snapshot_status", sa.String(length=32), nullable=False, server_default="ready"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index(
        "ux_agent_conversation_snapshots_generation",
        "agent_conversation_snapshots",
        ["conversation_id", "generation"],
        unique=True,
    )
    op.create_index(
        op.f("ix_agent_conversation_snapshots_conversation_id"),
        "agent_conversation_snapshots",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_snapshots_snapshot_status"),
        "agent_conversation_snapshots",
        ["snapshot_status"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_agent_conversations_latest_snapshot_id",
        "agent_conversations",
        "agent_conversation_snapshots",
        ["latest_snapshot_id"],
        ["snapshot_id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "agent_conversation_messages",
        sa.Column(
            "message_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("content_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("attachments_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="web"),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["agent_conversations.conversation_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id"),
    )
    op.create_index(
        "idx_agent_conversation_messages_conversation_created",
        "agent_conversation_messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_agent_conversation_messages_external_event",
        "agent_conversation_messages",
        ["conversation_id", "external_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_messages_conversation_id"),
        "agent_conversation_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_messages_role"),
        "agent_conversation_messages",
        ["role"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_messages_source"),
        "agent_conversation_messages",
        ["source"],
        unique=False,
    )
    op.create_index(
        op.f("ix_agent_conversation_messages_external_event_id"),
        "agent_conversation_messages",
        ["external_event_id"],
        unique=False,
    )

    op.create_table(
        "user_binding_codes",
        sa.Column(
            "code_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=128), nullable=False),
        sa.Column("code_encrypted", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("code_id"),
        sa.UniqueConstraint("code_hash"),
    )
    op.create_index(
        "idx_user_binding_codes_user_status",
        "user_binding_codes",
        ["user_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_user_binding_codes_user_id"), "user_binding_codes", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_binding_codes_code_hash"), "user_binding_codes", ["code_hash"], unique=False)
    op.create_index(op.f("ix_user_binding_codes_status"), "user_binding_codes", ["status"], unique=False)

    op.create_table(
        "agent_channel_publications",
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("channel_identity", sa.String(length=255), nullable=True),
        sa.Column("config_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("secret_encrypted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("webhook_path", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("publication_id"),
    )
    op.create_index(
        "ux_agent_channel_publications_agent_channel",
        "agent_channel_publications",
        ["agent_id", "channel_type"],
        unique=True,
    )
    op.create_index(op.f("ix_agent_channel_publications_agent_id"), "agent_channel_publications", ["agent_id"], unique=False)
    op.create_index(op.f("ix_agent_channel_publications_channel_type"), "agent_channel_publications", ["channel_type"], unique=False)
    op.create_index(op.f("ix_agent_channel_publications_status"), "agent_channel_publications", ["status"], unique=False)

    op.create_table(
        "user_external_bindings",
        sa.Column(
            "binding_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("external_open_id", sa.String(length=255), nullable=True),
        sa.Column("external_union_id", sa.String(length=255), nullable=True),
        sa.Column("tenant_key", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["publication_id"], ["agent_channel_publications.publication_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("binding_id"),
    )
    op.create_index(
        "ux_user_external_bindings_publication_open_id",
        "user_external_bindings",
        ["publication_id", "external_open_id"],
        unique=True,
    )
    op.create_index(op.f("ix_user_external_bindings_user_id"), "user_external_bindings", ["user_id"], unique=False)
    op.create_index(op.f("ix_user_external_bindings_channel_type"), "user_external_bindings", ["channel_type"], unique=False)
    op.create_index(op.f("ix_user_external_bindings_publication_id"), "user_external_bindings", ["publication_id"], unique=False)
    op.create_index(op.f("ix_user_external_bindings_external_user_id"), "user_external_bindings", ["external_user_id"], unique=False)
    op.create_index(op.f("ix_user_external_bindings_external_open_id"), "user_external_bindings", ["external_open_id"], unique=False)
    op.create_index(op.f("ix_user_external_bindings_external_union_id"), "user_external_bindings", ["external_union_id"], unique=False)
    op.create_index(op.f("ix_user_external_bindings_tenant_key"), "user_external_bindings", ["tenant_key"], unique=False)

    op.create_table(
        "external_conversation_links",
        sa.Column(
            "link_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "publication_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("external_chat_key", sa.String(length=255), nullable=False),
        sa.Column("external_thread_key", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["agent_conversations.conversation_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["agent_channel_publications.publication_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("link_id"),
    )
    op.create_index(
        "ux_external_conversation_links_publication_chat_thread",
        "external_conversation_links",
        ["publication_id", "external_chat_key", "external_thread_key"],
        unique=True,
    )
    op.create_index(op.f("ix_external_conversation_links_publication_id"), "external_conversation_links", ["publication_id"], unique=False)
    op.create_index(op.f("ix_external_conversation_links_conversation_id"), "external_conversation_links", ["conversation_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_external_conversation_links_conversation_id"), table_name="external_conversation_links")
    op.drop_index(op.f("ix_external_conversation_links_publication_id"), table_name="external_conversation_links")
    op.drop_index(
        "ux_external_conversation_links_publication_chat_thread",
        table_name="external_conversation_links",
    )
    op.drop_table("external_conversation_links")

    op.drop_index(op.f("ix_user_external_bindings_tenant_key"), table_name="user_external_bindings")
    op.drop_index(op.f("ix_user_external_bindings_external_union_id"), table_name="user_external_bindings")
    op.drop_index(op.f("ix_user_external_bindings_external_open_id"), table_name="user_external_bindings")
    op.drop_index(op.f("ix_user_external_bindings_external_user_id"), table_name="user_external_bindings")
    op.drop_index(op.f("ix_user_external_bindings_publication_id"), table_name="user_external_bindings")
    op.drop_index(op.f("ix_user_external_bindings_channel_type"), table_name="user_external_bindings")
    op.drop_index(op.f("ix_user_external_bindings_user_id"), table_name="user_external_bindings")
    op.drop_index(
        "ux_user_external_bindings_publication_open_id",
        table_name="user_external_bindings",
    )
    op.drop_table("user_external_bindings")

    op.drop_index(op.f("ix_agent_channel_publications_status"), table_name="agent_channel_publications")
    op.drop_index(op.f("ix_agent_channel_publications_channel_type"), table_name="agent_channel_publications")
    op.drop_index(op.f("ix_agent_channel_publications_agent_id"), table_name="agent_channel_publications")
    op.drop_index(
        "ux_agent_channel_publications_agent_channel",
        table_name="agent_channel_publications",
    )
    op.drop_table("agent_channel_publications")

    op.drop_index(op.f("ix_user_binding_codes_status"), table_name="user_binding_codes")
    op.drop_index(op.f("ix_user_binding_codes_code_hash"), table_name="user_binding_codes")
    op.drop_index(op.f("ix_user_binding_codes_user_id"), table_name="user_binding_codes")
    op.drop_index("idx_user_binding_codes_user_status", table_name="user_binding_codes")
    op.drop_table("user_binding_codes")

    op.drop_index(
        op.f("ix_agent_conversation_messages_external_event_id"),
        table_name="agent_conversation_messages",
    )
    op.drop_index(op.f("ix_agent_conversation_messages_source"), table_name="agent_conversation_messages")
    op.drop_index(op.f("ix_agent_conversation_messages_role"), table_name="agent_conversation_messages")
    op.drop_index(
        op.f("ix_agent_conversation_messages_conversation_id"),
        table_name="agent_conversation_messages",
    )
    op.drop_index(
        "idx_agent_conversation_messages_external_event",
        table_name="agent_conversation_messages",
    )
    op.drop_index(
        "idx_agent_conversation_messages_conversation_created",
        table_name="agent_conversation_messages",
    )
    op.drop_table("agent_conversation_messages")

    op.drop_constraint(
        "fk_agent_conversations_latest_snapshot_id",
        "agent_conversations",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_agent_conversation_snapshots_snapshot_status"), table_name="agent_conversation_snapshots")
    op.drop_index(op.f("ix_agent_conversation_snapshots_conversation_id"), table_name="agent_conversation_snapshots")
    op.drop_index(
        "ux_agent_conversation_snapshots_generation",
        table_name="agent_conversation_snapshots",
    )
    op.drop_table("agent_conversation_snapshots")

    op.drop_index(op.f("ix_agent_conversations_last_message_at"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_latest_snapshot_id"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_source"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_status"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_owner_user_id"), table_name="agent_conversations")
    op.drop_index(op.f("ix_agent_conversations_agent_id"), table_name="agent_conversations")
    op.drop_index("idx_agent_conversations_agent_updated", table_name="agent_conversations")
    op.drop_index("idx_agent_conversations_owner_agent", table_name="agent_conversations")
    op.drop_table("agent_conversations")
