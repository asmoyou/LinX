"""
LLM Provider Management API Routes

Provides endpoints for managing LLM providers, models, and configurations.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Provider Integration
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user, require_role
from access_control.rbac import Role
from database.connection import get_db_session
from llm_providers.db_manager import ProviderDBManager
from llm_providers.models import (
    ProviderCreateRequest,
    ProviderListResponse,
    ProviderResponse,
    ProviderUpdateRequest,
    TestConnectionRequest,
    TestConnectionResponse,
)
from llm_providers.protocol_clients import get_protocol_client

try:
    from llm_providers.router import get_llm_provider
except ImportError:
    # Fallback for development/testing
    logger.warning("LLM providers not available - using mock")
    get_llm_provider = None

logger = logging.getLogger(__name__)

router = APIRouter(tags=["LLM Providers"])


# Request/Response Models
class ProviderStatus(BaseModel):
    """Provider health status"""

    name: str
    healthy: bool
    available_models: List[str]
    is_config_based: bool = False  # True if from config.yaml, cannot be deleted


class ModelInfo(BaseModel):
    """Model information"""

    name: str
    provider: str
    task_types: List[str]


class LLMConfigResponse(BaseModel):
    """LLM configuration response"""

    providers: Dict[str, ProviderStatus]
    default_provider: str
    fallback_enabled: bool
    model_mapping: Dict[str, Dict[str, str]]


class TestGenerationRequest(BaseModel):
    """Test generation request"""

    prompt: str = Field(..., min_length=1, max_length=1000)
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=100, ge=1, le=4000)


class TestGenerationResponse(BaseModel):
    """Test generation response"""

    content: str
    model: str
    provider: str
    tokens_used: int
    success: bool


# Endpoints
@router.get("/providers", response_model=LLMConfigResponse)
async def get_providers(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get all LLM providers and their status.

    Returns provider health status, available models, and configuration.
    Marks providers from config.yaml as is_config_based=True (cannot be deleted via API).
    """
    if get_llm_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM providers not configured",
        )

    try:
        llm_router = get_llm_provider()

        # Get health status for all providers
        health_status = await llm_router.health_check_all()

        # Get available models for each provider
        available_models = await llm_router.list_available_models()

        # Get list of providers from database to determine which are config-based
        db_provider_names = set()
        try:
            with get_db_session() as db:
                db_manager = ProviderDBManager(db)
                db_providers = db_manager.list_providers()
                db_provider_names = {p.name for p in db_providers}
        except Exception as e:
            logger.warning(f"Failed to get database providers: {e}")

        # Build provider status
        providers = {}
        for provider_name in llm_router.providers.keys():
            # Provider is config-based if it's NOT in the database
            is_config_based = provider_name not in db_provider_names
            
            providers[provider_name] = ProviderStatus(
                name=provider_name,
                healthy=health_status.get(provider_name, False),
                available_models=available_models.get(provider_name, []),
                is_config_based=is_config_based,
            )

        return LLMConfigResponse(
            providers=providers,
            default_provider=llm_router.config.get("default_provider", "ollama"),
            fallback_enabled=llm_router.fallback_enabled,
            model_mapping=llm_router.model_mapping,
        )

    except Exception as e:
        logger.error(f"Failed to get LLM providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get LLM providers: {str(e)}",
        )


@router.get("/providers/{provider_name}/models", response_model=List[str])
async def get_provider_models(
    provider_name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get available models for a specific provider.

    Args:
        provider_name: Name of the provider (ollama, vllm, openai, anthropic)
    """
    if get_llm_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM providers not configured",
        )

    try:
        llm_router = get_llm_provider()

        if provider_name not in llm_router.providers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider '{provider_name}' not found",
            )

        provider = llm_router.providers[provider_name]
        models = await provider.list_models()

        return models

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get models for provider {provider_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get models: {str(e)}",
        )


@router.get("/providers/{provider_name}/health", response_model=Dict[str, bool])
async def check_provider_health(
    provider_name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Check health status of a specific provider.

    Args:
        provider_name: Name of the provider
    """
    if get_llm_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM providers not configured",
        )

    try:
        llm_router = get_llm_provider()

        if provider_name not in llm_router.providers:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider '{provider_name}' not found",
            )

        provider = llm_router.providers[provider_name]
        healthy = await provider.health_check()

        return {"healthy": healthy}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check health for provider {provider_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check health: {str(e)}",
        )


@router.post("/test", response_model=TestGenerationResponse)
async def test_generation(
    request: TestGenerationRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Test LLM generation with a prompt.

    Useful for testing provider connectivity and model performance.
    """
    if get_llm_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM providers not configured",
        )

    try:
        llm_router = get_llm_provider()

        # Generate response
        response = await llm_router.generate(
            prompt=request.prompt,
            provider=request.provider,
            model=request.model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return TestGenerationResponse(
            content=response.content,
            model=response.model,
            provider=response.provider,
            tokens_used=response.tokens_used,
            success=True,
        )

    except Exception as e:
        logger.error(f"Test generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test generation failed: {str(e)}",
        )


@router.get("/token-usage", response_model=Dict[str, int])
@require_role([Role.ADMIN])
async def get_token_usage(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get token usage statistics by provider.

    Requires admin permission.
    """
    if get_llm_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM providers not configured",
        )

    try:
        llm_router = get_llm_provider()
        return llm_router.get_token_usage()

    except Exception as e:
        logger.error(f"Failed to get token usage: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get token usage: {str(e)}",
        )


# Provider Management Endpoints (Admin Only)

@router.get("/providers/list", response_model=ProviderListResponse)
@require_role([Role.ADMIN])
async def list_providers(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    List all configured providers from both config.yaml and database.
    
    Providers from config.yaml are marked as is_config_based=True and cannot be deleted via API.
    Providers from database are marked as is_config_based=False and can be deleted.
    
    Requires admin permission.
    """
    try:
        provider_responses = []
        provider_names_seen = set()
        
        # First, get providers from database
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            db_providers = db_manager.list_providers()
            
            for p in db_providers:
                provider_responses.append(
                    ProviderResponse(
                        name=p.name,
                        protocol=p.protocol,
                        base_url=p.base_url,
                        timeout=p.timeout,
                        max_retries=p.max_retries,
                        selected_models=p.models,
                        enabled=p.enabled,
                        has_api_key=bool(p.api_key_encrypted),
                        is_config_based=False,
                    )
                )
                provider_names_seen.add(p.name)
        
        # Then, get providers from config.yaml
        try:
            from shared.config import get_config
            config = get_config()
            config_providers = config.get("llm.providers", {})
            
            for provider_name, provider_config in config_providers.items():
                # Skip if already in database (database takes precedence)
                if provider_name in provider_names_seen:
                    continue
                
                # Extract configuration
                enabled = provider_config.get("enabled", False)
                base_url = provider_config.get("base_url", "")
                models = list(provider_config.get("models", {}).values())
                timeout = config.get("llm.timeout_seconds", 30)
                max_retries = config.get("llm.max_retries", 3)
                
                # Determine protocol based on provider name or config
                protocol = "ollama" if provider_name == "ollama" else "openai_compatible"
                
                provider_responses.append(
                    ProviderResponse(
                        name=provider_name,
                        protocol=protocol,
                        base_url=base_url,
                        timeout=timeout,
                        max_retries=max_retries,
                        selected_models=models,
                        enabled=enabled,
                        has_api_key=False,  # Don't expose config.yaml API keys
                        is_config_based=True,
                    )
                )
        except Exception as e:
            logger.warning(f"Failed to load providers from config.yaml: {e}")
        
        return ProviderListResponse(
            providers=provider_responses,
            total=len(provider_responses),
        )
        
    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list providers: {str(e)}",
        )


@router.post("/providers", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
@require_role([Role.ADMIN])
async def create_provider(
    request: ProviderCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Create a new provider configuration.
    
    Requires admin permission.
    """
    try:
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            
            # Create provider in database
            provider = db_manager.create_provider(
                name=request.name,
                protocol=request.protocol,
                base_url=request.base_url,
                models=request.selected_models,
                api_key=request.api_key,
                timeout=request.timeout,
                max_retries=request.max_retries,
                created_by=current_user.user_id,
            )
            
            return ProviderResponse(
                name=provider.name,
                protocol=provider.protocol,
                base_url=provider.base_url,
                timeout=provider.timeout,
                max_retries=provider.max_retries,
                selected_models=provider.models,
                enabled=provider.enabled,
                has_api_key=bool(provider.api_key_encrypted),
            )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to create provider: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create provider: {str(e)}",
        )


@router.put("/providers/{name}", response_model=ProviderResponse)
@require_role([Role.ADMIN])
async def update_provider(
    name: str,
    request: ProviderUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Update an existing provider configuration.
    
    Requires admin permission.
    """
    try:
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            
            # Update provider in database
            provider = db_manager.update_provider(
                name=name,
                base_url=request.base_url,
                models=request.selected_models,
                api_key=request.api_key,
                timeout=request.timeout,
                max_retries=request.max_retries,
                enabled=request.enabled,
            )
            
            return ProviderResponse(
                name=provider.name,
                protocol=provider.protocol,
                base_url=provider.base_url,
                timeout=provider.timeout,
                max_retries=provider.max_retries,
                selected_models=provider.models,
                enabled=provider.enabled,
                has_api_key=bool(provider.api_key_encrypted),
            )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to update provider: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update provider: {str(e)}",
        )


@router.delete("/providers/{name}", status_code=status.HTTP_204_NO_CONTENT)
@require_role([Role.ADMIN])
async def delete_provider(
    name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Delete a provider configuration.
    
    Only dynamically added providers (stored in database) can be deleted.
    Providers defined in config.yaml cannot be deleted via API.
    
    Requires admin permission.
    """
    try:
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            
            # Check if provider exists in database
            provider = db_manager.get_provider(name)
            
            if not provider:
                # Check if it's a config.yaml provider
                from shared.config import get_config
                config = get_config()
                config_providers = config.get("llm.providers", {})
                
                if name in config_providers:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Provider '{name}' is defined in config.yaml and cannot be deleted via API. Please edit config.yaml directly.",
                    )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Provider '{name}' not found",
                    )
            
            # Delete provider from database
            deleted = db_manager.delete_provider(name)
            
            if not deleted:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Provider '{name}' not found",
                )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete provider: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete provider: {str(e)}",
        )


@router.post("/providers/test-connection", response_model=TestConnectionResponse)
@require_role([Role.ADMIN])
async def test_connection(
    request: TestConnectionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Test connection to a provider and fetch available models.
    
    Requires admin permission.
    """
    try:
        # Get protocol client
        client = get_protocol_client(request.protocol)
        
        # Fetch models
        models = await client.fetch_models(
            base_url=request.base_url,
            api_key=request.api_key,
            timeout=request.timeout,
        )
        
        return TestConnectionResponse(
            success=True,
            message=f"Successfully connected. Found {len(models)} models.",
            available_models=models,
        )
        
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return TestConnectionResponse(
            success=False,
            message="Connection failed",
            error=str(e),
        )

