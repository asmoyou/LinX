"""
Unit tests for the configuration loader module.

Tests cover:
- Configuration loading from YAML files
- Environment variable substitution
- Nested configuration access
- Default values
- Error handling
- Singleton pattern
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from shared.config import Config, ConfigurationError, get_config, reload_config


@pytest.fixture
def sample_config_data():
    """Sample configuration data for testing."""
    return {
        "platform": {"name": "Test Platform", "version": "1.0.0", "environment": "test"},
        "api": {
            "host": "0.0.0.0",
            "port": 8000,
            "jwt": {"secret_key": "${JWT_SECRET}", "expiration_hours": 24},
        },
        "database": {
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "password": "${POSTGRES_PASSWORD}",
                "pool_size": 20,
            }
        },
        "features": {"enabled": ["feature1", "feature2"], "disabled": []},
    }


@pytest.fixture
def config_file(sample_config_data):
    """Create a temporary configuration file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(sample_config_data, f)
        config_path = Path(f.name)

    yield config_path

    # Cleanup
    if config_path.exists():
        config_path.unlink()


@pytest.fixture
def set_env_vars():
    """Set environment variables for testing."""
    original_env = os.environ.copy()

    os.environ["JWT_SECRET"] = "test-jwt-secret-key"
    os.environ["POSTGRES_PASSWORD"] = "test-db-password"

    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


class TestConfigLoading:
    """Tests for configuration loading."""

    def test_load_valid_config(self, config_file):
        """Test loading a valid configuration file."""
        config = Config.load(config_file)

        assert config is not None
        assert config.config_path == config_file
        assert config.get("platform.name") == "Test Platform"

    def test_load_nonexistent_file(self):
        """Test loading a non-existent configuration file."""
        with pytest.raises(ConfigurationError, match="Configuration file not found"):
            Config.load("nonexistent.yaml")

    def test_load_invalid_yaml(self):
        """Test loading an invalid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            invalid_path = Path(f.name)

        try:
            with pytest.raises(ConfigurationError, match="Failed to parse YAML"):
                Config.load(invalid_path)
        finally:
            invalid_path.unlink()

    def test_load_non_dict_yaml(self):
        """Test loading a YAML file that doesn't contain a dictionary."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("- item1\n- item2\n")
            list_path = Path(f.name)

        try:
            with pytest.raises(ConfigurationError, match="must contain a YAML dictionary"):
                Config.load(list_path)
        finally:
            list_path.unlink()


class TestConfigAccess:
    """Tests for configuration value access."""

    def test_get_simple_value(self, config_file):
        """Test getting a simple configuration value."""
        config = Config.load(config_file)

        assert config.get("platform.name") == "Test Platform"
        assert config.get("api.port") == 8000

    def test_get_nested_value(self, config_file):
        """Test getting nested configuration values."""
        config = Config.load(config_file)

        assert config.get("database.postgres.host") == "localhost"
        assert config.get("database.postgres.port") == 5432
        assert config.get("api.jwt.expiration_hours") == 24

    def test_get_with_default(self, config_file):
        """Test getting a value with a default."""
        config = Config.load(config_file)

        assert config.get("nonexistent.key", default="fallback") == "fallback"
        assert config.get("another.missing.key", default=42) == 42

    def test_get_list_value(self, config_file):
        """Test getting a list value."""
        config = Config.load(config_file)

        features = config.get("features.enabled")
        assert isinstance(features, list)
        assert features == ["feature1", "feature2"]

    def test_has_key(self, config_file):
        """Test checking if a key exists."""
        config = Config.load(config_file)

        assert config.has("platform.name") is True
        assert config.has("database.postgres.host") is True
        assert config.has("nonexistent.key") is False

    def test_get_section(self, config_file):
        """Test getting an entire configuration section."""
        config = Config.load(config_file)

        postgres_config = config.get_section("database.postgres")
        assert isinstance(postgres_config, dict)
        assert postgres_config["host"] == "localhost"
        assert postgres_config["port"] == 5432

    def test_get_section_not_found(self, config_file):
        """Test getting a non-existent section."""
        config = Config.load(config_file)

        with pytest.raises(ConfigurationError, match="Configuration section not found"):
            config.get_section("nonexistent.section")

    def test_get_section_not_dict(self, config_file):
        """Test getting a section that is not a dictionary."""
        config = Config.load(config_file)

        with pytest.raises(ConfigurationError, match="is not a dictionary"):
            config.get_section("api.port")


class TestEnvironmentVariableSubstitution:
    """Tests for environment variable substitution."""

    def test_substitute_env_var(self, config_file, set_env_vars):
        """Test substituting environment variables."""
        config = Config.load(config_file)

        jwt_secret = config.get("api.jwt.secret_key")
        assert jwt_secret == "test-jwt-secret-key"

        db_password = config.get("database.postgres.password")
        assert db_password == "test-db-password"

    def test_substitute_missing_env_var(self, config_file):
        """Test substituting a missing environment variable."""
        # Ensure the env var is not set
        if "MISSING_VAR" in os.environ:
            del os.environ["MISSING_VAR"]

        # Create config with missing env var
        config_data = {"test": {"value": "${MISSING_VAR}"}}
        config = Config(config_data)

        # Should keep the original ${MISSING_VAR} string
        value = config.get("test.value")
        assert value == "${MISSING_VAR}"

    def test_substitute_in_nested_dict(self, config_file, set_env_vars):
        """Test substituting environment variables in nested dictionaries."""
        config = Config.load(config_file)

        postgres_section = config.get_section("database.postgres")
        assert postgres_section["password"] == "test-db-password"

    def test_substitute_in_list(self, set_env_vars):
        """Test substituting environment variables in lists."""
        os.environ["LIST_VAR"] = "substituted_value"

        config_data = {"items": ["item1", "${LIST_VAR}", "item3"]}
        config = Config(config_data)

        items = config.get("items")
        assert items == ["item1", "substituted_value", "item3"]

    def test_no_substitution_for_non_strings(self, config_file):
        """Test that non-string values are not affected by substitution."""
        config = Config.load(config_file)

        # Numbers should remain as numbers
        assert config.get("api.port") == 8000
        assert isinstance(config.get("api.port"), int)

        # Lists should remain as lists
        features = config.get("features.enabled")
        assert isinstance(features, list)


class TestConfigValidation:
    """Tests for configuration validation."""

    def test_validate_required_env_vars_success(self, config_file, set_env_vars):
        """Test validating required environment variables that are set."""
        config = Config.load(config_file)

        # Should not raise an exception
        config.validate_required_env_vars(["JWT_SECRET", "POSTGRES_PASSWORD"])

    def test_validate_required_env_vars_failure(self, config_file):
        """Test validating required environment variables that are not set."""
        config = Config.load(config_file)

        # Ensure vars are not set
        for var in ["MISSING_VAR1", "MISSING_VAR2"]:
            if var in os.environ:
                del os.environ[var]

        with pytest.raises(ConfigurationError, match="Required environment variables not set"):
            config.validate_required_env_vars(["MISSING_VAR1", "MISSING_VAR2"])


class TestSingletonPattern:
    """Tests for singleton pattern implementation."""

    def test_get_config_singleton(self, config_file):
        """Test that get_config returns the same instance."""
        # Clear any existing instance
        get_config.cache_clear()

        config1 = get_config(config_file)
        config2 = get_config(config_file)

        assert config1 is config2

    def test_reload_config(self, config_file):
        """Test reloading configuration."""
        # Clear any existing instance
        get_config.cache_clear()

        config1 = get_config(config_file)
        original_name = config1.get("platform.name")

        # Modify the config file
        with open(config_file, "r") as f:
            data = yaml.safe_load(f)
        data["platform"]["name"] = "Modified Platform"
        with open(config_file, "w") as f:
            yaml.dump(data, f)

        # Reload configuration
        config2 = reload_config(config_file)

        assert config2.get("platform.name") == "Modified Platform"
        assert config2.get("platform.name") != original_name


class TestConfigGetAll:
    """Tests for getting all configuration."""

    def test_get_all(self, config_file, set_env_vars):
        """Test getting all configuration with substitution."""
        config = Config.load(config_file)

        all_config = config.get_all()

        assert isinstance(all_config, dict)
        assert all_config["platform"]["name"] == "Test Platform"
        assert all_config["api"]["jwt"]["secret_key"] == "test-jwt-secret-key"
        assert all_config["database"]["postgres"]["password"] == "test-db-password"


class TestConfigCaching:
    """Tests for configuration value caching."""

    def test_caching_substituted_values(self, config_file, set_env_vars):
        """Test that substituted values are cached."""
        config = Config.load(config_file)

        # First access
        value1 = config.get("api.jwt.secret_key")

        # Change environment variable
        os.environ["JWT_SECRET"] = "new-secret"

        # Second access should return cached value
        value2 = config.get("api.jwt.secret_key")

        assert value1 == value2 == "test-jwt-secret-key"


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_config(self):
        """Test handling empty configuration."""
        config = Config({})

        assert config.get("any.key") is None
        assert config.get("any.key", default="default") == "default"

    def test_deeply_nested_access(self, config_file):
        """Test accessing deeply nested values."""
        config_data = {"level1": {"level2": {"level3": {"level4": {"value": "deep_value"}}}}}
        config = Config(config_data)

        assert config.get("level1.level2.level3.level4.value") == "deep_value"

    def test_config_repr(self, config_file):
        """Test string representation of config."""
        config = Config.load(config_file)

        repr_str = repr(config)
        assert "Config" in repr_str
        assert str(config_file) in repr_str
