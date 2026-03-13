"""Helpers for reading knowledge base configuration safely."""

from typing import Any


def load_knowledge_base_config(config: Any) -> dict[str, Any]:
    """Return the knowledge_base section with safe fallbacks.

    Supports both the real Config object and lightweight test doubles that may
    only expose ``get_section``.
    """
    if config is None:
        return {}

    getter = getattr(config, "get", None)
    if callable(getter):
        kb_config = getter("knowledge_base", {})
        if isinstance(kb_config, dict):
            return kb_config

    get_section = getattr(config, "get_section", None)
    if callable(get_section):
        try:
            kb_config = get_section("knowledge_base")
        except Exception:
            return {}
        if isinstance(kb_config, dict):
            return kb_config

    return {}
