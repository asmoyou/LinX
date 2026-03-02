"""Memory System implementation for multi-tiered memory management.

This module implements the Memory System with support for:
- Agent Memory (private to each agent)
- Company Memory (shared across agents)
- User Context (user-specific information accessible to all user's agents)
- Semantic similarity search
- Memory archival to MinIO

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 6: Memory System Design
"""

import hashlib
import json
import logging
import math
import re
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from pymilvus import Collection
import requests

from memory_system.collections import CollectionName
from memory_system.memory_action_planner import (
    MemoryAction,
    MemoryActionDecision,
    MemoryActionPlanner,
)
from memory_system.embedding_service import get_embedding_service
from memory_system.memory_interface import (
    MemoryItem,
    MemorySystemInterface,
    MemoryType,
    SearchQuery,
)
from memory_system.memory_repository import (
    MemoryRecordData,
    MemoryRepository,
    get_memory_repository,
)
from memory_system.milvus_connection import get_milvus_connection
from shared.config import get_config

try:
    from shared.metrics import memory_blocked_writes_total, memory_planner_actions_total
except Exception:  # pragma: no cover - metrics may be unavailable in minimal envs
    memory_blocked_writes_total = None
    memory_planner_actions_total = None

logger = logging.getLogger(__name__)


class MemoryQualitySkipError(ValueError):
    """Raised when a memory write is intentionally skipped by quality gates."""


class MemorySystem(MemorySystemInterface):
    """
    Implementation of the multi-tiered memory system.

    This class provides storage and retrieval of memories across three tiers:
    1. Agent Memory: Private memories for individual agents
    2. Company Memory: Shared memories accessible to all agents
    3. User Context: User-specific information accessible to all user's agents

    Example:
        >>> memory_system = MemorySystem()
        >>> memory = MemoryItem(
        ...     content="User prefers dark mode",
        ...     memory_type=MemoryType.USER_CONTEXT,
        ...     user_id="user123"
        ... )
        >>> memory_id = memory_system.store_memory(memory)
        >>> query = SearchQuery(
        ...     query_text="user preferences",
        ...     user_id="user123",
        ...     top_k=5
        ... )
        >>> results = memory_system.retrieve_memories(query)
    """

    _ALLOWED_FACT_PREFIXES_BY_TYPE: Dict[MemoryType, Tuple[str, ...]] = {
        MemoryType.AGENT: (
            "agent.identity.",
            "interaction.",
        ),
        MemoryType.USER_CONTEXT: ("user.",),
        MemoryType.COMPANY: (
            "company.",
            "organization.",
            "project.",
            "policy.",
            "workflow.",
            "customer.",
            "product.",
            "user.",
            "agent.",
            "interaction.",
        ),
        MemoryType.TASK_CONTEXT: (
            "task.",
            "interaction.",
            "user.",
            "agent.",
        ),
    }
    _PRE_EXTRACTED_SESSION_SIGNAL_TYPES = {
        "user_preference",
        "agent_memory_candidate",
    }

    def __init__(self):
        """Initialize the Memory System."""
        self._config = get_config()
        self._milvus = get_milvus_connection()
        self._embedding_service = get_embedding_service(scope="memory")
        self._repository = get_memory_repository()

        # Load memory configuration with retrieval-section priority and root compatibility fallback.
        memory_config = self._config.get_section("memory")
        retrieval_config = memory_config.get("retrieval", {})
        if not isinstance(retrieval_config, dict):
            retrieval_config = {}
        retrieval_milvus_cfg = retrieval_config.get("milvus", {})
        if not isinstance(retrieval_milvus_cfg, dict):
            retrieval_milvus_cfg = {}
        write_cfg = memory_config.get("write", {})
        if not isinstance(write_cfg, dict):
            write_cfg = {}
        observability_cfg = memory_config.get("observability", {})
        if not isinstance(observability_cfg, dict):
            observability_cfg = {}

        kb_config = self._config.get_section("knowledge_base")
        kb_search_cfg = kb_config.get("search", {}) if isinstance(kb_config, dict) else {}
        if not isinstance(kb_search_cfg, dict):
            kb_search_cfg = {}

        milvus_config = self._config.get_section("database.milvus")
        if not isinstance(milvus_config, dict):
            milvus_config = {}

        def _cfg_int(*candidates: object, default: int) -> int:
            for value in candidates:
                try:
                    parsed = int(value)
                except (TypeError, ValueError):
                    continue
                if parsed > 0:
                    return parsed
            return default

        def _cfg_float(
            *candidates: object, default: float, minimum: Optional[float] = None
        ) -> float:
            for value in candidates:
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    continue
                if minimum is not None and parsed < minimum:
                    continue
                return parsed
            return default

        def _cfg_text(*candidates: object) -> str:
            for value in candidates:
                text = str(value or "").strip()
                if text:
                    return text
            return ""

        self._default_top_k = _cfg_int(
            retrieval_config.get("top_k"),
            memory_config.get("default_top_k"),
            default=10,
        )
        self._recency_weight = _cfg_float(
            retrieval_config.get("recency_weight"),
            memory_config.get("recency_weight"),
            default=0.3,
            minimum=0.0,
        )
        self._similarity_weight = _cfg_float(
            retrieval_config.get("similarity_weight"),
            memory_config.get("similarity_weight"),
            default=0.7,
            minimum=0.0,
        )
        total_weight = self._recency_weight + self._similarity_weight
        if total_weight <= 0:
            self._similarity_weight = 0.7
            self._recency_weight = 0.3
        else:
            self._similarity_weight = self._similarity_weight / total_weight
            self._recency_weight = self._recency_weight / total_weight

        self._default_similarity_threshold = max(
            _cfg_float(
                retrieval_config.get("similarity_threshold"),
                memory_config.get("similarity_threshold"),
                default=0.0,
            ),
            0.0,
        )
        self._write_fail_closed_user_agent = bool(write_cfg.get("fail_closed_user_agent", True))
        self._quality_metrics_enabled = bool(observability_cfg.get("enable_quality_counters", True))

        self._enable_reranking = bool(
            retrieval_config.get(
                "enable_reranking",
                retrieval_config.get(
                    "rerank_enabled", memory_config.get("enable_reranking", False)
                ),
            )
        )
        self._rerank_top_k = _cfg_int(
            retrieval_config.get("rerank_top_k"),
            kb_search_cfg.get("rerank_top_k"),
            default=max(self._default_top_k, 20),
        )
        self._rerank_weight = min(
            max(
                _cfg_float(
                    retrieval_config.get("rerank_weight"),
                    kb_search_cfg.get("rerank_weight"),
                    default=0.75,
                ),
                0.0,
            ),
            1.0,
        )
        self._rerank_provider = _cfg_text(
            retrieval_config.get("rerank_provider"),
            kb_search_cfg.get("rerank_provider"),
        )
        self._rerank_model = _cfg_text(
            retrieval_config.get("rerank_model"),
            kb_search_cfg.get("rerank_model"),
        )
        self._rerank_timeout_seconds = _cfg_float(
            retrieval_config.get("rerank_timeout_seconds"),
            kb_search_cfg.get("rerank_timeout_seconds"),
            default=8.0,
            minimum=1.0,
        )
        self._rerank_failure_backoff_seconds = _cfg_float(
            retrieval_config.get("rerank_failure_backoff_seconds"),
            kb_search_cfg.get("rerank_failure_backoff_seconds"),
            default=30.0,
            minimum=1.0,
        )
        self._rerank_doc_max_chars = _cfg_int(
            retrieval_config.get("rerank_doc_max_chars"),
            kb_search_cfg.get("rerank_doc_max_chars"),
            default=1200,
        )
        self._rerank_fail_until = 0.0

        # Memory count/retention configuration.
        memory_types_cfg = memory_config.get("types", {})
        if not isinstance(memory_types_cfg, dict):
            memory_types_cfg = {}

        agent_memory_cfg = memory_types_cfg.get(
            "agent_memory", memory_config.get("agent_memory", {})
        )
        if not isinstance(agent_memory_cfg, dict):
            agent_memory_cfg = {}
        company_memory_cfg = memory_types_cfg.get(
            "company_memory", memory_config.get("company_memory", {})
        )
        if not isinstance(company_memory_cfg, dict):
            company_memory_cfg = {}
        user_context_cfg = memory_types_cfg.get(
            "user_context", memory_config.get("user_context", {})
        )
        if not isinstance(user_context_cfg, dict):
            user_context_cfg = {}

        self._max_items_per_agent = _cfg_int(
            agent_memory_cfg.get("max_items_per_agent"),
            default=10000,
        )
        self._max_items_company = _cfg_int(
            company_memory_cfg.get("max_items"),
            default=100000,
        )
        self._max_items_per_user = _cfg_int(
            user_context_cfg.get("max_items_per_user"),
            default=5000,
        )
        self._retention_days_by_type = {
            MemoryType.AGENT: _cfg_int(agent_memory_cfg.get("retention_days"), default=90),
            MemoryType.COMPANY: _cfg_int(company_memory_cfg.get("retention_days"), default=365),
            MemoryType.USER_CONTEXT: _cfg_int(user_context_cfg.get("retention_days"), default=365),
        }

        # Enhanced memory pipeline (fact extraction / dedup / merge / value-based eviction).
        enhanced_cfg = memory_config.get("enhanced_memory", {})
        if not isinstance(enhanced_cfg, dict):
            enhanced_cfg = {}
        dedupe_cfg = enhanced_cfg.get("dedupe", {})
        if not isinstance(dedupe_cfg, dict):
            dedupe_cfg = {}
        ranking_cfg = enhanced_cfg.get("ranking", {})
        if not isinstance(ranking_cfg, dict):
            ranking_cfg = {}
        core_cfg = enhanced_cfg.get("core_memory", {})
        if not isinstance(core_cfg, dict):
            core_cfg = {}
        fact_cfg = enhanced_cfg.get("fact_extraction", {})
        if not isinstance(fact_cfg, dict):
            fact_cfg = {}
        action_planner_cfg = enhanced_cfg.get("action_planner", {})
        if not isinstance(action_planner_cfg, dict):
            action_planner_cfg = {}

        self._enhanced_memory_enabled = bool(enhanced_cfg.get("enabled", True))
        self._exact_dedupe_window_minutes = _cfg_int(
            dedupe_cfg.get("exact_window_minutes"),
            default=4320,
        )
        self._semantic_dedupe_enabled = bool(dedupe_cfg.get("semantic_enabled", True))
        self._semantic_dedupe_threshold = min(
            max(_cfg_float(dedupe_cfg.get("semantic_similarity_threshold"), default=0.86), 0.0),
            1.0,
        )
        self._semantic_merge_min_overlap = min(
            max(_cfg_float(dedupe_cfg.get("min_fact_overlap"), default=0.35), 0.0),
            1.0,
        )
        self._semantic_dedupe_candidate_limit = _cfg_int(
            dedupe_cfg.get("candidate_limit"),
            default=8,
        )
        self._dedupe_candidate_scan_limit = _cfg_int(
            dedupe_cfg.get("db_candidate_limit"),
            default=50,
        )
        self._max_fact_conflict_history = _cfg_int(
            dedupe_cfg.get("max_conflict_history"),
            default=5,
        )

        self._importance_weight = _cfg_float(
            ranking_cfg.get("importance_weight"),
            default=0.15,
            minimum=0.0,
        )
        self._tier_weight = _cfg_float(
            ranking_cfg.get("tier_weight"),
            default=0.10,
            minimum=0.0,
        )
        self._mention_weight = _cfg_float(
            ranking_cfg.get("mention_weight"),
            default=0.08,
            minimum=0.0,
        )
        self._recency_half_life_days = max(
            _cfg_float(ranking_cfg.get("recency_half_life_days"), default=14.0, minimum=0.1),
            0.1,
        )
        self._score_weight_total = max(
            self._similarity_weight
            + self._recency_weight
            + self._importance_weight
            + self._tier_weight
            + self._mention_weight,
            1e-6,
        )

        self._core_protection_enabled = bool(core_cfg.get("protect_core", True))
        self._core_importance_threshold = min(
            max(_cfg_float(core_cfg.get("importance_threshold"), default=0.72), 0.0),
            1.0,
        )
        self._retention_cleanup_interval_seconds = _cfg_float(
            enhanced_cfg.get("retention_cleanup_interval_seconds"),
            default=300.0,
            minimum=1.0,
        )
        self._last_retention_cleanup_at = 0.0

        llm_cfg = {}
        try:
            llm_cfg = self._config.get_section("llm")
        except Exception:
            llm_cfg = {}
        if not isinstance(llm_cfg, dict):
            llm_cfg = {}

        self._fact_extraction_enabled = bool(fact_cfg.get("enabled", True))
        self._fact_extraction_model_enabled = bool(fact_cfg.get("model_enabled", True))
        self._fact_extraction_provider = _cfg_text(
            fact_cfg.get("provider"),
            llm_cfg.get("default_provider"),
        )
        self._fact_extraction_model = _cfg_text(fact_cfg.get("model"))
        self._fact_extraction_timeout_seconds = _cfg_float(
            fact_cfg.get("timeout_seconds"),
            default=4.0,
            minimum=0.5,
        )
        self._fact_extraction_max_facts = _cfg_int(
            fact_cfg.get("max_facts"),
            default=8,
        )
        self._fact_extraction_failure_backoff_seconds = _cfg_float(
            fact_cfg.get("failure_backoff_seconds"),
            default=60.0,
            minimum=1.0,
        )
        self._fact_extraction_fail_closed_auto_generated = bool(
            fact_cfg.get("fail_closed_auto_generated", True)
        )
        raw_fail_closed_types = fact_cfg.get(
            "fail_closed_types",
            ["agent", "user_context"],
        )
        fail_closed_type_values: set[str] = set()
        if isinstance(raw_fail_closed_types, list):
            for item in raw_fail_closed_types:
                normalized = str(item or "").strip().lower()
                if normalized:
                    fail_closed_type_values.add(normalized)
        self._fact_extraction_fail_closed_types = {
            memory_type
            for memory_type in MemoryType
            if memory_type.value in fail_closed_type_values
        }
        if not self._write_fail_closed_user_agent:
            self._fact_extraction_fail_closed_types = {
                memory_type
                for memory_type in self._fact_extraction_fail_closed_types
                if memory_type not in {MemoryType.AGENT, MemoryType.USER_CONTEXT}
            }
        self._fact_extract_fail_until = 0.0
        self._action_planner_enabled = bool(action_planner_cfg.get("enabled", True))
        self._action_planner_strict_fail_closed = bool(
            action_planner_cfg.get("strict_fail_closed", True)
        )
        self._action_planner_allow_explicit_delete = bool(
            action_planner_cfg.get("allow_explicit_delete", True)
        )
        self._action_planner = MemoryActionPlanner(
            allow_delete=self._action_planner_allow_explicit_delete
        )

        # Heuristic quality guards for noisy auto-generated conversational memories.
        self._low_value_min_chars = _cfg_int(
            enhanced_cfg.get("low_value_min_chars"),
            default=12,
        )

        self._collection_retry_attempts = _cfg_int(
            memory_config.get("collection_retry_attempts"),
            default=3,
        )
        self._collection_retry_delay_seconds = _cfg_float(
            memory_config.get("collection_retry_delay_seconds"),
            default=0.35,
            minimum=0.0,
        )
        self._search_timeout_seconds = _cfg_float(
            memory_config.get("search_timeout_seconds"),
            default=2.0,
            minimum=0.1,
        )
        self._delete_timeout_seconds = _cfg_float(
            memory_config.get("delete_timeout_seconds"),
            default=2.0,
            minimum=0.1,
        )
        self._search_metric_type = (
            _cfg_text(
                retrieval_milvus_cfg.get("metric_type"),
                retrieval_config.get("milvus_metric_type"),
                milvus_config.get("metric_type"),
            )
            or "L2"
        )
        self._search_nprobe = _cfg_int(
            retrieval_milvus_cfg.get("nprobe"),
            retrieval_config.get("milvus_nprobe"),
            milvus_config.get("nprobe"),
            default=10,
        )

        logger.info(
            "Memory System initialized",
            extra={
                "default_top_k": self._default_top_k,
                "similarity_weight": self._similarity_weight,
                "recency_weight": self._recency_weight,
                "similarity_threshold": self._default_similarity_threshold,
                "rerank_enabled": self._enable_reranking,
                "rerank_provider": self._rerank_provider,
                "rerank_model": self._rerank_model,
                "metric_type": self._search_metric_type,
                "nprobe": self._search_nprobe,
                "max_items_per_agent": self._max_items_per_agent,
                "max_items_company": self._max_items_company,
                "max_items_per_user": self._max_items_per_user,
                "enhanced_memory_enabled": self._enhanced_memory_enabled,
                "semantic_dedupe_enabled": self._semantic_dedupe_enabled,
                "semantic_dedupe_threshold": self._semantic_dedupe_threshold,
                "core_importance_threshold": self._core_importance_threshold,
                "fact_extraction_model_enabled": self._fact_extraction_model_enabled,
                "fact_extraction_fail_closed_auto_generated": self._fact_extraction_fail_closed_auto_generated,
                "action_planner_enabled": self._action_planner_enabled,
                "action_planner_strict_fail_closed": self._action_planner_strict_fail_closed,
                "action_planner_allow_explicit_delete": self._action_planner_allow_explicit_delete,
            },
        )

    @staticmethod
    def _clamp_score(raw: object, default: float = 0.0) -> float:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            value = float(default)
        return max(0.0, min(1.0, value))

    @staticmethod
    def _normalize_whitespace(text: object) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip())

    @staticmethod
    def _truncate_text(text: object, max_chars: int = 220) -> str:
        normalized = MemorySystem._normalize_whitespace(text)
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3].rstrip() + "..."

    def _normalize_content_for_hash(self, content: object) -> str:
        return self._normalize_whitespace(content).lower()

    def _compute_content_hash(self, content: object) -> str:
        normalized = self._normalize_content_for_hash(content)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _is_auto_generated_memory(self, memory: MemoryItem) -> bool:
        metadata = memory.metadata or {}
        if bool(metadata.get("auto_generated")):
            return True
        source = str(metadata.get("source") or "").strip().lower()
        if source in {"conversation", "agent_test_stream", "agent_executor"}:
            return True

        content = str(memory.content or "")
        return (
            ("Task:" in content and "Result:" in content)
            or "User discussed:" in content
            or "Topic:" in content
        )

    @staticmethod
    def _sanitize_fact_key(raw_key: object) -> str:
        key = str(raw_key or "").strip().lower()
        key = re.sub(r"[^a-z0-9_.-]+", "_", key)
        key = key.strip("_.-")
        if not key:
            return ""
        if "." not in key:
            key = f"memory.{key}"
        return key[:120]

    def _normalize_fact(
        self,
        raw_fact: Dict[str, Any],
        *,
        source: str,
    ) -> Optional[Dict[str, Any]]:
        key = self._sanitize_fact_key(raw_fact.get("key"))
        value = self._truncate_text(raw_fact.get("value"), max_chars=260)
        if not key or not value:
            return None

        fact = {
            "key": key,
            "value": value,
            "category": self._truncate_text(raw_fact.get("category") or "general", max_chars=40),
            "confidence": round(self._clamp_score(raw_fact.get("confidence"), default=0.75), 4),
            "importance": round(self._clamp_score(raw_fact.get("importance"), default=0.5), 4),
            "source": self._truncate_text(source, max_chars=32),
        }
        return fact

    def _is_pre_extracted_session_memory(self, memory: MemoryItem) -> bool:
        metadata = memory.metadata or {}
        if bool(metadata.get("skip_secondary_fact_extraction")):
            return True
        signal_type = str(metadata.get("signal_type") or "").strip().lower()
        if signal_type in self._PRE_EXTRACTED_SESSION_SIGNAL_TYPES:
            return True
        source = str(metadata.get("source") or "").strip().lower()
        return source in {
            "agent_test_preference_extractor",
            "agent_test_agent_candidate_extractor",
        }

    def _extract_structured_line_facts(self, memory: MemoryItem) -> List[Dict[str, Any]]:
        facts: List[Dict[str, Any]] = []
        for raw_line in str(memory.content or "").splitlines():
            line = str(raw_line or "").strip()
            if not line or "=" not in line:
                continue
            left, right = line.split("=", 1)
            key = self._sanitize_fact_key(left)
            value = self._truncate_text(right, max_chars=260)
            if not key or not value:
                continue
            normalized = self._normalize_fact(
                {
                    "key": key,
                    "value": value,
                    "category": key.split(".", 1)[0],
                    "importance": 0.72,
                    "confidence": 0.86,
                },
                source="session_seed",
            )
            if normalized:
                facts.append(normalized)
        return facts

    def _is_fact_allowed_for_memory_type(self, memory_type: MemoryType, fact_key: str) -> bool:
        key = str(fact_key or "").strip().lower()
        if not key:
            return False
        prefixes = self._ALLOWED_FACT_PREFIXES_BY_TYPE.get(memory_type)
        if not prefixes:
            return True
        return any(key.startswith(prefix) for prefix in prefixes)

    def _filter_facts_for_memory_type(
        self, memory_type: MemoryType, facts: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        filtered: List[Dict[str, Any]] = []
        for fact in facts:
            if not isinstance(fact, dict):
                continue
            key = str(fact.get("key") or "").strip().lower()
            if self._is_fact_allowed_for_memory_type(memory_type, key):
                filtered.append(fact)
        return filtered

    def _normalize_text_for_evidence_match(self, text: object) -> str:
        normalized = self._normalize_whitespace(text).lower()
        return re.sub(r"[\s\W_]+", "", normalized, flags=re.UNICODE)

    def _is_fact_value_grounded_in_content(self, content: str, value: object) -> bool:
        text = str(content or "")
        fact_value = str(value or "").strip()
        if not text or not fact_value:
            return False

        if fact_value in text:
            return True

        lowered_text = text.lower()
        lowered_value = fact_value.lower()
        if lowered_value in lowered_text:
            return True

        normalized_text = self._normalize_text_for_evidence_match(text)
        normalized_value = self._normalize_text_for_evidence_match(fact_value)
        if len(normalized_value) < 2:
            return False

        return normalized_value in normalized_text

    def _extract_heuristic_facts(self, memory: MemoryItem) -> List[Dict[str, Any]]:
        """Extract deterministic structured facts from known memory formats."""
        content = str(memory.content or "")
        lines = [line.strip() for line in content.splitlines() if line and line.strip()]
        facts: List[Dict[str, Any]] = []

        def _append_fact(
            key: str,
            value: object,
            *,
            category: str,
            importance: float,
            confidence: float = 0.85,
        ) -> None:
            fact = self._normalize_fact(
                {
                    "key": key,
                    "value": value,
                    "category": category,
                    "importance": importance,
                    "confidence": confidence,
                },
                source="heuristic",
            )
            if fact:
                facts.append(fact)

        for line in lines:
            if line.startswith("[Agent:") and line.endswith("]"):
                name = line.replace("[Agent:", "", 1).rstrip("]").strip()
                if name:
                    _append_fact(
                        "agent.identity.name",
                        name,
                        category="agent",
                        importance=0.35,
                        confidence=0.9,
                    )
            elif line.lower().startswith("task:"):
                task_text = line.split(":", 1)[1].strip()
                if task_text:
                    _append_fact(
                        "interaction.task.latest",
                        task_text,
                        category="task",
                        importance=0.62,
                        confidence=0.86,
                    )
            elif line.lower().startswith("result:"):
                result_text = line.split(":", 1)[1].strip()
                if result_text:
                    # Keep concise interaction outcome; avoid storing long answer details.
                    result_summary = re.split(r"[。！？.!?]", result_text, maxsplit=1)[0].strip()
                    if not result_summary:
                        result_summary = result_text
                    _append_fact(
                        "interaction.result.summary",
                        self._truncate_text(result_summary, max_chars=140),
                        category="result",
                        importance=0.45,
                        confidence=0.8,
                    )
            elif line.lower().startswith("user discussed:"):
                discussed_text = line.split(":", 1)[1].strip()
                if discussed_text:
                    _append_fact(
                        "user.topic.latest",
                        discussed_text,
                        category="user_context",
                        importance=0.68,
                        confidence=0.86,
                    )
            elif line.lower().startswith("topic:"):
                topic_text = line.split(":", 1)[1].strip()
                if topic_text:
                    _append_fact(
                        "user.topic.summary",
                        topic_text,
                        category="user_context",
                        importance=0.6,
                        confidence=0.84,
                    )

        # User preference/profile extraction should only run on user-context memories.
        if memory.memory_type != MemoryType.USER_CONTEXT:
            return facts

        lowered = content.lower()
        for match in re.finditer(
            r"\b(?:i|user)\s+(?:prefer|preferred|like|likes|love|dislike|hate)\s+([^\n\.,;!?]{2,80})",
            lowered,
        ):
            raw_value = match.group(1).strip()
            suffix = self._sanitize_fact_key(raw_value.replace(" ", "_"))[:24] or "general"
            _append_fact(
                f"user.preference.{suffix}",
                raw_value,
                category="user_preference",
                importance=0.88,
                confidence=0.84,
            )

        for match in re.finditer(r"我(?:更)?(?:喜欢|偏好|不喜欢|讨厌)([^。！？\n]{1,40})", content):
            raw_value = match.group(1).strip()
            suffix = self._sanitize_fact_key(raw_value)[:24] or "general"
            _append_fact(
                f"user.preference.{suffix}",
                raw_value,
                category="user_preference",
                importance=0.9,
                confidence=0.82,
            )

        name_patterns = [
            r"\bmy name is\s+([a-z0-9_ \-]{2,40})",
            r"\bi am\s+([a-z0-9_ \-]{2,40})",
            r"我是([^。！？\n]{1,20})",
        ]
        for pattern in name_patterns:
            match = re.search(pattern, content, flags=re.IGNORECASE)
            if not match:
                continue
            identity = match.group(1).strip()
            if not identity:
                continue
            _append_fact(
                "user.profile.identity",
                identity,
                category="user_profile",
                importance=0.82,
                confidence=0.8,
            )
            break

        return facts

    def _resolve_fact_extraction_model(self) -> str:
        if self._fact_extraction_model:
            return self._fact_extraction_model

        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(self._fact_extraction_provider)
        raw_models = provider_cfg.get("models")
        model_candidates: List[str] = []
        if isinstance(raw_models, dict):
            model_candidates.extend(
                [str(value).strip() for value in raw_models.values() if str(value).strip()]
            )
        elif isinstance(raw_models, list):
            model_candidates.extend(
                [str(value).strip() for value in raw_models if str(value).strip()]
            )
        elif isinstance(raw_models, str) and raw_models.strip():
            model_candidates.append(raw_models.strip())

        preference_markers = ("instruct", "chat", "qwen", "gpt", "llama", "claude")
        for candidate in model_candidates:
            lowered = candidate.lower()
            if any(marker in lowered for marker in preference_markers):
                return candidate

        return model_candidates[0] if model_candidates else ""

    def _extract_json_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        stripped = str(text or "").strip()
        if not stripped:
            return None

        candidates = [stripped]
        fenced_matches = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, flags=re.DOTALL)
        candidates.extend(fenced_matches)

        brace_match = re.search(r"(\{.*\})", stripped, flags=re.DOTALL)
        if brace_match:
            candidates.append(brace_match.group(1))

        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed

        return None

    def _extract_model_facts(self, memory: MemoryItem) -> List[Dict[str, Any]]:
        if not self._fact_extraction_model_enabled or not self._fact_extraction_provider:
            return []
        now = time.monotonic()
        if now < self._fact_extract_fail_until:
            return []

        model = self._resolve_fact_extraction_model()
        if not model:
            return []

        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(self._fact_extraction_provider)
        base_url = str(provider_cfg.get("base_url") or "").strip()
        if not base_url:
            return []

        headers = {"Content-Type": "application/json"}
        api_key = provider_cfg.get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        max_facts = max(int(self._fact_extraction_max_facts), 1)
        if memory.memory_type == MemoryType.AGENT:
            system_prompt = (
                "Extract durable AGENT memory facts. Return ONLY JSON: "
                '{"facts":[{"key":"domain.field","value":"...",'
                '"category":"...","confidence":0.0,"importance":0.0}]}. '
                "Allowed key prefixes: agent.identity.*, interaction.*. "
                "Prefer only: agent.identity.*, interaction.task.latest, "
                "interaction.result.summary, interaction.note.*. "
                "Do NOT extract task-domain knowledge from assistant answers "
                "(for example implementation details, procedural instructions, or specs). "
                "Ignore temporary chatter and repeated statements."
            )
        elif memory.memory_type == MemoryType.USER_CONTEXT:
            system_prompt = (
                "Extract durable USER PROFILE facts. Return ONLY JSON: "
                '{"facts":[{"key":"domain.field","value":"...",'
                '"category":"...","confidence":0.0,"importance":0.0}]}. '
                "Allowed key prefix: user.*. "
                "Only keep facts explicitly stated in user text (or close paraphrases). "
                "Do NOT infer personality, frequency, expertise, motivation, "
                "or expectations unless explicitly written by user. "
                "Ignore assistant self-introduction and one-off procedural details."
            )
        else:
            system_prompt = (
                "Extract durable memory facts from the text. Return ONLY JSON: "
                '{"facts":[{"key":"domain.field","value":"...",'
                '"category":"...","confidence":0.0,"importance":0.0}]}. '
                "Ignore temporary chatter, acknowledgements, and repeated statements."
            )
        user_prompt = (
            f"memory_type={memory.memory_type.value}\n"
            f"content:\n{memory.content}\n\n"
            f"max_facts={max_facts}"
        )
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "max_tokens": 500,
        }

        urls_to_try = [
            f"{base_url.rstrip('/')}/v1/chat/completions",
            f"{base_url.rstrip('/')}/chat/completions",
        ]
        last_error = ""
        for url in urls_to_try:
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=max(float(self._fact_extraction_timeout_seconds), 0.5),
                )
                if response.status_code != 200:
                    last_error = f"{url} -> HTTP {response.status_code}: {response.text[:140]}"
                    continue
                data = response.json()
                if isinstance(data, dict) and isinstance(data.get("output"), str):
                    wrapped = self._extract_json_from_text(data.get("output"))
                    if wrapped:
                        data = wrapped

                content_text = ""
                if isinstance(data, dict):
                    choices = data.get("choices")
                    if isinstance(choices, list) and choices:
                        message = (
                            choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                        )
                        content_text = str(
                            message.get("content") or message.get("reasoning_content") or ""
                        )
                    elif isinstance(data.get("output"), str):
                        content_text = data.get("output")

                parsed = self._extract_json_from_text(content_text) if content_text else None
                if not parsed and isinstance(data, dict):
                    parsed = data if isinstance(data.get("facts"), list) else None
                if not parsed:
                    last_error = f"{url} -> model output missing JSON facts"
                    continue

                raw_facts = parsed.get("facts")
                if not isinstance(raw_facts, list):
                    last_error = f"{url} -> no facts array"
                    continue

                normalized: List[Dict[str, Any]] = []
                for raw_fact in raw_facts[:max_facts]:
                    if not isinstance(raw_fact, dict):
                        continue
                    fact = self._normalize_fact(raw_fact, source="model")
                    if fact:
                        normalized.append(fact)

                if memory.memory_type in {MemoryType.AGENT, MemoryType.USER_CONTEXT}:
                    normalized = [
                        fact
                        for fact in normalized
                        if self._is_fact_value_grounded_in_content(
                            str(memory.content or ""),
                            fact.get("value"),
                        )
                    ]

                if normalized:
                    self._fact_extract_fail_until = 0.0
                return normalized
            except Exception as exc:
                last_error = f"{url} -> {exc}"

        if last_error:
            logger.debug(
                "Fact extraction model call failed",
                extra={
                    "provider": self._fact_extraction_provider,
                    "model": model,
                    "error": last_error,
                },
            )
            self._fact_extract_fail_until = now + max(
                self._fact_extraction_failure_backoff_seconds, 1.0
            )

        return []

    def _merge_fact_lists(
        self,
        existing_facts: List[Dict[str, Any]],
        incoming_facts: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Merge facts by key; conflicting values are overwritten by incoming values."""
        merged: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        conflicts: List[Dict[str, Any]] = []

        for existing in existing_facts:
            normalized = self._normalize_fact(existing, source=existing.get("source") or "existing")
            if not normalized:
                continue
            key = normalized["key"]
            if key not in order:
                order.append(key)
            merged[key] = normalized

        for incoming in incoming_facts:
            normalized = self._normalize_fact(incoming, source=incoming.get("source") or "incoming")
            if not normalized:
                continue
            key = normalized["key"]
            previous = merged.get(key)
            if previous and previous.get("value") != normalized.get("value"):
                conflicts.append(
                    {
                        "key": key,
                        "old_value": previous.get("value"),
                        "new_value": normalized.get("value"),
                        "resolved_at": datetime.utcnow().isoformat(),
                    }
                )
            merged[key] = normalized
            if key not in order:
                order.append(key)

        if len(conflicts) > self._max_fact_conflict_history:
            conflicts = conflicts[-self._max_fact_conflict_history :]

        merged_facts = [merged[key] for key in order if key in merged]
        return merged_facts, conflicts

    def _collect_facts(
        self, memory: MemoryItem
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        metadata = dict(memory.metadata or {})
        seed_facts = metadata.get("facts", [])
        if not isinstance(seed_facts, list):
            seed_facts = []

        normalized_seed: List[Dict[str, Any]] = []
        for raw_seed in seed_facts:
            if not isinstance(raw_seed, dict):
                continue
            fact = self._normalize_fact(raw_seed, source=raw_seed.get("source") or "seed")
            if fact:
                normalized_seed.append(fact)

        if self._is_pre_extracted_session_memory(memory):
            seeded_facts = normalized_seed or self._extract_structured_line_facts(memory)
            return self._filter_facts_for_memory_type(memory.memory_type, seeded_facts), []

        heuristic_facts = self._extract_heuristic_facts(memory)
        model_facts = self._extract_model_facts(memory) if self._fact_extraction_enabled else []
        prefer_model_only = bool(
            self._fact_extraction_enabled
            and self._fact_extraction_model_enabled
            and self._fact_extraction_provider
            and memory.memory_type in {MemoryType.AGENT, MemoryType.USER_CONTEXT}
        )
        fail_closed_on_empty_facts = self._should_fail_closed_on_empty_facts(
            memory,
            prefer_model_only=prefer_model_only,
        )
        incoming_facts = model_facts if prefer_model_only else (heuristic_facts + model_facts)
        merged_facts, conflicts = self._merge_fact_lists(
            normalized_seed,
            incoming_facts,
        )
        merged_facts = self._filter_facts_for_memory_type(memory.memory_type, merged_facts)

        fallback_key_map = {
            MemoryType.AGENT: "interaction.note.latest",
            MemoryType.USER_CONTEXT: "user.topic.latest",
            MemoryType.COMPANY: "company.note.latest",
            MemoryType.TASK_CONTEXT: "task.note.latest",
        }
        fallback_key = fallback_key_map.get(
            memory.memory_type, f"{memory.memory_type.value}.note.latest"
        )

        if not merged_facts and prefer_model_only:
            if fail_closed_on_empty_facts:
                return [], conflicts
            # Non-strict fallback: model-first, then deterministic heuristic extraction.
            heuristic_fallback = self._filter_facts_for_memory_type(
                memory.memory_type,
                heuristic_facts,
            )
            if heuristic_fallback:
                return heuristic_fallback, conflicts
            return [], conflicts

        if not merged_facts:
            if fail_closed_on_empty_facts:
                return [], conflicts
            fallback_fact = self._normalize_fact(
                {
                    "key": fallback_key,
                    "value": self._truncate_text(memory.content, max_chars=260),
                    "category": memory.memory_type.value,
                    "importance": 0.28,
                    "confidence": 0.5,
                },
                source="fallback",
            )
            if fallback_fact:
                merged_facts = [fallback_fact]

        return merged_facts, conflicts

    def _should_fail_closed_on_empty_facts(
        self,
        memory: MemoryItem,
        *,
        prefer_model_only: bool,
    ) -> bool:
        """Determine whether empty extraction should skip write for this memory."""
        metadata = dict(memory.metadata or {})

        explicit_override = metadata.get("fail_closed_extraction")
        if explicit_override is not None:
            return bool(explicit_override)

        if bool(metadata.get("allow_low_quality_fallback")):
            return False

        if memory.memory_type not in self._fact_extraction_fail_closed_types:
            return False

        if self._is_pre_extracted_session_memory(memory):
            return False

        if not self._fact_extraction_fail_closed_auto_generated:
            return prefer_model_only

        return self._is_auto_generated_memory(memory)

    def _build_structured_content(self, facts: List[Dict[str, Any]]) -> str:
        lines = []
        for fact in facts:
            key = str(fact.get("key") or "").strip()
            value = str(fact.get("value") or "").strip()
            if key and value:
                lines.append(f"{key} = {value}")
        return "\n".join(lines[: max(int(self._fact_extraction_max_facts), 1)])

    def _derive_importance_score(
        self,
        memory: MemoryItem,
        facts: List[Dict[str, Any]],
        *,
        auto_generated: bool,
    ) -> float:
        metadata = dict(memory.metadata or {})
        explicit_importance = metadata.get("importance_score")
        if explicit_importance is not None:
            return self._clamp_score(explicit_importance, default=0.5)

        if facts:
            mean_importance = sum(float(f.get("importance") or 0.0) for f in facts) / max(
                len(facts), 1
            )
        else:
            mean_importance = 0.35

        if memory.memory_type == MemoryType.USER_CONTEXT:
            mean_importance += 0.08
        if any(str(f.get("key") or "").startswith("user.preference.") for f in facts):
            mean_importance += 0.12
        if any(str(f.get("key") or "").startswith("user.profile.") for f in facts):
            mean_importance += 0.1
        if (
            auto_generated
            and len(self._normalize_whitespace(memory.content)) <= self._low_value_min_chars
        ):
            mean_importance -= 0.25
        elif auto_generated:
            mean_importance -= 0.05

        return self._clamp_score(mean_importance, default=0.5)

    def _derive_importance_level(self, score: float) -> str:
        if score >= 0.75:
            return "high"
        if score >= 0.45:
            return "medium"
        return "low"

    def _derive_memory_tier(
        self,
        metadata: Dict[str, Any],
        facts: List[Dict[str, Any]],
        importance_score: float,
    ) -> str:
        explicit_tier = str(metadata.get("memory_tier") or "").strip().lower()
        if explicit_tier in {"core", "archival"}:
            return explicit_tier
        if importance_score >= self._core_importance_threshold:
            return "core"
        if any(str(f.get("key") or "").startswith("user.preference.") for f in facts):
            return "core"
        return "archival"

    def _prepare_memory_for_storage(self, memory: MemoryItem) -> MemoryItem:
        """Normalize incoming memory into dedupe-friendly, fact-based representation."""
        metadata = dict(memory.metadata or {})
        auto_generated = self._is_auto_generated_memory(memory)
        facts, new_conflicts = self._collect_facts(memory)
        if (
            not facts
            and memory.memory_type in self._fact_extraction_fail_closed_types
            and self._should_fail_closed_on_empty_facts(memory, prefer_model_only=True)
        ):
            raise MemoryQualitySkipError(
                f"No reliable facts extracted for {memory.memory_type.value}; skipping write by quality gate."
            )
        importance_score = self._derive_importance_score(
            memory, facts, auto_generated=auto_generated
        )
        tier = self._derive_memory_tier(metadata, facts, importance_score)

        structured_content = self._build_structured_content(facts)
        use_structured_content = (
            auto_generated
            or memory.memory_type == MemoryType.USER_CONTEXT
            or bool(metadata.get("force_structured_memory"))
        )

        content = (
            structured_content
            if use_structured_content
            else self._normalize_whitespace(memory.content)
        )
        if not content:
            content = structured_content or self._normalize_whitespace(memory.content)
        content_hash = self._compute_content_hash(content)

        mention_count = metadata.get("mention_count", 1)
        try:
            mention_count = max(int(mention_count), 1)
        except (TypeError, ValueError):
            mention_count = 1

        existing_conflicts = metadata.get("conflict_history")
        if not isinstance(existing_conflicts, list):
            existing_conflicts = []
        combined_conflicts = existing_conflicts + new_conflicts
        if len(combined_conflicts) > self._max_fact_conflict_history:
            combined_conflicts = combined_conflicts[-self._max_fact_conflict_history :]

        metadata.update(
            {
                "facts": facts,
                "fact_keys": [fact.get("key") for fact in facts if fact.get("key")],
                "fact_version": "v2",
                "content_hash": content_hash,
                "importance_score": round(importance_score, 4),
                "importance_level": self._derive_importance_level(importance_score),
                "memory_tier": tier,
                "mention_count": mention_count,
                "last_seen_at": datetime.utcnow().isoformat(),
                "auto_generated": bool(auto_generated),
            }
        )
        if combined_conflicts:
            metadata["conflict_history"] = combined_conflicts

        if memory.user_id and "user_id" not in metadata:
            metadata["user_id"] = memory.user_id
        if memory.task_id and "task_id" not in metadata:
            metadata["task_id"] = memory.task_id

        memory.content = content
        memory.metadata = metadata
        if not memory.embedding:
            memory.embedding = self._embedding_service.generate_embedding(memory.content)

        return memory

    def _scope_filters_for_memory(self, memory: MemoryItem) -> Dict[str, Optional[str]]:
        return {
            "memory_type": memory.memory_type,
            "agent_id": memory.agent_id if memory.memory_type == MemoryType.AGENT else None,
            "user_id": memory.user_id,
        }

    def _build_scope_filter_expression_for_memory(self, memory: MemoryItem) -> Optional[str]:
        if memory.memory_type == MemoryType.AGENT:
            filters = [f'agent_id == "{memory.agent_id}"']
            if memory.user_id:
                filters.append(f'metadata["user_id"] == "{memory.user_id}"')
            return " && ".join(filters)

        filters = []
        if memory.user_id:
            filters.append(f'user_id == "{memory.user_id}"')
        filters.append(f'memory_type == "{memory.memory_type.value}"')
        if memory.task_id:
            filters.append(f'metadata["task_id"] == "{memory.task_id}"')
        return " && ".join(filters)

    def _fact_overlap_ratio(
        self,
        incoming_metadata: Dict[str, Any],
        existing_metadata: Dict[str, Any],
    ) -> float:
        incoming_keys = {
            str(key).strip()
            for key in (incoming_metadata.get("fact_keys") or [])
            if str(key).strip()
        }
        existing_keys = {
            str(key).strip()
            for key in (existing_metadata.get("fact_keys") or [])
            if str(key).strip()
        }
        if incoming_keys and existing_keys:
            shared = len(incoming_keys.intersection(existing_keys))
            total = len(incoming_keys.union(existing_keys))
            return shared / total if total else 0.0

        incoming_tokens = set(
            self._normalize_content_for_hash(incoming_metadata.get("content_hash")).split("_")
        )
        existing_tokens = set(
            self._normalize_content_for_hash(existing_metadata.get("content_hash")).split("_")
        )
        if incoming_tokens and existing_tokens:
            shared = len(incoming_tokens.intersection(existing_tokens))
            total = len(incoming_tokens.union(existing_tokens))
            return shared / total if total else 0.0

        return 0.0

    def _find_exact_duplicate(
        self, memory: MemoryItem
    ) -> Optional[Tuple[MemoryRecordData, float, str]]:
        metadata = dict(memory.metadata or {})
        content_hash = str(metadata.get("content_hash") or "").strip()
        if not content_hash:
            return None

        scope = self._scope_filters_for_memory(memory)
        existing = self._repository.find_recent_by_content_hash(
            memory_type=scope["memory_type"],
            content_hash=content_hash,
            agent_id=scope["agent_id"],
            user_id=scope["user_id"],
            within_minutes=self._exact_dedupe_window_minutes,
        )
        if not existing:
            return None
        return existing, 1.0, "exact_hash"

    def _find_semantic_duplicate(
        self, memory: MemoryItem
    ) -> Optional[Tuple[MemoryRecordData, float, str]]:
        if not self._semantic_dedupe_enabled:
            return None
        if not memory.embedding:
            return None

        if memory.memory_type == MemoryType.AGENT:
            collection_name = CollectionName.AGENT_MEMORIES
            output_fields = ["agent_id", "content", "timestamp", "metadata"]
        else:
            collection_name = CollectionName.COMPANY_MEMORIES
            output_fields = ["user_id", "content", "memory_type", "timestamp", "metadata"]

        collection = self._milvus.get_collection(collection_name)
        search_params = {
            "metric_type": self._search_metric_type,
            "params": {"nprobe": self._search_nprobe},
        }
        filter_expr = self._build_scope_filter_expression_for_memory(memory)

        results = self._search_collection_with_retry(
            collection=collection,
            collection_name=collection_name,
            query_embedding=memory.embedding,
            search_params=search_params,
            limit=max(int(self._semantic_dedupe_candidate_limit), 1),
            filter_expr=filter_expr,
            output_fields=output_fields,
        )
        best_candidate = None
        best_similarity = 0.0
        incoming_meta = dict(memory.metadata or {})
        incoming_hash = str(incoming_meta.get("content_hash") or "").strip()
        for hits in results:
            for hit in hits:
                similarity = self._distance_to_similarity(hit.distance)
                if similarity < self._semantic_dedupe_threshold:
                    continue
                try:
                    milvus_id = int(hit.id)
                except (TypeError, ValueError):
                    continue
                existing = self._repository.get_by_milvus_id(milvus_id)
                if not existing:
                    continue
                existing_meta = dict(existing.metadata or {})
                if incoming_hash and incoming_hash == str(existing_meta.get("content_hash") or ""):
                    return existing, 1.0, "semantic_hash_match"

                overlap = self._fact_overlap_ratio(incoming_meta, existing_meta)
                if overlap < self._semantic_merge_min_overlap and similarity < (
                    self._semantic_dedupe_threshold + 0.08
                ):
                    continue
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_candidate = existing

        if best_candidate:
            return best_candidate, best_similarity, "semantic"
        return None

    def _resync_record_vector(self, record) -> None:
        """Rebuild vector for an existing DB memory record after content merge/update."""
        if record.milvus_id is not None:
            try:
                self.delete_memory(record.milvus_id, record.memory_type)
            except Exception as exc:
                logger.debug("Failed to delete old vector during merge sync: %s", exc)
        self._repository.clear_milvus_link(record.id)

        updated_item = MemoryItem(
            content=record.content,
            memory_type=record.memory_type,
            agent_id=record.agent_id,
            user_id=record.user_id,
            task_id=record.task_id,
            timestamp=record.timestamp,
            metadata=dict(record.metadata or {}),
        )
        try:
            milvus_id = self._insert_into_milvus(updated_item)
            self._repository.mark_vector_synced(record.id, milvus_id)
        except Exception as exc:
            self._repository.mark_vector_failed(record.id, str(exc))
            logger.warning("Merged memory vector sync failed for record=%s: %s", record.id, exc)

    def _merge_into_existing_memory(
        self,
        *,
        existing,
        incoming: MemoryItem,
        similarity: float,
        reason: str,
    ) -> int:
        existing_meta = dict(existing.metadata or {})
        incoming_meta = dict(incoming.metadata or {})
        existing_facts = existing_meta.get("facts", [])
        if not isinstance(existing_facts, list):
            existing_facts = []
        incoming_facts = incoming_meta.get("facts", [])
        if not isinstance(incoming_facts, list):
            incoming_facts = []

        merged_facts, conflicts = self._merge_fact_lists(existing_facts, incoming_facts)
        merged_content = self._build_structured_content(merged_facts)
        if not merged_content:
            merged_content = incoming.content or existing.content

        existing_mention = existing_meta.get("mention_count", 1)
        incoming_mention = incoming_meta.get("mention_count", 1)
        try:
            mention_count = max(int(existing_mention), 1) + max(int(incoming_mention), 1)
        except (TypeError, ValueError):
            mention_count = 2

        merged_importance = max(
            self._clamp_score(existing_meta.get("importance_score"), default=0.0),
            self._clamp_score(incoming_meta.get("importance_score"), default=0.0),
        )
        merged_tier = (
            "core"
            if (
                str(existing_meta.get("memory_tier") or "").lower() == "core"
                or str(incoming_meta.get("memory_tier") or "").lower() == "core"
                or merged_importance >= self._core_importance_threshold
            )
            else "archival"
        )

        merged_conflicts = existing_meta.get("conflict_history", [])
        if not isinstance(merged_conflicts, list):
            merged_conflicts = []
        merged_conflicts.extend(conflicts)
        if len(merged_conflicts) > self._max_fact_conflict_history:
            merged_conflicts = merged_conflicts[-self._max_fact_conflict_history :]

        merged_metadata = dict(existing_meta)
        merged_metadata.update(
            {
                "facts": merged_facts,
                "fact_keys": [fact.get("key") for fact in merged_facts if fact.get("key")],
                "content_hash": self._compute_content_hash(merged_content),
                "importance_score": round(merged_importance, 4),
                "importance_level": self._derive_importance_level(merged_importance),
                "memory_tier": merged_tier,
                "mention_count": mention_count,
                "last_seen_at": datetime.utcnow().isoformat(),
                "last_merge_reason": reason,
                "last_merge_similarity": round(float(similarity), 4),
            }
        )
        for audit_key in (
            "decision_action",
            "decision_source",
            "decision_confidence",
            "decision_reason",
            "decision_target_memory_id",
        ):
            if audit_key in incoming_meta:
                merged_metadata[audit_key] = incoming_meta.get(audit_key)
        if merged_conflicts:
            merged_metadata["conflict_history"] = merged_conflicts
        if incoming.task_id and not merged_metadata.get("task_id"):
            merged_metadata["task_id"] = incoming.task_id
        if incoming.user_id and not merged_metadata.get("user_id"):
            merged_metadata["user_id"] = incoming.user_id

        existing_hash = str(existing_meta.get("content_hash") or "")
        merged_hash = str(merged_metadata.get("content_hash") or "")
        content_changed = existing_hash != merged_hash or self._normalize_content_for_hash(
            existing.content
        ) != self._normalize_content_for_hash(merged_content)

        updated = self._repository.update_record(
            existing.id,
            content=merged_content if content_changed else None,
            metadata=merged_metadata,
            timestamp=datetime.utcnow(),
            mark_vector_pending=bool(content_changed),
        )
        if updated and content_changed:
            self._resync_record_vector(updated)

        logger.info(
            "Merged duplicate memory",
            extra={
                "existing_id": existing.id,
                "reason": reason,
                "similarity": round(float(similarity), 4),
                "content_changed": content_changed,
            },
        )
        return int(existing.id)

    def _coerce_requested_memory_action(self, metadata: Dict[str, Any]) -> Optional[MemoryAction]:
        raw_action = str(metadata.get("memory_action") or "").strip().upper()
        if not raw_action:
            return None
        alias_map = {
            "NOOP": MemoryAction.NONE,
            "SKIP": MemoryAction.NONE,
        }
        if raw_action in alias_map:
            return alias_map[raw_action]
        try:
            return MemoryAction(raw_action)
        except ValueError:
            return None

    def _is_record_scope_compatible(self, memory: MemoryItem, record: MemoryRecordData) -> bool:
        if record.memory_type != memory.memory_type:
            return False

        if memory.memory_type == MemoryType.AGENT:
            if memory.agent_id and record.agent_id != memory.agent_id:
                return False
            if memory.user_id and record.user_id and record.user_id != memory.user_id:
                return False
            return True

        if memory.user_id and record.user_id and record.user_id != memory.user_id:
            return False
        if memory.task_id and record.task_id and record.task_id != memory.task_id:
            return False
        return True

    def _resolve_explicit_action_target(
        self,
        memory: MemoryItem,
        metadata: Dict[str, Any],
    ) -> Optional[MemoryRecordData]:
        for key in ("target_memory_id", "action_target_memory_id", "delete_memory_id"):
            raw_target_id = metadata.get(key)
            if raw_target_id is None:
                continue
            try:
                target_memory_id = int(raw_target_id)
            except (TypeError, ValueError):
                continue
            if target_memory_id <= 0:
                continue
            record = self._repository.get(target_memory_id)
            if not record:
                return None
            if not self._is_record_scope_compatible(memory, record):
                logger.warning(
                    "Ignore explicit memory action target outside scope",
                    extra={
                        "target_memory_id": target_memory_id,
                        "memory_type": memory.memory_type.value,
                    },
                )
                return None
            return record
        return None

    def _plan_memory_action(self, memory: MemoryItem) -> MemoryActionDecision:
        metadata = dict(memory.metadata or {})
        requested_action = self._coerce_requested_memory_action(metadata)
        explicit_target = None
        if requested_action in {MemoryAction.UPDATE, MemoryAction.DELETE}:
            explicit_target = self._resolve_explicit_action_target(memory, metadata)

        exact_duplicate = None
        semantic_duplicate = None
        if requested_action in {None, MemoryAction.UPDATE}:
            exact_duplicate = self._find_exact_duplicate(memory)
            if not exact_duplicate:
                try:
                    semantic_duplicate = self._find_semantic_duplicate(memory)
                except Exception as dedup_err:
                    logger.debug(
                        "Semantic dedup lookup failed during planning: %s",
                        dedup_err,
                    )

        return self._action_planner.plan(
            requested_action=requested_action,
            explicit_target=explicit_target,
            exact_duplicate=exact_duplicate,
            semantic_duplicate=semantic_duplicate,
        )

    def _apply_action_decision_metadata(
        self,
        memory: MemoryItem,
        decision: MemoryActionDecision,
    ) -> None:
        metadata = dict(memory.metadata or {})
        metadata["decision_action"] = decision.action.value
        metadata["decision_source"] = decision.source or "planner"
        metadata["decision_reason"] = str(decision.reason or "unspecified").strip() or "unspecified"
        if decision.confidence is not None:
            metadata["decision_confidence"] = round(
                self._clamp_score(decision.confidence, default=0.0),
                4,
            )
        if decision.existing_record:
            metadata["decision_target_memory_id"] = int(decision.existing_record.id)
        memory.metadata = metadata

    @staticmethod
    def _normalize_metric_label(value: Any, default: str = "unknown", max_length: int = 48) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")
        if not normalized:
            return default
        return normalized[:max_length]

    def _record_blocked_write_metric(self, memory_type: MemoryType, reason: str) -> None:
        if not self._quality_metrics_enabled or memory_blocked_writes_total is None:
            return
        try:
            memory_blocked_writes_total.labels(
                memory_type=str(memory_type.value),
                reason=self._normalize_metric_label(reason),
            ).inc()
        except Exception:
            logger.debug("Failed to increment blocked-write metric", exc_info=True)

    def _record_planner_action_metric(
        self,
        memory_type: MemoryType,
        decision: MemoryActionDecision,
    ) -> None:
        if not self._quality_metrics_enabled or memory_planner_actions_total is None:
            return
        try:
            memory_planner_actions_total.labels(
                memory_type=str(memory_type.value),
                action=self._normalize_metric_label(decision.action.value, default="unknown"),
                source=self._normalize_metric_label(decision.source or "planner"),
            ).inc()
        except Exception:
            logger.debug("Failed to increment planner-action metric", exc_info=True)

    @staticmethod
    def _classify_blocked_write_reason(error: MemoryQualitySkipError) -> str:
        message = str(error).strip().lower()
        if "no reliable facts extracted" in message:
            return "empty_extraction_fail_closed"
        if "planner decided none" in message:
            return "planner_none"
        if "planner failed in strict mode" in message:
            return "planner_failure_fail_closed"
        if "delete action missing target" in message:
            return "delete_target_missing"
        if "delete target not found" in message:
            return "delete_target_not_found"
        return "quality_gate_blocked"

    def _should_fail_closed_on_planner_failure(self, memory: MemoryItem) -> bool:
        if not self._action_planner_strict_fail_closed:
            return False
        return self._should_fail_closed_on_empty_facts(memory, prefer_model_only=True)

    def _persist_new_memory(self, memory: MemoryItem) -> int:
        self._maybe_run_retention_cleanup(memory)

        # Enforce memory count limits before inserting
        self._enforce_memory_limits(memory)

        # Write to PostgreSQL (source of truth)
        record = self._repository.create(memory)
        db_id = record.id

        # Best-effort Milvus vector sync
        try:
            milvus_id = self._insert_into_milvus(memory)
            self._repository.mark_vector_synced(db_id, milvus_id)
            logger.info(
                "Stored memory: db_id=%s, milvus_id=%s, type=%s",
                db_id,
                milvus_id,
                memory.memory_type.value,
            )
        except Exception as milvus_err:
            self._repository.mark_vector_failed(db_id, str(milvus_err))
            logger.warning(
                "Milvus sync failed for memory db_id=%s (DB record preserved): %s",
                db_id,
                milvus_err,
            )

        return db_id

    def _execute_delete_action(self, memory: MemoryItem, decision: MemoryActionDecision) -> int:
        target = decision.existing_record
        if not target:
            raise MemoryQualitySkipError("Planner DELETE action missing target record")

        now = datetime.utcnow()
        target_metadata = dict(target.metadata or {})
        target_metadata.update(
            {
                "is_active": False,
                "deleted_at": now.isoformat(),
                "decision_action": MemoryAction.DELETE.value,
                "decision_source": decision.source or "planner",
                "decision_reason": str(decision.reason or "explicit_delete"),
                "decision_target_memory_id": int(target.id),
            }
        )
        if decision.confidence is not None:
            target_metadata["decision_confidence"] = round(
                self._clamp_score(decision.confidence, default=0.0),
                4,
            )
        if memory.metadata:
            if memory.metadata.get("superseded_by") is not None:
                target_metadata["superseded_by"] = memory.metadata.get("superseded_by")

        self._repository.update_record(
            target.id,
            metadata=target_metadata,
            timestamp=now,
            mark_vector_pending=False,
        )

        deleted = self._repository.soft_delete(target.id)
        if not deleted:
            raise MemoryQualitySkipError(f"Delete target not found or already deleted: {target.id}")

        if target.milvus_id is not None:
            self.delete_memory(int(target.milvus_id), target.memory_type)

        logger.info(
            "Soft-deleted memory via planner action",
            extra={
                "memory_id": target.id,
                "memory_type": target.memory_type.value,
                "reason": decision.reason,
            },
        )
        return int(target.id)

    def _execute_memory_action(self, memory: MemoryItem, decision: MemoryActionDecision) -> int:
        if decision.action == MemoryAction.NONE:
            raise MemoryQualitySkipError(f"Planner decided NONE; skip write ({decision.reason})")

        if decision.action == MemoryAction.DELETE:
            return self._execute_delete_action(memory, decision)

        if decision.action == MemoryAction.UPDATE:
            if decision.existing_record:
                return self._merge_into_existing_memory(
                    existing=decision.existing_record,
                    incoming=memory,
                    similarity=float(decision.similarity or 1.0),
                    reason=decision.merge_reason or decision.reason or "planner_update",
                )
            logger.warning("Planner UPDATE action missing target; fallback to ADD")

        return self._persist_new_memory(memory)

    def _cleanup_records(self, records: List[Any]) -> None:
        for record in records:
            if record.milvus_id is None:
                continue
            try:
                self.delete_memory(record.milvus_id, record.memory_type)
            except Exception as exc:
                logger.debug(
                    "Failed to cleanup evicted vector milvus_id=%s: %s", record.milvus_id, exc
                )

    def _maybe_run_retention_cleanup(self, memory: MemoryItem) -> None:
        now = time.monotonic()
        if (now - self._last_retention_cleanup_at) < self._retention_cleanup_interval_seconds:
            return
        self._last_retention_cleanup_at = now

        retention_days = self._retention_days_by_type.get(memory.memory_type, 0)
        if retention_days <= 0:
            return

        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        evicted = self._repository.evict_older_than(
            memory_type=memory.memory_type,
            older_than=cutoff,
            agent_id=memory.agent_id if memory.memory_type == MemoryType.AGENT else None,
            user_id=memory.user_id if memory.memory_type == MemoryType.USER_CONTEXT else None,
            protect_core=self._core_protection_enabled,
            limit=500,
        )
        if evicted:
            self._cleanup_records(evicted)
            logger.info(
                "Retention cleanup evicted memories",
                extra={
                    "count": len(evicted),
                    "memory_type": memory.memory_type.value,
                    "cutoff": cutoff.isoformat(),
                },
            )

    def _insert_into_milvus(self, memory: MemoryItem) -> int:
        """Insert a memory item into Milvus vector index.

        Args:
            memory: Memory item with content (embedding generated if missing)

        Returns:
            int: Milvus primary key ID

        Raises:
            RuntimeError: If Milvus insertion fails
        """
        try:
            # Generate embedding if not already present
            if not memory.embedding:
                memory.embedding = self._embedding_service.generate_embedding(memory.content)

            embedding = memory.embedding

            # Determine target collection
            if memory.memory_type == MemoryType.AGENT:
                collection_name = CollectionName.AGENT_MEMORIES
            else:
                collection_name = CollectionName.COMPANY_MEMORIES

            # Get collection
            collection = self._milvus.get_collection(collection_name)

            # Prepare data for insertion
            if not memory.timestamp:
                memory.timestamp = datetime.utcnow()
            timestamp_ms = int(memory.timestamp.timestamp() * 1000)
            metadata_payload = dict(memory.metadata or {})
            if memory.user_id and "user_id" not in metadata_payload:
                metadata_payload["user_id"] = memory.user_id
            if memory.task_id and "task_id" not in metadata_payload:
                metadata_payload["task_id"] = memory.task_id

            if collection_name == CollectionName.AGENT_MEMORIES:
                data = [
                    [memory.agent_id],  # agent_id
                    [embedding],  # embedding
                    [memory.content],  # content
                    [timestamp_ms],  # timestamp
                    [metadata_payload],  # metadata
                ]
            else:  # COMPANY_MEMORIES
                data = [
                    [memory.user_id],  # user_id
                    [embedding],  # embedding
                    [memory.content],  # content
                    [memory.memory_type.value],  # memory_type
                    [timestamp_ms],  # timestamp
                    [metadata_payload],  # metadata
                ]

            # Insert into Milvus
            result = collection.insert(data)
            milvus_id = result.primary_keys[0]

            logger.info(
                "Inserted vector into Milvus: milvus_id=%s, type=%s, collection=%s",
                milvus_id,
                memory.memory_type.value,
                collection_name,
            )

            return milvus_id

        except Exception as e:
            raise RuntimeError(f"Milvus insertion failed: {e}")

    def _resolve_agent_owner_user_id(self, agent_id: Optional[str]) -> Optional[str]:
        """Resolve agent owner user_id for agent memories when caller omits it."""
        if not agent_id:
            return None

        try:
            parsed_agent_id = UUID(str(agent_id))
        except Exception:
            return None

        try:
            from database.connection import get_db_session
            from database.models import Agent

            with get_db_session() as session:
                row = (
                    session.query(Agent.owner_user_id)
                    .filter(Agent.agent_id == parsed_agent_id)
                    .first()
                )
            return str(row[0]) if row and row[0] else None
        except Exception as exc:
            logger.debug(
                "Failed to resolve owner user_id for agent_id=%s: %s",
                agent_id,
                exc,
            )
            return None

    def store_memory(self, memory: MemoryItem) -> int:
        """
        Store a memory item with PostgreSQL as source-of-truth.

        Flow:
        1. Validate content and scope fields
        2. Normalize to structured facts and memory quality metadata
        3. Deduplicate/merge with existing memories when possible
        4. Apply retention + value-aware capacity controls
        5. Write to PostgreSQL via MemoryRepository
        6. Best-effort insert into Milvus vector index
        7. Return PostgreSQL record ID (or merged existing ID)

        Args:
            memory: Memory item to store

        Returns:
            int: PostgreSQL record ID of the stored memory

        Raises:
            ValueError: If memory data is invalid
            RuntimeError: If PostgreSQL storage fails
        """
        # Validate memory
        if not memory.content or not memory.content.strip():
            raise ValueError("Memory content cannot be empty")

        if not memory.memory_type:
            raise ValueError("Memory type must be specified")

        if memory.memory_type == MemoryType.AGENT and not memory.agent_id:
            raise ValueError("agent_id required for agent memories")

        if memory.memory_type == MemoryType.AGENT and not memory.user_id:
            resolved_user_id = self._resolve_agent_owner_user_id(memory.agent_id)
            if resolved_user_id:
                memory.user_id = resolved_user_id

        if memory.memory_type != MemoryType.AGENT and not memory.user_id:
            raise ValueError("user_id required for company/user_context memories")

        # Set timestamp if not provided
        if not memory.timestamp:
            memory.timestamp = datetime.utcnow()

        # Keep metadata consistent with principal fields for downstream filtering.
        memory.metadata = dict(memory.metadata or {})
        if memory.user_id and "user_id" not in memory.metadata:
            memory.metadata["user_id"] = memory.user_id

        try:
            if self._enhanced_memory_enabled:
                try:
                    memory = self._prepare_memory_for_storage(memory)
                except MemoryQualitySkipError:
                    raise
                except Exception as prep_err:
                    logger.warning(
                        "Memory normalization failed; using original payload: %s",
                        prep_err,
                    )

                if self._action_planner_enabled:
                    try:
                        decision = self._plan_memory_action(memory)
                    except Exception as planner_err:
                        if self._should_fail_closed_on_planner_failure(memory):
                            raise MemoryQualitySkipError(
                                f"Planner failed in strict mode; skip write ({planner_err})"
                            )
                        logger.warning(
                            "Memory planner failed; fallback to ADD action: %s",
                            planner_err,
                        )
                        decision = MemoryActionDecision(
                            action=MemoryAction.ADD,
                            reason="planner_error_fallback_add",
                            source="planner_fallback",
                            confidence=0.4,
                        )

                    self._apply_action_decision_metadata(memory, decision)
                    self._record_planner_action_metric(memory.memory_type, decision)
                    return self._execute_memory_action(memory, decision)

                duplicate_match = self._find_exact_duplicate(memory)
                if not duplicate_match:
                    try:
                        duplicate_match = self._find_semantic_duplicate(memory)
                    except Exception as dedup_err:
                        logger.debug(
                            "Semantic dedup lookup failed; continuing with insert: %s",
                            dedup_err,
                        )
                if duplicate_match:
                    existing, similarity, reason = duplicate_match
                    return self._merge_into_existing_memory(
                        existing=existing,
                        incoming=memory,
                        similarity=similarity,
                        reason=reason,
                    )

            return self._persist_new_memory(memory)

        except MemoryQualitySkipError as skip_err:
            self._record_blocked_write_metric(
                memory.memory_type,
                self._classify_blocked_write_reason(skip_err),
            )
            raise
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise RuntimeError(f"Memory storage failed: {e}")

    def _enforce_memory_limits(self, memory: MemoryItem) -> None:
        """Evict low-value memories when count exceeds configured limits.

        Args:
            memory: The memory item about to be stored (used for type/scope)
        """
        try:
            if memory.memory_type == MemoryType.AGENT:
                limit = self._max_items_per_agent
                current_count = self._repository.count_memories(
                    memory_type=MemoryType.AGENT,
                    agent_id=memory.agent_id,
                )
            elif memory.memory_type == MemoryType.USER_CONTEXT:
                limit = self._max_items_per_user
                current_count = self._repository.count_memories(
                    memory_type=MemoryType.USER_CONTEXT,
                    user_id=memory.user_id,
                )
            elif memory.memory_type == MemoryType.COMPANY:
                limit = self._max_items_company
                current_count = self._repository.count_memories(
                    memory_type=MemoryType.COMPANY,
                )
            else:
                return

            if current_count < limit:
                return

            evict_count = current_count - limit + 1
            evicted = self._repository.evict_low_value(
                memory_type=memory.memory_type,
                agent_id=memory.agent_id if memory.memory_type == MemoryType.AGENT else None,
                user_id=memory.user_id if memory.memory_type == MemoryType.USER_CONTEXT else None,
                count=evict_count,
                protect_core=self._core_protection_enabled,
            )
            self._cleanup_records(evicted)

            logger.info(
                "Evicted %d low-value memories (type=%s, limit=%d, was=%d)",
                len(evicted),
                memory.memory_type.value,
                limit,
                current_count,
            )
        except Exception as e:
            logger.warning("Memory limit enforcement failed (continuing): %s", e)

    def retrieve_memories(self, query: SearchQuery) -> List[MemoryItem]:
        """
        Retrieve memories based on semantic similarity search.

        Args:
            query: Search query with filters

        Returns:
            List[MemoryItem]: List of matching memories ranked by relevance

        Raises:
            ValueError: If query is invalid
            RuntimeError: If retrieval fails
        """
        if not query.query_text or not query.query_text.strip():
            raise ValueError("Query text cannot be empty")

        try:
            # Generate query embedding
            query_embedding = self._embedding_service.generate_embedding(query.query_text)

            # Determine which collections to search
            collections_to_search = self._determine_search_collections(query)

            # Search each collection
            all_results = []
            for collection_name in collections_to_search:
                results = self._search_collection(collection_name, query_embedding, query)
                all_results.extend(results)

            # Rank results by relevance (similarity + recency + memory utility signals).
            ranked_results = self._rank_results(all_results)
            ranked_results = self._collapse_duplicate_results(ranked_results)

            # Optional model-based rerank for top candidates.
            top_k = query.top_k or self._default_top_k
            ranked_results = self._rerank_results(
                query_text=query.query_text,
                ranked_results=ranked_results,
                top_k=top_k,
            )

            # Apply top_k limit
            final_results = ranked_results[:top_k]

            logger.info(
                f"Retrieved {len(final_results)} memories for query "
                f"(searched {len(collections_to_search)} collections)"
            )

            return final_results

        except Exception as e:
            logger.error(f"Failed to retrieve memories: {e}")
            raise RuntimeError(f"Memory retrieval failed: {e}")

    def _determine_search_collections(self, query: SearchQuery) -> List[str]:
        """
        Determine which collections to search based on query filters.

        Args:
            query: Search query

        Returns:
            List[str]: List of collection names to search
        """
        collections = []

        if query.memory_type == MemoryType.AGENT:
            collections.append(CollectionName.AGENT_MEMORIES)
        elif query.memory_type in [
            MemoryType.COMPANY,
            MemoryType.USER_CONTEXT,
            MemoryType.TASK_CONTEXT,
        ]:
            collections.append(CollectionName.COMPANY_MEMORIES)
        else:
            # Search all collections if no specific type
            if query.agent_id:
                collections.append(CollectionName.AGENT_MEMORIES)
            if query.user_id:
                collections.append(CollectionName.COMPANY_MEMORIES)
            if not query.agent_id and not query.user_id:
                # Search both if no filters
                collections.extend([CollectionName.AGENT_MEMORIES, CollectionName.COMPANY_MEMORIES])

        return collections

    def _search_collection(
        self, collection_name: str, query_embedding: List[float], query: SearchQuery
    ) -> List[MemoryItem]:
        """
        Search a specific collection for similar memories.

        Args:
            collection_name: Name of the collection to search
            query_embedding: Query embedding vector
            query: Search query with filters

        Returns:
            List[MemoryItem]: List of matching memories
        """
        try:
            collection = self._milvus.get_collection(collection_name)

            # Build filter expression
            filter_expr = self._build_filter_expression(collection_name, query)

            # Prepare search parameters from Milvus config.
            search_params = {
                "metric_type": self._search_metric_type,
                "params": {"nprobe": self._search_nprobe},
            }

            # Determine output fields based on collection
            if collection_name == CollectionName.AGENT_MEMORIES:
                output_fields = ["agent_id", "content", "timestamp", "metadata"]
            else:  # COMPANY_MEMORIES
                output_fields = ["user_id", "content", "memory_type", "timestamp", "metadata"]

            candidate_limit = max(
                query.top_k or self._default_top_k,
                self._rerank_top_k if self._enable_reranking else 0,
            )

            # Perform search with short retries for transient load-state failures.
            results = self._search_collection_with_retry(
                collection=collection,
                collection_name=collection_name,
                query_embedding=query_embedding,
                search_params=search_params,
                limit=candidate_limit,
                filter_expr=filter_expr,
                output_fields=output_fields,
            )

            # Convert results to MemoryItem objects.
            if query.min_similarity is None:
                effective_min_similarity = self._default_similarity_threshold
            else:
                try:
                    effective_min_similarity = max(float(query.min_similarity), 0.0)
                except (TypeError, ValueError):
                    effective_min_similarity = self._default_similarity_threshold

            raw_hit_count = 0
            memories = []
            for hits in results:
                for hit in hits:
                    raw_hit_count += 1
                    memory = self._hit_to_memory_item(hit, collection_name)
                    if memory and memory.similarity_score >= effective_min_similarity:
                        memories.append(memory)

            logger.debug(
                "Memory search filtered results",
                extra={
                    "collection": collection_name,
                    "raw_hit_count": raw_hit_count,
                    "kept_hit_count": len(memories),
                    "effective_min_similarity": effective_min_similarity,
                    "query_min_similarity": query.min_similarity,
                },
            )

            return memories

        except Exception as e:
            logger.error(f"Failed to search collection {collection_name}: {e}")
            return []

    @staticmethod
    def _is_collection_not_loaded_error(exc: Exception) -> bool:
        """Detect Milvus transient collection load-state error."""
        current = exc
        seen = set()
        while current and id(current) not in seen:
            seen.add(id(current))
            code = getattr(current, "code", None)
            if code == 101:
                return True
            message = str(current).lower()
            if "collection not loaded" in message:
                return True
            if "not loaded" in message and "collection" in message:
                return True

            if current.__cause__ is not None:
                current = current.__cause__
            elif current.__context__ is not None:
                current = current.__context__
            else:
                current = None
        return False

    def _search_collection_with_retry(
        self,
        collection: Collection,
        collection_name: str,
        query_embedding: List[float],
        search_params: Dict[str, Any],
        limit: int,
        filter_expr: Optional[str],
        output_fields: List[str],
    ):
        """Search Milvus with retries when collection is still loading."""
        last_error: Optional[Exception] = None

        for attempt in range(1, self._collection_retry_attempts + 1):
            try:
                return collection.search(
                    data=[query_embedding],
                    anns_field="embedding",
                    param=search_params,
                    limit=limit,
                    expr=filter_expr if filter_expr else None,
                    output_fields=output_fields,
                    timeout=max(self._search_timeout_seconds, 0.5),
                )
            except Exception as exc:
                if not self._is_collection_not_loaded_error(exc):
                    raise
                last_error = exc
                try:
                    collection.load(timeout=1.0, _async=True)
                except Exception as load_exc:
                    logger.debug(
                        "Failed to trigger async load for %s after search failure: %s",
                        collection_name,
                        load_exc,
                    )

                if attempt < self._collection_retry_attempts:
                    delay = self._collection_retry_delay_seconds * attempt
                    logger.warning(
                        "Collection '%s' not loaded yet (attempt %d/%d), retrying in %.2fs",
                        collection_name,
                        attempt,
                        self._collection_retry_attempts,
                        delay,
                    )
                    time.sleep(delay)

        if last_error:
            logger.warning(
                "Collection '%s' remained unavailable after %d retries: %s",
                collection_name,
                self._collection_retry_attempts,
                last_error,
            )
        return []

    def _build_filter_expression(self, collection_name: str, query: SearchQuery) -> Optional[str]:
        """
        Build Milvus filter expression from query filters.

        Args:
            collection_name: Name of the collection
            query: Search query with filters

        Returns:
            Optional[str]: Filter expression or None
        """
        filters = []

        if collection_name == CollectionName.AGENT_MEMORIES:
            if query.agent_id:
                filters.append(f'agent_id == "{query.agent_id}"')
            if query.user_id:
                filters.append(f'metadata["user_id"] == "{query.user_id}"')
        else:  # COMPANY_MEMORIES
            if query.user_id:
                filters.append(f'user_id == "{query.user_id}"')
            if query.memory_type:
                filters.append(f'memory_type == "{query.memory_type.value}"')
            if query.task_id:
                # Filter by task_id in metadata (requires JSON filtering)
                filters.append(f'metadata["task_id"] == "{query.task_id}"')

        return " && ".join(filters) if filters else None

    def _distance_to_similarity(self, distance: float) -> float:
        """Normalize distance/score from Milvus into a [0, 1] similarity value."""
        metric = str(self._search_metric_type or "L2").upper()
        try:
            raw_distance = float(distance)
        except (TypeError, ValueError):
            return 0.0

        if metric == "L2":
            # Embeddings are unit-normalized at ingestion/query time. For unit vectors:
            #   ||a-b||^2 = 2 - 2*cos(theta)  =>  cos(theta) = 1 - ||a-b||^2 / 2
            # Convert L2 distance to cosine-like semantic similarity so threshold semantics are stable.
            bounded_l2 = min(max(raw_distance, 0.0), 2.0)
            cosine_like = 1.0 - (bounded_l2 * bounded_l2) / 2.0
            return max(min(cosine_like, 1.0), 0.0)

        # For IP/COSINE, Milvus returns score-like distances where larger is better.
        if metric in {"IP", "COSINE"}:
            return max(min(raw_distance, 1.0), 0.0)

        return 1.0 / (1.0 + max(raw_distance, 0.0))

    def _hit_to_memory_item(self, hit: Any, collection_name: str) -> Optional[MemoryItem]:
        """
        Convert a Milvus search hit to a MemoryItem.

        Args:
            hit: Milvus search hit
            collection_name: Name of the collection

        Returns:
            Optional[MemoryItem]: Memory item or None if conversion fails
        """
        try:
            # Extract fields from hit
            memory_id = hit.id
            similarity_score = self._distance_to_similarity(hit.distance)
            content = hit.entity.get("content")
            timestamp_ms = hit.entity.get("timestamp")
            raw_metadata = hit.entity.get("metadata")
            metadata = dict(raw_metadata) if isinstance(raw_metadata, dict) else {}
            metadata["_semantic_score"] = round(float(similarity_score), 6)

            # Convert timestamp
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0) if timestamp_ms else None

            # Determine memory type and extract type-specific fields
            if collection_name == CollectionName.AGENT_MEMORIES:
                agent_id = hit.entity.get("agent_id")
                memory_type = MemoryType.AGENT
                user_id = None
            else:  # COMPANY_MEMORIES
                agent_id = None
                user_id = hit.entity.get("user_id")
                memory_type_str = hit.entity.get("memory_type", "company")
                memory_type = MemoryType(memory_type_str)

            # Extract task_id from metadata if present
            task_id = metadata.get("task_id") if metadata else None

            return MemoryItem(
                id=memory_id,
                content=content,
                memory_type=memory_type,
                agent_id=agent_id,
                user_id=user_id,
                task_id=task_id,
                timestamp=timestamp,
                metadata=metadata,
                similarity_score=similarity_score,
            )

        except Exception as e:
            logger.error(f"Failed to convert hit to memory item: {e}")
            return None

    def _rank_results(self, results: List[MemoryItem]) -> List[MemoryItem]:
        """
        Rank results by relevance (similarity + recency + memory utility scores).

        Args:
            results: List of memory items

        Returns:
            List[MemoryItem]: Ranked list of memory items
        """
        if not results:
            return []

        # Calculate current time for recency scoring.
        current_time = datetime.utcnow()

        # Calculate combined scores.
        for memory in results:
            similarity_score = memory.similarity_score or 0.0

            metadata = dict(memory.metadata or {})
            if memory.timestamp:
                age_seconds = (current_time - memory.timestamp).total_seconds()
                age_days = age_seconds / 86400.0
                decay = math.log(2.0) / max(self._recency_half_life_days, 0.1)
                recency_score = math.exp(-decay * max(age_days, 0.0))
            else:
                recency_score = 0.0

            importance_score = self._clamp_score(metadata.get("importance_score"), default=0.0)
            tier_score = (
                1.0 if str(metadata.get("memory_tier") or "").strip().lower() == "core" else 0.0
            )
            mention_count = metadata.get("mention_count", 1)
            try:
                mention_count = max(int(mention_count), 1)
            except (TypeError, ValueError):
                mention_count = 1
            mention_score = min(math.log1p(mention_count) / math.log1p(20), 1.0)

            combined_score = (
                self._similarity_weight * similarity_score
                + self._recency_weight * recency_score
                + self._importance_weight * importance_score
                + self._tier_weight * tier_score
                + self._mention_weight * mention_score
            ) / self._score_weight_total

            metadata["_combined_score"] = round(combined_score, 6)
            metadata["_recency_score"] = round(recency_score, 6)
            metadata["_importance_score"] = round(importance_score, 6)
            metadata["_tier_score"] = round(tier_score, 6)
            metadata["_mention_score"] = round(mention_score, 6)
            memory.metadata = metadata

        ranked = sorted(
            results,
            key=lambda memory_item: (memory_item.metadata or {}).get("_combined_score", 0.0),
            reverse=True,
        )

        return ranked

    def _collapse_duplicate_results(self, ranked_results: List[MemoryItem]) -> List[MemoryItem]:
        """Remove duplicate memories in retrieval results using content/fact signatures."""
        collapsed: List[MemoryItem] = []
        seen_signatures = set()

        for item in ranked_results:
            metadata = dict(item.metadata or {})
            content_hash = str(metadata.get("content_hash") or "").strip()
            if not content_hash:
                content_hash = self._compute_content_hash(item.content)
            fact_keys = (
                metadata.get("fact_keys") if isinstance(metadata.get("fact_keys"), list) else []
            )
            fact_signature = "|".join(
                sorted([str(key).strip() for key in fact_keys if str(key).strip()])[:8]
            )
            scope_id = item.agent_id if item.memory_type == MemoryType.AGENT else item.user_id
            signature = (
                str(item.memory_type.value),
                str(scope_id or ""),
                content_hash,
                fact_signature,
            )
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)
            collapsed.append(item)

        return collapsed

    def _rerank_results(
        self,
        query_text: str,
        ranked_results: List[MemoryItem],
        top_k: int,
    ) -> List[MemoryItem]:
        """Apply optional model rerank to the highest-ranked candidates."""
        if (
            not self._enable_reranking
            or not self._rerank_provider
            or not self._rerank_model
            or len(ranked_results) <= 1
        ):
            return ranked_results

        now = time.monotonic()
        if now < self._rerank_fail_until:
            return ranked_results

        from llm_providers.provider_resolver import resolve_provider

        provider_cfg = resolve_provider(self._rerank_provider)
        base_url = str(provider_cfg.get("base_url") or "").strip()
        if not base_url:
            logger.warning(
                "Memory rerank provider not resolvable, skip model rerank",
                extra={"rerank_provider": self._rerank_provider},
            )
            return ranked_results

        candidate_limit = min(
            len(ranked_results),
            max(int(self._rerank_top_k), int(top_k) * 3, int(top_k)),
        )
        candidates = ranked_results[:candidate_limit]
        documents = [self._build_rerank_document(item) for item in candidates]

        rerank_items = self._call_rerank_api(
            query=query_text,
            documents=documents,
            base_url=base_url,
            api_key=provider_cfg.get("api_key"),
        )
        if not rerank_items:
            return ranked_results

        rerank_weight = min(max(self._rerank_weight, 0.0), 1.0)
        base_weight = 1.0 - rerank_weight

        reranked_candidates: List[MemoryItem] = []
        for doc_index, rerank_score in rerank_items:
            if doc_index < 0 or doc_index >= len(candidates):
                continue
            candidate = candidates[doc_index]
            candidate.metadata = dict(candidate.metadata or {})
            if "_semantic_score" not in candidate.metadata:
                candidate.metadata["_semantic_score"] = round(
                    float(candidate.similarity_score or 0.0),
                    6,
                )
            base_score = float(
                candidate.metadata.get("_combined_score", candidate.similarity_score or 0.0)
            )
            base_score = max(min(base_score, 1.0), 0.0)
            blended = rerank_weight * float(rerank_score) + base_weight * base_score
            candidate.metadata["_rerank_score"] = round(float(rerank_score), 4)
            candidate.metadata["_rerank_blended_score"] = round(float(blended), 4)
            candidate.metadata["_rerank_provider"] = self._rerank_provider
            candidate.metadata["_rerank_model"] = self._rerank_model
            candidate.similarity_score = float(blended)
            reranked_candidates.append(candidate)

        if not reranked_candidates:
            return ranked_results

        reranked_candidates.sort(
            key=lambda item: float((item.metadata or {}).get("_rerank_blended_score", 0.0)),
            reverse=True,
        )
        reranked_ids = {int(item.id) for item in reranked_candidates if item.id is not None}
        reranked_candidates.extend(
            [item for item in candidates if item.id is None or int(item.id) not in reranked_ids]
        )
        reranked_candidates.extend(ranked_results[candidate_limit:])
        return reranked_candidates

    def _build_rerank_document(self, memory: MemoryItem) -> str:
        """Build compact rerank document from memory content and selected metadata."""
        parts = [memory.content or ""]
        metadata = memory.metadata or {}

        summary = metadata.get("summary")
        if summary:
            parts.append(f"Summary: {summary}")

        tags = metadata.get("tags")
        if isinstance(tags, list) and tags:
            text_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
            if text_tags:
                parts.append("Tags: " + ", ".join(text_tags))

        text = "\n".join(part.strip() for part in parts if part and str(part).strip())
        return text[: max(int(self._rerank_doc_max_chars), 256)]

    def _call_rerank_api(
        self,
        query: str,
        documents: List[str],
        base_url: str,
        api_key: Optional[str],
    ) -> List[Tuple[int, float]]:
        """Call OpenAI-compatible rerank API and return ordered (doc_index, score)."""
        if not documents:
            return []

        now = time.monotonic()
        if now < self._rerank_fail_until:
            return []

        total_timeout = max(float(self._rerank_timeout_seconds), 1.0)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {
            "model": self._rerank_model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
        }

        urls_to_try = [
            f"{base_url.rstrip('/')}/v1/rerank",
            f"{base_url.rstrip('/')}/rerank",
            f"{base_url.rstrip('/')}/api/rerank",
        ]
        per_attempt_timeout = max(total_timeout / max(len(urls_to_try), 1), 1.0)

        last_error = None
        for url in urls_to_try:
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=per_attempt_timeout,
                )
                if response.status_code != 200:
                    last_error = f"{url} -> HTTP {response.status_code}: {response.text[:160]}"
                    continue
                parsed = self._parse_rerank_response(response.json(), len(documents))
                if parsed:
                    self._rerank_fail_until = 0.0
                    return parsed
                last_error = f"{url} -> empty or invalid rerank response"
            except Exception as call_err:
                last_error = f"{url} -> {call_err}"

        self._rerank_fail_until = now + max(self._rerank_failure_backoff_seconds, 1.0)
        if last_error:
            logger.warning(
                "Memory rerank failed, fallback to base ranking",
                extra={
                    "error": last_error,
                    "rerank_provider": self._rerank_provider,
                    "backoff_seconds": self._rerank_failure_backoff_seconds,
                },
            )
        return []

    def _parse_rerank_response(
        self,
        response_data: object,
        doc_count: int,
    ) -> List[Tuple[int, float]]:
        """Parse rerank response into ordered (index, score) pairs."""
        if isinstance(response_data, str):
            try:
                response_data = json.loads(response_data)
            except Exception:
                return []
        if not isinstance(response_data, dict):
            return []

        raw_results = response_data.get("results")
        if not isinstance(raw_results, list):
            raw_results = response_data.get("data")
        if not isinstance(raw_results, list):
            raw_results = response_data.get("output")
            if isinstance(raw_results, str):
                try:
                    wrapped_output = json.loads(raw_results)
                except Exception:
                    wrapped_output = None
                if isinstance(wrapped_output, dict):
                    raw_results = wrapped_output.get("results") or wrapped_output.get("data")
        if not isinstance(raw_results, list):
            return []

        parsed: List[Tuple[int, float]] = []
        for idx, item in enumerate(raw_results):
            if isinstance(item, dict):
                raw_index = (
                    item.get("index")
                    if item.get("index") is not None
                    else item.get("document_index")
                )
                if raw_index is None and isinstance(item.get("document"), dict):
                    raw_index = item.get("document", {}).get("index")
                try:
                    doc_index = int(raw_index if raw_index is not None else idx)
                except (TypeError, ValueError):
                    continue
                raw_score = (
                    item.get("relevance_score")
                    if item.get("relevance_score") is not None
                    else item.get("score")
                )
                if raw_score is None:
                    raw_score = item.get("similarity", 0.0)
            else:
                doc_index = idx
                raw_score = item

            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue

            if doc_index < 0 or doc_index >= doc_count:
                continue
            parsed.append((doc_index, max(min(score, 1.0), 0.0)))

        parsed.sort(key=lambda pair: pair[1], reverse=True)
        return parsed

    def delete_memory(self, memory_id: int, memory_type: MemoryType) -> bool:
        """
        Delete a specific memory by ID.

        Args:
            memory_id: ID of the memory to delete
            memory_type: Type of memory (determines collection)

        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            # Determine collection
            if memory_type == MemoryType.AGENT:
                collection_name = CollectionName.AGENT_MEMORIES
            else:
                collection_name = CollectionName.COMPANY_MEMORIES

            # Get collection
            collection = self._milvus.get_collection(collection_name)

            # Delete by ID
            expr = f"id == {memory_id}"
            collection.delete(expr, timeout=max(self._delete_timeout_seconds, 0.5))

            logger.info(f"Deleted memory: id={memory_id}, type={memory_type.value}")
            return True

        except Exception as e:
            if self._is_collection_not_loaded_error(e):
                logger.warning(
                    "Skip deleting memory %s in %s because collection is not loaded: %s",
                    memory_id,
                    memory_type.value,
                    e,
                )
                return False
            logger.error(f"Failed to delete memory {memory_id}: {e}")
            return False

    def archive_agent_memories(self, agent_id: str) -> Dict[str, Any]:
        """
        Archive all memories for an agent to cold storage (MinIO).

        This is called when an agent is terminated.

        Args:
            agent_id: Agent identifier

        Returns:
            dict: Archive metadata (location, count, timestamp)
        """
        try:
            # Query all memories for the agent
            collection = self._milvus.get_collection(CollectionName.AGENT_MEMORIES)

            # Search with filter
            expr = f'agent_id == "{agent_id}"'
            results = collection.query(
                expr=expr, output_fields=["id", "agent_id", "content", "timestamp", "metadata"]
            )

            if not results:
                logger.info(f"No memories to archive for agent {agent_id}")
                return {
                    "agent_id": agent_id,
                    "count": 0,
                    "timestamp": datetime.utcnow().isoformat(),
                }

            # Prepare archive data
            archive_data = {
                "agent_id": agent_id,
                "archived_at": datetime.utcnow().isoformat(),
                "count": len(results),
                "memories": results,
            }

            # TODO: Upload to MinIO (requires MinIO client integration)
            # For now, just log the archive
            logger.info(
                f"Archived {len(results)} memories for agent {agent_id} "
                f"(MinIO upload not yet implemented)"
            )

            # Delete memories from Milvus after archiving
            collection.delete(expr)

            return {
                "agent_id": agent_id,
                "count": len(results),
                "timestamp": archive_data["archived_at"],
                "location": f"minio://agent-artifacts/{agent_id}/memories.json",
            }

        except Exception as e:
            logger.error(f"Failed to archive memories for agent {agent_id}: {e}")
            raise RuntimeError(f"Memory archival failed: {e}")

    def classify_memory_type(
        self, content: str, context: Optional[Dict[str, Any]] = None
    ) -> MemoryType:
        """
        Classify whether memory should be user-specific or task-specific.

        This uses simple heuristics. For more sophisticated classification,
        an LLM could be used.

        Args:
            content: Memory content text
            context: Additional context for classification

        Returns:
            MemoryType: Classified memory type
        """
        content_lower = content.lower()

        # User context keywords
        user_keywords = [
            "prefer",
            "like",
            "dislike",
            "always",
            "never",
            "usually",
            "my",
            "i am",
            "i have",
            "remember that i",
        ]

        # Task context keywords
        task_keywords = [
            "task",
            "step",
            "result",
            "output",
            "completed",
            "failed",
            "processing",
            "analyzed",
            "generated",
        ]

        # Check for explicit context hints
        if context:
            if context.get("is_user_preference"):
                return MemoryType.USER_CONTEXT
            if context.get("is_task_result"):
                return MemoryType.TASK_CONTEXT

        # Check for user context keywords
        if any(keyword in content_lower for keyword in user_keywords):
            return MemoryType.USER_CONTEXT

        # Check for task context keywords
        if any(keyword in content_lower for keyword in task_keywords):
            return MemoryType.TASK_CONTEXT

        # Default to general company memory
        return MemoryType.COMPANY

    def share_memory(
        self, memory_id: int, source_type: MemoryType, target_user_ids: List[str]
    ) -> bool:
        """
        Share a memory with specific users.

        This creates copies of the memory in company_memories with
        appropriate user_id filters.

        Args:
            memory_id: ID of the memory to share
            source_type: Source memory type
            target_user_ids: List of user IDs to share with

        Returns:
            bool: True if shared successfully
        """
        try:
            # Retrieve the source memory
            if source_type == MemoryType.AGENT:
                collection_name = CollectionName.AGENT_MEMORIES
            else:
                collection_name = CollectionName.COMPANY_MEMORIES

            collection = self._milvus.get_collection(collection_name)

            # Query the memory
            results = collection.query(
                expr=f"id == {memory_id}", output_fields=["content", "timestamp", "metadata"]
            )

            if not results:
                logger.error(f"Memory {memory_id} not found")
                return False

            source_memory = results[0]

            # Create shared copies for each target user
            for user_id in target_user_ids:
                shared_memory = MemoryItem(
                    content=source_memory["content"],
                    memory_type=MemoryType.COMPANY,
                    user_id=user_id,
                    timestamp=datetime.fromtimestamp(source_memory["timestamp"] / 1000.0),
                    metadata={
                        **(source_memory.get("metadata") or {}),
                        "shared_from": memory_id,
                        "shared_at": datetime.utcnow().isoformat(),
                    },
                )

                self.store_memory(shared_memory)

            logger.info(f"Shared memory {memory_id} with {len(target_user_ids)} users")
            return True

        except Exception as e:
            logger.error(f"Failed to share memory {memory_id}: {e}")
            return False

    def get_memory_stats(self) -> Dict[str, Any]:
        """
        Get statistics about memory usage.

        Returns:
            dict: Statistics including counts, sizes, etc.
        """
        try:
            stats = {}

            # Get stats for each collection
            for collection_name in [CollectionName.AGENT_MEMORIES, CollectionName.COMPANY_MEMORIES]:
                try:
                    collection_stats = self._milvus.get_collection_stats(collection_name)
                    stats[collection_name] = collection_stats
                except Exception as e:
                    logger.error(f"Failed to get stats for {collection_name}: {e}")
                    stats[collection_name] = {"error": str(e)}

            return stats

        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {"error": str(e)}


# Global memory system instance
_memory_system: Optional[MemorySystem] = None


def get_memory_system() -> MemorySystem:
    """
    Get the global Memory System instance.

    Returns:
        MemorySystem: Global memory system instance
    """
    global _memory_system

    if _memory_system is None:
        _memory_system = MemorySystem()

    return _memory_system
