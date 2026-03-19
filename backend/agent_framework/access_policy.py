"""Agent access policy helpers for runtime context sources."""

from typing import List, Optional


def resolve_memory_scopes(access_level: Optional[str]) -> List[str]:
    """Resolve effective runtime context sources for an agent execution."""
    _ = (access_level or "private").strip().lower()
    return ["skills", "user_memory"]
