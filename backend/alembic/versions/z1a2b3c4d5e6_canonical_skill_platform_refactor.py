"""Canonical skill platform refactor.

Revision ID: z1a2b3c4d5e6
Revises: y3z4a5b6c7d8
Create Date: 2026-04-15 00:00:00.000000
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "z1a2b3c4d5e6"
down_revision = "y3z4a5b6c7d8"
branch_labels = None
depends_on = None


def _build_search_document(row: sa.Row) -> str:
    parts = [
        str(row.skill_slug or "").strip(),
        str(row.display_name or "").strip(),
        str(row.description or "").strip(),
        str(row.skill_md_content or "").strip(),
    ]
    return "\n".join(part for part in parts if part)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.create_table(
        "skill_revisions",
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False, server_default="1.0.0"),
        sa.Column("review_state", sa.String(length=32), nullable=False, server_default="approved"),
        sa.Column("instruction_md", sa.Text(), nullable=True),
        sa.Column("tool_code", sa.Text(), nullable=True),
        sa.Column("interface_definition", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("artifact_storage_kind", sa.String(length=32), nullable=False, server_default="inline"),
        sa.Column("artifact_ref", sa.String(length=500), nullable=True),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("search_document", sa.Text(), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.user_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("revision_id"),
    )
    op.create_index(
        "idx_skill_revisions_skill_created",
        "skill_revisions",
        ["skill_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ux_skill_revisions_skill_version",
        "skill_revisions",
        ["skill_id", "version"],
        unique=True,
    )
    op.create_index("ix_skill_revisions_checksum", "skill_revisions", ["checksum"], unique=False)
    op.create_index(
        "ix_skill_revisions_review_state",
        "skill_revisions",
        ["review_state"],
        unique=False,
    )

    op.add_column("skills", sa.Column("source_kind", sa.String(length=32), nullable=True))
    op.add_column("skills", sa.Column("artifact_kind", sa.String(length=32), nullable=True))
    op.add_column("skills", sa.Column("runtime_mode", sa.String(length=32), nullable=True))
    op.add_column("skills", sa.Column("lifecycle_state", sa.String(length=32), nullable=True))
    op.add_column("skills", sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("skills", sa.Column("active_revision_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_skills_updated_by_users",
        "skills",
        "users",
        ["updated_by"],
        ["user_id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_skills_active_revision",
        "skills",
        "skill_revisions",
        ["active_revision_id"],
        ["revision_id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_skills_source_kind", "skills", ["source_kind"], unique=False)
    op.create_index("ix_skills_artifact_kind", "skills", ["artifact_kind"], unique=False)
    op.create_index("ix_skills_runtime_mode", "skills", ["runtime_mode"], unique=False)
    op.create_index("ix_skills_lifecycle_state", "skills", ["lifecycle_state"], unique=False)

    if "skill_proposals" in inspector.get_table_names():
        op.rename_table("skill_proposals", "skill_candidates")
        op.execute("ALTER INDEX IF EXISTS idx_skill_proposals_agent_review RENAME TO idx_skill_candidates_agent_review")
        op.execute("ALTER INDEX IF EXISTS idx_skill_proposals_user_created RENAME TO idx_skill_candidates_user_created")
        op.execute("ALTER INDEX IF EXISTS ux_skill_proposals_agent_key RENAME TO ux_skill_candidates_agent_key")
        op.execute("ALTER INDEX IF EXISTS ix_skill_proposals_agent_id RENAME TO ix_skill_candidates_agent_id")
        op.execute("ALTER INDEX IF EXISTS ix_skill_proposals_user_id RENAME TO ix_skill_candidates_user_id")
        op.execute("ALTER INDEX IF EXISTS ix_skill_proposals_review_status RENAME TO ix_skill_candidates_review_status")
        op.execute(
            "ALTER INDEX IF EXISTS ix_skill_proposals_evidence_session_ledger_id "
            "RENAME TO ix_skill_candidates_evidence_session_ledger_id"
        )
        op.execute(
            "ALTER INDEX IF EXISTS ix_skill_proposals_published_skill_id "
            "RENAME TO ix_skill_candidates_published_skill_id"
        )

    op.add_column("skill_candidates", sa.Column("candidate_status", sa.String(length=32), nullable=True))
    op.add_column(
        "skill_candidates",
        sa.Column("promoted_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_skill_candidates_promoted_revision",
        "skill_candidates",
        "skill_revisions",
        ["promoted_revision_id"],
        ["revision_id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "idx_skill_candidates_agent_status",
        "skill_candidates",
        ["agent_id", "candidate_status"],
        unique=False,
    )

    op.create_table(
        "agent_skill_bindings",
        sa.Column("binding_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("skill_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_pin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("binding_mode", sa.String(length=32), nullable=False, server_default="doc"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
        sa.Column(
            "auto_update_policy",
            sa.String(length=32),
            nullable=False,
            server_default="follow_active",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.agent_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.skill_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revision_pin_id"], ["skill_revisions.revision_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("binding_id"),
    )
    op.create_index(
        "idx_agent_skill_bindings_agent_enabled",
        "agent_skill_bindings",
        ["agent_id", "enabled", "priority"],
        unique=False,
    )
    op.create_index(
        "ux_agent_skill_bindings_agent_skill",
        "agent_skill_bindings",
        ["agent_id", "skill_id"],
        unique=True,
    )

    skills_table = sa.table(
        "skills",
        sa.column("skill_id", postgresql.UUID(as_uuid=True)),
        sa.column("skill_slug", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("skill_type", sa.String()),
        sa.column("storage_type", sa.String()),
        sa.column("storage_path", sa.String()),
        sa.column("code", sa.Text()),
        sa.column("config", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("manifest", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("skill_md_content", sa.Text()),
        sa.column("interface_definition", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("version", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("access_level", sa.String()),
        sa.column("created_by", postgresql.UUID(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("source_kind", sa.String()),
        sa.column("artifact_kind", sa.String()),
        sa.column("runtime_mode", sa.String()),
        sa.column("lifecycle_state", sa.String()),
        sa.column("active_revision_id", postgresql.UUID(as_uuid=True)),
    )
    skill_revisions_table = sa.table(
        "skill_revisions",
        sa.column("revision_id", postgresql.UUID(as_uuid=True)),
        sa.column("skill_id", postgresql.UUID(as_uuid=True)),
        sa.column("version", sa.String()),
        sa.column("review_state", sa.String()),
        sa.column("instruction_md", sa.Text()),
        sa.column("tool_code", sa.Text()),
        sa.column("interface_definition", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("artifact_storage_kind", sa.String()),
        sa.column("artifact_ref", sa.String()),
        sa.column("manifest", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("config", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("search_document", sa.Text()),
        sa.column("checksum", sa.String()),
        sa.column("change_note", sa.Text()),
        sa.column("created_by", postgresql.UUID(as_uuid=True)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    binding_table = sa.table(
        "agent_skill_bindings",
        sa.column("binding_id", postgresql.UUID(as_uuid=True)),
        sa.column("agent_id", postgresql.UUID(as_uuid=True)),
        sa.column("skill_id", postgresql.UUID(as_uuid=True)),
        sa.column("revision_pin_id", postgresql.UUID(as_uuid=True)),
        sa.column("binding_mode", sa.String()),
        sa.column("enabled", sa.Boolean()),
        sa.column("priority", sa.Integer()),
        sa.column("source", sa.String()),
        sa.column("auto_update_policy", sa.String()),
    )
    agents_table = sa.table(
        "agents",
        sa.column("agent_id", postgresql.UUID(as_uuid=True)),
        sa.column("capabilities", postgresql.JSONB(astext_type=sa.Text())),
    )
    candidates_table = sa.table(
        "skill_candidates",
        sa.column("id", sa.BigInteger()),
        sa.column("published_skill_id", postgresql.UUID(as_uuid=True)),
        sa.column("candidate_status", sa.String()),
        sa.column("promoted_revision_id", postgresql.UUID(as_uuid=True)),
        sa.column("review_status", sa.String()),
    )

    skill_rows = list(
        bind.execute(
            sa.select(
                skills_table.c.skill_id,
                skills_table.c.skill_slug,
                skills_table.c.display_name,
                skills_table.c.description,
                skills_table.c.skill_type,
                skills_table.c.storage_type,
                skills_table.c.storage_path,
                skills_table.c.code,
                skills_table.c.config,
                skills_table.c.manifest,
                skills_table.c.skill_md_content,
                skills_table.c.interface_definition,
                skills_table.c.version,
                skills_table.c.is_active,
                skills_table.c.access_level,
                skills_table.c.created_by,
                skills_table.c.created_at,
            )
        ).mappings()
    )
    revision_ids_by_skill = {}
    for row in skill_rows:
        runtime_mode = "doc" if row["skill_type"] == "agent_skill" else "tool"
        artifact_kind = "instruction" if row["skill_type"] == "agent_skill" else "tool"
        source_kind = "candidate" if (row["config"] or {}).get("source") == "skill_proposal" else (
            "system" if (row["access_level"] == "public" and row["created_by"] is None) else "manual"
        )
        lifecycle_state = "active" if row["is_active"] else "deprecated"
        revision_id = uuid.uuid4()
        revision_ids_by_skill[row["skill_id"]] = revision_id
        bind.execute(
            sa.insert(skill_revisions_table).values(
                revision_id=revision_id,
                skill_id=row["skill_id"],
                version=row["version"] or "1.0.0",
                review_state="approved",
                instruction_md=row["skill_md_content"],
                tool_code=row["code"],
                interface_definition=row["interface_definition"],
                artifact_storage_kind=row["storage_type"] or "inline",
                artifact_ref=row["storage_path"],
                manifest=row["manifest"],
                config=row["config"],
                search_document=_build_search_document(row),
                checksum=None,
                change_note="Initial canonical revision backfill",
                created_by=row["created_by"],
                created_at=row["created_at"],
            )
        )
        bind.execute(
            sa.update(skills_table)
            .where(skills_table.c.skill_id == row["skill_id"])
            .values(
                source_kind=source_kind,
                artifact_kind=artifact_kind,
                runtime_mode=runtime_mode,
                lifecycle_state=lifecycle_state,
                active_revision_id=revision_id,
            )
        )

    agent_rows = list(
        bind.execute(
            sa.select(agents_table.c.agent_id, agents_table.c.capabilities)
        ).mappings()
    )
    known_skill_ids = {row["skill_id"] for row in skill_rows}
    priority = 0
    for row in agent_rows:
        capabilities = row["capabilities"] if isinstance(row["capabilities"], list) else []
        for raw_skill_id in capabilities:
            try:
                skill_id = uuid.UUID(str(raw_skill_id))
            except (TypeError, ValueError):
                continue
            if skill_id not in known_skill_ids:
                continue
            skill_row = next(item for item in skill_rows if item["skill_id"] == skill_id)
            runtime_mode = "doc" if skill_row["skill_type"] == "agent_skill" else "tool"
            bind.execute(
                sa.insert(binding_table).values(
                    binding_id=uuid.uuid4(),
                    agent_id=row["agent_id"],
                    skill_id=skill_id,
                    revision_pin_id=None,
                    binding_mode=runtime_mode,
                    enabled=True,
                    priority=priority,
                    source="manual",
                    auto_update_policy="follow_active",
                )
            )
            priority += 1

    bind.execute(
        sa.text(
            """
            UPDATE skill_candidates
            SET candidate_status = CASE
                WHEN review_status = 'published' THEN 'promoted'
                WHEN review_status = 'rejected' THEN 'rejected'
                ELSE 'new'
            END
            """
        )
    )
    for row in bind.execute(
        sa.select(candidates_table.c.id, candidates_table.c.published_skill_id).where(
            candidates_table.c.published_skill_id.isnot(None)
        )
    ).mappings():
        promoted_revision_id = revision_ids_by_skill.get(row["published_skill_id"])
        if promoted_revision_id is None:
            continue
        bind.execute(
            sa.update(candidates_table)
            .where(candidates_table.c.id == row["id"])
            .values(promoted_revision_id=promoted_revision_id)
        )

    bind.execute(sa.text("UPDATE skills SET source_kind = COALESCE(source_kind, 'manual')"))
    bind.execute(sa.text("UPDATE skills SET artifact_kind = COALESCE(artifact_kind, 'tool')"))
    bind.execute(sa.text("UPDATE skills SET runtime_mode = COALESCE(runtime_mode, 'tool')"))
    bind.execute(sa.text("UPDATE skills SET lifecycle_state = COALESCE(lifecycle_state, 'active')"))
    bind.execute(
        sa.text("UPDATE skill_candidates SET candidate_status = COALESCE(candidate_status, 'new')")
    )

    op.alter_column("skills", "source_kind", nullable=False)
    op.alter_column("skills", "artifact_kind", nullable=False)
    op.alter_column("skills", "runtime_mode", nullable=False)
    op.alter_column("skills", "lifecycle_state", nullable=False)
    op.alter_column("skill_candidates", "candidate_status", nullable=False)

    bind.execute(sa.text("UPDATE user_memory_entries SET fact_kind = 'expertise' WHERE fact_kind = 'skill'"))
    bind.execute(
        sa.text(
            """
            UPDATE user_memory_entries
            SET entry_data = jsonb_set(entry_data, '{fact_kind}', '"expertise"', true)
            WHERE entry_data IS NOT NULL AND entry_data->>'fact_kind' = 'skill'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE user_memory_views
            SET view_data = jsonb_set(view_data, '{fact_kind}', '"expertise"', true)
            WHERE view_data IS NOT NULL AND view_data->>'fact_kind' = 'skill'
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE user_memory_relations
            SET relation_data = jsonb_set(relation_data, '{fact_kind}', '"expertise"', true)
            WHERE relation_data IS NOT NULL AND relation_data->>'fact_kind' = 'skill'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ux_agent_skill_bindings_agent_skill", table_name="agent_skill_bindings")
    op.drop_index("idx_agent_skill_bindings_agent_enabled", table_name="agent_skill_bindings")
    op.drop_table("agent_skill_bindings")

    op.drop_constraint("fk_skill_candidates_promoted_revision", "skill_candidates", type_="foreignkey")
    op.drop_index("idx_skill_candidates_agent_status", table_name="skill_candidates")
    op.drop_column("skill_candidates", "promoted_revision_id")
    op.drop_column("skill_candidates", "candidate_status")

    op.execute("ALTER INDEX IF EXISTS idx_skill_candidates_agent_review RENAME TO idx_skill_proposals_agent_review")
    op.execute("ALTER INDEX IF EXISTS idx_skill_candidates_user_created RENAME TO idx_skill_proposals_user_created")
    op.execute("ALTER INDEX IF EXISTS ux_skill_candidates_agent_key RENAME TO ux_skill_proposals_agent_key")
    op.execute("ALTER INDEX IF EXISTS ix_skill_candidates_agent_id RENAME TO ix_skill_proposals_agent_id")
    op.execute("ALTER INDEX IF EXISTS ix_skill_candidates_user_id RENAME TO ix_skill_proposals_user_id")
    op.execute("ALTER INDEX IF EXISTS ix_skill_candidates_review_status RENAME TO ix_skill_proposals_review_status")
    op.execute(
        "ALTER INDEX IF EXISTS ix_skill_candidates_evidence_session_ledger_id "
        "RENAME TO ix_skill_proposals_evidence_session_ledger_id"
    )
    op.execute(
        "ALTER INDEX IF EXISTS ix_skill_candidates_published_skill_id "
        "RENAME TO ix_skill_proposals_published_skill_id"
    )
    op.rename_table("skill_candidates", "skill_proposals")

    op.drop_constraint("fk_skills_active_revision", "skills", type_="foreignkey")
    op.drop_constraint("fk_skills_updated_by_users", "skills", type_="foreignkey")
    op.drop_index("ix_skills_lifecycle_state", table_name="skills")
    op.drop_index("ix_skills_runtime_mode", table_name="skills")
    op.drop_index("ix_skills_artifact_kind", table_name="skills")
    op.drop_index("ix_skills_source_kind", table_name="skills")
    op.drop_column("skills", "active_revision_id")
    op.drop_column("skills", "updated_by")
    op.drop_column("skills", "lifecycle_state")
    op.drop_column("skills", "runtime_mode")
    op.drop_column("skills", "artifact_kind")
    op.drop_column("skills", "source_kind")

    op.drop_index("ix_skill_revisions_review_state", table_name="skill_revisions")
    op.drop_index("ix_skill_revisions_checksum", table_name="skill_revisions")
    op.drop_index("ux_skill_revisions_skill_version", table_name="skill_revisions")
    op.drop_index("idx_skill_revisions_skill_created", table_name="skill_revisions")
    op.drop_table("skill_revisions")
