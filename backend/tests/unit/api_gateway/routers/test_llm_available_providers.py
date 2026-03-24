"""Tests for the lightweight available providers endpoint."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from access_control.permissions import CurrentUser
from access_control.rbac import Role


@pytest.fixture
def mock_current_user():
    return CurrentUser(
        user_id="test-user-id",
        username="testuser",
        role=Role.USER.value,
        token_jti="test-jti",
    )


class TestGetAvailableProvidersAndModels:
    @pytest.mark.asyncio
    async def test_includes_failed_db_providers_without_config_fallback(self, mock_current_user):
        db_manager = MagicMock()
        db_manager.list_providers.return_value = [
            SimpleNamespace(
                name="ollama",
                enabled=True,
                models=["qwen3-vl:30b", "bge-m3"],
                last_test_status="failed",
            ),
            SimpleNamespace(
                name="xinference",
                enabled=True,
                models=["bge-reranker-v2-m3"],
                last_test_status=None,
            ),
            SimpleNamespace(
                name="disabled-provider",
                enabled=False,
                models=["ignored"],
                last_test_status="success",
            ),
        ]
        db_context = MagicMock()
        db_context.__enter__.return_value = MagicMock()
        db_context.__exit__.return_value = False

        with patch("api_gateway.routers.llm.get_llm_provider", return_value=MagicMock()):
            with patch("api_gateway.routers.llm.get_db_session", return_value=db_context):
                with patch("api_gateway.routers.llm.ProviderDBManager", return_value=db_manager):
                    with patch(
                        "shared.config.get_config",
                        side_effect=AssertionError("should not read config"),
                    ):
                        from api_gateway.routers.llm import get_available_providers_and_models

                        response = await get_available_providers_and_models(
                            current_user=mock_current_user
                        )

        assert response == {
            "ollama": ["qwen3-vl:30b", "bge-m3"],
            "xinference": ["bge-reranker-v2-m3"],
        }
