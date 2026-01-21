"""
vLLM Provider Implementation

Provides integration with vLLM for high-performance local LLM deployment.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.1: Provider Architecture (vLLM)
"""

import aiohttp
import logging
from typing import List, Dict, Any, Optional

from llm_providers.base import BaseLLMProvider, LLMResponse, EmbeddingResponse


logger = logging.getLogger(__name__)


class VLLMProvider(BaseLLMProvider):
    """
    vLLM provider for high-performance local LLM deployment.
    
    vLLM is optimized for production scale with PagedAttention,
    higher throughput, and lower latency. Supports GPU acceleration.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize vLLM provider.
        
        Args:
            config: Configuration dict with keys:
                - base_url: vLLM API base URL (default: http://localhost:8000)
                - timeout: Request timeout in seconds (default: 120)
                - api_key: Optional API key for authentication
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:8000")
        self.timeout = config.get("timeout", 120)
        self.api_key = config.get("api_key")
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self.session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self.session
    
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate text completion using vLLM.
        
        vLLM uses OpenAI-compatible API format.
        
        Args:
            prompt: Input prompt text
            model: Model name
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters
        
        Returns:
            LLMResponse with generated text
        """
        session = await self._get_session()
        
        payload = {
            "model": model,
            "prompt": prompt,
            "temperature": temperature,
            "stream": False,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        # Add any additional parameters
        payload.update(kwargs)
        
        try:
            async with session.post(
                f"{self.base_url}/v1/completions",
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                choice = data.get("choices", [{}])[0]
                usage = data.get("usage", {})
                
                return LLMResponse(
                    content=choice.get("text", ""),
                    model=model,
                    provider="vLLM",
                    tokens_used=usage.get("total_tokens", 0),
                    finish_reason=choice.get("finish_reason", "stop"),
                    metadata={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                    }
                )
        except aiohttp.ClientError as e:
            logger.error(f"vLLM API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in vLLM generate: {e}")
            raise
    
    async def generate_embedding(
        self,
        text: str,
        model: str,
        **kwargs
    ) -> EmbeddingResponse:
        """
        Generate embedding vector using vLLM.
        
        Args:
            text: Input text to embed
            model: Embedding model name
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
            async with session.post(
                f"{self.base_url}/v1/embeddings",
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                embedding_data = data.get("data", [{}])[0]
                usage = data.get("usage", {})
                
                return EmbeddingResponse(
                    embedding=embedding_data.get("embedding", []),
                    model=model,
                    provider="vLLM",
                    tokens_used=usage.get("total_tokens", 0),
                    metadata={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                    }
                )
        except aiohttp.ClientError as e:
            logger.error(f"vLLM embedding API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in vLLM embedding: {e}")
            raise
    
    async def list_models(self) -> List[str]:
        """
        List available vLLM models.
        
        Returns:
            List of model names
        """
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/v1/models") as response:
                response.raise_for_status()
                data = await response.json()
                models = data.get("data", [])
                return [model.get("id") for model in models]
        except aiohttp.ClientError as e:
            logger.error(f"vLLM list models error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing vLLM models: {e}")
            return []
    
    async def health_check(self) -> bool:
        """
        Check if vLLM is available.
        
        Returns:
            True if vLLM is healthy
        """
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/health") as response:
                return response.status == 200
        except Exception:
            # Try alternative health check endpoint
            try:
                async with session.get(f"{self.base_url}/v1/models") as response:
                    return response.status == 200
            except Exception as e:
                logger.warning(f"vLLM health check failed: {e}")
                return False
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
