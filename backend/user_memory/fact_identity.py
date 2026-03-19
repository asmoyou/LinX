"""Stable server-side identity helpers for user-memory facts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Any, Iterable, Optional, Sequence

_ALLOWED_FACT_KINDS = {
    "preference",
    "identity",
    "relationship",
    "experience",
    "expertise",
    "goal",
    "constraint",
    "habit",
    "event",
}
_SINGLE_VALUED_PREFERENCE_KEYS = {
    "output_format",
    "language",
    "response_language",
    "response_style",
    "budget_preference",
}
_SINGLE_VALUED_RELATIONSHIPS = {
    "spouse",
    "partner",
    "mother",
    "father",
    "son",
    "daughter",
    "child",
}


@dataclass(frozen=True)
class UserFactIdentity:
    fact_kind: str
    semantic_key: str
    fact_key: str
    identity_signature: str


def normalize_memory_key(value: Any, max_chars: int = 80) -> Optional[str]:
    key = str(value or "").strip().lower()
    if not key:
        return None
    key = re.sub(r"[^a-z0-9_]+", "_", key)
    key = re.sub(r"_+", "_", key).strip("_")
    if not key:
        return None
    if len(key) > max_chars:
        key = key[:max_chars].rstrip("_")
    return key or None


def normalize_fact_kind(value: Any) -> str:
    fact_kind = normalize_memory_key(value, max_chars=32) or "preference"
    if fact_kind == "skill":
        fact_kind = "expertise"
    if fact_kind in _ALLOWED_FACT_KINDS:
        return fact_kind
    return "preference"


def normalize_identity_text(value: Any, max_chars: int = 240) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    if not text:
        return ""
    text = text.replace("将和", "将与").replace("和小", "与小")
    text = text.replace("一起和", "一起与")
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def _normalize_compact_text(value: Any, max_chars: int = 240) -> str:
    return "".join(
        ch for ch in normalize_identity_text(value, max_chars=max_chars) if not ch.isspace()
    )


def _normalize_event_basis_text(value: Any, max_chars: int = 200) -> str:
    text = _normalize_compact_text(value, max_chars=max_chars)
    if not text:
        return ""
    text = re.sub(r"\d{4}年\d{1,2}月\d{1,2}日?", "", text)
    text = re.sub(r"\d{4}-\d{1,2}-\d{1,2}", "", text)
    text = (
        text.replace("将与", "与")
        .replace("将和", "与")
        .replace("一起去", "")
        .replace("一起", "")
    )
    while True:
        updated = text
        for prefix in ("用户", "我", "计划", "打算", "准备", "将会", "将", "会", "要"):
            if updated.startswith(prefix):
                updated = updated[len(prefix) :]
        if updated == text:
            break
        text = updated
    return text


def _hash_parts(*parts: Any) -> str:
    payload = "||".join(str(part or "").strip() for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def build_stable_identity_key(prefix: str, *parts: Any) -> str:
    payload = "||".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _first_normalized(values: Optional[Sequence[Any]], *, max_chars: int = 160) -> str:
    for value in values or []:
        normalized = normalize_identity_text(value, max_chars=max_chars)
        if normalized:
            return normalized
    return ""


def _join_normalized(values: Optional[Iterable[Any]], *, max_chars: int = 160) -> str:
    normalized = {
        normalize_identity_text(value, max_chars=max_chars)
        for value in (values or [])
        if normalize_identity_text(value, max_chars=max_chars)
    }
    return "|".join(sorted(normalized))


def _normalize_relationship_predicate(
    *,
    raw_key: Optional[str],
    predicate: Optional[str],
) -> str:
    relation = normalize_memory_key(predicate, max_chars=48)
    if not relation:
        raw_relation = normalize_memory_key(raw_key, max_chars=80) or ""
        if raw_relation.startswith("relationship_"):
            relation = raw_relation[len("relationship_") :]
    relation = relation or "related"
    if relation not in _SINGLE_VALUED_RELATIONSHIPS and "_" in relation:
        relation_prefix = relation.split("_", 1)[0].strip()
        if relation_prefix:
            relation = relation_prefix
    return relation or "related"


def build_user_fact_semantic_key(
    *,
    fact_kind: Any,
    raw_key: Optional[str],
    predicate: Optional[str] = None,
    obj: Optional[str] = None,
    topic: Optional[str] = None,
    value: Optional[str] = None,
) -> str:
    normalized_fact_kind = normalize_fact_kind(fact_kind)
    normalized_key = normalize_memory_key(raw_key, max_chars=80)
    normalized_predicate = normalize_memory_key(predicate, max_chars=48)
    normalized_object = normalize_memory_key(obj, max_chars=48)
    normalized_topic = normalize_memory_key(topic, max_chars=48)
    normalized_value = normalize_memory_key(value, max_chars=48)
    if normalized_fact_kind == "relationship":
        return f"relationship_{_normalize_relationship_predicate(raw_key=normalized_key, predicate=predicate)}"
    if normalized_fact_kind == "event":
        if normalized_key and normalized_key not in {"event", "user_fact"}:
            return normalized_key
        if normalized_topic:
            return f"event_{normalized_topic}"[:80]
        return "important_event"
    if normalized_key and normalized_key not in {"user_fact"}:
        return normalized_key
    if normalized_fact_kind == "preference":
        if normalized_topic and normalized_predicate:
            return f"{normalized_topic}_{normalized_predicate}"[:80]
        if normalized_topic:
            return normalized_topic
        if normalized_predicate:
            return f"preference_{normalized_predicate}"[:80]
    if normalized_topic:
        return f"{normalized_fact_kind}_{normalized_topic}"[:80]
    if normalized_predicate:
        return f"{normalized_fact_kind}_{normalized_predicate}"[:80]
    if normalized_object:
        return f"{normalized_fact_kind}_{normalized_object}"[:80]
    if normalized_value and normalized_fact_kind == "identity":
        return f"{normalized_fact_kind}_{normalized_value}"[:80]
    return normalized_fact_kind


def build_user_fact_identity(
    *,
    fact_kind: Any,
    raw_key: Optional[str],
    value: Any,
    canonical_statement: Optional[str] = None,
    predicate: Optional[str] = None,
    obj: Optional[str] = None,
    persons: Optional[Sequence[Any]] = None,
    entities: Optional[Sequence[Any]] = None,
    event_time: Optional[str] = None,
    location: Optional[str] = None,
    topic: Optional[str] = None,
) -> UserFactIdentity:
    normalized_fact_kind = normalize_fact_kind(fact_kind)
    semantic_key = build_user_fact_semantic_key(
        fact_kind=normalized_fact_kind,
        raw_key=raw_key,
        predicate=predicate,
        obj=obj,
        topic=topic,
        value=value,
    )
    normalized_canonical = _normalize_compact_text(canonical_statement, max_chars=240)
    normalized_value = _normalize_compact_text(value, max_chars=160)
    normalized_object = _normalize_compact_text(obj, max_chars=160) or _first_normalized(
        persons,
        max_chars=160,
    )
    normalized_persons = _join_normalized(persons, max_chars=160)
    normalized_entities = _join_normalized(entities, max_chars=160)
    normalized_event_time = _normalize_compact_text(event_time, max_chars=48)
    normalized_location = _normalize_compact_text(location, max_chars=96)
    normalized_topic = _normalize_compact_text(topic, max_chars=96)

    if normalized_fact_kind == "relationship":
        relation = _normalize_relationship_predicate(raw_key=raw_key, predicate=predicate)
        relation_target = (
            normalized_object
            or normalized_persons
            or normalized_entities
            or normalized_canonical
            or normalized_value
        )
        identity_signature = f"relationship|{relation}|{relation_target}"
        if relation in _SINGLE_VALUED_RELATIONSHIPS:
            fact_key = semantic_key
        else:
            fact_key = f"{semantic_key}_{_hash_parts(identity_signature)}"
        return UserFactIdentity(
            fact_kind=normalized_fact_kind,
            semantic_key=semantic_key,
            fact_key=fact_key,
            identity_signature=identity_signature,
        )

    if normalized_fact_kind == "event":
        text_basis = _normalize_event_basis_text(value) or _normalize_event_basis_text(
            canonical_statement
        )
        event_basis = text_basis or normalized_topic or semantic_key
        participant_basis = ""
        if not text_basis:
            participant_basis = normalized_persons or normalized_entities
        identity_signature = f"event|{normalized_event_time}|{event_basis}|{participant_basis}"
        time_token = normalize_memory_key(normalized_event_time, max_chars=24) or "undated"
        fact_key = f"event_{time_token}_{_hash_parts(identity_signature)}"
        return UserFactIdentity(
            fact_kind=normalized_fact_kind,
            semantic_key=semantic_key,
            fact_key=fact_key[:255],
            identity_signature=identity_signature,
        )

    basis = normalized_canonical or normalized_value or normalized_object or semantic_key
    if normalized_fact_kind == "preference":
        if semantic_key in _SINGLE_VALUED_PREFERENCE_KEYS:
            identity_signature = f"{normalized_fact_kind}|{semantic_key}"
            fact_key = semantic_key
        else:
            identity_signature = f"{normalized_fact_kind}|{basis}"
            fact_key = f"{normalized_fact_kind}_{_hash_parts(identity_signature)}"
    elif normalized_fact_kind in {
        "experience",
        "expertise",
        "goal",
        "identity",
        "constraint",
        "habit",
    }:
        identity_signature = f"{normalized_fact_kind}|{basis}"
        fact_key = f"{normalized_fact_kind}_{_hash_parts(identity_signature)}"
    else:
        identity_signature = f"{normalized_fact_kind}|{basis}"
        fact_key = semantic_key or f"user_fact_{_hash_parts(identity_signature)}"

    return UserFactIdentity(
        fact_kind=normalized_fact_kind,
        semantic_key=semantic_key,
        fact_key=fact_key[:255],
        identity_signature=identity_signature,
    )


def build_user_memory_view_key(
    *,
    view_type: Any,
    stable_key: str,
    canonical_statement: Optional[str],
    event_time: Optional[str],
    value: Any,
) -> str:
    normalized_view_type = normalize_memory_key(view_type, max_chars=32) or "user_profile"
    stable_key = str(stable_key or "").strip()
    if normalized_view_type == "episode":
        return build_stable_identity_key(
            "episode",
            stable_key or event_time or canonical_statement or value or "",
        )
    return stable_key


__all__ = [
    "UserFactIdentity",
    "build_user_fact_identity",
    "build_stable_identity_key",
    "build_user_memory_view_key",
    "build_user_fact_semantic_key",
    "normalize_fact_kind",
    "normalize_identity_text",
    "normalize_memory_key",
]
