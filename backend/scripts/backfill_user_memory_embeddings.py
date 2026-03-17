#!/usr/bin/env python3
"""Enqueue and optionally execute a full backfill for user-memory embeddings."""

import argparse
import json
import sys
import time
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from database.connection import get_db_session
from database.models import UserMemoryEntry, UserMemoryView
from shared.logging import setup_logging
from user_memory.indexing_jobs import count_pending_user_memory_jobs, enqueue_user_memory_upsert_job
from user_memory.indexing_worker import load_user_memory_indexing_settings, run_user_memory_indexing_once
from user_memory.vector_index import (
    bootstrap_user_memory_vector_index,
    build_user_memory_embedding_signature,
    resolve_active_user_memory_collection,
    set_user_memory_vector_index_state,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="Process all queued jobs before exiting")
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    setup_logging()
    state = bootstrap_user_memory_vector_index(build_state="building")
    collection_name = resolve_active_user_memory_collection()
    embedding_signature = build_user_memory_embedding_signature()

    enqueued = 0
    with get_db_session() as session:
        entries = (
            session.query(UserMemoryEntry)
            .filter(UserMemoryEntry.status.in_(["active", "superseded"]))
            .all()
        )
        views = (
            session.query(UserMemoryView)
            .filter(UserMemoryView.status.in_(["active", "superseded"]))
            .all()
        )
        for row in entries:
            enqueue_user_memory_upsert_job(
                session,
                source_kind="entry",
                source_id=int(row.id),
                user_id=str(row.user_id),
                collection_name=collection_name,
                embedding_signature=embedding_signature,
                payload={"reason": "backfill"},
            )
            row.vector_sync_state = "pending"
            row.vector_collection_name = collection_name
            enqueued += 1
        for row in views:
            enqueue_user_memory_upsert_job(
                session,
                source_kind="view",
                source_id=int(row.id),
                user_id=str(row.user_id),
                collection_name=collection_name,
                embedding_signature=embedding_signature,
                payload={"reason": "backfill"},
            )
            row.vector_sync_state = "pending"
            row.vector_collection_name = collection_name
            enqueued += 1
        session.flush()

    if args.strict:
        settings = load_user_memory_indexing_settings()
        while count_pending_user_memory_jobs() > 0:
            run_user_memory_indexing_once(settings, worker_id="backfill-script", reason="backfill")
            time.sleep(0.2)
        state["build_state"] = "ready"
        state["last_backfill_completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        set_user_memory_vector_index_state(state)

    print(
        json.dumps(
            {
                "collection_name": collection_name,
                "enqueued": enqueued,
                "pending_jobs": count_pending_user_memory_jobs(),
                "strict": bool(args.strict),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
