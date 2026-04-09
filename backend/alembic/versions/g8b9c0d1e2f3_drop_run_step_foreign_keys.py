"""Drop run-step foreign keys from node-migrated execution records.

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-04-09 15:10:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "g8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "project_task_handoffs_run_step_id_fkey",
        "project_task_handoffs",
        type_="foreignkey",
    )
    op.drop_column("project_task_handoffs", "run_step_id")

    op.drop_constraint(
        "project_task_change_bundles_run_step_id_fkey",
        "project_task_change_bundles",
        type_="foreignkey",
    )
    op.drop_column("project_task_change_bundles", "run_step_id")

    op.drop_constraint(
        "project_task_evidence_bundles_run_step_id_fkey",
        "project_task_evidence_bundles",
        type_="foreignkey",
    )
    op.drop_column("project_task_evidence_bundles", "run_step_id")

    op.drop_constraint(
        "external_agent_dispatches_run_step_id_fkey",
        "external_agent_dispatches",
        type_="foreignkey",
    )
    op.drop_column("external_agent_dispatches", "run_step_id")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for run-step foreign-key removal.")
