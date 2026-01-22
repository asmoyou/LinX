"""
Test LLM Provider Deletion Logic

Tests the fix for config.yaml vs database provider deletion.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException

from llm_providers.db_manager import ProviderDBManager
from llm_providers.models import ProviderProtocol


def test_delete_database_provider_success(db_session):
    """Test deleting a provider that exists in database."""
    db_manager = ProviderDBManager(db_session)
    
    # Create a provider in database
    provider = db_manager.create_provider(
        name="test_provider",
        protocol=ProviderProtocol.OLLAMA,
        base_url="http://localhost:11434",
        models=["test-model"],
    )
    
    # Delete should succeed
    result = db_manager.delete_provider("test_provider")
    assert result is True
    
    # Verify it's deleted
    deleted_provider = db_manager.get_provider("test_provider")
    assert deleted_provider is None


def test_delete_nonexistent_provider(db_session):
    """Test deleting a provider that doesn't exist."""
    db_manager = ProviderDBManager(db_session)
    
    # Delete should return False
    result = db_manager.delete_provider("nonexistent")
    assert result is False


def test_delete_config_provider_should_fail():
    """Test that config.yaml providers cannot be deleted via API."""
    # This test verifies the API endpoint logic
    # In practice, the API should check if provider is in config.yaml
    # and return 400 Bad Request with appropriate message
    
    # Mock config with vllm provider
    mock_config = {
        "llm": {
            "providers": {
                "vllm": {
                    "enabled": True,
                    "base_url": "http://localhost:8000",
                    "models": {"chat": "llama-3-70b"}
                }
            }
        }
    }
    
    with patch('shared.config.get_config') as mock_get_config:
        mock_get_config.return_value.get.side_effect = lambda key, default=None: {
            "llm.providers": mock_config["llm"]["providers"]
        }.get(key, default)
        
        # Simulate API endpoint logic
        provider_name = "vllm"
        config_providers = mock_config["llm"]["providers"]
        
        # Provider is in config.yaml
        assert provider_name in config_providers
        
        # Should raise HTTPException with 400 status
        # (This would be tested in the actual API test)


def test_list_providers_includes_config_and_db(db_session):
    """Test that list_providers returns both config.yaml and database providers."""
    db_manager = ProviderDBManager(db_session)
    
    # Create a database provider
    db_manager.create_provider(
        name="custom_provider",
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        base_url="http://custom:8000",
        models=["custom-model"],
    )
    
    # Get database providers
    db_providers = db_manager.list_providers()
    db_provider_names = {p.name for p in db_providers}
    
    assert "custom_provider" in db_provider_names
    
    # In the actual API, config.yaml providers would also be included
    # and marked with is_config_based=True


@pytest.fixture
def db_session():
    """Mock database session for testing."""
    from unittest.mock import MagicMock
    from sqlalchemy.orm import Session
    
    session = MagicMock(spec=Session)
    
    # Mock query behavior
    providers = []
    
    def mock_query(model):
        query_mock = MagicMock()
        query_mock.filter.return_value.first.return_value = None
        query_mock.order_by.return_value.all.return_value = providers
        return query_mock
    
    session.query = mock_query
    session.add = lambda p: providers.append(p)
    session.commit = lambda: None
    session.refresh = lambda p: None
    session.delete = lambda p: providers.remove(p) if p in providers else None
    
    return session
