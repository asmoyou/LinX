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
        
        OpenAI API endpoint: GET /v1/models
        Response format: {"data": [{"id": "model_id"}, ...]}
        """
        url = f"{base_url.rstrip('/')}/v1/models"
        
        headers = {}
        if api_key:
            headers['Authorization'] = f"Bearer {api_key}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise Exception(f"OpenAI API returned {response.status}: {text}")
                    
                    data = await response.json()
                    models = data.get('data', [])
                    
                    # Extract model IDs
                    model_names = [model.get('id', '') for model in models if model.get('id')]
                    
                    logger.info(f"Fetched {len(model_names)} models from OpenAI Compatible API")
                    return model_names
                    
        except aiohttp.ClientError as e:
            logger.error(f"Failed to fetch OpenAI Compatible models: {e}")
            raise Exception(f"Failed to connect to OpenAI Compatible API: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching OpenAI Compatible models: {e}")
            raise


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
