"""API Router modules for API Gateway.

This package contains route handlers for different resource types.

References:
- Requirements 15: API and Integration Layer
- Design Section 12: API Gateway
"""

from api_gateway.routers import (
    admin_users,
    agents,
    auth,
    dashboard,
    departments,
    knowledge,
    memory,
    missions,
    monitoring,
    notifications,
    roles,
    skills,
    users,
)

__all__ = [
    "auth",
    "users",
    "admin_users",
    "roles",
    "departments",
    "agents",
    "dashboard",
    "knowledge",
    "memory",
    "missions",
    "monitoring",
    "notifications",
    "skills",
]
