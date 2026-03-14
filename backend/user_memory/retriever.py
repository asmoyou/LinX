"""User-memory retrieval service for reset runtime and APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from user_memory.memory_entry_retrieval import get_memory_entry_retrieval_service
from user_memory.items import RetrievedMemoryItem
from user_memory.user_memory_view_retrieval import get_user_memory_view_retrieval_service


class UserMemoryRetriever:
    """Search user atomic facts and profile views under one contract."""

    @staticmethod
    def _dedupe_key(item: RetrievedMemoryItem) -> Tuple[str, str, str]:
        metadata = dict(item.metadata or {})
        return (
            str(metadata.get("memory_source") or ""),
            str(
                metadata.get("entry_id")
                or metadata.get("view_id")
                or metadata.get("proposal_id")
                or ""
            ),
            str(item.content or "").strip(),
        )

    @staticmethod
    def _passes_min_score(item: RetrievedMemoryItem, min_score: Optional[float]) -> bool:
        if min_score is None:
            return True
        try:
            score = float(item.similarity_score or 0.0)
        except (TypeError, ValueError):
            return False
        return score >= float(min_score)

    @staticmethod
    def _sort_key(item: RetrievedMemoryItem) -> Tuple[float, datetime]:
        timestamp = item.timestamp if isinstance(item.timestamp, datetime) else datetime.min
        try:
            score = float(item.similarity_score or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        return (score, timestamp)

    def _merge_items(
        self,
        *groups: Iterable[RetrievedMemoryItem],
        limit: int,
        min_score: Optional[float] = None,
    ) -> List[RetrievedMemoryItem]:
        merged: List[RetrievedMemoryItem] = []
        seen = set()
        for group in groups:
            for item in group or []:
                if not self._passes_min_score(item, min_score):
                    continue
                key = self._dedupe_key(item)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        merged.sort(key=self._sort_key, reverse=True)
        return merged[: max(int(limit), 1)]

    def search_user_memory(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
    ) -> List[RetrievedMemoryItem]:
        facts = get_memory_entry_retrieval_service().retrieve_user_facts(
            user_id=str(user_id),
            query_text=query_text,
            top_k=limit,
        )
        profile = get_user_memory_view_retrieval_service().retrieve_user_profile(
            user_id=str(user_id),
            query_text=query_text,
            top_k=limit,
        )
        return self._merge_items(facts, profile, limit=limit, min_score=min_score)

    def list_profile(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
    ) -> List[RetrievedMemoryItem]:
        profile = get_user_memory_view_retrieval_service().retrieve_user_profile(
            user_id=str(user_id),
            query_text=query_text,
            top_k=limit,
        )
        return self._merge_items(profile, limit=limit, min_score=min_score)

    def list_episodes(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
    ) -> List[RetrievedMemoryItem]:
        """Return user episode views, with event-fact fallback for older rows."""

        episode_views = get_user_memory_view_retrieval_service().retrieve_user_episodes(
            user_id=str(user_id),
            query_text=query_text,
            top_k=limit,
        )
        if episode_views:
            return self._merge_items(episode_views, limit=limit, min_score=min_score)

        facts = get_memory_entry_retrieval_service().retrieve_user_facts(
            user_id=str(user_id),
            query_text=query_text,
            top_k=max(int(limit), 1) * 4,
        )
        episodes = [
            item
            for item in facts
            if str((item.metadata or {}).get("fact_kind") or "").strip().lower() == "event"
        ]
        return self._merge_items(episodes, limit=limit, min_score=min_score)


_user_memory_retriever: Optional[UserMemoryRetriever] = None


def get_user_memory_retriever() -> UserMemoryRetriever:
    """Return the shared user-memory retriever."""

    global _user_memory_retriever
    if _user_memory_retriever is None:
        _user_memory_retriever = UserMemoryRetriever()
    return _user_memory_retriever


__all__ = ["UserMemoryRetriever", "get_user_memory_retriever"]
