# CLAUDE.md

This file provides comprehensive guidance to Claude Code when working with this repository.

## Project Overview

LinX (灵枢) is an enterprise-grade intelligent collaboration platform for managing and coordinating AI agents and future robotic workers. The platform establishes a digital company structure enabling autonomous goal completion through hierarchical task management, collaborative agent coordination, and comprehensive knowledge management.

### Core Capabilities

- **Intelligent Agent Management**: LangChain-based AI agent framework with multiple agent types and templates
- **Hierarchical Task Management**: Automatic decomposition of high-level goals into executable tasks with dependency tracking
- **Multi-Tiered Memory System**: Agent Memory (private), Company Memory (shared), and User Context for seamless collaboration
- **Enterprise Knowledge Base**: Centralized document processing (PDF, DOCX, audio, video) with OCR and transcription
- **Privacy-First Architecture**: Local LLM deployment with complete data privacy using Ollama/vLLM
- **Secure Code Execution**: Multi-layer sandbox isolation (gVisor, Firecracker, Docker)

### Key Features

- Multi-provider LLM support (Ollama primary, vLLM, optional cloud fallback)
- Real-time task visualization via WebSocket
- Vector search with Milvus for semantic similarity
- RBAC and ABAC access control
- Comprehensive monitoring with Prometheus metrics and structured logging
- Containerized deployment with Docker and Kubernetes support

---

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI for REST API and WebSocket
- **Agent Framework**: LangChain/LangGraph 1.0 for AI agent implementation
- **ORM**: SQLAlchemy with Alembic for migrations
- **Async**: asyncio, asyncpg, aiohttp

### Databases & Storage
- **PostgreSQL 16+**: Primary operational data
- **Milvus 2.3+**: Vector embeddings and semantic search
- **Redis 7+**: Message bus and caching
- **MinIO**: Object storage for documents and files

### LLM Providers
- **Ollama**: Primary local LLM provider
- **vLLM**: High-performance local provider
- **OpenAI/Anthropic**: Optional cloud fallback

### Frontend
- **React 19** with TypeScript
- **Vite** for build tooling
- **Zustand** for state management
- **TailwindCSS** for styling

### Development Tools
- **Code Formatting**: Black (line length 100), isort (Black profile)
- **Linting**: flake8, ESLint
- **Type Checking**: mypy (strict mode), TypeScript
- **Testing**: pytest with pytest-asyncio, pytest-cov, Vitest
- **Pre-commit**: Configured with hooks

---

## Common Commands

### Backend (from `/backend`)

```bash
# Install dependencies
make install           # Production
make install-dev       # Development (includes pre-commit hooks)

# Run API server
make run              # uvicorn on port 8000 with reload

# Code quality
make format           # black + isort
make lint             # flake8 + pylint
make type-check       # mypy
make security-check   # bandit, safety, pip-audit

# Testing
make test             # pytest
make test-cov         # pytest with coverage

# Database
make migrate          # alembic upgrade head
make migrate-create   # interactive new migration

# All checks (CI)
make check-all

# Pre-commit workflow
make pre-commit-check  # format + lint + type-check + security + test
make quick-check       # format + lint + type-check (no tests)
```

### Frontend (from `/frontend`)

```bash
npm install           # Install dependencies
npm run dev           # Dev server on port 3000
npm run build         # Production build
npm run lint          # ESLint
npm run lint:fix      # Fix lint issues
npm run type-check    # TypeScript check
npm run format        # Prettier
npm test              # Run tests
npm run pre-commit    # All checks before commit
```

### Docker

```bash
docker-compose up -d              # Start all services
docker-compose logs -f            # View logs
docker-compose exec api python -m shared.database init  # Init DB
```

---

## Architecture

### Backend Structure

```
backend/
├── api_gateway/          # FastAPI REST + WebSocket endpoints
│   ├── main.py          # App initialization
│   └── routers/         # Route handlers (agents, tasks, skills, llm, auth)
├── agent_framework/      # LangGraph 1.0 agent system
│   ├── base_agent.py    # Agent base class with StateGraph
│   ├── agent_registry.py
│   └── tools/           # LangChain tools (bash, process, read_skill)
├── skill_library/        # Reusable agent capabilities
│   ├── skill_types.py   # SkillType enum (LANGCHAIN_TOOL, AGENT_SKILL)
│   ├── skill_executor.py
│   └── skill_loader.py
├── task_manager/         # Hierarchical task decomposition
├── memory_system/        # Multi-tiered memory (Agent/Company/User)
├── knowledge_base/       # Document processing and retrieval
├── llm_providers/        # LLM integrations (Ollama, vLLM, OpenAI, Anthropic)
├── access_control/       # JWT auth, RBAC/ABAC
├── virtualization/       # Container and sandbox management
├── database/            # SQLAlchemy models
├── shared/              # Common utilities and config
├── tests/               # Test suite (unit, integration, e2e)
└── alembic/             # Database migrations
```

### Frontend Structure

```
frontend/src/
├── api/                 # Axios client and service layer
│   └── client.ts       # Configured axios with auth interceptors
├── components/          # React components by domain
│   ├── skills/         # Skill management (V2 components)
│   ├── workforce/      # Agent management
│   └── tasks/          # Task components
├── pages/              # Page components (Dashboard, Workforce, Tasks, Skills, etc.)
├── stores/             # Zustand state stores
│   ├── authStore.ts    # Authentication state (persisted)
│   ├── agentStore.ts   # Agent state
│   ├── taskStore.ts    # Task state
│   └── skillStore.ts   # Skills state
├── hooks/              # Custom hooks (useWebSocket, useTranslation)
├── types/              # TypeScript type definitions
└── i18n/               # Internationalization
```

### Key Patterns

**Agent Framework**: Uses LangGraph 1.0 StateGraph API. Agents have isolated identity, skills from the Skill Library, and access to multi-tiered memory. Supports error recovery with multi-turn self-correction.

**Skill Types**:
- `LANGCHAIN_TOOL`: Simple @tool decorated functions, stored inline
- `AGENT_SKILL`: Complex multi-function skills, auto-detects inline vs MinIO storage

**Memory System**: Three layers - Agent Memory (private per agent), Company Memory (shared), User Context (per-user)

**State Management**: Zustand stores per domain, with localStorage persistence for auth. WebSocket integration for real-time updates.

**Configuration**: Backend uses `config.yaml` with environment variable substitution (`${VAR_NAME}`). Frontend uses Vite env vars (`VITE_*`).

---

## Coding Conventions

### File Naming
- Python files: `snake_case.py`
- Test files: `test_*.py` or `*_test.py`
- TypeScript/React: `PascalCase.tsx` for components, `camelCase.ts` for utilities
- Configuration: `config.yaml`, `.env`

### Code Style
- **Line Length**: 100 characters (Black default)
- **Imports**: Sorted with isort (Black profile)
- **Type Hints**: Required for all function signatures
- **Docstrings**: Google style for modules, classes, and functions

### Python Module Structure
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

---

## Documentation Management Rules

### Critical Principle

**NEVER** create documentation files inside code directories. All documentation must be centrally managed.

### Directory Structure

```
project-root/
├── backend/                    # Code only - NO documentation
├── frontend/                   # Code only - NO documentation
├── docs/                       # All documentation goes here
│   ├── api/                   # API documentation
│   ├── architecture/          # Architecture diagrams and docs
│   ├── backend/               # Backend-specific documentation
│   ├── deployment/            # Deployment guides
│   ├── developer/             # Developer guides
│   └── user-guide/            # User documentation
├── .kiro/specs/               # Feature specifications and tasks
│   └── feature-name/
│       ├── requirements.md
│       ├── design.md
│       └── tasks.md
└── CLAUDE.md                   # This file
```

### Forbidden Practices

- **DO NOT** create `IMPLEMENTATION_SUMMARY.md`, `TASKS_COMPLETED.md` in code directories
- **DO NOT** create individual README files in each module
- **DO NOT** create feature documentation in code folders
- **DO NOT** create `docs/` or `examples/` inside backend/ or frontend/

### Allowed Files in Code Directories

Each backend module should ONLY contain:
```
backend/module_name/
├── __init__.py              # Module exports
├── *.py                     # Python source files
└── test_*.py                # Test files (optional, prefer tests/)
```

---

## Task Management Rules

### Critical Workflow

**MANDATORY**: When completing ANY task from a spec's tasks.md file, follow this workflow:

#### 1. Before Starting a Task
- Read the spec's tasks.md file to understand the task requirements
- Read the spec's requirements.md and design.md for context
- Identify the specific task(s) you will be working on

#### 2. During Task Execution
- Implement the required functionality
- Write tests for the implementation
- Create documentation as needed (in `docs/`)

#### 3. After Completing a Task - CRITICAL STEP
**YOU MUST ALWAYS DO THIS - NO EXCEPTIONS:**

1. **Update tasks.md immediately** after completing implementation
2. Change task status from `- [ ]` to `- [x]` for completed tasks
3. Update ALL sub-tasks if the parent task is complete
4. **Commit the tasks.md update** along with your code changes

### Task Status Format

Tasks use markdown checkbox syntax:
- `- [ ]` = Not started (INCOMPLETE)
- `- [x]` = Completed (COMPLETE)
- `- [-]` = In progress
- `- [~]` = Queued

### Task File Locations

Spec task files are located at:
- `.kiro/specs/{spec-name}/tasks.md`

Always update the tasks.md file in the SAME spec directory as the work you're completing.

---

## Testing Rules

### Critical Principles

1. **ALWAYS write unit tests** - Every feature must have corresponding tests
2. **ALWAYS update tests when modifying features** - Tests must stay in sync with code
3. **Tests are NOT optional** - They are a required part of every implementation
4. **Minimum coverage**: 80% for all modules, 100% for critical paths

### Frontend API Client Rules

**NEVER** use raw fetch() or axios directly:

```typescript
// BAD - Direct fetch calls
const response = await fetch('/api/agents');

// GOOD - Use apiClient wrapper
import { apiClient } from '@/api/client';
const response = await apiClient.get('/agents');

// GOOD - Use typed API functions
import { agentApi } from '@/api/agents';
const agents = await agentApi.getAll();
```

### Test File Organization

```
backend/tests/                  # Backend tests
├── unit/                      # Unit tests
├── integration/               # Integration tests
└── e2e/                       # End-to-end tests

frontend/src/                   # Frontend tests (co-located)
├── components/
│   ├── AgentList.tsx
│   └── AgentList.test.tsx     # Co-located with component
```

### Running Tests

```bash
# Backend
cd backend
pytest --cov=. --cov-report=html --cov-report=term

# Frontend
cd frontend
npm test -- --coverage
```

---

## Pre-Commit Quality Control

### Critical Principle

**NEVER commit code that will fail CI/CD pipelines.** All code must pass quality checks locally before committing.

### Mandatory Workflow Before Every Commit

#### Backend
```bash
cd backend
make pre-commit-check  # Or run steps manually:
# 1. black . && isort .
# 2. flake8 .
# 3. mypy .
# 4. bandit -r . -ll && pip-audit
# 5. pytest --cov=.
```

#### Frontend
```bash
cd frontend
npm run pre-commit  # Or run steps manually:
# 1. npm run format
# 2. npm run lint
# 3. npm run type-check
# 4. npm test -- --run
# 5. npm run build
```

### Never Do This
- Skip pre-commit hooks: `git commit --no-verify`
- Commit with failing tests
- Ignore linting errors
- Commit with type errors
- Push without local verification

### Commit Message Format

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

Examples:
```bash
git commit -m "feat(auth): add JWT token refresh"
git commit -m "fix(api): resolve memory leak in websocket handler"
git commit -m "test(agents): add unit tests for agent lifecycle"
```

---

## Ongoing Development Specs

**IMPORTANT**: Before implementing any feature related to the specs below, you MUST:
1. Read the spec's `requirements.md` for user stories and acceptance criteria
2. Read the spec's `design.md` for technical architecture and implementation details
3. Read the spec's `tasks.md` to find the specific task to work on
4. After completing work, update `tasks.md` to mark tasks as complete

The following features are currently in development. Reference their specs for detailed requirements and tasks:

### Agent Error Recovery (58% complete)

Spec files:
- `.kiro/specs/agent-error-recovery/requirements.md` - User stories, functional requirements, success metrics
- `.kiro/specs/agent-error-recovery/design.md` - Architecture, data structures, algorithms, frontend integration
- `.kiro/specs/agent-error-recovery/tasks.md` - 85 tasks, 49 completed

Multi-turn self-correction system for agent tool call errors. Core implementation in `backend/agent_framework/base_agent.py`.

**Completed**: Core data structures, enhanced parsing, error feedback, tool execution recovery, main loop refactor, configuration, structured logging, frontend streaming integration

**Remaining**: Prometheus metrics (Phase 7.2), comprehensive tests (Phase 9), documentation (Phase 10), deployment (Phase 11)

### Code Execution Improvement (21% complete)

Spec files:
- `.kiro/specs/code-execution-improvement/requirements.md` - User stories for real execution, PTY, background processes
- `.kiro/specs/code-execution-improvement/design.md` - BashTool, SkillLoader, CodeValidator, DependencyManager architecture
- `.kiro/specs/code-execution-improvement/tasks.md` - 120 tasks, 25 completed

Enhanced bash tool, process management, and real skill execution. Core files:
- `backend/agent_framework/tools/bash_tool.py` - Enhanced bash with PTY
- `backend/agent_framework/tools/process_manager.py` - Background process management
- `backend/skill_library/skill_loader.py` - Real skill code extraction
- `backend/virtualization/` - Sandbox, container manager, dependency manager

**Completed**: Enhanced Bash Tool with PTY (Phase 1), Background Process Management (Phase 2), Skill Loader (Phase 3), Enhanced Sandbox (Phase 5)

**Remaining**: Code Validator (Phase 4), File Segmentation (Phase 6), Code Generation Optimization (Phase 7), Testing (Phase 8), Documentation (Phase 9), Deployment (Phase 10)

### Agent Skills Redesign (Template Complete)

Spec files:
- `.kiro/specs/agent-skills-redesign/requirements.md` - Skill type issues, Moltbot format requirements
- `.kiro/specs/agent-skills-redesign/design.md` - Agent Skills vs LangChain Tools architecture
- `.kiro/specs/agent-skills-redesign/tasks.md` - Template restructuring tasks
- `.kiro/specs/agent-skills-redesign/ANALYSIS.md` - Current analysis comparing Moltbot/Claude Code

Redesign of Agent Skills system. Key insight: Agent Skills = Instructions (SKILL.md) + Executable Code, not LangChain tools.

**Completed**: Template restructuring (Phase 0), analysis of Moltbot's 54 skills format

### Department Management (~80% complete)

Spec files:
- `.kiro/specs/department-management/requirements.md` - 5 user stories for department CRUD, assignment, and access control
- `.kiro/specs/department-management/design.md` - DB schema, API design, frontend architecture, migration strategy
- `.kiro/specs/department-management/tasks.md` - 8 phases, ~55 tasks

Enterprise department management system for organizing users, agents, and knowledge bases into departments with hierarchical support.

**Completed**: Department model with self-referencing FK (Phase 1), Alembic migrations with data migration (Phase 1), Full CRUD API with resource endpoints (Phase 2), ABAC/knowledge filter adaptation (Phase 3), Frontend infrastructure - types, API, store, DepartmentSelect (Phase 4), Department management page (Phase 5), Integration with Workforce/Knowledge/Profile pages (Phase 6), Backend + frontend tests (Phase 7), Tasks.md update (Phase 8)

**Remaining**: Backend API adaptations for existing endpoints (2.3), agent/knowledge list server-side filtering (3.3), additional test coverage, API documentation

### Digital Workforce Platform (Foundation Spec)

Spec files:
- `.kiro/specs/digital-workforce-platform/requirements.md` - Core platform requirements and glossary
- `.kiro/specs/digital-workforce-platform/design.md` - Comprehensive 133KB architecture document
- `.kiro/specs/digital-workforce-platform/tasks.md` - Full platform implementation tasks

Main platform specification covering agents, tasks, memory, knowledge base, and access control. This is the foundational spec for the entire LinX platform.

---

## API Documentation

When the backend is running:
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## Environment Setup

1. Copy `backend/config.yaml.example` to `backend/config.yaml`
2. Copy `.env.example` to `.env`
3. Required services: PostgreSQL, Milvus, Redis, MinIO
4. For local LLM: Install and run Ollama (`ollama run llama3:8b`)

---

## Quick Reference Checklist

Before committing ANY code:

- [ ] Code is formatted (Black, isort, Prettier)
- [ ] Linting passes (flake8, ESLint)
- [ ] Type checking passes (mypy, TypeScript)
- [ ] Security checks pass (bandit, npm audit)
- [ ] All tests pass locally
- [ ] Build succeeds
- [ ] No debug code or console.logs
- [ ] No commented-out code
- [ ] No hardcoded secrets or credentials
- [ ] Commit message follows conventional format
- [ ] Related tasks.md updated (if working on a spec)
- [ ] Documentation in `docs/` (not in code directories)
