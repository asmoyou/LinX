"""
Configuration Management Module

This module provides a centralized configuration loader with the following features:
- Loads configuration from config.yaml file
- Supports environment variable substitution using ${VAR_NAME} syntax
- Provides type-safe access to configuration values
- Handles nested configuration structures
- Supports default values
- Implements singleton pattern for global access
- Validates configuration on startup

References:
- Requirements 20: Configuration Management
- Design Section 16: Configuration Management
"""

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Raised when there is an error in configuration loading or validation."""

    pass


class Config:
    """
    Configuration loader with environment variable substitution.

    This class loads configuration from a YAML file and provides type-safe
    access to configuration values. It supports:
    - Environment variable substitution (${VAR_NAME} syntax)
    - Nested configuration access using dot notation
    - Default values for missing keys
    - Singleton pattern for global access

    Example:
        >>> config = Config.load("config.yaml")
        >>> db_host = config.get("database.postgres.host")
        >>> api_port = config.get("api.port", default=8000)
        >>> jwt_secret = config.get("api.jwt.secret_key")  # Substitutes ${JWT_SECRET}
    """

    # Environment variable substitution pattern: ${VAR_NAME}
    ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

    def __init__(self, config_data: Dict[str, Any], config_path: Optional[Path] = None):
        """
        Initialize configuration with loaded data.

        Args:
            config_data: Dictionary containing configuration data
            config_path: Path to the configuration file (for reference)
        """
        self._config_data = config_data
        self._config_path = config_path
        self._substituted_cache: Dict[str, Any] = {}

    @classmethod
    def load(cls, config_path: Union[str, Path] = "config.yaml") -> "Config":
        """
        Load configuration from a YAML file.

        Args:
            config_path: Path to the configuration file (default: "config.yaml")

        Returns:
            Config instance with loaded configuration

        Raises:
            ConfigurationError: If the configuration file cannot be loaded
        """
        config_path = Path(config_path)

        if not config_path.exists():
            raise ConfigurationError(f"Configuration file not found: {config_path.absolute()}")

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)

            if not isinstance(config_data, dict):
                raise ConfigurationError(
                    f"Configuration file must contain a YAML dictionary, "
                    f"got {type(config_data).__name__}"
                )

            logger.info(f"Loaded configuration from {config_path.absolute()}")
            return cls(config_data, config_path)

        except yaml.YAMLError as e:
            raise ConfigurationError(f"Failed to parse YAML configuration file: {e}") from e
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration file: {e}") from e

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key with environment variable substitution.

        Supports nested keys using dot notation (e.g., "database.postgres.host").
        Environment variables in the format ${VAR_NAME} are automatically substituted.

        Args:
            key: Configuration key (supports dot notation for nested values)
            default: Default value if key is not found

        Returns:
            Configuration value with environment variables substituted

        Example:
            >>> config.get("api.port")
            8000
            >>> config.get("database.postgres.password")  # Returns value of ${POSTGRES_PASSWORD}
            "secret_password"
            >>> config.get("nonexistent.key", default="fallback")
            "fallback"
        """
        # Check cache first
        if key in self._substituted_cache:
            return self._substituted_cache[key]

        # Navigate nested dictionary using dot notation
        value = self._get_nested_value(key)

        if value is None:
            return default

        # Substitute environment variables
        substituted_value = self._substitute_env_vars(value)

        # Cache the substituted value
        self._substituted_cache[key] = substituted_value

        return substituted_value

    def get_section(self, section: str) -> Dict[str, Any]:
        """
        Get an entire configuration section as a dictionary.

        Args:
            section: Section name (supports dot notation)

        Returns:
            Dictionary containing the section configuration

        Raises:
            ConfigurationError: If section is not found or is not a dictionary

        Example:
            >>> db_config = config.get_section("database.postgres")
            >>> print(db_config["host"])
            "localhost"
        """
        value = self._get_nested_value(section)

        if value is None:
            raise ConfigurationError(f"Configuration section not found: {section}")

        if not isinstance(value, dict):
            raise ConfigurationError(
                f"Configuration section '{section}' is not a dictionary, "
                f"got {type(value).__name__}"
            )

        # Recursively substitute environment variables in the entire section
        return self._substitute_env_vars(value)

    def has(self, key: str) -> bool:
        """
        Check if a configuration key exists.

        Args:
            key: Configuration key (supports dot notation)

        Returns:
            True if key exists, False otherwise
        """
        return self._get_nested_value(key) is not None

    def _get_nested_value(self, key: str) -> Any:
        """
        Get a value from nested dictionary using dot notation.

        Args:
            key: Key with dot notation (e.g., "database.postgres.host")

        Returns:
            Value at the specified key path, or None if not found
        """
        keys = key.split(".")
        value = self._config_data

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None

        return value

    def _substitute_env_vars(self, value: Any) -> Any:
        """
        Recursively substitute environment variables in configuration values.

        Supports the ${VAR_NAME} syntax. If the environment variable is not set,
        the original ${VAR_NAME} string is kept.

        Args:
            value: Configuration value (can be string, dict, list, or other types)

        Returns:
            Value with environment variables substituted
        """
        if isinstance(value, str):
            return self._substitute_string(value)
        elif isinstance(value, dict):
            return {k: self._substitute_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._substitute_env_vars(item) for item in value]
        else:
            return value

    def _substitute_string(self, value: str) -> str:
        """
        Substitute environment variables in a string.

        Args:
            value: String potentially containing ${VAR_NAME} patterns

        Returns:
            String with environment variables substituted
        """

        def replace_env_var(match):
            var_name = match.group(1)
            env_value = os.environ.get(var_name)

            if env_value is None:
                logger.warning(
                    f"Environment variable '{var_name}' not set, "
                    f"keeping original value: {match.group(0)}"
                )
                return match.group(0)

            return env_value

        return self.ENV_VAR_PATTERN.sub(replace_env_var, value)

    def validate_required_env_vars(self, required_vars: list[str]) -> None:
        """
        Validate that required environment variables are set.

        Args:
            required_vars: List of required environment variable names

        Raises:
            ConfigurationError: If any required environment variable is not set
        """
        missing_vars = []

        for var in required_vars:
            if not os.environ.get(var):
                missing_vars.append(var)

        if missing_vars:
            raise ConfigurationError(
                f"Required environment variables not set: {', '.join(missing_vars)}"
            )

    def get_all(self) -> Dict[str, Any]:
        """
        Get the entire configuration as a dictionary with environment variables substituted.

        Returns:
            Complete configuration dictionary
        """
        return self._substitute_env_vars(self._config_data)

    @property
    def config_path(self) -> Optional[Path]:
        """Get the path to the configuration file."""
        return self._config_path

    def __repr__(self) -> str:
        """String representation of the configuration."""
        path_str = str(self._config_path) if self._config_path else "in-memory"
        return f"Config(source={path_str})"


# Singleton instance
_config_instance: Optional[Config] = None


@lru_cache(maxsize=1)
def get_config(config_path: Union[str, Path] = "config.yaml") -> Config:
    """
    Get the global configuration instance (singleton pattern).

    This function loads the configuration once and returns the same instance
    on subsequent calls. This ensures consistent configuration across the
    entire application.

    Args:
        config_path: Path to the configuration file (default: "config.yaml")

    Returns:
        Global Config instance

    Example:
        >>> config = get_config()
        >>> db_host = config.get("database.postgres.host")
    """
    global _config_instance

    if _config_instance is None:
        _config_instance = Config.load(config_path)

    return _config_instance


def reload_config(config_path: Union[str, Path] = "config.yaml") -> Config:
    """
    Reload the configuration from file.

    This function forces a reload of the configuration, useful for
    hot-reloading configuration changes.

    Args:
        config_path: Path to the configuration file

    Returns:
        Newly loaded Config instance
    """
    global _config_instance

    # Clear the cache
    get_config.cache_clear()

    # Load new configuration
    _config_instance = Config.load(config_path)

    logger.info("Configuration reloaded")
    return _config_instance
