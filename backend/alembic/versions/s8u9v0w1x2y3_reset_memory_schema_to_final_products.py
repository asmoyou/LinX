"""reset_memory_schema_to_final_products

Revision ID: s8u9v0w1x2y3
Revises: r7s8t9u0v1w2
Create Date: 2026-03-12 23:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "s8u9v0w1x2y3"
down_revision: Union[str, Sequence[str], None] = "r7s8t9u0v1w2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Destructive reset: old generic/transitional memory tables are dropped outright.
    for table_name in (
        "memory_acl",
        "memory_records",
        "memory_links",
        "memory_entries",
        "memory_materializations",
        "memory_observations",
        "memory_session_events",
        "memory_sessions",
    ):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))

    op.create_table(
        "session_ledgers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("end_reason", sa.String(length=64), nullable=True),
        sa.Column("ledger_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_session_ledgers_session_id", "session_ledgers", ["session_id"], unique=True)
    op.create_index("ix_session_ledgers_user_id", "session_ledgers", ["user_id"], unique=False)
    op.create_index("ix_session_ledgers_agent_id", "session_ledgers", ["agent_id"], unique=False)
    op.create_index("ix_session_ledgers_status", "session_ledgers", ["status"], unique=False)
    op.create_index("ix_session_ledgers_started_at", "session_ledgers", ["started_at"], unique=False)
    op.create_index("ix_session_ledgers_ended_at", "session_ledgers", ["ended_at"], unique=False)
    op.create_index(
        "idx_session_ledgers_agent_status",
        "session_ledgers",
        ["agent_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_session_ledgers_user_started",
        "session_ledgers",
        ["user_id", "started_at"],
        unique=False,
    )

    op.create_table(
        "session_ledger_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_ledger_id", sa.BigInteger(), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_ledger_id"], ["session_ledgers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_session_ledger_events_session_ledger_id",
        "session_ledger_events",
        ["session_ledger_id"],
        unique=False,
    )
    op.create_index("ix_session_ledger_events_event_kind", "session_ledger_events", ["event_kind"], unique=False)
    op.create_index("ix_session_ledger_events_role", "session_ledger_events", ["role"], unique=False)
    op.create_index(
        "ix_session_ledger_events_event_timestamp",
        "session_ledger_events",
        ["event_timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_session_ledger_events_session_order",
        "session_ledger_events",
        ["session_ledger_id", "event_index"],
        unique=False,
    )

    op.create_table(
        "user_memory_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("entry_key", sa.String(length=255), nullable=False),
        sa.Column("fact_kind", sa.String(length=64), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("predicate", sa.String(length=255), nullable=True),
        sa.Column("object_text", sa.Text(), nullable=True),
        sa.Column("event_time", sa.String(length=255), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("persons", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("entities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("source_session_ledger_id", sa.BigInteger(), nullable=True),
        sa.Column("source_event_indexes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("entry_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("superseded_by_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["source_session_ledger_id"], ["session_ledgers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["user_memory_entries.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_memory_entries_user_id", "user_memory_entries", ["user_id"], unique=False)
    op.create_index("ix_user_memory_entries_fact_kind", "user_memory_entries", ["fact_kind"], unique=False)
    op.create_index("ix_user_memory_entries_status", "user_memory_entries", ["status"], unique=False)
    op.create_index(
        "ix_user_memory_entries_source_session_ledger_id",
        "user_memory_entries",
        ["source_session_ledger_id"],
        unique=False,
    )
    op.create_index(
        "idx_user_memory_entries_user_fact_status",
        "user_memory_entries",
        ["user_id", "fact_kind", "status"],
        unique=False,
    )
    op.create_index(
        "ux_user_memory_entries_user_key",
        "user_memory_entries",
        ["user_id", "entry_key"],
        unique=True,
    )

    op.create_table(
        "user_memory_links",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("source_entry_id", sa.BigInteger(), nullable=False),
        sa.Column("target_entry_id", sa.BigInteger(), nullable=False),
        sa.Column("link_type", sa.String(length=64), nullable=False),
        sa.Column("link_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["source_entry_id"], ["user_memory_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_entry_id"], ["user_memory_entries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_memory_links_user_id", "user_memory_links", ["user_id"], unique=False)
    op.create_index("ix_user_memory_links_link_type", "user_memory_links", ["link_type"], unique=False)
    op.create_index(
        "idx_user_memory_links_source",
        "user_memory_links",
        ["user_id", "source_entry_id", "link_type"],
        unique=False,
    )
    op.create_index(
        "idx_user_memory_links_target",
        "user_memory_links",
        ["user_id", "target_entry_id", "link_type"],
        unique=False,
    )
    op.create_index(
        "ux_user_memory_links_identity",
        "user_memory_links",
        ["user_id", "source_entry_id", "target_entry_id", "link_type"],
        unique=True,
    )

    op.create_table(
        "user_memory_views",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("view_type", sa.String(length=64), nullable=False),
        sa.Column("view_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("view_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_memory_views_user_id", "user_memory_views", ["user_id"], unique=False)
    op.create_index("ix_user_memory_views_view_type", "user_memory_views", ["view_type"], unique=False)
    op.create_index("ix_user_memory_views_status", "user_memory_views", ["status"], unique=False)
    op.create_index(
        "idx_user_memory_views_user_type",
        "user_memory_views",
        ["user_id", "view_type", "status"],
        unique=False,
    )
    op.create_index(
        "ux_user_memory_views_user_key",
        "user_memory_views",
        ["user_id", "view_type", "view_key"],
        unique=True,
    )

    op.create_table(
        "skill_proposals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("proposal_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("successful_path", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("why_it_worked", sa.Text(), nullable=True),
        sa.Column("applicability", sa.Text(), nullable=True),
        sa.Column("avoid", sa.Text(), nullable=True),
        sa.Column("evidence_session_ledger_id", sa.BigInteger(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.72"),
        sa.Column("review_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("published_skill_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("proposal_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["evidence_session_ledger_id"], ["session_ledgers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["published_skill_id"], ["skills.skill_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skill_proposals_agent_id", "skill_proposals", ["agent_id"], unique=False)
    op.create_index("ix_skill_proposals_user_id", "skill_proposals", ["user_id"], unique=False)
    op.create_index("ix_skill_proposals_review_status", "skill_proposals", ["review_status"], unique=False)
    op.create_index(
        "ix_skill_proposals_evidence_session_ledger_id",
        "skill_proposals",
        ["evidence_session_ledger_id"],
        unique=False,
    )
    op.create_index(
        "ix_skill_proposals_published_skill_id",
        "skill_proposals",
        ["published_skill_id"],
        unique=False,
    )
    op.create_index(
        "idx_skill_proposals_agent_review",
        "skill_proposals",
        ["agent_id", "review_status"],
        unique=False,
    )
    op.create_index(
        "idx_skill_proposals_user_created",
        "skill_proposals",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ux_skill_proposals_agent_key",
        "skill_proposals",
        ["agent_id", "proposal_key"],
        unique=True,
    )


def downgrade() -> None:
    raise NotImplementedError("This destructive reset migration is intentionally irreversible")
