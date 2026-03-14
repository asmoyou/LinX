"""Shared config helpers for reset-era memory routes."""

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from access_control.permissions import CurrentUser
from shared.config import get_config

from .memory_contracts import MemoryConfigResponse, MemoryConfigUpdateRequest

logger = logging.getLogger(__name__)

_RESET_CONFIG_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "user_memory": {
        "embedding": {
            "provider": "",
            "model": "",
            "dimension": 1024,
            "inherit_from_knowledge_base": True,
        },
        "retrieval": {
            "similarity_threshold": 0.3,
        },
        "extraction": {
            "provider": "",
            "model": "",
            "timeout_seconds": 120,
            "max_facts": 10,
            "max_preference_facts": 10,
            "enable_heuristic_fallback": True,
            "secondary_recall_enabled": True,
            "failure_backoff_seconds": 60,
            "fail_closed_empty_writes": True,
        },
        "consolidation": {
            "enabled": True,
            "run_on_startup": True,
            "startup_delay_seconds": 180,
            "interval_seconds": 21600,
            "dry_run": False,
            "limit": 5000,
            "use_advisory_lock": True,
        },
        "observability": {
            "enable_quality_counters": True,
        },
    },
    "skill_learning": {
        "extraction": {
            "provider": "",
            "model": "",
            "timeout_seconds": 120,
            "max_proposals": 6,
            "failure_backoff_seconds": 60,
        },
        "publish_policy": {
            "skill_type": "agent_skill",
            "storage_type": "inline",
            "reuse_existing_by_name": True,
        },
    },
    "session_ledger": {
        "enabled": True,
        "retention_days": 14,
        "run_on_startup": True,
        "startup_delay_seconds": 120,
        "cleanup_interval_seconds": 21600,
        "batch_size": 1000,
        "dry_run": False,
        "use_advisory_lock": True,
    },
    "runtime_context": {
        "enable_user_memory": True,
        "enable_skills": True,
        "enable_knowledge_base": True,
    },
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _dict_section(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _resolve_provider_default_chat_model(llm_section: dict, provider: str) -> str:
    providers_cfg = llm_section.get("providers", {}) if isinstance(llm_section, dict) else {}
    if not isinstance(providers_cfg, dict):
        return ""
    provider_cfg = providers_cfg.get(provider, {})
    if not isinstance(provider_cfg, dict):
        return ""
    raw_models = provider_cfg.get("models")
    if isinstance(raw_models, dict):
        for preferred_key in ("chat", "default", "completion", "instruct"):
            candidate = str(raw_models.get(preferred_key) or "").strip()
            if candidate:
                return candidate
        for value in raw_models.values():
            candidate = str(value or "").strip()
            if candidate:
                return candidate
        return ""
    if isinstance(raw_models, list):
        for value in raw_models:
            candidate = str(value or "").strip()
            if candidate:
                return candidate
        return ""
    return str(raw_models or "").strip()


def _safe_get_section(config: Any, name: str) -> Dict[str, Any]:
    try:
        value = config.get_section(name)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _build_extraction_payload(
    *,
    extraction_cfg: Dict[str, Any],
    defaults: Dict[str, Any],
    llm_section: Dict[str, Any],
    provider_source_key: str,
    model_source_key: str,
) -> Dict[str, Any]:
    llm_default_provider = str(llm_section.get("default_provider") or "").strip()
    merged = _deep_merge(defaults, extraction_cfg)

    configured_provider = str(extraction_cfg.get("provider") or "").strip()
    configured_model = str(extraction_cfg.get("model") or "").strip()
    effective_provider = configured_provider or llm_default_provider
    effective_model = configured_model or _resolve_provider_default_chat_model(
        llm_section,
        effective_provider,
    )
    provider_source = (
        provider_source_key
        if configured_provider
        else ("llm.default_provider" if llm_default_provider else "none")
    )
    model_source = (
        model_source_key
        if configured_model
        else (
            f"llm.providers.{effective_provider}.models.chat"
            if effective_model and effective_provider
            else "none"
        )
    )
    return {
        **merged,
        "effective": {
            "provider": effective_provider,
            "model": effective_model,
        },
        "sources": {
            "provider": provider_source,
            "model": model_source,
        },
    }


def _stored_user_memory_section_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    user_memory_payload = _dict_section(payload.get("user_memory"))
    return {
        "embedding": {
            key: value
            for key, value in _dict_section(user_memory_payload.get("embedding")).items()
            if key not in {"effective", "sources"}
        },
        "retrieval": _dict_section(user_memory_payload.get("retrieval")),
        "extraction": {
            key: value
            for key, value in _dict_section(user_memory_payload.get("extraction")).items()
            if key not in {"effective", "sources"}
        },
        "consolidation": _dict_section(user_memory_payload.get("consolidation")),
        "observability": _dict_section(user_memory_payload.get("observability")),
    }


def _stored_skill_learning_section_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    skill_learning_payload = _dict_section(payload.get("skill_learning"))
    return {
        "extraction": {
            key: value
            for key, value in _dict_section(skill_learning_payload.get("extraction")).items()
            if key not in {"effective", "sources"}
        },
        "publish_policy": _dict_section(skill_learning_payload.get("publish_policy")),
    }


def _build_memory_config_payload(
    user_memory_section: dict,
    skill_learning_section: dict,
    session_ledger_section: dict,
    runtime_context_section: dict,
    kb_section: Optional[dict] = None,
    llm_section: Optional[dict] = None,
) -> dict:
    """Build reset-era config payload with effective resolved settings and source hints."""
    from memory_system.embedding_service import resolve_embedding_settings

    llm_section = llm_section if isinstance(llm_section, dict) else {}

    user_memory_defaults = _RESET_CONFIG_DEFAULTS["user_memory"]
    skill_learning_defaults = _RESET_CONFIG_DEFAULTS["skill_learning"]
    session_ledger_defaults = _RESET_CONFIG_DEFAULTS["session_ledger"]
    runtime_context_defaults = _RESET_CONFIG_DEFAULTS["runtime_context"]

    user_memory_cfg = _dict_section(user_memory_section)
    skill_learning_cfg = _dict_section(skill_learning_section)
    session_ledger_cfg = _dict_section(session_ledger_section)
    runtime_context_cfg = _dict_section(runtime_context_section)

    user_memory_embedding_cfg = _dict_section(user_memory_cfg.get("embedding"))
    user_memory_retrieval_cfg = _dict_section(user_memory_cfg.get("retrieval"))
    user_memory_extraction_cfg = _dict_section(user_memory_cfg.get("extraction"))
    user_memory_consolidation_cfg = _dict_section(user_memory_cfg.get("consolidation"))
    user_memory_observability_cfg = _dict_section(user_memory_cfg.get("observability"))

    skill_learning_extraction_cfg = _dict_section(skill_learning_cfg.get("extraction"))
    skill_learning_publish_cfg = _dict_section(skill_learning_cfg.get("publish_policy"))

    user_memory_embedding = _deep_merge(
        user_memory_defaults["embedding"], user_memory_embedding_cfg
    )
    user_memory_retrieval = {
        "similarity_threshold": max(
            0.0,
            float(
                user_memory_retrieval_cfg.get("similarity_threshold")
                or user_memory_defaults["retrieval"]["similarity_threshold"]
            ),
        )
    }
    user_memory_consolidation = _deep_merge(
        user_memory_defaults["consolidation"], user_memory_consolidation_cfg
    )
    user_memory_observability = _deep_merge(
        user_memory_defaults["observability"], user_memory_observability_cfg
    )
    skill_learning_publish = _deep_merge(
        skill_learning_defaults["publish_policy"], skill_learning_publish_cfg
    )

    session_ledger_payload = _deep_merge(session_ledger_defaults, session_ledger_cfg)
    runtime_context_payload = _deep_merge(runtime_context_defaults, runtime_context_cfg)

    effective_embedding = resolve_embedding_settings(scope="user_memory")
    embedding_payload = {
        **user_memory_embedding,
        "effective": {
            "provider": effective_embedding.get("provider"),
            "model": effective_embedding.get("model"),
            "dimension": effective_embedding.get("dimension"),
        },
        "sources": {
            "provider": effective_embedding.get("provider_source"),
            "model": effective_embedding.get("model_source"),
            "dimension": effective_embedding.get("dimension_source"),
        },
    }

    user_memory_extraction = _build_extraction_payload(
        extraction_cfg=user_memory_extraction_cfg,
        defaults=user_memory_defaults["extraction"],
        llm_section=llm_section,
        provider_source_key="user_memory.extraction.provider",
        model_source_key="user_memory.extraction.model",
    )
    user_memory_extraction["max_facts"] = _coerce_positive_int(
        user_memory_extraction.get("max_facts"),
        int(user_memory_defaults["extraction"]["max_facts"]),
    )
    user_memory_extraction["max_preference_facts"] = _coerce_positive_int(
        user_memory_extraction.get("max_preference_facts"),
        int(user_memory_extraction["max_facts"]),
    )

    skill_learning_extraction = _build_extraction_payload(
        extraction_cfg=skill_learning_extraction_cfg,
        defaults=skill_learning_defaults["extraction"],
        llm_section=llm_section,
        provider_source_key="skill_learning.extraction.provider",
        model_source_key="skill_learning.extraction.model",
    )
    skill_learning_extraction["max_proposals"] = _coerce_positive_int(
        skill_learning_extraction.get("max_proposals"),
        int(skill_learning_defaults["extraction"]["max_proposals"]),
    )

    return {
        "user_memory": {
            "embedding": embedding_payload,
            "retrieval": user_memory_retrieval,
            "extraction": user_memory_extraction,
            "consolidation": user_memory_consolidation,
            "observability": user_memory_observability,
        },
        "skill_learning": {
            "extraction": skill_learning_extraction,
            "publish_policy": skill_learning_publish,
        },
        "session_ledger": session_ledger_payload,
        "runtime_context": runtime_context_payload,
        "recommended": _RESET_CONFIG_DEFAULTS,
    }


async def get_memory_config(
    *,
    current_user: CurrentUser,
) -> MemoryConfigResponse:
    """Get reset-era user-memory and skill-learning configuration."""
    try:
        config = get_config()
        return MemoryConfigResponse(
            **_build_memory_config_payload(
                _safe_get_section(config, "user_memory"),
                _safe_get_section(config, "skill_learning"),
                _safe_get_section(config, "session_ledger"),
                _safe_get_section(config, "runtime_context"),
                _safe_get_section(config, "knowledge_base"),
                _safe_get_section(config, "llm"),
            )
        )
    except Exception as exc:
        logger.error("Failed to get memory config: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get memory configuration: {exc}",
        ) from exc


async def update_memory_config(
    *,
    update_data: MemoryConfigUpdateRequest,
    current_user: CurrentUser,
) -> MemoryConfigResponse:
    """Update reset-era memory configuration. Requires admin role."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update memory configuration",
        )

    try:
        import os

        import yaml

        from shared.config import reload_config

        config_path = os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml")
        config_path = os.path.abspath(config_path)

        with open(config_path, "r", encoding="utf-8") as file_obj:
            raw_config = yaml.safe_load(file_obj) or {}

        merged_user_memory = _dict_section(raw_config.get("user_memory"))
        merged_skill_learning = _dict_section(raw_config.get("skill_learning"))
        merged_session_ledger = _dict_section(raw_config.get("session_ledger"))
        merged_runtime_context = _dict_section(raw_config.get("runtime_context"))

        if update_data.user_memory is not None:
            merged_user_memory = _deep_merge(merged_user_memory, update_data.user_memory)
        if update_data.skill_learning is not None:
            merged_skill_learning = _deep_merge(merged_skill_learning, update_data.skill_learning)
        if update_data.session_ledger is not None:
            merged_session_ledger = _deep_merge(merged_session_ledger, update_data.session_ledger)
        if update_data.runtime_context is not None:
            merged_runtime_context = _deep_merge(
                merged_runtime_context, update_data.runtime_context
            )

        canonical_payload = _build_memory_config_payload(
            merged_user_memory,
            merged_skill_learning,
            merged_session_ledger,
            merged_runtime_context,
            _dict_section(raw_config.get("knowledge_base")),
            _dict_section(raw_config.get("llm")),
        )
        raw_config["user_memory"] = _stored_user_memory_section_from_payload(canonical_payload)
        raw_config["skill_learning"] = _stored_skill_learning_section_from_payload(
            canonical_payload
        )
        raw_config["session_ledger"] = _dict_section(canonical_payload.get("session_ledger"))
        raw_config["runtime_context"] = _dict_section(canonical_payload.get("runtime_context"))

        with open(config_path, "w", encoding="utf-8") as file_obj:
            yaml.dump(
                raw_config,
                file_obj,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        reloaded = reload_config(config_path)
        return MemoryConfigResponse(
            **_build_memory_config_payload(
                _safe_get_section(reloaded, "user_memory"),
                _safe_get_section(reloaded, "skill_learning"),
                _safe_get_section(reloaded, "session_ledger"),
                _safe_get_section(reloaded, "runtime_context"),
                _safe_get_section(reloaded, "knowledge_base"),
                _safe_get_section(reloaded, "llm"),
            )
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update memory config: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update memory configuration: {exc}",
        ) from exc
