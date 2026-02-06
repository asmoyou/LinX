"""Migrate department data from User.attributes to Department FK

Revision ID: b9g2h3i4j5k6
Revises: a8f1b2c3d4e5
Create Date: 2026-02-06 10:01:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b9g2h3i4j5k6"
down_revision: Union[str, Sequence[str], None] = "a8f1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Migrate department strings from User.attributes to Department FK."""
    conn = op.get_bind()

    # 1. Find all unique department values in User.attributes
    result = conn.execute(
        sa.text(
            "SELECT DISTINCT attributes->>'department' AS dept "
            "FROM users "
            "WHERE attributes->>'department' IS NOT NULL "
            "AND attributes->>'department' != ''"
        )
    )
    departments = [row.dept for row in result if row.dept]

    if not departments:
        return

    # 2. Create Department records for each unique value
    for dept_name in departments:
        dept_id = str(uuid.uuid4())
        code = dept_name.lower().replace(" ", "_").replace("-", "_")

        # Ensure code uniqueness by checking if it already exists
        existing = conn.execute(
            sa.text("SELECT department_id FROM departments WHERE code = :code"),
            {"code": code},
        ).fetchone()

        if existing:
            dept_id = str(existing.department_id)
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO departments (department_id, name, code, status) "
                    "VALUES (:id, :name, :code, 'active')"
                ),
                {"id": dept_id, "name": dept_name, "code": code},
            )

        # 3. Update User.department_id for users with this department
        conn.execute(
            sa.text(
                "UPDATE users SET department_id = :dept_id "
                "WHERE attributes->>'department' = :dept_name"
            ),
            {"dept_id": dept_id, "dept_name": dept_name},
        )


def downgrade() -> None:
    """Reverse: copy department FK back to attributes (best effort)."""
    conn = op.get_bind()

    # Update attributes.department from the FK relationship
    conn.execute(
        sa.text(
            "UPDATE users SET attributes = "
            "COALESCE(attributes, '{}'::jsonb) || "
            "jsonb_build_object('department', d.name) "
            "FROM departments d "
            "WHERE users.department_id = d.department_id"
        )
    )
