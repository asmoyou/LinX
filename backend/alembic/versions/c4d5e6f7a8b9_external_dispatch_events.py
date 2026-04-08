"""external dispatch events

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-08 15:50:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "external_agent_dispatch_events" not in tables:
        op.create_table(
            "external_agent_dispatch_events",
            sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("dispatch_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("sequence_number", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column(
                "payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ["dispatch_id"],
                ["external_agent_dispatches.dispatch_id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("event_id"),
        )
        op.create_index(
            "ix_external_agent_dispatch_events_dispatch_id",
            "external_agent_dispatch_events",
            ["dispatch_id"],
        )
        op.create_index(
            "ix_external_agent_dispatch_events_event_type",
            "external_agent_dispatch_events",
            ["event_type"],
        )
        op.create_index(
            "ux_external_agent_dispatch_events_sequence",
            "external_agent_dispatch_events",
            ["dispatch_id", "sequence_number"],
            unique=True,
        )
        op.create_index(
            "idx_external_agent_dispatch_events_dispatch_created",
            "external_agent_dispatch_events",
            ["dispatch_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "external_agent_dispatch_events" in tables:
        op.drop_index(
            "idx_external_agent_dispatch_events_dispatch_created",
            table_name="external_agent_dispatch_events",
        )
        op.drop_index(
            "ux_external_agent_dispatch_events_sequence",
            table_name="external_agent_dispatch_events",
        )
        op.drop_index(
            "ix_external_agent_dispatch_events_event_type",
            table_name="external_agent_dispatch_events",
        )
        op.drop_index(
            "ix_external_agent_dispatch_events_dispatch_id",
            table_name="external_agent_dispatch_events",
        )
        op.drop_table("external_agent_dispatch_events")
