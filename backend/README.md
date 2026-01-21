# Backend - LinX (灵枢)

Python backend services for LinX (灵枢) intelligent collaboration platform.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start API server
uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000
```

## Project Structure

```
backend/
├── access_control/      # Authentication & authorization (RBAC/ABAC)
├── agent_framework/     # LangChain-based agent implementation
├── api_gateway/         # FastAPI REST API and WebSocket server
├── database/            # PostgreSQL models and migrations
├── knowledge_base/      # Document processing and retrieval
├── llm_providers/       # LLM integrations (Ollama, vLLM, OpenAI, Anthropic)
├── memory_system/       # Multi-tiered memory (Milvus)
├── message_bus/         # Redis-based inter-agent communication
├── object_storage/      # MinIO client and file metadata
├── shared/              # Common utilities (config, logging, validators)
├── skill_library/       # Reusable agent capabilities
├── task_manager/        # Hierarchical task decomposition
├── virtualization/      # Container-based agent isolation
└── tests/               # Test suite
```

## Technology Stack

- **Python 3.11+** with FastAPI
- **LangChain** for agent framework
- **PostgreSQL** for operational data
- **Milvus** for vector embeddings
- **Redis** for message bus
- **MinIO** for object storage

## Development

```bash
# Run tests
pytest

# Format code
black . && isort .

# Type check
mypy .

# Lint
flake8 .
```

## Documentation

See the main project [README](../README.md) and [docs](../docs/) for detailed documentation.
