"""
LLM Provider Router with Lazy Loading

Routes requests to appropriate LLM providers with on-demand initialization.

Key Design Principles:
1. Lazy Loading: Providers initialized only when first used
2. Database-First: Always reads latest config from database
3. Auto-Refresh: Config changes take effect immediately (no manual reload)
4. Memory Efficient: Only active providers kept in memory
5. Optional Caching: Configurable TTL to avoid repeated initialization

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.2: Model Selection Strategy
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from llm_providers.anthropic_provider import AnthropicProvider
from llm_providers.base import BaseLLMProvider, EmbeddingResponse, LLMResponse, TaskType
from llm_providers.openai_compatible import model_names_match
from llm_providers.ollama_provider import OllamaProvider
from llm_providers.openai_provider import OpenAIProvider
from llm_providers.provider_resolver import resolve_provider
from llm_providers.vllm_provider import VLLMProvider

logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM requests to appropriate providers with lazy loading.

    Architecture:
    - No pre-loading: Providers created on first use
    - Database priority: User configs override system defaults
    - Cache with TTL: Optional performance optimization
    - Stateless: Each request gets fresh config from database
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM Router with lazy loading.

        Args:
            config: Configuration dict with keys:
                - providers: Dict of provider configs from config.yaml (system defaults)
                - model_mapping: Task type to model mapping
                - fallback_enabled: Enable fallback to cloud providers
                - max_retries: Maximum retry attempts (default: 3)
                - retry_delay: Initial retry delay in seconds (default: 1)
                - cache_ttl: Provider cache TTL in seconds (default: 300, 0 to disable)

        Provider Priority:
        1. Database (user-configured via UI) - Always checked first
        2. Config.yaml (system defaults) - Fallback only
        """
        self.config = config
        self.model_mapping = config.get("model_mapping", {})
        self.fallback_enabled = config.get("fallback_enabled", False)
        self.prefer_config_providers = bool(config.get("prefer_config_providers", False))
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 1)
        self.cache_ttl = config.get("cache_ttl", 300)  # 5 minutes default
        self.default_provider = str(config.get("default_provider", "") or "").strip() or None

        # Provider cache: {provider_name: (provider_instance, timestamp)}
        self._provider_cache: Dict[str, tuple[BaseLLMProvider, float]] = {}
        self._cache_lock = asyncio.Lock()

        # Token usage tracking
        self.token_usage: Dict[str, int] = {}

        # Config.yaml providers (read-only system defaults)
        self._config_providers = config.get("providers", {})
        self.providers = self._config_providers

        logger.info("=" * 70)
        logger.info("LLMRouter initialized with LAZY LOADING architecture")
        logger.info("- Cache TTL: %ds (0 = disabled)", self.cache_ttl)
        logger.info("- Config.yaml providers: %s", list(self._config_providers.keys()))
        logger.info("- Default provider: %s", self.default_provider or "<none>")
        logger.info("- Prefer config providers: %s", self.prefer_config_providers)
        logger.info("- Database providers: Loaded on-demand")
        logger.info("- No pre-loading: Providers created when first used")
        logger.info("=" * 70)

    async def _get_provider(self, provider_name: str) -> Optional[BaseLLMProvider]:
        """
        Get provider instance with lazy loading and optional caching.

        Flow:
        1. Check cache (if enabled and not expired)
        2. Load from database (user config)
        3. Load from config.yaml (system default)
        4. Cache result (if caching enabled)

        Args:
            provider_name: Name of the provider

        Returns:
            Provider instance or None if not found
        """
        async with self._cache_lock:
            # Check cache first (if enabled)
            if self.cache_ttl > 0 and provider_name in self._provider_cache:
                provider, timestamp = self._provider_cache[provider_name]
                age = time.time() - timestamp

                if age < self.cache_ttl:
                    logger.debug(f"Cache HIT: {provider_name} (age: {age:.1f}s)")
                    return provider
                else:
                    logger.debug(f"Cache EXPIRED: {provider_name} (age: {age:.1f}s)")
                    del self._provider_cache[provider_name]

            # Load provider fresh from database or config
            logger.info(f"Loading provider: {provider_name}")
            provider = await self._load_provider(provider_name)

            if provider:
                # Cache if enabled
                if self.cache_ttl > 0:
                    self._provider_cache[provider_name] = (provider, time.time())
                    logger.info(f"✓ Loaded and cached: {provider_name}")
                else:
                    logger.info(f"✓ Loaded (no cache): {provider_name}")
            else:
                logger.warning(f"✗ Provider not found: {provider_name}")

            return provider

    async def _load_provider(self, provider_name: str) -> Optional[BaseLLMProvider]:
        """
        Load provider from database only.

        Config.yaml providers are synced to database on startup.

        Args:
            provider_name: Name of the provider

        Returns:
            Provider instance or None
        """
        if self.prefer_config_providers:
            provider_config = self._config_providers.get(provider_name)
            if isinstance(provider_config, dict):
                logger.info(f"  → Loading from CONFIG (preferred): {provider_name}")
                return self._create_provider_from_config(provider_name, provider_config)

        # Load from database first unless config is explicitly preferred
        try:
            from database.connection import get_db_session
            from llm_providers.db_manager import ProviderDBManager

            with get_db_session() as db:
                db_manager = ProviderDBManager(db)
                db_provider = db_manager.get_provider(provider_name)

                if db_provider and db_provider.enabled:
                    logger.info(f"  → Loading from DATABASE: {provider_name}")
                    return await self._create_provider_from_db(db_provider, db_manager)
                else:
                    logger.warning(
                        f"  → Provider '{provider_name}' not found or disabled in database"
                    )
        except Exception as e:
            logger.error(f"  → Database load failed: {e}")

        provider_config = self._config_providers.get(provider_name)
        if isinstance(provider_config, dict):
            logger.info(f"  → Loading from CONFIG: {provider_name}")
            return self._create_provider_from_config(provider_name, provider_config)

        return None

    async def _create_provider_from_db(self, db_provider, db_manager) -> Optional[BaseLLMProvider]:
        """Create provider instance from database model."""
        try:
            # Build config
            base_url = str(db_provider.base_url or "")
            require_api_key = "api.openai.com" in base_url
            provider_config = {
                "enabled": db_provider.enabled,
                "base_url": base_url,
                "timeout": db_provider.timeout,
                "max_retries": db_provider.max_retries,
                "models": {},
                "available_models": db_provider.models or [],
                "require_api_key": require_api_key,
            }

            # Add models
            if db_provider.models:
                provider_config["models"] = {
                    "chat": db_provider.models[0],
                    "embedding": db_provider.models[0],
                    "code": db_provider.models[0],
                }

            # Decrypt API key
            if db_provider.api_key_encrypted:
                decrypted_key = db_manager._decrypt_api_key(db_provider.api_key_encrypted)
                if decrypted_key:
                    provider_config["api_key"] = decrypted_key

            # Create provider by protocol
            if db_provider.protocol == "ollama":
                return OllamaProvider(provider_config)
            elif db_provider.protocol == "openai_compatible":
                return OpenAIProvider(provider_config)
            else:
                logger.error(f"Unknown protocol: {db_provider.protocol}")
                return None

        except Exception as e:
            logger.error(f"Failed to create provider from DB: {e}", exc_info=True)
            return None

    def _create_provider_from_config(
        self, provider_name: str, provider_config: Dict[str, Any]
    ) -> Optional[BaseLLMProvider]:
        """Create provider instance from config.yaml."""
        try:
            if provider_name == "ollama":
                return OllamaProvider(provider_config)
            elif provider_name == "vllm":
                return VLLMProvider(provider_config)
            elif provider_name == "openai":
                return OpenAIProvider(provider_config)
            elif provider_name == "anthropic":
                return AnthropicProvider(provider_config)
            else:
                # Generic OpenAI-compatible
                return OpenAIProvider(provider_config)
        except Exception as e:
            logger.error(f"Failed to create provider from config: {e}", exc_info=True)
            return None

    async def list_all_providers(self) -> List[str]:
        """
        List all available provider names from database only.

        Config.yaml providers are synced to database on startup.

        Returns:
            List of enabled provider names from database
        """
        providers = set(self._config_providers.keys())

        # Get providers from database only
        try:
            from database.connection import get_db_session
            from llm_providers.db_manager import ProviderDBManager

            with get_db_session() as db:
                db_manager = ProviderDBManager(db)
                db_providers = db_manager.list_providers()
                providers.update(p.name for p in db_providers if p.enabled)
        except Exception as e:
            logger.warning(f"Failed to list database providers: {e}")

        return sorted(providers)

    def select_model_for_task(self, task_type: TaskType) -> Tuple[Optional[str], Optional[str]]:
        """Select provider/model from static task mapping."""
        task_key = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        mapping = self.model_mapping.get(task_key, {})
        if not isinstance(mapping, dict) or not mapping:
            return None, None
        provider_name, model_name = next(iter(mapping.items()))
        return str(provider_name), str(model_name)

    def _track_token_usage(self, provider: str, tokens_used: int) -> None:
        self.token_usage[str(provider)] = self.token_usage.get(str(provider), 0) + int(
            tokens_used or 0
        )

    @staticmethod
    def _provider_models(provider_cfg: Dict[str, Any]) -> List[str]:
        models = provider_cfg.get("models") or provider_cfg.get("available_models") or []
        if isinstance(models, dict):
            models = list(models.values())
        if isinstance(models, str):
            models = [models]
        return [str(model).strip() for model in models if str(model).strip()]

    def _provider_supports_model(self, provider_name: str, model_name: Optional[str]) -> bool:
        requested_model = str(model_name or "").strip()
        if not requested_model:
            return True
        provider_cfg = resolve_provider(provider_name)
        provider_models = self._provider_models(provider_cfg)
        if not provider_models:
            return False
        return any(model_names_match(requested_model, candidate) for candidate in provider_models)

    async def _select_provider_for_request(self, model_name: Optional[str]) -> str:
        provider_names = await self.list_all_providers()
        if not provider_names:
            raise ValueError("No providers available")

        requested_model = str(model_name or "").strip()
        default_provider = (
            self.default_provider if self.default_provider in provider_names else None
        )

        if requested_model:
            if default_provider and self._provider_supports_model(
                default_provider, requested_model
            ):
                return default_provider
            for provider_name in provider_names:
                if self._provider_supports_model(provider_name, requested_model):
                    return provider_name
            logger.warning(
                "No provider advertises requested model; fallback to default selection",
                extra={"model": requested_model, "default_provider": default_provider},
            )

        if default_provider:
            return default_provider
        return provider_names[0]

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all available providers.

        Note: This loads all providers on-demand to check health.
        Use sparingly as it may be expensive.

        Returns:
            Dict mapping provider name to health status
        """
        provider_names = await self.list_all_providers()
        health_status = {}

        # Check health concurrently
        async def check_one(name: str) -> tuple[str, bool]:
            try:
                provider = await self._get_provider(name)
                if provider:
                    healthy = await provider.health_check()
                    return (name, healthy)
                return (name, False)
            except Exception as e:
                logger.error(f"Health check failed for {name}: {e}")
                return (name, False)

        results = await asyncio.gather(*[check_one(name) for name in provider_names])
        health_status = dict(results)

        return health_status

    async def list_available_models(self) -> Dict[str, List[str]]:
        """
        List available models for all providers.

        Note: This loads all providers on-demand.
        Use sparingly as it may be expensive.

        Returns:
            Dict mapping provider name to list of models
        """
        provider_names = await self.list_all_providers()
        models_dict = {}

        # List models concurrently
        async def list_one(name: str) -> tuple[str, List[str]]:
            try:
                provider = await self._get_provider(name)
                if provider:
                    models = await provider.list_models()
                    return (name, models)
                return (name, [])
            except Exception as e:
                logger.error(f"List models failed for {name}: {e}")
                return (name, [])

        results = await asyncio.gather(*[list_one(name) for name in provider_names])
        models_dict = dict(results)

        return models_dict

    async def generate(
        self,
        prompt: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate text completion.

        Provider is loaded on-demand when this method is called.

        Args:
            prompt: Input prompt
            provider: Provider name (optional, auto-selected if not provided)
            model: Model name (optional)
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            **kwargs: Additional parameters

        Returns:
            LLMResponse
        """
        task_type = kwargs.pop("task_type", None)
        if task_type is not None and (not provider or not model):
            mapped_provider, mapped_model = self.select_model_for_task(task_type)
            provider = provider or mapped_provider
            model = model or mapped_model

        if isinstance(task_type, Enum):
            kwargs["task_type"] = task_type.value
        elif task_type is not None:
            kwargs["task_type"] = str(task_type)

        # Auto-select provider if not specified
        if not provider:
            provider = await self._select_provider_for_request(model)

        # Load provider on-demand
        provider_instance = await self._get_provider(provider)
        if not provider_instance:
            raise ValueError(f"Provider '{provider}' not available")

        # Generate
        response = await provider_instance.generate(
            prompt=prompt,
            model=model or "default",
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        # Track token usage
        self._track_token_usage(str(provider), int(response.tokens_used or 0))

        return response

    def get_token_usage(self) -> Dict[str, int]:
        """Get token usage by provider."""
        return self.token_usage.copy()

    async def invalidate_provider(self, provider_name: str) -> bool:
        """Close and evict a single cached provider instance."""
        cached_provider: Optional[tuple[BaseLLMProvider, float]] = None
        async with self._cache_lock:
            cached_provider = self._provider_cache.pop(provider_name, None)

        if not cached_provider:
            return False

        provider, _ = cached_provider
        try:
            await provider.close()
        except Exception as e:
            logger.error(f"Error closing provider '{provider_name}': {e}")
        return True

    async def clear_cache(self):
        """Clear provider cache and close cached sessions."""
        async with self._cache_lock:
            cached_items = list(self._provider_cache.items())
            self._provider_cache.clear()

        for provider_name, (provider, _) in cached_items:
            try:
                await provider.close()
            except Exception as e:
                logger.error(f"Error closing provider '{provider_name}' during cache clear: {e}")
        logger.info("Provider cache cleared")

    async def close(self):
        """Close all cached providers."""
        await self.clear_cache()


# Singleton instance
_llm_router: Optional[LLMRouter] = None


def get_llm_provider(config: Optional[Dict[str, Any]] = None) -> LLMRouter:
    """
    Get or create the LLM router singleton.

    Args:
        config: Optional configuration. If not provided, loads from config.yaml

    Returns:
        LLMRouter instance
    """
    global _llm_router

    if _llm_router is None:
        if config is None:
            from shared.config import get_config

            cfg = get_config()
            config = {
                "providers": cfg.get("llm.providers", {}),
                "model_mapping": cfg.get("llm.model_mapping", {}),
                "fallback_enabled": cfg.get("llm.fallback_enabled", False),
                "default_provider": cfg.get("llm.default_provider", ""),
                "max_retries": cfg.get("llm.max_retries", 3),
                "retry_delay": cfg.get("llm.retry_delay", 1),
                "cache_ttl": cfg.get("llm.cache_ttl", 300),
            }

        _llm_router = LLMRouter(config)
        logger.info("LLM Router singleton created")

    return _llm_router
