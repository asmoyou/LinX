"""
OpenAI Provider Implementation (Optional)

Provides integration with OpenAI API for cloud-based LLM access.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.1: Provider Architecture (Cloud Fallback)
"""

import json
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from llm_providers.base import BaseLLMProvider, EmbeddingResponse, LLMResponse

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """
    OpenAI provider for cloud-based LLM access.

    This is an optional provider for fallback scenarios.
    Should only be used for non-sensitive data.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize OpenAI provider.

        Args:
            config: Configuration dict with keys:
                - api_key: OpenAI API key (required)
                - base_url: API base URL (should include full path, e.g., https://api.openai.com/v1)
                - timeout: Request timeout in seconds (default: 60)
                - organization: Optional organization ID
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")

        # Use base_url as-is, don't modify it
        # User should provide the complete base URL including version path
        base_url = config.get("base_url", "https://api.openai.com/v1")
        self.base_url = base_url.rstrip('/')
        
        self.timeout = config.get("timeout", 60)
        self.organization = config.get("organization")
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            if self.organization:
                headers["OpenAI-Organization"] = self.organization

            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session

    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate text completion using OpenAI or OpenAI-compatible API.

        Args:
            prompt: Input prompt text
            model: Model name (e.g., "gpt-4", "gpt-3.5-turbo", "glm-4.7")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            LLMResponse with generated text
            
        Note:
            Modern OpenAI-compatible APIs use /chat/completions endpoint.
            The legacy /completions endpoint is only used for specific completion models.
        """
        session = await self._get_session()

        # Default to chat completions API (modern standard for OpenAI-compatible APIs)
        # Only use legacy completions API for specific models that require it
        use_chat_api = True
        
        # Check if this is a legacy completion model (not a chat model)
        # These are rare and typically only in older OpenAI models
        legacy_completion_models = ["text-davinci-003", "text-davinci-002", "text-curie-001", "text-babbage-001", "text-ada-001"]
        if any(legacy in model.lower() for legacy in legacy_completion_models):
            use_chat_api = False
        
        if use_chat_api:
            # Use chat completions API (standard for all modern models)
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }

            if max_tokens:
                payload["max_tokens"] = max_tokens

            payload.update(kwargs)

            try:
                async with session.post(
                    f"{self.base_url}/chat/completions", json=payload
                ) as response:
                    response.raise_for_status()
                    data = await response.json()
                    
                    # Handle wrapped response format (some proxies wrap the response)
                    # Example: {"output": "{...}", "request_tokens": 12, ...}
                    if "output" in data and isinstance(data["output"], str):
                        try:
                            # Parse the wrapped JSON string
                            data = json.loads(data["output"])
                            logger.debug("Unwrapped proxy response format")
                        except json.JSONDecodeError:
                            logger.warning("Failed to parse wrapped output, using original response")

                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    usage = data.get("usage", {})
                    
                    # Extract content - try multiple fields for compatibility
                    # Some models put content in "reasoning_content" instead of "content"
                    content = message.get("content", "")
                    if not content:
                        content = message.get("reasoning_content", "")
                    if not content:
                        # Fallback to text field for completion-style responses
                        content = message.get("text", "")

                    return LLMResponse(
                        content=content,
                        model=model,
                        provider="OpenAI",
                        tokens_used=usage.get("total_tokens", 0),
                        finish_reason=choice.get("finish_reason", "stop"),
                        metadata={
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                        },
                    )
            except aiohttp.ClientError as e:
                logger.error(f"OpenAI API error: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in OpenAI generate: {e}")
                raise
        else:
            # Use legacy completions API (only for specific old models)
            payload = {
                "model": model,
                "prompt": prompt,
                "temperature": temperature,
            }

            if max_tokens:
                payload["max_tokens"] = max_tokens

            payload.update(kwargs)

            try:
                async with session.post(f"{self.base_url}/completions", json=payload) as response:
                    response.raise_for_status()
                    data = await response.json()

                    choice = data.get("choices", [{}])[0]
                    usage = data.get("usage", {})

                    return LLMResponse(
                        content=choice.get("text", ""),
                        model=model,
                        provider="OpenAI",
                        tokens_used=usage.get("total_tokens", 0),
                        finish_reason=choice.get("finish_reason", "stop"),
                        metadata={
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                        },
                    )
            except aiohttp.ClientError as e:
                logger.error(f"OpenAI API error: {e}")
                raise
            except Exception as e:
                logger.error(f"Unexpected error in OpenAI generate: {e}")
                raise

    async def generate_embedding(self, text: str, model: str, **kwargs) -> EmbeddingResponse:
        """
        Generate embedding vector using OpenAI.

        Args:
            text: Input text to embed
            model: OpenAI embedding model (e.g., "text-embedding-ada-002")
            **kwargs: Additional parameters

        Returns:
            EmbeddingResponse with embedding vector
        """
        session = await self._get_session()

        payload = {
            "model": model,
            "input": text,
        }

        try:
            async with session.post(f"{self.base_url}/embeddings", json=payload) as response:
                response.raise_for_status()
                data = await response.json()

                embedding_data = data.get("data", [{}])[0]
                usage = data.get("usage", {})

                return EmbeddingResponse(
                    embedding=embedding_data.get("embedding", []),
                    model=model,
                    provider="OpenAI",
                    tokens_used=usage.get("total_tokens", 0),
                    metadata={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                    },
                )
        except aiohttp.ClientError as e:
            logger.error(f"OpenAI embedding API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in OpenAI embedding: {e}")
            raise

    async def list_models(self) -> List[str]:
        """
        List available OpenAI models.
        
        Uses a fallback strategy:
        1. Try to fetch from /models endpoint
        2. If that fails, return models from configuration
        3. If no configuration, return empty list

        Returns:
            List of model IDs
        """
        session = await self._get_session()

        # Strategy 1: Try to fetch from API
        try:
            async with session.get(
                f"{self.base_url}/models",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get("data", [])
                    model_list = [model.get("id") for model in models]
                    if model_list:
                        logger.info(f"Fetched {len(model_list)} models from OpenAI API")
                        return model_list
        except aiohttp.ClientError as e:
            logger.debug(f"OpenAI list models error: {e}")
        except Exception as e:
            logger.debug(f"Unexpected error listing OpenAI models: {e}")
        
        # Strategy 2: Return configured models as fallback
        # First check available_models (from database)
        available_models = self.config.get("available_models", [])
        if available_models:
            logger.info(f"Using {len(available_models)} models from configuration")
            return available_models
        
        # Then check models dict (from config.yaml)
        configured_models = self.config.get("models", {})
        if configured_models:
            # Extract model names from config
            model_list = []
            if isinstance(configured_models, dict):
                # Format: {"chat": "model-name", "embedding": "model-name"}
                model_list = list(set(configured_models.values()))
            elif isinstance(configured_models, list):
                # Format: ["model1", "model2"]
                model_list = configured_models
            
            if model_list:
                logger.info(f"Using {len(model_list)} configured models (API fetch failed)")
                return model_list
        
        logger.warning("No models available from API or configuration")
        return []

    async def health_check(self) -> bool:
        """
        Check if OpenAI API is available.
        
        Uses a two-tier strategy:
        1. Try GET /models endpoint (standard OpenAI API)
        2. If configured models exist, try a minimal chat request

        Returns:
            True if OpenAI is healthy
        """
        session = await self._get_session()

        # Strategy 1: Try /models endpoint
        try:
            async with session.get(
                f"{self.base_url}/models",
                timeout=aiohttp.ClientTimeout(total=3)
            ) as response:
                if response.status == 200:
                    logger.debug(f"OpenAI health check passed via /models endpoint")
                    return True
                # Log the failure for debugging
                response_text = await response.text()
                logger.debug(f"OpenAI /models endpoint returned {response.status}: {response_text[:200]}")
        except Exception as e:
            logger.debug(f"OpenAI /models endpoint failed: {e}")
        
        # Strategy 2: If user has configured models, try a minimal chat request
        configured_models = self.config.get("models", {})
        if configured_models:
            try:
                # Get the first configured model
                if isinstance(configured_models, dict):
                    test_model = list(configured_models.values())[0]
                elif isinstance(configured_models, list):
                    test_model = configured_models[0]
                else:
                    test_model = str(configured_models)
                
                test_payload = {
                    "model": test_model,
                    "messages": [{"role": "user", "content": "test"}],
                    "max_tokens": 1
                }
                
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    json=test_payload,
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as response:
                    # 200 = success, 400/422 = bad request but server is up
                    if response.status in [200, 400, 422]:
                        logger.info(f"OpenAI health check passed via chat endpoint (status {response.status})")
                        return True
                    # Log the failure
                    response_text = await response.text()
                    logger.warning(f"OpenAI chat endpoint returned {response.status}: {response_text[:200]}")
            except Exception as e:
                logger.debug(f"OpenAI chat endpoint test failed: {e}")
        
        logger.warning(f"OpenAI health check failed: all strategies exhausted")
        return False

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
