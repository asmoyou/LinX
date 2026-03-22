"""Drop agent_skill_uses_minio CHECK constraint.

Candidate-promoted playbooks use inline instruction_md, not MinIO artifacts.
The constraint forced a mismatch where storage_type claimed 'minio' but
artifact_ref was NULL.  Removing it lets agent_skill rows use any valid
storage_type.

Revision ID: 6d450e8eab02
Revises: z4y5x6w7v8u9
Create Date: 2026-03-22 00:00:00.000000
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "6d450e8eab02"
down_revision = "z4y5x6w7v8u9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("agent_skill_uses_minio", "skills", type_="check")


def downgrade() -> None:
    op.create_check_constraint(
        "agent_skill_uses_minio",
        "skills",
        "skill_type != 'agent_skill' OR storage_type = 'minio'",
    )
