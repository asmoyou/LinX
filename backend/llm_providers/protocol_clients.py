"""
LLM Provider Protocol Clients

Clients for fetching models from different provider protocols.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 18.8: Settings Page
- Task 6.21.7: Implement Ollama protocol client
- Task 6.21.8: Implement OpenAI Compatible protocol client
"""

import logging
from typing import List

import aiohttp

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
