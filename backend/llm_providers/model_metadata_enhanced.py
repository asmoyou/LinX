"""
Enhanced Model Metadata Management

Comprehensive model metadata detection based on cherry-studio's implementation.
Provides accurate capability detection for vision, reasoning, function calling, and more.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Provider Integration
- cherry-studio: src/renderer/src/config/models/
"""

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ModelCapability(str, Enum):
    """Model capabilities."""
    
    CHAT = "chat"
    CODE_GENERATION = "code_generation"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    FUNCTION_CALLING = "function_calling"
    VISION = "vision"
    AUDIO = "audio"
    REASONING = "reasoning"
    STREAMING = "streaming"
    SYSTEM_PROMPT = "system_prompt"
    JSON_MODE = "json_mode"
    WEB_SEARCH = "web_search"
    IMAGE_GENERATION = "image_generation"
    IMAGE_ENHANCEMENT = "image_enhancement"


class ModelType(str, Enum):
    """Model types for categorization."""
    
    CHAT = "chat"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    VISION = "vision"
    REASONING = "reasoning"
    CODE = "code"
    IMAGE_GENERATION = "image_generation"


class ModelMetadata(BaseModel):
    """Comprehensive model metadata."""
    
    model_id: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    provider: str
    model_type: ModelType = ModelType.CHAT
    
    # Capabilities
    capabilities: List[ModelCapability] = Field(default_factory=list)
    
    # Context and tokens
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    
    # Thinking/Reasoning tokens (for reasoning models)
    min_thinking_tokens: Optional[int] = None
    max_thinking_tokens: Optional[int] = None
    
    # Parameters
    default_temperature: float = 0.7
    temperature_range: Tuple[float, float] = (0.0, 2.0)
    default_top_p: float = 1.0
    top_p_range: Tuple[float, float] = (0.0, 1.0)
    
    # Features
    supports_streaming: bool = True
    supports_system_prompt: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    supports_json_mode: bool = False
    supports_reasoning: bool = False
    
    # Reasoning effort options (for models that support it)
    reasoning_effort_options: Optional[List[str]] = None
    
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


class EnhancedModelCapabilityDetector:
    """
    Enhanced model capability detector based on cherry-studio's patterns.
    
    Provides comprehensive detection for:
    - Vision models (including Qwen-VL, GPT-4V, Claude-3, etc.)
    - Reasoning models (o1, DeepSeek-R1, QwQ, etc.)
    - Function calling models
    - Embedding and rerank models
    - Image generation models
    """
    
    # Vision model patterns (from cherry-studio/vision.ts)
    VISION_ALLOWED_PATTERNS = [
        r'llava', r'moondream', r'minicpm',
        r'gemini-1\.5', r'gemini-2\.0', r'gemini-2\.5',
        r'gemini-3(?:-flash|-pro)(?:-preview)?',
        r'gemini-(flash|pro|flash-lite)-latest',
        r'gemini-exp',
        r'claude-3', r'claude-haiku-4', r'claude-sonnet-4', r'claude-opus-4',
        r'vision',
        r'glm-4(?:\.\d+)?v(?:-[\w-]+)?',
        r'qwen-vl', r'qwen2-vl', r'qwen2\.5-vl', r'qwen3-vl',
        r'qwen2\.5-omni', r'qwen3-omni(?:-[\w-]+)?',
        r'qvq', r'internvl2',
        r'grok-vision-beta', r'grok-4(?:-[\w-]+)?',
        r'pixtral',
        r'gpt-4(?:-[\w-]+)', r'gpt-4\.1(?:-[\w-]+)?',
        r'gpt-4o(?:-[\w-]+)?', r'gpt-4\.5(?:-[\w-]+)',
        r'gpt-5(?:-[\w-]+)?',
        r'chatgpt-4o(?:-[\w-]+)?',
        r'o1(?:-[\w-]+)?', r'o3(?:-[\w-]+)?', r'o4(?:-[\w-]+)?',
        r'deepseek-vl(?:[\w-]+)?',
        r'kimi-latest', r'kimi-vl-a3b-thinking(?:-[\w-]+)?',
        r'gemma-3(?:-[\w-]+)',
        r'doubao-seed-1[.-][68](?:-[\w-]+)?',
        r'doubao-seed-code(?:-[\w-]+)?',
        r'kimi-thinking-preview',
        r'gemma3(?:[-:\w]+)?',
        r'llama-guard-4(?:-[\w-]+)?', r'llama-4(?:-[\w-]+)?',
        r'step-1o(?:.*vision)?', r'step-1v(?:-[\w-]+)?',
        r'qwen-omni(?:-[\w-]+)?',
        r'mistral-large-(2512|latest)',
        r'mistral-medium-(2508|latest)',
        r'mistral-small-(2506|latest)',
    ]
    
    VISION_EXCLUDED_PATTERNS = [
        r'gpt-4-\d+-preview',
        r'gpt-4-turbo-preview',
        r'gpt-4-32k',
        r'gpt-4-\d+',
        r'o1-mini', r'o3-mini',
        r'o1-preview',
        r'AIDC-AI/Marco-o1',
    ]
    
    # Reasoning model patterns (from cherry-studio/reasoning.ts)
    REASONING_PATTERNS = [
        r'o\d+(?:-[\w-]+)?',
        r'.*\b(?:reasoning|reasoner|thinking|think)\b.*',
        r'.*-[rR]\d+.*',
        r'.*\bqwq(?:-[\w-]+)?\b.*',
        r'.*\bhunyuan-t1(?:-[\w-]+)?\b.*',
        r'.*\bglm-zero-preview\b.*',
        r'.*\bgrok-(?:3-mini|4|4-fast)(?:-[\w-]+)?\b.*',
        r'claude-3-7-sonnet', r'claude-3\.7-sonnet',
        r'claude-sonnet-4', r'claude-opus-4', r'claude-haiku-4',
        r'gemini-2\.5.*(?:-latest)?',
        r'gemini-3(?:\.\d+)?-(?:flash|pro)(?:-preview)?',
        r'qwen3.*thinking',
        r'qwq', r'qvq',
        r'deepseek-v3(?:\.\d|-\d)',
        r'deepseek-chat',
        r'hunyuan-a13b', r'hunyuan-t1',
        r'glm-4\.5', r'glm-4\.6', r'glm-4\.7', r'glm-z1',
        r'ring-1t', r'ring-mini', r'ring-flash',
        r'step-3', r'step-r1-v-mini',
        r'minimax-m1', r'minimax-m2', r'minimax-m2\.1',
        r'baichuan-m2', r'baichuan-m3',
        r'mimo-v2-flash',
        r'doubao-seed-1[.-][68]', r'doubao-seed-code',
        r'doubao-1-5-thinking-pro-m',
        r'sonar-deep-research',
    ]
    
    # Function calling model patterns (from cherry-studio/tooluse.ts)
    FUNCTION_CALLING_PATTERNS = [
        r'gpt-4o', r'gpt-4o-mini', r'gpt-4', r'gpt-4\.5',
        r'gpt-oss(?:-[\w-]+)', r'gpt-5(?:-[0-9-]+)?',
        r'o[134](?:-[\w-]+)?',
        r'claude',
        r'qwen', r'qwen3',
        r'hunyuan',
        r'deepseek',
        r'glm-4(?:-[\w-]+)?', r'glm-4\.5(?:-[\w-]+)?', r'glm-4\.7(?:-[\w-]+)?',
        r'learnlm(?:-[\w-]+)?',
        r'gemini(?:-[\w-]+)?',
        r'grok-3(?:-[\w-]+)?',
        r'doubao-seed-1[.-][68](?:-[\w-]+)?',
        r'doubao-seed-code(?:-[\w-]+)?',
        r'kimi-k2(?:-[\w-]+)?',
        r'ling-\w+(?:-[\w-]+)?',
        r'ring-\w+(?:-[\w-]+)?',
        r'minimax-m2(?:\.1)?',
        r'mimo-v2-flash',
    ]
    
    FUNCTION_CALLING_EXCLUDED_PATTERNS = [
        r'aqa(?:-[\w-]+)?',
        r'imagen(?:-[\w-]+)?',
        r'o1-mini', r'o1-preview',
        r'AIDC-AI/Marco-o1',
        r'gemini-1(?:\.[\w-]+)?',
        r'qwen-mt(?:-[\w-]+)?',
        r'gpt-5-chat(?:-[\w-]+)?',
        r'glm-4\.5v',
        r'gemini-2\.5-flash-image(?:-[\w-]+)?',
        r'gemini-2\.0-flash-preview-image-generation',
        r'gemini-3(?:\.\d+)?-pro-image(?:-[\w-]+)?',
        r'deepseek-v3\.2-speciale',
    ]
    
    # Embedding model patterns (from cherry-studio/embedding.ts)
    EMBEDDING_PATTERNS = [
        r'^text-', r'embed', r'bge-', r'e5-',
        r'LLM2Vec', r'retrieval', r'uae-', r'gte-',
        r'jina-clip', r'jina-embeddings', r'voyage-',
    ]
    
    # Rerank model patterns
    RERANK_PATTERNS = [
        r'rerank', r're-rank', r're-ranker', r're-ranking',
        r'retrieval', r'retriever',
    ]
    
    # Image generation model patterns
    IMAGE_GENERATION_PATTERNS = [
        r'dall-e(?:-[\w-]+)?', r'gpt-image(?:-[\w-]+)?',
        r'grok-2-image(?:-[\w-]+)?',
        r'imagen(?:-[\w-]+)?',
        r'flux(?:-[\w-]+)?',
        r'stable-?diffusion(?:-[\w-]+)?',
        r'stabilityai(?:-[\w-]+)?',
        r'sd-[\w-]+', r'sdxl(?:-[\w-]+)?',
        r'cogview(?:-[\w-]+)?',
        r'qwen-image(?:-[\w-]+)?',
        r'janus(?:-[\w-]+)?',
        r'midjourney(?:-[\w-]+)?', r'mj-[\w-]+',
        r'z-image(?:-[\w-]+)?',
        r'longcat-image(?:-[\w-]+)?',
        r'hunyuanimage(?:-[\w-]+)?',
        r'seedream(?:-[\w-]+)?',
        r'kandinsky(?:-[\w-]+)?',
    ]
    
    # Thinking token limits (from cherry-studio/reasoning.ts)
    THINKING_TOKEN_LIMITS = {
        r'gemini-2\.5-flash-lite.*': (512, 24576),
        r'gemini-.*-flash.*': (0, 24576),
        r'gemini-.*-pro.*': (128, 32768),
        r'qwen3-235b-a22b-thinking-2507': (0, 81920),
        r'qwen3-30b-a3b-thinking-2507': (0, 81920),
        r'qwen3-vl-235b-a22b-thinking': (0, 81920),
        r'qwen3-vl-30b-a3b-thinking': (0, 81920),
        r'qwen-plus-2025-07-14': (0, 38912),
        r'qwen-plus-2025-04-28': (0, 38912),
        r'qwen3-1\.7b': (0, 30720),
        r'qwen3-0\.6b': (0, 30720),
        r'qwen-plus.*': (0, 81920),
        r'qwen-turbo.*': (0, 38912),
        r'qwen-flash.*': (0, 81920),
        r'qwen3-(?!max).*': (1024, 38912),
        r'(?:anthropic\.)?claude-3[.-]7.*sonnet.*(?:-v\d+:\d+)?': (1024, 64000),
        r'(?:anthropic\.)?claude-(?:haiku|sonnet|opus)-4[.-]5.*(?:-v\d+:\d+)?': (1024, 64000),
        r'(?:anthropic\.)?claude-opus-4[.-]1.*(?:-v\d+:\d+)?': (1024, 32000),
        r'(?:anthropic\.)?claude-sonnet-4(?:[.-]0)?(?:[@-](?:\d{4,}|[a-z][\w-]*))?(?:-v\d+:\d+)?': (1024, 64000),
        r'(?:anthropic\.)?claude-opus-4(?:[.-]0)?(?:[@-](?:\d{4,}|[a-z][\w-]*))?(?:-v\d+:\d+)?': (1024, 32000),
        r'baichuan-m2': (0, 30000),
        r'baichuan-m3': (0, 30000),
    }
    
    @classmethod
    def _matches_pattern(cls, text: str, patterns: List[str], excluded: List[str] = None) -> bool:
        """Check if text matches any pattern and doesn't match excluded patterns."""
        text_lower = text.lower()
        
        # Check excluded patterns first
        if excluded:
            for pattern in excluded:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    return False
        
        # Check allowed patterns
        for pattern in patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                return True
        
        return False
    
    @classmethod
    def is_vision_model(cls, model_id: str, model_name: str = None) -> bool:
        """Detect if model supports vision capabilities."""
        # Check both model_id and model_name (for providers like doubao)
        for text in [model_id, model_name]:
            if text and cls._matches_pattern(
                text,
                cls.VISION_ALLOWED_PATTERNS,
                cls.VISION_EXCLUDED_PATTERNS
            ):
                return True
        return False
    
    @classmethod
    def is_reasoning_model(cls, model_id: str, model_name: str = None) -> bool:
        """Detect if model supports reasoning capabilities."""
        for text in [model_id, model_name]:
            if text and cls._matches_pattern(text, cls.REASONING_PATTERNS):
                return True
        return False
    
    @classmethod
    def is_function_calling_model(cls, model_id: str, model_name: str = None) -> bool:
        """Detect if model supports function calling."""
        for text in [model_id, model_name]:
            if text and cls._matches_pattern(
                text,
                cls.FUNCTION_CALLING_PATTERNS,
                cls.FUNCTION_CALLING_EXCLUDED_PATTERNS
            ):
                return True
        return False
    
    @classmethod
    def is_embedding_model(cls, model_id: str) -> bool:
        """Detect if model is an embedding model."""
        return cls._matches_pattern(model_id, cls.EMBEDDING_PATTERNS)
    
    @classmethod
    def is_rerank_model(cls, model_id: str) -> bool:
        """Detect if model is a rerank model."""
        return cls._matches_pattern(model_id, cls.RERANK_PATTERNS)
    
    @classmethod
    def is_image_generation_model(cls, model_id: str) -> bool:
        """Detect if model is an image generation model."""
        return cls._matches_pattern(model_id, cls.IMAGE_GENERATION_PATTERNS)
    
    @classmethod
    def get_thinking_token_limits(cls, model_id: str) -> Optional[Tuple[int, int]]:
        """Get thinking token limits for reasoning models."""
        model_lower = model_id.lower()
        for pattern, limits in cls.THINKING_TOKEN_LIMITS.items():
            if re.search(pattern, model_lower, re.IGNORECASE):
                return limits
        return None
    
    @classmethod
    def detect_model_family(cls, model_id: str) -> Optional[str]:
        """Detect model family from model ID."""
        model_lower = model_id.lower()
        
        families = {
            'gpt-4': r'gpt-4',
            'gpt-3.5': r'gpt-3\.5',
            'gpt-5': r'gpt-5',
            'o1': r'\bo1\b',
            'o3': r'\bo3\b',
            'claude-3': r'claude-3',
            'claude-4': r'claude-(?:sonnet|opus|haiku)-4',
            'gemini': r'gemini',
            'qwen': r'qwen',
            'deepseek': r'deepseek',
            'llama-3': r'llama-3',
            'llama-2': r'llama-2',
            'mistral': r'mistral',
            'glm': r'glm-',
            'doubao': r'doubao',
            'hunyuan': r'hunyuan',
            'kimi': r'kimi',
            'minimax': r'minimax',
            'baichuan': r'baichuan',
        }
        
        for family, pattern in families.items():
            if re.search(pattern, model_lower):
                return family
        
        return None
    
    @classmethod
    def extract_size(cls, model_id: str) -> Optional[str]:
        """Extract model size (e.g., 7B, 70B) from model ID."""
        match = re.search(r'(\d+[bB])', model_id)
        return match.group(1).upper() if match else None
    
    @classmethod
    def extract_quantization(cls, model_id: str) -> Optional[str]:
        """Extract quantization info (e.g., Q4_K_M) from model ID."""
        match = re.search(r'(Q\d+_[A-Z0-9_]+)', model_id, re.IGNORECASE)
        return match.group(1).upper() if match else None
    
    @classmethod
    def detect_metadata(cls, model_id: str, provider: str, model_name: str = None) -> ModelMetadata:
        """
        Detect comprehensive model metadata.
        
        Args:
            model_id: Model identifier
            provider: Provider name
            model_name: Optional model display name (used for some providers like doubao)
            
        Returns:
            ModelMetadata with detected capabilities
        """
        model_lower = model_id.lower()
        
        # Detect model type
        if cls.is_embedding_model(model_id):
            model_type = ModelType.EMBEDDING
        elif cls.is_rerank_model(model_id):
            model_type = ModelType.RERANK
        elif cls.is_image_generation_model(model_id):
            model_type = ModelType.IMAGE_GENERATION
        elif cls.is_reasoning_model(model_id, model_name):
            model_type = ModelType.REASONING
        elif cls.is_vision_model(model_id, model_name):
            model_type = ModelType.VISION
        elif 'code' in model_lower or 'coder' in model_lower:
            model_type = ModelType.CODE
        else:
            model_type = ModelType.CHAT
        
        # Detect capabilities
        capabilities = []
        
        if model_type == ModelType.EMBEDDING:
            capabilities = [ModelCapability.EMBEDDING]
        elif model_type == ModelType.RERANK:
            capabilities = [ModelCapability.RERANK]
        elif model_type == ModelType.IMAGE_GENERATION:
            capabilities = [ModelCapability.IMAGE_GENERATION]
        else:
            # Chat-based models
            capabilities = [
                ModelCapability.CHAT,
                ModelCapability.STREAMING,
                ModelCapability.SYSTEM_PROMPT,
            ]
            
            if cls.is_vision_model(model_id, model_name):
                capabilities.append(ModelCapability.VISION)
            
            if cls.is_reasoning_model(model_id, model_name):
                capabilities.append(ModelCapability.REASONING)
            
            if cls.is_function_calling_model(model_id, model_name):
                capabilities.append(ModelCapability.FUNCTION_CALLING)
            
            if 'code' in model_lower or 'coder' in model_lower:
                capabilities.append(ModelCapability.CODE_GENERATION)
        
        # Get thinking token limits for reasoning models
        thinking_limits = cls.get_thinking_token_limits(model_id)
        min_thinking = thinking_limits[0] if thinking_limits else None
        max_thinking = thinking_limits[1] if thinking_limits else None
        
        # Detect context window based on model family
        context_window = cls._detect_context_window(model_id)
        max_output_tokens = cls._detect_max_output_tokens(model_id)
        
        # Build metadata
        metadata = ModelMetadata(
            model_id=model_id,
            display_name=cls._generate_display_name(model_id),
            provider=provider,
            model_type=model_type,
            capabilities=capabilities,
            family=cls.detect_model_family(model_id),
            size=cls.extract_size(model_id),
            quantization=cls.extract_quantization(model_id),
            context_window=context_window,
            max_output_tokens=max_output_tokens,
            min_thinking_tokens=min_thinking,
            max_thinking_tokens=max_thinking,
            supports_streaming=model_type not in [ModelType.EMBEDDING, ModelType.RERANK],
            supports_system_prompt=model_type not in [ModelType.EMBEDDING, ModelType.RERANK, ModelType.IMAGE_GENERATION],
            supports_function_calling=ModelCapability.FUNCTION_CALLING in capabilities,
            supports_vision=ModelCapability.VISION in capabilities,
            supports_reasoning=ModelCapability.REASONING in capabilities,
        )
        
        return metadata
    
    @classmethod
    def _detect_context_window(cls, model_id: str) -> Optional[int]:
        """Detect context window size based on model patterns."""
        model_lower = model_id.lower()
        
        # Known context windows
        if 'gpt-4' in model_lower or 'gpt-5' in model_lower:
            return 128000
        elif 'gpt-3.5' in model_lower:
            return 16385
        elif 'claude-3' in model_lower or 'claude-4' in model_lower:
            return 200000
        elif 'gemini' in model_lower:
            return 1000000 if '1.5' in model_lower or '2.0' in model_lower else 32768
        elif 'qwen' in model_lower:
            return 32768
        elif 'deepseek' in model_lower:
            return 64000
        elif 'llama-3' in model_lower:
            return 8192
        elif 'mistral' in model_lower:
            return 32768
        
        return None
    
    @classmethod
    def _detect_max_output_tokens(cls, model_id: str) -> Optional[int]:
        """Detect max output tokens based on model patterns."""
        model_lower = model_id.lower()
        
        if 'gpt-4' in model_lower or 'gpt-5' in model_lower:
            return 4096
        elif 'claude' in model_lower:
            return 4096
        elif 'gemini' in model_lower:
            return 8192
        elif 'qwen' in model_lower:
            return 2048
        
        return None
    
    @classmethod
    def _generate_display_name(cls, model_id: str) -> str:
        """Generate a human-readable display name from model ID."""
        # Remove common prefixes
        name = model_id
        for prefix in ["models/", "providers/", "anthropic.", "openai/"]:
            if name.startswith(prefix):
                name = name[len(prefix):]
        
        # Replace underscores and hyphens with spaces
        name = name.replace("_", " ").replace("-", " ")
        
        # Capitalize words
        name = " ".join(word.capitalize() for word in name.split())
        
        return name


# Singleton registry instance
_enhanced_detector = EnhancedModelCapabilityDetector()


def get_enhanced_detector() -> EnhancedModelCapabilityDetector:
    """Get singleton enhanced detector instance."""
    return _enhanced_detector
