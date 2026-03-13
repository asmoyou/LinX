"""Performance tests for reset-architecture user-memory retrieval."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from user_memory.retriever import UserMemoryRetriever


def _item(*, item_id: int, content: str, score: float, source: str, fact_kind: str = "preference"):
    return SimpleNamespace(
        id=item_id,
        content=content,
        similarity_score=score,
        timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        metadata={
            "memory_source": source,
            ("entry_id" if source == "entry" else "materialization_id"): item_id,
            "fact_kind": fact_kind,
        },
    )


def test_user_memory_retriever_merges_stubbed_load_under_budget():
    retriever = UserMemoryRetriever()
    fact_items = [
        _item(
            item_id=index,
            content=f"用户事件 {index}",
            score=0.9 - index * 0.0002,
            source="entry",
            fact_kind="event" if index % 5 == 0 else "preference",
        )
        for index in range(1000)
    ]
    profile_items = [
        _item(
            item_id=2000 + index,
            content=f"user.preference.preference_{index}=value_{index}",
            score=0.8 - index * 0.0005,
            source="materialization",
        )
        for index in range(200)
    ]

    with (
        patch(
            "user_memory.retriever.get_memory_entry_retrieval_service",
            return_value=SimpleNamespace(retrieve_user_facts=lambda **_: fact_items),
        ),
        patch(
            "user_memory.retriever.get_materialized_view_retrieval_service",
            return_value=SimpleNamespace(retrieve_user_profile=lambda **_: profile_items),
        ),
    ):
        started = time.perf_counter()
        results = retriever.search_user_memory(
            user_id="u-1",
            query_text="用户过去做过什么",
            limit=40,
        )
        duration = time.perf_counter() - started

    assert len(results) == 40
    assert duration < 0.25, f"user-memory retrieval took {duration:.4f}s"
