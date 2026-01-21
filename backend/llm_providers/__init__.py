"""
LLM Provider Integration Module

This module provides a unified interface for interacting with various LLM providers
including local providers (Ollama, vLLM) and optional cloud providers (OpenAI, Anthropic).

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Integration Design
"""

from llm_providers.base import BaseLLMProvider, LLMResponse, EmbeddingResponse
from llm_providers.router import LLMRouter
from llm_providers.ollama_provider import OllamaProvider
from llm_providers.vllm_provider import VLLMProvider

__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "EmbeddingResponse",
    "LLMRouter",
    "OllamaProvider",
    "VLLMProvider",
]
