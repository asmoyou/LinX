"""Agent access policy helpers.

Defines normalization and effective-scope resolution for agent-level
access configuration such as allowed memory scopes.
"""

from typing import List, Optional, Tuple


_MEMORY_SCOPE_ALIASES = {
    "agent": "agent",
    "agent_memories": "agent",
    "company": "company",
    "company_memories": "company",
    "user_context": "user_context",
    "task_context": "task_context",
}


def normalize_allowed_memory_scopes(
    allowed_memory: Optional[List[str]],
) -> Tuple[List[str], List[str]]:
    """Normalize configured memory scopes and collect invalid values."""
    if not allowed_memory:
        return [], []

    normalized: List[str] = []
    invalid: List[str] = []

    for raw_scope in allowed_memory:
        scope = (raw_scope or "").strip().lower()
        if not scope:
            continue
        canonical = _MEMORY_SCOPE_ALIASES.get(scope)
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
    """Resolve effective memory scopes for an agent execution."""
    normalized_scopes, _ = normalize_allowed_memory_scopes(allowed_memory)
    if normalized_scopes:
        return normalized_scopes

    level = (access_level or "private").strip().lower()
    if level in {"team", "public"}:
        return ["agent", "company", "user_context"]
    return ["agent", "user_context"]
