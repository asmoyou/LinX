# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LinX (灵枢) is an enterprise-grade intelligent collaboration platform for managing AI agents. It combines a Python FastAPI backend with a React/TypeScript frontend.

**Tech Stack:**
- Backend: Python 3.11+, FastAPI, LangChain/LangGraph, SQLAlchemy, Alembic
- Frontend: React 19, TypeScript, Vite, Zustand, TailwindCSS
- Databases: PostgreSQL (primary), Milvus (vectors), Redis (cache/message bus), MinIO (objects)
- LLM: Ollama (primary local), with OpenAI/Anthropic fallback options

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
```

### Docker

```bash
docker-compose up -d              # Start all services
docker-compose logs -f            # View logs
docker-compose exec api python -m shared.database init  # Init DB
```

## Architecture

### Backend Structure

```
backend/
├── api_gateway/          # FastAPI REST + WebSocket endpoints
│   ├── main.py          # App initialization
│   └── routers/         # Route handlers (agents, tasks, skills, llm, auth)
├── agent_framework/      # LangGraph 1.0 agent system
│   ├── base_agent.py    # Agent base class with StateGraph
│   └── agent_registry.py
├── skill_library/        # Reusable agent capabilities
│   ├── skill_types.py   # SkillType enum (LANGCHAIN_TOOL, AGENT_SKILL)
│   └── execution_engine.py
├── task_manager/         # Hierarchical task decomposition
├── memory_system/        # Multi-tiered memory (Agent/Company/User)
├── knowledge_base/       # Document processing and retrieval
├── llm_providers/        # LLM integrations (Ollama, vLLM, OpenAI, Anthropic)
├── access_control/       # JWT auth, RBAC/ABAC
├── database/            # SQLAlchemy models
├── shared/              # Common utilities and config
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
└── i18n/               # Internationalization
```

### Key Patterns

**Agent Framework**: Uses LangGraph 1.0 StateGraph API. Agents have isolated identity, skills from the Skill Library, and access to multi-tiered memory.

**Skill Types**:
- `LANGCHAIN_TOOL`: Simple @tool decorated functions, stored inline
- `AGENT_SKILL`: Complex multi-function skills, auto-detects inline vs MinIO storage

**Memory System**: Three layers - Agent Memory (private per agent), Company Memory (shared), User Context (per-user)

**State Management**: Zustand stores per domain, with localStorage persistence for auth. WebSocket integration for real-time updates.

**Configuration**: Backend uses `config.yaml` with environment variable substitution (`${VAR_NAME}`). Frontend uses Vite env vars (`VITE_*`).

## Running Tests

```bash
# Backend - run specific test file
pytest tests/unit/test_agents.py -v

# Backend - run specific test
pytest tests/unit/test_agents.py::test_create_agent -v

# Backend - run with markers
pytest -m "not slow"

# Frontend
npm test
```

## API Documentation

When the backend is running:
- Swagger: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

## Environment Setup

1. Copy `backend/config.yaml.example` to `backend/config.yaml`
2. Copy `.env.example` to `.env`
3. Required services: PostgreSQL, Milvus, Redis, MinIO
4. For local LLM: Install and run Ollama (`ollama run llama3:8b`)
