"""Query planning for user-memory hybrid retrieval."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import requests

from llm_providers.openai_compatible import (
    build_api_url_candidates,
    extract_chat_completion_content,
)
from llm_providers.provider_resolver import resolve_provider
from shared.config import get_config
from user_memory.lexical_search import build_query_variants, extract_query_terms, normalize_text
from user_memory.structured_search import StructuredQueryFilters, StructuredTimeRange
from user_memory.vector_documents import parse_event_time_range

logger = logging.getLogger(__name__)

_PROFILE_CUES = {
    "偏好",
    "喜欢",
    "习惯",
    "风格",
    "格式",
    "语言",
    "preference",
    "prefer",
    "style",
    "format",
    "language",
    "profile",
}
_EPISODE_CUES = {"什么时候", "何时", "哪年", "哪月", "哪天", "经历", "event", "episode", "when"}
_RELATIONSHIP_CUES = {"配偶", "妻子", "老公", "丈夫", "spouse", "wife", "husband", "relationship"}
_EVENT_CUES = {"搬家", "搬到", "去了", "move", "moved", "event", "经历", "何时", "什么时候"}
_RELATIONSHIP_PREDICATE_CUES = {
    "配偶": "spouse",
    "妻子": "spouse",
    "老婆": "spouse",
    "老公": "spouse",
    "丈夫": "spouse",
    "spouse": "spouse",
    "wife": "spouse",
    "husband": "spouse",
    "妈妈": "mother",
    "母亲": "mother",
    "爸爸": "father",
    "父亲": "father",
    "儿子": "son",
    "女儿": "daughter",
    "孩子": "child",
    "朋友": "friend",
    "好友": "friend",
    "friend": "friend",
    "同事": "coworker",
    "同僚": "coworker",
    "coworker": "coworker",
    "colleague": "coworker",
}
_LOCATION_PATTERN = re.compile(r"(?:在|到|去|搬到)([\u4e00-\u9fffA-Za-z0-9_-]{2,24})")
_DATE_FRAGMENT_PATTERN = re.compile(
    r"(\d{4}年\d{1,2}月\d{1,2}日?|\d{4}年\d{1,2}月|\d{4}年|\d{4}-\d{1,2}-\d{1,2}|\d{4}-\d{1,2}|\d{4})"
)


@dataclass(frozen=True)
class QueryPlan:
    """Planner output consumed by the hybrid retriever."""

    planner_mode: str
    query_variants: List[str]
    keyword_terms: List[str]
    structured_filters: StructuredQueryFilters
    reflection_worthwhile: bool
    vector_top_k: int
    lexical_top_k: int
    structured_top_k: int
    rerank_top_k: int


class UserMemoryQueryPlanner:
    """Build deterministic or LLM-assisted query plans."""

    def __init__(self) -> None:
        self._fail_until = 0.0

    def _planner_cfg(self) -> Dict[str, Any]:
        return get_config().get("user_memory.retrieval.planner", {}) or {}

    def _reflection_cfg(self) -> Dict[str, Any]:
        return get_config().get("user_memory.retrieval.reflection", {}) or {}

    def _fanout_defaults(self, mode: str) -> Dict[str, int]:
        if mode == "runtime_light":
            return {
                "vector_top_k": 40,
                "lexical_top_k": 25,
                "structured_top_k": 15,
                "rerank_top_k": 20,
            }
        return {
            "vector_top_k": 40,
            "lexical_top_k": 30,
            "structured_top_k": 20,
            "rerank_top_k": 30,
        }

    def _deterministic_filters(
        self,
        *,
        query_text: str,
        scope_view_types: Optional[Sequence[str]] = None,
    ) -> StructuredQueryFilters:
        normalized = normalize_text(query_text)
        keyword_terms = extract_query_terms(query_text)
        fact_kinds: List[str] = []
        view_types: List[str] = list(scope_view_types or [])
        locations: List[str] = []
        predicates: List[str] = []

        if any(cue in normalized for cue in _PROFILE_CUES):
            if "user_profile" not in view_types:
                view_types.append("user_profile")
            if "preference" not in fact_kinds:
                fact_kinds.append("preference")

        if any(cue in normalized for cue in _EPISODE_CUES):
            if "episode" not in view_types:
                view_types.append("episode")
            if "event" not in fact_kinds:
                fact_kinds.append("event")

        if (
            any(cue in normalized for cue in _RELATIONSHIP_CUES)
            and "relationship" not in fact_kinds
        ):
            fact_kinds.append("relationship")
        for cue, predicate in _RELATIONSHIP_PREDICATE_CUES.items():
            if cue in normalized and predicate not in predicates:
                predicates.append(predicate)

        if any(cue in normalized for cue in _EVENT_CUES) and "event" not in fact_kinds:
            fact_kinds.append("event")

        match = _LOCATION_PATTERN.search(query_text)
        if match:
            locations.append(match.group(1).strip())

        time_start = None
        time_end = None
        fragment = _DATE_FRAGMENT_PATTERN.search(query_text)
        if fragment:
            time_start, time_end = parse_event_time_range(fragment.group(1))

        allow_history = any(
            token in normalized for token in ("以前", "之前", "过去", "history", "曾经")
        )
        if time_start or time_end:
            allow_history = True

        return StructuredQueryFilters(
            persons=[],
            entities=[],
            locations=locations,
            predicates=predicates,
            fact_kinds=fact_kinds,
            view_types=view_types,
            time_range=StructuredTimeRange(start=time_start, end=time_end),
            allow_history=allow_history,
        )

    def _deterministic_plan(
        self,
        *,
        query_text: str,
        mode: str,
        scope_view_types: Optional[Sequence[str]] = None,
    ) -> QueryPlan:
        fanout = self._fanout_defaults(mode)
        structured_filters = self._deterministic_filters(
            query_text=query_text,
            scope_view_types=scope_view_types,
        )
        variants = build_query_variants(query_text)
        keyword_terms = extract_query_terms(query_text)
        reflection_worthwhile = (
            mode == "api_full"
            and len(keyword_terms) >= 2
            and (
                structured_filters.allow_history
                or bool(structured_filters.fact_kinds)
                or bool(structured_filters.view_types)
            )
        )
        return QueryPlan(
            planner_mode=mode,
            query_variants=variants,
            keyword_terms=keyword_terms,
            structured_filters=structured_filters,
            reflection_worthwhile=reflection_worthwhile,
            vector_top_k=fanout["vector_top_k"],
            lexical_top_k=fanout["lexical_top_k"],
            structured_top_k=fanout["structured_top_k"],
            rerank_top_k=fanout["rerank_top_k"],
        )

    def _call_planner_model(self, query_text: str) -> Optional[Dict[str, Any]]:
        cfg = self._planner_cfg()
        provider_name = str(cfg.get("provider") or "").strip()
        model = str(cfg.get("model") or "").strip()
        if not provider_name or not model:
            return None

        now = time.monotonic()
        if now < self._fail_until:
            return None

        provider_cfg = resolve_provider(provider_name)
        base_url = str(provider_cfg.get("base_url") or "").strip()
        if not base_url:
            return None

        timeout = max(float(cfg.get("timeout_seconds") or 4), 1.0)
        headers = {"Content-Type": "application/json"}
        if provider_cfg.get("api_key"):
            headers["Authorization"] = f"Bearer {provider_cfg['api_key']}"

        payload = {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a retrieval planner. Return strict JSON with keys: "
                        "query_variants, keyword_terms, persons, entities, location, "
                        "time_range, fact_kind_hints, predicates, view_scope, allow_history, "
                        "reflection_worthwhile."
                    ),
                },
                {"role": "user", "content": query_text},
            ],
        }
        urls = build_api_url_candidates(base_url, "/chat/completions")
        for url in urls:
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=timeout)
                if response.status_code != 200:
                    continue
                data = response.json()
                content = extract_chat_completion_content(data)
                if not content:
                    continue
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    self._fail_until = 0.0
                    return parsed
            except Exception as exc:
                logger.debug("User-memory planner model call failed: %s", exc)
                continue

        self._fail_until = now + max(float(cfg.get("failure_backoff_seconds") or 60), 1.0)
        return None

    def _merge_llm_plan(
        self,
        *,
        query_text: str,
        base_plan: QueryPlan,
        llm_plan: Dict[str, Any],
    ) -> QueryPlan:
        query_variants = build_query_variants(
            query_text,
            extra_queries=list(llm_plan.get("query_variants") or []),
            max_variants=max(int(self._planner_cfg().get("max_query_variants") or 3), 1),
        )
        keyword_terms = list(
            dict.fromkeys(
                [
                    *base_plan.keyword_terms,
                    *[
                        str(term).strip()
                        for term in list(llm_plan.get("keyword_terms") or [])
                        if str(term).strip()
                    ],
                ]
            )
        )[:12]

        location = str(llm_plan.get("location") or "").strip()
        locations = list(
            dict.fromkeys(
                [*base_plan.structured_filters.locations, *([location] if location else [])]
            )
        )
        fact_kinds = list(
            dict.fromkeys(
                [
                    *base_plan.structured_filters.fact_kinds,
                    *[
                        str(kind).strip()
                        for kind in list(llm_plan.get("fact_kind_hints") or [])
                        if str(kind).strip()
                    ],
                ]
            )
        )

        view_scope = str(llm_plan.get("view_scope") or "").strip()
        view_types = list(
            dict.fromkeys(
                [*base_plan.structured_filters.view_types, *([view_scope] if view_scope else [])]
            )
        )

        time_start = base_plan.structured_filters.time_range.start
        time_end = base_plan.structured_filters.time_range.end
        raw_time_range = llm_plan.get("time_range")
        if isinstance(raw_time_range, dict):
            start_candidate = raw_time_range.get("start")
            end_candidate = raw_time_range.get("end")
            parsed_start, parsed_end = parse_event_time_range(start_candidate)
            parsed_end_start, parsed_end_end = parse_event_time_range(end_candidate)
            time_start = parsed_start or parsed_end_start or time_start
            time_end = parsed_end_end or parsed_end or time_end

        structured_filters = StructuredQueryFilters(
            persons=[
                str(value).strip()
                for value in list(llm_plan.get("persons") or [])
                if str(value).strip()
            ],
            entities=[
                str(value).strip()
                for value in list(llm_plan.get("entities") or [])
                if str(value).strip()
            ],
            locations=locations,
            predicates=[
                str(value).strip()
                for value in list(llm_plan.get("predicates") or [])
                if str(value).strip()
            ]
            or list(base_plan.structured_filters.predicates),
            fact_kinds=fact_kinds,
            view_types=view_types,
            time_range=StructuredTimeRange(start=time_start, end=time_end),
            allow_history=bool(
                llm_plan.get("allow_history", base_plan.structured_filters.allow_history)
            ),
        )
        return QueryPlan(
            planner_mode="api_full",
            query_variants=query_variants,
            keyword_terms=keyword_terms,
            structured_filters=structured_filters,
            reflection_worthwhile=bool(llm_plan.get("reflection_worthwhile", True)),
            vector_top_k=base_plan.vector_top_k,
            lexical_top_k=base_plan.lexical_top_k,
            structured_top_k=base_plan.structured_top_k,
            rerank_top_k=base_plan.rerank_top_k,
        )

    def plan(
        self,
        *,
        query_text: str,
        planner_mode: str,
        scope_view_types: Optional[Sequence[str]] = None,
    ) -> QueryPlan:
        """Build a query plan for runtime or API retrieval."""

        if planner_mode == "runtime_light":
            return self._deterministic_plan(
                query_text=query_text,
                mode="runtime_light",
                scope_view_types=scope_view_types,
            )

        base_plan = self._deterministic_plan(
            query_text=query_text,
            mode="api_full",
            scope_view_types=scope_view_types,
        )
        llm_plan = self._call_planner_model(query_text)
        if not llm_plan:
            fallback = self._deterministic_plan(
                query_text=query_text,
                mode="runtime_light",
                scope_view_types=scope_view_types,
            )
            return QueryPlan(
                planner_mode="runtime_light",
                query_variants=fallback.query_variants,
                keyword_terms=fallback.keyword_terms,
                structured_filters=fallback.structured_filters,
                reflection_worthwhile=False,
                vector_top_k=base_plan.vector_top_k,
                lexical_top_k=base_plan.lexical_top_k,
                structured_top_k=base_plan.structured_top_k,
                rerank_top_k=base_plan.rerank_top_k,
            )
        return self._merge_llm_plan(query_text=query_text, base_plan=base_plan, llm_plan=llm_plan)

    def build_reflection_queries(
        self,
        *,
        query_text: str,
        plan: QueryPlan,
        top_result_content: Optional[str] = None,
    ) -> List[str]:
        """Build at most two reflection queries for API mode follow-up retrieval."""

        cfg = self._reflection_cfg()
        if not _PROFILE_CUES and not cfg:
            return []
        candidates: List[str] = []
        if plan.keyword_terms:
            candidates.append(" ".join(plan.keyword_terms[:4]))
        if top_result_content:
            candidates.append(f"{query_text} {top_result_content[:40]}")
        if plan.structured_filters.locations:
            candidates.append(f"{query_text} {' '.join(plan.structured_filters.locations[:2])}")
        return build_query_variants(query_text, extra_queries=candidates, max_variants=3)[1:3]


_query_planner: Optional[UserMemoryQueryPlanner] = None


def get_user_memory_query_planner() -> UserMemoryQueryPlanner:
    """Return the shared user-memory query planner."""

    global _query_planner
    if _query_planner is None:
        _query_planner = UserMemoryQueryPlanner()
    return _query_planner


__all__ = ["QueryPlan", "UserMemoryQueryPlanner", "get_user_memory_query_planner"]
