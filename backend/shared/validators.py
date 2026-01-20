"""
Configuration Validation Module

This module provides comprehensive configuration validation that runs on application startup.
It validates:
- Required configuration sections exist
- Data types for configuration values
- Value ranges (e.g., port numbers, percentages)
- Required environment variables are set
- Dependencies between configuration values
- Provides clear error messages for validation failures

References:
- Requirements 20: Configuration Management
- Design Section 16: Configuration Management
"""

import os
import re
from typing import Any, Dict, List, Optional, Tuple, Union, Callable
from pathlib import Path
import logging

from .config import Config, ConfigurationError


logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class ValidationResult:
    """Result of a validation check."""
    
    def __init__(self, valid: bool, message: str = "", field: str = ""):
        self.valid = valid
        self.message = message
        self.field = field
    
    def __bool__(self) -> bool:
        return self.valid
    
    def __repr__(self) -> str:
        status = "VALID" if self.valid else "INVALID"
        field_str = f" [{self.field}]" if self.field else ""
        msg_str = f": {self.message}" if self.message else ""
        return f"<ValidationResult {status}{field_str}{msg_str}>"


class ConfigValidator:
    """
    Comprehensive configuration validator.
    
    Validates the complete configuration structure including:
    - Required sections and fields
    - Data types
    - Value ranges
    - Environment variables
    - Dependencies between values
    
    Example:
        >>> validator = ConfigValidator(config)
        >>> validator.validate()  # Raises ValidationError if invalid
        >>> 
        >>> # Or check without raising
        >>> results = validator.validate_all()
        >>> if not all(results):
        >>>     for result in results:
        >>>         if not result:
        >>>             print(f"Error: {result.message}")
    """
    
    def __init__(self, config: Config):
        """
        Initialize validator with configuration.
        
        Args:
            config: Configuration instance to validate
        """
        self.config = config
        self.errors: List[ValidationResult] = []
    
    def validate(self) -> None:
        """
        Validate the complete configuration and raise exception if invalid.
        
        Raises:
            ValidationError: If any validation check fails
        """
        results = self.validate_all()
        
        invalid_results = [r for r in results if not r.valid]
        
        if invalid_results:
            error_messages = [f"  - {r.field}: {r.message}" for r in invalid_results]
            error_summary = "\n".join(error_messages)
            raise ValidationError(
                f"Configuration validation failed with {len(invalid_results)} error(s):\n"
                f"{error_summary}"
            )
        
        logger.info("Configuration validation passed successfully")
    
    def validate_all(self) -> List[ValidationResult]:
        """
        Run all validation checks and return results.
        
        Returns:
            List of ValidationResult objects
        """
        results = []
        
        # Validate required sections
        results.extend(self._validate_required_sections())
        
        # Validate platform section
        results.extend(self._validate_platform())
        
        # Validate API section
        results.extend(self._validate_api())
        
        # Validate database section
        results.extend(self._validate_database())
        
        # Validate storage section
        results.extend(self._validate_storage())
        
        # Validate LLM section
        results.extend(self._validate_llm())
        
        # Validate agents section
        results.extend(self._validate_agents())
        
        # Validate security section
        results.extend(self._validate_security())
        
        # Validate monitoring section
        results.extend(self._validate_monitoring())
        
        # Validate quotas section
        results.extend(self._validate_quotas())
        
        # Validate environment variables
        results.extend(self._validate_environment_variables())
        
        # Validate dependencies
        results.extend(self._validate_dependencies())
        
        return results

    def _validate_required_sections(self) -> List[ValidationResult]:
        """Validate that all required configuration sections exist."""
        results = []
        
        required_sections = [
            "platform",
            "api",
            "database",
            "storage",
            "llm",
            "agents",
            "security",
            "monitoring",
            "quotas"
        ]
        
        for section in required_sections:
            if not self.config.has(section):
                results.append(ValidationResult(
                    False,
                    f"Required section '{section}' is missing",
                    section
                ))
            else:
                results.append(ValidationResult(True, "", section))
        
        return results
    
    def _validate_platform(self) -> List[ValidationResult]:
        """Validate platform configuration section."""
        results = []
        
        # Required fields
        results.append(self._validate_required_field("platform.name", str))
        results.append(self._validate_required_field("platform.version", str))
        results.append(self._validate_required_field("platform.environment", str))
        
        # Validate environment value
        env = self.config.get("platform.environment")
        if env:
            valid_envs = ["development", "staging", "production"]
            if env not in valid_envs:
                results.append(ValidationResult(
                    False,
                    f"Invalid environment '{env}', must be one of: {', '.join(valid_envs)}",
                    "platform.environment"
                ))
            else:
                results.append(ValidationResult(True, "", "platform.environment"))
        
        return results
    
    def _validate_api(self) -> List[ValidationResult]:
        """Validate API configuration section."""
        results = []
        
        # Required fields
        results.append(self._validate_required_field("api.host", str))
        results.append(self._validate_required_field("api.port", int))
        
        # Validate port range
        port = self.config.get("api.port")
        if port is not None:
            results.append(self._validate_port("api.port", port))
        
        # Validate JWT configuration
        results.append(self._validate_required_field("api.jwt.secret_key", str))
        results.append(self._validate_required_field("api.jwt.expiration_hours", (int, float)))
        
        # Validate expiration hours range
        exp_hours = self.config.get("api.jwt.expiration_hours")
        if exp_hours is not None:
            results.append(self._validate_range(
                "api.jwt.expiration_hours",
                exp_hours,
                min_val=1,
                max_val=720  # 30 days
            ))
        
        # Validate rate limit if enabled
        if self.config.get("api.rate_limit.enabled", False):
            results.append(self._validate_required_field("api.rate_limit.requests_per_minute", int))
            results.append(self._validate_required_field("api.rate_limit.requests_per_hour", int))
        
        return results

    def _validate_database(self) -> List[ValidationResult]:
        """Validate database configuration section."""
        results = []
        
        # PostgreSQL validation
        results.append(self._validate_required_field("database.postgres.host", str))
        results.append(self._validate_required_field("database.postgres.port", int))
        results.append(self._validate_required_field("database.postgres.database", str))
        results.append(self._validate_required_field("database.postgres.username", str))
        results.append(self._validate_required_field("database.postgres.password", str))
        
        # Validate PostgreSQL port
        pg_port = self.config.get("database.postgres.port")
        if pg_port is not None:
            results.append(self._validate_port("database.postgres.port", pg_port))
        
        # Validate pool size
        pool_size = self.config.get("database.postgres.pool_size")
        if pool_size is not None:
            results.append(self._validate_range(
                "database.postgres.pool_size",
                pool_size,
                min_val=1,
                max_val=100
            ))
        
        # Milvus validation
        results.append(self._validate_required_field("database.milvus.host", str))
        results.append(self._validate_required_field("database.milvus.port", int))
        
        milvus_port = self.config.get("database.milvus.port")
        if milvus_port is not None:
            results.append(self._validate_port("database.milvus.port", milvus_port))
        
        # Redis validation
        results.append(self._validate_required_field("database.redis.host", str))
        results.append(self._validate_required_field("database.redis.port", int))
        
        redis_port = self.config.get("database.redis.port")
        if redis_port is not None:
            results.append(self._validate_port("database.redis.port", redis_port))
        
        return results
    
    def _validate_storage(self) -> List[ValidationResult]:
        """Validate storage configuration section."""
        results = []
        
        # MinIO validation
        results.append(self._validate_required_field("storage.minio.endpoint", str))
        results.append(self._validate_required_field("storage.minio.access_key", str))
        results.append(self._validate_required_field("storage.minio.secret_key", str))
        results.append(self._validate_required_field("storage.minio.buckets", dict))
        
        # Validate required buckets
        required_buckets = ["documents", "audio", "video", "images", "artifacts"]
        buckets = self.config.get("storage.minio.buckets", {})
        
        if isinstance(buckets, dict):
            for bucket in required_buckets:
                if bucket not in buckets:
                    results.append(ValidationResult(
                        False,
                        f"Required bucket '{bucket}' not configured",
                        f"storage.minio.buckets.{bucket}"
                    ))
                else:
                    results.append(ValidationResult(True, "", f"storage.minio.buckets.{bucket}"))
        
        return results

    def _validate_llm(self) -> List[ValidationResult]:
        """Validate LLM configuration section."""
        results = []
        
        # Required fields
        results.append(self._validate_required_field("llm.default_provider", str))
        results.append(self._validate_required_field("llm.providers", dict))
        
        # Validate default provider exists
        default_provider = self.config.get("llm.default_provider")
        providers = self.config.get("llm.providers", {})
        
        if default_provider and isinstance(providers, dict):
            if default_provider not in providers:
                results.append(ValidationResult(
                    False,
                    f"Default provider '{default_provider}' not found in providers",
                    "llm.default_provider"
                ))
            else:
                # Check if default provider is enabled
                provider_config = providers.get(default_provider, {})
                if not provider_config.get("enabled", False):
                    results.append(ValidationResult(
                        False,
                        f"Default provider '{default_provider}' is not enabled",
                        f"llm.providers.{default_provider}.enabled"
                    ))
                else:
                    results.append(ValidationResult(True, "", "llm.default_provider"))
        
        # Validate each enabled provider has required fields
        if isinstance(providers, dict):
            for provider_name, provider_config in providers.items():
                if provider_config.get("enabled", False):
                    # Check for required model types
                    models = provider_config.get("models", {})
                    if not models:
                        results.append(ValidationResult(
                            False,
                            f"Provider '{provider_name}' has no models configured",
                            f"llm.providers.{provider_name}.models"
                        ))
                    else:
                        results.append(ValidationResult(True, "", f"llm.providers.{provider_name}.models"))
        
        return results
    
    def _validate_agents(self) -> List[ValidationResult]:
        """Validate agents configuration section."""
        results = []
        
        # Pool configuration
        results.append(self._validate_required_field("agents.pool.min_size", int))
        results.append(self._validate_required_field("agents.pool.max_size", int))
        
        min_size = self.config.get("agents.pool.min_size")
        max_size = self.config.get("agents.pool.max_size")
        
        if min_size is not None and max_size is not None:
            if min_size > max_size:
                results.append(ValidationResult(
                    False,
                    f"min_size ({min_size}) cannot be greater than max_size ({max_size})",
                    "agents.pool"
                ))
            else:
                results.append(ValidationResult(True, "", "agents.pool"))
        
        # Resource limits
        results.append(self._validate_required_field("agents.resources.default_cpu_cores", (int, float)))
        results.append(self._validate_required_field("agents.resources.default_memory_gb", (int, float)))
        results.append(self._validate_required_field("agents.resources.max_cpu_cores", (int, float)))
        results.append(self._validate_required_field("agents.resources.max_memory_gb", (int, float)))
        
        # Validate resource ranges
        default_cpu = self.config.get("agents.resources.default_cpu_cores")
        max_cpu = self.config.get("agents.resources.max_cpu_cores")
        
        if default_cpu is not None and max_cpu is not None:
            if default_cpu > max_cpu:
                results.append(ValidationResult(
                    False,
                    f"default_cpu_cores ({default_cpu}) cannot exceed max_cpu_cores ({max_cpu})",
                    "agents.resources.default_cpu_cores"
                ))
            else:
                results.append(ValidationResult(True, "", "agents.resources.default_cpu_cores"))
        
        return results

    def _validate_security(self) -> List[ValidationResult]:
        """Validate security configuration section."""
        results = []
        
        # Encryption settings
        results.append(self._validate_required_field("security.encryption.at_rest", bool))
        results.append(self._validate_required_field("security.encryption.in_transit", bool))
        
        # Data classification
        if self.config.get("security.data_classification.enabled", False):
            results.append(self._validate_required_field("security.data_classification.levels", list))
            
            levels = self.config.get("security.data_classification.levels", [])
            if not isinstance(levels, list):
                results.append(ValidationResult(
                    False,
                    "data_classification.levels must be a list",
                    "security.data_classification.levels"
                ))
            elif isinstance(levels, list) and len(levels) == 0:
                results.append(ValidationResult(
                    False,
                    "data_classification.levels cannot be empty when enabled",
                    "security.data_classification.levels"
                ))
            else:
                results.append(ValidationResult(True, "", "security.data_classification.levels"))
        
        return results
    
    def _validate_monitoring(self) -> List[ValidationResult]:
        """Validate monitoring configuration section."""
        results = []
        
        # Logging configuration
        results.append(self._validate_required_field("monitoring.logging.level", str))
        results.append(self._validate_required_field("monitoring.logging.format", str))
        
        # Validate log level
        log_level = self.config.get("monitoring.logging.level")
        if log_level:
            valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
            if log_level.upper() not in valid_levels:
                results.append(ValidationResult(
                    False,
                    f"Invalid log level '{log_level}', must be one of: {', '.join(valid_levels)}",
                    "monitoring.logging.level"
                ))
            else:
                results.append(ValidationResult(True, "", "monitoring.logging.level"))
        
        # Validate log format
        log_format = self.config.get("monitoring.logging.format")
        if log_format:
            valid_formats = ["json", "text"]
            if log_format not in valid_formats:
                results.append(ValidationResult(
                    False,
                    f"Invalid log format '{log_format}', must be one of: {', '.join(valid_formats)}",
                    "monitoring.logging.format"
                ))
            else:
                results.append(ValidationResult(True, "", "monitoring.logging.format"))
        
        # Prometheus configuration
        if self.config.get("monitoring.prometheus.enabled", False):
            results.append(self._validate_required_field("monitoring.prometheus.port", int))
            
            prom_port = self.config.get("monitoring.prometheus.port")
            if prom_port is not None:
                results.append(self._validate_port("monitoring.prometheus.port", prom_port))
        
        return results
    
    def _validate_quotas(self) -> List[ValidationResult]:
        """Validate quotas configuration section."""
        results = []
        
        # Validate default quotas exist
        results.append(self._validate_required_field("quotas.default", dict))
        
        # Validate quota values are positive
        default_quotas = self.config.get("quotas.default", {})
        if isinstance(default_quotas, dict):
            for key, value in default_quotas.items():
                if isinstance(value, (int, float)) and value < 0:
                    results.append(ValidationResult(
                        False,
                        f"Quota value must be non-negative, got {value}",
                        f"quotas.default.{key}"
                    ))
                else:
                    results.append(ValidationResult(True, "", f"quotas.default.{key}"))
        
        return results

    def _validate_environment_variables(self) -> List[ValidationResult]:
        """Validate that required environment variables are set."""
        results = []
        
        # Get environment from config
        environment = self.config.get("platform.environment", "development")
        
        # Required environment variables for production
        if environment == "production":
            required_vars = [
                "JWT_SECRET",
                "POSTGRES_PASSWORD",
                "REDIS_PASSWORD",
                "MINIO_ACCESS_KEY",
                "MINIO_SECRET_KEY"
            ]
            
            for var in required_vars:
                if not os.environ.get(var):
                    results.append(ValidationResult(
                        False,
                        f"Required environment variable '{var}' is not set (production mode)",
                        f"env.{var}"
                    ))
                else:
                    results.append(ValidationResult(True, "", f"env.{var}"))
        
        # Check for environment variables referenced in config
        jwt_secret = self.config.get("api.jwt.secret_key", "")
        if "${JWT_SECRET}" in str(jwt_secret) and not os.environ.get("JWT_SECRET"):
            results.append(ValidationResult(
                False,
                "JWT_SECRET environment variable is referenced but not set",
                "env.JWT_SECRET"
            ))
        
        return results
    
    def _validate_dependencies(self) -> List[ValidationResult]:
        """Validate dependencies between configuration values."""
        results = []
        
        # If encryption at rest is enabled, check for encryption keys
        if self.config.get("security.encryption.at_rest", False):
            # This is a placeholder - actual key validation would depend on implementation
            results.append(ValidationResult(
                True,
                "Encryption at rest is enabled",
                "security.encryption.at_rest"
            ))
        
        # If TLS is enabled, check for certificate paths
        if self.config.get("security.encryption.in_transit", False):
            results.append(ValidationResult(
                True,
                "Encryption in transit is enabled",
                "security.encryption.in_transit"
            ))
        
        # If alerting is enabled, check for at least one channel
        if self.config.get("alerting.enabled", False):
            channels = self.config.get("alerting.channels", {})
            has_enabled_channel = False
            
            if isinstance(channels, dict):
                for channel_name, channel_config in channels.items():
                    if isinstance(channel_config, dict) and channel_config.get("enabled", False):
                        has_enabled_channel = True
                        break
            
            if not has_enabled_channel:
                results.append(ValidationResult(
                    False,
                    "Alerting is enabled but no alert channels are configured",
                    "alerting.channels"
                ))
            else:
                results.append(ValidationResult(True, "", "alerting.channels"))
        
        return results
    
    # Helper validation methods
    
    def _validate_required_field(
        self,
        field: str,
        expected_type: Union[type, Tuple[type, ...]]
    ) -> ValidationResult:
        """
        Validate that a required field exists and has the correct type.
        
        Args:
            field: Field path (dot notation)
            expected_type: Expected type or tuple of types
            
        Returns:
            ValidationResult
        """
        value = self.config.get(field)
        
        if value is None:
            return ValidationResult(
                False,
                f"Required field is missing",
                field
            )
        
        if not isinstance(value, expected_type):
            type_names = (
                expected_type.__name__ if isinstance(expected_type, type)
                else " or ".join(t.__name__ for t in expected_type)
            )
            return ValidationResult(
                False,
                f"Expected type {type_names}, got {type(value).__name__}",
                field
            )
        
        return ValidationResult(True, "", field)

    def _validate_port(self, field: str, port: int) -> ValidationResult:
        """
        Validate that a port number is in valid range.
        
        Args:
            field: Field path
            port: Port number to validate
            
        Returns:
            ValidationResult
        """
        if not isinstance(port, int):
            return ValidationResult(
                False,
                f"Port must be an integer, got {type(port).__name__}",
                field
            )
        
        if port < 1 or port > 65535:
            return ValidationResult(
                False,
                f"Port must be between 1 and 65535, got {port}",
                field
            )
        
        return ValidationResult(True, "", field)
    
    def _validate_range(
        self,
        field: str,
        value: Union[int, float],
        min_val: Optional[Union[int, float]] = None,
        max_val: Optional[Union[int, float]] = None
    ) -> ValidationResult:
        """
        Validate that a numeric value is within a specified range.
        
        Args:
            field: Field path
            value: Value to validate
            min_val: Minimum allowed value (inclusive)
            max_val: Maximum allowed value (inclusive)
            
        Returns:
            ValidationResult
        """
        if not isinstance(value, (int, float)):
            return ValidationResult(
                False,
                f"Value must be numeric, got {type(value).__name__}",
                field
            )
        
        if min_val is not None and value < min_val:
            return ValidationResult(
                False,
                f"Value must be >= {min_val}, got {value}",
                field
            )
        
        if max_val is not None and value > max_val:
            return ValidationResult(
                False,
                f"Value must be <= {max_val}, got {value}",
                field
            )
        
        return ValidationResult(True, "", field)
    
    def _validate_percentage(self, field: str, value: Union[int, float]) -> ValidationResult:
        """
        Validate that a value is a valid percentage (0-100).
        
        Args:
            field: Field path
            value: Value to validate
            
        Returns:
            ValidationResult
        """
        return self._validate_range(field, value, min_val=0, max_val=100)
    
    def _validate_url(self, field: str, url: str) -> ValidationResult:
        """
        Validate that a string is a valid URL.
        
        Args:
            field: Field path
            url: URL to validate
            
        Returns:
            ValidationResult
        """
        if not isinstance(url, str):
            return ValidationResult(
                False,
                f"URL must be a string, got {type(url).__name__}",
                field
            )
        
        # Basic URL validation
        url_pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
            r'localhost|'  # localhost
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # IP
            r'(?::\d+)?'  # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE
        )
        
        if not url_pattern.match(url):
            return ValidationResult(
                False,
                f"Invalid URL format: {url}",
                field
            )
        
        return ValidationResult(True, "", field)
    
    def _validate_path(self, field: str, path: str, must_exist: bool = False) -> ValidationResult:
        """
        Validate that a string is a valid file path.
        
        Args:
            field: Field path
            path: File path to validate
            must_exist: If True, check that the path exists
            
        Returns:
            ValidationResult
        """
        if not isinstance(path, str):
            return ValidationResult(
                False,
                f"Path must be a string, got {type(path).__name__}",
                field
            )
        
        if must_exist:
            path_obj = Path(path)
            if not path_obj.exists():
                return ValidationResult(
                    False,
                    f"Path does not exist: {path}",
                    field
                )
        
        return ValidationResult(True, "", field)


def validate_config(config: Config) -> None:
    """
    Validate configuration and raise exception if invalid.
    
    This is a convenience function that creates a ConfigValidator
    and runs validation.
    
    Args:
        config: Configuration instance to validate
        
    Raises:
        ValidationError: If validation fails
        
    Example:
        >>> from shared.config import get_config
        >>> from shared.validators import validate_config
        >>> 
        >>> config = get_config()
        >>> validate_config(config)  # Raises ValidationError if invalid
    """
    validator = ConfigValidator(config)
    validator.validate()


def validate_config_file(config_path: str = "config.yaml") -> None:
    """
    Load and validate a configuration file.
    
    Args:
        config_path: Path to configuration file
        
    Raises:
        ConfigurationError: If configuration cannot be loaded
        ValidationError: If validation fails
        
    Example:
        >>> from shared.validators import validate_config_file
        >>> validate_config_file("config.yaml")
    """
    from .config import Config
    
    config = Config.load(config_path)
    validate_config(config)
