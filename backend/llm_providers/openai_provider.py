"""
OpenAI Provider Implementation (Optional)

Provides integration with OpenAI API for cloud-based LLM access.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.1: Provider Architecture (Cloud Fallback)
"""

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
                - base_url: API base URL (default: https://api.openai.com/v1)
                - timeout: Request timeout in seconds (default: 60)
                - organization: Optional organization ID
        """
        super().__init__(config)
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("OpenAI API key is required")

        self.base_url = config.get("base_url", "https://api.openai.com/v1")
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
        Generate text completion using OpenAI.

        Args:
            prompt: Input prompt text
            model: OpenAI model name (e.g., "gpt-4", "gpt-3.5-turbo")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional OpenAI parameters

        Returns:
            LLMResponse with generated text
        """
        session = await self._get_session()

        # Use chat completions API for chat models
        if "gpt" in model.lower():
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

                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    usage = data.get("usage", {})

                    return LLMResponse(
                        content=message.get("content", ""),
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
            # Use completions API for other models
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

        Returns:
            List of model IDs
        """
        session = await self._get_session()

        try:
            async with session.get(f"{self.base_url}/models") as response:
                response.raise_for_status()
                data = await response.json()
                models = data.get("data", [])
                return [model.get("id") for model in models]
        except aiohttp.ClientError as e:
            logger.error(f"OpenAI list models error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing OpenAI models: {e}")
            return []

    async def health_check(self) -> bool:
        """
        Check if OpenAI API is available.

        Returns:
            True if OpenAI is healthy
        """
        session = await self._get_session()

        try:
            async with session.get(f"{self.base_url}/models") as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False

    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
