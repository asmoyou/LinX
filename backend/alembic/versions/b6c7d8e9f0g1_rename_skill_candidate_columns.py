"""Rename legacy skill-candidate columns to canonical names.

Revision ID: b6c7d8e9f0g1
Revises: a4b5c6d7e8f9
Create Date: 2026-04-16 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b6c7d8e9f0g1"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("skill_candidates")}

    if "proposal_key" in columns and "cluster_key" not in columns:
        op.alter_column(
            "skill_candidates",
            "proposal_key",
            new_column_name="cluster_key",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )
    if "proposal_data" in columns and "candidate_data" not in columns:
        op.alter_column(
            "skill_candidates",
            "proposal_data",
            new_column_name="candidate_data",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            existing_nullable=True,
        )
    if "published_skill_id" in columns and "promoted_skill_id" not in columns:
        op.alter_column(
            "skill_candidates",
            "published_skill_id",
            new_column_name="promoted_skill_id",
            existing_type=postgresql.UUID(as_uuid=True),
            existing_nullable=True,
        )

    indexes = {index["name"] for index in inspector.get_indexes("skill_candidates")}
    if (
        "ix_skill_candidates_published_skill_id" in indexes
        and "ix_skill_candidates_promoted_skill_id" not in indexes
    ):
        op.execute(
            "ALTER INDEX IF EXISTS ix_skill_candidates_published_skill_id "
            "RENAME TO ix_skill_candidates_promoted_skill_id"
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("skill_candidates")}

    if "promoted_skill_id" in columns and "published_skill_id" not in columns:
        op.alter_column(
            "skill_candidates",
            "promoted_skill_id",
            new_column_name="published_skill_id",
            existing_type=postgresql.UUID(as_uuid=True),
            existing_nullable=True,
        )
    if "candidate_data" in columns and "proposal_data" not in columns:
        op.alter_column(
            "skill_candidates",
            "candidate_data",
            new_column_name="proposal_data",
            existing_type=postgresql.JSONB(astext_type=sa.Text()),
            existing_nullable=True,
        )
    if "cluster_key" in columns and "proposal_key" not in columns:
        op.alter_column(
            "skill_candidates",
            "cluster_key",
            new_column_name="proposal_key",
            existing_type=sa.String(length=255),
            existing_nullable=False,
        )

    indexes = {index["name"] for index in inspector.get_indexes("skill_candidates")}
    if (
        "ix_skill_candidates_promoted_skill_id" in indexes
        and "ix_skill_candidates_published_skill_id" not in indexes
    ):
        op.execute(
            "ALTER INDEX IF EXISTS ix_skill_candidates_promoted_skill_id "
            "RENAME TO ix_skill_candidates_published_skill_id"
        )
