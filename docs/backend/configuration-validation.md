# Configuration Validation

This document describes the configuration validation system implemented for LinX (灵枢).

## Overview

The configuration validation system provides comprehensive validation of the platform's configuration file (`config.yaml`) on application startup. It ensures that:

- All required configuration sections exist
- Configuration values have correct data types
- Numeric values are within valid ranges (e.g., port numbers, percentages)
- Required environment variables are set
- Dependencies between configuration values are satisfied
- Clear error messages are provided when validation fails

## Features

### 1. Required Section Validation

Validates that all required top-level configuration sections are present:
- `platform` - Platform metadata
- `api` - API Gateway configuration
- `database` - Database connections (PostgreSQL, Milvus, Redis)
- `storage` - Object storage (MinIO)
- `llm` - LLM provider configuration
- `agents` - Agent framework settings
- `security` - Security and encryption settings
- `monitoring` - Logging and monitoring
- `quotas` - Resource quotas

### 2. Data Type Validation

Ensures configuration values have the correct data types:
- Strings (e.g., hostnames, names)
- Integers (e.g., ports, pool sizes)
- Floats (e.g., CPU cores, memory)
- Booleans (e.g., feature flags)
- Lists (e.g., classification levels)
- Dictionaries (e.g., nested configurations)

### 3. Value Range Validation

Validates that numeric values are within acceptable ranges:
- **Port numbers**: 1-65535
- **Pool sizes**: 1-100
- **JWT expiration**: 1-720 hours (30 days)
- **Percentages**: 0-100
- **Resource limits**: Positive values, defaults ≤ maximums

### 4. Environment Variable Validation

Checks that required environment variables are set:
- **Production mode** requires:
  - `JWT_SECRET`
  - `POSTGRES_PASSWORD`
  - `REDIS_PASSWORD`
  - `MINIO_ACCESS_KEY`
  - `MINIO_SECRET_KEY`
- **Development mode** allows hardcoded values

### 5. Dependency Validation

Validates relationships between configuration values:
- Default LLM provider must exist and be enabled
- Enabled LLM providers must have models configured
- Agent pool min_size ≤ max_size
- Agent default resources ≤ max resources
- Alerting requires at least one enabled channel
- Data classification requires levels when enabled

### 6. Clear Error Messages

Provides detailed, actionable error messages:
```
❌ Configuration Validation Failed:
  - api.port: Port must be between 1 and 65535, got 99999
  - llm.default_provider: Default provider 'nonexistent' not found in providers
  - agents.pool: min_size (100) cannot be greater than max_size (10)
```

## Usage

### Basic Usage

```python
from shared.config import get_config
from shared.validators import validate_config

# Load and validate configuration
config = get_config("config.yaml")
validate_config(config)  # Raises ValidationError if invalid
```

### Startup Validation

The recommended way to use validation is through the startup module:

```python
from shared.startup import validate_startup_config

# In your main application startup
def main():
    # This loads, validates, and returns the config
    # Exits with code 1 if validation fails
    config = validate_startup_config("config.yaml")
    
    # Your application code here
    ...

if __name__ == "__main__":
    main()
```

## References

- **Requirements 20**: Configuration Management
- **Design Section 16**: Configuration Management
- **Implementation**: `backend/shared/validators.py`
- **Tests**: `backend/tests/test_validators.py`
- **Startup**: `backend/shared/startup.py`
