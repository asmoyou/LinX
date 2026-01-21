"""
LLM Provider Integration Module

This module provides a unified interface for interacting with various LLM providers
including local providers (Ollama, vLLM) and optional cloud providers (OpenAI, Anthropic).

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Integration Design
"""

from llm_providers.base import BaseLLMProvider, EmbeddingResponse, LLMResponse
from llm_providers.ollama_provider import OllamaProvider
from llm_providers.router import LLMRouter, get_llm_provider
from llm_providers.vllm_provider import VLLMProvider

__all__ = [
    "BaseLLMProvider",
    "LLMResponse",
    "EmbeddingResponse",
    "LLMRouter",
    "OllamaProvider",
    "VLLMProvider",
    "get_llm_provider",
]
