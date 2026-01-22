"""
Unit tests for Protocol Clients

Tests Ollama and OpenAI Compatible protocol clients.
"""

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from llm_providers.protocol_clients import (
    OllamaClient,
    OpenAICompatibleClient,
    get_protocol_client,
)
from llm_providers.models import ProviderProtocol


class TestOllamaClient(AioHTTPTestCase):
    """Test Ollama protocol client."""
    
    async def get_application(self):
        """Create test application."""
        app = web.Application()
        app.router.add_get('/api/tags', self.handle_tags)
        return app
    
    async def handle_tags(self, request):
        """Mock Ollama /api/tags endpoint."""
        return web.json_response({
            'models': [
                {'name': 'llama2'},
                {'name': 'mistral'},
                {'name': 'codellama'},
            ]
        })
    
    @unittest_run_loop
    async def test_fetch_models_success(self):
        """Test successful model fetching."""
        client = OllamaClient()
        base_url = f"http://{self.server.host}:{self.server.port}"
        
        models = await client.fetch_models(base_url)
        
        assert len(models) == 3
        assert 'llama2' in models
        assert 'mistral' in models
        assert 'codellama' in models
    
    @unittest_run_loop
    async def test_fetch_models_timeout(self):
        """Test timeout handling."""
        client = OllamaClient()
        base_url = "http://localhost:99999"  # Invalid port
        
        with pytest.raises(Exception):
            await client.fetch_models(base_url, timeout=1)


class TestOpenAICompatibleClient(AioHTTPTestCase):
    """Test OpenAI Compatible protocol client."""
    
    async def get_application(self):
        """Create test application."""
        app = web.Application()
        app.router.add_get('/v1/models', self.handle_models)
        return app
    
    async def handle_models(self, request):
        """Mock OpenAI /v1/models endpoint."""
        # Check authorization header
        auth = request.headers.get('Authorization')
        if not auth or not auth.startswith('Bearer '):
            return web.json_response(
                {'error': 'Unauthorized'},
                status=401
            )
        
        return web.json_response({
            'data': [
                {'id': 'gpt-4'},
                {'id': 'gpt-3.5-turbo'},
                {'id': 'text-davinci-003'},
            ]
        })
    
    @unittest_run_loop
    async def test_fetch_models_success(self):
        """Test successful model fetching with API key."""
        client = OpenAICompatibleClient()
        base_url = f"http://{self.server.host}:{self.server.port}"
        
        models = await client.fetch_models(base_url, api_key='test-key')
        
        assert len(models) == 3
        assert 'gpt-4' in models
        assert 'gpt-3.5-turbo' in models
        assert 'text-davinci-003' in models
    
    @unittest_run_loop
    async def test_fetch_models_no_api_key(self):
        """Test fetching without API key (should fail)."""
        client = OpenAICompatibleClient()
        base_url = f"http://{self.server.host}:{self.server.port}"
        
        with pytest.raises(Exception):
            await client.fetch_models(base_url)


def test_get_protocol_client_ollama():
    """Test getting Ollama client."""
    client = get_protocol_client(ProviderProtocol.OLLAMA)
    assert isinstance(client, OllamaClient)


def test_get_protocol_client_openai():
    """Test getting OpenAI Compatible client."""
    client = get_protocol_client(ProviderProtocol.OPENAI_COMPATIBLE)
    assert isinstance(client, OpenAICompatibleClient)


def test_get_protocol_client_invalid():
    """Test getting client for invalid protocol."""
    with pytest.raises(ValueError, match="Unsupported protocol"):
        get_protocol_client("invalid_protocol")
