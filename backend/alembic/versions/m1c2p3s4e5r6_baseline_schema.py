"""baseline_schema

Revision ID: m1c2p3s4e5r6
Revises:
Create Date: 2026-03-23 22:03:36.832746

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from database.models import Base
from object_storage.file_metadata import FileMetadata  # noqa: F401

# revision identifiers, used by Alembic.
revision: str = "m1c2p3s4e5r6"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_MEMORY_ENTRIES_SEARCH_TRIGGER_SQL = """
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

USER_MEMORY_ENTRIES_TRIGGER_SQL = """
CREATE TRIGGER user_memory_entries_search_vector_trigger
BEFORE INSERT OR UPDATE ON user_memory_entries
FOR EACH ROW EXECUTE FUNCTION user_memory_entries_search_vector_update();
"""

USER_MEMORY_VIEWS_SEARCH_TRIGGER_SQL = """
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

USER_MEMORY_VIEWS_TRIGGER_SQL = """
CREATE TRIGGER user_memory_views_search_vector_trigger
BEFORE INSERT OR UPDATE ON user_memory_views
FOR EACH ROW EXECUTE FUNCTION user_memory_views_search_vector_update();
"""

KNOWLEDGE_CHUNKS_SEARCH_TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION knowledge_chunks_search_vector_update()
RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.content, '')), 'A') ||
        setweight(to_tsvector('pg_catalog.simple', COALESCE(NEW.summary, '')), 'B') ||
        setweight(
            to_tsvector(
                'pg_catalog.simple',
                COALESCE(array_to_string(NEW.keywords, ' '), '')
            ),
            'C'
        );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

KNOWLEDGE_CHUNKS_TRIGGER_SQL = """
CREATE TRIGGER knowledge_chunks_search_vector_trigger
BEFORE INSERT OR UPDATE ON knowledge_chunks
FOR EACH ROW EXECUTE FUNCTION knowledge_chunks_search_vector_update();
"""


def _create_search_vector_triggers() -> None:
    op.execute(USER_MEMORY_ENTRIES_SEARCH_TRIGGER_SQL)
    op.execute(USER_MEMORY_ENTRIES_TRIGGER_SQL)
    op.execute(USER_MEMORY_VIEWS_SEARCH_TRIGGER_SQL)
    op.execute(USER_MEMORY_VIEWS_TRIGGER_SQL)
    op.execute(KNOWLEDGE_CHUNKS_SEARCH_TRIGGER_SQL)
    op.execute(KNOWLEDGE_CHUNKS_TRIGGER_SQL)


def _drop_search_vector_triggers() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS user_memory_entries_search_vector_trigger "
        "ON user_memory_entries"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS user_memory_views_search_vector_trigger "
        "ON user_memory_views"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS knowledge_chunks_search_vector_trigger "
        "ON knowledge_chunks"
    )
    op.execute("DROP FUNCTION IF EXISTS user_memory_entries_search_vector_update()")
    op.execute("DROP FUNCTION IF EXISTS user_memory_views_search_vector_update()")
    op.execute("DROP FUNCTION IF EXISTS knowledge_chunks_search_vector_update()")


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gin")
    Base.metadata.create_all(bind=bind)
    _create_search_vector_triggers()


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    _drop_search_vector_triggers()
    Base.metadata.drop_all(bind=bind)
