# Structured JSON Logging System

## Overview

The Digital Workforce Platform uses a structured JSON logging system that provides:

- **JSON Format**: Machine-parsable structured logs for easy integration with log aggregation systems
- **Correlation IDs**: Track requests across components and services
- **Component-Specific Levels**: Configure different log levels for different components
- **Context-Aware Logging**: Include user_id, agent_id, task_id, and other context in logs
- **File and Stdout Output**: Support for both console and file-based logging with rotation
- **Integration with Configuration**: Fully configurable via config.yaml

## Quick Start

### Basic Usage

```python
from shared.logging import setup_logging, get_logger
from shared.config import Config

# Load configuration and set up logging
config = Config.load("config.yaml")
setup_logging(config)

# Get a logger
logger = get_logger(__name__)

# Log messages
logger.info("Application started")
logger.warning("Resource usage high")
logger.error("Failed to connect to database")
```

### With Correlation ID

```python
from shared.logging import LogContext, get_logger

logger = get_logger(__name__)

# Use LogContext to set correlation ID for request tracking
with LogContext(correlation_id="req-12345"):
    logger.info("Processing request")
    # All logs within this context will include correlation_id="req-12345"
    logger.info("Request completed")
```

### With Context Fields

```python
from shared.logging import get_logger

# Create logger with context fields
logger = get_logger(__name__, user_id="user-123", agent_id="agent-456")

# All logs from this logger will include user_id and agent_id
logger.info("Agent started processing task")
```

## Configuration

Configure logging in `config.yaml`:

```yaml
monitoring:
  logging:
    level: "INFO"                    # Global log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    format: "json"                   # Format: json or text
    output: "stdout"                 # Output: stdout, file, or both
    
    # File output configuration
    file:
      path: "/var/log/workforce-platform"
      filename: "platform.log"
      max_size_mb: 100              # Max size before rotation
      max_files: 10                 # Number of rotated files to keep
      rotation: "daily"             # Rotation: daily or size
    
    # Include standard fields
    include_timestamp: true
    include_level: true
    include_caller: true
    include_correlation_id: true
    
    # Component-specific log levels
    components:
      api_gateway: "INFO"
      task_manager: "INFO"
      agent_framework: "INFO"
      memory_system: "INFO"
      llm_providers: "WARNING"
      database: "WARNING"
```

## Log Format

### JSON Structure

Each log entry is a JSON object with the following fields:

```json
{
  "timestamp": "2024-01-20T10:30:45.123456Z",
  "level": "INFO",
  "component": "api_gateway",
  "message": "API request received",
  "correlation_id": "req-12345",
  "caller": {
    "file": "/app/api_gateway/routes.py",
    "function": "handle_request",
    "line": 42
  },
  "user_id": "user-123",
  "agent_id": "agent-456",
  "task_id": "task-789"
}
```

### Standard Fields

- **timestamp**: ISO 8601 timestamp in UTC
- **level**: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **component**: Logger name (typically module name)
- **message**: Log message
- **correlation_id**: Request correlation ID for tracking
- **caller**: Information about where the log was generated
  - **file**: Source file path
  - **function**: Function name
  - **line**: Line number

### Context Fields

Additional fields can be included based on context:

- **user_id**: User identifier
- **agent_id**: Agent identifier
- **task_id**: Task identifier
- **event_type**: Type of event (api_request, task_event, agent_event, etc.)
- Custom fields via `extra` parameter

## Convenience Functions

The logging module provides convenience functions for common logging patterns:

### API Request Logging

```python
from shared.logging import log_api_request, get_logger

logger = get_logger(__name__)

log_api_request(
    logger,
    method="POST",
    path="/api/v1/tasks",
    user_id="user-123",
    status_code=201,
    duration_ms=150
)
```

### Task Event Logging

```python
from shared.logging import log_task_event, get_logger

logger = get_logger(__name__)

log_task_event(
    logger,
    event="started",
    task_id="task-789",
    agent_id="agent-456"
)
```

### Agent Event Logging

```python
from shared.logging import log_agent_event, get_logger

logger = get_logger(__name__)

log_agent_event(
    logger,
    event="created",
    agent_id="agent-456",
    agent_type="data_analyst"
)
```

### Security Event Logging

```python
from shared.logging import log_security_event, get_logger

logger = get_logger(__name__)

log_security_event(
    logger,
    event="unauthorized_access",
    user_id="user-123",
    severity="high",
    resource="/api/v1/admin"
)
```

### Error Logging

```python
from shared.logging import log_error, get_logger

logger = get_logger(__name__)

try:
    # Some operation
    process_data()
except Exception as e:
    log_error(
        logger,
        error=e,
        context="Processing user data",
        user_id="user-123"
    )
```

## Advanced Usage

### Structured Data Logging

Include additional structured data in logs:

```python
logger = get_logger(__name__)

logger.info(
    "Task execution completed",
    extra={
        'task_id': 'task-123',
        'duration_ms': 1500,
        'status': 'success',
        'result_size_bytes': 2048,
        'agent_id': 'agent-456'
    }
)
```

### Component-Specific Logging

Configure different log levels for different components:

```python
# In config.yaml
monitoring:
  logging:
    level: "WARNING"  # Global level
    components:
      api_gateway: "DEBUG"      # API Gateway logs at DEBUG
      task_manager: "INFO"      # Task Manager logs at INFO
      llm_providers: "WARNING"  # LLM Providers log at WARNING
```

```python
# In code
api_logger = get_logger("api_gateway")
api_logger.debug("This will be logged")  # Because api_gateway is set to DEBUG

task_logger = get_logger("task_manager")
task_logger.debug("This will NOT be logged")  # Because task_manager is set to INFO
```

### Nested Correlation IDs

Handle nested contexts with correlation IDs:

```python
from shared.logging import LogContext, get_logger

logger = get_logger(__name__)

with LogContext(correlation_id="req-12345"):
    logger.info("Processing main request")
    
    # Nested context with different correlation ID
    with LogContext(correlation_id="sub-req-67890"):
        logger.info("Processing sub-request")
    
    # Back to original correlation ID
    logger.info("Main request completed")
```

## Integration with Log Aggregation

### ELK Stack (Elasticsearch, Logstash, Kibana)

The JSON format is compatible with Logstash:

```conf
# logstash.conf
input {
  file {
    path => "/var/log/workforce-platform/platform.log"
    codec => json
  }
}

filter {
  # Add any additional processing
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "workforce-platform-%{+YYYY.MM.dd}"
  }
}
```

### Loki + Grafana

Use Promtail to ship logs to Loki:

```yaml
# promtail-config.yaml
clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: workforce-platform
    static_configs:
      - targets:
          - localhost
        labels:
          job: workforce-platform
          __path__: /var/log/workforce-platform/*.log
    pipeline_stages:
      - json:
          expressions:
            timestamp: timestamp
            level: level
            component: component
            correlation_id: correlation_id
```

## Best Practices

### 1. Use Appropriate Log Levels

- **DEBUG**: Detailed information for debugging (disabled in production)
- **INFO**: General informational messages about application flow
- **WARNING**: Warning messages for potentially harmful situations
- **ERROR**: Error messages for failures that don't stop the application
- **CRITICAL**: Critical errors that may cause application failure

### 2. Include Context

Always include relevant context in logs:

```python
# Good
logger.info(
    "Task completed",
    extra={
        'task_id': task_id,
        'duration_ms': duration,
        'status': 'success'
    }
)

# Bad
logger.info("Task completed")
```

### 3. Use Correlation IDs

Use correlation IDs to track requests across components:

```python
# In API Gateway
with LogContext(correlation_id=request_id):
    logger.info("Request received")
    result = process_request()
    logger.info("Request completed")
```

### 4. Don't Log Sensitive Data

Never log passwords, API keys, or other sensitive information:

```python
# Bad
logger.info(f"User logged in with password: {password}")

# Good
logger.info(f"User logged in", extra={'user_id': user_id})
```

### 5. Use Structured Logging

Prefer structured data over string formatting:

```python
# Good
logger.info("Task failed", extra={'task_id': task_id, 'error': str(error)})

# Less good
logger.info(f"Task {task_id} failed: {error}")
```

## Troubleshooting

### Logs Not Appearing

1. Check log level configuration
2. Verify component-specific log levels
3. Check file permissions for log directory
4. Verify logging is initialized: `setup_logging(config)`

### Log File Not Rotating

1. Check `max_size_mb` and `max_files` configuration
2. Verify write permissions on log directory
3. Check disk space

### Missing Correlation IDs

1. Ensure `LogContext` is used in request handlers
2. Verify `include_correlation_id: true` in config
3. Check that correlation ID is set before logging

## Testing

Run logging tests:

```bash
pytest tests/test_logging.py -v
```

Run the logging demo:

```bash
python examples/logging_demo.py
```

## References

- Requirements 11: Monitoring and Observability
- Design Section 11.2: Logging Strategy
- [python-json-logger Documentation](https://github.com/madzak/python-json-logger)
- [structlog Documentation](https://www.structlog.org/)
