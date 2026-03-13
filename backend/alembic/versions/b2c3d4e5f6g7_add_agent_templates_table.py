"""add agent_templates table

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-21 10:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "b2c3d4e5f6g7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    """Create agent_templates table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "agent_templates" in inspector.get_table_names():
        return

    op.create_table(
        "agent_templates",
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("agent_type", sa.String(length=100), nullable=False),
        sa.Column("capabilities", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("tools", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("use_case", sa.String(length=500), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "is_system_template", sa.String(length=10), nullable=False, server_default="true"
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("template_id"),
        sa.UniqueConstraint("name"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="SET NULL"),
    )

    # Create indexes for common queries
    op.create_index("ix_agent_templates_agent_type", "agent_templates", ["agent_type"])
    op.create_index(
        "ix_agent_templates_is_system_template", "agent_templates", ["is_system_template"]
    )


def downgrade():
    """Drop agent_templates table."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "agent_templates" not in inspector.get_table_names():
        return

    op.drop_index("ix_agent_templates_is_system_template", table_name="agent_templates")
    op.drop_index("ix_agent_templates_agent_type", table_name="agent_templates")
    op.drop_table("agent_templates")
