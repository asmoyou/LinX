"""
Anthropic Provider Implementation (Optional)

Provides integration with Anthropic API for cloud-based LLM access.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.1: Provider Architecture (Cloud Fallback)
"""

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from llm_providers.base import BaseLLMProvider, EmbeddingResponse, LLMResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """
    Anthropic provider for cloud-based LLM access.

    This is an optional provider for fallback scenarios.
    Should only be used for non-sensitive data.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Anthropic provider.

        Args:
            config: Configuration dict with keys:
                - api_key: Anthropic API key (required)
                - base_url: API base URL (default: https://api.anthropic.com)
                - timeout: Request timeout in seconds (default: 60)
                - api_version: API version (default: 2023-06-01)
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("Anthropic API key is required")

        self.base_url = config.get("base_url", "https://api.anthropic.com")
        self.timeout = config.get("timeout", 60)
        self.api_version = config.get("api_version", "2023-06-01")
        self.session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": self.api_version,
                "Content-Type": "application/json",
            }
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
        Generate text completion using Anthropic.

        Args:
            prompt: Input prompt text
            model: Anthropic model name (e.g., "claude-3-opus-20240229")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate (required for Anthropic)
            **kwargs: Additional Anthropic parameters

        Returns:
            LLMResponse with generated text
        """
        session = await self._get_session()

        # Anthropic requires max_tokens
        if not max_tokens:
            max_tokens = 1024

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        payload.update(kwargs)

        try:
            async with session.post(f"{self.base_url}/v1/messages", json=payload) as response:
                response.raise_for_status()
                data = await response.json()

                content = data.get("content", [{}])[0]
                usage = data.get("usage", {})

                return LLMResponse(
                    content=content.get("text", ""),
                    model=model,
                    provider="Anthropic",
                    tokens_used=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                    finish_reason=data.get("stop_reason", "end_turn"),
                    metadata={
                        "input_tokens": usage.get("input_tokens", 0),
                        "output_tokens": usage.get("output_tokens", 0),
                    },
                )
        except aiohttp.ClientError as e:
            logger.error(f"Anthropic API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Anthropic generate: {e}")
            raise

    async def generate_embedding(self, text: str, model: str, **kwargs) -> EmbeddingResponse:
        """
        Generate embedding vector using Anthropic.

        Note: Anthropic does not currently provide embedding models.
        This method raises NotImplementedError.

        Args:
            text: Input text to embed
            model: Model name
            **kwargs: Additional parameters

        Raises:
            NotImplementedError: Anthropic does not support embeddings
        """
        raise NotImplementedError(
            "Anthropic does not currently provide embedding models. "
            "Use Ollama or OpenAI for embeddings."
        )

    async def list_models(self) -> List[str]:
        """
        List available Anthropic models.

        Note: Anthropic API does not provide a models endpoint.
        Returns a hardcoded list of known models.

        Returns:
            List of known Anthropic model names
        """
        return [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-2.1",
            "claude-2.0",
            "claude-instant-1.2",
        ]

    async def health_check(self) -> bool:
        """
        Check if Anthropic API is available.

        Returns:
            True if Anthropic is healthy
        """
        # Anthropic doesn't have a dedicated health endpoint
        # We'll try a minimal request to check availability
        session = await self._get_session()

        try:
            payload = {
                "model": "claude-3-haiku-20240307",
                "messages": [{"role": "user", "content": "test"}],
                "max_tokens": 1,
            }
            async with session.post(f"{self.base_url}/v1/messages", json=payload) as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return False

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
