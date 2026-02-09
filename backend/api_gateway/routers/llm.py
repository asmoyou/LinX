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
    Only returns providers from database (config.yaml providers are synced on startup).
    
    NOTE: This endpoint does NOT initialize providers (lazy loading).
    Health status is based on database configuration validity, not actual connection test.
    Use test_connection endpoint to verify actual connectivity.
    """
    if get_llm_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM providers not configured",
        )

    try:
        llm_router = get_llm_provider()

        # Get all providers from database only
        db_providers = {}
        try:
            with get_db_session() as db:
                db_manager = ProviderDBManager(db)
                db_provider_list = db_manager.list_providers()
                for p in db_provider_list:
                    db_providers[p.name] = p
        except Exception as e:
            logger.warning(f"Failed to get database providers: {e}")

        # Get default provider from config
        from shared.config import get_config
        config = get_config()

        # Build provider status from database only
        providers = {}
        
        for provider_name, db_provider in db_providers.items():
            # Health based on last test status
            if db_provider.last_test_status == 'success':
                healthy = True
            elif db_provider.last_test_status == 'failed':
                healthy = False
            else:
                # Untested or no test yet - assume healthy if enabled and has base_url
                healthy = db_provider.enabled and bool(db_provider.base_url)
            
            available_models = db_provider.models or []
            
            providers[provider_name] = ProviderStatus(
                name=provider_name,
                healthy=healthy,
                available_models=available_models,
                is_config_based=False,  # All providers are now in database
            )

        return LLMConfigResponse(
            providers=providers,
            default_provider=config.get("llm.default_provider", "ollama"),
            fallback_enabled=config.get("llm.enable_fallback", False),
            model_mapping=config.get("llm.model_mapping", {}),
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
    try:
        # Get models from database or config.yaml
        models = []
        
        # Try database first
        try:
            with get_db_session() as db:
                db_manager = ProviderDBManager(db)
                db_provider = db_manager.get_provider(provider_name)
                
                if db_provider and db_provider.enabled:
                    models = db_provider.models or []
                    if models:
                        return models
        except Exception as e:
            logger.warning(f"Failed to get models from database: {e}")
        
        # Try config.yaml
        from shared.config import get_config
        config = get_config()
        config_providers = config.get("llm.providers", {})
        
        if provider_name in config_providers:
            provider_config = config_providers[provider_name]
            models_dict = provider_config.get("models", {})
            if isinstance(models_dict, dict):
                models = list(set(models_dict.values()))
            elif isinstance(models_dict, list):
                models = models_dict
        
        if not models:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider '{provider_name}' not found or has no models",
            )
        
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
    
    This performs an actual health check (may take time).
    For quick status, use GET /providers instead.

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

        # Load provider on-demand
        provider = await llm_router._get_provider(provider_name)
        
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Provider '{provider_name}' not found",
            )

        # Perform actual health check
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
    
    Based on cherry-studio's checkApi implementation:
    - Detects model type (chat, embedding, rerank)
    - Uses appropriate test method for each type
    - Uses streaming for chat models (abort after first chunk)
    - Measures latency accurately
    
    Useful for testing provider connectivity and model performance.
    Returns detailed error information if generation fails.
    """
    import time
    import re
    
    try:
        start_time = time.time()
        
        # Get provider from database
        with get_db_session() as db:
            from llm_providers.db_manager import ProviderDBManager
            db_manager = ProviderDBManager(db)
            
            # Find provider
            if request.provider:
                db_provider = db_manager.get_provider(request.provider)
                if not db_provider:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Provider '{request.provider}' not found"
                    )
            else:
                # Use first available provider
                providers = db_manager.list_providers()
                enabled_providers = [p for p in providers if p.enabled]
                if not enabled_providers:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="No enabled providers found"
                    )
                db_provider = enabled_providers[0]
            
            # Get model
            model_to_test = request.model
            if not model_to_test:
                if not db_provider.models:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Provider '{db_provider.name}' has no models configured"
                    )
                model_to_test = db_provider.models[0]
            
            # Verify model exists in provider
            if model_to_test not in db_provider.models:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Model '{model_to_test}' not found in provider '{db_provider.name}'"
                )
            
            # Decrypt API key
            api_key = None
            if db_provider.api_key_encrypted:
                api_key = db_manager._decrypt_api_key(db_provider.api_key_encrypted)
            
            # Get model type from metadata (if available)
            model_type = "chat"  # default
            if db_provider.model_metadata and model_to_test in db_provider.model_metadata:
                metadata = db_provider.model_metadata[model_to_test]
                metadata_type = metadata.get('model_type', 'chat')
                if metadata_type in ['embedding', 'rerank']:
                    model_type = metadata_type
            else:
                # Fallback to pattern detection
                model_type = _detect_model_type(model_to_test)
            
            logger.info(f"Testing {model_type} model: {model_to_test} on {db_provider.name}")
            
            response_content = ""
            
            try:
                if model_type == "embedding":
                    # Test embedding model
                    response_content = await _test_embedding_model(
                        protocol=db_provider.protocol,
                        base_url=db_provider.base_url,
                        model=model_to_test,
                        api_key=api_key,
                        timeout=30
                    )
                elif model_type == "rerank":
                    # Test rerank model
                    response_content = await _test_rerank_model(
                        protocol=db_provider.protocol,
                        base_url=db_provider.base_url,
                        model=model_to_test,
                        api_key=api_key,
                        timeout=30
                    )
                else:
                    # Test chat/completion model with streaming
                    first_chunk_received = False
                    
                    async def stream_callback(chunk):
                        nonlocal first_chunk_received, response_content
                        if chunk and not first_chunk_received:
                            first_chunk_received = True
                            response_content = str(chunk)[:100]
                    
                    if db_provider.protocol == "ollama":
                        await _test_ollama_streaming(
                            base_url=db_provider.base_url,
                            model=model_to_test,
                            prompt=request.prompt,
                            callback=stream_callback,
                            timeout=30
                        )
                    else:
                        # OpenAI compatible
                        await _test_openai_streaming(
                            base_url=db_provider.base_url,
                            model=model_to_test,
                            prompt=request.prompt,
                            api_key=api_key,
                            callback=stream_callback,
                            timeout=30
                        )
                    
                    if not first_chunk_received:
                        raise Exception("No response received from model")
                
            except Exception as e:
                raise
            
            latency = (time.time() - start_time) * 1000  # ms
            
            return TestGenerationResponse(
                content=response_content or "Test successful",
                model=model_to_test,
                provider=db_provider.name,
                tokens_used=1,
                success=True,
            )

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Test generation failed: {error_msg}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Generation failed: {error_msg}",
        )


def _detect_model_type(model_id: str) -> str:
    """
    Detect model type based on model ID.
    Based on cherry-studio's model detection logic.
    
    Returns: "embedding", "rerank", or "chat"
    """
    import re
    
    model_lower = model_id.lower()
    
    # Rerank models (check first, as some rerank models may contain "embed")
    rerank_patterns = [
        r'rerank', r're-rank', r're-ranker', r're-ranking',
        r'retrieval', r'retriever'
    ]
    for pattern in rerank_patterns:
        if re.search(pattern, model_lower):
            return "rerank"
    
    # Embedding models
    embedding_patterns = [
        r'^text-', r'embed', r'bge-', r'e5-', r'llm2vec',
        r'retrieval', r'uae-', r'gte-', r'jina-clip',
        r'jina-embeddings', r'voyage-'
    ]
    for pattern in embedding_patterns:
        if re.search(pattern, model_lower):
            return "embedding"
    
    # Default to chat model
    return "chat"


async def _test_embedding_model(
    protocol: str,
    base_url: str,
    model: str,
    api_key: str,
    timeout: int = 30
) -> str:
    """Test embedding model by getting embedding dimensions."""
    import aiohttp
    
    if protocol == "ollama":
        # Ollama embedding test
        url = f"{base_url.rstrip('/')}/api/embeddings"
        payload = {
            "model": model,
            "prompt": "test"
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Ollama embedding test failed: {response.status} - {text}")
                
                data = await response.json()
                embedding = data.get('embedding', [])
                return f"Embedding test successful (dimension: {len(embedding)})"
    
    else:
        # OpenAI compatible embedding test
        base_url = base_url.rstrip('/')
        urls_to_try = [
            f"{base_url}/v1/embeddings",
            f"{base_url}/embeddings",
        ]
        
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        
        payload = {
            "model": model,
            "input": "test"
        }
        
        last_error = None
        for url in urls_to_try:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            embeddings = data.get('data', [])
                            if embeddings:
                                dim = len(embeddings[0].get('embedding', []))
                                return f"Embedding test successful (dimension: {dim})"
                        else:
                            text = await response.text()
                            last_error = f"HTTP {response.status}: {text[:200]}"
            except Exception as e:
                last_error = str(e)
        
        raise Exception(last_error or "Embedding test failed")


async def _test_rerank_model(
    protocol: str,
    base_url: str,
    model: str,
    api_key: str,
    timeout: int = 30
) -> str:
    """Test rerank model."""
    import aiohttp
    
    # Most rerank models use OpenAI-compatible API
    base_url = base_url.rstrip('/')
    urls_to_try = [
        f"{base_url}/v1/rerank",
        f"{base_url}/rerank",
    ]
    
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": model,
        "query": "test query",
        "documents": ["test document 1", "test document 2"]
    }
    
    last_error = None
    for url in urls_to_try:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        results = data.get('results', [])
                        return f"Rerank test successful ({len(results)} results)"
                    else:
                        text = await response.text()
                        last_error = f"HTTP {response.status}: {text[:200]}"
        except Exception as e:
            last_error = str(e)
    
    raise Exception(last_error or "Rerank test failed")


async def _test_ollama_streaming(
    base_url: str,
    model: str,
    prompt: str,
    callback: callable,
    timeout: int = 30
):
    """Test Ollama with streaming."""
    import aiohttp
    import json
    
    url = f"{base_url.rstrip('/')}/api/generate"
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"Ollama returned {response.status}: {text}")
            
            # Read stream line by line
            async for line in response.content:
                if line:
                    try:
                        line_text = line.decode('utf-8').strip()
                        if line_text:
                            data = json.loads(line_text)
                            if "response" in data and data["response"]:
                                # Got first chunk - success!
                                await callback(data["response"])
                                return
                    except json.JSONDecodeError:
                        # Skip invalid JSON lines
                        continue
                    except Exception as e:
                        logger.warning(f"Error parsing Ollama stream: {e}")
                        continue


async def _test_openai_streaming(
    base_url: str,
    model: str,
    prompt: str,
    api_key: str,
    callback: callable,
    timeout: int = 30
):
    """Test OpenAI compatible with streaming."""
    import aiohttp
    
    base_url = base_url.rstrip('/')
    
    urls_to_try = [
        f"{base_url}/v1/chat/completions",
        f"{base_url}/chat/completions",
    ]
    
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "max_tokens": 10,
    }
    
    last_error = None
    
    for url in urls_to_try:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        last_error = f"HTTP {response.status}: {text[:200]}"
                        continue
                    
                    # Read first chunk only
                    async for line in response.content:
                        if line:
                            line_text = line.decode('utf-8').strip()
                            if line_text.startswith('data: '):
                                data_str = line_text[6:]
                                if data_str == '[DONE]':
                                    continue
                                try:
                                    import json
                                    data = json.loads(data_str)
                                    if 'choices' in data and len(data['choices']) > 0:
                                        delta = data['choices'][0].get('delta', {})
                                        content = delta.get('content', '')
                                        if content:
                                            await callback(content)
                                            return  # Success - abort after first chunk
                                except:
                                    pass
                    
                    return  # Success even if no content
                    
        except aiohttp.ClientError as e:
            last_error = f"Connection error: {str(e)}"
        except Exception as e:
            last_error = f"Error: {str(e)}"
    
    raise Exception(last_error or "Failed to connect to model")


@router.get("/providers/available", response_model=Dict[str, List[str]])
async def get_available_providers_and_models(
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get available providers and their models for agent configuration.
    
    Returns enabled providers with their configured models from database only.
    Does NOT perform actual health checks to avoid blocking.
    Uses last known test status from database.
    
    This endpoint is used by the agent configuration UI.
    Config.yaml providers are synced to database on startup.
    """
    if get_llm_provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LLM providers not configured",
        )

    try:
        result = {}
        
        # Get providers from database only
        try:
            with get_db_session() as db:
                db_manager = ProviderDBManager(db)
                db_providers = db_manager.list_providers()
                
                logger.info(f"[LLM-AVAILABLE-PROVIDERS] Found {len(db_providers)} providers in database")
                
                for p in db_providers:
                    logger.info(f"[LLM-AVAILABLE-PROVIDERS] Provider: {p.name}, enabled={p.enabled}, models={len(p.models) if p.models else 0}, test_status={p.last_test_status}")
                    # Include if enabled and has models
                    # Optionally filter by last_test_status == 'success'
                    if p.enabled and p.models:
                        # Only include if last test was successful or untested
                        if p.last_test_status in ['success', None, 'untested']:
                            result[p.name] = p.models
        except Exception as e:
            logger.warning(f"Failed to get database providers: {e}")
        
        logger.info(f"[LLM-AVAILABLE-PROVIDERS] Returning {len(result)} providers: {list(result.keys())}")
        return result

    except Exception as e:
        logger.error(f"Failed to get available providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available providers: {str(e)}",
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

@router.get("/providers/{name}", response_model=ProviderResponse)
@require_role([Role.ADMIN])
async def get_provider_detail(
    name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get detailed configuration for a specific provider.
    
    Returns full configuration including base_url, timeout, models, etc.
    Useful for editing provider configuration.
    
    Requires admin permission.
    """
    try:
        # First, try to get from database
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            db_provider = db_manager.get_provider(name)
            
            if db_provider:
                return ProviderResponse(
                    name=db_provider.name,
                    protocol=db_provider.protocol,
                    base_url=db_provider.base_url,
                    timeout=db_provider.timeout,
                    max_retries=db_provider.max_retries,
                    selected_models=db_provider.models,
                    enabled=db_provider.enabled,
                    has_api_key=bool(db_provider.api_key_encrypted),
                    is_config_based=False,
                )
        
        # If not in database, try to get from config.yaml
        from shared.config import get_config
        config = get_config()
        config_providers = config.get("llm.providers", {})
        
        if name in config_providers:
            provider_config = config_providers[name]
            
            # Extract models from config
            models_dict = provider_config.get("models", {})
            models = list(models_dict.values()) if isinstance(models_dict, dict) else []
            
            # Get timeout and max_retries from provider config or global config
            timeout = provider_config.get("timeout", config.get("llm.timeout_seconds", 30))
            max_retries = provider_config.get("max_retries", config.get("llm.max_retries", 3))
            
            # Determine protocol
            protocol = "ollama" if name == "ollama" else "openai_compatible"
            
            return ProviderResponse(
                name=name,
                protocol=protocol,
                base_url=provider_config.get("base_url", ""),
                timeout=timeout,
                max_retries=max_retries,
                selected_models=models,
                enabled=provider_config.get("enabled", False),
                has_api_key=bool(provider_config.get("api_key")),
                is_config_based=True,
            )
        
        # Provider not found
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{name}' not found",
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get provider detail: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provider detail: {str(e)}",
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
            
            # Clear cache to force reload on next use
            if get_llm_provider is not None:
                try:
                    llm_router = get_llm_provider()
                    llm_router.clear_cache()
                    logger.info(f"Cleared provider cache after creating {provider.name}")
                except Exception as cache_error:
                    logger.error(f"Failed to clear cache: {cache_error}")
            
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
            
            # Clear cache to force reload on next use
            if get_llm_provider is not None:
                try:
                    llm_router = get_llm_provider()
                    llm_router.clear_cache()
                    logger.info(f"Cleared provider cache after updating {provider.name}")
                except Exception as cache_error:
                    logger.error(f"Failed to clear cache: {cache_error}")
            
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
    
    Automatically reloads providers after deletion (hot reload).
    
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
            
            # Hot reload: Remove the provider from runtime immediately
            if get_llm_provider is not None:
                try:
                    llm_router = get_llm_provider()
                    llm_router.reload_database_providers()
                    logger.info(f"Hot reloaded providers after deleting {name}")
                except Exception as reload_error:
                    logger.error(f"Failed to hot reload after delete: {reload_error}")
                    # Don't fail the request if reload fails
        
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
    
    If testing an existing provider and no API key is provided in the request,
    the stored API key from the database will be used.
    
    Updates the provider's last_test_status in database if provider exists.
    
    Returns detailed error information if connection fails.
    
    Requires admin permission.
    """
    try:
        logger.info(f"Testing connection to {request.protocol} provider at {request.base_url}")
        
        # Determine which API key to use and find existing provider
        api_key_to_use = request.api_key
        existing_provider = None
        
        # If no API key provided, try to fetch from database
        if not api_key_to_use:
            try:
                with get_db_session() as db:
                    db_manager = ProviderDBManager(db)
                    # Try to find provider by base_url
                    providers = db_manager.list_providers()
                    for provider in providers:
                        if provider.base_url == request.base_url:
                            existing_provider = provider
                            # Decrypt and use its API key
                            api_key_to_use = db_manager._decrypt_api_key(provider.api_key_encrypted)
                            if api_key_to_use:
                                logger.info(f"Using stored API key from provider: {provider.name}")
                            break
            except Exception as e:
                logger.warning(f"Failed to fetch stored API key: {e}")
        
        logger.info(f"API key available: {'YES' if api_key_to_use else 'NO'} (length: {len(api_key_to_use) if api_key_to_use else 0})")
        
        # Get protocol client
        client = get_protocol_client(request.protocol)
        
        # Fetch models
        try:
            models = await client.fetch_models(
                base_url=request.base_url,
                api_key=api_key_to_use,
                timeout=request.timeout,
            )
            
            logger.info(f"✓ Connection test successful: {len(models)} models found")
            
            # Update test status in database if provider exists
            if existing_provider:
                try:
                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        db_manager.update_test_status(
                            provider_name=existing_provider.name,
                            status='success',
                            error_message=None
                        )
                        logger.info(f"Updated test status for {existing_provider.name}: success")
                except Exception as e:
                    logger.error(f"Failed to update test status: {e}")
            
            return TestConnectionResponse(
                success=True,
                message=f"Successfully connected. Found {len(models)} models.",
                available_models=models,
            )
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"✗ Connection test failed: {error_message}")
            
            # Update test status in database if provider exists
            if existing_provider:
                try:
                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        db_manager.update_test_status(
                            provider_name=existing_provider.name,
                            status='failed',
                            error_message=error_message
                        )
                        logger.info(f"Updated test status for {existing_provider.name}: failed")
                except Exception as update_error:
                    logger.error(f"Failed to update test status: {update_error}")
            
            # Return detailed error information
            return TestConnectionResponse(
                success=False,
                message="Connection test failed",
                error=error_message,
                available_models=[],
            )
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"✗ Test connection error: {error_message}")
        
        # Return error response
        return TestConnectionResponse(
            success=False,
            message="Connection test error",
            error=error_message,
            available_models=[],
        )


# Model Health Check Endpoints (Based on cherry-studio)

class ModelTestRequest(BaseModel):
    """Request to test specific models."""
    
    provider_name: str
    protocol: str = Field(..., description="Provider protocol (ollama, openai_compatible)")
    base_url: str
    models: List[str] = Field(..., description="List of model IDs to test")
    api_keys: List[str] = Field(default=[], description="List of API keys to test (optional)")
    concurrent: bool = Field(default=True, description="Test models concurrently")
    timeout: int = Field(default=15, ge=5, le=60, description="Timeout per model test in seconds")


class ModelTestResponse(BaseModel):
    """Response from model testing."""
    
    provider_name: str
    status: str  # success, failed, not_checked
    models: List[Dict[str, Any]]
    summary: str
    error: Optional[str] = None


@router.post("/providers/test-models", response_model=ModelTestResponse)
@require_role([Role.ADMIN])
async def test_models(
    request: ModelTestRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Test specific models for a provider.
    
    Performs actual generation tests on each model to verify functionality.
    Based on cherry-studio's comprehensive health check system.
    
    Features:
    - Tests multiple API keys per model
    - Measures response latency
    - Provides detailed error messages
    - Supports concurrent or sequential testing
    
    Requires admin permission.
    """
    from llm_providers.health_check import check_models_health, summarize_health_results
    
    try:
        logger.info(f"Testing {len(request.models)} models for {request.provider_name}")
        
        # Get API keys (use stored key if not provided)
        api_keys = request.api_keys
        if not api_keys:
            try:
                with get_db_session() as db:
                    db_manager = ProviderDBManager(db)
                    providers = db_manager.list_providers()
                    for provider in providers:
                        if provider.name == request.provider_name:
                            decrypted_key = db_manager._decrypt_api_key(provider.api_key_encrypted)
                            if decrypted_key:
                                api_keys = [decrypted_key]
                            break
            except Exception as e:
                logger.warning(f"Failed to fetch stored API key: {e}")
        
        # Perform health check
        results = await check_models_health(
            provider_name=request.provider_name,
            protocol=request.protocol,
            base_url=request.base_url,
            models=request.models,
            api_keys=api_keys or [],
            concurrent=request.concurrent,
            timeout=request.timeout,
        )
        
        # Convert results to dict format
        models_data = []
        for result in results:
            models_data.append({
                "model_id": result.model_id,
                "status": result.status.value,
                "latency": result.latency,
                "error": result.error,
                "key_results": [
                    {
                        "key_masked": kr.key_masked,
                        "status": kr.status.value,
                        "latency": kr.latency,
                        "error": kr.error,
                    }
                    for kr in result.key_results
                ],
            })
        
        # Determine overall status
        success_count = sum(1 for r in results if r.status.value == "success")
        failed_count = sum(1 for r in results if r.status.value == "failed")
        
        if success_count == len(results):
            overall_status = "success"
        elif success_count > 0:
            overall_status = "partial"
        else:
            overall_status = "failed"
        
        # Generate summary
        summary = summarize_health_results(results, request.provider_name)
        
        logger.info(f"✓ Model testing complete: {summary}")
        
        return ModelTestResponse(
            provider_name=request.provider_name,
            status=overall_status,
            models=models_data,
            summary=summary,
        )
        
    except Exception as e:
        error_message = str(e)
        logger.error(f"✗ Model testing failed: {error_message}")
        
        return ModelTestResponse(
            provider_name=request.provider_name,
            status="failed",
            models=[],
            summary=f"Testing failed: {error_message}",
            error=error_message,
        )



# Model Metadata Endpoints

class ModelMetadataResponse(BaseModel):
    """Model metadata response."""
    
    model_id: str
    model_type: Optional[str] = None  # chat, vision, reasoning, embedding, rerank, code, image_generation
    display_name: Optional[str] = None
    description: Optional[str] = None
    capabilities: List[str] = []
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    embedding_dimension: Optional[int] = None  # Vector dimension for embedding models
    default_temperature: float = 0.7
    temperature_range: tuple[float, float] = (0.0, 2.0)
    supports_streaming: bool = True
    supports_system_prompt: bool = True
    supports_function_calling: bool = False
    supports_vision: bool = False
    supports_reasoning: bool = False
    input_price_per_1m: Optional[float] = None  # Per 1 million tokens
    output_price_per_1m: Optional[float] = None  # Per 1 million tokens
    version: Optional[str] = None
    release_date: Optional[str] = None
    deprecated: bool = False


class ProviderModelsResponse(BaseModel):
    """Provider models with metadata."""
    
    provider_name: str
    protocol: str
    models: Dict[str, ModelMetadataResponse]


@router.get("/providers/{provider_name}/models/metadata", response_model=ProviderModelsResponse)
async def get_provider_models_metadata(
    provider_name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get detailed metadata for all models of a provider.
    
    Returns model capabilities, context windows, pricing, and other metadata.
    Supports both database providers and config.yaml providers.
    Uses enhanced detection based on cherry-studio patterns.
    """
    try:
        from llm_providers.model_metadata import get_enhanced_detector
        from shared.config import get_config
        
        detector = get_enhanced_detector()
        
        # Try database first
        provider = None
        protocol = None
        models_list = []
        stored_metadata = {}
        
        # Check database
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            provider = db_manager.get_provider(provider_name)
            
            if provider:
                protocol = provider.protocol
                models_list = provider.models
                stored_metadata = provider.model_metadata or {}
        
        # If not in database, try config.yaml
        if not provider:
            config = get_config()
            providers_config = config.get("llm.providers", {})
            
            if provider_name not in providers_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Provider '{provider_name}' not found"
                )
            
            provider_config = providers_config[provider_name]
            
            # Determine protocol from config
            if provider_name == "ollama":
                protocol = "ollama"
            elif provider_name == "vllm":
                protocol = "vllm"
            elif provider_name in ["openai", "anthropic"]:
                protocol = "openai_compatible"
            else:
                protocol = "openai_compatible"
            
            # Get models from config
            models_dict = provider_config.get("models", {})
            if isinstance(models_dict, dict):
                models_list = list(set(models_dict.values()))
            elif isinstance(models_dict, list):
                models_list = models_dict
            else:
                models_list = []
        
        if not models_list:
            return ProviderModelsResponse(
                provider_name=provider_name,
                protocol=protocol or "unknown",
                models={}
            )
        
        # Get or generate metadata for each model
        models_metadata = {}
        
        for model_name in models_list:
            if model_name in stored_metadata:
                # Use stored metadata (user customizations)
                metadata_dict = stored_metadata[model_name]
                models_metadata[model_name] = ModelMetadataResponse(**metadata_dict)
            else:
                # Use enhanced detector for accurate detection
                detected_metadata = detector.detect_metadata(
                    model_id=model_name,
                    provider=provider_name,
                    model_name=model_name  # Pass model_name for providers like doubao
                )
                
                # Convert to response format
                # Note: Convert enum capabilities to string values
                capabilities_str = [cap.value if hasattr(cap, 'value') else str(cap) for cap in detected_metadata.capabilities]
                
                # Convert model_type enum to string
                model_type_str = detected_metadata.model_type.value if hasattr(detected_metadata.model_type, 'value') else str(detected_metadata.model_type)
                
                models_metadata[model_name] = ModelMetadataResponse(
                    model_id=detected_metadata.model_id,
                    model_type=model_type_str,
                    display_name=detected_metadata.display_name,
                    description=detected_metadata.description,
                    capabilities=capabilities_str,
                    context_window=detected_metadata.context_window,
                    max_output_tokens=detected_metadata.max_output_tokens,
                    embedding_dimension=detected_metadata.embedding_dimension,
                    default_temperature=detected_metadata.default_temperature,
                    temperature_range=detected_metadata.temperature_range,
                    supports_streaming=detected_metadata.supports_streaming,
                    supports_system_prompt=detected_metadata.supports_system_prompt,
                    supports_function_calling=detected_metadata.supports_function_calling,
                    supports_vision=detected_metadata.supports_vision,
                    supports_reasoning=detected_metadata.supports_reasoning,
                    input_price_per_1m=detected_metadata.input_price_per_1m,
                    output_price_per_1m=detected_metadata.output_price_per_1m,
                    version=detected_metadata.version,
                    release_date=detected_metadata.release_date,
                    deprecated=detected_metadata.deprecated,
                )
        
        return ProviderModelsResponse(
            provider_name=provider_name,
            protocol=protocol or "unknown",
            models=models_metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get models metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get models metadata: {str(e)}"
        )


@router.get("/providers/{provider_name}/models/{model_name:path}/metadata", response_model=ModelMetadataResponse)
async def get_model_metadata(
    provider_name: str,
    model_name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Get detailed metadata for a specific model.
    
    Returns model capabilities, context window, pricing, and other metadata.
    Used for pre-filling agent configuration forms.
    """
    try:
        from llm_providers.model_metadata import EnhancedModelCapabilityDetector
        from shared.config import get_config
        
        # Try database first
        provider = None
        protocol = None
        stored_metadata = {}
        
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            provider = db_manager.get_provider(provider_name)
            
            if provider:
                protocol = provider.protocol
                stored_metadata = provider.model_metadata or {}
                
                # Check if model exists in provider
                if model_name not in provider.models:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Model '{model_name}' not found in provider '{provider_name}'"
                    )
        
        # If not in database, try config.yaml
        if not provider:
            config = get_config()
            providers_config = config.get("llm.providers", {})
            
            if provider_name not in providers_config:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Provider '{provider_name}' not found"
                )
            
            provider_config = providers_config[provider_name]
            
            # Determine protocol
            if provider_name == "ollama":
                protocol = "ollama"
            elif provider_name == "vllm":
                protocol = "vllm"
            elif provider_name in ["openai", "anthropic"]:
                protocol = "openai_compatible"
            else:
                protocol = "openai_compatible"
            
            # Check if model exists in config
            models_dict = provider_config.get("models", {})
            if isinstance(models_dict, dict):
                models_list = list(set(models_dict.values()))
            elif isinstance(models_dict, list):
                models_list = models_dict
            else:
                models_list = []
            
            if model_name not in models_list:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Model '{model_name}' not found in provider '{provider_name}'"
                )
        
        # Get or generate metadata for the model
        if model_name in stored_metadata:
            # Use stored metadata
            metadata_dict = stored_metadata[model_name]
            return ModelMetadataResponse(**metadata_dict)
        else:
            # Generate default metadata using enhanced detector
            detector = EnhancedModelCapabilityDetector()
            default_metadata = detector.detect_metadata(
                model_name,
                provider_name
            )
            
            # Auto-save generated metadata to database for future use
            if provider:
                try:
                    with get_db_session() as db:
                        db_manager = ProviderDBManager(db)
                        db_provider = db_manager.get_provider(provider_name)
                        if db_provider:
                            stored_metadata = db_provider.model_metadata or {}
                            stored_metadata[model_name] = default_metadata.dict()
                            db_provider.model_metadata = stored_metadata
                            db.commit()
                            logger.info(f"Auto-saved generated metadata for model {model_name} in provider {provider_name}")
                except Exception as save_error:
                    logger.warning(f"Failed to auto-save metadata: {save_error}")
                    # Continue even if save fails
            
            return ModelMetadataResponse(**default_metadata.dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get model metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get model metadata: {str(e)}"
        )


@router.put("/providers/{provider_name}/models/{model_name:path}/metadata")
@require_role([Role.ADMIN])
async def update_model_metadata(
    provider_name: str,
    model_name: str,
    metadata: ModelMetadataResponse,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Update metadata for a specific model.
    
    Admin only. Allows customizing model capabilities, context windows, pricing, etc.
    """
    try:
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            provider = db_manager.get_provider(provider_name)
            
            if not provider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Provider '{provider_name}' not found"
                )
            
            if model_name not in provider.models:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Model '{model_name}' not found in provider '{provider_name}'"
                )
            
            # Update metadata
            stored_metadata = provider.model_metadata or {}
            stored_metadata[model_name] = metadata.dict()
            
            # Save to database
            provider.model_metadata = stored_metadata
            db.commit()
            
            logger.info(f"Updated metadata for model {model_name} in provider {provider_name}")
            
            return {"success": True, "message": "Model metadata updated"}
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update model metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update model metadata: {str(e)}"
        )


@router.post("/providers/{provider_name}/models/refresh-metadata")
@require_role([Role.ADMIN])
async def refresh_models_metadata(
    provider_name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """
    Refresh model metadata from provider API.
    
    Fetches latest model information from the provider and updates stored metadata.
    This is useful after provider updates or to get accurate context windows and capabilities.
    
    Admin only.
    """
    try:
        from llm_providers.model_metadata import EnhancedModelCapabilityDetector
        from llm_providers.protocol_clients import get_protocol_client
        
        # Get provider from database
        with get_db_session() as db:
            db_manager = ProviderDBManager(db)
            provider = db_manager.get_provider(provider_name)
            
            if not provider:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Provider '{provider_name}' not found"
                )
            
            # Get protocol client
            from llm_providers.models import ProviderProtocol
            protocol = ProviderProtocol(provider.protocol)
            client = get_protocol_client(protocol)
            
            # Decrypt API key
            api_key = db_manager._decrypt_api_key(provider.api_key_encrypted)
            
            # Fetch models
            try:
                models = await client.fetch_models(
                    base_url=provider.base_url,
                    api_key=api_key,
                    timeout=provider.timeout,
                )
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to fetch models from provider: {str(e)}"
                )
            
            # OPTIMIZATION: Only refresh metadata for user-selected models
            # This prevents timeout when provider has 100+ models
            selected_models = provider.models or []
            models_to_refresh = [m for m in selected_models if m in models]
            
            if not models_to_refresh:
                # If no selected models, just return success
                return {
                    "success": True,
                    "message": "No selected models to refresh",
                    "metadata_count": 0,
                    "selected_models_count": len(selected_models)
                }
            
            # Fetch metadata for each SELECTED model only
            updated_metadata = {}
            for model_id in models_to_refresh:
                # Try to fetch from provider API
                provider_metadata = await client.fetch_model_metadata(
                    base_url=provider.base_url,
                    model_id=model_id,
                    api_key=api_key,
                    timeout=provider.timeout,
                )
                
                # Generate base metadata using enhanced detector
                detector = EnhancedModelCapabilityDetector()
                detected_metadata = detector.detect_metadata(
                    model_id,
                    provider_name
                )
                
                # Merge provider metadata with detected metadata
                if provider_metadata:
                    # Update detected metadata with provider-specific info
                    if "context_window" in provider_metadata:
                        detected_metadata.context_window = provider_metadata["context_window"]
                    if "max_output_tokens" in provider_metadata:
                        detected_metadata.max_output_tokens = provider_metadata["max_output_tokens"]
                    if "embedding_dimension" in provider_metadata:
                        detected_metadata.embedding_dimension = provider_metadata["embedding_dimension"]
                    if "size" in provider_metadata:
                        detected_metadata.size = provider_metadata["size"]
                    if "quantization" in provider_metadata:
                        detected_metadata.quantization = provider_metadata["quantization"]
                
                updated_metadata[model_id] = detected_metadata.dict()
            
            # IMPORTANT: Only update metadata, DO NOT change the models list
            # The models list is user-selected and should not be overwritten
            provider.model_metadata = updated_metadata
            db.commit()
            
            logger.info(f"Refreshed metadata for {len(updated_metadata)} models in provider {provider_name}")
            
            return {
                "success": True,
                "message": f"Refreshed metadata for {len(updated_metadata)} models (user-selected models unchanged)",
                "metadata_count": len(updated_metadata),
                "selected_models_count": len(provider.models)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to refresh models metadata: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to refresh models metadata: {str(e)}"
        )
