# Project Structure

## Directory Organization

```
LinX/
├── backend/                    # Python backend services
├── frontend/                   # React frontend (placeholder)
├── infrastructure/             # Docker, Kubernetes, deployment
├── docs/                       # Documentation
├── examples-of-reference/      # Reference implementations
├── .kiro/                      # Kiro AI specifications
│   ├── specs/                  # Feature specifications
│   └── steering/               # Steering rules (this file)
├── docker-compose.yml          # Development services
└── .env.example                # Environment template
```

## Backend Structure

```
backend/
├── api_gateway/          # FastAPI REST API and WebSocket server
├── task_manager/         # Task decomposition and coordination
├── agent_framework/      # LangChain-based agent implementation
├── memory_system/        # Multi-tiered memory (Milvus integration)
├── knowledge_base/       # Document processing and retrieval
├── llm_providers/        # LLM provider integrations
├── access_control/       # Authentication and authorization (RBAC/ABAC)
├── skill_library/        # Reusable agent capabilities
├── virtualization/       # Container and sandbox management
├── message_bus/          # Redis-based message bus (Pub/Sub, Streams)
├── database/             # PostgreSQL models and connection pooling
├── object_storage/       # MinIO client and file metadata
├── shared/               # Common utilities (config, logging, validators)
├── tests/                # Test suite
├── docs/                 # Backend-specific documentation
├── alembic/              # Database migrations
├── config.yaml           # Configuration file
├── requirements.txt      # Production dependencies
└── pyproject.toml        # Poetry configuration
```

## Module Organization

Each backend module follows this pattern:
- `__init__.py` - Module exports
- Core implementation files (e.g., `connection.py`, `models.py`)
- `test_*.py` - Unit and integration tests
- `README.md` - Module documentation
- `IMPLEMENTATION_SUMMARY.md` - Implementation notes (if applicable)

## Coding Conventions

### File Naming
- Python files: `snake_case.py`
- Test files: `test_*.py` or `*_test.py`
- Configuration: `config.yaml`, `.env`

### Code Style
- **Line Length**: 100 characters (Black default)
- **Imports**: Sorted with isort (Black profile)
- **Type Hints**: Required for all function signatures
- **Docstrings**: Google style for modules, classes, and functions

### Module Structure
```python
"""Module docstring with description and references.

References:
- Requirements X.Y: Description
- Design Section Z: Description
"""

import standard_library
import third_party
from local_module import something

logger = logging.getLogger(__name__)

# Constants
CONSTANT_NAME = "value"

# Classes and functions
class MyClass:
    """Class docstring."""
    pass

def my_function() -> ReturnType:
    """Function docstring."""
    pass
```

### Configuration Access
```python
from shared.config import get_config

config = get_config()
value = config.get("section.key", default="fallback")
section = config.get_section("section")
```

### Logging
```python
from shared.logging import get_logger, LogContext

logger = get_logger(__name__)

# With correlation ID
with LogContext(correlation_id="req-123"):
    logger.info("Processing request")
```

### Database Access
```python
from database.connection import get_db_session
from database.models import User

with get_db_session() as session:
    users = session.query(User).all()
    session.commit()
```

### Error Handling
- Use specific exception types
- Log errors with context
- Provide meaningful error messages
- Clean up resources in finally blocks

### Testing
- Co-locate tests with source files when possible
- Use descriptive test names: `test_<function>_<scenario>_<expected>`
- Use fixtures for common setup
- Mock external dependencies
- Aim for high coverage of critical paths

## Documentation

- **Inline Comments**: Explain why, not what
- **Docstrings**: Required for all public APIs
- **README.md**: In each major module
- **Type Hints**: Serve as inline documentation
- **References**: Link to requirements and design docs

## Common Patterns

### Singleton Pattern
```python
_instance = None

def get_instance():
    global _instance
    if _instance is None:
        _instance = MyClass()
    return _instance
```

### Context Managers
```python
@contextmanager
def my_resource():
    resource = acquire()
    try:
        yield resource
    finally:
        release(resource)
```

### Configuration with Environment Variables
```yaml
# config.yaml
database:
  host: ${DB_HOST}
  password: ${DB_PASSWORD}
```

### Structured Logging
```python
logger.info(
    "Event occurred",
    extra={
        'event_type': 'my_event',
        'user_id': user_id,
        'custom_field': value
    }
)
```
