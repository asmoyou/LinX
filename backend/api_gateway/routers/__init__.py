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
    mcp_servers,
    monitoring,
    notifications,
    platform_settings,
    project_execution,
    roles,
    schedules,
    skill_bindings,
    skill_candidates,
    skills,
    telemetry,
    user_memory,
    users,
)

__all__ = [
    "auth",
    "users",
    "admin_users",
    "roles",
    "schedules",
    "departments",
    "agents",
    "agent_conversations",
    "dashboard",
    "integrations",
    "knowledge",
    "mcp_servers",
    "monitoring",
    "notifications",
    "platform_settings",
    "project_execution",
    "skills",
    "skill_candidates",
    "skill_bindings",
    "telemetry",
    "user_memory",
]
