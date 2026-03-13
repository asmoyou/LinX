"""Agent access policy helpers for runtime context sources."""

from typing import List, Optional, Tuple

_CONTEXT_SOURCE_ALIASES = {
    "skills": "skills",
    "user_memory": "user_memory",
}


def normalize_allowed_memory_scopes(
    allowed_memory: Optional[List[str]],
) -> Tuple[List[str], List[str]]:
    """Normalize configured runtime context sources and collect invalid values."""
    if not allowed_memory:
        return [], []

    normalized: List[str] = []
    invalid: List[str] = []

    for raw_scope in allowed_memory:
        scope = (raw_scope or "").strip().lower()
        if not scope:
            continue
        canonical = _CONTEXT_SOURCE_ALIASES.get(scope)
        if canonical is None:
            invalid.append(raw_scope)
            continue
        if canonical not in normalized:
            normalized.append(canonical)

    return normalized, invalid


def resolve_memory_scopes(
    access_level: Optional[str],
    allowed_memory: Optional[List[str]],
) -> List[str]:
    """Resolve effective runtime context sources for an agent execution."""
    normalized_scopes, _ = normalize_allowed_memory_scopes(allowed_memory)
    if allowed_memory:
        return normalized_scopes

    _ = (access_level or "private").strip().lower()
    return ["skills", "user_memory"]
