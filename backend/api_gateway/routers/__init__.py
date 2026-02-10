"""API Router modules for API Gateway.

This package contains route handlers for different resource types.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
"""

from api_gateway.routers import agents, auth, departments, knowledge, memory, tasks, users

__all__ = ["auth", "users", "departments", "agents", "tasks", "knowledge", "memory"]
