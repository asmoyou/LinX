#!/usr/bin/env python3
"""Verify user-memory hybrid retrieval latency and vector index health."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from database.connection import get_db_session
from database.models import UserMemoryEntry, UserMemoryView
from shared.logging import setup_logging
from user_memory.lexical_search import normalize_text
from user_memory.storage_cleanup import reconcile_user_memory_vectors
from user_memory.hybrid_retriever import get_user_memory_hybrid_retriever


def _sample_queries(limit: int = 20) -> list[tuple[str, str]]:
    with get_db_session() as session:
        rows = (
            session.query(UserMemoryEntry.user_id, UserMemoryEntry.canonical_text)
            .filter(UserMemoryEntry.status.in_(["active", "superseded"]))
            .order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
            .limit(max(int(limit), 1))
            .all()
        )
    return [(str(user_id), str(text)) for user_id, text in rows if user_id and text]


def _recent_baseline(user_id: str, limit: int = 5) -> list[str]:
    with get_db_session() as session:
        entry_rows = (
            session.query(
                UserMemoryEntry.canonical_text, UserMemoryEntry.updated_at, UserMemoryEntry.id
            )
            .filter(
                UserMemoryEntry.user_id == str(user_id),
                UserMemoryEntry.status == "active",
            )
            .order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
            .limit(max(int(limit), 1))
            .all()
        )
        view_rows = (
            session.query(UserMemoryView.content, UserMemoryView.updated_at, UserMemoryView.id)
            .filter(
                UserMemoryView.user_id == str(user_id),
                UserMemoryView.status == "active",
            )
            .order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
            .limit(max(int(limit), 1))
            .all()
        )

    merged = [
        (str(content or "").strip(), updated_at, int(row_id))
        for content, updated_at, row_id in [*entry_rows, *view_rows]
        if str(content or "").strip()
    ]
    merged.sort(
        key=lambda row: (row[1] or datetime.min.replace(tzinfo=timezone.utc), row[2]),
        reverse=True,
    )
    return [content for content, _, _ in merged[: max(int(limit), 1)]]


def _is_hit(query_text: str, contents: list[str]) -> bool:
    normalized_query = normalize_text(query_text)
    if not normalized_query:
        return False
    for content in contents:
        normalized_content = normalize_text(content)
        if not normalized_content:
            continue
        if normalized_query in normalized_content or normalized_content in normalized_query:
            return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    setup_logging()
    queries = _sample_queries(limit=max(int(args.limit), 1))
    hybrid = get_user_memory_hybrid_retriever()

    hybrid_hits = 0
    baseline_hits = 0
    hybrid_elapsed = 0.0
    baseline_elapsed = 0.0

    for user_id, query_text in queries:
        started = time.perf_counter()
        hybrid_results = hybrid.search_user_memory(
            user_id=user_id,
            query_text=query_text,
            limit=5,
            planner_mode="api_full",
            allow_reflection=True,
        )
        hybrid_elapsed += time.perf_counter() - started

        started = time.perf_counter()
        baseline_contents = _recent_baseline(user_id=user_id, limit=5)
        baseline_elapsed += time.perf_counter() - started

        if _is_hit(query_text, [str(item.content or "") for item in hybrid_results]):
            hybrid_hits += 1
        if _is_hit(query_text, baseline_contents):
            baseline_hits += 1

    reconcile = reconcile_user_memory_vectors(
        dry_run=True,
        batch_size=500,
        compact_on_cycle=False,
    )
    result = {
        "sample_queries": len(queries),
        "hybrid_exact_hit_queries": hybrid_hits,
        "recent_baseline_exact_hit_queries": baseline_hits,
        "hybrid_avg_ms": round((hybrid_elapsed / max(len(queries), 1)) * 1000, 2),
        "recent_baseline_avg_ms": round((baseline_elapsed / max(len(queries), 1)) * 1000, 2),
        "reconcile": reconcile,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
