"""Shared config and maintenance helpers for reset-era memory routes."""

import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException, status

from access_control.permissions import CurrentUser
from shared.config import get_config

from .memory_contracts import (
    MaterializationMaintenanceResponse,
    MemoryConfigResponse,
    MemoryConfigUpdateRequest,
)

logger = logging.getLogger(__name__)

_RUNTIME_CONTEXT_NUMERIC_KEYS = (
    "collection_retry_attempts",
    "collection_retry_delay_seconds",
    "search_timeout_seconds",
    "delete_timeout_seconds",
)

_RESET_CONFIG_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "user_memory": {
        "retention": {
            "enabled": True,
            "retention_days": 365,
            "max_entries_per_user": 5000,
        },
        "embedding": {
            "provider": "",
            "model": "",
            "dimension": 1024,
            "inherit_from_knowledge_base": True,
        },
        "retrieval": {
            "top_k": 10,
            "similarity_threshold": 0.3,
            "similarity_weight": 0.7,
            "recency_weight": 0.3,
            "strict_keyword_fallback": True,
            "enable_reranking": True,
            "rerank_weight": 0.75,
            "rerank_provider": "",
            "rerank_model": "",
            "rerank_top_k": 30,
            "rerank_timeout_seconds": 8,
            "rerank_failure_backoff_seconds": 30,
            "rerank_doc_max_chars": 1200,
            "milvus": {
                "metric_type": "L2",
                "nprobe": 10,
            },
        },
        "extraction": {
            "enabled": True,
            "model_enabled": True,
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
        "retention": {
            "enabled": True,
            "retention_days": 90,
            "max_proposals_per_agent": 10000,
        },
        "extraction": {
            "enabled": True,
            "provider": "",
            "model": "",
            "timeout_seconds": 120,
            "max_proposals": 6,
            "failure_backoff_seconds": 60,
        },
        "proposal_review": {
            "require_human_review": True,
            "allow_revise": True,
            "default_review_status": "pending",
        },
        "publish_policy": {
            "enabled": True,
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
        "collection_retry_attempts": 3,
        "collection_retry_delay_seconds": 0.35,
        "search_timeout_seconds": 2.0,
        "delete_timeout_seconds": 2.0,
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
        provider_source_key if configured_provider else ("llm.default_provider" if llm_default_provider else "none")
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

    kb_section = kb_section if isinstance(kb_section, dict) else {}
    llm_section = llm_section if isinstance(llm_section, dict) else {}
    kb_search = kb_section.get("search", {}) if isinstance(kb_section.get("search"), dict) else {}

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
    user_memory_retention_cfg = _dict_section(user_memory_cfg.get("retention"))

    skill_learning_extraction_cfg = _dict_section(skill_learning_cfg.get("extraction"))
    skill_learning_review_cfg = _dict_section(skill_learning_cfg.get("proposal_review"))
    skill_learning_publish_cfg = _dict_section(skill_learning_cfg.get("publish_policy"))
    skill_learning_retention_cfg = _dict_section(skill_learning_cfg.get("retention"))

    user_memory_embedding = _deep_merge(user_memory_defaults["embedding"], user_memory_embedding_cfg)
    user_memory_retrieval = _deep_merge(user_memory_defaults["retrieval"], user_memory_retrieval_cfg)
    user_memory_consolidation = _deep_merge(user_memory_defaults["consolidation"], user_memory_consolidation_cfg)
    user_memory_observability = _deep_merge(user_memory_defaults["observability"], user_memory_observability_cfg)
    user_memory_retention = _deep_merge(user_memory_defaults["retention"], user_memory_retention_cfg)

    skill_learning_review = _deep_merge(skill_learning_defaults["proposal_review"], skill_learning_review_cfg)
    skill_learning_publish = _deep_merge(skill_learning_defaults["publish_policy"], skill_learning_publish_cfg)
    skill_learning_retention = _deep_merge(skill_learning_defaults["retention"], skill_learning_retention_cfg)

    session_ledger_payload = _deep_merge(session_ledger_defaults, session_ledger_cfg)
    runtime_context_payload = _deep_merge(runtime_context_defaults, runtime_context_cfg)

    effective_embedding = resolve_embedding_settings(scope="user_memory")
    effective_rerank_provider = (
        str(user_memory_retrieval_cfg.get("rerank_provider") or "").strip()
        or str(kb_search.get("rerank_provider") or "").strip()
    )
    effective_rerank_model = (
        str(user_memory_retrieval_cfg.get("rerank_model") or "").strip()
        or str(kb_search.get("rerank_model") or "").strip()
    )
    rerank_provider_source = (
        "user_memory.retrieval.rerank_provider"
        if str(user_memory_retrieval_cfg.get("rerank_provider") or "").strip()
        else (
            "knowledge_base.search.rerank_provider"
            if str(kb_search.get("rerank_provider") or "").strip()
            else "none"
        )
    )
    rerank_model_source = (
        "user_memory.retrieval.rerank_model"
        if str(user_memory_retrieval_cfg.get("rerank_model") or "").strip()
        else (
            "knowledge_base.search.rerank_model"
            if str(kb_search.get("rerank_model") or "").strip()
            else "none"
        )
    )
    retrieval_payload = {
        **user_memory_retrieval,
        "rerank_provider": effective_rerank_provider,
        "rerank_model": effective_rerank_model,
        "sources": {
            "rerank_provider": rerank_provider_source,
            "rerank_model": rerank_model_source,
        },
    }
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
            "retention": user_memory_retention,
            "embedding": embedding_payload,
            "retrieval": retrieval_payload,
            "extraction": user_memory_extraction,
            "consolidation": user_memory_consolidation,
            "observability": user_memory_observability,
        },
        "skill_learning": {
            "retention": skill_learning_retention,
            "extraction": skill_learning_extraction,
            "proposal_review": skill_learning_review,
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
            raw_config = yaml.safe_load(file_obj)

        if update_data.user_memory is not None:
            raw_config["user_memory"] = _deep_merge(
                _dict_section(raw_config.get("user_memory")),
                update_data.user_memory,
            )
        if update_data.skill_learning is not None:
            raw_config["skill_learning"] = _deep_merge(
                _dict_section(raw_config.get("skill_learning")),
                update_data.skill_learning,
            )
        if update_data.session_ledger is not None:
            raw_config["session_ledger"] = _deep_merge(
                _dict_section(raw_config.get("session_ledger")),
                update_data.session_ledger,
            )
        if update_data.runtime_context is not None:
            runtime_context = _dict_section(raw_config.get("runtime_context"))
            for key, value in update_data.runtime_context.items():
                if key in _RUNTIME_CONTEXT_NUMERIC_KEYS or key.startswith("enable_"):
                    runtime_context[key] = value
                else:
                    runtime_context[key] = value
            raw_config["runtime_context"] = runtime_context

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


async def maintain_materializations(
    *,
    dry_run: bool,
    user_id: Optional[str],
    agent_id: Optional[str],
    limit: Optional[int],
    current_user: CurrentUser,
) -> MaterializationMaintenanceResponse:
    """Admin maintenance entry for materialization consolidation."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can run materialization maintenance",
        )

    from user_memory.materialization_maintenance_service import (
        get_materialization_maintenance_service,
    )

    service = get_materialization_maintenance_service()
    try:
        result = await asyncio.to_thread(
            service.run_maintenance,
            dry_run=dry_run,
            user_id=user_id,
            agent_id=agent_id,
            limit=limit,
        )
    except Exception as exc:
        logger.error("Materialization maintenance failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Materialization maintenance failed: {exc}",
        ) from exc

    payload = service.to_dict(result)
    payload["requested_by"] = {
        "user_id": current_user.user_id,
        "role": current_user.role,
    }
    return MaterializationMaintenanceResponse(**payload)
