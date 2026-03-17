"""Performance tests for the user-memory retriever facade."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from user_memory.retriever import UserMemoryRetriever


def _item(*, item_id: int, content: str, score: float, source: str, fact_kind: str = "preference"):
    return SimpleNamespace(
        id=item_id,
        content=content,
        similarity_score=score,
        timestamp=datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc),
        metadata={
            "memory_source": source,
            ("entry_id" if source == "entry" else "view_id"): item_id,
            "fact_kind": fact_kind,
        },
    )


def test_user_memory_retriever_delegates_under_budget():
    retriever = UserMemoryRetriever()
    expected = [
        _item(
            item_id=index,
            content=f"用户事件 {index}",
            score=0.9 - index * 0.0002,
            source="entry",
            fact_kind="event" if index % 5 == 0 else "preference",
        )
        for index in range(40)
    ]
    hybrid = MagicMock()
    hybrid.search_user_memory.return_value = expected

    with patch("user_memory.retriever.get_user_memory_hybrid_retriever", return_value=hybrid):
        started = time.perf_counter()
        results = retriever.search_user_memory(
            user_id="u-1",
            query_text="用户过去做过什么",
            limit=40,
        )
        duration = time.perf_counter() - started

    assert results == expected
    assert duration < 0.05, f"user-memory retriever facade took {duration:.4f}s"
