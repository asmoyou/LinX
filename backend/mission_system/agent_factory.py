"""Agent factory for mission execution.

Provides reusable functions for instantiating BaseAgent instances
with LLM providers, extracting the pattern from agents.py router.
"""

import logging
from typing import Any, Optional
from uuid import UUID

from agent_framework.base_agent import AgentConfig, BaseAgent
from agent_framework.agent_registry import AgentRegistry
from llm_providers.custom_openai_provider import CustomOpenAIChat

logger = logging.getLogger(__name__)


def _to_positive_int(value: Any) -> Optional[int]:
    """Best-effort parse for positive integer values."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _resolve_model_context_window(
    provider: Any,
    provider_name: str,
    model_name: str,
) -> Optional[int]:
    """Resolve model context window from provider metadata or detector fallback."""
    if provider and provider.model_metadata and model_name in provider.model_metadata:
        metadata = provider.model_metadata.get(model_name) or {}
        context_window = _to_positive_int(
            metadata.get("context_window") or metadata.get("context_length")
        )
        if context_window:
            return context_window

    try:
        from llm_providers.model_metadata import EnhancedModelCapabilityDetector

        detector = EnhancedModelCapabilityDetector()
        detected = detector.detect_metadata(model_name, provider_name)
        return _to_positive_int(detected.context_window)
    except Exception as detect_error:
        logger.warning(
            "Failed to resolve model context window via detector: %s",
            detect_error,
        )
        return None


async def create_mission_agent(
    agent_config: AgentConfig,
    llm_provider: str = "ollama",
    llm_model: str = "qwen2.5:14b",
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> BaseAgent:
    """Create and initialize a BaseAgent with LLM from database provider config.

    Args:
        agent_config: The AgentConfig for the agent.
        llm_provider: Provider name (e.g. "ollama").
        llm_model: Model name (e.g. "qwen2.5:14b").
        temperature: LLM temperature.
        max_tokens: Max tokens for generation.

    Returns:
        An initialized BaseAgent ready for task execution.

    Raises:
        ValueError: If the LLM provider cannot be loaded.
    """
    agent = BaseAgent(agent_config)

    llm = None
    resolved_context_window: Optional[int] = None

    from database.connection import get_db_session
    from llm_providers.db_manager import ProviderDBManager

    with get_db_session() as db:
        db_manager = ProviderDBManager(db)
        db_provider = db_manager.get_provider(llm_provider)

        if db_provider and db_provider.enabled:
            resolved_context_window = _resolve_model_context_window(
                provider=db_provider,
                provider_name=llm_provider,
                model_name=llm_model,
            )

            if db_provider.protocol == "openai_compatible":
                api_key = None
                if db_provider.api_key_encrypted:
                    api_key = db_manager._decrypt_api_key(db_provider.api_key_encrypted)
                llm = CustomOpenAIChat(
                    base_url=db_provider.base_url,
                    model=llm_model,
                    temperature=temperature,
                    api_key=api_key,
                    timeout=db_provider.timeout,
                    max_retries=db_provider.max_retries,
                    max_tokens=max_tokens,
                    streaming=True,
                )
            elif db_provider.protocol == "ollama":
                llm = CustomOpenAIChat(
                    base_url=db_provider.base_url,
                    model=llm_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    api_key=None,
                    timeout=db_provider.timeout,
                    max_retries=db_provider.max_retries,
                    streaming=True,
                )

            logger.info(
                "Created LLM for mission agent: provider=%s, model=%s",
                llm_provider,
                llm_model,
            )
        else:
            raise ValueError(f"Provider '{llm_provider}' not found or disabled in database")

    if llm is None:
        raise ValueError(f"Could not create LLM for provider: {llm_provider}")

    agent.llm = llm
    if resolved_context_window:
        agent.config.context_window_tokens = resolved_context_window

    await agent.initialize()
    return agent


async def create_registered_mission_agent(
    agent_id: UUID,
    owner_user_id: UUID,
    max_iterations: int = 20,
) -> Optional[BaseAgent]:
    """Create a mission execution agent from an existing platform agent definition.

    Returns None when the requested agent does not exist or is not owned by the user.
    """
    registry = AgentRegistry()
    agent_info = registry.get_agent(agent_id)
    if agent_info is None:
        return None
    if agent_info.owner_user_id != owner_user_id:
        return None

    config = AgentConfig(
        agent_id=agent_info.agent_id,
        name=agent_info.name,
        agent_type=agent_info.agent_type,
        owner_user_id=owner_user_id,
        capabilities=agent_info.capabilities or [],
        access_level=agent_info.access_level or "private",
        allowed_knowledge=agent_info.allowed_knowledge or [],
        llm_model=agent_info.llm_model or "qwen2.5:14b",
        temperature=agent_info.temperature or 0.7,
        max_iterations=max_iterations,
        system_prompt=agent_info.system_prompt,
    )
    return await create_mission_agent(
        agent_config=config,
        llm_provider=agent_info.llm_provider or "ollama",
        llm_model=agent_info.llm_model or "qwen2.5:14b",
        temperature=agent_info.temperature or 0.7,
        max_tokens=agent_info.max_tokens or 4096,
    )
