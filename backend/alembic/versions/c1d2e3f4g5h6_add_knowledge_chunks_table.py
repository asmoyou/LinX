"""Add knowledge_chunks table with BM25 full-text search support

Revision ID: c1d2e3f4g5h6
Revises: b9g2h3i4j5k6
Create Date: 2026-02-06 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4g5h6"
down_revision: Union[str, Sequence[str], None] = "b9g2h3i4j5k6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create knowledge_chunks table with GIN index and auto-update trigger."""
    # Create knowledge_chunks table using raw SQL for tsvector support
    op.execute("""
        CREATE TABLE knowledge_chunks (
            chunk_id UUID NOT NULL PRIMARY KEY,
            knowledge_id UUID NOT NULL REFERENCES knowledge_items(knowledge_id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            content TEXT NOT NULL,
            keywords VARCHAR[] DEFAULT NULL,
            questions VARCHAR[] DEFAULT NULL,
            summary TEXT DEFAULT NULL,
            token_count INTEGER DEFAULT NULL,
            search_vector TSVECTOR DEFAULT NULL,
            chunk_metadata JSONB DEFAULT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # Create indexes
    op.execute(
        "CREATE INDEX ix_knowledge_chunks_knowledge_id "
        "ON knowledge_chunks (knowledge_id)"
    )
    op.execute(
        "CREATE INDEX idx_chunk_knowledge_index "
        "ON knowledge_chunks (knowledge_id, chunk_index)"
    )
    op.execute(
        "CREATE INDEX idx_chunk_search_vector "
        "ON knowledge_chunks USING gin (search_vector)"
    )

    # Create trigger function to auto-update search_vector
    op.execute("""
        CREATE OR REPLACE FUNCTION knowledge_chunks_search_vector_update()
        RETURNS trigger AS $$
        BEGIN
            NEW.search_vector :=
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.content, '')), 'A') ||
                setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.summary, '')), 'B') ||
                setweight(to_tsvector('pg_catalog.simple',
                    COALESCE(array_to_string(NEW.keywords, ' '), '')), 'C');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger
    op.execute("""
        CREATE TRIGGER knowledge_chunks_search_vector_trigger
        BEFORE INSERT OR UPDATE ON knowledge_chunks
        FOR EACH ROW EXECUTE FUNCTION knowledge_chunks_search_vector_update();
    """)


def downgrade() -> None:
    """Drop knowledge_chunks table and related objects."""
    op.execute(
        "DROP TRIGGER IF EXISTS knowledge_chunks_search_vector_trigger ON knowledge_chunks"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS knowledge_chunks_search_vector_update()"
    )
    op.execute("DROP TABLE IF EXISTS knowledge_chunks")
