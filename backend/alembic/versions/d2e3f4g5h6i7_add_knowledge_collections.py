"""Add knowledge_collections table and collection_id FK to knowledge_items

Revision ID: d2e3f4g5h6i7
Revises: c1d2e3f4g5h6
Create Date: 2026-02-09 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2e3f4g5h6i7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create knowledge_collections table and add collection_id to knowledge_items."""
    # Create knowledge_collections table
    op.create_table(
        "knowledge_collections",
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(500), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "owner_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.user_id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "access_level", sa.String(50), nullable=False, server_default="private", index=True
        ),
        sa.Column(
            "department_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("departments.department_id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Create composite index
    op.create_index(
        "idx_collection_owner_access",
        "knowledge_collections",
        ["owner_user_id", "access_level"],
    )

    # Add collection_id FK to knowledge_items
    op.add_column(
        "knowledge_items",
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_collections.collection_id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_knowledge_items_collection_id",
        "knowledge_items",
        ["collection_id"],
    )


def downgrade() -> None:
    """Drop collection_id from knowledge_items and drop knowledge_collections table."""
    op.drop_index("ix_knowledge_items_collection_id", table_name="knowledge_items")
    op.drop_column("knowledge_items", "collection_id")
    op.drop_index("idx_collection_owner_access", table_name="knowledge_collections")
    op.drop_table("knowledge_collections")
