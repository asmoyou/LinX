"""
LLM Provider Configuration Models

Pydantic models for provider configuration and management.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 18.8: Settings Page
- Task 6.21.1: Create provider configuration model
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ProviderProtocol(str, Enum):
    """Supported LLM provider protocols."""
    
    OLLAMA = "ollama"
    OPENAI_COMPATIBLE = "openai_compatible"


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""
    
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    protocol: ProviderProtocol
    base_url: str = Field(..., min_length=1)
    api_key: Optional[str] = Field(default=None, min_length=1)
    timeout: int = Field(default=30, ge=5, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    enabled: bool = Field(default=True)
    selected_models: List[str] = Field(default_factory=list)
    
    @field_validator('base_url')
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base URL format."""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Base URL must start with http:// or https://')
        # Remove trailing slash
        return v.rstrip('/')
    
    @field_validator('api_key')
    @classmethod
    def validate_api_key(cls, v: Optional[str], info) -> Optional[str]:
        """Validate API key is provided for OpenAI Compatible protocol."""
        protocol = info.data.get('protocol')
        if protocol == ProviderProtocol.OPENAI_COMPATIBLE and not v:
            raise ValueError('API key is required for OpenAI Compatible protocol')
        return v
    
    class Config:
        use_enum_values = True


class ProviderCreateRequest(BaseModel):
    """Request model for creating a new provider."""
    
    name: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    protocol: ProviderProtocol
    base_url: str = Field(..., min_length=1)
    api_key: Optional[str] = Field(default=None)
    timeout: int = Field(default=30, ge=5, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    selected_models: List[str] = Field(default_factory=list)


class ProviderUpdateRequest(BaseModel):
    """Request model for updating an existing provider."""
    
    protocol: Optional[ProviderProtocol] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: Optional[int] = Field(default=None, ge=5, le=300)
    max_retries: Optional[int] = Field(default=None, ge=0, le=10)
    enabled: Optional[bool] = None
    selected_models: Optional[List[str]] = None


class TestConnectionRequest(BaseModel):
    """Request model for testing provider connection."""
    
    protocol: ProviderProtocol
    base_url: str = Field(..., min_length=1)
    api_key: Optional[str] = None
    timeout: int = Field(default=30, ge=5, le=300)


class TestConnectionResponse(BaseModel):
    """Response model for connection test."""
    
    success: bool
    message: str
    available_models: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class ProviderResponse(BaseModel):
    """Response model for provider information."""
    
    name: str
    protocol: str
    base_url: str
    timeout: int
    max_retries: int
    enabled: bool
    selected_models: List[str]
    has_api_key: bool  # Don't expose actual API key
    is_config_based: bool = Field(default=False)  # True if from config.yaml, False if from database
    
    @classmethod
    def from_config(cls, config: ProviderConfig, is_config_based: bool = False) -> "ProviderResponse":
        """Create response from config."""
        return cls(
            name=config.name,
            protocol=config.protocol,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=config.max_retries,
            enabled=config.enabled,
            selected_models=config.selected_models,
            has_api_key=bool(config.api_key),
            is_config_based=is_config_based,
        )


class ProviderListResponse(BaseModel):
    """Response model for listing providers."""
    
    providers: List[ProviderResponse]
    total: int
