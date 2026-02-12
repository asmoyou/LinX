"""add_memory_records_table

Revision ID: e4f8a1b2c3d4
Revises: d2e3f4g5h6i7
Create Date: 2026-02-12 20:40:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4f8a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d2e3f4g5h6i7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "memory_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("milvus_id", sa.BigInteger(), nullable=True),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=True),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("memory_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("vector_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("vector_error", sa.Text(), nullable=True),
        sa.Column("vector_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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

    op.create_index("ix_memory_records_milvus_id", "memory_records", ["milvus_id"], unique=True)
    op.create_index(
        "ix_memory_records_memory_type", "memory_records", ["memory_type"], unique=False
    )
    op.create_index("ix_memory_records_user_id", "memory_records", ["user_id"], unique=False)
    op.create_index("ix_memory_records_agent_id", "memory_records", ["agent_id"], unique=False)
    op.create_index("ix_memory_records_task_id", "memory_records", ["task_id"], unique=False)
    op.create_index("ix_memory_records_timestamp", "memory_records", ["timestamp"], unique=False)
    op.create_index(
        "ix_memory_records_vector_status", "memory_records", ["vector_status"], unique=False
    )
    op.create_index("ix_memory_records_is_deleted", "memory_records", ["is_deleted"], unique=False)
    op.create_index(
        "idx_memory_type_user", "memory_records", ["memory_type", "user_id"], unique=False
    )
    op.create_index(
        "idx_memory_type_agent", "memory_records", ["memory_type", "agent_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_memory_type_agent", table_name="memory_records")
    op.drop_index("idx_memory_type_user", table_name="memory_records")
    op.drop_index("ix_memory_records_is_deleted", table_name="memory_records")
    op.drop_index("ix_memory_records_vector_status", table_name="memory_records")
    op.drop_index("ix_memory_records_timestamp", table_name="memory_records")
    op.drop_index("ix_memory_records_task_id", table_name="memory_records")
    op.drop_index("ix_memory_records_agent_id", table_name="memory_records")
    op.drop_index("ix_memory_records_user_id", table_name="memory_records")
    op.drop_index("ix_memory_records_memory_type", table_name="memory_records")
    op.drop_index("ix_memory_records_milvus_id", table_name="memory_records")
    op.drop_table("memory_records")
