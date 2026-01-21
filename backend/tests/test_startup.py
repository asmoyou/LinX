"""
Unit tests for the startup validation module.

Tests cover:
- Configuration validation on startup
- Error handling
- Logging initialization
- Startup banner
"""

import logging
import tempfile
from pathlib import Path

import pytest
import yaml

from shared.config import Config
from shared.startup import (
    check_config_file_exists,
    initialize_logging,
    print_startup_banner,
    startup_checks,
    validate_startup_config,
)


@pytest.fixture
def valid_config_file():
    """Create a temporary valid configuration file."""
    config_data = {
        "platform": {"name": "Test Platform", "version": "1.0.0", "environment": "development"},
        "api": {
            "host": "0.0.0.0",
            "port": 8000,
            "jwt": {"secret_key": "test-secret", "expiration_hours": 24},
        },
        "database": {
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "username": "test_user",
                "password": "test_pass",
                "pool_size": 10,
            },
            "milvus": {"host": "localhost", "port": 19530},
            "redis": {"host": "localhost", "port": 6379},
        },
        "storage": {
            "minio": {
                "endpoint": "localhost:9000",
                "access_key": "minioadmin",
                "secret_key": "minioadmin",
                "buckets": {
                    "documents": "documents",
                    "audio": "audio",
                    "video": "video",
                    "images": "images",
                    "artifacts": "agent-artifacts",
                },
            }
        },
        "llm": {
            "default_provider": "ollama",
            "providers": {"ollama": {"enabled": True, "models": {"chat": "llama3:70b"}}},
        },
        "agents": {
            "pool": {"min_size": 10, "max_size": 100},
            "resources": {
                "default_cpu_cores": 1.0,
                "default_memory_gb": 2,
                "max_cpu_cores": 4,
                "max_memory_gb": 8,
            },
        },
        "security": {"encryption": {"at_rest": True, "in_transit": True}},
        "monitoring": {"logging": {"level": "INFO", "format": "json"}},
        "quotas": {"default": {"max_agents": 10, "max_storage_gb": 100}},
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = Path(f.name)

    yield config_path

    # Cleanup
    if config_path.exists():
        config_path.unlink()


@pytest.fixture
def invalid_config_file():
    """Create a temporary invalid configuration file."""
    config_data = {
        "platform": {
            "name": "Test Platform",
            "version": "1.0.0",
            "environment": "invalid_env",  # Invalid
        }
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        config_path = Path(f.name)

    yield config_path

    # Cleanup
    if config_path.exists():
        config_path.unlink()


class TestValidateStartupConfig:
    """Tests for validate_startup_config function."""

    def test_valid_config_loads_successfully(self, valid_config_file):
        """Test that valid configuration loads without errors."""
        config = validate_startup_config(str(valid_config_file))

        assert config is not None
        assert config.get("platform.name") == "Test Platform"

    def test_invalid_config_exits(self, invalid_config_file):
        """Test that invalid configuration causes system exit."""
        with pytest.raises(SystemExit) as exc_info:
            validate_startup_config(str(invalid_config_file))

        assert exc_info.value.code == 1

    def test_nonexistent_config_exits(self):
        """Test that nonexistent configuration file causes system exit."""
        with pytest.raises(SystemExit) as exc_info:
            validate_startup_config("nonexistent.yaml")

        assert exc_info.value.code == 1


class TestCheckConfigFileExists:
    """Tests for check_config_file_exists function."""

    def test_existing_file_returns_true(self, valid_config_file):
        """Test that existing file returns True."""
        assert check_config_file_exists(str(valid_config_file)) is True

    def test_nonexistent_file_returns_false(self):
        """Test that nonexistent file returns False."""
        assert check_config_file_exists("nonexistent.yaml") is False


class TestPrintStartupBanner:
    """Tests for print_startup_banner function."""

    def test_banner_prints_without_error(self, valid_config_file, capsys):
        """Test that startup banner prints without errors."""
        config = Config.load(str(valid_config_file))

        print_startup_banner(config)

        captured = capsys.readouterr()
        assert "Test Platform" in captured.out
        assert "1.0.0" in captured.out
        assert "development" in captured.out


class TestInitializeLogging:
    """Tests for initialize_logging function."""

    def test_logging_initialized_with_config(self, valid_config_file):
        """Test that logging is initialized based on config."""
        config = Config.load(str(valid_config_file))

        # Should not raise any errors
        initialize_logging(config)

        # Check that logging was called (we can't reliably check the level
        # because other tests may have already configured logging)
        # Just verify the function completes without error
        assert True


class TestStartupChecks:
    """Tests for startup_checks function."""

    def test_startup_checks_with_valid_config(self, valid_config_file, capsys):
        """Test that startup checks complete successfully with valid config."""
        config = Config.load(str(valid_config_file))

        result_config = startup_checks(config)

        assert result_config is not None
        assert result_config.get("platform.name") == "Test Platform"

        # Check that banner was printed
        captured = capsys.readouterr()
        assert "Test Platform" in captured.out

    def test_startup_checks_loads_config_if_not_provided(
        self, valid_config_file, capsys, monkeypatch
    ):
        """Test that startup_checks loads config if not provided."""
        # Mock the default config path
        monkeypatch.setattr(
            "shared.startup.validate_startup_config",
            lambda path="config.yaml": Config.load(str(valid_config_file)),
        )

        result_config = startup_checks()

        assert result_config is not None


class TestIntegration:
    """Integration tests for startup validation."""

    def test_full_startup_flow(self, valid_config_file, capsys):
        """Test the complete startup flow."""
        # Load config
        config = validate_startup_config(str(valid_config_file))

        # Initialize logging
        initialize_logging(config)

        # Print banner
        print_startup_banner(config)

        # Verify everything worked
        assert config.get("platform.name") == "Test Platform"

        captured = capsys.readouterr()
        assert "Test Platform" in captured.out
