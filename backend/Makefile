.PHONY: help install install-dev clean test lint format type-check security-check run docker-build docker-up docker-down migrate

# Default target
help:
	@echo "LinX (灵枢) - Backend Makefile"
	@echo ""
	@echo "Available targets:"
	@echo "  install          - Install production dependencies"
	@echo "  install-dev      - Install development dependencies"
	@echo "  clean            - Remove build artifacts and cache files"
	@echo "  test             - Run test suite"
	@echo "  test-cov         - Run tests with coverage report"
	@echo "  lint             - Run linting checks"
	@echo "  format           - Format code with black and isort"
	@echo "  type-check       - Run mypy type checking"
	@echo "  security-check   - Run security vulnerability checks"
	@echo "  run              - Run API Gateway in development mode"
	@echo "  run-debug        - Run with debug logging to console"
	@echo "  run-log          - Run with debug logging to backend.log"
	@echo "  restart          - Clean cache, stop and restart backend"
	@echo "  restart-log      - Clean cache, stop and restart with logging"
	@echo "  stop             - Stop running backend processes"
	@echo "  docker-build     - Build Docker images"
	@echo "  docker-up        - Start Docker services"
	@echo "  docker-down      - Stop Docker services"
	@echo "  migrate          - Run database migrations"
	@echo "  migrate-create   - Create new migration"

# Installation
install:
	pip install -r requirements.txt

install-dev:
	pip install -r requirements-dev.txt
	pre-commit install

install-poetry:
	poetry install

install-poetry-dev:
	poetry install --with dev

# Cleaning
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.coverage" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	rm -rf build dist

# Testing
test:
	pytest -v -m "not performance"

test-cov:
	pytest -m "not performance" --cov=. --cov-report=html --cov-report=term-missing

test-watch:
	pytest-watch

# Code Quality
lint:
	flake8 .
	pylint api_gateway task_manager agent_framework memory_system knowledge_base

format:
	black .
	isort .

format-check:
	black --check .
	isort --check-only .

type-check:
	mypy .

# Security
security-check:
	bandit -r . -ll
	safety check
	pip-audit

# Development
run:
	set -a; [ -f ../.env ] && . ../.env; set +a; \
	python -m uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000

run-debug:
	set -a; [ -f ../.env ] && . ../.env; set +a; \
	python -m uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug

run-log:
	@echo "Starting backend with logs written to backend.log..."
	@echo "Use 'tail -f backend.log' in another terminal to monitor"
	set -a; [ -f ../.env ] && . ../.env; set +a; \
	python -m uvicorn api_gateway.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug >> backend.log 2>&1

restart: clean stop run
	@echo "Backend restarted"

restart-log: clean stop run-log
	@echo "Backend restarted with logging"

stop:
	@echo "Stopping backend processes on port 8000..."
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@pkill -9 -f "uvicorn.*api_gateway" 2>/dev/null || true
	@sleep 1
	@echo "Backend stopped"

run-worker:
	python -m task_manager.worker

run-processor:
	python -m knowledge_base.processor

# Docker
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-ps:
	docker compose ps

# Database
migrate:
	alembic upgrade head

migrate-create:
	@read -p "Enter migration message: " msg; \
	alembic revision --autogenerate -m "$$msg"

migrate-rollback:
	alembic downgrade -1

migrate-history:
	alembic history

# All checks (for CI/CD)
check-all: format-check lint type-check security-check test

# Setup development environment
setup-dev: install-dev
	@echo "Development environment setup complete!"
	@echo "Run 'make run' to start the API Gateway"

# Quick start
quickstart: install docker-up migrate
	@echo "Platform is ready!"
	@echo "API Gateway: http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"
