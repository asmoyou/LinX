# Structured JSON Logging System

## Overview

LinX (灵枢) uses a structured JSON logging system that provides:

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

## References

- Requirements 11: Monitoring and Observability
- Design Section 11.2: Logging Strategy
- Implementation: `backend/shared/logging.py`
