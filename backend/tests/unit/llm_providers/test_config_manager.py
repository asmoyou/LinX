"""
Unit tests for ConfigManager

Tests configuration reading, writing, and provider management.
"""

import tempfile
from pathlib import Path

import pytest
import yaml

from llm_providers.config_manager import ConfigManager
from llm_providers.models import ProviderConfig, ProviderProtocol


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config = {
            'llm': {
                'default_provider': 'ollama',
                'providers': {
                    'ollama': {
                        'protocol': 'ollama',
                        'base_url': 'http://localhost:11434',
                        'timeout': 30,
                        'max_retries': 3,
                        'enabled': True,
                        'selected_models': ['llama2', 'mistral'],
                    }
                }
            }
        }
        yaml.dump(config, f)
        temp_path = f.name
    
    yield temp_path
    
    # Cleanup
    Path(temp_path).unlink(missing_ok=True)


def test_read_config(temp_config_file):
    """Test reading config file."""
    manager = ConfigManager(temp_config_file)
    config = manager.read_config()
    
    assert 'llm' in config
    assert 'providers' in config['llm']
    assert 'ollama' in config['llm']['providers']


def test_get_providers(temp_config_file):
    """Test getting all providers."""
    manager = ConfigManager(temp_config_file)
    providers = manager.get_providers()
    
    assert 'ollama' in providers
    assert isinstance(providers['ollama'], ProviderConfig)
    assert providers['ollama'].protocol == ProviderProtocol.OLLAMA
    assert providers['ollama'].base_url == 'http://localhost:11434'


def test_get_provider(temp_config_file):
    """Test getting a specific provider."""
    manager = ConfigManager(temp_config_file)
    provider = manager.get_provider('ollama')
    
    assert provider is not None
    assert provider.name == 'ollama'
    assert provider.protocol == ProviderProtocol.OLLAMA


def test_get_nonexistent_provider(temp_config_file):
    """Test getting a provider that doesn't exist."""
    manager = ConfigManager(temp_config_file)
    provider = manager.get_provider('nonexistent')
    
    assert provider is None


def test_add_provider(temp_config_file):
    """Test adding a new provider."""
    manager = ConfigManager(temp_config_file)
    
    new_provider = ProviderConfig(
        name='openai',
        protocol=ProviderProtocol.OPENAI_COMPATIBLE,
        base_url='https://api.openai.com',
        api_key='test-key',
        timeout=60,
        max_retries=5,
        enabled=True,
        selected_models=['gpt-4', 'gpt-3.5-turbo'],
    )
    
    manager.add_provider(new_provider)
    
    # Verify it was added
    provider = manager.get_provider('openai')
    assert provider is not None
    assert provider.name == 'openai'
    assert provider.api_key == 'test-key'


def test_add_duplicate_provider(temp_config_file):
    """Test adding a provider that already exists."""
    manager = ConfigManager(temp_config_file)
    
    duplicate_provider = ProviderConfig(
        name='ollama',
        protocol=ProviderProtocol.OLLAMA,
        base_url='http://localhost:11434',
        timeout=30,
        max_retries=3,
        enabled=True,
        selected_models=[],
    )
    
    with pytest.raises(ValueError, match="already exists"):
        manager.add_provider(duplicate_provider)


def test_update_provider(temp_config_file):
    """Test updating an existing provider."""
    manager = ConfigManager(temp_config_file)
    
    updates = {
        'base_url': 'http://localhost:8080',
        'timeout': 60,
        'selected_models': ['llama3'],
    }
    
    manager.update_provider('ollama', updates)
    
    # Verify updates
    provider = manager.get_provider('ollama')
    assert provider.base_url == 'http://localhost:8080'
    assert provider.timeout == 60
    assert provider.selected_models == ['llama3']


def test_update_nonexistent_provider(temp_config_file):
    """Test updating a provider that doesn't exist."""
    manager = ConfigManager(temp_config_file)
    
    with pytest.raises(ValueError, match="not found"):
        manager.update_provider('nonexistent', {'timeout': 60})


def test_delete_provider(temp_config_file):
    """Test deleting a provider."""
    manager = ConfigManager(temp_config_file)
    
    manager.delete_provider('ollama')
    
    # Verify it was deleted
    provider = manager.get_provider('ollama')
    assert provider is None


def test_delete_nonexistent_provider(temp_config_file):
    """Test deleting a provider that doesn't exist."""
    manager = ConfigManager(temp_config_file)
    
    with pytest.raises(ValueError, match="not found"):
        manager.delete_provider('nonexistent')


def test_get_default_provider(temp_config_file):
    """Test getting default provider."""
    manager = ConfigManager(temp_config_file)
    default = manager.get_default_provider()
    
    assert default == 'ollama'


def test_set_default_provider(temp_config_file):
    """Test setting default provider."""
    manager = ConfigManager(temp_config_file)
    
    manager.set_default_provider('vllm')
    
    # Verify it was set
    default = manager.get_default_provider()
    assert default == 'vllm'
