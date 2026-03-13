"""Runtime context retrieval for user memory and published skills."""

from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from skill_learning.service import get_skill_proposal_service
from user_memory.retriever import get_user_memory_retriever

logger = logging.getLogger(__name__)


class RuntimeContextService:
    """Retrieve runtime context from reset-architecture memory products."""

    def retrieve_skills(
        self,
        *,
        agent_id: UUID | str,
        user_id: UUID | str,
        query: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
    ) -> List[object]:
        """Retrieve published skill experiences for an agent."""

        results = get_skill_proposal_service().list_published_experiences(
            agent_id=str(agent_id),
            query_text=query,
            limit=top_k,
            min_score=min_similarity,
        )
        logger.info(
            "Retrieved runtime skills",
            extra={
                "agent_id": str(agent_id),
                "user_id": str(user_id),
                "query_preview": (query or "")[:120],
                "top_k": top_k,
                "min_similarity": min_similarity,
                "hit_count": len(results),
            },
        )
        return results

    def retrieve_user_memory(
        self,
        *,
        user_id: UUID | str,
        query: str,
        top_k: int = 5,
        min_similarity: Optional[float] = None,
    ) -> List[object]:
        """Retrieve merged user memory for runtime injection."""

        results = get_user_memory_retriever().search_user_memory(
            user_id=str(user_id),
            query_text=query,
            limit=top_k,
            min_score=min_similarity,
        )
        logger.info(
            "Retrieved runtime user memory",
            extra={
                "user_id": str(user_id),
                "query_preview": (query or "")[:120],
                "top_k": top_k,
                "min_similarity": min_similarity,
                "hit_count": len(results),
            },
        )
        return results


_runtime_context_service: Optional[RuntimeContextService] = None


def get_runtime_context_service() -> RuntimeContextService:
    """Return the shared runtime context service."""

    global _runtime_context_service
    if _runtime_context_service is None:
        _runtime_context_service = RuntimeContextService()
    return _runtime_context_service
