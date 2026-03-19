"""Agent execution loop and context management.

References:
- Requirements 2: Agent Framework Implementation
- Design Section 4.3: Agent Lifecycle
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from agent_framework.access_policy import resolve_memory_scopes
from agent_framework.base_agent import BaseAgent
from agent_framework.runtime_capabilities import (
    apply_authoritative_runtime_overrides,
    build_runtime_capabilities_snapshot,
)
from agent_framework.runtime_context_service import (
    RuntimeContextService,
    get_runtime_context_service,
)
from agent_framework.runtime_policy import ExecutionProfile, RuntimePolicy
from agent_framework.runtime_service import RuntimeAdapterRequest, get_unified_agent_runtime_service
from shared.config import get_config

try:
    from shared.metrics import memory_retrieval_source_quality_total
except Exception:  # pragma: no cover - metrics may be unavailable in minimal envs
    memory_retrieval_source_quality_total = None

logger = logging.getLogger(__name__)

_SESSION_INTERACTION_LOG_SOURCES = {
    "session_turn_aggregate",
    "agent_test_session",
}
_TASK_MEMORY_SOURCES = {
    "agent_executor_task",
}

_HISTORY_QUERY_CUES = {
    "上次",
    "之前",
    "刚才",
    "继续",
    "接着",
    "延续",
    "沿用",
    "参考上次",
    "还记得",
    "最早",
    "历史",
    "回顾",
    "复盘",
    "前文",
    "上文",
    "前一次",
    "上一轮",
    "继续上一个",
    "continue",
    "previous",
    "earlier",
    "history",
    "last time",
    "follow up",
}

_PREFERENCE_DOMAIN_HINTS = {
    "food": {"吃", "食物", "美食", "菜", "餐", "food", "meal", "dish", "cuisine"},
    "drink": {"喝", "饮料", "饮品", "咖啡", "茶", "酒", "drink", "beverage"},
    "hobby": {"爱好", "兴趣", "hobby", "interest"},
    "activity": {"活动", "运动", "骑行", "骑车", "露营", "旅行", "旅游", "activity", "sport"},
}


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

    def __init__(self, context_service: Optional[RuntimeContextService] = None):
        """Initialize agent executor.

        Args:
            context_service: RuntimeContextService instance
        """
        self.context_service = context_service or get_runtime_context_service()
        self._quality_metrics_enabled = True
        self._context_similarity_floor = 0.3
        self._keyword_similarity_floor = 0.4
        self._runtime_source_enabled = {
            "user_memory": True,
            "skills": True,
            "knowledge_base": True,
        }
        try:
            config = get_config()
            user_memory_cfg = config.get_section("user_memory")
            if isinstance(user_memory_cfg, dict):
                retrieval_cfg = user_memory_cfg.get("retrieval", {})
                if isinstance(retrieval_cfg, dict):
                    configured_floor = self._coerce_similarity_threshold(
                        retrieval_cfg.get("similarity_threshold")
                    )
                    if configured_floor is not None:
                        self._context_similarity_floor = configured_floor
                    configured_keyword_floor = self._coerce_similarity_threshold(
                        retrieval_cfg.get("keyword_similarity_floor")
                    )
                    if configured_keyword_floor is not None:
                        self._keyword_similarity_floor = configured_keyword_floor
                    self._keyword_similarity_floor = max(
                        self._keyword_similarity_floor,
                        self._context_similarity_floor,
                    )
                observability_cfg = user_memory_cfg.get("observability", {})
                if isinstance(observability_cfg, dict):
                    self._quality_metrics_enabled = bool(
                        observability_cfg.get("enable_quality_counters", True)
                    )
            runtime_context_cfg = config.get_section("runtime_context")
            if isinstance(runtime_context_cfg, dict):
                self._runtime_source_enabled["user_memory"] = bool(
                    runtime_context_cfg.get("enable_user_memory", True)
                )
                self._runtime_source_enabled["skills"] = bool(
                    runtime_context_cfg.get("enable_skills", True)
                )
                self._runtime_source_enabled["knowledge_base"] = bool(
                    runtime_context_cfg.get("enable_knowledge_base", True)
                )
        except Exception:
            self._quality_metrics_enabled = True
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
    def _coerce_similarity_threshold(value: Any) -> Optional[float]:
        """Normalize optional similarity threshold to [0, 1]."""
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return min(max(parsed, 0.0), 1.0)

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

    def _extract_semantic_similarity_score(self, value: Any) -> Optional[float]:
        """Extract raw semantic similarity score independent of blended business ranking."""
        metadata = self._extract_metadata(value)
        semantic_score = metadata.get("_semantic_score")
        if semantic_score is None:
            semantic_score = metadata.get("semantic_score")
        try:
            if semantic_score is not None:
                return float(semantic_score)
        except (TypeError, ValueError):
            pass
        return self._extract_similarity_score(value)

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        """Best-effort datetime parsing for memory timeline annotations."""
        if isinstance(value, datetime):
            return value

        raw = str(value or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    def _extract_timestamp(self, value: Any) -> Optional[datetime]:
        """Extract timestamp from memory object or metadata."""
        candidates = [self._extract_value(value, "timestamp")]
        metadata = self._extract_metadata(value)
        candidates.extend(
            [
                metadata.get("timestamp"),
                metadata.get("extracted_at"),
                metadata.get("created_at"),
                metadata.get("latest_turn_ts"),
            ]
        )

        for candidate in candidates:
            parsed = self._parse_datetime(candidate)
            if parsed is not None:
                return parsed
        return None

    def _memory_sort_key(self, memory: Any) -> Tuple[float, float]:
        """Sort memories by timeline first, then semantic score."""
        timestamp = self._extract_timestamp(memory)
        if timestamp is not None and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        ts_epoch = timestamp.timestamp() if timestamp is not None else -1.0
        similarity = self._extract_similarity_score(memory) or 0.0
        return ts_epoch, similarity

    def _sort_context_memories(self, memories: List[Any]) -> List[Any]:
        """Prioritize newer memories to keep prompt timeline coherent."""
        if not memories:
            return []
        return sorted(memories, key=self._memory_sort_key, reverse=True)

    def _format_memory_for_prompt(self, memory: Any) -> Optional[str]:
        """Render memory with timestamp marker so model can reason about timeline."""
        content = self._extract_content(memory)
        if not content:
            return None

        timestamp = self._extract_timestamp(memory)
        if timestamp is None:
            return content

        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        time_label = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        return f"[memory_time={time_label}] {content}"

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
            # Skip 2-grams to reduce accidental overlap on high-frequency short fragments.
            for n in (3, 4):
                for i in range(0, len(chunk) - n + 1):
                    token = chunk[i : i + n]
                    if token in zh_stop_terms or token in seen:
                        continue
                    seen.add(token)
                    terms.append(token)
                    if len(terms) >= 48:
                        return terms
        return terms

    def _query_requests_historical_context(self, query_text: str) -> bool:
        """Detect whether user explicitly asks to continue/refer historical context."""
        query = str(query_text or "").strip().lower()
        if not query:
            return False
        return any(cue in query for cue in _HISTORY_QUERY_CUES)

    @staticmethod
    def _infer_preference_domain_from_query(query_text: str) -> Optional[str]:
        query = str(query_text or "").strip().lower()
        if not query:
            return None
        for domain, hints in _PREFERENCE_DOMAIN_HINTS.items():
            if any(hint in query for hint in hints):
                return domain
        return None

    def _infer_preference_domain_from_memory(self, memory: Any) -> Optional[str]:
        metadata = self._extract_metadata(memory)
        parts: List[str] = []

        for key in ("preference_key", "category"):
            value = metadata.get(key)
            if value is not None:
                parts.append(str(value))

        facts = metadata.get("facts")
        if isinstance(facts, list):
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                for key in ("key", "category", "value"):
                    value = fact.get(key)
                    if value is not None:
                        parts.append(str(value))

        content = self._extract_content(memory)
        if content:
            parts.append(content)

        merged = " ".join(parts).lower()
        if not merged:
            return None
        for domain, hints in _PREFERENCE_DOMAIN_HINTS.items():
            if domain in merged or any(hint in merged for hint in hints):
                return domain
        return None

    def _is_interaction_log_memory(self, memory: Any) -> bool:
        """Identify session-level interaction memories."""
        metadata = self._extract_metadata(memory)
        source = str(metadata.get("source") or "").strip().lower()
        if source in _SESSION_INTERACTION_LOG_SOURCES:
            return True

        content = self._extract_content(memory)
        if not content:
            return False

        normalized = str(content).strip().lower()
        return (
            normalized.startswith("[agent:")
            and "session conversation summary" in normalized
            and "round 1 user:" in normalized
        )

    def _is_task_log_memory(self, memory: Any) -> bool:
        """Identify task-level execution memories that should never be re-injected."""
        metadata = self._extract_metadata(memory)
        source = str(metadata.get("source") or "").strip().lower()
        if source in _TASK_MEMORY_SOURCES:
            return True

        content = self._extract_content(memory)
        if not content:
            return False

        normalized = str(content).strip().lower()
        has_task_line = normalized.startswith("task:") or "\ntask:" in normalized
        has_result_line = "\nresult:" in normalized
        return has_task_line and has_result_line

    def _is_unpublished_agent_candidate_memory(self, memory: Any) -> bool:
        """Filter out agent-candidate memories until they are explicitly published."""
        metadata = self._extract_metadata(memory)
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type != "skill_candidate":
            return False
        review_status = str(metadata.get("review_status") or "").strip().lower()
        return review_status != "published"

    def _prune_interaction_log_memories(
        self,
        memories: List[Any],
        allow_interaction_logs: bool,
    ) -> Tuple[List[Any], int]:
        """Drop task-log memories unconditionally; gate session logs by intent."""
        if not memories:
            return memories, 0

        kept: List[Any] = []
        pruned = 0
        for item in memories:
            if self._is_unpublished_agent_candidate_memory(item):
                pruned += 1
                continue
            if self._is_task_log_memory(item):
                pruned += 1
                continue
            if (not allow_interaction_logs) and self._is_interaction_log_memory(item):
                pruned += 1
                continue
            kept.append(item)

        return kept, pruned

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

    def _is_structured_user_preference_memory(
        self,
        memory: Any,
        *,
        allow_inactive: bool = False,
    ) -> bool:
        """Detect compact user preference memories."""
        metadata = self._extract_metadata(memory)
        active_flag = metadata.get("is_active")
        if (not allow_inactive) and isinstance(active_flag, bool) and not active_flag:
            return False
        if (
            (not allow_inactive)
            and isinstance(active_flag, str)
            and active_flag.strip().lower()
            in {
                "false",
                "0",
                "no",
            }
        ):
            return False
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type == "user_preference":
            return True

        content = self._extract_content(memory)
        if not content:
            return False
        return str(content).strip().lower().startswith("user.preference.")

    def _is_context_memory_relevant(self, memory: Any, query_text: str) -> bool:
        """Mem0-aligned gate: rely on retrieval score threshold; avoid extra lexical/domain gating."""
        content = self._extract_content(memory)
        if not content:
            return False

        metadata = self._extract_metadata(memory)
        search_method = str(metadata.get("search_method") or "").strip().lower()
        similarity = self._extract_semantic_similarity_score(memory)
        score = float(similarity) if similarity is not None else 0.0
        history_requested = self._query_requests_historical_context(query_text)

        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type == "user_preference" and not self._is_structured_user_preference_memory(
            memory,
            allow_inactive=history_requested,
        ):
            return False

        base_floor = (
            self._keyword_similarity_floor
            if search_method == "keyword"
            else self._context_similarity_floor
        )
        return score >= base_floor

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
            is_relevant = self._is_context_memory_relevant(item, query_text)
            self._record_retrieval_quality_metric(item, accepted=is_relevant)
            if is_relevant:
                kept.append(item)
            else:
                filtered_out += 1
        return kept, filtered_out

    @staticmethod
    def _normalize_metric_label(value: Any, default: str = "unknown", max_length: int = 48) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
        if not normalized:
            return default
        return normalized[:max_length]

    def _record_retrieval_quality_metric(self, memory: Any, *, accepted: bool) -> None:
        if not self._quality_metrics_enabled or memory_retrieval_source_quality_total is None:
            return

        metadata = self._extract_metadata(memory)
        memory_type_raw = self._extract_value(memory, "memory_type") or metadata.get("memory_type")
        if hasattr(memory_type_raw, "value"):
            memory_type_raw = memory_type_raw.value
        source = str(metadata.get("search_method") or "semantic")
        quality = "accepted" if accepted else "rejected"
        try:
            memory_retrieval_source_quality_total.labels(
                memory_type=self._normalize_metric_label(memory_type_raw, default="unknown"),
                source=self._normalize_metric_label(source, default="semantic"),
                quality=quality,
            ).inc()
        except Exception:
            logger.debug("Failed to increment retrieval quality metric", exc_info=True)

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
        memory_min_similarity: Optional[float],
        knowledge_min_relevance_score: Optional[float],
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Internal context builder returning both context and debug data."""
        context_started = time.perf_counter()
        if top_k <= 0:
            top_k = 3

        # Keep memory threshold opt-in only (Mem0-aligned): use explicit override
        # from caller, otherwise let memory_system apply its own default threshold.
        memory_min_similarity = self._coerce_similarity_threshold(memory_min_similarity)

        config = getattr(agent, "config", None)
        access_level = self._normalize_access_level(getattr(config, "access_level", None))
        allowed_knowledge = self._normalize_string_list(getattr(config, "allowed_knowledge", None))

        skill_memories = []
        user_memories = []
        context_sources = resolve_memory_scopes(access_level=access_level)
        context_sources = [
            source
            for source in context_sources
            if self._runtime_source_enabled.get(source, True)
        ]
        if not self._runtime_source_enabled.get("knowledge_base", True):
            allowed_knowledge = []
        memory_debug: Dict[str, Any] = {
            "query": context.task_description,
            "top_k": top_k,
            "sources": context_sources,
            "history_context_requested": self._query_requests_historical_context(
                context.task_description
            ),
            "skills": {
                "enabled": "skills" in context_sources,
                "filter": f"agent_id={context.agent_id}, user_id={context.user_id}",
                "min_similarity": memory_min_similarity,
                "pre_filter_hit_count": 0,
                "hit_count": 0,
                "filtered_out_count": 0,
                "interaction_logs_pruned": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
            "user_memory": {
                "enabled": "user_memory" in context_sources,
                "filter": f"user_id={context.user_id}, view=user_memory",
                "min_similarity": memory_min_similarity,
                "pre_filter_hit_count": 0,
                "hit_count": 0,
                "filtered_out_count": 0,
                "interaction_logs_pruned": 0,
                "hits": [],
                "fallback_used": False,
                "fallback_hit_count": 0,
                "fallback_error": None,
                "error": None,
            },
        }
        memory_retrieval_ms = 0.0

        if "skills" in context_sources:
            scope_started = time.perf_counter()
            try:
                skill_memories = self.context_service.retrieve_skills(
                    agent_id=context.agent_id,
                    user_id=context.user_id,
                    query=context.task_description,
                    top_k=top_k,
                    min_similarity=memory_min_similarity,
                )
                logger.debug("Retrieved %s skill memories", len(skill_memories))
            except Exception as mem_error:
                memory_debug["skills"]["error"] = str(mem_error)
                logger.warning(
                    "Failed to retrieve skill memories (continuing without): %s",
                    mem_error,
                )
            finally:
                elapsed_ms = round((time.perf_counter() - scope_started) * 1000.0, 2)
                memory_debug["skills"]["latency_ms"] = elapsed_ms
                memory_retrieval_ms += elapsed_ms

        if "user_memory" in context_sources:
            scope_started = time.perf_counter()
            try:
                user_memories = self.context_service.retrieve_user_memory(
                    user_id=context.user_id,
                    query=context.task_description,
                    top_k=top_k,
                    min_similarity=memory_min_similarity,
                )
                logger.debug("Retrieved %s user memories", len(user_memories))
            except Exception as mem_error:
                memory_debug["user_memory"]["error"] = str(mem_error)
                logger.warning(
                    "Failed to retrieve user memories (continuing without): %s",
                    mem_error,
                )
            finally:
                elapsed_ms = round((time.perf_counter() - scope_started) * 1000.0, 2)
                memory_debug["user_memory"]["latency_ms"] = elapsed_ms
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
            "skills": [],
            "user_memory": [],
            "knowledge_refs": knowledge_snippets,
            "knowledge_hits": knowledge_hits,
        }

        memory_debug["skills"]["pre_filter_hit_count"] = len(skill_memories)
        memory_debug["user_memory"]["pre_filter_hit_count"] = len(user_memories)

        memory_postprocess_started = time.perf_counter()
        allow_interaction_logs = bool(memory_debug.get("history_context_requested"))
        skill_memories, skills_pruned = self._prune_interaction_log_memories(
            skill_memories, allow_interaction_logs
        )
        user_memories, user_memory_pruned = self._prune_interaction_log_memories(
            user_memories, allow_interaction_logs
        )
        memory_debug["skills"]["interaction_logs_pruned"] = skills_pruned
        memory_debug["user_memory"]["interaction_logs_pruned"] = user_memory_pruned

        skill_memories, skills_filtered = self._filter_context_memories(
            skill_memories, context.task_description
        )
        user_memories, user_memory_filtered = self._filter_context_memories(
            user_memories, context.task_description
        )

        skill_memories = self._sort_context_memories(skill_memories)
        user_memories = self._sort_context_memories(user_memories)

        memory_debug["skills"]["filtered_out_count"] = skills_filtered
        memory_debug["user_memory"]["filtered_out_count"] = user_memory_filtered

        for memory in skill_memories:
            content = self._format_memory_for_prompt(memory)
            if content:
                exec_context["skills"].append(content)
        for memory in user_memories:
            content = self._format_memory_for_prompt(memory)
            if content:
                exec_context["user_memory"].append(content)

        memory_debug["skills"]["hit_count"] = len(exec_context["skills"])
        memory_debug["user_memory"]["hit_count"] = len(exec_context["user_memory"])
        memory_debug["skills"]["hits"] = [
            self._trim_text(content) for content in exec_context["skills"][:3]
        ]
        memory_debug["user_memory"]["hits"] = [
            self._trim_text(content) for content in exec_context["user_memory"][:3]
        ]

        memory_postprocess_ms = round(
            (time.perf_counter() - memory_postprocess_started) * 1000.0, 2
        )
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
        memory_min_similarity: Optional[float] = None,
        knowledge_min_relevance_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build memory and knowledge context for an execution."""
        exec_context, _ = self._build_execution_context_internal(
            agent=agent,
            context=context,
            top_k=top_k,
            memory_min_similarity=memory_min_similarity,
            knowledge_min_relevance_score=knowledge_min_relevance_score,
        )
        return exec_context

    def build_execution_context_with_debug(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
        top_k: int = 3,
        memory_min_similarity: Optional[float] = None,
        knowledge_min_relevance_score: Optional[float] = None,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Build execution context and include retrieval debug details."""
        return self._build_execution_context_internal(
            agent=agent,
            context=context,
            top_k=top_k,
            memory_min_similarity=memory_min_similarity,
            knowledge_min_relevance_score=knowledge_min_relevance_score,
        )

    def execute(
        self,
        agent: BaseAgent,
        context: ExecutionContext,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        execution_profile: Optional[ExecutionProfile | str] = None,
        runtime_policy: Optional[RuntimePolicy] = None,
        stream_callback: Optional[callable] = None,
        session_workdir: Optional[Any] = None,
        container_id: Optional[str] = None,
        code_execution_network_access: Optional[bool] = None,
        message_content: Optional[Any] = None,
        memory_min_similarity: Optional[float] = None,
        knowledge_min_relevance_score: Optional[float] = None,
        prebuilt_execution_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute agent with given context.

        Args:
            agent: BaseAgent instance
            context: ExecutionContext with task details
            conversation_history: Optional prior user/assistant turns to prepend.
            execution_profile: Optional runtime profile controlling loop strategy.
            runtime_policy: Optional explicit runtime policy override.
            stream_callback: Optional callback for streaming output transport.
            session_workdir: Optional execution workspace root.
            container_id: Optional sandbox container id for code execution.
            code_execution_network_access: Optional network policy for code execution.
            message_content: Optional multimodal content payload.
            memory_min_similarity: Optional memory recall threshold override.
            knowledge_min_relevance_score: Optional knowledge retrieval relevance threshold override.
            prebuilt_execution_context: Optional execution context; skips retrieval if provided.

        Returns:
            Dict with execution results
        """
        logger.info(
            f"Executing agent: {agent.config.name}",
            extra={"agent_id": str(context.agent_id), "task_id": str(context.task_id)},
        )

        try:
            if prebuilt_execution_context is not None:
                exec_context = dict(prebuilt_execution_context)
            else:
                exec_context = self.build_execution_context(
                    agent=agent,
                    context=context,
                    memory_min_similarity=memory_min_similarity,
                    knowledge_min_relevance_score=knowledge_min_relevance_score,
                )

            if context.additional_context:
                exec_context.update(context.additional_context)

            runtime_capabilities = apply_authoritative_runtime_overrides(
                exec_context.get("runtime_capabilities"),
                defaults=build_runtime_capabilities_snapshot(
                    sandbox_enabled=bool(str(container_id or "").strip()),
                    sandbox_backend="docker" if container_id else "host_subprocess",
                    workspace_root_virtual="/workspace",
                    writable_roots=["/workspace"],
                    ui_mode="none",
                    network_access=(
                        True
                        if code_execution_network_access is None
                        else bool(code_execution_network_access)
                    ),
                    session_persistent=bool(session_workdir),
                    source="agent_executor",
                ),
                preserve_sandbox_backend_when_enabled=True,
            )
            exec_context["runtime_capabilities"] = runtime_capabilities

            runtime_service = get_unified_agent_runtime_service()
            result = runtime_service.execute(
                RuntimeAdapterRequest(
                    agent=agent,
                    task_description=context.task_description,
                    context=exec_context,
                    conversation_history=conversation_history,
                    execution_profile=execution_profile,
                    runtime_policy=runtime_policy,
                    stream_callback=stream_callback,
                    session_workdir=session_workdir,
                    container_id=container_id,
                    code_execution_network_access=code_execution_network_access,
                    message_content=message_content,
                )
            )

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
