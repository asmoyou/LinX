"""Lexical helpers and candidate scoring for user-memory retrieval."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from sqlalchemy import or_
from sqlalchemy.sql import func

from database.connection import get_db_session
from database.models import UserMemoryEntry, UserMemoryView
from user_memory.items import RetrievedMemoryItem
from user_memory.vector_documents import build_entry_vector_content, build_view_vector_content

STOP_TERMS = {
    "如何",
    "怎么",
    "怎样",
    "请问",
    "一下",
    "一下子",
    "可以",
    "是否",
    "这个",
    "那个",
    "什么",
    "是谁",
    "what",
    "how",
    "why",
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

_TOKEN_SPLIT_PATTERN = re.compile(r"[\s,，。！？!?;；:：/\\|()\[\]{}【】\"'“”‘’]+")
_LATIN_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9._-]{1,}")
_CJK_FRAGMENT_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")


def normalize_text(text: object) -> str:
    """Normalize text for lexical matching."""

    normalized = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"\s+", " ", normalized).strip()


def is_wildcard_query(query_text: str) -> bool:
    """Return True when the query should bypass full retrieval planning."""

    normalized = normalize_text(query_text)
    return normalized in {"", "*"}


def flatten_payload(value: Any) -> List[str]:
    """Flatten nested payloads into a list of lexical strings."""

    if value is None:
        return []
    if isinstance(value, dict):
        flattened: List[str] = []
        for item in value.values():
            flattened.extend(flatten_payload(item))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(flatten_payload(item))
        return flattened

    text = str(value).strip()
    return [text] if text else []


def build_search_document(*parts: object, payload: Any = None) -> str:
    """Build one normalized lexical document from fields and payload values."""

    doc_parts = [str(part).strip() for part in parts if str(part or "").strip()]
    if payload is not None:
        doc_parts.extend(flatten_payload(payload))
    return normalize_text(" ".join(doc_parts))


def extract_query_terms(query_text: str, *, max_terms: int = 12) -> List[str]:
    """Extract normalized query terms for lexical retrieval and reranking."""

    normalized = normalize_text(query_text)
    if is_wildcard_query(normalized):
        return []

    terms = set()
    for token in _LATIN_TOKEN_PATTERN.findall(normalized):
        if token not in STOP_TERMS:
            terms.add(token)

    for token in _TOKEN_SPLIT_PATTERN.split(normalized):
        stripped = token.strip()
        if len(stripped) >= 2 and stripped not in STOP_TERMS:
            terms.add(stripped)

    for fragment in _CJK_FRAGMENT_PATTERN.findall(normalized):
        if len(fragment) >= 2 and fragment not in STOP_TERMS:
            terms.add(fragment)
        for size in (2, 3, 4):
            if len(fragment) < size:
                continue
            for idx in range(len(fragment) - size + 1):
                gram = fragment[idx : idx + size]
                if gram and gram not in STOP_TERMS:
                    terms.add(gram)

    return sorted(terms, key=lambda item: (-len(item), item))[: max(int(max_terms), 1)]


def build_query_variants(
    query_text: str,
    *,
    extra_queries: Sequence[str] | None = None,
    max_variants: int = 6,
) -> List[str]:
    """Build deduplicated query variants while preserving the original query first."""

    variants: List[str] = []
    seen = set()
    for candidate in [query_text, *(extra_queries or [])]:
        value = str(candidate or "").strip()
        normalized = normalize_text(value)
        if not value or normalized in seen:
            continue
        seen.add(normalized)
        variants.append(value)
        if len(variants) >= max(int(max_variants), 1):
            break
    return variants


@dataclass(slots=True)
class LexicalMatch:
    """Structured lexical score details for one candidate document."""

    score: float
    matched_terms: List[str] = field(default_factory=list)
    exact_match: bool = False
    phrase_match: bool = False
    coverage: float = 0.0


class LexicalSearchEngine:
    """Score normalized lexical documents against one user-memory query."""

    def score_document(
        self,
        *,
        query_text: str,
        query_terms: Sequence[str],
        document: str,
        quality: float = 0.0,
        query_variants: Sequence[str] | None = None,
    ) -> LexicalMatch:
        normalized_query = normalize_text(query_text)
        normalized_document = normalize_text(document)
        if not normalized_document or is_wildcard_query(normalized_query):
            return LexicalMatch(score=0.0)

        matched_terms = [term for term in query_terms if term and term in normalized_document]
        coverage = len(matched_terms) / max(len(query_terms), 1) if query_terms else 0.0
        exact_match = bool(
            normalized_query
            and normalized_query not in STOP_TERMS
            and normalized_query in normalized_document
        )
        phrase_match = any(
            normalize_text(variant) in normalized_document
            for variant in (query_variants or [])
            if normalize_text(variant)
        )

        if not matched_terms and not exact_match and not phrase_match:
            return LexicalMatch(score=0.0)

        base = 0.14
        if exact_match:
            base += 0.18
        if phrase_match:
            base += 0.12
        score = min(base + 0.46 * coverage + 0.12 * min(max(float(quality), 0.0), 1.0), 0.98)
        return LexicalMatch(
            score=round(float(score), 4),
            matched_terms=matched_terms[:16],
            exact_match=exact_match,
            phrase_match=phrase_match,
            coverage=round(float(coverage), 4),
        )


__all__ = [
    "LexicalMatch",
    "LexicalSearchEngine",
    "STOP_TERMS",
    "build_query_variants",
    "build_search_document",
    "extract_query_terms",
    "flatten_payload",
    "is_wildcard_query",
    "normalize_text",
]


class UserMemoryLexicalSearchService:
    """PostgreSQL-backed lexical candidate generation for entries and views."""

    def __init__(self) -> None:
        self._engine = LexicalSearchEngine()

    @staticmethod
    def _entry_to_item(
        row: Any,
        *,
        score: float,
        match: LexicalMatch,
    ) -> RetrievedMemoryItem:
        payload = row.entry_data if isinstance(row.entry_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": "lexical",
            "search_methods": ["lexical"],
            "memory_source": "entry",
            "record_type": "user_fact",
            "entry_id": row.id,
            "entry_key": row.entry_key,
            "fact_kind": row.fact_kind,
            "status": row.status,
            "_lexical_score": round(float(score), 4),
            "_lexical_terms": list(match.matched_terms),
            "_lexical_coverage": match.coverage,
        }
        metadata.update(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "fact_kind",
                    "semantic_key",
                    "identity_signature",
                    "canonical_statement",
                    "event_time",
                    "location",
                    "topic",
                    "persons",
                    "entities",
                }
            }
        )
        content = str(row.canonical_text or "").strip()
        return RetrievedMemoryItem(
            id=int(row.id),
            content=content,
            summary=str(row.summary or "").strip() or None,
            memory_type="user_memory",
            user_id=str(row.user_id),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    @staticmethod
    def _view_to_item(
        row: Any,
        *,
        score: float,
        match: LexicalMatch,
    ) -> RetrievedMemoryItem:
        payload = row.view_data if isinstance(row.view_data, dict) else {}
        metadata: Dict[str, Any] = {
            "search_method": "lexical",
            "search_methods": ["lexical"],
            "memory_source": "user_memory_view",
            "record_type": str(row.view_type or "view"),
            "view_id": row.id,
            "view_key": row.view_key,
            "view_type": row.view_type,
            "status": row.status,
            "_lexical_score": round(float(score), 4),
            "_lexical_terms": list(match.matched_terms),
            "_lexical_coverage": match.coverage,
        }
        metadata.update(
            {
                key: value
                for key, value in payload.items()
                if key
                in {
                    "fact_kind",
                    "semantic_key",
                    "identity_signature",
                    "canonical_statement",
                    "event_time",
                    "location",
                    "topic",
                }
            }
        )
        content = str(row.content or row.title or "").strip()
        return RetrievedMemoryItem(
            id=int(row.id),
            content=content,
            summary=str(row.content or "").strip() or None,
            memory_type="user_memory",
            user_id=str(row.user_id),
            timestamp=row.updated_at or row.created_at,
            metadata=metadata,
            similarity_score=round(float(score), 4),
        )

    def _query_entry_rows(
        self,
        *,
        user_id: str,
        normalized_query: str,
        query_terms: Sequence[str],
        statuses: Sequence[str],
        fact_kinds: Optional[Sequence[str]] = None,
        limit: int,
    ) -> List[Any]:
        safe_limit = max(int(limit), 1)
        with get_db_session() as session:
            query = session.query(UserMemoryEntry).filter(UserMemoryEntry.user_id == str(user_id))
            if statuses:
                query = query.filter(UserMemoryEntry.status.in_(list(statuses)))
            if fact_kinds:
                query = query.filter(UserMemoryEntry.fact_kind.in_(list(fact_kinds)))

            if normalized_query and query_terms:
                patterns = [f"%{term}%" for term in query_terms[:8]]
                filters = [
                    UserMemoryEntry.search_vector.op("@@")(
                        func.plainto_tsquery("simple", normalized_query)
                    )
                ]
                for pattern in patterns:
                    filters.extend(
                        [
                            UserMemoryEntry.canonical_text.ilike(pattern),
                            UserMemoryEntry.summary.ilike(pattern),
                            UserMemoryEntry.entry_key.ilike(pattern),
                            UserMemoryEntry.event_time.ilike(pattern),
                            UserMemoryEntry.location.ilike(pattern),
                            UserMemoryEntry.topic.ilike(pattern),
                        ]
                    )
                query = query.filter(or_(*filters))

            query = query.order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
            return list(query.limit(safe_limit).all())

    def _query_view_rows(
        self,
        *,
        user_id: str,
        normalized_query: str,
        query_terms: Sequence[str],
        statuses: Sequence[str],
        view_types: Optional[Sequence[str]] = None,
        limit: int,
    ) -> List[Any]:
        safe_limit = max(int(limit), 1)
        with get_db_session() as session:
            query = session.query(UserMemoryView).filter(UserMemoryView.user_id == str(user_id))
            if statuses:
                query = query.filter(UserMemoryView.status.in_(list(statuses)))
            if view_types:
                query = query.filter(UserMemoryView.view_type.in_(list(view_types)))

            if normalized_query and query_terms:
                patterns = [f"%{term}%" for term in query_terms[:8]]
                filters = [
                    UserMemoryView.search_vector.op("@@")(
                        func.plainto_tsquery("simple", normalized_query)
                    )
                ]
                for pattern in patterns:
                    filters.extend(
                        [
                            UserMemoryView.content.ilike(pattern),
                            UserMemoryView.title.ilike(pattern),
                            UserMemoryView.view_key.ilike(pattern),
                        ]
                    )
                query = query.filter(or_(*filters))

            query = query.order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
            return list(query.limit(safe_limit).all())

    def search_entries(
        self,
        *,
        user_id: str,
        query_text: str,
        top_k: int,
        statuses: Sequence[str],
        fact_kinds: Optional[Sequence[str]] = None,
        query_variants: Optional[Sequence[str]] = None,
    ) -> List[RetrievedMemoryItem]:
        normalized_query = normalize_text(query_text)
        query_terms = extract_query_terms(query_text)
        try:
            rows = self._query_entry_rows(
                user_id=user_id,
                normalized_query=normalized_query,
                query_terms=query_terms,
                statuses=statuses,
                fact_kinds=fact_kinds,
                limit=max(int(top_k), 1) * 6,
            )
        except Exception:
            with get_db_session() as session:
                rows = list(
                    session.query(UserMemoryEntry)
                    .filter(
                        UserMemoryEntry.user_id == str(user_id),
                        UserMemoryEntry.status.in_(list(statuses)),
                    )
                    .order_by(UserMemoryEntry.updated_at.desc(), UserMemoryEntry.id.desc())
                    .limit(max(int(top_k), 1) * 8)
                    .all()
                )

        scored: List[RetrievedMemoryItem] = []
        for row in rows:
            document = build_entry_vector_content(row)
            match = self._engine.score_document(
                query_text=query_text,
                query_terms=query_terms,
                document=document,
                quality=max(float(row.importance or 0.0), float(row.confidence or 0.0)),
                query_variants=query_variants,
            )
            if match.score <= 0:
                continue
            scored.append(self._entry_to_item(row, score=match.score, match=match))

        scored.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                (
                    item.timestamp
                    if isinstance(item.timestamp, datetime)
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
            reverse=True,
        )
        return scored[: max(int(top_k), 1)]

    def search_views(
        self,
        *,
        user_id: str,
        query_text: str,
        top_k: int,
        statuses: Sequence[str],
        view_types: Optional[Sequence[str]] = None,
        query_variants: Optional[Sequence[str]] = None,
    ) -> List[RetrievedMemoryItem]:
        normalized_query = normalize_text(query_text)
        query_terms = extract_query_terms(query_text)
        try:
            rows = self._query_view_rows(
                user_id=user_id,
                normalized_query=normalized_query,
                query_terms=query_terms,
                statuses=statuses,
                view_types=view_types,
                limit=max(int(top_k), 1) * 6,
            )
        except Exception:
            with get_db_session() as session:
                query = session.query(UserMemoryView).filter(
                    UserMemoryView.user_id == str(user_id),
                    UserMemoryView.status.in_(list(statuses)),
                )
                if view_types:
                    query = query.filter(UserMemoryView.view_type.in_(list(view_types)))
                rows = list(
                    query.order_by(UserMemoryView.updated_at.desc(), UserMemoryView.id.desc())
                    .limit(max(int(top_k), 1) * 8)
                    .all()
                )

        scored: List[RetrievedMemoryItem] = []
        for row in rows:
            document = build_view_vector_content(row)
            payload = row.view_data if isinstance(row.view_data, dict) else {}
            match = self._engine.score_document(
                query_text=query_text,
                query_terms=query_terms,
                document=document,
                quality=max(
                    float(payload.get("importance") or 0.0),
                    float(payload.get("confidence") or 0.0),
                ),
                query_variants=query_variants,
            )
            if match.score <= 0:
                continue
            scored.append(self._view_to_item(row, score=match.score, match=match))

        scored.sort(
            key=lambda item: (
                float(item.similarity_score or 0.0),
                (
                    item.timestamp
                    if isinstance(item.timestamp, datetime)
                    else datetime.min.replace(tzinfo=timezone.utc)
                ),
            ),
            reverse=True,
        )
        return scored[: max(int(top_k), 1)]


_lexical_search_service: Optional[UserMemoryLexicalSearchService] = None


def get_user_memory_lexical_search_service() -> UserMemoryLexicalSearchService:
    """Return the shared lexical search service."""

    global _lexical_search_service
    if _lexical_search_service is None:
        _lexical_search_service = UserMemoryLexicalSearchService()
    return _lexical_search_service


__all__.extend(
    [
        "UserMemoryLexicalSearchService",
        "get_user_memory_lexical_search_service",
    ]
)
