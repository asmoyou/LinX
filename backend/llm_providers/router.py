"""
LLM Provider Router

Routes requests to appropriate LLM providers with fallback logic,
model selection, retry mechanisms, and request/response logging.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.2: Model Selection Strategy
- Design Section 9.3: Prompt Engineering
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from enum import Enum

from llm_providers.base import (
    BaseLLMProvider,
    LLMResponse,
    EmbeddingResponse,
    TaskType
)
from llm_providers.ollama_provider import OllamaProvider
from llm_providers.vllm_provider import VLLMProvider
from llm_providers.openai_provider import OpenAIProvider
from llm_providers.anthropic_provider import AnthropicProvider


logger = logging.getLogger(__name__)


class LLMRouter:
    """
    Routes LLM requests to appropriate providers with fallback logic.
    
    Supports:
    - Automatic provider selection based on availability
    - Task-specific model selection
    - Retry logic with exponential backoff
    - Request/response logging
    - Token usage tracking
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize LLM Router.
        
        Args:
            config: Configuration dict with keys:
                - providers: Dict of provider configs
                - model_mapping: Task type to model mapping
                - fallback_enabled: Enable fallback to cloud providers
                - max_retries: Maximum retry attempts (default: 3)
                - retry_delay: Initial retry delay in seconds (default: 1)
        """
        self.config = config
        self.providers: Dict[str, BaseLLMProvider] = {}
        self.model_mapping = config.get("model_mapping", {})
        self.fallback_enabled = config.get("fallback_enabled", False)
        self.max_retries = config.get("max_retries", 3)
        self.retry_delay = config.get("retry_delay", 1)
        
        # Token usage tracking
        self.token_usage: Dict[str, int] = {}
        
        # Initialize providers
        self._initialize_providers(config.get("providers", {}))
    
    def _initialize_providers(self, provider_configs: Dict[str, Dict[str, Any]]):
        """Initialize configured providers"""
        
        # Initialize Ollama (primary local provider)
        if "ollama" in provider_configs:
            try:
                self.providers["ollama"] = OllamaProvider(provider_configs["ollama"])
                logger.info("Initialized Ollama provider")
            except Exception as e:
                logger.error(f"Failed to initialize Ollama provider: {e}")
        
        # Initialize vLLM (high-performance local provider)
        if "vllm" in provider_configs:
            try:
                self.providers["vllm"] = VLLMProvider(provider_configs["vllm"])
                logger.info("Initialized vLLM provider")
            except Exception as e:
                logger.error(f"Failed to initialize vLLM provider: {e}")
        
        # Initialize OpenAI (optional cloud fallback)
        if "openai" in provider_configs and self.fallback_enabled:
            try:
                self.providers["openai"] = OpenAIProvider(provider_configs["openai"])
                logger.info("Initialized OpenAI provider (fallback)")
            except Exception as e:
                logger.error(f"Failed to initialize OpenAI provider: {e}")
        
        # Initialize Anthropic (optional cloud fallback)
        if "anthropic" in provider_configs and self.fallback_enabled:
            try:
                self.providers["anthropic"] = AnthropicProvider(provider_configs["anthropic"])
                logger.info("Initialized Anthropic provider (fallback)")
            except Exception as e:
                logger.error(f"Failed to initialize Anthropic provider: {e}")
    
    def select_model_for_task(self, task_type: TaskType) -> tuple[str, str]:
        """
        Select appropriate model and provider for task type.
        
        Args:
            task_type: Type of task
        
        Returns:
            Tuple of (provider_name, model_name)
        """
        # Get model mapping for task type
        task_config = self.model_mapping.get(task_type.value, {})
        
        # Try local providers first
        if "ollama" in self.providers:
            model = task_config.get("ollama")
            if model:
                return ("ollama", model)
        
        if "vllm" in self.providers:
            model = task_config.get("vllm")
            if model:
                return ("vllm", model)
        
        # Fallback to cloud providers if enabled
        if self.fallback_enabled:
            if "openai" in self.providers:
                model = task_config.get("openai")
                if model:
                    logger.warning(f"Falling back to OpenAI for {task_type.value}")
                    return ("openai", model)
            
            if "anthropic" in self.providers:
                model = task_config.get("anthropic")
                if model:
                    logger.warning(f"Falling back to Anthropic for {task_type.value}")
                    return ("anthropic", model)
        
        # Default fallback
        if "ollama" in self.providers:
            return ("ollama", "llama3")
        
        raise RuntimeError("No LLM providers available")
    
    async def generate(
        self,
        prompt: str,
        task_type: TaskType = TaskType.CHAT,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text completion with automatic provider selection and retry.
        
        Args:
            prompt: Input prompt text
            task_type: Type of task for model selection
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            provider: Specific provider to use (optional)
            model: Specific model to use (optional)
            **kwargs: Additional parameters
        
        Returns:
            LLMResponse with generated text
        """
        start_time = time.time()
        
        # Select provider and model if not specified
        if not provider or not model:
            provider, model = self.select_model_for_task(task_type)
        
        # Log request
        logger.info(
            f"LLM generate request",
            extra={
                "provider": provider,
                "model": model,
                "task_type": task_type.value,
                "prompt_length": len(prompt),
            }
        )
        
        # Try with retries
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                provider_instance = self.providers.get(provider)
                if not provider_instance:
                    raise ValueError(f"Provider {provider} not available")
                
                # Check provider health
                if not await provider_instance.health_check():
                    raise RuntimeError(f"Provider {provider} is unhealthy")
                
                # Generate response
                response = await provider_instance.generate(
                    prompt=prompt,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    **kwargs
                )
                
                # Track token usage
                self._track_token_usage(provider, response.tokens_used)
                
                # Log response
                duration = time.time() - start_time
                logger.info(
                    f"LLM generate success",
                    extra={
                        "provider": provider,
                        "model": model,
                        "tokens_used": response.tokens_used,
                        "duration_seconds": duration,
                    }
                )
                
                return response
                
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"LLM generate attempt {attempt + 1} failed: {e}",
                    extra={"provider": provider, "model": model}
                )
                
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                else:
                    # Try fallback provider on final attempt
                    if self.fallback_enabled and provider in ["ollama", "vllm"]:
                        logger.warning(f"Attempting fallback to cloud provider")
                        try:
                            return await self._try_fallback_generate(
                                prompt, task_type, temperature, max_tokens, **kwargs
                            )
                        except Exception as fallback_error:
                            logger.error(f"Fallback also failed: {fallback_error}")
        
        # All retries failed
        logger.error(
            f"LLM generate failed after {self.max_retries} attempts",
            extra={"provider": provider, "model": model}
        )
        raise last_exception
    
    async def _try_fallback_generate(
        self,
        prompt: str,
        task_type: TaskType,
        temperature: float,
        max_tokens: Optional[int],
        **kwargs
    ) -> LLMResponse:
        """Try fallback cloud providers"""
        
        # Try OpenAI
        if "openai" in self.providers:
            task_config = self.model_mapping.get(task_type.value, {})
            model = task_config.get("openai", "gpt-3.5-turbo")
            return await self.providers["openai"].generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        # Try Anthropic
        if "anthropic" in self.providers:
            task_config = self.model_mapping.get(task_type.value, {})
            model = task_config.get("anthropic", "claude-3-haiku-20240307")
            return await self.providers["anthropic"].generate(
                prompt=prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
        
        raise RuntimeError("No fallback providers available")
    
    async def generate_embedding(
        self,
        text: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ) -> EmbeddingResponse:
        """
        Generate embedding vector with automatic provider selection and retry.
        
        Args:
            text: Input text to embed
            provider: Specific provider to use (optional)
            model: Specific model to use (optional)
            **kwargs: Additional parameters
        
        Returns:
            EmbeddingResponse with embedding vector
        """
        start_time = time.time()
        
        # Select provider and model if not specified
        if not provider or not model:
            provider, model = self.select_model_for_task(TaskType.EMBEDDING)
        
        # Log request
        logger.info(
            f"Embedding generate request",
            extra={
                "provider": provider,
                "model": model,
                "text_length": len(text),
            }
        )
        
        # Try with retries
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                provider_instance = self.providers.get(provider)
                if not provider_instance:
                    raise ValueError(f"Provider {provider} not available")
                
                # Check provider health
                if not await provider_instance.health_check():
                    raise RuntimeError(f"Provider {provider} is unhealthy")
                
                # Generate embedding
                response = await provider_instance.generate_embedding(
                    text=text,
                    model=model,
                    **kwargs
                )
                
                # Track token usage
                self._track_token_usage(provider, response.tokens_used)
                
                # Log response
                duration = time.time() - start_time
                logger.info(
                    f"Embedding generate success",
                    extra={
                        "provider": provider,
                        "model": model,
                        "tokens_used": response.tokens_used,
                        "embedding_dim": len(response.embedding),
                        "duration_seconds": duration,
                    }
                )
                
                return response
                
            except Exception as e:
                last_exception = e
                logger.warning(
                    f"Embedding generate attempt {attempt + 1} failed: {e}",
                    extra={"provider": provider, "model": model}
                )
                
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    delay = self.retry_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
        
        # All retries failed
        logger.error(
            f"Embedding generate failed after {self.max_retries} attempts",
            extra={"provider": provider, "model": model}
        )
        raise last_exception
    
    def _track_token_usage(self, provider: str, tokens: int):
        """Track token usage by provider"""
        if provider not in self.token_usage:
            self.token_usage[provider] = 0
        self.token_usage[provider] += tokens
    
    def get_token_usage(self) -> Dict[str, int]:
        """Get token usage statistics"""
        return self.token_usage.copy()
    
    async def list_available_models(self) -> Dict[str, List[str]]:
        """
        List available models from all providers.
        
        Returns:
            Dict mapping provider names to model lists
        """
        models = {}
        for provider_name, provider in self.providers.items():
            try:
                models[provider_name] = await provider.list_models()
            except Exception as e:
                logger.error(f"Failed to list models for {provider_name}: {e}")
                models[provider_name] = []
        return models
    
    async def health_check_all(self) -> Dict[str, bool]:
        """
        Check health of all providers.
        
        Returns:
            Dict mapping provider names to health status
        """
        health = {}
        for provider_name, provider in self.providers.items():
            try:
                health[provider_name] = await provider.health_check()
            except Exception as e:
                logger.error(f"Health check failed for {provider_name}: {e}")
                health[provider_name] = False
        return health
    
    async def close_all(self):
        """Close all provider connections"""
        for provider in self.providers.values():
            try:
                await provider.close()
            except Exception as e:
                logger.error(f"Error closing provider: {e}")
