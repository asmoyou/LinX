"""
LLM Provider Health Check Service

Comprehensive health checking for LLM providers and models.
Based on cherry-studio's robust testing architecture.

Supports model-type-aware testing: chat, embedding, and rerank models
are each tested with the appropriate API endpoint and payload.

References:
- cherry-studio: src/renderer/src/services/HealthCheckService.ts
- cherry-studio: src/renderer/src/services/ApiService.ts
"""

import asyncio
import json
import logging
import re
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

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
    model_metadata: Optional[Dict[str, Any]] = None,
) -> ApiKeyStatus:
    """
    Check a single model with a single API key.

    Detects model type (chat / embedding / rerank) and uses the appropriate
    test endpoint so that non-chat models are not incorrectly tested against
    /chat/completions.

    Args:
        provider_name: Provider name
        protocol: Provider protocol (ollama, openai_compatible)
        base_url: Provider base URL
        model_id: Model to test
        api_key: API key (optional)
        timeout: Request timeout in seconds
        model_metadata: Optional per-model metadata dict (may contain "model_type")

    Returns:
        ApiKeyStatus with test results
    """
    key_masked = _mask_api_key(api_key) if api_key else "no-key"
    start_time = time.time()

    try:
        # Resolve model type: DB metadata first, pattern detection fallback
        model_type = _resolve_model_type(model_id, model_metadata)

        logger.info(f"Testing {model_type} model: {model_id} on {provider_name}")

        # Dispatch to the correct test method
        if model_type == "embedding":
            await _test_embedding_model(protocol, base_url, model_id, api_key, timeout)
        elif model_type == "rerank":
            await _test_rerank_model(protocol, base_url, model_id, api_key, timeout)
        else:
            # Chat / completion model
            if protocol == "ollama":
                await _test_ollama_model(base_url, model_id, timeout)
            else:
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


def _detect_model_type(model_id: str) -> str:
    """
    Detect model type based on model ID patterns.

    Returns: "embedding", "rerank", or "chat"
    """
    model_lower = model_id.lower()

    # Rerank models (check first — some rerank models contain "embed")
    rerank_patterns = [
        r"rerank",
        r"re-rank",
        r"re-ranker",
        r"re-ranking",
    ]
    for pattern in rerank_patterns:
        if re.search(pattern, model_lower):
            return "rerank"

    # Embedding models
    embedding_patterns = [
        r"^text-embedding",
        r"embed",
        r"bge-(?!rerank)",
        r"e5-",
        r"llm2vec",
        r"uae-",
        r"gte-",
        r"jina-clip",
        r"jina-embeddings",
        r"voyage-",
        r"mxbai-embed",
        r"doubao-embedding",
    ]
    for pattern in embedding_patterns:
        if re.search(pattern, model_lower):
            return "embedding"

    return "chat"


def _resolve_model_type(
    model_id: str,
    model_metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Determine model type using metadata first, falling back to pattern detection.
    """
    if model_metadata:
        meta_type = model_metadata.get("model_type", "")
        if meta_type in ("embedding", "rerank"):
            return meta_type
    return _detect_model_type(model_id)


async def _test_embedding_model(
    protocol: str,
    base_url: str,
    model_id: str,
    api_key: Optional[str],
    timeout: int,
) -> None:
    """Test an embedding model by requesting a single embedding vector."""
    import aiohttp

    if protocol == "ollama":
        url = f"{base_url.rstrip('/')}/api/embeddings"
        payload = {"model": model_id, "prompt": "test"}

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
                embedding = data.get("embedding", [])
                if not embedding:
                    raise Exception("No embedding vector returned by Ollama")
                return  # success
    else:
        # OpenAI-compatible embedding endpoint
        base = base_url.rstrip("/")
        urls_to_try = [
            f"{base}/v1/embeddings",
            f"{base}/embeddings",
        ]

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        payload = {"model": model_id, "input": "test"}

        last_error: Optional[str] = None
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
                            # Accept any response with embedding-like data
                            if _has_embedding_data(data):
                                return  # success
                            last_error = (
                                "HTTP 200 but no embedding vector found in payload"
                            )
                        else:
                            text = await response.text()
                            last_error = f"HTTP {response.status}: {text[:200]}"
            except Exception as e:
                last_error = str(e)

        raise Exception(last_error or "Embedding test failed")


async def _test_rerank_model(
    protocol: str,
    base_url: str,
    model_id: str,
    api_key: Optional[str],
    timeout: int,
) -> None:
    """Test a rerank model by sending a minimal rerank request."""
    import aiohttp

    base = base_url.rstrip("/")
    urls_to_try = [
        f"{base}/v1/rerank",
        f"{base}/rerank",
        f"{base}/api/rerank",
    ]

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_id,
        "query": "test query",
        "documents": ["document one", "document two"],
    }

    last_error: Optional[str] = None
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
                        if _has_rerank_data(data):
                            return  # success
                        last_error = "HTTP 200 but no rerank results found in payload"
                    else:
                        text = await response.text()
                        last_error = f"HTTP {response.status}: {text[:200]}"
        except Exception as e:
            last_error = str(e)

    raise Exception(last_error or "Rerank test failed")


def _has_embedding_data(data: Any) -> bool:
    """Check whether a response payload contains embedding vectors."""
    if not isinstance(data, dict):
        return False
    # Ollama style
    if isinstance(data.get("embedding"), list) and data["embedding"]:
        return True
    # OpenAI style
    items = data.get("data")
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and isinstance(item.get("embedding"), list):
                return True
    # Alternative keys
    for key in ("embeddings", "results"):
        items = data.get(key)
        if isinstance(items, list) and items:
            return True
    return False


def _has_rerank_data(data: Any) -> bool:
    """Check whether a response payload contains rerank results."""
    if not isinstance(data, dict):
        return False
    for key in ("results", "data"):
        value = data.get(key)
        if isinstance(value, list) and value:
            return True
    return False


async def check_model_with_multiple_keys(
    provider_name: str,
    protocol: str,
    base_url: str,
    model_id: str,
    api_keys: List[str],
    timeout: int = 15,
    model_metadata: Optional[Dict[str, Any]] = None,
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
        model_metadata: Optional per-model metadata dict

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
            model_metadata=model_metadata,
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
    model_metadata_map: Optional[Dict[str, Dict[str, Any]]] = None,
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
        model_metadata_map: Optional mapping of model_id → metadata dict

    Returns:
        List of ModelHealthResult
    """
    results: List[ModelHealthResult] = []
    metadata_map = model_metadata_map or {}

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
                model_metadata=metadata_map.get(model_id),
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
    model_metadata_map: Optional[Dict[str, Dict[str, Any]]] = None,
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
        model_metadata_map: Optional mapping of model_id → metadata dict

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
            model_metadata_map=model_metadata_map,
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
