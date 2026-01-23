"""
Model Metadata and Capabilities

Defines model metadata structure and capability detection.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Provider Management
"""

from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ModelCapability(str, Enum):
    """Model capabilities enumeration."""
    
    TEXT = "text"  # Text generation
    CHAT = "chat"  # Chat/conversation
    CODE = "code"  # Code generation
    FUNCTION_CALLING = "function_calling"  # Function/tool calling
    VISION = "vision"  # Image understanding
    AUDIO = "audio"  # Audio processing
    VIDEO = "video"  # Video understanding
    EMBEDDING = "embedding"  # Text embeddings
    REASONING = "reasoning"  # Chain-of-thought reasoning
    MULTIMODAL = "multimodal"  # Multiple modalities


class ModelMetadata(BaseModel):
    """Model metadata and configuration."""
    
    # Basic info
    model_id: str = Field(..., description="Model identifier")
    display_name: Optional[str] = Field(None, description="Human-readable name")
    description: Optional[str] = Field(None, description="Model description")
    
    # Capabilities
    capabilities: List[ModelCapability] = Field(
        default_factory=lambda: [ModelCapability.TEXT, ModelCapability.CHAT],
        description="Model capabilities"
    )
    
    # Context and tokens
    context_window: Optional[int] = Field(None, description="Maximum context window size")
    max_output_tokens: Optional[int] = Field(None, description="Maximum output tokens")
    
    # Parameters
    default_temperature: float = Field(0.7, description="Default temperature")
    temperature_range: tuple[float, float] = Field((0.0, 2.0), description="Temperature range")
    supports_streaming: bool = Field(True, description="Supports streaming responses")
    supports_system_prompt: bool = Field(True, description="Supports system prompts")
    
    # Pricing (optional, for cost tracking)
    input_price_per_1k: Optional[float] = Field(None, description="Input price per 1K tokens (USD)")
    output_price_per_1k: Optional[float] = Field(None, description="Output price per 1K tokens (USD)")
    
    # Additional metadata
    version: Optional[str] = Field(None, description="Model version")
    release_date: Optional[str] = Field(None, description="Release date")
    deprecated: bool = Field(False, description="Whether model is deprecated")
    
    class Config:
        use_enum_values = True


class ModelCapabilityDetector:
    """Detect model capabilities based on model name and provider."""
    
    # Known model patterns and their capabilities
    CAPABILITY_PATTERNS = {
        # OpenAI models
        "gpt-4": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.CODE, 
                  ModelCapability.FUNCTION_CALLING, ModelCapability.REASONING],
        "gpt-4-vision": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.VISION, 
                        ModelCapability.MULTIMODAL],
        "gpt-3.5": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.CODE],
        "text-embedding": [ModelCapability.EMBEDDING],
        
        # Anthropic models
        "claude": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.CODE, 
                   ModelCapability.REASONING],
        
        # GLM models (智谱AI)
        "glm": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.CODE, 
                ModelCapability.REASONING],
        "glm-4v": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.VISION, 
                   ModelCapability.MULTIMODAL],
        
        # Ollama models
        "llama": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.CODE],
        "mistral": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.CODE],
        "codellama": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.CODE],
        "llava": [ModelCapability.TEXT, ModelCapability.CHAT, ModelCapability.VISION, 
                  ModelCapability.MULTIMODAL],
        
        # Embedding models
        "embedding": [ModelCapability.EMBEDDING],
        "bge": [ModelCapability.EMBEDDING],
        "nomic-embed": [ModelCapability.EMBEDDING],
    }
    
    @classmethod
    def detect_capabilities(cls, model_name: str, provider_protocol: str = None) -> List[ModelCapability]:
        """
        Detect model capabilities based on model name.
        
        Args:
            model_name: Model identifier
            provider_protocol: Provider protocol (ollama, openai_compatible, etc.)
            
        Returns:
            List of detected capabilities
        """
        model_lower = model_name.lower()
        
        # Check known patterns
        for pattern, capabilities in cls.CAPABILITY_PATTERNS.items():
            if pattern in model_lower:
                return capabilities
        
        # Default capabilities for unknown models
        return [ModelCapability.TEXT, ModelCapability.CHAT]
    
    @classmethod
    def get_default_metadata(cls, model_name: str, provider_protocol: str = None) -> ModelMetadata:
        """
        Get default metadata for a model.
        
        Args:
            model_name: Model identifier
            provider_protocol: Provider protocol
            
        Returns:
            ModelMetadata with detected capabilities
        """
        capabilities = cls.detect_capabilities(model_name, provider_protocol)
        
        # Estimate context window based on model name
        context_window = cls._estimate_context_window(model_name)
        
        return ModelMetadata(
            model_id=model_name,
            display_name=model_name,
            capabilities=capabilities,
            context_window=context_window,
            supports_streaming=True,
            supports_system_prompt=True,
        )
    
    @classmethod
    def _estimate_context_window(cls, model_name: str) -> Optional[int]:
        """Estimate context window size based on model name."""
        model_lower = model_name.lower()
        
        # Known context windows
        if "gpt-4-turbo" in model_lower or "gpt-4-1106" in model_lower:
            return 128000
        elif "gpt-4-32k" in model_lower:
            return 32768
        elif "gpt-4" in model_lower:
            return 8192
        elif "gpt-3.5-turbo-16k" in model_lower:
            return 16384
        elif "gpt-3.5" in model_lower:
            return 4096
        elif "claude-2" in model_lower:
            return 100000
        elif "claude" in model_lower:
            return 9000
        elif "glm-4" in model_lower:
            return 128000
        elif "llama-2-70b" in model_lower:
            return 4096
        elif "llama-2" in model_lower:
            return 4096
        elif "mistral" in model_lower:
            return 8192
        
        # Default
        return 4096


def get_capability_icon(capability: ModelCapability) -> str:
    """Get emoji icon for capability."""
    icons = {
        ModelCapability.TEXT: "📝",
        ModelCapability.CHAT: "💬",
        ModelCapability.CODE: "💻",
        ModelCapability.FUNCTION_CALLING: "🔧",
        ModelCapability.VISION: "👁️",
        ModelCapability.AUDIO: "🎵",
        ModelCapability.VIDEO: "🎬",
        ModelCapability.EMBEDDING: "🔢",
        ModelCapability.REASONING: "🧠",
        ModelCapability.MULTIMODAL: "🎨",
    }
    return icons.get(capability, "❓")


def get_capability_label(capability: ModelCapability) -> str:
    """Get human-readable label for capability."""
    labels = {
        ModelCapability.TEXT: "Text",
        ModelCapability.CHAT: "Chat",
        ModelCapability.CODE: "Code",
        ModelCapability.FUNCTION_CALLING: "Functions",
        ModelCapability.VISION: "Vision",
        ModelCapability.AUDIO: "Audio",
        ModelCapability.VIDEO: "Video",
        ModelCapability.EMBEDDING: "Embeddings",
        ModelCapability.REASONING: "Reasoning",
        ModelCapability.MULTIMODAL: "Multimodal",
    }
    return labels.get(capability, capability.value)
