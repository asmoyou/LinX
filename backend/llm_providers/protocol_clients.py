"""
LLM Provider Protocol Clients

Clients for fetching models and metadata from different provider protocols.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 18.8: Settings Page
- Task 6.21.7: Implement Ollama protocol client
- Task 6.21.8: Implement OpenAI Compatible protocol client
"""

import logging
from typing import Dict, List, Optional

import aiohttp

from llm_providers.model_metadata import ModelMetadata, ModelCapabilityDetector
from llm_providers.models import ProviderProtocol

logger = logging.getLogger(__name__)


class ProtocolClient:
    """Base class for protocol clients."""
    
    async def fetch_models(
        self,
        base_url: str,
        api_key: str = None,
        timeout: int = 30,
    ) -> List[str]:
        """
        Fetch available models from provider.
        
        Args:
            base_url: Provider base URL
            api_key: API key (if required)
            timeout: Request timeout in seconds
            
        Returns:
            List of model names
            
        Raises:
            Exception: If request fails
        """
        raise NotImplementedError
    
    async def fetch_model_metadata(
        self,
        base_url: str,
        model_id: str,
        api_key: str = None,
        timeout: int = 30,
    ) -> Optional[Dict]:
        """
        Fetch detailed metadata for a specific model.
        
        Args:
            base_url: Provider base URL
            model_id: Model identifier
            api_key: API key (if required)
            timeout: Request timeout in seconds
            
        Returns:
            Dictionary with model metadata or None if not available
        """
        return None  # Default implementation returns None


class OllamaClient(ProtocolClient):
    """Client for Ollama protocol."""
    
    async def fetch_models(
        self,
        base_url: str,
        api_key: str = None,
        timeout: int = 30,
    ) -> List[str]:
        """
        Fetch models from Ollama API.
        
        Ollama API endpoint: GET /api/tags
        Response format: {"models": [{"name": "model_name"}, ...]}
        """
        url = f"{base_url.rstrip('/')}/api/tags"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"Ollama API returned {response.status}: {text}")
                    
                    data = await response.json()
                    models = data.get('models', [])
                    
                    # Extract model names
                    model_names = [model.get('name', '') for model in models if model.get('name')]
                    
                    logger.info(f"Fetched {len(model_names)} models from Ollama")
                    return model_names
                    
        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch Ollama models: {e}")
            raise Exception(f"Failed to connect to Ollama: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching Ollama models: {e}")
            raise
    
    async def fetch_model_metadata(
        self,
        base_url: str,
        model_id: str,
        api_key: str = None,
        timeout: int = 30,
    ) -> Optional[Dict]:
        """
        Fetch detailed metadata for an Ollama model.
        
        Ollama API endpoint: POST /api/show
        Request: {"name": "model_name"}
        Response: {"modelfile": "...", "parameters": "...", "template": "...", ...}
        """
        url = f"{base_url.rstrip('/')}/api/show"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={"name": model_id},
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        logger.warning(f"Failed to fetch metadata for {model_id}: {response.status}")
                        return None
                    
                    data = await response.json()
                    
                    # Extract useful metadata
                    metadata = {
                        "model_id": model_id,
                        "modelfile": data.get("modelfile"),
                        "parameters": data.get("parameters"),
                        "template": data.get("template"),
                        "details": data.get("details", {}),
                    }
                    
                    # Extract context window from details
                    details = data.get("details", {})
                    if "parameter_size" in details:
                        metadata["size"] = details["parameter_size"]
                    if "quantization_level" in details:
                        metadata["quantization"] = details["quantization_level"]
                    
                    return metadata
                    
        except Exception as e:
            logger.warning(f"Error fetching Ollama model metadata for {model_id}: {e}")
            return None


class OpenAICompatibleClient(ProtocolClient):
    """Client for OpenAI Compatible protocol."""
    
    async def fetch_models(
        self,
        base_url: str,
        api_key: str = None,
        timeout: int = 30,
    ) -> List[str]:
        """
        Fetch models from OpenAI Compatible API.
        
        Tries multiple URL patterns for compatibility:
        1. /v1/models (standard OpenAI format)
        2. /models (without /v1 prefix)
        
        OpenAI API endpoint: GET /v1/models
        Response format: {"data": [{"id": "model_id"}, ...]}
        """
        # Normalize base_url
        base_url = base_url.rstrip('/')
        
        headers = {}
        if api_key:
            headers['Authorization'] = f"Bearer {api_key}"
            logger.info(f"API key provided: {api_key[:10]}... (length: {len(api_key)})")
        else:
            logger.warning("No API key provided for OpenAI Compatible API")
        
        # Try different URL patterns
        urls_to_try = [
            f"{base_url}/v1/models",
            f"{base_url}/models",  # Fallback without /v1
        ]
        
        last_error = None
        
        for url in urls_to_try:
            try:
                logger.info(f"Testing connection to {url} with headers: {list(headers.keys())}")
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as response:
                        response_text = await response.text()
                        
                        if response.status == 200:
                            try:
                                data = await response.json()
                                models = data.get('data', [])
                                
                                # Extract model IDs
                                model_names = [model.get('id', '') for model in models if model.get('id')]
                                
                                if model_names:
                                    logger.info(f"✓ Successfully fetched {len(model_names)} models from {url}")
                                    return model_names
                                else:
                                    logger.warning(f"✗ No models found in response from {url}")
                                    last_error = "No models found in API response"
                            except Exception as json_error:
                                logger.error(f"✗ Failed to parse JSON from {url}: {json_error}")
                                last_error = f"Invalid JSON response: {str(json_error)}"
                        else:
                            error_msg = f"HTTP {response.status}: {response_text[:200]}"
                            logger.warning(f"✗ {url} returned {error_msg}")
                            last_error = error_msg
                            
            except aiohttp.ClientError as e:
                error_msg = f"Connection error: {str(e)}"
                logger.warning(f"✗ Failed to connect to {url}: {error_msg}")
                last_error = error_msg
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(f"✗ Error testing {url}: {error_msg}")
                last_error = error_msg
        
        # All attempts failed
        error_message = f"Failed to connect to OpenAI Compatible API at {base_url}. "
        if last_error:
            error_message += f"Last error: {last_error}"
        else:
            error_message += "Please verify the URL and API key."
        
        logger.error(f"✗ All connection attempts failed: {error_message}")
        raise Exception(error_message)
    
    async def fetch_model_metadata(
        self,
        base_url: str,
        model_id: str,
        api_key: str = None,
        timeout: int = 30,
    ) -> Optional[Dict]:
        """
        Fetch detailed metadata for an OpenAI Compatible model.
        
        OpenAI API endpoint: GET /v1/models/{model_id}
        Response format: {"id": "...", "object": "model", "created": ..., ...}
        """
        base_url = base_url.rstrip('/')
        
        headers = {}
        if api_key:
            headers['Authorization'] = f"Bearer {api_key}"
        
        # Try different URL patterns
        urls_to_try = [
            f"{base_url}/v1/models/{model_id}",
            f"{base_url}/models/{model_id}",
        ]
        
        for url in urls_to_try:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=timeout),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            # Extract useful metadata
                            metadata = {
                                "model_id": data.get("id", model_id),
                                "object": data.get("object"),
                                "created": data.get("created"),
                                "owned_by": data.get("owned_by"),
                            }
                            
                            # Some providers include additional fields
                            if "context_length" in data:
                                metadata["context_window"] = data["context_length"]
                            if "max_tokens" in data:
                                metadata["max_output_tokens"] = data["max_tokens"]
                            
                            return metadata
                            
            except Exception as e:
                logger.debug(f"Failed to fetch metadata from {url}: {e}")
                continue
        
        logger.warning(f"Could not fetch metadata for model {model_id}")
        return None


def get_protocol_client(protocol: ProviderProtocol) -> ProtocolClient:
    """
    Get protocol client for the specified protocol.
    
    Args:
        protocol: Provider protocol
        
    Returns:
        Protocol client instance
        
    Raises:
        ValueError: If protocol is not supported
    """
    if protocol == ProviderProtocol.OLLAMA:
        return OllamaClient()
    elif protocol == ProviderProtocol.OPENAI_COMPATIBLE:
        return OpenAICompatibleClient()
    else:
        raise ValueError(f"Unsupported protocol: {protocol}")
