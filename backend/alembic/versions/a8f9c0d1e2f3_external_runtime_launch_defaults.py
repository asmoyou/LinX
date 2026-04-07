"""normalize external runtime launch command defaults

Revision ID: a8f9c0d1e2f3
Revises: z7l8e9g0a1c2
Create Date: 2026-04-07 14:20:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "a8f9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "z7l8e9g0a1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "platform_settings" in tables:
        op.execute(
            """
            UPDATE platform_settings
            SET setting_value = jsonb_build_object(
                'default_launch_command_template',
                COALESCE(
                    NULLIF(setting_value ->> 'default_launch_command_template', ''),
                    setting_value ->> 'external_agent_command_template',
                    ''
                )
            )
            WHERE setting_key = 'project_execution'
            """
        )

    if "projects" in tables:
        project_columns = {column["name"] for column in inspector.get_columns("projects")}
        if "configuration" in project_columns:
            op.execute(
                """
                UPDATE projects
                SET configuration = COALESCE(configuration, '{}'::jsonb) - 'external_agent_command_template'
                WHERE COALESCE(configuration, '{}'::jsonb) ? 'external_agent_command_template'
                """
            )

    if "agent_provisioning_profiles" in tables:
        profile_columns = {
            column["name"] for column in inspector.get_columns("agent_provisioning_profiles")
        }
        if "preferred_node_selector" in profile_columns:
            op.drop_column("agent_provisioning_profiles", "preferred_node_selector")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "agent_provisioning_profiles" in tables:
        profile_columns = {
            column["name"] for column in inspector.get_columns("agent_provisioning_profiles")
        }
        if "preferred_node_selector" not in profile_columns:
            op.add_column(
                "agent_provisioning_profiles",
                sa.Column("preferred_node_selector", sa.String(length=255), nullable=True),
            )

    if "platform_settings" in tables:
        op.execute(
            """
            UPDATE platform_settings
            SET setting_value = jsonb_build_object(
                'external_agent_command_template',
                COALESCE(setting_value ->> 'default_launch_command_template', '')
            )
            WHERE setting_key = 'project_execution'
            """
        )
