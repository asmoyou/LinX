# Developer Guide

This guide helps developers extend and customize LinX (灵枢).

## Table of Contents

1. [Development Setup](#development-setup)
2. [Project Structure](#project-structure)
3. [Creating Custom Agents](#creating-custom-agents)
4. [Adding New Skills](#adding-new-skills)
5. [Extending the API](#extending-the-api)
6. [Testing](#testing)
7. [Contributing](#contributing)

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker and Docker Compose
- Git

### Clone and Setup

```bash
# Clone repository
git clone https://github.com/your-org/linx.git
cd linx

# Backend setup
cd backend
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Frontend setup
cd ../frontend
npm install

# Start infrastructure
cd ..
docker-compose up -d
```

### Running in Development Mode

```bash
# Backend (with hot reload)
cd backend
source venv/bin/activate
uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (with hot reload)
cd frontend
npm run dev
```

## Project Structure

```
linx/
├── backend/              # Python backend
│   ├── api_gateway/      # REST API
│   ├── agent_framework/  # Agent system
│   ├── task_manager/     # Task orchestration
│   ├── memory_system/    # Memory management
│   ├── knowledge_base/   # Document processing
│   └── ...
├── frontend/             # React frontend
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── pages/        # Page components
│   │   ├── api/          # API client
│   │   └── stores/       # State management
│   └── ...
└── infrastructure/       # Deployment configs
```

## Creating Custom Agents

### 1. Define Agent Template

Create a new template in `backend/agent_framework/default_templates.py`:

```python
CUSTOM_AGENT_TEMPLATE = {
    "name": "Custom Agent",
    "description": "My custom agent",
    "skills": ["custom_skill_1", "custom_skill_2"],
    "system_prompt": "You are a custom agent that...",
    "config": {
        "temperature": 0.7,
        "max_tokens": 2000
    }
}
```

### 2. Register Template

```python
from agent_framework.agent_template import AgentTemplateManager

manager = AgentTemplateManager()
manager.register_template("custom_agent", CUSTOM_AGENT_TEMPLATE)
```

### 3. Create Agent Instance

```python
from agent_framework.base_agent import BaseAgent

agent = BaseAgent.from_template(
    template_id="custom_agent",
    name="My Custom Agent",
    user_id="user-123"
)
```

## Adding New Skills

### 1. Create Skill Class

Create `backend/skill_library/custom_skill.py`:

```python
from skill_library.skill_model import Skill, SkillParameter

class CustomSkill(Skill):
    def __init__(self):
        super().__init__(
            name="custom_skill",
            description="Performs custom operation",
            version="1.0.0",
            parameters=[
                SkillParameter(
                    name="input_data",
                    type="string",
                    required=True,
                    description="Input data to process"
                )
            ]
        )
    
    def execute(self, input_data: str, **kwargs) -> dict:
        """Execute the skill."""
        # Your custom logic here
        result = self.process_data(input_data)
        
        return {
            "success": True,
            "result": result
        }
    
    def process_data(self, data: str) -> str:
        """Custom processing logic."""
        return data.upper()
```

### 2. Register Skill

```python
from skill_library.skill_registry import SkillRegistry
from skill_library.custom_skill import CustomSkill

registry = SkillRegistry()
registry.register_skill(CustomSkill())
```

### 3. Use Skill in Agent

```python
agent.add_skill("custom_skill")
result = agent.execute_skill("custom_skill", input_data="hello")
```

## Extending the API

### 1. Create New Router

Create `backend/api_gateway/routers/custom.py`:

```python
from fastapi import APIRouter, Depends
from access_control.jwt_auth import get_current_user

router = APIRouter(prefix="/custom", tags=["custom"])

@router.get("/")
async def get_custom_data(current_user = Depends(get_current_user)):
    """Get custom data."""
    return {"message": "Custom endpoint"}

@router.post("/")
async def create_custom_data(
    data: dict,
    current_user = Depends(get_current_user)
):
    """Create custom data."""
    return {"created": True, "data": data}
```

### 2. Register Router

In `backend/api_gateway/main.py`:

```python
from api_gateway.routers import custom

app.include_router(custom.router, prefix="/api/v1")
```

## Testing

### Unit Tests

```python
# backend/tests/test_custom_skill.py
import pytest
from skill_library.custom_skill import CustomSkill

def test_custom_skill():
    skill = CustomSkill()
    result = skill.execute(input_data="hello")
    
    assert result["success"] is True
    assert result["result"] == "HELLO"
```

### Run Tests

```bash
cd backend
pytest tests/
pytest tests/test_custom_skill.py -v
pytest --cov=. --cov-report=html
```

### Integration Tests

```python
# backend/tests/integration/test_api.py
import pytest
from fastapi.testclient import TestClient
from api_gateway.main import app

client = TestClient(app)

def test_create_agent():
    response = client.post(
        "/api/v1/agents",
        json={"name": "Test Agent", "type": "data_analyst"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201
```

## Code Style

### Python

```bash
# Format code
black .
isort .

# Lint
flake8 .

# Type check
mypy .
```

### TypeScript

```bash
# Format code
npm run format

# Lint
npm run lint

# Type check
npm run type-check
```

## Contributing

### 1. Fork and Clone

```bash
git clone https://github.com/your-username/linx.git
cd linx
git remote add upstream https://github.com/your-org/linx.git
```

### 2. Create Branch

```bash
git checkout -b feature/my-feature
```

### 3. Make Changes

- Write code
- Add tests
- Update documentation

### 4. Commit

```bash
git add .
git commit -m "feat: add my feature"
```

### 5. Push and Create PR

```bash
git push origin feature/my-feature
```

Then create a Pull Request on GitHub.

## Best Practices

### Code Organization

- Keep functions small and focused
- Use type hints
- Write docstrings
- Follow SOLID principles

### Error Handling

```python
from api_gateway.errors import APIError

try:
    result = risky_operation()
except ValueError as e:
    raise APIError(
        code="INVALID_INPUT",
        message=str(e),
        status_code=400
    )
```

### Logging

```python
from shared.logging import get_logger

logger = get_logger(__name__)

logger.info("Operation started", extra={"user_id": user_id})
logger.error("Operation failed", extra={"error": str(e)})
```

### Configuration

```python
from shared.config import get_config

config = get_config()
api_key = config.get("external_api.key")
```

## Resources

- [API Documentation](../api/api-documentation.md)
- [Architecture Documentation](../architecture/system-architecture.md)
- [CI/CD Pipeline](./ci-cd-pipeline.md)
- [GitHub Repository](https://github.com/your-org/linx)

## Support

For development questions:
- GitHub Discussions
- Discord: https://discord.gg/linx
- Email: dev-support@example.com
