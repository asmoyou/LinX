"""
Ollama LLM Provider Implementation

Provides integration with Ollama for local LLM deployment.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.1: Provider Architecture (Ollama)
"""

import aiohttp
import logging
from typing import List, Dict, Any, Optional

from llm_providers.base import BaseLLMProvider, LLMResponse, EmbeddingResponse


logger = logging.getLogger(__name__)


class OllamaProvider(BaseLLMProvider):
    """
    Ollama provider for local LLM deployment.
    
    Ollama is the default provider for development and small-scale deployments.
    Supports multiple models concurrently with easy setup and model management.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama provider.
        
        Args:
            config: Configuration dict with keys:
                - base_url: Ollama API base URL (default: http://localhost:11434)
                - timeout: Request timeout in seconds (default: 60)
        """
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.timeout = config.get("timeout", 60)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
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
        Generate text completion using Ollama.
        
        Args:
            prompt: Input prompt text
            model: Ollama model name (e.g., "llama3", "mistral")
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional Ollama parameters
        
        Returns:
            LLMResponse with generated text
        """
        session = await self._get_session()
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens
        
        # Add any additional options
        payload["options"].update(kwargs)
        
        try:
            async with session.post(
                f"{self.base_url}/api/generate",
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                return LLMResponse(
                    content=data.get("response", ""),
                    model=model,
                    provider="Ollama",
                    tokens_used=data.get("eval_count", 0) + data.get("prompt_eval_count", 0),
                    finish_reason=data.get("done_reason", "stop"),
                    metadata={
                        "eval_count": data.get("eval_count", 0),
                        "prompt_eval_count": data.get("prompt_eval_count", 0),
                        "total_duration": data.get("total_duration", 0),
                    }
                )
        except aiohttp.ClientError as e:
            logger.error(f"Ollama API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Ollama generate: {e}")
            raise
    
    async def generate_embedding(
        self,
        text: str,
        model: str,
        **kwargs
    ) -> EmbeddingResponse:
        """
        Generate embedding vector using Ollama.
        
        Args:
            text: Input text to embed
            model: Ollama embedding model (e.g., "nomic-embed-text")
            **kwargs: Additional parameters
        
        Returns:
            EmbeddingResponse with embedding vector
        """
        session = await self._get_session()
        
        payload = {
            "model": model,
            "prompt": text,
        }
        
        try:
            async with session.post(
                f"{self.base_url}/api/embeddings",
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                return EmbeddingResponse(
                    embedding=data.get("embedding", []),
                    model=model,
                    provider="Ollama",
                    tokens_used=data.get("prompt_eval_count", 0),
                    metadata={
                        "total_duration": data.get("total_duration", 0),
                    }
                )
        except aiohttp.ClientError as e:
            logger.error(f"Ollama embedding API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Ollama embedding: {e}")
            raise
    
    async def list_models(self) -> List[str]:
        """
        List available Ollama models.
        
        Returns:
            List of model names
        """
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/api/tags") as response:
                response.raise_for_status()
                data = await response.json()
                models = data.get("models", [])
                return [model.get("name") for model in models]
        except aiohttp.ClientError as e:
            logger.error(f"Ollama list models error: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing Ollama models: {e}")
            return []
    
    async def health_check(self) -> bool:
        """
        Check if Ollama is available.
        
        Returns:
            True if Ollama is healthy
        """
        session = await self._get_session()
        
        try:
            async with session.get(f"{self.base_url}/api/tags") as response:
                return response.status == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False
    
    async def close(self):
        """Close the aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
