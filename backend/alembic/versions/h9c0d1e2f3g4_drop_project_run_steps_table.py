"""Drop execution-node mirror columns and the legacy project_run_steps table.

Revision ID: h9c0d1e2f3g4
Revises: g8b9c0d1e2f3
Create Date: 2026-04-09 16:15:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "h9c0d1e2f3g4"
down_revision = "g8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE execution_nodes DROP CONSTRAINT IF EXISTS execution_nodes_run_step_id_fkey")
    op.execute("DROP INDEX IF EXISTS ix_execution_nodes_run_step_id")
    op.execute("ALTER TABLE execution_nodes DROP COLUMN IF EXISTS run_step_id")
    op.execute("DROP TABLE IF EXISTS project_run_steps")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for project_run_steps removal.")
