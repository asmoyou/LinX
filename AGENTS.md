# Repository Guidelines

## Project Structure & Module Organization
- `backend/`: FastAPI backend and core services, including `api_gateway/`, `agent_framework/`, `task_manager/`, `skill_library/`, `memory_system/`, `knowledge_base/`, `llm_providers/`, `database/`, and `alembic/`.
- `backend/tests/`: backend test suites split into `unit/`, `integration/`, `e2e/`, plus `security/` and `performance/`.
- `frontend/src/`: React + TypeScript app with `api/`, `components/`, `pages/`, `stores/`, `hooks/`, `types/`, and `i18n/`.
- `docs/`, `infrastructure/`, and `docker-compose.yml`: deployment, architecture, and operations assets.

## Build, Test, and Development Commands
- Backend setup: `cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Backend run: `cd backend && source .venv/bin/activate && make run` (Uvicorn on `:8000`)
- Backend quality: `cd backend && source .venv/bin/activate && make format && make lint && make type-check`
- Backend tests: `cd backend && source .venv/bin/activate && make test` or `cd backend && source .venv/bin/activate && make test-cov`
- Frontend setup: `cd frontend && npm install`
- Frontend run: `cd frontend && npm run dev`
- Frontend quality: `cd frontend && npm run lint && npm run type-check && npm run format`
- Full local stack: `docker-compose up -d`

## Python Environment (Required)
- Always use the project virtual environment under `backend/.venv` for backend commands.
- Prefer `cd backend && .venv/bin/python ...` and `cd backend && .venv/bin/pytest ...`.
- Do not install backend dependencies with system/global `pip` on the host.

## Coding Style & Naming Conventions
- Python: PEP 8 with Black + isort, 100-char line length, and type hints for production code.
- Python naming: modules `snake_case.py`, classes `PascalCase`, functions/variables `snake_case`.
- TypeScript/React: ESLint + Prettier; components use `PascalCase.tsx`, hooks use `useX.ts`, stores use `camelCaseStore.ts`.
- Keep modules cohesive by domain (example: agent logic under `backend/agent_framework/`, not in routers).

## Testing Guidelines
- Backend uses `pytest` with async support and coverage configured in `backend/pytest.ini`.
- Test naming: `test_*.py` or `*_test.py`; use markers (`unit`, `integration`, `e2e`, `security`, `performance`) where relevant.
- Typical runs: `cd backend && .venv/bin/pytest tests/unit/` or `cd backend && .venv/bin/pytest -m "not slow"`.
- Frontend test files are co-located as `*.test.ts`/`*.test.tsx`; keep them updated when behavior changes.
- Maintain coverage discipline: target at least 80% overall and full coverage for critical paths.

## Commit & Pull Request Guidelines
- Follow Conventional Commits: `feat(scope): ...`, `fix(scope): ...`, `docs: ...`, `refactor: ...`, `test: ...`, `chore: ...`.
- Recent history follows this pattern (example: `feat(admin): ...`, `fix(knowledge): ...`), so keep scopes meaningful.
- PRs should include: purpose, key changes, test evidence (commands run), migration/config impact, and screenshots for UI changes.
- Link related issues and call out breaking changes explicitly.

## Security & Configuration Tips
- Never commit secrets; start from `.env.example` and keep credentials in environment variables.
- Backend config uses `config.yaml` with env substitution; frontend env keys must use `VITE_*`.

## Reference Docs (Read by Depth)
- Quick contributor flow: `AGENTS.md` (this file)
- Agent and engineering playbook: `CLAUDE.md`
- Contribution process and etiquette: `CONTRIBUTING.md`
- Architecture details: `docs/architecture/system-architecture.md`
- Backend implementation guides: `docs/backend/`
- Developer workflows (frontend/testing/CI): `docs/developer/`
- Deployment and operations: `docs/deployment/` and `infrastructure/`

When guidance conflicts, prefer the most specific document for the area you are changing, then sync this file if contributor-facing behavior changes.
