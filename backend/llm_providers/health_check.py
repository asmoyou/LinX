"""
LLM Provider Health Check Service

Comprehensive health checking for LLM providers and models.
Based on cherry-studio's robust testing architecture.

References:
- cherry-studio: src/renderer/src/services/HealthCheckService.ts
- cherry-studio: src/renderer/src/services/ApiService.ts
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel

from llm_providers.base import BaseLLMProvider
from llm_providers.protocol_clients import get_protocol_client

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health check status."""
    SUCCESS = "success"
    FAILED = "failed"
    NOT_CHECKED = "not_checked"


class ApiKeyStatus(BaseModel):
    """API key health check result."""
    key_masked: str  # Masked key (first 8 chars + ...)
    status: HealthStatus
    latency: Optional[float] = None  # Response time in milliseconds
    error: Optional[str] = None


class ModelHealthResult(BaseModel):
    """Model health check result."""
    model_id: str
    status: HealthStatus
    key_results: List[ApiKeyStatus] = []
    latency: Optional[float] = None  # Best latency across all keys
    error: Optional[str] = None
    checking: bool = False


class ProviderHealthResult(BaseModel):
    """Provider health check result."""
    provider_name: str
    status: HealthStatus
    models: List[ModelHealthResult] = []
    error: Optional[str] = None
    checking: bool = False


async def check_model_with_single_key(
    provider_name: str,
    protocol: str,
    base_url: str,
    model_id: str,
    api_key: Optional[str] = None,
    timeout: int = 15,
) -> ApiKeyStatus:
    """
    Check a single model with a single API key.
    
    Performs a minimal test request to verify connectivity.
    
    Args:
        provider_name: Provider name
        protocol: Provider protocol (ollama, openai_compatible)
        base_url: Provider base URL
        model_id: Model to test
        api_key: API key (optional)
        timeout: Request timeout in seconds
        
    Returns:
        ApiKeyStatus with test results
    """
    key_masked = _mask_api_key(api_key) if api_key else "no-key"
    start_time = time.time()
    
    try:
        # Get protocol client
        from llm_providers.models import ProviderProtocol
        protocol_enum = ProviderProtocol(protocol)
        client = get_protocol_client(protocol_enum)
        
        # Perform test based on protocol
        if protocol == "ollama":
            # Ollama: Test with minimal generation request
            await _test_ollama_model(base_url, model_id, timeout)
        else:
            # OpenAI Compatible: Test with minimal chat completion
            await _test_openai_compatible_model(base_url, model_id, api_key, timeout)
        
        latency = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        logger.info(f"✓ Model {model_id} test passed (latency: {latency:.0f}ms)")
        
        return ApiKeyStatus(
            key_masked=key_masked,
            status=HealthStatus.SUCCESS,
            latency=latency,
        )
        
    except Exception as e:
        error_msg = str(e)
        logger.warning(f"✗ Model {model_id} test failed: {error_msg}")
        
        return ApiKeyStatus(
            key_masked=key_masked,
            status=HealthStatus.FAILED,
            error=error_msg,
        )


async def _test_ollama_model(base_url: str, model_id: str, timeout: int):
    """Test Ollama model with minimal generation request."""
    import aiohttp
    
    url = f"{base_url.rstrip('/')}/api/generate"
    
    payload = {
        "model": model_id,
        "prompt": "hi",
        "stream": False,
        "options": {
            "num_predict": 1,  # Generate only 1 token
        }
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
            
            data = await response.json()
            
            # Verify response has expected fields
            if "response" not in data:
                raise Exception("Invalid response format from Ollama")


async def _test_openai_compatible_model(
    base_url: str,
    model_id: str,
    api_key: Optional[str],
    timeout: int
):
    """Test OpenAI Compatible model with minimal chat completion."""
    import aiohttp
    
    base_url = base_url.rstrip('/')
    
    # Try different URL patterns
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
        "model": model_id,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 1,  # Generate only 1 token
        "stream": False,
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
                        
                        # Verify response has expected fields
                        if "choices" not in data:
                            raise Exception("Invalid response format")
                        
                        return  # Success
                    else:
                        text = await response.text()
                        last_error = f"HTTP {response.status}: {text[:200]}"
                        
        except aiohttp.ClientError as e:
            last_error = f"Connection error: {str(e)}"
        except Exception as e:
            last_error = f"Error: {str(e)}"
    
    # All attempts failed
    raise Exception(last_error or "Failed to connect to model")


async def check_model_with_multiple_keys(
    provider_name: str,
    protocol: str,
    base_url: str,
    model_id: str,
    api_keys: List[str],
    timeout: int = 15,
) -> List[ApiKeyStatus]:
    """
    Check a model with multiple API keys.
    
    Tests all keys in parallel and returns results for each.
    
    Args:
        provider_name: Provider name
        protocol: Provider protocol
        base_url: Provider base URL
        model_id: Model to test
        api_keys: List of API keys to test
        timeout: Request timeout in seconds
        
    Returns:
        List of ApiKeyStatus results
    """
    if not api_keys:
        # No API key provided - test without key
        api_keys = [None]
    
    # Test all keys in parallel
    tasks = [
        check_model_with_single_key(
            provider_name=provider_name,
            protocol=protocol,
            base_url=base_url,
            model_id=model_id,
            api_key=key,
            timeout=timeout,
        )
        for key in api_keys
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=False)
    return results


def _aggregate_key_results(key_results: List[ApiKeyStatus]) -> Tuple[HealthStatus, Optional[str], Optional[float]]:
    """
    Aggregate multiple API key results into overall status.
    
    Returns:
        Tuple of (status, error_message, best_latency)
    """
    success_results = [r for r in key_results if r.status == HealthStatus.SUCCESS]
    failed_results = [r for r in key_results if r.status == HealthStatus.FAILED]
    
    if success_results:
        # At least one key succeeded
        best_latency = min(r.latency for r in success_results if r.latency)
        return HealthStatus.SUCCESS, None, best_latency
    
    if failed_results:
        # All keys failed
        # Collect unique error messages
        errors = list(set(r.error for r in failed_results if r.error))
        error_msg = "; ".join(errors[:3])  # Limit to 3 errors
        return HealthStatus.FAILED, error_msg, None
    
    return HealthStatus.NOT_CHECKED, None, None


async def check_models_health(
    provider_name: str,
    protocol: str,
    base_url: str,
    models: List[str],
    api_keys: List[str],
    concurrent: bool = True,
    timeout: int = 15,
    on_model_checked: Optional[callable] = None,
) -> List[ModelHealthResult]:
    """
    Check health of multiple models.
    
    Args:
        provider_name: Provider name
        protocol: Provider protocol
        base_url: Provider base URL
        models: List of model IDs to test
        api_keys: List of API keys to test
        concurrent: Whether to test models concurrently
        timeout: Request timeout in seconds
        on_model_checked: Callback called after each model is checked
        
    Returns:
        List of ModelHealthResult
    """
    results: List[ModelHealthResult] = []
    
    async def check_one_model(model_id: str, index: int) -> ModelHealthResult:
        """Check a single model."""
        try:
            # Test with all API keys
            key_results = await check_model_with_multiple_keys(
                provider_name=provider_name,
                protocol=protocol,
                base_url=base_url,
                model_id=model_id,
                api_keys=api_keys,
                timeout=timeout,
            )
            
            # Aggregate results
            status, error, latency = _aggregate_key_results(key_results)
            
            result = ModelHealthResult(
                model_id=model_id,
                status=status,
                key_results=key_results,
                latency=latency,
                error=error,
            )
            
            # Call callback if provided
            if on_model_checked:
                on_model_checked(result, index)
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking model {model_id}: {e}")
            return ModelHealthResult(
                model_id=model_id,
                status=HealthStatus.FAILED,
                error=str(e),
            )
    
    if concurrent:
        # Test all models in parallel
        tasks = [check_one_model(model_id, i) for i, model_id in enumerate(models)]
        results = await asyncio.gather(*tasks)
    else:
        # Test models sequentially
        for i, model_id in enumerate(models):
            result = await check_one_model(model_id, i)
            results.append(result)
    
    return results


async def check_provider_health(
    provider_name: str,
    protocol: str,
    base_url: str,
    models: List[str],
    api_keys: List[str],
    concurrent: bool = True,
    timeout: int = 15,
) -> ProviderHealthResult:
    """
    Check health of a provider and all its models.
    
    Args:
        provider_name: Provider name
        protocol: Provider protocol
        base_url: Provider base URL
        models: List of model IDs to test
        api_keys: List of API keys to test
        concurrent: Whether to test models concurrently
        timeout: Request timeout in seconds
        
    Returns:
        ProviderHealthResult
    """
    try:
        # Check all models
        model_results = await check_models_health(
            provider_name=provider_name,
            protocol=protocol,
            base_url=base_url,
            models=models,
            api_keys=api_keys,
            concurrent=concurrent,
            timeout=timeout,
        )
        
        # Aggregate provider status
        success_count = sum(1 for r in model_results if r.status == HealthStatus.SUCCESS)
        failed_count = sum(1 for r in model_results if r.status == HealthStatus.FAILED)
        
        if success_count > 0:
            status = HealthStatus.SUCCESS
            error = None
        elif failed_count > 0:
            status = HealthStatus.FAILED
            error = f"{failed_count}/{len(models)} models failed"
        else:
            status = HealthStatus.NOT_CHECKED
            error = "No models checked"
        
        return ProviderHealthResult(
            provider_name=provider_name,
            status=status,
            models=model_results,
            error=error,
        )
        
    except Exception as e:
        logger.error(f"Error checking provider {provider_name}: {e}")
        return ProviderHealthResult(
            provider_name=provider_name,
            status=HealthStatus.FAILED,
            error=str(e),
        )


def _mask_api_key(api_key: Optional[str]) -> str:
    """Mask API key for logging (show first 8 chars)."""
    if not api_key:
        return "no-key"
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:8]}..."


def summarize_health_results(results: List[ModelHealthResult], provider_name: str) -> str:
    """
    Summarize health check results into a human-readable message.
    
    Args:
        results: List of model health results
        provider_name: Provider name
        
    Returns:
        Summary message
    """
    success_count = sum(1 for r in results if r.status == HealthStatus.SUCCESS)
    failed_count = sum(1 for r in results if r.status == HealthStatus.FAILED)
    partial_count = sum(
        1 for r in results
        if r.status == HealthStatus.FAILED and any(k.status == HealthStatus.SUCCESS for k in r.key_results)
    )
    
    parts = []
    if success_count > 0:
        parts.append(f"{success_count} passed")
    if partial_count > 0:
        parts.append(f"{partial_count} partial")
    if failed_count > 0:
        parts.append(f"{failed_count} failed")
    
    if not parts:
        return f"{provider_name}: No results"
    
    summary = ", ".join(parts)
    return f"{provider_name}: {summary}"
