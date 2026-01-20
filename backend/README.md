# Digital Workforce Platform - Backend

Python backend services for the Digital Workforce Management Platform.

## Overview

The backend consists of multiple microservices that work together to provide AI agent management, task orchestration, and knowledge management capabilities.

### Architecture Components

- **API Gateway** (`api_gateway/`) - FastAPI-based REST API and WebSocket server
- **Task Manager** (`task_manager/`) - Hierarchical task decomposition and coordination
- **Agent Framework** (`agent_framework/`) - LangChain-based agent implementation
- **Memory System** (`memory_system/`) - Multi-tiered memory management (Agent, Company, User Context)
- **Knowledge Base** (`knowledge_base/`) - Document processing and knowledge retrieval
- **LLM Providers** (`llm_providers/`) - Integration with Ollama, vLLM, OpenAI, Anthropic
- **Access Control** (`access_control/`) - Authentication and authorization (RBAC/ABAC)
- **Skill Library** (`skill_library/`) - Reusable agent capabilities
- **Virtualization** (`virtualization/`) - Container-based agent isolation
- **Shared** (`shared/`) - Common utilities and models

## Technology Stack

- **Python**: 3.11+
- **Framework**: FastAPI
- **Agent Framework**: LangChain
- **Databases**: 
  - PostgreSQL (primary operational data)
  - Milvus (vector embeddings)
  - Redis (message bus)
- **Object Storage**: MinIO
- **LLM Providers**: Ollama (primary), vLLM, OpenAI, Anthropic

## Installation

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 16+
- Redis 7+
- Milvus 2.3+
- MinIO
- Docker (for containerized deployment)

### Option 1: Using pip

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install production dependencies
pip install -r requirements.txt

# Install development dependencies (optional)
pip install -r requirements-dev.txt

# Install package in editable mode
pip install -e .
```

### Option 2: Using Poetry

```bash
# Install Poetry if not already installed
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install

# Install with development dependencies
poetry install --with dev

# Activate virtual environment
poetry shell
```

## Configuration

### Environment Variables

Create a `.env` file in the backend directory:

```bash
# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=workforce_platform
POSTGRES_USER=platform_user
POSTGRES_PASSWORD=your_secure_password

# Milvus Configuration
MILVUS_HOST=localhost
MILVUS_PORT=19530

# MinIO Configuration
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=your_access_key
MINIO_SECRET_KEY=your_secret_key

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password

# JWT Configuration
JWT_SECRET=your_jwt_secret_key
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# LLM Configuration
OLLAMA_HOST=localhost
OLLAMA_PORT=11434

# Optional: Cloud LLM Providers
OPENAI_API_KEY=your_openai_key
ANTHROPIC_API_KEY=your_anthropic_key

# Application Configuration
ENVIRONMENT=development
LOG_LEVEL=INFO
API_HOST=0.0.0.0
API_PORT=8000
```

### Configuration File

The platform uses `config.yaml` for detailed configuration. See `config.yaml.example` for a complete template.

## Running the Services

### Development Mode

```bash
# Run API Gateway
uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000

# Run Task Manager Worker
python -m task_manager.worker

# Run Document Processor Worker
python -m knowledge_base.processor
```

### Production Mode

```bash
# Using Gunicorn with Uvicorn workers
gunicorn api_gateway.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile -
```

### Using Docker Compose

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

## Development

### Code Style

The project uses:
- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

```bash
# Format code
black .
isort .

# Lint code
flake8 .

# Type check
mypy .
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_api_gateway.py

# Run with verbose output
pytest -v
```

### Pre-commit Hooks

```bash
# Install pre-commit hooks
pre-commit install

# Run manually
pre-commit run --all-files
```

## Project Structure

```
backend/
├── api_gateway/          # FastAPI application
│   ├── main.py          # Application entry point
│   ├── routes/          # API route handlers
│   ├── middleware/      # Custom middleware
│   └── dependencies.py  # Dependency injection
├── task_manager/        # Task orchestration
│   ├── decomposer.py   # Goal decomposition
│   ├── coordinator.py  # Task coordination
│   └── aggregator.py   # Result aggregation
├── agent_framework/     # Agent implementation
│   ├── base_agent.py   # Base agent class
│   ├── templates/      # Agent templates
│   └── registry.py     # Agent registry
├── memory_system/       # Memory management
│   ├── agent_memory.py # Agent-specific memory
│   ├── company_memory.py # Shared memory
│   └── embeddings.py   # Embedding generation
├── knowledge_base/      # Document processing
│   ├── processor.py    # Document processor
│   ├── extractors/     # Text extractors
│   └── indexer.py      # Knowledge indexing
├── llm_providers/       # LLM integrations
│   ├── ollama.py       # Ollama client
│   ├── vllm.py         # vLLM client
│   └── router.py       # Provider routing
├── access_control/      # Authentication & authorization
│   ├── auth.py         # JWT authentication
│   ├── rbac.py         # Role-based access control
│   └── abac.py         # Attribute-based access control
├── skill_library/       # Reusable skills
│   ├── registry.py     # Skill registry
│   └── skills/         # Skill implementations
├── virtualization/      # Container management
│   ├── sandbox.py      # Code execution sandbox
│   └── docker_manager.py # Docker integration
├── shared/              # Shared utilities
│   ├── config.py       # Configuration loader
│   ├── database.py     # Database connections
│   ├── models.py       # Shared data models
│   └── utils.py        # Utility functions
├── tests/               # Test suite
│   ├── unit/           # Unit tests
│   ├── integration/    # Integration tests
│   └── e2e/            # End-to-end tests
├── requirements.txt     # Production dependencies
├── requirements-dev.txt # Development dependencies
├── pyproject.toml      # Poetry configuration
├── setup.py            # Package setup
└── README.md           # This file
```

## API Documentation

Once the API Gateway is running, access the interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "Description of changes"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1

# View migration history
alembic history
```

## Monitoring and Observability

### Metrics

Prometheus metrics are exposed at `/metrics` endpoint.

### Logging

Structured JSON logging is configured by default. Logs include:
- Request/response details
- Agent actions
- Task execution
- Error traces
- Audit events

### Tracing

Distributed tracing with OpenTelemetry and Jaeger integration.

## Security

### Best Practices

1. **Never commit secrets** - Use environment variables or secret management
2. **Keep dependencies updated** - Run `pip-audit` and `safety check` regularly
3. **Use HTTPS in production** - Configure TLS certificates
4. **Enable authentication** - JWT tokens required for all API endpoints
5. **Implement rate limiting** - Protect against abuse
6. **Validate inputs** - Use Pydantic models for validation
7. **Sanitize outputs** - Prevent injection attacks

### Security Scanning

```bash
# Check for known vulnerabilities
pip-audit

# Security linting
bandit -r .

# Dependency scanning
safety check
```

## Troubleshooting

### Common Issues

**Database Connection Errors**
```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Test connection
psql -h localhost -U platform_user -d workforce_platform
```

**Milvus Connection Errors**
```bash
# Check Milvus status
docker ps | grep milvus

# View Milvus logs
docker logs milvus-standalone
```

**Redis Connection Errors**
```bash
# Test Redis connection
redis-cli -h localhost -p 6379 ping
```

**Import Errors**
```bash
# Ensure package is installed in editable mode
pip install -e .

# Verify Python path
python -c "import sys; print(sys.path)"
```

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.

## License

MIT License - See [LICENSE](../LICENSE) for details.

## Support

For issues and questions:
- GitHub Issues: https://github.com/yourusername/digital-workforce-platform/issues
- Documentation: https://docs.digitalworkforce.com
- Email: support@digitalworkforce.com
