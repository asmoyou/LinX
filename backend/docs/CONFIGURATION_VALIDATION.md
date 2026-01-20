# Configuration Validation

This document describes the configuration validation system implemented for the Digital Workforce Platform.

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

### Full Startup Flow

For a complete startup with logging and banner:

```python
from shared.startup import startup_checks

def main():
    # Performs all startup checks:
    # 1. Loads and validates config
    # 2. Initializes logging
    # 3. Prints startup banner
    config = startup_checks()
    
    # Your application code here
    ...

if __name__ == "__main__":
    main()
```

### Command-Line Validation

You can validate a configuration file from the command line:

```bash
# Validate the default config.yaml
python -m shared.startup

# Validate a specific config file
python -m shared.startup path/to/config.yaml
```

Output:
```
Validating configuration: config.yaml

✓ Configuration is valid!

Platform: Digital Workforce Platform
Version: 1.0.0
Environment: development
```

### Programmatic Validation

For more control over validation:

```python
from shared.config import Config
from shared.validators import ConfigValidator

# Load config
config = Config.load("config.yaml")

# Create validator
validator = ConfigValidator(config)

# Get all validation results
results = validator.validate_all()

# Check for failures
invalid_results = [r for r in results if not r.valid]
if invalid_results:
    for result in invalid_results:
        print(f"Error in {result.field}: {result.message}")
```

## Validation Rules

### Platform Section

```yaml
platform:
  name: string (required)
  version: string (required)
  environment: string (required, must be: development, staging, production)
```

### API Section

```yaml
api:
  host: string (required)
  port: integer (required, 1-65535)
  jwt:
    secret_key: string (required)
    expiration_hours: number (required, 1-720)
  rate_limit:
    enabled: boolean
    requests_per_minute: integer (required if enabled)
    requests_per_hour: integer (required if enabled)
```

### Database Section

```yaml
database:
  postgres:
    host: string (required)
    port: integer (required, 1-65535)
    database: string (required)
    username: string (required)
    password: string (required)
    pool_size: integer (1-100)
  
  milvus:
    host: string (required)
    port: integer (required, 1-65535)
  
  redis:
    host: string (required)
    port: integer (required, 1-65535)
```

### Storage Section

```yaml
storage:
  minio:
    endpoint: string (required)
    access_key: string (required)
    secret_key: string (required)
    buckets: dict (required)
      documents: string (required)
      audio: string (required)
      video: string (required)
      images: string (required)
      artifacts: string (required)
```

### LLM Section

```yaml
llm:
  default_provider: string (required, must exist in providers)
  providers: dict (required)
    <provider_name>:
      enabled: boolean (default provider must be enabled)
      models: dict (required if enabled, must not be empty)
```

### Agents Section

```yaml
agents:
  pool:
    min_size: integer (required, must be ≤ max_size)
    max_size: integer (required, must be ≥ min_size)
  
  resources:
    default_cpu_cores: number (required, must be ≤ max_cpu_cores)
    default_memory_gb: number (required)
    max_cpu_cores: number (required, must be ≥ default_cpu_cores)
    max_memory_gb: number (required)
```

### Security Section

```yaml
security:
  encryption:
    at_rest: boolean (required)
    in_transit: boolean (required)
  
  data_classification:
    enabled: boolean
    levels: list (required if enabled, must not be empty)
```

### Monitoring Section

```yaml
monitoring:
  logging:
    level: string (required, must be: DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format: string (required, must be: json, text)
  
  prometheus:
    enabled: boolean
    port: integer (required if enabled, 1-65535)
```

### Quotas Section

```yaml
quotas:
  default: dict (required)
    # All quota values must be non-negative
    max_agents: integer (≥ 0)
    max_storage_gb: number (≥ 0)
```

## Custom Validation Rules

You can extend the validator with custom rules:

```python
from shared.validators import ConfigValidator, ValidationResult

class CustomValidator(ConfigValidator):
    def _validate_custom_section(self):
        """Add custom validation logic."""
        results = []
        
        # Your validation logic here
        value = self.config.get("custom.field")
        if value and value < 0:
            results.append(ValidationResult(
                False,
                "Custom field must be positive",
                "custom.field"
            ))
        else:
            results.append(ValidationResult(True, "", "custom.field"))
        
        return results
    
    def validate_all(self):
        """Override to include custom validation."""
        results = super().validate_all()
        results.extend(self._validate_custom_section())
        return results
```

## Testing

The validation system includes comprehensive tests:

```bash
# Run validation tests
pytest tests/test_validators.py -v

# Run startup tests
pytest tests/test_startup.py -v

# Run all tests
pytest tests/ -v
```

Test coverage:
- 46 validator tests
- 10 startup tests
- 95% overall code coverage

## Error Handling

### Validation Errors

When validation fails, a `ValidationError` is raised with details:

```python
try:
    validate_config(config)
except ValidationError as e:
    print(f"Validation failed: {e}")
    # Handle error appropriately
```

### Configuration Loading Errors

When configuration file cannot be loaded:

```python
try:
    config = Config.load("config.yaml")
except ConfigurationError as e:
    print(f"Failed to load config: {e}")
    # Handle error appropriately
```

## Best Practices

1. **Always validate on startup**: Use `validate_startup_config()` or `startup_checks()` in your application entry point

2. **Use environment variables for secrets**: Never hardcode secrets in production config files

3. **Test configuration changes**: Run validation before deploying configuration changes

4. **Provide clear defaults**: Use sensible defaults in development mode

5. **Document custom settings**: If you add custom configuration sections, document their validation rules

## References

- **Requirements 20**: Configuration Management
- **Design Section 16**: Configuration Management
- **Implementation**: `backend/shared/validators.py`
- **Tests**: `backend/tests/test_validators.py`
- **Startup**: `backend/shared/startup.py`

## See Also

- [Configuration Management](../CONFIG.md) - Configuration file structure and options
- [Environment Variables](../.env.example) - Required environment variables
- [Deployment Guide](DEPLOYMENT.md) - Production deployment configuration
