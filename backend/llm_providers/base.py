"""
Base LLM Provider Interface

Defines the abstract base class that all LLM providers must implement.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9.1: Provider Architecture
"""

import inspect
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskType(Enum):
    """Task types for model selection"""

    CHAT = "chat"
    CODE_GENERATION = "code_generation"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    REASONING = "reasoning"


@dataclass
class LLMResponse:
    """Response from LLM generation"""

    content: str
    model: str
    provider: str
    tokens_used: int
    finish_reason: str
    metadata: Dict[str, Any]


@dataclass
class EmbeddingResponse:
    """Response from embedding generation"""

    embedding: List[float]
    model: str
    provider: str
    tokens_used: int
    metadata: Dict[str, Any]


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.

    All provider implementations must inherit from this class and implement
    the required methods for text generation and embedding generation.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the LLM provider.

        Args:
            config: Provider-specific configuration
        """
        self.config = config
        self.provider_name = self.__class__.__name__

    @staticmethod
    def _normalize_request_value(value: Any) -> Any:
        """Convert request payload values into JSON-safe primitives."""
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, dict):
            return {
                str(key): BaseLLMProvider._normalize_request_value(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [BaseLLMProvider._normalize_request_value(item) for item in value]
        if isinstance(value, tuple):
            return [BaseLLMProvider._normalize_request_value(item) for item in value]
        return value

    @classmethod
    def _normalize_request_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            str(key): cls._normalize_request_value(value)
            for key, value in dict(payload or {}).items()
        }

    @staticmethod
    async def _resolve_request_context(request_result: Any) -> Any:
        """Support both aiohttp request managers and awaited AsyncMock stubs."""
        if hasattr(request_result, "__aenter__") and hasattr(request_result, "__aexit__"):
            return request_result
        if inspect.isawaitable(request_result):
            request_result = await request_result
        return request_result

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate text completion from prompt.

        Args:
            prompt: Input prompt text
            model: Model identifier
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Provider-specific parameters

        Returns:
            LLMResponse with generated text and metadata
        """
        pass

    @abstractmethod
    async def generate_embedding(self, text: str, model: str, **kwargs) -> EmbeddingResponse:
        """
        Generate embedding vector for text.

        Args:
            text: Input text to embed
            model: Embedding model identifier
            **kwargs: Provider-specific parameters

        Returns:
            EmbeddingResponse with embedding vector and metadata
        """
        pass

    @abstractmethod
    async def list_models(self) -> List[str]:
        """
        List available models from this provider.

        Returns:
            List of model identifiers
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is available and healthy.

        Returns:
            True if provider is healthy, False otherwise
        """
        pass

    def get_provider_name(self) -> str:
        """Get the provider name"""
        return self.provider_name
