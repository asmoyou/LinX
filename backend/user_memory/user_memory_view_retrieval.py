"""Retrieve projected user-memory views."""

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


class UserMemoryViewRetrievalService:
    """Lightweight retrieval over projected user-memory views."""

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
                flattened.extend(UserMemoryViewRetrievalService._flatten_payload(item))
            return flattened
        if isinstance(value, (list, tuple, set)):
            flattened = []
            for item in value:
                flattened.extend(UserMemoryViewRetrievalService._flatten_payload(item))
            return flattened
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
        return re.sub(r"\s+", " ", normalized).strip()

    def _build_search_document(self, row: Any) -> str:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        parts: List[str] = [
            str(row.view_key or ""),
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

    def _query_requests_temporal_context(self, query_text: str) -> bool:
        normalized = self._normalize_text(query_text)
        if not normalized or normalized == "*":
            return False
        return any(cue in normalized for cue in _TEMPORAL_QUERY_CUES)

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

        payload = row.view_data if isinstance(row.view_data, dict) else {}
        quality = self._extract_quality(payload)
        normalized_query = self._normalize_text(query_text)
        exact_match = bool(
            normalized_query and normalized_query != "*" and normalized_query in document
        )

        if not query_terms:
            if normalized_query == "*" or not normalized_query:
                return min(0.35 + 0.25 * quality, 0.92)
            if str(row.view_type) == "user_profile":
                key = str(payload.get("key") or row.view_key or "").strip().lower()
                if key in _GENERAL_USER_PROFILE_KEYS:
                    return min(0.32 + 0.25 * quality, 0.9)
            return 0.0

        hit_count = 0
        for term in query_terms:
            if term and term in document:
                hit_count += 1
        hit_ratio = hit_count / max(len(query_terms), 1)

        view_type = str(row.view_type or "").strip().lower()
        if hit_count == 0:
            if view_type == "user_profile":
                key = str(payload.get("key") or row.view_key or "").strip().lower()
                if key in _GENERAL_USER_PROFILE_KEYS:
                    return min(0.3 + 0.2 * quality, 0.88)
                if self._query_requests_profile_context(query_text):
                    return min(0.24 + 0.2 * quality, 0.82)
            if view_type == "episode" and self._query_requests_temporal_context(query_text):
                anchors = [
                    self._normalize_text(str(payload.get("event_time") or "")),
                    self._normalize_text(str(payload.get("location") or "")),
                    self._normalize_text(str(payload.get("topic") or "")),
                    self._normalize_text(str(payload.get("value") or "")),
                ]
                if any(anchor and anchor in normalized_query for anchor in anchors):
                    return min(0.27 + 0.22 * quality, 0.88)
            return 0.0

        base = 0.24
        if exact_match:
            base += 0.12
        if view_type == "episode" and self._query_requests_temporal_context(query_text):
            base += 0.08
        return min(base + 0.46 * hit_ratio + 0.18 * quality, 0.98)

    @staticmethod
    def _build_user_profile_content(row: Any) -> str:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        canonical_statement = str(payload.get("canonical_statement") or "").strip()
        if canonical_statement:
            return canonical_statement
        key = str(payload.get("key") or row.view_key or "").strip()
        value = str(payload.get("value") or row.summary or "").strip()
        if not key or not value:
            return ""
        return f"user.preference.{key}={value}"

    @staticmethod
    def _build_user_episode_content(row: Any) -> str:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        canonical_statement = str(payload.get("canonical_statement") or row.summary or "").strip()
        if canonical_statement:
            return canonical_statement
        event_time = str(payload.get("event_time") or "").strip()
        value = str(payload.get("value") or row.summary or row.title or "").strip()
        if event_time and value:
            return f"在{event_time}，{value}"
        topic = str(payload.get("topic") or row.title or "").strip()
        if topic and value:
            return f"{topic}：{value}"
        return value

    def _row_to_memory_item(
        self, row: Any, *, memory_type: str, score: float
    ) -> Optional[RetrievedMemoryItem]:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        view_type = str(row.view_type or "").strip().lower()
        if view_type == "user_profile":
            content = self._build_user_profile_content(row)
            signal_type = str(payload.get("fact_kind") or "user_preference")
        elif view_type == "episode":
            content = self._build_user_episode_content(row)
            signal_type = str(payload.get("fact_kind") or "event")
        else:
            content = str(row.summary or row.title or "").strip()
            signal_type = view_type or "view"

        if not content:
            return None

        metadata: Dict[str, Any] = {
            "search_method": "view_projection",
            "memory_source": "user_memory_view",
            "record_type": view_type or "view",
            "view_id": row.id,
            "view_type": view_type,
            "view_key": row.view_key,
            "signal_type": signal_type,
            "timestamp": (
                row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else None
            ),
            "_semantic_score": round(float(score), 4),
        }
        if view_type in {"user_profile", "episode"}:
            metadata["is_active"] = True
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
                    "location",
                    "topic",
                }
            }
        )

        return RetrievedMemoryItem(
            id=int(row.id) if row.id is not None else None,
            content=content,
            memory_type=memory_type,
            agent_id=None,
            user_id=(getattr(row, "owner_id", None) if memory_type == "user_memory" else None),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
            summary=str(row.summary or "").strip() or None,
        )

    def _search_rows(
        self,
        *,
        owner_type: str,
        owner_id: str,
        view_type: str,
        query_text: str,
        top_k: Optional[int],
        memory_type: str,
    ) -> List[RetrievedMemoryItem]:
        rows = self._repository.list_projections(
            owner_type=owner_type,
            owner_id=owner_id,
            projection_type=view_type,
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

        results: List[RetrievedMemoryItem] = []
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
    ) -> List[RetrievedMemoryItem]:
        return self._search_rows(
            owner_type="user",
            owner_id=str(user_id),
            view_type="user_profile",
            query_text=query_text,
            top_k=top_k,
            memory_type="user_memory",
        )

    def retrieve_user_episodes(
        self,
        *,
        user_id: str,
        query_text: str,
        top_k: Optional[int] = 5,
    ) -> List[RetrievedMemoryItem]:
        return self._search_rows(
            owner_type="user",
            owner_id=str(user_id),
            view_type="episode",
            query_text=query_text,
            top_k=top_k,
            memory_type="user_memory",
        )


_user_memory_view_retrieval_service: Optional[UserMemoryViewRetrievalService] = None


def get_user_memory_view_retrieval_service() -> UserMemoryViewRetrievalService:
    """Return a process-wide user-memory view retrieval service."""

    global _user_memory_view_retrieval_service
    if _user_memory_view_retrieval_service is None:
        _user_memory_view_retrieval_service = UserMemoryViewRetrievalService()
    return _user_memory_view_retrieval_service
