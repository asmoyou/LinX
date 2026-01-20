# Technology Stack

## Backend

- **Language**: Python 3.11+
- **Framework**: FastAPI for REST API and WebSocket
- **Agent Framework**: LangChain for AI agent implementation
- **ORM**: SQLAlchemy with Alembic for migrations
- **Async**: asyncio, asyncpg, aiohttp

## Databases & Storage

- **PostgreSQL 16+**: Primary operational data
- **Milvus 2.3+**: Vector embeddings and semantic search
- **Redis 7+**: Message bus and caching
- **MinIO**: Object storage for documents and files

## LLM Providers

- **Ollama**: Primary local LLM provider
- **vLLM**: High-performance local provider
- **OpenAI/Anthropic**: Optional cloud fallback

## Key Libraries

- `langchain` - Agent framework
- `pymilvus` - Vector database client
- `minio` - Object storage client
- `redis` - Message bus client
- `pydantic` - Data validation
- `structlog` - Structured logging
- `prometheus-client` - Metrics
- `opentelemetry` - Distributed tracing
- `celery` - Task queue
- `python-jose` - JWT authentication
- `PyPDF2`, `python-docx`, `pytesseract` - Document processing

## Development Tools

- **Package Management**: pip or Poetry
- **Code Formatting**: Black (line length 100)
- **Import Sorting**: isort (Black profile)
- **Linting**: flake8
- **Type Checking**: mypy (strict mode)
- **Testing**: pytest with pytest-asyncio, pytest-cov
- **Pre-commit**: Configured with hooks

## Common Commands

### Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt
pip install -r backend/requirements-dev.txt  # Development only

# Or with Poetry
poetry install
poetry install --with dev
```

### Database
```bash
# Run migrations
cd backend
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"

# Rollback
alembic downgrade -1
```

### Development
```bash
# Start API server (development)
cd backend
uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000

# Start with Gunicorn (production)
gunicorn api_gateway.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Docker
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Restart specific service
docker-compose restart api

# Rebuild after changes
docker-compose up -d --build

# Stop all services
docker-compose down
```

### Testing
```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html --cov-report=term

# Run specific test file
pytest tests/test_api_gateway.py

# Run with verbose output
pytest -v
```

### Code Quality
```bash
cd backend

# Format code
black .
isort .

# Lint
flake8 .

# Type check
mypy .

# Security check
bandit -r .
pip-audit

# Run pre-commit hooks
pre-commit run --all-files
```

## Configuration

- **Environment Variables**: `.env` file in root and backend directories
- **Configuration File**: `backend/config.yaml` with environment variable substitution using `${VAR_NAME}` syntax
- **Secrets**: Never commit secrets; use environment variables or secret management
