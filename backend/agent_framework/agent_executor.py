"""Agent execution loop and context management.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4.3: Agent Lifecycle
"""

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
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
    def _normalize_match_text(text: Optional[str]) -> str:
        """Normalize text for lightweight overlap matching."""
        raw = str(text or "").lower()
        return re.sub(r"[\s\W_]+", "", raw, flags=re.UNICODE)

    def _extract_query_terms(self, query_text: str) -> List[str]:
        """Extract language-agnostic query terms for relevance guard."""
        text = str(query_text or "").strip()
        if not text:
            return []

        zh_stop_terms = {
            "怎么",
            "如何",
            "一下",
            "上次",
            "还能",
            "可以",
            "是否",
            "请问",
            "这个",
            "那个",
            "什么",
        }
        en_stop_terms = {"what", "how", "can", "could", "would", "please", "about"}

        terms: List[str] = []
        seen = set()

        for token in re.findall(r"[a-zA-Z0-9]{3,}", text.lower()):
            if token in en_stop_terms or token in seen:
                continue
            seen.add(token)
            terms.append(token)

        for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
            if len(chunk) <= 4:
                if chunk in zh_stop_terms or chunk in seen:
                    continue
                seen.add(chunk)
                terms.append(chunk)
                continue

            # For long CJK chunks, add compact n-grams to avoid relying on full-sentence match.
            for n in (2, 3, 4):
                for i in range(0, len(chunk) - n + 1):
                    token = chunk[i : i + n]
                    if token in zh_stop_terms or token in seen:
                        continue
                    seen.add(token)
                    terms.append(token)
                    if len(terms) >= 64:
                        return terms
        return terms

    def _count_query_term_overlap(self, content: str, query_terms: List[str]) -> int:
        """Count how many extracted query terms appear in memory content."""
        if not query_terms:
            return 0
        raw_content = str(content or "")
        lower_content = raw_content.lower()
        normalized_content = self._normalize_match_text(raw_content)
        overlap = 0
        for term in query_terms:
            if not term:
                continue
            if term.isascii():
                if term.lower() in lower_content:
                    overlap += 1
                continue
            term_norm = self._normalize_match_text(term)
            if term in raw_content or (term_norm and term_norm in normalized_content):
                overlap += 1
        return overlap

    def _is_context_memory_relevant(self, memory: Any, query_text: str) -> bool:
        """Guard memory injection with a lightweight topic-relevance check."""
        content = self._extract_content(memory)
        if not content:
            return False

        similarity = self._extract_similarity_score(memory)
        score = float(similarity) if similarity is not None else 0.0
        # Keep only very high-confidence semantic matches without lexical overlap.
        if score >= 0.86:
            return True

        query_terms = self._extract_query_terms(query_text)
        if not query_terms:
            return score >= 0.72

        overlap_count = self._count_query_term_overlap(content, query_terms)
        if overlap_count >= 2:
            return True
        if overlap_count >= 1 and score >= 0.4:
            return True

        # Avoid off-topic context bleed from loosely similar past conversations.
        return False

    def _filter_context_memories(
        self,
        memories: List[Any],
        query_text: str,
    ) -> Tuple[List[Any], int]:
        """Filter out low-relevance memories before prompt injection."""
        if not memories:
            return [], 0
        kept: List[Any] = []
        filtered_out = 0
        for item in memories:
            if self._is_context_memory_relevant(item, query_text):
                kept.append(item)
            else:
                filtered_out += 1
        return kept, filtered_out

    @staticmethod
    def _trim_text(text: Optional[str], max_chars: int = 120) -> str:
        """Trim text to a safe debug preview length."""
        if not text:
            return ""
        clean = " ".join(text.split())
        if len(clean) <= max_chars:
            return clean
        return clean[: max_chars - 3] + "..."

    def _build_execution_context_internal(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
        top_k: int,
        knowledge_min_relevance_score: Optional[float],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Internal context builder returning both context and debug data."""
        context_started = time.perf_counter()
        if top_k <= 0:
            top_k = 3

        memory_min_similarity: Optional[float] = None
        if knowledge_min_relevance_score is not None:
            try:
                memory_min_similarity = max(
                    0.0,
                    min(float(knowledge_min_relevance_score), 1.0),
                )
            except (TypeError, ValueError):
                memory_min_similarity = None

        config = getattr(agent, "config", None)
        access_level = self._normalize_access_level(getattr(config, "access_level", None))
        allowed_memory = self._normalize_string_list(getattr(config, "allowed_memory", None))
        allowed_knowledge = self._normalize_string_list(getattr(config, "allowed_knowledge", None))

        agent_memories = []
        company_memories = []
        user_context_memories = []
        task_context_memories = []
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
                "filter": f"agent_id={context.agent_id}, user_id={context.user_id}",
                "min_similarity": memory_min_similarity,
                "pre_filter_hit_count": 0,
                "hit_count": 0,
                "filtered_out_count": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
            "company": {
                "enabled": "company" in memory_scopes,
                "filter": f"user_id={context.user_id}, memory_type=company",
                "min_similarity": memory_min_similarity,
                "pre_filter_hit_count": 0,
                "hit_count": 0,
                "filtered_out_count": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
            "user_context": {
                "enabled": "user_context" in memory_scopes,
                "filter": f"user_id={context.user_id}, memory_type=user_context",
                "min_similarity": memory_min_similarity,
                "pre_filter_hit_count": 0,
                "hit_count": 0,
                "filtered_out_count": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
            "task_context": {
                "enabled": "task_context" in memory_scopes and bool(context.task_id),
                "filter": (
                    f"user_id={context.user_id}, memory_type=task_context, task_id={context.task_id}"
                    if context.task_id
                    else "task_id=<missing>"
                ),
                "min_similarity": memory_min_similarity,
                "pre_filter_hit_count": 0,
                "hit_count": 0,
                "filtered_out_count": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
        }
        memory_retrieval_ms = 0.0

        if "agent" in memory_scopes:
            scope_started = time.perf_counter()
            try:
                agent_memories = self.memory_interface.retrieve_agent_memory(
                    agent_id=context.agent_id,
                    user_id=context.user_id,
                    query=context.task_description,
                    top_k=top_k,
                    min_similarity=memory_min_similarity,
                )
                logger.debug(f"Retrieved {len(agent_memories)} agent memories")
            except Exception as mem_error:
                memory_debug["agent"]["error"] = str(mem_error)
                logger.warning(
                    f"Failed to retrieve agent memories (continuing without): {mem_error}"
                )
            finally:
                elapsed_ms = round((time.perf_counter() - scope_started) * 1000.0, 2)
                memory_debug["agent"]["latency_ms"] = elapsed_ms
                memory_retrieval_ms += elapsed_ms

        if "company" in memory_scopes:
            scope_started = time.perf_counter()
            try:
                company_memories = self.memory_interface.retrieve_company_memory(
                    user_id=context.user_id,
                    query=context.task_description,
                    top_k=top_k,
                    min_similarity=memory_min_similarity,
                )
                logger.debug(f"Retrieved {len(company_memories)} company memories")
            except Exception as mem_error:
                memory_debug["company"]["error"] = str(mem_error)
                logger.warning(
                    f"Failed to retrieve company memories (continuing without): {mem_error}"
                )
            finally:
                elapsed_ms = round((time.perf_counter() - scope_started) * 1000.0, 2)
                memory_debug["company"]["latency_ms"] = elapsed_ms
                memory_retrieval_ms += elapsed_ms

        if "user_context" in memory_scopes:
            scope_started = time.perf_counter()
            try:
                user_context_query = SearchQuery(
                    query_text=context.task_description,
                    memory_type=MemoryType.USER_CONTEXT,
                    user_id=str(context.user_id),
                    top_k=top_k,
                    min_similarity=memory_min_similarity,
                )
                user_context_memories = self.memory_interface.memory_system.retrieve_memories(
                    user_context_query
                )
                logger.debug(f"Retrieved {len(user_context_memories)} user-context memories")
            except Exception as mem_error:
                memory_debug["user_context"]["error"] = str(mem_error)
                logger.warning(
                    f"Failed to retrieve user-context memories (continuing without): {mem_error}"
                )
            finally:
                elapsed_ms = round((time.perf_counter() - scope_started) * 1000.0, 2)
                memory_debug["user_context"]["latency_ms"] = elapsed_ms
                memory_retrieval_ms += elapsed_ms

        if "task_context" in memory_scopes and context.task_id:
            scope_started = time.perf_counter()
            try:
                task_context_query = SearchQuery(
                    query_text=context.task_description,
                    memory_type=MemoryType.TASK_CONTEXT,
                    user_id=str(context.user_id),
                    task_id=str(context.task_id),
                    top_k=top_k,
                    min_similarity=memory_min_similarity,
                )
                task_context_memories = self.memory_interface.memory_system.retrieve_memories(
                    task_context_query
                )
                logger.debug(f"Retrieved {len(task_context_memories)} task-context memories")
            except Exception as mem_error:
                memory_debug["task_context"]["error"] = str(mem_error)
                logger.warning(
                    f"Failed to retrieve task-context memories (continuing without): {mem_error}"
                )
            finally:
                elapsed_ms = round((time.perf_counter() - scope_started) * 1000.0, 2)
                memory_debug["task_context"]["latency_ms"] = elapsed_ms
                memory_retrieval_ms += elapsed_ms

        knowledge_started = time.perf_counter()
        knowledge_candidate_resolution_ms = 0.0
        knowledge_search_ms = 0.0
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
            candidate_started = time.perf_counter()
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
            knowledge_candidate_resolution_ms = round(
                (time.perf_counter() - candidate_started) * 1000.0,
                2,
            )

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
                search_started = time.perf_counter()
                knowledge_results = search_service.search(
                    query=context.task_description,
                    search_filter=search_filter,
                )
                knowledge_search_ms = round((time.perf_counter() - search_started) * 1000.0, 2)
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
        finally:
            knowledge_debug["timing_ms"] = {
                "candidate_resolution": knowledge_candidate_resolution_ms,
                "search": knowledge_search_ms,
                "total": round((time.perf_counter() - knowledge_started) * 1000.0, 2),
            }

        knowledge_debug["hit_count"] = len(knowledge_hits)
        knowledge_debug["hits"] = knowledge_hits

        exec_context = {
            "agent_memories": [],
            "company_memories": [],
            "user_context_memories": [],
            "task_context_memories": [],
            "knowledge_snippets": knowledge_snippets,
            "knowledge_hits": knowledge_hits,
        }

        memory_debug["agent"]["pre_filter_hit_count"] = len(agent_memories)
        memory_debug["company"]["pre_filter_hit_count"] = len(company_memories)
        memory_debug["user_context"]["pre_filter_hit_count"] = len(user_context_memories)
        memory_debug["task_context"]["pre_filter_hit_count"] = len(task_context_memories)

        memory_postprocess_started = time.perf_counter()
        agent_memories, agent_filtered = self._filter_context_memories(
            agent_memories, context.task_description
        )
        company_memories, company_filtered = self._filter_context_memories(
            company_memories, context.task_description
        )
        user_context_memories, user_context_filtered = self._filter_context_memories(
            user_context_memories, context.task_description
        )
        task_context_memories, task_context_filtered = self._filter_context_memories(
            task_context_memories, context.task_description
        )

        memory_debug["agent"]["filtered_out_count"] = agent_filtered
        memory_debug["company"]["filtered_out_count"] = company_filtered
        memory_debug["user_context"]["filtered_out_count"] = user_context_filtered
        memory_debug["task_context"]["filtered_out_count"] = task_context_filtered

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
        for memory in task_context_memories:
            content = self._extract_content(memory)
            if content:
                exec_context["task_context_memories"].append(content)

        memory_debug["agent"]["hit_count"] = len(exec_context["agent_memories"])
        memory_debug["company"]["hit_count"] = len(exec_context["company_memories"])
        memory_debug["user_context"]["hit_count"] = len(exec_context["user_context_memories"])
        memory_debug["task_context"]["hit_count"] = len(exec_context["task_context_memories"])
        memory_debug["agent"]["hits"] = [
            self._trim_text(content) for content in exec_context["agent_memories"][:3]
        ]
        memory_debug["company"]["hits"] = [
            self._trim_text(content) for content in exec_context["company_memories"][:3]
        ]
        memory_debug["user_context"]["hits"] = [
            self._trim_text(content) for content in exec_context["user_context_memories"][:3]
        ]
        memory_debug["task_context"]["hits"] = [
            self._trim_text(content) for content in exec_context["task_context_memories"][:3]
        ]

        memory_postprocess_ms = round((time.perf_counter() - memory_postprocess_started) * 1000.0, 2)
        memory_debug["timing_ms"] = {
            "retrieval": round(memory_retrieval_ms, 2),
            "postprocess": memory_postprocess_ms,
            "total": round(memory_retrieval_ms + memory_postprocess_ms, 2),
        }

        context_debug = {
            "memory": memory_debug,
            "knowledge": knowledge_debug,
            "timing_ms": {"total": round((time.perf_counter() - context_started) * 1000.0, 2)},
        }
        return exec_context, context_debug

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
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Execute agent with given context.

        Args:
            agent: BaseAgent instance
            context: ExecutionContext with task details
            conversation_history: Optional prior user/assistant turns to prepend.

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
            execute_kwargs: Dict[str, Any] = {
                "task_description": context.task_description,
                "context": exec_context,
            }
            if conversation_history:
                execute_kwargs["conversation_history"] = conversation_history

            result = agent.execute_task(**execute_kwargs)

            # Persist one task-level memory record per task completion (success or failure).
            try:
                execution_success = bool(result.get("success"))
                execution_summary = result.get("output")
                if not execution_success:
                    execution_summary = result.get("error") or "Task execution failed"

                content = _format_agent_memory_content(
                    task=context.task_description,
                    result=str(execution_summary or ""),
                    agent_name=agent.config.name,
                )
                self.memory_interface.store_agent_memory(
                    agent_id=context.agent_id,
                    content=content,
                    user_id=context.user_id,
                    metadata={
                        "task_id": str(context.task_id) if context.task_id else None,
                        "execution_status": "success" if execution_success else "failed",
                        "source": "agent_executor_task",
                    },
                )
                logger.debug(
                    "Stored task completion memory",
                    extra={
                        "agent_id": str(context.agent_id),
                        "task_id": str(context.task_id) if context.task_id else None,
                        "execution_status": "success" if execution_success else "failed",
                    },
                )
            except Exception as mem_error:
                logger.warning(f"Failed to store task completion memory (continuing): {mem_error}")

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
