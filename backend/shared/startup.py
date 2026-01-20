"""
Application Startup Module

This module provides utilities for application startup including:
- Configuration validation
- Environment setup
- Dependency checks
- Logging initialization

References:
- Requirements 20: Configuration Management
- Design Section 16: Configuration Management
"""

import sys
import logging
from pathlib import Path
from typing import Optional

from .config import Config, ConfigurationError, get_config
from .validators import validate_config, ValidationError
from .logging import setup_logging, get_logger


# Use basic logger until logging is properly configured
logger = logging.getLogger(__name__)


def validate_startup_config(config_path: str = "config.yaml") -> Config:
    """
    Load and validate configuration on application startup.
    
    This function:
    1. Loads the configuration file
    2. Validates all configuration sections
    3. Checks required environment variables
    4. Validates dependencies between values
    5. Provides clear error messages if validation fails
    
    Args:
        config_path: Path to configuration file (default: "config.yaml")
        
    Returns:
        Validated Config instance
        
    Raises:
        SystemExit: If configuration is invalid (exits with code 1)
        
    Example:
        >>> from shared.startup import validate_startup_config
        >>> 
        >>> # In your main application startup
        >>> config = validate_startup_config("config.yaml")
        >>> # Configuration is now validated and ready to use
    """
    try:
        # Load configuration
        logger.info(f"Loading configuration from {config_path}")
        config = Config.load(config_path)
        
        # Validate configuration
        logger.info("Validating configuration...")
        validate_config(config)
        
        logger.info("✓ Configuration validation passed successfully")
        return config
        
    except ConfigurationError as e:
        logger.error(f"Configuration loading failed: {e}")
        print(f"\n❌ Configuration Error:\n{e}\n", file=sys.stderr)
        sys.exit(1)
        
    except ValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        print(f"\n❌ Configuration Validation Failed:\n{e}\n", file=sys.stderr)
        print("Please check your config.yaml file and ensure all required fields are present", 
              file=sys.stderr)
        print("and have valid values.\n", file=sys.stderr)
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Unexpected error during startup: {e}", exc_info=True)
        print(f"\n❌ Unexpected Error:\n{e}\n", file=sys.stderr)
        sys.exit(1)


def check_config_file_exists(config_path: str = "config.yaml") -> bool:
    """
    Check if configuration file exists.
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        True if file exists, False otherwise
    """
    return Path(config_path).exists()


def print_startup_banner(config: Config) -> None:
    """
    Print a startup banner with platform information.
    
    Args:
        config: Validated configuration instance
    """
    platform_name = config.get("platform.name", "Digital Workforce Platform")
    platform_version = config.get("platform.version", "unknown")
    environment = config.get("platform.environment", "unknown")
    
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║  {platform_name:^58}  ║
║  Version: {platform_version:^50}  ║
║  Environment: {environment:^46}  ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""
    print(banner)
    
    # Print key configuration info
    api_host = config.get("api.host", "0.0.0.0")
    api_port = config.get("api.port", 8000)
    print(f"API Server: http://{api_host}:{api_port}")
    
    default_provider = config.get("llm.default_provider", "unknown")
    print(f"LLM Provider: {default_provider}")
    
    print()


def initialize_logging(config: Config) -> None:
    """
    Initialize logging based on configuration.
    
    This function sets up the structured JSON logging system with:
    - JSON formatting for machine parsing
    - Correlation ID tracking
    - Component-specific log levels
    - File and stdout output
    - Log rotation
    
    Args:
        config: Configuration instance
        
    Example:
        >>> from shared.config import Config
        >>> from shared.startup import initialize_logging
        >>> 
        >>> config = Config.load("config.yaml")
        >>> initialize_logging(config)
    """
    # Set up structured logging
    setup_logging(config)
    
    # Get a new logger instance after setup
    logger = get_logger(__name__)
    
    log_level = config.get("monitoring.logging.level", "INFO")
    log_format = config.get("monitoring.logging.format", "json")
    log_output = config.get("monitoring.logging.output", "stdout")
    
    logger.info(
        "Logging system initialized",
        extra={
            'log_level': log_level,
            'log_format': log_format,
            'log_output': log_output
        }
    )


def startup_checks(config: Optional[Config] = None) -> Config:
    """
    Perform all startup checks and initialization.
    
    This is the main entry point for application startup. It:
    1. Validates configuration
    2. Initializes logging
    3. Prints startup banner
    4. Returns validated config
    
    Args:
        config: Optional pre-loaded config (if None, loads from config.yaml)
        
    Returns:
        Validated Config instance
        
    Example:
        >>> from shared.startup import startup_checks
        >>> 
        >>> # In your main.py or app.py
        >>> def main():
        >>>     config = startup_checks()
        >>>     # Your application code here
        >>>     
        >>> if __name__ == "__main__":
        >>>     main()
    """
    # Load and validate config if not provided
    if config is None:
        config = validate_startup_config()
    
    # Initialize logging
    initialize_logging(config)
    
    # Print startup banner
    print_startup_banner(config)
    
    return config


if __name__ == "__main__":
    """
    Run startup validation from command line.
    
    Usage:
        python -m shared.startup [config_path]
    """
    import sys
    
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    
    print(f"Validating configuration: {config_path}\n")
    
    try:
        config = validate_startup_config(config_path)
        print("\n✓ Configuration is valid!")
        print(f"\nPlatform: {config.get('platform.name')}")
        print(f"Version: {config.get('platform.version')}")
        print(f"Environment: {config.get('platform.environment')}")
        
    except SystemExit:
        # Already handled by validate_startup_config
        pass
