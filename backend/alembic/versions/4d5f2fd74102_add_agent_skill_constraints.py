"""add_agent_skill_constraints

Revision ID: 4d5f2fd74102
Revises: b727ddf0f77c
Create Date: 2026-01-29 13:03:40.272339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d5f2fd74102'
down_revision: Union[str, Sequence[str], None] = 'b727ddf0f77c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add constraint: agent_skill must have skill_md_content
    op.create_check_constraint(
        'agent_skill_has_md',
        'skills',
        "skill_type != 'agent_skill' OR skill_md_content IS NOT NULL"
    )
    
    # Add constraint: agent_skill must use minio storage
    op.create_check_constraint(
        'agent_skill_uses_minio',
        'skills',
        "skill_type != 'agent_skill' OR storage_type = 'minio'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop constraints
    op.drop_constraint('agent_skill_uses_minio', 'skills', type_='check')
    op.drop_constraint('agent_skill_has_md', 'skills', type_='check')
