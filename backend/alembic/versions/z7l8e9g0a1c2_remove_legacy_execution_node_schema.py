"""remove legacy execution-node schema

Revision ID: z7l8e9g0a1c2
Revises: x3t4r5n6a7l8
Create Date: 2026-04-07 12:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "z7l8e9g0a1c2"
down_revision: Union[str, Sequence[str], None] = "x3t4r5n6a7l8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "project_run_steps" in tables:
        columns = {column["name"] for column in inspector.get_columns("project_run_steps")}
        if "node_id" in columns:
            op.execute("ALTER TABLE project_run_steps DROP COLUMN IF EXISTS node_id CASCADE")

    op.execute("DROP TABLE IF EXISTS external_agent_sessions CASCADE")
    op.execute("DROP TABLE IF EXISTS agent_runtime_bindings CASCADE")
    op.execute("DROP TABLE IF EXISTS execution_leases CASCADE")
    op.execute("DROP TABLE IF EXISTS execution_nodes CASCADE")


def downgrade() -> None:
    raise NotImplementedError(
        "Legacy execution-node cleanup is irreversible; restore from backup if needed."
    )
