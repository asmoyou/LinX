"""Add execution-node foreign keys to delivery and dispatch records.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-04-09 13:40:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("project_task_handoffs", sa.Column("node_id", _UUID, nullable=True))
    op.create_foreign_key(
        "fk_project_task_handoffs_node_id",
        "project_task_handoffs",
        "execution_nodes",
        ["node_id"],
        ["node_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_project_task_handoffs_node_id",
        "project_task_handoffs",
        ["node_id"],
        unique=False,
    )

    op.add_column("project_task_change_bundles", sa.Column("node_id", _UUID, nullable=True))
    op.create_foreign_key(
        "fk_project_task_change_bundles_node_id",
        "project_task_change_bundles",
        "execution_nodes",
        ["node_id"],
        ["node_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_project_task_change_bundles_node_id",
        "project_task_change_bundles",
        ["node_id"],
        unique=False,
    )

    op.add_column("project_task_evidence_bundles", sa.Column("node_id", _UUID, nullable=True))
    op.create_foreign_key(
        "fk_project_task_evidence_bundles_node_id",
        "project_task_evidence_bundles",
        "execution_nodes",
        ["node_id"],
        ["node_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_project_task_evidence_bundles_node_id",
        "project_task_evidence_bundles",
        ["node_id"],
        unique=False,
    )

    op.add_column("external_agent_dispatches", sa.Column("node_id", _UUID, nullable=True))
    op.create_foreign_key(
        "fk_external_agent_dispatches_node_id",
        "external_agent_dispatches",
        "execution_nodes",
        ["node_id"],
        ["node_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_external_agent_dispatches_node_id",
        "external_agent_dispatches",
        ["node_id"],
        unique=False,
    )

    op.execute(
        """
        UPDATE project_task_handoffs handoff
        SET node_id = node.node_id
        FROM execution_nodes node
        WHERE handoff.run_step_id IS NOT NULL
          AND node.run_step_id = handoff.run_step_id
          AND handoff.node_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE project_task_change_bundles bundle
        SET node_id = node.node_id
        FROM execution_nodes node
        WHERE bundle.run_step_id IS NOT NULL
          AND node.run_step_id = bundle.run_step_id
          AND bundle.node_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE project_task_evidence_bundles evidence
        SET node_id = node.node_id
        FROM execution_nodes node
        WHERE evidence.run_step_id IS NOT NULL
          AND node.run_step_id = evidence.run_step_id
          AND evidence.node_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE external_agent_dispatches dispatch
        SET node_id = node.node_id
        FROM execution_nodes node
        WHERE dispatch.run_step_id IS NOT NULL
          AND node.run_step_id = dispatch.run_step_id
          AND dispatch.node_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_external_agent_dispatches_node_id", table_name="external_agent_dispatches")
    op.drop_constraint(
        "fk_external_agent_dispatches_node_id",
        "external_agent_dispatches",
        type_="foreignkey",
    )
    op.drop_column("external_agent_dispatches", "node_id")

    op.drop_index("ix_project_task_evidence_bundles_node_id", table_name="project_task_evidence_bundles")
    op.drop_constraint(
        "fk_project_task_evidence_bundles_node_id",
        "project_task_evidence_bundles",
        type_="foreignkey",
    )
    op.drop_column("project_task_evidence_bundles", "node_id")

    op.drop_index("ix_project_task_change_bundles_node_id", table_name="project_task_change_bundles")
    op.drop_constraint(
        "fk_project_task_change_bundles_node_id",
        "project_task_change_bundles",
        type_="foreignkey",
    )
    op.drop_column("project_task_change_bundles", "node_id")

    op.drop_index("ix_project_task_handoffs_node_id", table_name="project_task_handoffs")
    op.drop_constraint(
        "fk_project_task_handoffs_node_id",
        "project_task_handoffs",
        type_="foreignkey",
    )
    op.drop_column("project_task_handoffs", "node_id")
