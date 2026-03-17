"""Add typed user-memory relations table.

Revision ID: u1v2w3x4y5z6
Revises: t4u5v6w7x8y9
Create Date: 2026-03-22 10:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, Sequence[str], None] = "t4u5v6w7x8y9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "user_memory_relations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("relation_key", sa.String(length=255), nullable=False),
        sa.Column("predicate", sa.String(length=64), nullable=False),
        sa.Column(
            "subject_type",
            sa.String(length=32),
            nullable=False,
            server_default="user",
        ),
        sa.Column("subject_text", sa.String(length=255), nullable=True),
        sa.Column("object_text", sa.Text(), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("event_time", sa.String(length=255), nullable=True),
        sa.Column("event_time_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_time_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("persons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="active",
        ),
        sa.Column("source_entry_id", sa.BigInteger(), nullable=True),
        sa.Column("source_session_ledger_id", sa.BigInteger(), nullable=True),
        sa.Column("relation_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["source_entry_id"],
            ["user_memory_entries.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_session_ledger_id"],
            ["session_ledgers.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_user_memory_relations_user_predicate",
        "user_memory_relations",
        ["user_id", "predicate", "status"],
        unique=False,
    )
    op.create_index(
        "ix_user_memory_relations_event_time_start",
        "user_memory_relations",
        ["event_time_start"],
        unique=False,
    )
    op.create_index(
        "ix_user_memory_relations_event_time_end",
        "user_memory_relations",
        ["event_time_end"],
        unique=False,
    )
    op.create_index(
        "ix_user_memory_relations_source_entry_id",
        "user_memory_relations",
        ["source_entry_id"],
        unique=False,
    )
    op.create_index(
        "ix_user_memory_relations_source_session_ledger_id",
        "user_memory_relations",
        ["source_session_ledger_id"],
        unique=False,
    )
    op.create_index(
        "ux_user_memory_relations_user_key",
        "user_memory_relations",
        ["user_id", "relation_key"],
        unique=True,
    )
    op.create_index(
        "idx_user_memory_relations_object_text_trgm",
        "user_memory_relations",
        ["object_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"object_text": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "idx_user_memory_relations_object_text_trgm",
        table_name="user_memory_relations",
    )
    op.drop_index(
        "ix_user_memory_relations_source_session_ledger_id",
        table_name="user_memory_relations",
    )
    op.drop_index(
        "ix_user_memory_relations_source_entry_id",
        table_name="user_memory_relations",
    )
    op.drop_index(
        "ix_user_memory_relations_event_time_end",
        table_name="user_memory_relations",
    )
    op.drop_index(
        "ix_user_memory_relations_event_time_start",
        table_name="user_memory_relations",
    )
    op.drop_index("ux_user_memory_relations_user_key", table_name="user_memory_relations")
    op.drop_index(
        "idx_user_memory_relations_user_predicate",
        table_name="user_memory_relations",
    )
    op.drop_table("user_memory_relations")
