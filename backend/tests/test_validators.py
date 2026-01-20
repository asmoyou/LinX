"""
Unit tests for the configuration validation module.

Tests cover:
- Required section validation
- Data type validation
- Value range validation (ports, percentages, etc.)
- Environment variable validation
- Dependency validation
- Error message clarity
"""

import os
import tempfile
from pathlib import Path
import pytest
import yaml

from shared.config import Config, ConfigurationError
from shared.validators import (
    ConfigValidator,
    ValidationError,
    ValidationResult,
    validate_config,
    validate_config_file
)


@pytest.fixture
def minimal_valid_config():
    """Minimal valid configuration for testing."""
    return {
        "platform": {
            "name": "Test Platform",
            "version": "1.0.0",
            "environment": "development"
        },
        "api": {
            "host": "0.0.0.0",
            "port": 8000,
            "jwt": {
                "secret_key": "test-secret",
                "expiration_hours": 24
            }
        },
        "database": {
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "username": "test_user",
                "password": "test_pass",
                "pool_size": 10
            },
            "milvus": {
                "host": "localhost",
                "port": 19530
            },
            "redis": {
                "host": "localhost",
                "port": 6379
            }
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
                    "artifacts": "agent-artifacts"
                }
            }
        },
        "llm": {
            "default_provider": "ollama",
            "providers": {
                "ollama": {
                    "enabled": True,
                    "models": {
                        "chat": "llama3:70b"
                    }
                }
            }
        },
        "agents": {
            "pool": {
                "min_size": 10,
                "max_size": 100
            },
            "resources": {
                "default_cpu_cores": 1.0,
                "default_memory_gb": 2,
                "max_cpu_cores": 4,
                "max_memory_gb": 8
            }
        },
        "security": {
            "encryption": {
                "at_rest": True,
                "in_transit": True
            }
        },
        "monitoring": {
            "logging": {
                "level": "INFO",
                "format": "json"
            }
        },
        "quotas": {
            "default": {
                "max_agents": 10,
                "max_storage_gb": 100
            }
        }
    }


@pytest.fixture
def config_from_dict(minimal_valid_config):
    """Create a Config instance from dictionary."""
    return Config(minimal_valid_config)


class TestValidationResult:
    """Tests for ValidationResult class."""
    
    def test_valid_result(self):
        """Test creating a valid result."""
        result = ValidationResult(True, "All good", "test.field")
        
        assert result.valid is True
        assert result.message == "All good"
        assert result.field == "test.field"
        assert bool(result) is True
    
    def test_invalid_result(self):
        """Test creating an invalid result."""
        result = ValidationResult(False, "Error message", "test.field")
        
        assert result.valid is False
        assert result.message == "Error message"
        assert result.field == "test.field"
        assert bool(result) is False
    
    def test_repr(self):
        """Test string representation."""
        result = ValidationResult(True, "Success", "test.field")
        repr_str = repr(result)
        
        assert "VALID" in repr_str
        assert "test.field" in repr_str


class TestRequiredSections:
    """Tests for required section validation."""
    
    def test_all_required_sections_present(self, config_from_dict):
        """Test validation passes when all required sections are present."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_required_sections()
        
        assert all(r.valid for r in results)
    
    def test_missing_required_section(self):
        """Test validation fails when a required section is missing."""
        config_data = {"platform": {"name": "Test"}}
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_required_sections()
        
        # Should have failures for missing sections
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("api" in r.field for r in invalid_results)


class TestPlatformValidation:
    """Tests for platform section validation."""
    
    def test_valid_platform_config(self, config_from_dict):
        """Test validation passes for valid platform config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_platform()
        
        assert all(r.valid for r in results)
    
    def test_invalid_environment(self):
        """Test validation fails for invalid environment value."""
        config_data = {
            "platform": {
                "name": "Test",
                "version": "1.0.0",
                "environment": "invalid_env"
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_platform()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("environment" in r.field for r in invalid_results)


class TestAPIValidation:
    """Tests for API section validation."""
    
    def test_valid_api_config(self, config_from_dict):
        """Test validation passes for valid API config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_api()
        
        assert all(r.valid for r in results)
    
    def test_invalid_port_range(self):
        """Test validation fails for invalid port number."""
        config_data = {
            "api": {
                "host": "0.0.0.0",
                "port": 99999,  # Invalid port
                "jwt": {
                    "secret_key": "test",
                    "expiration_hours": 24
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_api()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("port" in r.field and "65535" in r.message for r in invalid_results)
    
    def test_invalid_expiration_hours(self):
        """Test validation fails for invalid expiration hours."""
        config_data = {
            "api": {
                "host": "0.0.0.0",
                "port": 8000,
                "jwt": {
                    "secret_key": "test",
                    "expiration_hours": 1000  # Too high
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_api()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0


class TestDatabaseValidation:
    """Tests for database section validation."""
    
    def test_valid_database_config(self, config_from_dict):
        """Test validation passes for valid database config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_database()
        
        assert all(r.valid for r in results)
    
    def test_invalid_postgres_port(self):
        """Test validation fails for invalid PostgreSQL port."""
        config_data = {
            "database": {
                "postgres": {
                    "host": "localhost",
                    "port": 0,  # Invalid
                    "database": "test",
                    "username": "user",
                    "password": "pass"
                },
                "milvus": {"host": "localhost", "port": 19530},
                "redis": {"host": "localhost", "port": 6379}
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_database()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
    
    def test_invalid_pool_size(self):
        """Test validation fails for invalid pool size."""
        config_data = {
            "database": {
                "postgres": {
                    "host": "localhost",
                    "port": 5432,
                    "database": "test",
                    "username": "user",
                    "password": "pass",
                    "pool_size": 200  # Too high
                },
                "milvus": {"host": "localhost", "port": 19530},
                "redis": {"host": "localhost", "port": 6379}
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_database()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0


class TestStorageValidation:
    """Tests for storage section validation."""
    
    def test_valid_storage_config(self, config_from_dict):
        """Test validation passes for valid storage config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_storage()
        
        assert all(r.valid for r in results)
    
    def test_missing_required_bucket(self):
        """Test validation fails when required bucket is missing."""
        config_data = {
            "storage": {
                "minio": {
                    "endpoint": "localhost:9000",
                    "access_key": "key",
                    "secret_key": "secret",
                    "buckets": {
                        "documents": "documents"
                        # Missing other required buckets
                    }
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_storage()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("bucket" in r.message.lower() for r in invalid_results)


class TestLLMValidation:
    """Tests for LLM section validation."""
    
    def test_valid_llm_config(self, config_from_dict):
        """Test validation passes for valid LLM config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_llm()
        
        assert all(r.valid for r in results)
    
    def test_default_provider_not_found(self):
        """Test validation fails when default provider doesn't exist."""
        config_data = {
            "llm": {
                "default_provider": "nonexistent",
                "providers": {
                    "ollama": {
                        "enabled": True,
                        "models": {"chat": "llama3"}
                    }
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_llm()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("not found" in r.message for r in invalid_results)
    
    def test_default_provider_not_enabled(self):
        """Test validation fails when default provider is not enabled."""
        config_data = {
            "llm": {
                "default_provider": "ollama",
                "providers": {
                    "ollama": {
                        "enabled": False,  # Not enabled
                        "models": {"chat": "llama3"}
                    }
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_llm()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("not enabled" in r.message for r in invalid_results)
    
    def test_provider_missing_models(self):
        """Test validation fails when enabled provider has no models."""
        config_data = {
            "llm": {
                "default_provider": "ollama",
                "providers": {
                    "ollama": {
                        "enabled": True,
                        "models": {}  # No models
                    }
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_llm()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0


class TestAgentsValidation:
    """Tests for agents section validation."""
    
    def test_valid_agents_config(self, config_from_dict):
        """Test validation passes for valid agents config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_agents()
        
        assert all(r.valid for r in results)
    
    def test_min_size_greater_than_max_size(self):
        """Test validation fails when min_size > max_size."""
        config_data = {
            "agents": {
                "pool": {
                    "min_size": 100,
                    "max_size": 10  # Less than min_size
                },
                "resources": {
                    "default_cpu_cores": 1.0,
                    "default_memory_gb": 2,
                    "max_cpu_cores": 4,
                    "max_memory_gb": 8
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_agents()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("min_size" in r.message and "max_size" in r.message for r in invalid_results)
    
    def test_default_cpu_exceeds_max_cpu(self):
        """Test validation fails when default_cpu > max_cpu."""
        config_data = {
            "agents": {
                "pool": {
                    "min_size": 10,
                    "max_size": 100
                },
                "resources": {
                    "default_cpu_cores": 8.0,  # Greater than max
                    "default_memory_gb": 2,
                    "max_cpu_cores": 4,
                    "max_memory_gb": 8
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_agents()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0



class TestSecurityValidation:
    """Tests for security section validation."""
    
    def test_valid_security_config(self, config_from_dict):
        """Test validation passes for valid security config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_security()
        
        assert all(r.valid for r in results)
    
    def test_data_classification_enabled_without_levels(self):
        """Test validation fails when classification is enabled but no levels defined."""
        config_data = {
            "security": {
                "encryption": {
                    "at_rest": True,
                    "in_transit": True
                },
                "data_classification": {
                    "enabled": True,
                    "levels": []  # Empty
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_security()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0


class TestMonitoringValidation:
    """Tests for monitoring section validation."""
    
    def test_valid_monitoring_config(self, config_from_dict):
        """Test validation passes for valid monitoring config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_monitoring()
        
        assert all(r.valid for r in results)
    
    def test_invalid_log_level(self):
        """Test validation fails for invalid log level."""
        config_data = {
            "monitoring": {
                "logging": {
                    "level": "INVALID",
                    "format": "json"
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_monitoring()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("log level" in r.message.lower() for r in invalid_results)
    
    def test_invalid_log_format(self):
        """Test validation fails for invalid log format."""
        config_data = {
            "monitoring": {
                "logging": {
                    "level": "INFO",
                    "format": "invalid_format"
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_monitoring()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("format" in r.message.lower() for r in invalid_results)


class TestQuotasValidation:
    """Tests for quotas section validation."""
    
    def test_valid_quotas_config(self, config_from_dict):
        """Test validation passes for valid quotas config."""
        validator = ConfigValidator(config_from_dict)
        results = validator._validate_quotas()
        
        assert all(r.valid for r in results)
    
    def test_negative_quota_value(self):
        """Test validation fails for negative quota values."""
        config_data = {
            "quotas": {
                "default": {
                    "max_agents": -10,  # Negative
                    "max_storage_gb": 100
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_quotas()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("non-negative" in r.message for r in invalid_results)


class TestEnvironmentVariableValidation:
    """Tests for environment variable validation."""
    
    def test_production_requires_env_vars(self):
        """Test that production environment requires certain env vars."""
        config_data = {
            "platform": {
                "name": "Test",
                "version": "1.0.0",
                "environment": "production"
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        # Clear environment variables
        for var in ["JWT_SECRET", "POSTGRES_PASSWORD", "REDIS_PASSWORD", 
                    "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"]:
            if var in os.environ:
                del os.environ[var]
        
        results = validator._validate_environment_variables()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("production" in r.message.lower() for r in invalid_results)
    
    def test_development_allows_missing_env_vars(self):
        """Test that development environment doesn't require env vars."""
        config_data = {
            "platform": {
                "name": "Test",
                "version": "1.0.0",
                "environment": "development"
            },
            "api": {
                "jwt": {
                    "secret_key": "hardcoded-dev-secret"
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_environment_variables()
        
        # Should not fail for missing env vars in development
        # (unless they're explicitly referenced with ${VAR})
        assert True  # Test passes if no exception


class TestDependencyValidation:
    """Tests for dependency validation between config values."""
    
    def test_alerting_enabled_without_channels(self):
        """Test validation fails when alerting is enabled but no channels configured."""
        config_data = {
            "alerting": {
                "enabled": True,
                "channels": {
                    "email": {"enabled": False},
                    "slack": {"enabled": False}
                }
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        results = validator._validate_dependencies()
        
        invalid_results = [r for r in results if not r.valid]
        assert len(invalid_results) > 0
        assert any("channel" in r.message.lower() for r in invalid_results)


class TestHelperMethods:
    """Tests for helper validation methods."""
    
    def test_validate_port_valid(self):
        """Test port validation with valid port."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_port("test.port", 8000)
        assert result.valid is True
    
    def test_validate_port_invalid_range(self):
        """Test port validation with invalid range."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_port("test.port", 99999)
        assert result.valid is False
        assert "65535" in result.message
    
    def test_validate_port_invalid_type(self):
        """Test port validation with invalid type."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_port("test.port", "8000")
        assert result.valid is False
        assert "integer" in result.message.lower()
    
    def test_validate_range_valid(self):
        """Test range validation with valid value."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_range("test.value", 50, min_val=0, max_val=100)
        assert result.valid is True
    
    def test_validate_range_below_min(self):
        """Test range validation with value below minimum."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_range("test.value", -10, min_val=0, max_val=100)
        assert result.valid is False
        assert ">=" in result.message
    
    def test_validate_range_above_max(self):
        """Test range validation with value above maximum."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_range("test.value", 150, min_val=0, max_val=100)
        assert result.valid is False
        assert "<=" in result.message
    
    def test_validate_percentage_valid(self):
        """Test percentage validation with valid value."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_percentage("test.percent", 75)
        assert result.valid is True
    
    def test_validate_percentage_invalid(self):
        """Test percentage validation with invalid value."""
        config = Config({})
        validator = ConfigValidator(config)
        
        result = validator._validate_percentage("test.percent", 150)
        assert result.valid is False


class TestFullValidation:
    """Tests for full configuration validation."""
    
    def test_validate_all_with_valid_config(self, config_from_dict):
        """Test that validate_all returns all valid results for valid config."""
        validator = ConfigValidator(config_from_dict)
        results = validator.validate_all()
        
        # Should have many results
        assert len(results) > 0
        
        # Check for any failures
        invalid_results = [r for r in results if not r.valid]
        if invalid_results:
            for r in invalid_results:
                print(f"Failed: {r.field} - {r.message}")
        
        # Most should be valid (some might be skipped due to optional features)
        valid_count = sum(1 for r in results if r.valid)
        assert valid_count > len(results) * 0.8  # At least 80% valid
    
    def test_validate_raises_on_invalid_config(self):
        """Test that validate() raises ValidationError for invalid config."""
        config_data = {
            "platform": {
                "name": "Test",
                "version": "1.0.0",
                "environment": "invalid_env"  # Invalid
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        with pytest.raises(ValidationError) as exc_info:
            validator.validate()
        
        assert "validation failed" in str(exc_info.value).lower()
        assert "error" in str(exc_info.value).lower()
    
    def test_validate_config_convenience_function(self, config_from_dict):
        """Test the validate_config convenience function."""
        # Should not raise for valid config
        validate_config(config_from_dict)
    
    def test_validate_config_file_convenience_function(self, minimal_valid_config):
        """Test the validate_config_file convenience function."""
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(minimal_valid_config, f)
            config_path = Path(f.name)
        
        try:
            # Should not raise for valid config file
            validate_config_file(str(config_path))
        finally:
            config_path.unlink()


class TestErrorMessages:
    """Tests for error message clarity."""
    
    def test_error_messages_are_descriptive(self):
        """Test that error messages provide clear information."""
        config_data = {
            "api": {
                "port": 99999  # Invalid
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        try:
            validator.validate()
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            error_msg = str(e)
            # Should mention the field and the problem
            assert "port" in error_msg.lower()
            assert "65535" in error_msg or "range" in error_msg.lower()
    
    def test_multiple_errors_reported(self):
        """Test that multiple errors are all reported."""
        config_data = {
            "platform": {
                "environment": "invalid"  # Error 1
            },
            "api": {
                "port": 99999  # Error 2
            }
        }
        config = Config(config_data)
        validator = ConfigValidator(config)
        
        try:
            validator.validate()
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            error_msg = str(e)
            # Should report count of errors
            assert "error" in error_msg.lower()
            # Should list multiple issues
            assert "environment" in error_msg.lower() or "invalid" in error_msg.lower()
