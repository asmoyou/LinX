"""add_memory_acl_and_scope_columns

Revision ID: 91c4e2b8a5d1
Revises: f7a1c9d8e6b0
Create Date: 2026-02-14 10:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91c4e2b8a5d1"
down_revision: Union[str, Sequence[str], None] = "f7a1c9d8e6b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("memory_records", sa.Column("owner_user_id", sa.String(length=255), nullable=True))
    op.add_column("memory_records", sa.Column("owner_agent_id", sa.String(length=255), nullable=True))
    op.add_column("memory_records", sa.Column("department_id", sa.String(length=255), nullable=True))
    op.add_column(
        "memory_records",
        sa.Column("visibility", sa.String(length=50), nullable=False, server_default="account"),
    )
    op.add_column(
        "memory_records",
        sa.Column("sensitivity", sa.String(length=50), nullable=False, server_default="internal"),
    )
    op.add_column("memory_records", sa.Column("source_memory_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "memory_records", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.create_foreign_key(
        "fk_memory_records_source_memory_id",
        "memory_records",
        "memory_records",
        ["source_memory_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_index("idx_memory_owner_user", "memory_records", ["owner_user_id"], unique=False)
    op.create_index("idx_memory_owner_agent", "memory_records", ["owner_agent_id"], unique=False)
    op.create_index("idx_memory_department_id", "memory_records", ["department_id"], unique=False)
    op.create_index("idx_memory_visibility", "memory_records", ["visibility"], unique=False)
    op.create_index("idx_memory_sensitivity", "memory_records", ["sensitivity"], unique=False)
    op.create_index("idx_memory_source_memory", "memory_records", ["source_memory_id"], unique=False)
    op.create_index("idx_memory_expires_at", "memory_records", ["expires_at"], unique=False)
    op.create_index(
        "idx_memory_visibility_scope",
        "memory_records",
        ["visibility", "department_id"],
        unique=False,
    )

    op.alter_column("memory_records", "visibility", server_default=None)
    op.alter_column("memory_records", "sensitivity", server_default=None)

    op.create_table(
        "memory_acl",
        sa.Column("acl_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("memory_id", sa.BigInteger(), nullable=False),
        sa.Column("effect", sa.String(length=20), nullable=False),
        sa.Column("principal_type", sa.String(length=50), nullable=False),
        sa.Column("principal_id", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("acl_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memory_records.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("acl_id"),
    )

    op.create_index("idx_memory_acl_memory_id", "memory_acl", ["memory_id"], unique=False)
    op.create_index("idx_memory_acl_effect", "memory_acl", ["effect"], unique=False)
    op.create_index(
        "idx_memory_acl_principal", "memory_acl", ["principal_type", "principal_id"], unique=False
    )
    op.create_index("idx_memory_acl_expires_at", "memory_acl", ["expires_at"], unique=False)
    op.create_index(
        "idx_memory_acl_memory_effect", "memory_acl", ["memory_id", "effect"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_memory_acl_memory_effect", table_name="memory_acl")
    op.drop_index("idx_memory_acl_expires_at", table_name="memory_acl")
    op.drop_index("idx_memory_acl_principal", table_name="memory_acl")
    op.drop_index("idx_memory_acl_effect", table_name="memory_acl")
    op.drop_index("idx_memory_acl_memory_id", table_name="memory_acl")
    op.drop_table("memory_acl")

    op.drop_index("idx_memory_visibility_scope", table_name="memory_records")
    op.drop_index("idx_memory_expires_at", table_name="memory_records")
    op.drop_index("idx_memory_source_memory", table_name="memory_records")
    op.drop_index("idx_memory_sensitivity", table_name="memory_records")
    op.drop_index("idx_memory_visibility", table_name="memory_records")
    op.drop_index("idx_memory_department_id", table_name="memory_records")
    op.drop_index("idx_memory_owner_agent", table_name="memory_records")
    op.drop_index("idx_memory_owner_user", table_name="memory_records")

    op.drop_constraint("fk_memory_records_source_memory_id", "memory_records", type_="foreignkey")
    op.drop_column("memory_records", "expires_at")
    op.drop_column("memory_records", "source_memory_id")
    op.drop_column("memory_records", "sensitivity")
    op.drop_column("memory_records", "visibility")
    op.drop_column("memory_records", "department_id")
    op.drop_column("memory_records", "owner_agent_id")
    op.drop_column("memory_records", "owner_user_id")
