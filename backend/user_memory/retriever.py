"""Facade over the user-memory hybrid retrieval pipeline."""

from __future__ import annotations

from typing import Optional

from user_memory.hybrid_retriever import (
    UserMemoryHybridRetriever,
    get_user_memory_hybrid_retriever,
)


class UserMemoryRetriever:
    """Thin facade that centralizes default planner modes for callers."""

    def search_user_memory(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
        planner_mode: str = "runtime_light",
        allow_reflection: bool = False,
    ):
        return get_user_memory_hybrid_retriever().search_user_memory(
            user_id=user_id,
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode=planner_mode,
            allow_reflection=allow_reflection,
        )

    def list_profile(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
        planner_mode: str = "api_full",
        allow_reflection: bool = False,
    ):
        return get_user_memory_hybrid_retriever().list_profile(
            user_id=user_id,
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode=planner_mode,
            allow_reflection=allow_reflection,
        )

    def list_episodes(
        self,
        *,
        user_id: str,
        query_text: str,
        limit: int = 20,
        min_score: Optional[float] = None,
        planner_mode: str = "api_full",
        allow_reflection: bool = False,
    ):
        return get_user_memory_hybrid_retriever().list_episodes(
            user_id=user_id,
            query_text=query_text,
            limit=limit,
            min_score=min_score,
            planner_mode=planner_mode,
            allow_reflection=allow_reflection,
        )


_user_memory_retriever: Optional[UserMemoryRetriever] = None


def get_user_memory_retriever() -> UserMemoryRetriever:
    """Return the shared user-memory retriever facade."""

    global _user_memory_retriever
    if _user_memory_retriever is None:
        _user_memory_retriever = UserMemoryRetriever()
    return _user_memory_retriever


__all__ = [
    "UserMemoryHybridRetriever",
    "UserMemoryRetriever",
    "get_user_memory_hybrid_retriever",
    "get_user_memory_retriever",
]
