"""Resolve LLM provider config from database (primary) or config.yaml (fallback).

All knowledge pipeline components (ChunkEnricher, VisionParser, EmbeddingService)
should use this to look up provider base_url and protocol, instead of directly
reading from config.yaml which only has initial/default providers.

The authoritative provider source is the `llm_providers` database table,
managed via the LLM settings page. config.yaml providers are only used
as fallback for backward compatibility or first-boot initialization.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def resolve_provider(provider_name: str) -> dict:
    """Resolve a provider's config by name.

    Lookup order:
    1. Database `llm_providers` table (authoritative source)
    2. config.yaml `llm.providers.{name}` (fallback)

    Args:
        provider_name: Provider name (e.g. "ollama", "vllm", "llm-pool")

    Returns:
        dict with keys: base_url, protocol, models.
        Empty dict if provider not found anywhere.
    """
    # 1. Try database first
    result = _resolve_from_db(provider_name)
    if result:
        return result

    # 2. Fallback to config.yaml
    result = _resolve_from_config(provider_name)
    if result:
        return result

    logger.warning(f"Provider '{provider_name}' not found in DB or config.yaml")
    return {}


def _resolve_from_db(provider_name: str) -> Optional[dict]:
    """Look up provider from database."""
    try:
        from database.connection import get_db_session
        from database.models import LLMProvider

        with get_db_session() as session:
            provider = (
                session.query(LLMProvider)
                .filter(LLMProvider.name == provider_name)
                .first()
            )
            if provider and provider.enabled:
                protocol = provider.protocol or "openai_compatible"
                return {
                    "base_url": provider.base_url,
                    "protocol": protocol,
                    "models": provider.models or [],
                }
    except Exception as e:
        logger.debug(f"DB provider lookup failed for '{provider_name}': {e}")

    return None


def _resolve_from_config(provider_name: str) -> Optional[dict]:
    """Look up provider from config.yaml."""
    try:
        from shared.config import get_config

        config = get_config()
        if not config:
            return None

        llm_config = config.get_section("llm")
        providers = llm_config.get("providers", {})
        provider_cfg = providers.get(provider_name, {})

        if provider_cfg and provider_cfg.get("base_url"):
            # Infer protocol from provider name
            protocol = "ollama" if provider_name == "ollama" else "openai_compatible"
            models_cfg = provider_cfg.get("models", {})
            models = list(models_cfg.values()) if isinstance(models_cfg, dict) else models_cfg
            return {
                "base_url": provider_cfg["base_url"],
                "protocol": protocol,
                "models": models,
            }
    except Exception as e:
        logger.debug(f"Config provider lookup failed for '{provider_name}': {e}")

    return None
