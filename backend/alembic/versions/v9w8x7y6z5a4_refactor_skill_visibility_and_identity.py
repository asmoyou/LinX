"""Refactor skill visibility and identity.

Revision ID: v9w8x7y6z5a4
Revises: u1v2w3x4y5z6
Create Date: 2026-02-08 00:00:00.000000
"""

from __future__ import annotations

from typing import Iterable

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "v9w8x7y6z5a4"
down_revision = "u1v2w3x4y5z6"
branch_labels = None
depends_on = None


DEFAULT_PUBLIC_SKILL_SLUGS = (
    "data_processing",
    "sql_query",
    "web_scraping",
    "statistical_analysis",
    "visualization",
    "text_summarization",
    "sentiment_analysis",
    "file_operations",
    "api_request",
    "json_processing",
)


def _drop_index_if_exists(index_name: str, table_name: str) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {index["name"] for index in inspector.get_indexes(table_name)}
    if index_name in indexes:
        op.drop_index(index_name, table_name=table_name)


def _drop_unique_constraints_for_columns(table_name: str, columns: Iterable[str]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    target = list(columns)
    for constraint in inspector.get_unique_constraints(table_name):
        if list(constraint.get("column_names") or []) == target:
            op.drop_constraint(constraint["name"], table_name=table_name, type_="unique")


def upgrade() -> None:
    _drop_index_if_exists("idx_skills_system", "skills")
    _drop_index_if_exists("ix_skills_name", "skills")
    _drop_unique_constraints_for_columns("skills", ["name"])

    op.alter_column("skills", "name", new_column_name="skill_slug")
    op.add_column("skills", sa.Column("display_name", sa.String(length=255), nullable=True))
    op.add_column(
        "skills",
        sa.Column("access_level", sa.String(length=50), nullable=False, server_default="private"),
    )
    op.add_column("skills", sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_skills_department_id_departments",
        "skills",
        "departments",
        ["department_id"],
        ["department_id"],
        ondelete="SET NULL",
    )

    skills_table = sa.table(
        "skills",
        sa.column("skill_slug", sa.String(length=255)),
        sa.column("display_name", sa.String(length=255)),
        sa.column("access_level", sa.String(length=50)),
        sa.column("is_system", sa.Boolean()),
    )

    public_predicate = sa.or_(
        skills_table.c.skill_slug.in_(DEFAULT_PUBLIC_SKILL_SLUGS),
        skills_table.c.is_system.is_(True),
    )
    op.execute(skills_table.update().values(display_name=skills_table.c.skill_slug))
    op.execute(skills_table.update().where(public_predicate).values(access_level="public"))
    op.execute(skills_table.update().where(sa.not_(public_predicate)).values(access_level="private"))

    op.alter_column("skills", "display_name", nullable=False)
    op.drop_column("skills", "is_system")

    op.create_index("ux_skills_skill_slug", "skills", ["skill_slug"], unique=True)
    op.create_index("idx_skills_access_level", "skills", ["access_level"], unique=False)
    op.create_index(
        "idx_skills_department_access",
        "skills",
        ["department_id", "access_level"],
        unique=False,
    )
    op.create_index(
        "idx_skills_created_by_access",
        "skills",
        ["created_by", "access_level"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_skills_created_by_access", table_name="skills")
    op.drop_index("idx_skills_department_access", table_name="skills")
    op.drop_index("idx_skills_access_level", table_name="skills")
    op.drop_index("ux_skills_skill_slug", table_name="skills")
    op.drop_constraint("fk_skills_department_id_departments", "skills", type_="foreignkey")
    op.add_column(
        "skills",
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.drop_column("skills", "department_id")
    op.drop_column("skills", "access_level")
    op.drop_column("skills", "display_name")
    op.alter_column("skills", "skill_slug", new_column_name="name")
    op.create_index("idx_skills_system", "skills", ["is_system"], unique=False)
