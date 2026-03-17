"""
Unit tests for LLM Provider API Routes

Tests the LLM provider management endpoints including provider status,
model listing, health checks, and test generation.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 9: LLM Provider Integration
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from api_gateway.main import app
from api_gateway.routers.llm import (
    LLMConfigResponse,
    ProviderStatus,
    TestGenerationRequest,
    TestGenerationResponse,
    _detect_model_type,
    _test_audio_transcription_model,
)
from access_control.permissions import CurrentUser
from access_control.rbac import Role


@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    return CurrentUser(
        user_id="test-user-id",
        username="testuser",
        role=Role.USER.value,
        token_jti="test-jti",
    )


@pytest.fixture
def mock_admin_user():
    """Mock admin user."""
    return CurrentUser(
        user_id="admin-user-id",
        username="admin",
        role=Role.ADMIN.value,
        token_jti="admin-jti",
    )


@pytest.fixture
def mock_llm_router():
    """Mock LLM router with providers."""
    router = MagicMock()
    router.providers = {
        "ollama": MagicMock(),
        "vllm": MagicMock(),
    }
    router.config = {"default_provider": "ollama"}
    router.fallback_enabled = True
    router.model_mapping = {
        "code": {"ollama": "codellama", "vllm": "codellama"},
        "chat": {"ollama": "llama2", "vllm": "llama2"},
    }
    
    # Mock async methods
    router.health_check_all = AsyncMock(return_value={
        "ollama": True,
        "vllm": False,
    })
    router.list_available_models = AsyncMock(return_value={
        "ollama": ["llama2", "codellama", "mistral"],
        "vllm": ["llama2", "codellama"],
    })
    router.get_token_usage = MagicMock(return_value={
        "ollama": 1000,
        "vllm": 500,
    })
    
    # Mock provider methods
    router.providers["ollama"].list_models = AsyncMock(
        return_value=["llama2", "codellama", "mistral"]
    )
    router.providers["ollama"].health_check = AsyncMock(return_value=True)
    router.providers["vllm"].list_models = AsyncMock(
        return_value=["llama2", "codellama"]
    )
    router.providers["vllm"].health_check = AsyncMock(return_value=False)
    
    # Mock generate method
    mock_response = MagicMock()
    mock_response.content = "Test response"
    mock_response.model = "llama2"
    mock_response.provider = "ollama"
    mock_response.tokens_used = 50
    router.generate = AsyncMock(return_value=mock_response)
    
    return router


class TestGetProviders:
    """Tests for GET /api/v1/llm/providers endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_providers_success(self, mock_current_user, mock_llm_router):
        """Test successful retrieval of provider status."""
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import get_providers
                
                response = await get_providers(current_user=mock_current_user)
                
                assert isinstance(response, LLMConfigResponse)
                assert "ollama" in response.providers
                assert "vllm" in response.providers
                assert response.providers["ollama"].healthy is True
                assert response.providers["vllm"].healthy is False
                assert response.default_provider == "ollama"
                assert response.fallback_enabled is True
    
    @pytest.mark.asyncio
    async def test_get_providers_not_configured(self, mock_current_user):
        """Test when LLM providers are not configured."""
        with patch("api_gateway.routers.llm.get_llm_provider", None):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import get_providers
                
                with pytest.raises(HTTPException) as exc_info:
                    await get_providers(current_user=mock_current_user)
                
                assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
                assert "not configured" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_get_providers_error(self, mock_current_user, mock_llm_router):
        """Test error handling when getting providers."""
        mock_llm_router.health_check_all.side_effect = Exception("Connection error")
        
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import get_providers
                
                with pytest.raises(HTTPException) as exc_info:
                    await get_providers(current_user=mock_current_user)
                
                assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetProviderModels:
    """Tests for GET /api/v1/llm/providers/{provider_name}/models endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_provider_models_success(self, mock_current_user, mock_llm_router):
        """Test successful retrieval of provider models."""
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import get_provider_models
                
                models = await get_provider_models(
                    provider_name="ollama",
                    current_user=mock_current_user
                )
                
                assert isinstance(models, list)
                assert "llama2" in models
                assert "codellama" in models
                assert "mistral" in models
    
    @pytest.mark.asyncio
    async def test_get_provider_models_not_found(self, mock_current_user, mock_llm_router):
        """Test when provider is not found."""
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import get_provider_models
                
                with pytest.raises(HTTPException) as exc_info:
                    await get_provider_models(
                        provider_name="nonexistent",
                        current_user=mock_current_user
                    )
                
                assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
                assert "not found" in exc_info.value.detail


class TestCheckProviderHealth:
    """Tests for GET /api/v1/llm/providers/{provider_name}/health endpoint."""
    
    @pytest.mark.asyncio
    async def test_check_provider_health_success(self, mock_current_user, mock_llm_router):
        """Test successful health check."""
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import check_provider_health
                
                result = await check_provider_health(
                    provider_name="ollama",
                    current_user=mock_current_user
                )
                
                assert result == {"healthy": True}
    
    @pytest.mark.asyncio
    async def test_check_provider_health_unhealthy(self, mock_current_user, mock_llm_router):
        """Test health check for unhealthy provider."""
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import check_provider_health
                
                result = await check_provider_health(
                    provider_name="vllm",
                    current_user=mock_current_user
                )
                
                assert result == {"healthy": False}


class TestTestGeneration:
    """Tests for POST /api/v1/llm/test endpoint."""

    @pytest.mark.asyncio
    async def test_audio_model_detection_and_helper(self, monkeypatch):
        """Audio models should be tested via the transcription endpoint."""

        class _FakeResponse:
            def __init__(self):
                self.status = 200

            async def json(self):
                return {"text": "hello from asr"}

            async def text(self):
                return '{"text":"hello from asr"}'

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        class _FakeSession:
            def __init__(self):
                self.calls = []

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            def post(self, url, **kwargs):
                self.calls.append((url, kwargs))
                return _FakeResponse()

        fake_session = _FakeSession()
        monkeypatch.setattr("aiohttp.ClientSession", lambda: fake_session)

        result = await _test_audio_transcription_model(
            protocol="openai_compatible",
            base_url="http://localhost:9997",
            model="sensevoicesmall",
            api_key="test-key",
            timeout=10,
        )

        assert _detect_model_type("sensevoicesmall") == "audio"
        assert "ASR test successful" in result
        assert fake_session.calls
        assert "/audio/transcriptions" in fake_session.calls[0][0]
    
    @pytest.mark.asyncio
    async def test_test_generation_success(self, mock_current_user, mock_llm_router):
        """Test successful LLM generation."""
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import test_generation
                
                request = TestGenerationRequest(
                    prompt="Hello, world!",
                    provider="ollama",
                    model="llama2",
                    temperature=0.7,
                    max_tokens=100,
                )
                
                response = await test_generation(
                    request=request,
                    current_user=mock_current_user
                )
                
                assert isinstance(response, TestGenerationResponse)
                assert response.content == "Test response"
                assert response.model == "llama2"
                assert response.provider == "ollama"
                assert response.tokens_used == 50
                assert response.success is True
    
    @pytest.mark.asyncio
    async def test_test_generation_error(self, mock_current_user, mock_llm_router):
        """Test error handling during generation."""
        mock_llm_router.generate.side_effect = Exception("Generation failed")
        
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_current_user):
                from api_gateway.routers.llm import test_generation
                
                request = TestGenerationRequest(
                    prompt="Hello, world!",
                )
                
                with pytest.raises(HTTPException) as exc_info:
                    await test_generation(
                        request=request,
                        current_user=mock_current_user
                    )
                
                assert exc_info.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetTokenUsage:
    """Tests for GET /api/v1/llm/token-usage endpoint."""
    
    @pytest.mark.asyncio
    async def test_get_token_usage_success(self, mock_admin_user, mock_llm_router):
        """Test successful token usage retrieval (admin only)."""
        with patch("api_gateway.routers.llm.get_llm_provider", return_value=mock_llm_router):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_admin_user):
                from api_gateway.routers.llm import get_token_usage
                
                # Note: The @require_role decorator needs to be tested separately
                # This test assumes the decorator passes
                result = await get_token_usage(current_user=mock_admin_user)
                
                assert result == {"ollama": 1000, "vllm": 500}
    
    @pytest.mark.asyncio
    async def test_get_token_usage_not_configured(self, mock_admin_user):
        """Test when LLM providers are not configured."""
        with patch("api_gateway.routers.llm.get_llm_provider", None):
            with patch("api_gateway.routers.llm.get_current_user", return_value=mock_admin_user):
                from api_gateway.routers.llm import get_token_usage
                
                with pytest.raises(HTTPException) as exc_info:
                    await get_token_usage(current_user=mock_admin_user)
                
                assert exc_info.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
