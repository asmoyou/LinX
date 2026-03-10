"""Retrieve materialized memory projections for prompt injection."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from memory_system.memory_interface import MemoryItem, MemoryType
from memory_system.session_ledger_repository import (
    SessionLedgerRepository,
    get_session_ledger_repository,
)

_STOP_TERMS = {
    "如何",
    "怎么",
    "怎样",
    "请问",
    "一下",
    "可以",
    "是否",
    "这个",
    "那个",
    "什么",
    "是谁",
    "what",
    "how",
    "who",
    "where",
    "when",
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "to",
    "of",
    "in",
    "on",
}
_GENERAL_USER_PROFILE_KEYS = {"response_style", "output_format", "language"}
_PROFILE_QUERY_CUES = {
    "prefer",
    "preference",
    "style",
    "format",
    "language",
    "habit",
    "profile",
    "偏好",
    "喜欢",
    "口味",
    "习惯",
    "风格",
    "格式",
    "语言",
    "历史",
}


class MaterializationRetrievalService:
    """Lightweight retrieval over materialized session projections."""

    def __init__(self, repository: Optional[SessionLedgerRepository] = None):
        self._repository = repository or get_session_ledger_repository()

    @staticmethod
    def _extract_query_terms(query_text: str, *, max_terms: int = 12) -> List[str]:
        normalized = unicodedata.normalize("NFKC", str(query_text or "")).strip().lower()
        if not normalized or normalized == "*":
            return []

        terms = set()
        for token in re.findall(r"[a-z0-9][a-z0-9._-]{1,}", normalized):
            if token not in _STOP_TERMS:
                terms.add(token)

        split_terms = re.split(
            r"[\s,，。！？!?;；:：/\\|()\[\]{}【】\"'“”‘’]+",
            normalized,
        )
        for token in split_terms:
            token = token.strip()
            if len(token) >= 2 and token not in _STOP_TERMS:
                terms.add(token)

        for fragment in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", normalized):
            if len(fragment) >= 2 and fragment not in _STOP_TERMS:
                terms.add(fragment)
            for size in (2, 3, 4):
                if len(fragment) < size:
                    continue
                for idx in range(len(fragment) - size + 1):
                    gram = fragment[idx : idx + size]
                    if gram and gram not in _STOP_TERMS:
                        terms.add(gram)

        return sorted(terms, key=lambda item: (-len(item), item))[: max(int(max_terms), 1)]

    @staticmethod
    def _flatten_payload(value: Any) -> Iterable[str]:
        if value is None:
            return []
        if isinstance(value, dict):
            flattened: List[str] = []
            for item in value.values():
                flattened.extend(MaterializationRetrievalService._flatten_payload(item))
            return flattened
        if isinstance(value, (list, tuple, set)):
            flattened = []
            for item in value:
                flattened.extend(MaterializationRetrievalService._flatten_payload(item))
            return flattened
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
        return re.sub(r"\s+", " ", normalized).strip()

    def _build_search_document(self, row: Any) -> str:
        payload = row.materialized_data if isinstance(row.materialized_data, dict) else {}
        parts: List[str] = [
            str(row.materialization_key or ""),
            str(row.title or ""),
            str(row.summary or ""),
            str(row.details or ""),
        ]
        parts.extend(self._flatten_payload(payload))
        return self._normalize_text(" ".join(part for part in parts if part))

    def _query_requests_profile_context(self, query_text: str) -> bool:
        normalized = self._normalize_text(query_text)
        if not normalized or normalized == "*":
            return False
        return any(cue in normalized for cue in _PROFILE_QUERY_CUES)

    @staticmethod
    def _extract_quality(payload: Dict[str, Any]) -> float:
        for key in ("importance", "confidence"):
            value = payload.get(key)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            return min(max(numeric, 0.0), 1.0)
        return 0.0

    def _score_row(self, row: Any, *, query_text: str, query_terms: List[str]) -> float:
        document = self._build_search_document(row)
        if not document:
            return 0.0

        payload = row.materialized_data if isinstance(row.materialized_data, dict) else {}
        quality = self._extract_quality(payload)
        normalized_query = self._normalize_text(query_text)
        exact_match = bool(
            normalized_query and normalized_query != "*" and normalized_query in document
        )

        if not query_terms:
            if normalized_query == "*" or not normalized_query:
                return min(0.35 + 0.25 * quality, 0.92)
            if str(row.materialization_type) == "user_profile":
                key = str(payload.get("key") or row.materialization_key or "").strip().lower()
                if key in _GENERAL_USER_PROFILE_KEYS:
                    return min(0.32 + 0.25 * quality, 0.9)
            return 0.0

        hit_count = 0
        for term in query_terms:
            if term and term in document:
                hit_count += 1
        hit_ratio = hit_count / max(len(query_terms), 1)

        materialization_type = str(row.materialization_type or "").strip().lower()
        if hit_count == 0:
            if materialization_type == "user_profile":
                key = str(payload.get("key") or row.materialization_key or "").strip().lower()
                if key in _GENERAL_USER_PROFILE_KEYS:
                    return min(0.3 + 0.2 * quality, 0.88)
                if self._query_requests_profile_context(query_text):
                    return min(0.24 + 0.2 * quality, 0.82)
            return 0.0

        base = 0.28 if materialization_type == "agent_experience" else 0.24
        if exact_match:
            base += 0.12
        return min(base + 0.46 * hit_ratio + 0.18 * quality, 0.98)

    @staticmethod
    def _build_user_profile_content(row: Any) -> str:
        payload = row.materialized_data if isinstance(row.materialized_data, dict) else {}
        key = str(payload.get("key") or row.materialization_key or "").strip()
        value = str(payload.get("value") or row.summary or "").strip()
        if not key or not value:
            return ""
        return f"user.preference.{key}={value}"

    @staticmethod
    def _build_agent_experience_content(row: Any) -> str:
        payload = row.materialized_data if isinstance(row.materialized_data, dict) else {}
        goal = str(payload.get("goal") or row.title or "").strip()
        steps = [
            str(step).strip() for step in payload.get("successful_path") or [] if str(step).strip()
        ]
        why_it_worked = str(payload.get("why_it_worked") or row.summary or "").strip()
        applicability = str(payload.get("applicability") or "").strip()
        avoid = str(payload.get("avoid") or "").strip()

        if not goal:
            return ""

        lines = [f"agent.experience.goal={goal}"]
        if steps:
            lines.append(f"agent.experience.successful_path={' | '.join(steps)}")
        if why_it_worked:
            lines.append(f"agent.experience.why_it_worked={why_it_worked}")
        if applicability:
            lines.append(f"agent.experience.applicability={applicability}")
        if avoid:
            lines.append(f"agent.experience.avoid={avoid}")
        return "\n".join(lines)

    def _row_to_memory_item(
        self, row: Any, *, memory_type: MemoryType, score: float
    ) -> Optional[MemoryItem]:
        materialization_type = str(row.materialization_type or "").strip().lower()
        if materialization_type == "user_profile":
            content = self._build_user_profile_content(row)
            signal_type = "user_preference"
        elif materialization_type == "agent_experience":
            content = self._build_agent_experience_content(row)
            signal_type = "agent_success_path"
        else:
            content = str(row.summary or row.title or "").strip()
            signal_type = materialization_type or "materialization"

        if not content:
            return None

        payload = row.materialized_data if isinstance(row.materialized_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": "materialization",
            "memory_source": "materialization",
            "materialization_id": row.id,
            "materialization_type": materialization_type,
            "materialization_key": row.materialization_key,
            "signal_type": signal_type,
            "timestamp": (
                row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else None
            ),
            "_semantic_score": round(float(score), 4),
        }
        if materialization_type == "user_profile":
            metadata["is_active"] = True
        metadata.update(
            {k: v for k, v in payload.items() if k in {"confidence", "importance", "key", "value"}}
        )

        return MemoryItem(
            id=int(row.id) if row.id is not None else None,
            content=content,
            memory_type=memory_type,
            agent_id=getattr(row, "owner_id", None) if memory_type == MemoryType.AGENT else None,
            user_id=(
                getattr(row, "owner_id", None) if memory_type == MemoryType.USER_CONTEXT else None
            ),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    def _search_rows(
        self,
        *,
        owner_type: str,
        owner_id: str,
        materialization_type: str,
        query_text: str,
        top_k: Optional[int],
        memory_type: MemoryType,
    ) -> List[MemoryItem]:
        rows = self._repository.list_materializations(
            owner_type=owner_type,
            owner_id=owner_id,
            materialization_type=materialization_type,
            status="active",
            limit=(max(int(top_k), 1) * 8) if top_k is not None else None,
        )
        query_terms = self._extract_query_terms(query_text)
        scored_rows: List[tuple[float, Any]] = []
        for row in rows:
            score = self._score_row(row, query_text=query_text, query_terms=query_terms)
            if score <= 0:
                continue
            scored_rows.append((score, row))

        scored_rows.sort(
            key=lambda item: (
                float(item[0]),
                getattr(item[1], "updated_at", None)
                or getattr(item[1], "created_at", None)
                or datetime.min,
            ),
            reverse=True,
        )

        results: List[MemoryItem] = []
        selected_rows = scored_rows[: max(int(top_k), 1)] if top_k is not None else scored_rows
        for score, row in selected_rows:
            item = self._row_to_memory_item(row, memory_type=memory_type, score=score)
            if item is not None:
                results.append(item)
        return results

    def retrieve_user_profile(
        self,
        *,
        user_id: str,
        query_text: str,
        top_k: Optional[int] = 5,
    ) -> List[MemoryItem]:
        """Return user-profile materializations relevant to the query."""

        return self._search_rows(
            owner_type="user",
            owner_id=str(user_id),
            materialization_type="user_profile",
            query_text=query_text,
            top_k=top_k,
            memory_type=MemoryType.USER_CONTEXT,
        )

    def retrieve_agent_experience(
        self,
        *,
        agent_id: str,
        query_text: str,
        top_k: Optional[int] = 5,
    ) -> List[MemoryItem]:
        """Return reusable agent-success-path projections relevant to the task."""

        return self._search_rows(
            owner_type="agent",
            owner_id=str(agent_id),
            materialization_type="agent_experience",
            query_text=query_text,
            top_k=top_k,
            memory_type=MemoryType.AGENT,
        )


_materialization_retrieval_service: Optional[MaterializationRetrievalService] = None


def get_materialization_retrieval_service() -> MaterializationRetrievalService:
    """Return a process-wide materialization retrieval service."""

    global _materialization_retrieval_service
    if _materialization_retrieval_service is None:
        _materialization_retrieval_service = MaterializationRetrievalService()
    return _materialization_retrieval_service
