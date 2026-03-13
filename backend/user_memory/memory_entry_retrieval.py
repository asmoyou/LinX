"""Retrieve atomic memory entries for prompt injection and maintenance checks."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from user_memory.items import RetrievedMemoryItem
from user_memory.session_ledger_repository import (
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
_GENERAL_USER_FACT_KEYS = {"response_style", "output_format", "language"}
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
_TEMPORAL_QUERY_CUES = {
    "什么时候",
    "何时",
    "哪年",
    "哪月",
    "哪天",
    "时间",
    "when",
    "time",
}


class MemoryEntryRetrievalService:
    """Lightweight retrieval over atomic memory entries."""

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
                flattened.extend(MemoryEntryRetrievalService._flatten_payload(item))
            return flattened
        if isinstance(value, (list, tuple, set)):
            flattened = []
            for item in value:
                flattened.extend(MemoryEntryRetrievalService._flatten_payload(item))
            return flattened
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
        return re.sub(r"\s+", " ", normalized).strip()

    def _build_search_document(self, row: Any) -> str:
        payload = row.entry_data if isinstance(row.entry_data, dict) else {}
        parts: List[str] = [
            str(row.entry_key or ""),
            str(row.canonical_text or ""),
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

    def _query_requests_temporal_context(self, query_text: str) -> bool:
        normalized = self._normalize_text(query_text)
        if not normalized or normalized == "*":
            return False
        return any(cue in normalized for cue in _TEMPORAL_QUERY_CUES)

    @staticmethod
    def _extract_quality(payload: Dict[str, Any], row: Any) -> float:
        for key in ("importance", "confidence"):
            value = payload.get(key)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            return min(max(numeric, 0.0), 1.0)
        for value in (getattr(row, "importance", None), getattr(row, "confidence", None)):
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

        payload = row.entry_data if isinstance(row.entry_data, dict) else {}
        quality = self._extract_quality(payload, row)
        normalized_query = self._normalize_text(query_text)
        exact_match = bool(
            normalized_query and normalized_query != "*" and normalized_query in document
        )
        entry_type = str(row.entry_type or "").strip().lower()
        fact_kind = str(payload.get("fact_kind") or "").strip().lower()

        if not query_terms:
            if normalized_query == "*" or not normalized_query:
                return min(0.34 + 0.25 * quality, 0.92)
            if entry_type == "user_fact":
                key = str(payload.get("key") or row.entry_key or "").strip().lower()
                if key in _GENERAL_USER_FACT_KEYS:
                    return min(0.31 + 0.24 * quality, 0.9)
                if self._query_requests_profile_context(query_text):
                    return min(0.26 + 0.2 * quality, 0.84)
            return 0.0

        hit_count = 0
        for term in query_terms:
            if term and term in document:
                hit_count += 1
        hit_ratio = hit_count / max(len(query_terms), 1)

        if hit_count == 0:
            if entry_type == "user_fact":
                key = str(payload.get("key") or row.entry_key or "").strip().lower()
                if key in _GENERAL_USER_FACT_KEYS:
                    return min(0.28 + 0.18 * quality, 0.84)
                if fact_kind == "event" and self._query_requests_temporal_context(query_text):
                    anchors = [
                        self._normalize_text(str(payload.get("location") or "")),
                        self._normalize_text(str(payload.get("topic") or "")),
                        self._normalize_text(str(payload.get("value") or "")),
                    ]
                    if any(anchor and anchor in normalized_query for anchor in anchors):
                        return min(0.26 + 0.22 * quality, 0.86)
                if self._query_requests_profile_context(query_text):
                    return min(0.22 + 0.18 * quality, 0.8)
            return 0.0

        base = 0.27 if entry_type == "agent_skill_candidate" else 0.23
        if exact_match:
            base += 0.12
        if fact_kind == "event" and self._query_requests_temporal_context(query_text):
            base += 0.08
        return min(base + 0.46 * hit_ratio + 0.18 * quality, 0.98)

    def _row_to_memory_item(
        self, row: Any, *, memory_type: str, score: float
    ) -> Optional[RetrievedMemoryItem]:
        content = str(row.canonical_text or "").strip()
        if not content:
            return None

        payload = row.entry_data if isinstance(row.entry_data, dict) else {}
        entry_type = str(row.entry_type or "").strip().lower()
        metadata: Dict[str, Any] = {
            "search_method": "entry",
            "memory_source": "entry",
            "record_type": entry_type or "entry",
            "entry_id": row.id,
            "entry_type": entry_type,
            "entry_key": row.entry_key,
            "signal_type": (
                str(payload.get("fact_kind") or "user_preference")
                if entry_type == "user_fact"
                else (
                    "agent_success_path"
                    if entry_type == "agent_skill_candidate"
                    else entry_type or "entry"
                )
            ),
            "status": getattr(row, "status", None),
            "timestamp": (
                row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else None
            ),
            "_semantic_score": round(float(score), 4),
        }
        metadata.update(
            {
                k: v
                for k, v in payload.items()
                if k
                in {
                    "confidence",
                    "importance",
                    "key",
                    "value",
                    "fact_kind",
                    "semantic_key",
                    "canonical_statement",
                    "event_time",
                }
            }
        )

        return RetrievedMemoryItem(
            id=int(row.id) if row.id is not None else None,
            content=content,
            memory_type=memory_type,
            agent_id=getattr(row, "owner_id", None) if memory_type == "skill_experience" else None,
            user_id=(getattr(row, "owner_id", None) if memory_type == "user_memory" else None),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    def _search_rows(
        self,
        *,
        owner_type: str,
        owner_id: str,
        entry_type: str,
        query_text: str,
        top_k: Optional[int],
        memory_type: str,
        status: Optional[str] = "active",
    ) -> List[RetrievedMemoryItem]:
        rows = self._repository.list_entries(
            owner_type=owner_type,
            owner_id=owner_id,
            entry_type=entry_type,
            status=status,
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

        results: List[RetrievedMemoryItem] = []
        selected_rows = scored_rows[: max(int(top_k), 1)] if top_k is not None else scored_rows
        for score, row in selected_rows:
            item = self._row_to_memory_item(row, memory_type=memory_type, score=score)
            if item is not None:
                results.append(item)
        return results

    def retrieve_user_facts(
        self,
        *,
        user_id: str,
        query_text: str,
        top_k: Optional[int] = 5,
        status: Optional[str] = "active",
    ) -> List[RetrievedMemoryItem]:
        """Return user-fact entries relevant to the query."""

        return self._search_rows(
            owner_type="user",
            owner_id=str(user_id),
            entry_type="user_fact",
            query_text=query_text,
            top_k=top_k,
            memory_type="user_memory",
            status=status,
        )

    def retrieve_agent_skill_candidates(
        self,
        *,
        agent_id: str,
        query_text: str,
        top_k: Optional[int] = 5,
        status: Optional[str] = "active",
    ) -> List[RetrievedMemoryItem]:
        """Return agent skill-candidate entries relevant to the query."""

        return self._search_rows(
            owner_type="agent",
            owner_id=str(agent_id),
            entry_type="agent_skill_candidate",
            query_text=query_text,
            top_k=top_k,
            memory_type="skill_experience",
            status=status,
        )


_memory_entry_retrieval_service: Optional[MemoryEntryRetrievalService] = None


def get_memory_entry_retrieval_service() -> MemoryEntryRetrievalService:
    """Return a process-wide memory-entry retrieval service."""

    global _memory_entry_retrieval_service
    if _memory_entry_retrieval_service is None:
        _memory_entry_retrieval_service = MemoryEntryRetrievalService()
    return _memory_entry_retrieval_service
