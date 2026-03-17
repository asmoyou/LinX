"""Helpers for stable skill slug generation."""

from __future__ import annotations

import re
from uuid import uuid4


_NON_SLUG_CHARS = re.compile(r"[^a-z0-9_-]+")
_REPEATED_SEPARATORS = re.compile(r"[_-]{2,}")


def normalize_skill_slug(raw_value: str) -> str:
    """Normalize free-form text into a machine-safe skill slug."""
    text = str(raw_value or "").strip().lower().replace(" ", "_")
    text = _NON_SLUG_CHARS.sub("_", text)
    text = _REPEATED_SEPARATORS.sub("_", text).strip("_-")
    return text or f"skill_{uuid4().hex[:8]}"


def generate_unique_skill_slug(raw_value: str, registry) -> str:
    """Generate a unique slug against the current registry contents."""
    base_slug = normalize_skill_slug(raw_value)
    candidate = base_slug
    while registry.get_skill_by_slug(candidate) is not None:
        candidate = f"{base_slug}_{uuid4().hex[:6]}"
    return candidate
