"""
Tests for LLM Provider Integration

Tests the LLM provider interface, implementations, and router.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Integration Design
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from llm_providers.base import (
    BaseLLMProvider,
    LLMResponse,
    EmbeddingResponse,
    TaskType
)
from llm_providers.ollama_provider import OllamaProvider
from llm_providers.vllm_provider import VLLMProvider
from llm_providers.openai_provider import OpenAIProvider
from llm_providers.anthropic_provider import AnthropicProvider
from llm_providers.router import LLMRouter
from llm_providers.prompts import (
    get_agent_prompt,
    get_task_decomposition_prompt,
    get_clarification_prompt
)


# Test Base Provider Interface

def test_base_provider_is_abstract():
    """Test that BaseLLMProvider cannot be instantiated directly"""
    with pytest.raises(TypeError):
        BaseLLMProvider({})


# Test Ollama Provider

@pytest.mark.asyncio
async def test_ollama_provider_initialization():
    """Test Ollama provider initialization"""
    config = {"base_url": "http://localhost:11434", "timeout": 60}
    provider = OllamaProvider(config)
    
    assert provider.base_url == "http://localhost:11434"
    assert provider.timeout == 60
    assert provider.get_provider_name() == "OllamaProvider"


@pytest.mark.asyncio
async def test_ollama_generate_success():
    """Test successful text generation with Ollama"""
    config = {"base_url": "http://localhost:11434"}
    provider = OllamaProvider(config)
    
    # Mock the aiohttp session
    mock_response = {
        "response": "This is a test response",
        "eval_count": 50,
        "prompt_eval_count": 10,
        "total_duration": 1000000,
        "done_reason": "stop"
    }
    
    # Create mock session
    mock_session_obj = AsyncMock()
    mock_post = AsyncMock()
    mock_post.return_value.__aenter__.return_value.json = AsyncMock(
        return_value=mock_response
    )
    mock_post.return_value.__aenter__.return_value.raise_for_status = Mock()
    mock_session_obj.post = mock_post
    
    # Make _get_session return the mock session
    async def mock_get_session():
        return mock_session_obj
    
    with patch.object(provider, '_get_session', side_effect=mock_get_session):
        response = await provider.generate(
            prompt="Test prompt",
            model="llama3",
            temperature=0.7
        )
        
        assert isinstance(response, LLMResponse)
        assert response.content == "This is a test response"
        assert response.model == "llama3"
        assert response.provider == "Ollama"
        assert response.tokens_used == 60
        assert response.finish_reason == "stop"


@pytest.mark.asyncio
async def test_ollama_generate_embedding():
    """Test embedding generation with Ollama"""
    config = {"base_url": "http://localhost:11434"}
    provider = OllamaProvider(config)
    
    mock_response = {
        "embedding": [0.1, 0.2, 0.3],
        "prompt_eval_count": 5,
        "total_duration": 500000
    }
    
    # Create mock session
    mock_session_obj = AsyncMock()
    mock_post = AsyncMock()
    mock_post.return_value.__aenter__.return_value.json = AsyncMock(
        return_value=mock_response
    )
    mock_post.return_value.__aenter__.return_value.raise_for_status = Mock()
    mock_session_obj.post = mock_post
    
    # Make _get_session return the mock session
    async def mock_get_session():
        return mock_session_obj
    
    with patch.object(provider, '_get_session', side_effect=mock_get_session):
        response = await provider.generate_embedding(
            text="Test text",
            model="nomic-embed-text"
        )
        
        assert isinstance(response, EmbeddingResponse)
        assert response.embedding == [0.1, 0.2, 0.3]
        assert response.model == "nomic-embed-text"
        assert response.provider == "Ollama"
        assert response.tokens_used == 5


# Test vLLM Provider

@pytest.mark.asyncio
async def test_vllm_provider_initialization():
    """Test vLLM provider initialization"""
    config = {
        "base_url": "http://localhost:8000",
        "timeout": 120,
        "api_key": "test-key"
    }
    provider = VLLMProvider(config)
    
    assert provider.base_url == "http://localhost:8000"
    assert provider.timeout == 120
    assert provider.api_key == "test-key"


@pytest.mark.asyncio
async def test_vllm_generate_success():
    """Test successful text generation with vLLM"""
    config = {"base_url": "http://localhost:8000"}
    provider = VLLMProvider(config)
    
    mock_response = {
        "choices": [{"text": "vLLM response", "finish_reason": "stop"}],
        "usage": {
            "total_tokens": 75,
            "prompt_tokens": 25,
            "completion_tokens": 50
        }
    }
    
    # Create mock session
    mock_session_obj = AsyncMock()
    mock_post = AsyncMock()
    mock_post.return_value.__aenter__.return_value.json = AsyncMock(
        return_value=mock_response
    )
    mock_post.return_value.__aenter__.return_value.raise_for_status = Mock()
    mock_session_obj.post = mock_post
    
    # Make _get_session return the mock session
    async def mock_get_session():
        return mock_session_obj
    
    with patch.object(provider, '_get_session', side_effect=mock_get_session):
        response = await provider.generate(
            prompt="Test prompt",
            model="llama3",
            temperature=0.7
        )
        
        assert response.content == "vLLM response"
        assert response.tokens_used == 75


# Test OpenAI Provider

@pytest.mark.asyncio
async def test_openai_provider_requires_api_key():
    """Test that OpenAI provider requires API key"""
    config = {}
    with pytest.raises(ValueError, match="OpenAI API key is required"):
        OpenAIProvider(config)


@pytest.mark.asyncio
async def test_openai_generate_chat_model():
    """Test text generation with OpenAI chat model"""
    config = {"api_key": "test-key"}
    provider = OpenAIProvider(config)
    
    mock_response = {
        "choices": [{
            "message": {"content": "OpenAI response"},
            "finish_reason": "stop"
        }],
        "usage": {
            "total_tokens": 100,
            "prompt_tokens": 30,
            "completion_tokens": 70
        }
    }
    
    # Create mock session
    mock_session_obj = AsyncMock()
    mock_post = AsyncMock()
    mock_post.return_value.__aenter__.return_value.json = AsyncMock(
        return_value=mock_response
    )
    mock_post.return_value.__aenter__.return_value.raise_for_status = Mock()
    mock_session_obj.post = mock_post
    
    # Make _get_session return the mock session
    async def mock_get_session():
        return mock_session_obj
    
    with patch.object(provider, '_get_session', side_effect=mock_get_session):
        response = await provider.generate(
            prompt="Test prompt",
            model="gpt-4",
            temperature=0.7
        )
        
        assert response.content == "OpenAI response"
        assert response.provider == "OpenAI"
        assert response.tokens_used == 100


# Test Anthropic Provider

@pytest.mark.asyncio
async def test_anthropic_provider_requires_api_key():
    """Test that Anthropic provider requires API key"""
    config = {}
    with pytest.raises(ValueError, match="Anthropic API key is required"):
        AnthropicProvider(config)


@pytest.mark.asyncio
async def test_anthropic_embedding_not_supported():
    """Test that Anthropic does not support embeddings"""
    config = {"api_key": "test-key"}
    provider = AnthropicProvider(config)
    
    with pytest.raises(NotImplementedError):
        await provider.generate_embedding(text="test", model="claude-3")


# Test LLM Router

@pytest.mark.asyncio
async def test_router_initialization():
    """Test LLM router initialization"""
    config = {
        "providers": {
            "ollama": {"base_url": "http://localhost:11434"}
        },
        "model_mapping": {
            "chat": {"ollama": "llama3"}
        },
        "fallback_enabled": False,
        "max_retries": 3
    }
    
    router = LLMRouter(config)
    
    assert "ollama" in router.providers
    assert router.max_retries == 3
    assert not router.fallback_enabled


@pytest.mark.asyncio
async def test_router_model_selection():
    """Test router model selection for task types"""
    config = {
        "providers": {
            "ollama": {"base_url": "http://localhost:11434"}
        },
        "model_mapping": {
            "chat": {"ollama": "llama3"},
            "code_generation": {"ollama": "codellama"},
            "embedding": {"ollama": "nomic-embed-text"}
        }
    }
    
    router = LLMRouter(config)
    
    provider, model = router.select_model_for_task(TaskType.CHAT)
    assert provider == "ollama"
    assert model == "llama3"
    
    provider, model = router.select_model_for_task(TaskType.CODE_GENERATION)
    assert provider == "ollama"
    assert model == "codellama"
    
    provider, model = router.select_model_for_task(TaskType.EMBEDDING)
    assert provider == "ollama"
    assert model == "nomic-embed-text"


@pytest.mark.asyncio
async def test_router_token_tracking():
    """Test router token usage tracking"""
    config = {
        "providers": {
            "ollama": {"base_url": "http://localhost:11434"}
        },
        "model_mapping": {
            "chat": {"ollama": "llama3"}
        }
    }
    
    router = LLMRouter(config)
    
    # Track some token usage
    router._track_token_usage("ollama", 100)
    router._track_token_usage("ollama", 50)
    router._track_token_usage("vllm", 75)
    
    usage = router.get_token_usage()
    assert usage["ollama"] == 150
    assert usage["vllm"] == 75


# Test Prompt Templates

def test_agent_prompt_formatting():
    """Test agent system prompt formatting"""
    prompt = get_agent_prompt(
        agent_type="Data Analyst",
        skills=["data_processing", "visualization"],
        task_description="Analyze sales data",
        tools=["pandas", "matplotlib"],
        context="Q4 2023 data"
    )
    
    assert "Data Analyst" in prompt
    assert "data_processing" in prompt
    assert "Analyze sales data" in prompt
    assert "pandas" in prompt
    assert "Q4 2023 data" in prompt


def test_task_decomposition_prompt():
    """Test task decomposition prompt formatting"""
    prompt = get_task_decomposition_prompt(
        goal="Create a sales report",
        available_skills=["data_processing", "writing", "visualization"]
    )
    
    assert "Create a sales report" in prompt
    assert "data_processing" in prompt
    assert "JSON" in prompt


def test_clarification_prompt():
    """Test clarification prompt formatting"""
    prompt = get_clarification_prompt(goal="Build a website")
    
    assert "Build a website" in prompt
    assert "clarifying questions" in prompt
    assert "JSON" in prompt


# Integration Tests

@pytest.mark.asyncio
@pytest.mark.integration
async def test_ollama_integration():
    """
    Integration test for Ollama provider.
    Requires Ollama running on localhost:11434
    """
    config = {"base_url": "http://localhost:11434"}
    provider = OllamaProvider(config)
    
    # Check health
    is_healthy = await provider.health_check()
    if not is_healthy:
        pytest.skip("Ollama not available")
    
    # List models
    models = await provider.list_models()
    assert isinstance(models, list)
    
    # Generate text (if models available)
    if models:
        response = await provider.generate(
            prompt="Say hello",
            model=models[0],
            temperature=0.7,
            max_tokens=10
        )
        assert isinstance(response, LLMResponse)
        assert len(response.content) > 0
    
    await provider.close()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_router_integration():
    """
    Integration test for LLM router.
    Requires Ollama running on localhost:11434
    """
    config = {
        "providers": {
            "ollama": {"base_url": "http://localhost:11434"}
        },
        "model_mapping": {
            "chat": {"ollama": "llama3"}
        },
        "fallback_enabled": False,
        "max_retries": 2
    }
    
    router = LLMRouter(config)
    
    # Check health
    health = await router.health_check_all()
    if not health.get("ollama"):
        pytest.skip("Ollama not available")
    
    # Generate text
    response = await router.generate(
        prompt="Say hello",
        task_type=TaskType.CHAT,
        temperature=0.7,
        max_tokens=10
    )
    
    assert isinstance(response, LLMResponse)
    assert len(response.content) > 0
    
    # Check token tracking
    usage = router.get_token_usage()
    assert "ollama" in usage
    assert usage["ollama"] > 0
    
    await router.close_all()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
