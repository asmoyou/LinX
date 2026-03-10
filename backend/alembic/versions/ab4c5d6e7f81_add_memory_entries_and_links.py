"""add_memory_entries_and_links

Revision ID: ab4c5d6e7f81
Revises: 9f2c7a6b1d4e
Create Date: 2026-03-10 16:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ab4c5d6e7f81"
down_revision: Union[str, Sequence[str], None] = "9f2c7a6b1d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "memory_entries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("entry_type", sa.String(length=64), nullable=False),
        sa.Column("entry_key", sa.String(length=255), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("entry_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_session_id", sa.BigInteger(), nullable=True),
        sa.Column("source_observation_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["memory_sessions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_observation_id"],
            ["memory_observations.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_memory_entries_owner_type", "memory_entries", ["owner_type"], unique=False)
    op.create_index("ix_memory_entries_owner_id", "memory_entries", ["owner_id"], unique=False)
    op.create_index("ix_memory_entries_entry_type", "memory_entries", ["entry_type"], unique=False)
    op.create_index("ix_memory_entries_status", "memory_entries", ["status"], unique=False)
    op.create_index(
        "ix_memory_entries_source_session_id",
        "memory_entries",
        ["source_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_entries_source_observation_id",
        "memory_entries",
        ["source_observation_id"],
        unique=False,
    )
    op.create_index(
        "idx_memory_entries_owner_type",
        "memory_entries",
        ["owner_type", "owner_id", "entry_type"],
        unique=False,
    )
    op.create_index(
        "ux_memory_entries_owner_key",
        "memory_entries",
        ["owner_type", "owner_id", "entry_type", "entry_key"],
        unique=True,
    )

    op.create_table(
        "memory_links",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_session_id", sa.BigInteger(), nullable=True),
        sa.Column("source_kind", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("target_kind", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False),
        sa.Column("link_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["source_session_id"],
            ["memory_sessions.id"],
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_memory_links_source_session_id",
        "memory_links",
        ["source_session_id"],
        unique=False,
    )
    op.create_index("ix_memory_links_source_kind", "memory_links", ["source_kind"], unique=False)
    op.create_index("ix_memory_links_source_id", "memory_links", ["source_id"], unique=False)
    op.create_index("ix_memory_links_target_kind", "memory_links", ["target_kind"], unique=False)
    op.create_index("ix_memory_links_target_id", "memory_links", ["target_id"], unique=False)
    op.create_index("ix_memory_links_link_type", "memory_links", ["link_type"], unique=False)
    op.create_index(
        "idx_memory_links_source",
        "memory_links",
        ["source_kind", "source_id", "link_type"],
        unique=False,
    )
    op.create_index(
        "idx_memory_links_target",
        "memory_links",
        ["target_kind", "target_id", "link_type"],
        unique=False,
    )
    op.create_index(
        "ux_memory_links_identity",
        "memory_links",
        ["source_kind", "source_id", "target_kind", "target_id", "link_type"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ux_memory_links_identity", table_name="memory_links")
    op.drop_index("idx_memory_links_target", table_name="memory_links")
    op.drop_index("idx_memory_links_source", table_name="memory_links")
    op.drop_index("ix_memory_links_link_type", table_name="memory_links")
    op.drop_index("ix_memory_links_target_id", table_name="memory_links")
    op.drop_index("ix_memory_links_target_kind", table_name="memory_links")
    op.drop_index("ix_memory_links_source_id", table_name="memory_links")
    op.drop_index("ix_memory_links_source_kind", table_name="memory_links")
    op.drop_index("ix_memory_links_source_session_id", table_name="memory_links")
    op.drop_table("memory_links")

    op.drop_index("ux_memory_entries_owner_key", table_name="memory_entries")
    op.drop_index("idx_memory_entries_owner_type", table_name="memory_entries")
    op.drop_index("ix_memory_entries_source_observation_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_source_session_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_status", table_name="memory_entries")
    op.drop_index("ix_memory_entries_entry_type", table_name="memory_entries")
    op.drop_index("ix_memory_entries_owner_id", table_name="memory_entries")
    op.drop_index("ix_memory_entries_owner_type", table_name="memory_entries")
    op.drop_table("memory_entries")
