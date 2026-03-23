"""Add mcp_servers table and mcp_server_id FK on skills.

MCP (Model Context Protocol) server integration: stores connection
configurations for external MCP servers whose tools are synced into
the skill library as mcp_tool skills.

Revision ID: m1c2p3s4e5r6
Revises: 6d450e8eab02
Create Date: 2026-03-23 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision = "m1c2p3s4e5r6"
down_revision = "6d450e8eab02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("server_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("transport_type", sa.String(32), nullable=False),
        sa.Column("command", sa.String(500), nullable=True),
        sa.Column("args", JSONB, nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("headers", JSONB, nullable=True),
        sa.Column("env_vars", JSONB, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="disconnected"),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tool_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("idx_mcp_server_name", "mcp_servers", ["name"])
    op.create_index("idx_mcp_server_status", "mcp_servers", ["status"])
    op.create_index("idx_mcp_server_active", "mcp_servers", ["is_active"])
    op.create_index("idx_mcp_server_created_by", "mcp_servers", ["created_by"])

    op.add_column(
        "skills",
        sa.Column(
            "mcp_server_id",
            UUID(as_uuid=True),
            sa.ForeignKey("mcp_servers.server_id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index("idx_skills_mcp_server", "skills", ["mcp_server_id"])


def downgrade() -> None:
    op.drop_index("idx_skills_mcp_server", table_name="skills")
    op.drop_column("skills", "mcp_server_id")
    op.drop_index("idx_mcp_server_created_by", table_name="mcp_servers")
    op.drop_index("idx_mcp_server_active", table_name="mcp_servers")
    op.drop_index("idx_mcp_server_status", table_name="mcp_servers")
    op.drop_index("idx_mcp_server_name", table_name="mcp_servers")
    op.drop_table("mcp_servers")
