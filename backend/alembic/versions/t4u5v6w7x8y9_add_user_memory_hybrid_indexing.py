"""Add user-memory hybrid retrieval indexing schema.

Revision ID: t4u5v6w7x8y9
Revises: s8u9v0w1x2y3
Create Date: 2026-03-21 10:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "t4u5v6w7x8y9"
down_revision: Union[str, Sequence[str], None] = "s8u9v0w1x2y3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.add_column(
        "user_memory_entries",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )
    op.add_column(
        "user_memory_entries",
        sa.Column("event_time_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_memory_entries",
        sa.Column("event_time_end", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_memory_entries",
        sa.Column(
            "vector_sync_state",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "user_memory_entries",
        sa.Column("vector_document_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_memory_entries",
        sa.Column("vector_collection_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "user_memory_entries",
        sa.Column("vector_indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_memory_entries",
        sa.Column("vector_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_user_memory_entries_search_vector",
        "user_memory_entries",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_user_memory_entries_canonical_text_trgm",
        "user_memory_entries",
        ["canonical_text"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"canonical_text": "gin_trgm_ops"},
    )
    op.create_index(
        "idx_user_memory_entries_vector_sync",
        "user_memory_entries",
        ["user_id", "status", "vector_sync_state", "vector_indexed_at"],
        unique=False,
    )
    op.create_index(
        "idx_user_memory_entries_vector_collection",
        "user_memory_entries",
        ["vector_collection_name", "vector_sync_state"],
        unique=False,
    )

    op.add_column(
        "user_memory_views",
        sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True),
    )
    op.add_column(
        "user_memory_views",
        sa.Column(
            "vector_sync_state",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "user_memory_views",
        sa.Column("vector_document_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "user_memory_views",
        sa.Column("vector_collection_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "user_memory_views",
        sa.Column("vector_indexed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_memory_views",
        sa.Column("vector_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_user_memory_views_search_vector",
        "user_memory_views",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "idx_user_memory_views_content_trgm",
        "user_memory_views",
        ["content"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"content": "gin_trgm_ops"},
    )
    op.create_index(
        "idx_user_memory_views_vector_sync",
        "user_memory_views",
        ["user_id", "view_type", "status", "vector_sync_state", "vector_indexed_at"],
        unique=False,
    )
    op.create_index(
        "idx_user_memory_views_vector_collection",
        "user_memory_views",
        ["vector_collection_name", "vector_sync_state"],
        unique=False,
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION user_memory_entries_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.entry_key, '')), 'A') ||
                setweight(
                    to_tsvector('pg_catalog.simple', COALESCE(NEW.canonical_text, '')),
                    'A'
                ) ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.summary, '')), 'B') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.predicate, '')), 'B') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.object_text, '')), 'B') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.event_time, '')), 'C') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.location, '')), 'C') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.topic, '')), 'C') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.persons::text, '')), 'D') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.entities::text, '')), 'D') ||
                setweight(
                    to_tsvector('pg_catalog.simple', COALESCE(NEW.entry_data::text, '')),
                    'D'
                );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER user_memory_entries_search_vector_trigger
        BEFORE INSERT OR UPDATE ON user_memory_entries
        FOR EACH ROW EXECUTE FUNCTION user_memory_entries_search_vector_update();
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION user_memory_views_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.view_key, '')), 'A') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.title, '')), 'A') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.content, '')), 'A') ||
                setweight(
                    to_tsvector('pg_catalog.simple', COALESCE(NEW.view_data::text, '')),
                    'C'
                );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER user_memory_views_search_vector_trigger
        BEFORE INSERT OR UPDATE ON user_memory_views
        FOR EACH ROW EXECUTE FUNCTION user_memory_views_search_vector_update();
        """
    )

    op.execute("UPDATE user_memory_entries SET canonical_text = canonical_text")
    op.execute("UPDATE user_memory_views SET content = content")

    op.create_table(
        "user_memory_embedding_jobs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("job_key", sa.String(length=255), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=True),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("collection_name", sa.String(length=255), nullable=False),
        sa.Column("embedding_signature", sa.String(length=255), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_key", name="ux_user_memory_embedding_jobs_job_key"),
    )
    op.create_index(
        "idx_user_memory_embedding_jobs_claim",
        "user_memory_embedding_jobs",
        ["status", "available_at", "id"],
        unique=False,
    )
    op.create_index(
        "idx_user_memory_embedding_jobs_user_status",
        "user_memory_embedding_jobs",
        ["user_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_user_memory_embedding_jobs_source_status",
        "user_memory_embedding_jobs",
        ["source_kind", "source_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_user_memory_embedding_jobs_source_status", table_name="user_memory_embedding_jobs")
    op.drop_index("idx_user_memory_embedding_jobs_user_status", table_name="user_memory_embedding_jobs")
    op.drop_index("idx_user_memory_embedding_jobs_claim", table_name="user_memory_embedding_jobs")
    op.drop_table("user_memory_embedding_jobs")

    op.execute(
        "DROP TRIGGER IF EXISTS user_memory_views_search_vector_trigger ON user_memory_views"
    )
    op.execute("DROP FUNCTION IF EXISTS user_memory_views_search_vector_update()")
    op.drop_index("idx_user_memory_views_vector_collection", table_name="user_memory_views")
    op.drop_index("idx_user_memory_views_vector_sync", table_name="user_memory_views")
    op.drop_index("idx_user_memory_views_content_trgm", table_name="user_memory_views")
    op.drop_index("idx_user_memory_views_search_vector", table_name="user_memory_views")
    op.drop_column("user_memory_views", "vector_error")
    op.drop_column("user_memory_views", "vector_indexed_at")
    op.drop_column("user_memory_views", "vector_collection_name")
    op.drop_column("user_memory_views", "vector_document_hash")
    op.drop_column("user_memory_views", "vector_sync_state")
    op.drop_column("user_memory_views", "search_vector")

    op.execute(
        "DROP TRIGGER IF EXISTS user_memory_entries_search_vector_trigger ON user_memory_entries"
    )
    op.execute("DROP FUNCTION IF EXISTS user_memory_entries_search_vector_update()")
    op.drop_index("idx_user_memory_entries_vector_collection", table_name="user_memory_entries")
    op.drop_index("idx_user_memory_entries_vector_sync", table_name="user_memory_entries")
    op.drop_index("idx_user_memory_entries_canonical_text_trgm", table_name="user_memory_entries")
    op.drop_index("idx_user_memory_entries_search_vector", table_name="user_memory_entries")
    op.drop_column("user_memory_entries", "vector_error")
    op.drop_column("user_memory_entries", "vector_indexed_at")
    op.drop_column("user_memory_entries", "vector_collection_name")
    op.drop_column("user_memory_entries", "vector_document_hash")
    op.drop_column("user_memory_entries", "vector_sync_state")
    op.drop_column("user_memory_entries", "event_time_end")
    op.drop_column("user_memory_entries", "event_time_start")
    op.drop_column("user_memory_entries", "search_vector")
