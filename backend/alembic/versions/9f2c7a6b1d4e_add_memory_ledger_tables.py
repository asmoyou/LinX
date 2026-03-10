"""add_memory_ledger_tables

Revision ID: 9f2c7a6b1d4e
Revises: p3c4d5e6f7g8
Create Date: 2026-03-07 16:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f2c7a6b1d4e"
down_revision: Union[str, Sequence[str], None] = "p3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "memory_sessions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(length=255), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("end_reason", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "session_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
    )
    op.create_index("ix_memory_sessions_session_id", "memory_sessions", ["session_id"], unique=True)
    op.create_index("ix_memory_sessions_agent_id", "memory_sessions", ["agent_id"], unique=False)
    op.create_index("ix_memory_sessions_user_id", "memory_sessions", ["user_id"], unique=False)
    op.create_index("ix_memory_sessions_status", "memory_sessions", ["status"], unique=False)
    op.create_index(
        "ix_memory_sessions_end_reason",
        "memory_sessions",
        ["end_reason"],
        unique=False,
    )
    op.create_index(
        "ix_memory_sessions_started_at",
        "memory_sessions",
        ["started_at"],
        unique=False,
    )
    op.create_index("ix_memory_sessions_ended_at", "memory_sessions", ["ended_at"], unique=False)
    op.create_index(
        "idx_memory_sessions_agent_status",
        "memory_sessions",
        ["agent_id", "status"],
        unique=False,
    )
    op.create_index(
        "idx_memory_sessions_user_started",
        "memory_sessions",
        ["user_id", "started_at"],
        unique=False,
    )

    op.create_table(
        "memory_session_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("memory_session_id", sa.BigInteger(), nullable=False),
        sa.Column("event_index", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("event_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["memory_session_id"],
            ["memory_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_memory_session_events_memory_session_id",
        "memory_session_events",
        ["memory_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_session_events_event_kind",
        "memory_session_events",
        ["event_kind"],
        unique=False,
    )
    op.create_index(
        "ix_memory_session_events_role",
        "memory_session_events",
        ["role"],
        unique=False,
    )
    op.create_index(
        "ix_memory_session_events_event_timestamp",
        "memory_session_events",
        ["event_timestamp"],
        unique=False,
    )
    op.create_index(
        "idx_memory_session_events_session_order",
        "memory_session_events",
        ["memory_session_id", "event_index"],
        unique=False,
    )

    op.create_table(
        "memory_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("memory_session_id", sa.BigInteger(), nullable=False),
        sa.Column("observation_key", sa.String(length=255), nullable=False),
        sa.Column("observation_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column(
            "source_event_indexes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("importance", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column(
            "observation_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
            ["memory_session_id"],
            ["memory_sessions.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_memory_observations_memory_session_id",
        "memory_observations",
        ["memory_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_observations_observation_key",
        "memory_observations",
        ["observation_key"],
        unique=False,
    )
    op.create_index(
        "ix_memory_observations_observation_type",
        "memory_observations",
        ["observation_type"],
        unique=False,
    )
    op.create_index(
        "idx_memory_observations_session_type",
        "memory_observations",
        ["memory_session_id", "observation_type"],
        unique=False,
    )
    op.create_index(
        "idx_memory_observations_type_key",
        "memory_observations",
        ["observation_type", "observation_key"],
        unique=False,
    )

    op.create_table(
        "memory_materializations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("owner_type", sa.String(length=32), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("materialization_type", sa.String(length=64), nullable=False),
        sa.Column("materialization_key", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column(
            "materialized_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
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
    op.create_index(
        "ix_memory_materializations_owner_type",
        "memory_materializations",
        ["owner_type"],
        unique=False,
    )
    op.create_index(
        "ix_memory_materializations_owner_id",
        "memory_materializations",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_materializations_materialization_type",
        "memory_materializations",
        ["materialization_type"],
        unique=False,
    )
    op.create_index(
        "ix_memory_materializations_status",
        "memory_materializations",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_memory_materializations_source_session_id",
        "memory_materializations",
        ["source_session_id"],
        unique=False,
    )
    op.create_index(
        "ix_memory_materializations_source_observation_id",
        "memory_materializations",
        ["source_observation_id"],
        unique=False,
    )
    op.create_index(
        "idx_memory_materializations_owner_type",
        "memory_materializations",
        ["owner_type", "owner_id", "materialization_type"],
        unique=False,
    )
    op.create_index(
        "ux_memory_materializations_owner_key",
        "memory_materializations",
        ["owner_type", "owner_id", "materialization_type", "materialization_key"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ux_memory_materializations_owner_key",
        table_name="memory_materializations",
    )
    op.drop_index(
        "idx_memory_materializations_owner_type",
        table_name="memory_materializations",
    )
    op.drop_index(
        "ix_memory_materializations_source_observation_id",
        table_name="memory_materializations",
    )
    op.drop_index(
        "ix_memory_materializations_source_session_id",
        table_name="memory_materializations",
    )
    op.drop_index("ix_memory_materializations_status", table_name="memory_materializations")
    op.drop_index(
        "ix_memory_materializations_materialization_type",
        table_name="memory_materializations",
    )
    op.drop_index("ix_memory_materializations_owner_id", table_name="memory_materializations")
    op.drop_index(
        "ix_memory_materializations_owner_type",
        table_name="memory_materializations",
    )
    op.drop_table("memory_materializations")

    op.drop_index("idx_memory_observations_type_key", table_name="memory_observations")
    op.drop_index("idx_memory_observations_session_type", table_name="memory_observations")
    op.drop_index(
        "ix_memory_observations_observation_type",
        table_name="memory_observations",
    )
    op.drop_index("ix_memory_observations_observation_key", table_name="memory_observations")
    op.drop_index(
        "ix_memory_observations_memory_session_id",
        table_name="memory_observations",
    )
    op.drop_table("memory_observations")

    op.drop_index(
        "idx_memory_session_events_session_order",
        table_name="memory_session_events",
    )
    op.drop_index(
        "ix_memory_session_events_event_timestamp",
        table_name="memory_session_events",
    )
    op.drop_index("ix_memory_session_events_role", table_name="memory_session_events")
    op.drop_index("ix_memory_session_events_event_kind", table_name="memory_session_events")
    op.drop_index(
        "ix_memory_session_events_memory_session_id",
        table_name="memory_session_events",
    )
    op.drop_table("memory_session_events")

    op.drop_index("idx_memory_sessions_user_started", table_name="memory_sessions")
    op.drop_index("idx_memory_sessions_agent_status", table_name="memory_sessions")
    op.drop_index("ix_memory_sessions_ended_at", table_name="memory_sessions")
    op.drop_index("ix_memory_sessions_started_at", table_name="memory_sessions")
    op.drop_index("ix_memory_sessions_end_reason", table_name="memory_sessions")
    op.drop_index("ix_memory_sessions_status", table_name="memory_sessions")
    op.drop_index("ix_memory_sessions_user_id", table_name="memory_sessions")
    op.drop_index("ix_memory_sessions_agent_id", table_name="memory_sessions")
    op.drop_index("ix_memory_sessions_session_id", table_name="memory_sessions")
    op.drop_table("memory_sessions")
