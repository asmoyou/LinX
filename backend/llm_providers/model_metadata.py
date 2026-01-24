"""
Model Metadata Management

Provides comprehensive model metadata detection, management, and configuration.
Inspired by cherry-studio's model management approach.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Provider Integration
- cherry-studio: src/renderer/src/config/models.ts
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelCapability(str, Enum):
    """Model capabilities."""
    
    CHAT = "chat"
    CODE_GENERATION = "code_generation"
    EMBEDDING = "embedding"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    AUDIO = "audio"
    REASONING = "reasoning"
    STREAMING = "streaming"
    SYSTEM_PROMPT = "system_prompt"
    JSON_MODE = "json_mode"
    WEB_SEARCH = "web_search"


class ModelMetadata(BaseModel):
    """Comprehensive model metadata."""
    
    model_id: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider: str
    
    # Capabilities
    capabilities: List[ModelCapability] = Field(default_factory=list)
    
    # Context and tokens
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    
    # Parameters
    default_temperature: float = 0.7
    temperature_range: tuple[float, float] = (0.0, 2.0)
    default_top_p: float = 1.0
    top_p_range: tuple[float, float] = (0.0, 1.0)
    
    # Features
    supports_streaming: bool = True
    supports_system_prompt: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    
    # Pricing (per 1M tokens)
    input_price_per_1m: Optional[float] = None
    output_price_per_1m: Optional[float] = None
    
    # Version info
    version: Optional[str] = None
    release_date: Optional[str] = None
    deprecated: bool = False
    deprecation_message: Optional[str] = None
    
    # Additional metadata
    family: Optional[str] = None  # e.g., "gpt-4", "claude-3", "llama-3"
    size: Optional[str] = None  # e.g., "7B", "70B", "175B"
    quantization: Optional[str] = None  # e.g., "Q4_K_M", "Q8_0"
    
    # Custom fields
    custom_fields: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True


class ModelCapabilityDetector:
    """
    Detects model capabilities based on model name patterns.
    
    Provides intelligent defaults for common model families.
    """
    
    # Model family patterns
    PATTERNS = {
        # OpenAI models
        "gpt-4": {
            "family": "gpt-4",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.REASONING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
                ModelCapability.JSON_MODE,
            ],
            "context_window": 128000,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "supports_json_mode": True,
            "input_price_per_1m": 30.0,
            "output_price_per_1m": 60.0,
        },
        "gpt-4-turbo": {
            "family": "gpt-4",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
                ModelCapability.REASONING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
                ModelCapability.JSON_MODE,
            ],
            "context_window": 128000,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "supports_vision": True,
            "supports_json_mode": True,
            "input_price_per_1m": 10.0,
            "output_price_per_1m": 30.0,
        },
        "gpt-3.5-turbo": {
            "family": "gpt-3.5",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
                ModelCapability.JSON_MODE,
            ],
            "context_window": 16385,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "supports_json_mode": True,
            "input_price_per_1m": 0.5,
            "output_price_per_1m": 1.5,
        },
        "o1": {
            "family": "o1",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.REASONING,
                ModelCapability.STREAMING,
            ],
            "context_window": 200000,
            "max_output_tokens": 100000,
            "supports_system_prompt": False,  # o1 doesn't support system prompts
            "input_price_per_1m": 15.0,
            "output_price_per_1m": 60.0,
        },
        # Anthropic models
        "claude-3-opus": {
            "family": "claude-3",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
                ModelCapability.REASONING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 200000,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "supports_vision": True,
            "input_price_per_1m": 15.0,
            "output_price_per_1m": 75.0,
        },
        "claude-3-sonnet": {
            "family": "claude-3",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 200000,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "supports_vision": True,
            "input_price_per_1m": 3.0,
            "output_price_per_1m": 15.0,
        },
        "claude-3-haiku": {
            "family": "claude-3",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 200000,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "supports_vision": True,
            "input_price_per_1m": 0.25,
            "output_price_per_1m": 1.25,
        },
        # DeepSeek models
        "deepseek-chat": {
            "family": "deepseek",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 64000,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "input_price_per_1m": 0.14,
            "output_price_per_1m": 0.28,
        },
        "deepseek-coder": {
            "family": "deepseek",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 64000,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
            "input_price_per_1m": 0.14,
            "output_price_per_1m": 0.28,
        },
        # Qwen models
        "qwen": {
            "family": "qwen",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 32768,
            "max_output_tokens": 2048,
            "supports_function_calling": True,
        },
        # Llama models
        "llama-3": {
            "family": "llama-3",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 8192,
            "max_output_tokens": 2048,
            "supports_function_calling": True,
        },
        "llama-2": {
            "family": "llama-2",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 4096,
            "max_output_tokens": 2048,
        },
        # Mistral models
        "mistral": {
            "family": "mistral",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 32768,
            "max_output_tokens": 4096,
            "supports_function_calling": True,
        },
        # Gemini models
        "gemini-pro": {
            "family": "gemini",
            "capabilities": [
                ModelCapability.CHAT,
                ModelCapability.CODE_GENERATION,
                ModelCapability.FUNCTION_CALLING,
                ModelCapability.VISION,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ],
            "context_window": 32768,
            "max_output_tokens": 8192,
            "supports_function_calling": True,
            "supports_vision": True,
        },
        # Embedding models
        "text-embedding": {
            "family": "embedding",
            "capabilities": [ModelCapability.EMBEDDING],
            "context_window": 8191,
            "supports_streaming": False,
            "supports_system_prompt": False,
        },
        "embedding": {
            "family": "embedding",
            "capabilities": [ModelCapability.EMBEDDING],
            "context_window": 8191,
            "supports_streaming": False,
            "supports_system_prompt": False,
        },
    }
    
    @classmethod
    def detect_metadata(cls, model_id: str, provider: str) -> ModelMetadata:
        """
        Detect model metadata based on model ID and provider.
        
        Args:
            model_id: Model identifier
            provider: Provider name
            
        Returns:
            ModelMetadata with detected capabilities
        """
        # Normalize model ID for pattern matching
        model_lower = model_id.lower()
        
        # Try to match patterns
        detected_data = {}
        for pattern, data in cls.PATTERNS.items():
            if pattern in model_lower:
                detected_data = data.copy()
                break
        
        # Extract size information (e.g., "7B", "70B")
        size_match = re.search(r'(\d+[bB])', model_id)
        size = size_match.group(1).upper() if size_match else None
        
        # Extract quantization (e.g., "Q4_K_M", "Q8_0")
        quant_match = re.search(r'(Q\d+_[A-Z0-9_]+)', model_id, re.IGNORECASE)
        quantization = quant_match.group(1).upper() if quant_match else None
        
        # Build metadata
        metadata = ModelMetadata(
            model_id=model_id,
            display_name=cls._generate_display_name(model_id),
            provider=provider,
            family=detected_data.get("family"),
            size=size,
            quantization=quantization,
            capabilities=detected_data.get("capabilities", [
                ModelCapability.CHAT,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ]),
            context_window=detected_data.get("context_window"),
            max_output_tokens=detected_data.get("max_output_tokens"),
            supports_streaming=detected_data.get("supports_streaming", True),
            supports_system_prompt=detected_data.get("supports_system_prompt", True),
            supports_function_calling=detected_data.get("supports_function_calling", False),
            supports_vision=detected_data.get("supports_vision", False),
            supports_json_mode=detected_data.get("supports_json_mode", False),
            input_price_per_1m=detected_data.get("input_price_per_1m"),
            output_price_per_1m=detected_data.get("output_price_per_1m"),
        )
        
        return metadata
    
    @classmethod
    def _generate_display_name(cls, model_id: str) -> str:
        """Generate a human-readable display name from model ID."""
        # Remove common prefixes
        name = model_id
        for prefix in ["models/", "providers/"]:
            if name.startswith(prefix):
                name = name[len(prefix):]
        
        # Replace underscores and hyphens with spaces
        name = name.replace("_", " ").replace("-", " ")
        
        # Capitalize words
        name = " ".join(word.capitalize() for word in name.split())
        
        return name
    
    @classmethod
    def get_default_metadata(cls, model_id: str, protocol: str) -> ModelMetadata:
        """
        Get default metadata for a model.
        
        Args:
            model_id: Model identifier
            protocol: Protocol type (ollama, openai_compatible, etc.)
            
        Returns:
            ModelMetadata with defaults
        """
        # Determine provider from protocol
        provider_map = {
            "ollama": "ollama",
            "openai_compatible": "openai",
            "vllm": "vllm",
        }
        provider = provider_map.get(protocol, "unknown")
        
        return cls.detect_metadata(model_id, provider)


class ModelRegistry:
    """
    Central registry for model metadata.
    
    Manages model metadata from multiple sources:
    - Auto-detected from model names
    - User-configured overrides
    - Provider-specific metadata
    """
    
    def __init__(self):
        self._metadata_cache: Dict[str, ModelMetadata] = {}
        self._custom_metadata: Dict[str, Dict[str, Any]] = {}
    
    def get_metadata(
        self,
        model_id: str,
        provider: str,
        custom_overrides: Optional[Dict[str, Any]] = None
    ) -> ModelMetadata:
        """
        Get metadata for a model.
        
        Args:
            model_id: Model identifier
            provider: Provider name
            custom_overrides: Optional custom metadata overrides
            
        Returns:
            ModelMetadata
        """
        cache_key = f"{provider}:{model_id}"
        
        # Check cache
        if cache_key in self._metadata_cache and not custom_overrides:
            return self._metadata_cache[cache_key]
        
        # Detect base metadata
        metadata = ModelCapabilityDetector.detect_metadata(model_id, provider)
        
        # Apply custom overrides
        if custom_overrides:
            for key, value in custom_overrides.items():
                if hasattr(metadata, key):
                    setattr(metadata, key, value)
        
        # Cache and return
        self._metadata_cache[cache_key] = metadata
        return metadata
    
    def set_custom_metadata(
        self,
        model_id: str,
        provider: str,
        metadata: Dict[str, Any]
    ) -> None:
        """
        Set custom metadata for a model.
        
        Args:
            model_id: Model identifier
            provider: Provider name
            metadata: Custom metadata dictionary
        """
        cache_key = f"{provider}:{model_id}"
        self._custom_metadata[cache_key] = metadata
        
        # Invalidate cache
        if cache_key in self._metadata_cache:
            del self._metadata_cache[cache_key]
    
    def clear_cache(self) -> None:
        """Clear metadata cache."""
        self._metadata_cache.clear()


# Global registry instance
_model_registry = ModelRegistry()


def get_model_registry() -> ModelRegistry:
    """Get global model registry instance."""
    return _model_registry
