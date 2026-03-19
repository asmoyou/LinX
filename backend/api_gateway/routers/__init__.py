"""API Router modules for API Gateway.

This package contains route handlers for different resource types.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
"""

from api_gateway.routers import (
    admin_users,
    agent_conversations,
    agents,
    auth,
    dashboard,
    departments,
    integrations,
    knowledge,
    missions,
    monitoring,
    notifications,
    roles,
    skill_bindings,
    skill_candidates,
    skills,
    user_memory,
    users,
)

__all__ = [
    "auth",
    "users",
    "admin_users",
    "roles",
    "departments",
    "agents",
    "agent_conversations",
    "dashboard",
    "integrations",
    "knowledge",
    "missions",
    "monitoring",
    "notifications",
    "skills",
    "skill_candidates",
    "skill_bindings",
    "user_memory",
]
