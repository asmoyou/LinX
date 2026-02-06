"""Add departments table and department_id to users, agents, knowledge_items

Revision ID: a8f1b2c3d4e5
Revises: cefea2414350
Create Date: 2026-02-06 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a8f1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "cefea2414350"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create departments table and add department_id FK to related tables."""
    # Create departments table
    op.create_table(
        "departments",
        sa.Column("department_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("manager_id", sa.UUID(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="active",
        ),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
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
            ["parent_id"],
            ["departments.department_id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["manager_id"],
            ["users.user_id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("department_id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        op.f("ix_departments_name"), "departments", ["name"], unique=False
    )
    op.create_index(
        op.f("ix_departments_code"), "departments", ["code"], unique=True
    )
    op.create_index(
        op.f("ix_departments_parent_id"), "departments", ["parent_id"], unique=False
    )
    op.create_index(
        op.f("ix_departments_manager_id"), "departments", ["manager_id"], unique=False
    )
    op.create_index(
        op.f("ix_departments_status"), "departments", ["status"], unique=False
    )
    op.create_index(
        "idx_department_parent_status",
        "departments",
        ["parent_id", "status"],
        unique=False,
    )

    # Add department_id to users
    op.add_column(
        "users", sa.Column("department_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_users_department_id",
        "users",
        "departments",
        ["department_id"],
        ["department_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_users_department_id"), "users", ["department_id"], unique=False
    )

    # Add department_id to agents
    op.add_column(
        "agents", sa.Column("department_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_agents_department_id",
        "agents",
        "departments",
        ["department_id"],
        ["department_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_agents_department_id"), "agents", ["department_id"], unique=False
    )

    # Add department_id to knowledge_items
    op.add_column(
        "knowledge_items", sa.Column("department_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_knowledge_items_department_id",
        "knowledge_items",
        "departments",
        ["department_id"],
        ["department_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_knowledge_items_department_id"),
        "knowledge_items",
        ["department_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove department_id from related tables and drop departments table."""
    # Remove FK and column from knowledge_items
    op.drop_index(
        op.f("ix_knowledge_items_department_id"), table_name="knowledge_items"
    )
    op.drop_constraint(
        "fk_knowledge_items_department_id", "knowledge_items", type_="foreignkey"
    )
    op.drop_column("knowledge_items", "department_id")

    # Remove FK and column from agents
    op.drop_index(op.f("ix_agents_department_id"), table_name="agents")
    op.drop_constraint("fk_agents_department_id", "agents", type_="foreignkey")
    op.drop_column("agents", "department_id")

    # Remove FK and column from users
    op.drop_index(op.f("ix_users_department_id"), table_name="users")
    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    op.drop_column("users", "department_id")

    # Drop departments table
    op.drop_index("idx_department_parent_status", table_name="departments")
    op.drop_index(op.f("ix_departments_status"), table_name="departments")
    op.drop_index(op.f("ix_departments_manager_id"), table_name="departments")
    op.drop_index(op.f("ix_departments_parent_id"), table_name="departments")
    op.drop_index(op.f("ix_departments_code"), table_name="departments")
    op.drop_index(op.f("ix_departments_name"), table_name="departments")
    op.drop_table("departments")
