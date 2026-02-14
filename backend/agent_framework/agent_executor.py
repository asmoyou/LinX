"""Agent execution loop and context management.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4.3: Agent Lifecycle
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from agent_framework.access_policy import resolve_memory_scopes
from agent_framework.agent_memory_interface import (
    AgentMemoryInterface,
    _format_agent_memory_content,
    get_agent_memory_interface,
)
from agent_framework.base_agent import BaseAgent
from memory_system.memory_interface import MemoryType, SearchQuery

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    """Context for agent execution."""

    agent_id: UUID
    user_id: UUID
    user_role: str = "user"
    task_id: Optional[UUID] = None
    task_description: str = ""
    additional_context: Optional[Dict[str, Any]] = None


class AgentExecutor:
    """Execute agents with proper context and memory access."""

    def __init__(self, memory_interface: Optional[AgentMemoryInterface] = None):
        """Initialize agent executor.

        Args:
            memory_interface: AgentMemoryInterface instance
        """
        self.memory_interface = memory_interface or get_agent_memory_interface()
        logger.info("AgentExecutor initialized")

    @staticmethod
    def _normalize_access_level(access_level: Any) -> str:
        """Normalize access level values from agent config."""
        if isinstance(access_level, str) and access_level.strip():
            return access_level.strip()
        return "private"

    @staticmethod
    def _normalize_string_list(raw_values: Any) -> list[str]:
        """Normalize optional string list config fields."""
        if not isinstance(raw_values, list):
            return []
        values: list[str] = []
        for value in raw_values:
            if isinstance(value, str) and value.strip():
                values.append(value.strip())
        return values

    @staticmethod
    def _extract_content(value: Any) -> Optional[str]:
        """Extract text content from memory/search result objects."""
        if isinstance(value, str):
            return value if value.strip() else None

        if isinstance(value, dict):
            for key in ("content", "content_snippet", "summary"):
                text = value.get(key)
                if isinstance(text, str) and text.strip():
                    return text
            return None

        text = getattr(value, "content", None)
        if isinstance(text, str) and text.strip():
            return text
        return None

    @staticmethod
    def _extract_value(value: Any, key: str) -> Any:
        """Extract a field from either dict-based or object-based values."""
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _extract_metadata(value: Any) -> Dict[str, Any]:
        """Extract metadata dictionary from search results."""
        if isinstance(value, dict):
            metadata = value.get("metadata")
            if isinstance(metadata, dict):
                return metadata
            return {}

        metadata = getattr(value, "metadata", None)
        if isinstance(metadata, dict):
            return metadata
        return {}

    def _extract_similarity_score(self, value: Any) -> Optional[float]:
        """Extract normalized similarity score."""
        score = self._extract_value(value, "similarity_score")
        if score is None:
            score = self._extract_value(value, "relevance_score")
        try:
            return float(score) if score is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _trim_text(text: Optional[str], max_chars: int = 120) -> str:
        """Trim text to a safe debug preview length."""
        if not text:
            return ""
        clean = " ".join(text.split())
        if len(clean) <= max_chars:
            return clean
        return clean[: max_chars - 3] + "..."

    def _retrieve_memories_without_similarity_threshold(
        self,
        *,
        query_text: str,
        memory_type: MemoryType,
        top_k: int,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> list[Any]:
        """Retry memory retrieval with `min_similarity=0` as a fallback."""
        search_query = SearchQuery(
            query_text=query_text,
            memory_type=memory_type,
            agent_id=agent_id,
            user_id=user_id,
            task_id=task_id,
            top_k=top_k,
            min_similarity=0.0,
        )
        return self.memory_interface.memory_system.retrieve_memories(search_query)

    def _build_execution_context_internal(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
        top_k: int,
        knowledge_min_relevance_score: Optional[float],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Internal context builder returning both context and debug data."""
        if top_k <= 0:
            top_k = 3

        config = getattr(agent, "config", None)
        access_level = self._normalize_access_level(getattr(config, "access_level", None))
        allowed_memory = self._normalize_string_list(getattr(config, "allowed_memory", None))
        allowed_knowledge = self._normalize_string_list(getattr(config, "allowed_knowledge", None))

        agent_memories = []
        company_memories = []
        user_context_memories = []
        memory_scopes = resolve_memory_scopes(
            access_level=access_level,
            allowed_memory=allowed_memory,
        )
        memory_debug: Dict[str, Any] = {
            "query": context.task_description,
            "top_k": top_k,
            "scopes": memory_scopes,
            "agent": {
                "enabled": "agent" in memory_scopes,
                "filter": f"agent_id={context.agent_id}",
                "hit_count": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
            "company": {
                "enabled": "company" in memory_scopes,
                "filter": f"user_id={context.user_id}, memory_type=company",
                "hit_count": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
            "user_context": {
                "enabled": "user_context" in memory_scopes,
                "filter": f"user_id={context.user_id}, memory_type=user_context",
                "hit_count": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
        }

        if "agent" in memory_scopes:
            try:
                agent_memories = self.memory_interface.retrieve_agent_memory(
                    agent_id=context.agent_id,
                    query=context.task_description,
                    top_k=top_k,
                )
                logger.debug(f"Retrieved {len(agent_memories)} agent memories")
                if not agent_memories:
                    try:
                        fallback_memories = self._retrieve_memories_without_similarity_threshold(
                            query_text=context.task_description,
                            memory_type=MemoryType.AGENT,
                            agent_id=str(context.agent_id),
                            top_k=top_k,
                        )
                        if fallback_memories:
                            agent_memories = fallback_memories
                            memory_debug["agent"]["fallback_used"] = True
                            memory_debug["agent"]["fallback_hit_count"] = len(fallback_memories)
                    except Exception as fallback_error:
                        memory_debug["agent"]["fallback_error"] = str(fallback_error)
            except Exception as mem_error:
                memory_debug["agent"]["error"] = str(mem_error)
                logger.warning(
                    f"Failed to retrieve agent memories (continuing without): {mem_error}"
                )

        if "company" in memory_scopes:
            try:
                company_memories = self.memory_interface.retrieve_company_memory(
                    user_id=context.user_id,
                    query=context.task_description,
                    top_k=top_k,
                )
                logger.debug(f"Retrieved {len(company_memories)} company memories")
                if not company_memories:
                    try:
                        fallback_memories = self._retrieve_memories_without_similarity_threshold(
                            query_text=context.task_description,
                            memory_type=MemoryType.COMPANY,
                            user_id=str(context.user_id),
                            top_k=top_k,
                        )
                        if fallback_memories:
                            company_memories = fallback_memories
                            memory_debug["company"]["fallback_used"] = True
                            memory_debug["company"]["fallback_hit_count"] = len(fallback_memories)
                    except Exception as fallback_error:
                        memory_debug["company"]["fallback_error"] = str(fallback_error)
            except Exception as mem_error:
                memory_debug["company"]["error"] = str(mem_error)
                logger.warning(
                    f"Failed to retrieve company memories (continuing without): {mem_error}"
                )

        if "user_context" in memory_scopes:
            try:
                user_context_query = SearchQuery(
                    query_text=context.task_description,
                    memory_type=MemoryType.USER_CONTEXT,
                    user_id=str(context.user_id),
                    top_k=top_k,
                )
                user_context_memories = self.memory_interface.memory_system.retrieve_memories(
                    user_context_query
                )
                logger.debug(f"Retrieved {len(user_context_memories)} user-context memories")
                if not user_context_memories:
                    try:
                        fallback_memories = self._retrieve_memories_without_similarity_threshold(
                            query_text=context.task_description,
                            memory_type=MemoryType.USER_CONTEXT,
                            user_id=str(context.user_id),
                            top_k=top_k,
                        )
                        if fallback_memories:
                            user_context_memories = fallback_memories
                            memory_debug["user_context"]["fallback_used"] = True
                            memory_debug["user_context"]["fallback_hit_count"] = len(
                                fallback_memories
                            )
                    except Exception as fallback_error:
                        memory_debug["user_context"]["fallback_error"] = str(fallback_error)
            except Exception as mem_error:
                memory_debug["user_context"]["error"] = str(mem_error)
                logger.warning(
                    f"Failed to retrieve user-context memories (continuing without): {mem_error}"
                )

        knowledge_snippets: list[str] = []
        knowledge_hits: list[Dict[str, Any]] = []
        knowledge_debug: Dict[str, Any] = {
            "query": context.task_description,
            "top_k": top_k,
            "allowed_collections": allowed_knowledge,
            "candidate_document_count": None,
            "candidate_document_ids_preview": [],
            "hit_count": 0,
            "hits": [],
            "error": None,
        }
        try:
            candidate_document_ids = None
            if allowed_knowledge:
                from access_control.knowledge_filter import filter_knowledge_query
                from access_control.permissions import CurrentUser
                from database.connection import get_db_session
                from database.models import KnowledgeItem

                current_user = CurrentUser(
                    user_id=str(context.user_id),
                    username="agent_executor_user",
                    role=context.user_role or "user",
                )

                allowed_collection_uuids = []
                for collection_id in allowed_knowledge:
                    try:
                        allowed_collection_uuids.append(UUID(collection_id))
                    except ValueError:
                        continue

                if allowed_collection_uuids:
                    with get_db_session() as db_session:
                        query = db_session.query(KnowledgeItem.knowledge_id)
                        query = filter_knowledge_query(query, current_user)
                        query = query.filter(
                            KnowledgeItem.collection_id.in_(allowed_collection_uuids)
                        )
                        candidate_document_ids = [str(row[0]) for row in query.all()]
                else:
                    candidate_document_ids = []

            if isinstance(candidate_document_ids, list):
                knowledge_debug["candidate_document_count"] = len(candidate_document_ids)
                knowledge_debug["candidate_document_ids_preview"] = candidate_document_ids[:5]

            if candidate_document_ids != []:
                from knowledge_base.knowledge_search import SearchFilter, get_knowledge_search

                search_service = get_knowledge_search()
                search_filter = SearchFilter(
                    user_id=str(context.user_id),
                    user_role=context.user_role or "user",
                    document_ids=candidate_document_ids,
                    top_k=top_k,
                    min_relevance_score=knowledge_min_relevance_score,
                )
                knowledge_results = search_service.search(
                    query=context.task_description,
                    search_filter=search_filter,
                )
                for result in knowledge_results[:top_k]:
                    snippet = self._extract_content(result)
                    if snippet:
                        knowledge_snippets.append(snippet)

                    metadata = self._extract_metadata(result)
                    hit_data: Dict[str, Any] = {
                        "document_id": self._extract_value(result, "document_id")
                        or self._extract_value(result, "knowledge_id"),
                        "chunk_id": self._extract_value(result, "chunk_id"),
                        "chunk_index": self._extract_value(result, "chunk_index"),
                        "similarity_score": self._extract_similarity_score(result),
                        "title": (
                            metadata.get("title")
                            or metadata.get("document_title")
                            or metadata.get("knowledge_title")
                        ),
                        "file_reference": (
                            metadata.get("file_reference")
                            or metadata.get("source_file")
                            or metadata.get("filename")
                            or metadata.get("file_name")
                        ),
                        "excerpt": self._trim_text(snippet, max_chars=180),
                    }
                    knowledge_hits.append(hit_data)

                # Enrich file-level metadata for debug display.
                unresolved_doc_ids = []
                for hit in knowledge_hits:
                    doc_id = hit.get("document_id")
                    if not doc_id:
                        continue
                    if hit.get("title") and hit.get("file_reference"):
                        continue
                    unresolved_doc_ids.append(str(doc_id))

                if unresolved_doc_ids:
                    try:
                        from database.connection import get_db_session
                        from database.models import KnowledgeItem

                        doc_uuid_map: Dict[UUID, str] = {}
                        for doc_id in unresolved_doc_ids:
                            try:
                                doc_uuid_map[UUID(doc_id)] = doc_id
                            except ValueError:
                                continue

                        if doc_uuid_map:
                            with get_db_session() as db_session:
                                rows = (
                                    db_session.query(
                                        KnowledgeItem.knowledge_id,
                                        KnowledgeItem.title,
                                        KnowledgeItem.file_reference,
                                    )
                                    .filter(
                                        KnowledgeItem.knowledge_id.in_(list(doc_uuid_map.keys()))
                                    )
                                    .all()
                                )
                            details = {
                                str(row.knowledge_id): {
                                    "title": row.title,
                                    "file_reference": row.file_reference,
                                }
                                for row in rows
                            }
                            for hit in knowledge_hits:
                                doc_id = str(hit.get("document_id") or "")
                                if not doc_id or doc_id not in details:
                                    continue
                                detail = details[doc_id]
                                if not hit.get("title"):
                                    hit["title"] = detail.get("title")
                                if not hit.get("file_reference"):
                                    hit["file_reference"] = detail.get("file_reference")
                    except Exception as meta_error:
                        logger.debug(
                            "Knowledge hit metadata enrichment failed: %s",
                            meta_error,
                        )

        except Exception as knowledge_error:
            knowledge_debug["error"] = str(knowledge_error)
            logger.warning(
                "Failed to retrieve knowledge snippets (continuing without): %s",
                knowledge_error,
            )

        knowledge_debug["hit_count"] = len(knowledge_hits)
        knowledge_debug["hits"] = knowledge_hits

        exec_context = {
            "agent_memories": [],
            "company_memories": [],
            "user_context_memories": [],
            "knowledge_snippets": knowledge_snippets,
            "knowledge_hits": knowledge_hits,
        }

        for memory in agent_memories:
            content = self._extract_content(memory)
            if content:
                exec_context["agent_memories"].append(content)
        for memory in company_memories:
            content = self._extract_content(memory)
            if content:
                exec_context["company_memories"].append(content)
        for memory in user_context_memories:
            content = self._extract_content(memory)
            if content:
                exec_context["user_context_memories"].append(content)

        memory_debug["agent"]["hit_count"] = len(exec_context["agent_memories"])
        memory_debug["company"]["hit_count"] = len(exec_context["company_memories"])
        memory_debug["user_context"]["hit_count"] = len(exec_context["user_context_memories"])
        memory_debug["agent"]["hits"] = [
            self._trim_text(content) for content in exec_context["agent_memories"][:3]
        ]
        memory_debug["company"]["hits"] = [
            self._trim_text(content) for content in exec_context["company_memories"][:3]
        ]
        memory_debug["user_context"]["hits"] = [
            self._trim_text(content) for content in exec_context["user_context_memories"][:3]
        ]

        return exec_context, {"memory": memory_debug, "knowledge": knowledge_debug}

    def build_execution_context(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
        top_k: int = 3,
        knowledge_min_relevance_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build memory and knowledge context for an execution."""
        exec_context, _ = self._build_execution_context_internal(
            agent=agent,
            context=context,
            top_k=top_k,
            knowledge_min_relevance_score=knowledge_min_relevance_score,
        )
        return exec_context

    def build_execution_context_with_debug(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
        top_k: int = 3,
        knowledge_min_relevance_score: Optional[float] = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Build execution context and include retrieval debug details."""
        return self._build_execution_context_internal(
            agent=agent,
            context=context,
            top_k=top_k,
            knowledge_min_relevance_score=knowledge_min_relevance_score,
        )

    def execute(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
    ) -> Dict[str, Any]:
        """Execute agent with given context.

        Args:
            agent: BaseAgent instance
            context: ExecutionContext with task details

        Returns:
            Dict with execution results
        """
        logger.info(
            f"Executing agent: {agent.config.name}",
            extra={"agent_id": str(context.agent_id), "task_id": str(context.task_id)},
        )

        try:
            exec_context = self.build_execution_context(agent=agent, context=context)

            if context.additional_context:
                exec_context.update(context.additional_context)

            # Execute task
            result = agent.execute_task(
                task_description=context.task_description,
                context=exec_context,
            )

            # Store result in memory if successful (optional - don't fail if this fails)
            if result.get("success"):
                try:
                    content = _format_agent_memory_content(
                        task=context.task_description,
                        result=result.get("output", ""),
                        agent_name=agent.config.name,
                    )
                    self.memory_interface.store_agent_memory(
                        agent_id=context.agent_id,
                        content=content,
                        metadata={"task_id": str(context.task_id) if context.task_id else None},
                    )
                    logger.debug("Stored execution result in agent memory")
                except Exception as mem_error:
                    logger.warning(f"Failed to store result in memory (continuing): {mem_error}")

            logger.info(f"Agent execution completed: {agent.config.name}")
            return result

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "output": None,
            }


# Singleton instance
_agent_executor: Optional[AgentExecutor] = None


def get_agent_executor() -> AgentExecutor:
    """Get or create the agent executor singleton.

    Returns:
        AgentExecutor instance
    """
    global _agent_executor
    if _agent_executor is None:
        _agent_executor = AgentExecutor()
    return _agent_executor
