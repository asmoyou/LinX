"""
LLM Provider Configuration Manager

Handles reading and writing provider configurations to config.yaml.

References:
- Requirements 5: Multi-Provider LLM Support
- Design Section 18.8: Settings Page
- Task 6.21.2: Create config.yaml reader/writer utility
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

from llm_providers.models import ProviderConfig, ProviderProtocol

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages LLM provider configurations in config.yaml."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize config manager.
        
        Args:
            config_path: Path to config.yaml file (relative to backend directory)
        """
        # Try to find config.yaml in multiple locations
        possible_paths = [
            Path(config_path),  # Direct path
            Path("backend") / config_path,  # From project root
            Path(__file__).parent.parent / config_path,  # From llm_providers directory
        ]
        
        self.config_path = None
        for path in possible_paths:
            if path.exists():
                self.config_path = path
                break
        
        if self.config_path is None:
            raise FileNotFoundError(
                f"Config file not found. Tried: {[str(p) for p in possible_paths]}"
            )
    
    def read_config(self) -> Dict:
        """Read entire config.yaml file."""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to read config file: {e}")
            raise
    
    def write_config(self, config: Dict) -> None:
        """Write entire config.yaml file."""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            logger.error(f"Failed to write config file: {e}")
            raise
    
    def get_providers(self) -> Dict[str, ProviderConfig]:
        """
        Get all provider configurations.
        
        Returns:
            Dictionary mapping provider name to ProviderConfig
        """
        config = self.read_config()
        llm_config = config.get('llm', {})
        providers_data = llm_config.get('providers', {})
        
        providers = {}
        for name, data in providers_data.items():
            try:
                # Convert to ProviderConfig model
                provider = ProviderConfig(
                    name=name,
                    protocol=data.get('protocol', 'ollama'),
                    base_url=data.get('base_url', ''),
                    api_key=data.get('api_key'),
                    timeout=data.get('timeout', 30),
                    max_retries=data.get('max_retries', 3),
                    enabled=data.get('enabled', True),
                    selected_models=data.get('selected_models', []),
                )
                providers[name] = provider
            except Exception as e:
                logger.warning(f"Failed to parse provider {name}: {e}")
                continue
        
        return providers
    
    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """
        Get a specific provider configuration.
        
        Args:
            name: Provider name
            
        Returns:
            ProviderConfig or None if not found
        """
        providers = self.get_providers()
        return providers.get(name)
    
    def add_provider(self, provider: ProviderConfig) -> None:
        """
        Add a new provider configuration.
        
        Args:
            provider: Provider configuration to add
            
        Raises:
            ValueError: If provider already exists
        """
        config = self.read_config()
        
        # Ensure llm section exists
        if 'llm' not in config:
            config['llm'] = {}
        if 'providers' not in config['llm']:
            config['llm']['providers'] = {}
        
        # Check if provider already exists
        if provider.name in config['llm']['providers']:
            raise ValueError(f"Provider '{provider.name}' already exists")
        
        # Add provider
        config['llm']['providers'][provider.name] = {
            'protocol': provider.protocol,
            'base_url': provider.base_url,
            'api_key': provider.api_key,
            'timeout': provider.timeout,
            'max_retries': provider.max_retries,
            'enabled': provider.enabled,
            'selected_models': provider.selected_models,
        }
        
        # Remove None values
        config['llm']['providers'][provider.name] = {
            k: v for k, v in config['llm']['providers'][provider.name].items()
            if v is not None
        }
        
        self.write_config(config)
        logger.info(f"Added provider: {provider.name}")
    
    def update_provider(self, name: str, updates: Dict) -> None:
        """
        Update an existing provider configuration.
        
        Args:
            name: Provider name
            updates: Dictionary of fields to update
            
        Raises:
            ValueError: If provider doesn't exist
        """
        config = self.read_config()
        
        if 'llm' not in config or 'providers' not in config['llm']:
            raise ValueError(f"Provider '{name}' not found")
        
        if name not in config['llm']['providers']:
            raise ValueError(f"Provider '{name}' not found")
        
        # Update provider fields
        for key, value in updates.items():
            if value is not None:
                config['llm']['providers'][name][key] = value
        
        self.write_config(config)
        logger.info(f"Updated provider: {name}")
    
    def delete_provider(self, name: str) -> None:
        """
        Delete a provider configuration.
        
        Args:
            name: Provider name
            
        Raises:
            ValueError: If provider doesn't exist
        """
        config = self.read_config()
        
        if 'llm' not in config or 'providers' not in config['llm']:
            raise ValueError(f"Provider '{name}' not found")
        
        if name not in config['llm']['providers']:
            raise ValueError(f"Provider '{name}' not found")
        
        # Delete provider
        del config['llm']['providers'][name]
        
        self.write_config(config)
        logger.info(f"Deleted provider: {name}")
    
    def get_default_provider(self) -> str:
        """Get the default provider name."""
        config = self.read_config()
        return config.get('llm', {}).get('default_provider', 'ollama')
    
    def set_default_provider(self, name: str) -> None:
        """Set the default provider."""
        config = self.read_config()
        
        if 'llm' not in config:
            config['llm'] = {}
        
        config['llm']['default_provider'] = name
        self.write_config(config)
        logger.info(f"Set default provider: {name}")


# Singleton instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get singleton ConfigManager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager
