# LinX (灵枢) Project Context

## Project Overview
LinX (灵枢) is an enterprise-grade intelligent collaboration platform designed to manage and coordinate AI agents. It features a microservices architecture with a Python-based backend (FastAPI, LangChain) and a modern React frontend. The platform supports hierarchical task management, multi-tiered memory systems, and local LLM deployment.

## Technology Stack

### Backend (`/backend`)
*   **Language:** Python 3.11+
*   **Framework:** FastAPI
*   **Agent Framework:** LangChain / LangGraph
*   **Database:** PostgreSQL (SQLAlchemy + Alembic)
*   **Vector Database:** Milvus
*   **Message Bus:** Redis
*   **Object Storage:** MinIO
*   **LLM Support:** Ollama (local), vLLM, OpenAI, Anthropic

### Frontend (`/frontend`)
*   **Framework:** React 19
*   **Language:** TypeScript
*   **Build Tool:** Vite
*   **State Management:** Zustand
*   **Styling:** TailwindCSS
*   **UI Components:** Lucide React, Framer Motion, Recharts

### Infrastructure (`/infrastructure`)
*   **Containerization:** Docker & Docker Compose
*   **Orchestration:** Kubernetes
*   **Monitoring:** Prometheus, Grafana, Jaeger

## Project Structure

*   `backend/` - Main backend application code.
    *   `api_gateway/` - REST API endpoints and WebSockets.
    *   `agent_framework/` - Core logic for AI agents.
    *   `task_manager/` - Task decomposition and assignment.
    *   `memory_system/` - Agent, company, and user memory.
    *   `knowledge_base/` - Document processing.
*   `frontend/` - React application source.
    *   `src/components/` - Reusable UI components.
    *   `src/pages/` - Application views.
    *   `src/stores/` - Zustand state management.
*   `infrastructure/` - Deployment configurations (Docker, K8s).
*   `docs/` - Comprehensive project documentation.
*   `.kiro/` - Project specifications and requirements.

## Development & Usage

### Backend

Run commands from the `backend/` directory:

*   **Install Dependencies:** `make install-dev` (Development) or `make install` (Production)
*   **Start Server:** `make run` (Starts API Gateway on port 8000)
*   **Run Tests:** `make test` (Runs pytest)
*   **Lint Code:** `make lint` (Flake8, Pylint)
*   **Format Code:** `make format` (Black, Isort)
*   **Type Check:** `make type-check` (MyPy)
*   **Database Migrations:** `make migrate` (Applies Alembic migrations)
*   **Security Check:** `make security-check` (Bandit, Safety, Pip-audit)

### Frontend

Run commands from the `frontend/` directory:

*   **Install Dependencies:** `npm install`
*   **Start Dev Server:** `npm run dev` (Starts Vite server)
*   **Build for Production:** `npm run build`
*   **Lint Code:** `npm run lint`
*   **Format Code:** `npm run format`
*   **Type Check:** `npm run type-check`

### Docker (Full Stack)

Run commands from the project root:

*   **Start All Services:** `docker-compose up -d`
*   **View Logs:** `docker-compose logs -f`
*   **Initialize Database:** `docker-compose exec api python -m shared.database init`

## Development Conventions

*   **Code Style:**
    *   Python: Enforced via `black` and `isort`.
    *   TypeScript/React: Enforced via `prettier` and `eslint`.
*   **Testing:**
    *   Backend tests use `pytest`. Run `make test` before committing.
    *   Frontend tests are currently placeholders.
*   **Configuration:**
    *   Backend config uses `backend/config.yaml` and environment variables.
    *   Frontend config uses `.env` files (e.g., `VITE_API_URL`).
