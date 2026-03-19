"""Remove deprecated allowed_memory field from agents.

Revision ID: a4b5c6d7e8f9
Revises: z1a2b3c4d5e6
Create Date: 2026-04-15 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a4b5c6d7e8f9"
down_revision = "z1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("agents")}
    if "allowed_memory" in columns:
        op.drop_column("agents", "allowed_memory")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("agents")}
    if "allowed_memory" not in columns:
        op.add_column(
            "agents",
            sa.Column(
                "allowed_memory",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            ),
        )
