"""RBAC (Role-Based Access Control) role definitions and permissions.

This module defines the four standard roles (admin, manager, user, viewer) with their
associated permissions for the Digital Workforce Platform.

References:
- Requirements 14: User-Based Access Control
- Design Section 8: Access Control System
- Task 2.2.3: Create RBAC role definitions
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class Role(str, Enum):
    """Standard RBAC roles in the platform.

    Role hierarchy (from highest to lowest privilege):
    admin > manager > user > viewer
    """

    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    VIEWER = "viewer"


class ResourceType(str, Enum):
    """Types of resources that can be controlled by permissions."""

    AGENTS = "agents"
    TASKS = "tasks"
    KNOWLEDGE = "knowledge"
    MEMORY = "memory"
    USERS = "users"
    SYSTEM = "system"


class Action(str, Enum):
    """Actions that can be performed on resources."""

    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXECUTE = "execute"
    MANAGE = "manage"  # Special action for administrative operations


@dataclass
class Permission:
    """Represents a single permission for a resource type and action.

    Attributes:
        resource_type: The type of resource this permission applies to
        action: The action that can be performed
        scope: Optional scope restriction (e.g., "own" for own resources only)
        description: Human-readable description of the permission
    """

    resource_type: ResourceType
    action: Action
    scope: Optional[str] = None
    description: str = ""

    def __str__(self) -> str:
        """String representation of permission."""
        scope_str = f":{self.scope}" if self.scope else ""
        return f"{self.resource_type.value}:{self.action.value}{scope_str}"

    def __hash__(self) -> int:
        """Make Permission hashable for use in sets."""
        return hash((self.resource_type, self.action, self.scope))

    def __eq__(self, other) -> bool:
        """Check equality based on resource_type, action, and scope."""
        if not isinstance(other, Permission):
            return False
        return (
            self.resource_type == other.resource_type
            and self.action == other.action
            and self.scope == other.scope
        )


@dataclass
class RoleDefinition:
    """Complete definition of a role with its permissions.

    Attributes:
        name: Role name (from Role enum)
        display_name: Human-readable role name
        description: Description of the role's purpose
        permissions: Set of permissions granted to this role
        inherits_from: Optional parent role to inherit permissions from
    """

    name: Role
    display_name: str
    description: str
    permissions: Set[Permission] = field(default_factory=set)
    inherits_from: Optional[Role] = None

    def has_permission(
        self, resource_type: ResourceType, action: Action, scope: Optional[str] = None
    ) -> bool:
        """Check if this role has a specific permission.

        Args:
            resource_type: Type of resource
            action: Action to perform
            scope: Optional scope restriction

        Returns:
            True if role has the permission, False otherwise
        """
        # Check exact match
        perm = Permission(resource_type, action, scope)
        if perm in self.permissions:
            return True

        # Check for wildcard scope (None scope grants all scopes)
        wildcard_perm = Permission(resource_type, action, None)
        if wildcard_perm in self.permissions:
            return True

        # Check for MANAGE action (grants all actions)
        manage_perm = Permission(resource_type, Action.MANAGE, scope)
        if manage_perm in self.permissions:
            return True

        wildcard_manage = Permission(resource_type, Action.MANAGE, None)
        if wildcard_manage in self.permissions:
            return True

        return False

    def get_all_permissions(self) -> Set[Permission]:
        """Get all permissions including inherited ones.

        Returns:
            Set of all permissions for this role
        """
        all_perms = self.permissions.copy()

        # Add inherited permissions
        if self.inherits_from:
            parent_role = ROLE_DEFINITIONS.get(self.inherits_from)
            if parent_role:
                all_perms.update(parent_role.get_all_permissions())

        return all_perms


# Define permissions for each role

# Viewer Role: Read-only access to permitted resources
VIEWER_PERMISSIONS = {
    # Can view agents they have access to
    Permission(
        ResourceType.AGENTS, Action.READ, "permitted", "View agents user has permission to see"
    ),
    # Can view tasks they have access to
    Permission(
        ResourceType.TASKS, Action.READ, "permitted", "View tasks user has permission to see"
    ),
    # Can view knowledge base items they have access to
    Permission(
        ResourceType.KNOWLEDGE,
        Action.READ,
        "permitted",
        "View knowledge base items user has permission to see",
    ),
    # Can view memory they have access to
    Permission(
        ResourceType.MEMORY, Action.READ, "permitted", "View memory user has permission to see"
    ),
    # Can view their own user profile
    Permission(ResourceType.USERS, Action.READ, "own", "View own user profile"),
}

# User Role: Standard user access (create/manage own resources)
USER_PERMISSIONS = {
    # Can create and manage own agents
    Permission(ResourceType.AGENTS, Action.CREATE, None, "Create new agents"),
    Permission(ResourceType.AGENTS, Action.READ, "own", "View own agents"),
    Permission(ResourceType.AGENTS, Action.UPDATE, "own", "Update own agents"),
    Permission(ResourceType.AGENTS, Action.DELETE, "own", "Delete own agents"),
    Permission(ResourceType.AGENTS, Action.EXECUTE, "own", "Execute own agents"),
    # Can create and manage own tasks
    Permission(ResourceType.TASKS, Action.CREATE, None, "Create new tasks"),
    Permission(ResourceType.TASKS, Action.READ, "own", "View own tasks"),
    Permission(ResourceType.TASKS, Action.UPDATE, "own", "Update own tasks"),
    Permission(ResourceType.TASKS, Action.DELETE, "own", "Delete own tasks"),
    Permission(ResourceType.TASKS, Action.EXECUTE, "own", "Execute own tasks"),
    # Can create and manage own knowledge
    Permission(ResourceType.KNOWLEDGE, Action.CREATE, None, "Upload knowledge base items"),
    Permission(ResourceType.KNOWLEDGE, Action.READ, "own", "View own knowledge base items"),
    Permission(ResourceType.KNOWLEDGE, Action.UPDATE, "own", "Update own knowledge base items"),
    Permission(ResourceType.KNOWLEDGE, Action.DELETE, "own", "Delete own knowledge base items"),
    # Can access own memory
    Permission(ResourceType.MEMORY, Action.READ, "own", "View own agent memory"),
    Permission(ResourceType.MEMORY, Action.CREATE, "own", "Create memory entries"),
    Permission(ResourceType.MEMORY, Action.DELETE, "own", "Delete own memory entries"),
    # Can manage own user profile
    Permission(ResourceType.USERS, Action.READ, "own", "View own user profile"),
    Permission(ResourceType.USERS, Action.UPDATE, "own", "Update own user profile"),
}

# Manager Role: Manage users and agents, view all data
MANAGER_PERMISSIONS = {
    # Can manage all agents
    Permission(ResourceType.AGENTS, Action.CREATE, None, "Create agents for any user"),
    Permission(ResourceType.AGENTS, Action.READ, None, "View all agents"),
    Permission(ResourceType.AGENTS, Action.UPDATE, None, "Update any agent"),
    Permission(ResourceType.AGENTS, Action.DELETE, None, "Delete any agent"),
    Permission(ResourceType.AGENTS, Action.EXECUTE, None, "Execute any agent"),
    # Can view and manage all tasks
    Permission(ResourceType.TASKS, Action.CREATE, None, "Create tasks for any user"),
    Permission(ResourceType.TASKS, Action.READ, None, "View all tasks"),
    Permission(ResourceType.TASKS, Action.UPDATE, None, "Update any task"),
    Permission(ResourceType.TASKS, Action.DELETE, None, "Delete any task"),
    # Can view all knowledge
    Permission(ResourceType.KNOWLEDGE, Action.READ, None, "View all knowledge base items"),
    Permission(ResourceType.KNOWLEDGE, Action.UPDATE, None, "Update any knowledge base item"),
    # Can view all memory
    Permission(ResourceType.MEMORY, Action.READ, None, "View all memory"),
    # Can manage users (except admin operations)
    Permission(ResourceType.USERS, Action.READ, None, "View all users"),
    Permission(ResourceType.USERS, Action.CREATE, None, "Create new users"),
    Permission(ResourceType.USERS, Action.UPDATE, "non-admin", "Update non-admin users"),
}

# Admin Role: Full system access
ADMIN_PERMISSIONS = {
    # Full control over all resources
    Permission(ResourceType.AGENTS, Action.MANAGE, None, "Full control over all agents"),
    Permission(ResourceType.TASKS, Action.MANAGE, None, "Full control over all tasks"),
    Permission(ResourceType.KNOWLEDGE, Action.MANAGE, None, "Full control over knowledge base"),
    Permission(ResourceType.MEMORY, Action.MANAGE, None, "Full control over memory system"),
    Permission(ResourceType.USERS, Action.MANAGE, None, "Full control over users"),
    Permission(ResourceType.SYSTEM, Action.MANAGE, None, "Full control over system configuration"),
}

# Role definitions with hierarchy
ROLE_DEFINITIONS: Dict[Role, RoleDefinition] = {
    Role.VIEWER: RoleDefinition(
        name=Role.VIEWER,
        display_name="Viewer",
        description="Read-only access to permitted resources",
        permissions=VIEWER_PERMISSIONS,
        inherits_from=None,
    ),
    Role.USER: RoleDefinition(
        name=Role.USER,
        display_name="User",
        description="Standard user access (create/manage own agents, tasks, knowledge)",
        permissions=USER_PERMISSIONS,
        inherits_from=Role.VIEWER,  # Inherits viewer permissions
    ),
    Role.MANAGER: RoleDefinition(
        name=Role.MANAGER,
        display_name="Manager",
        description="Manage users and agents, view all data",
        permissions=MANAGER_PERMISSIONS,
        inherits_from=Role.USER,  # Inherits user permissions
    ),
    Role.ADMIN: RoleDefinition(
        name=Role.ADMIN,
        display_name="Administrator",
        description="Full system access (all permissions)",
        permissions=ADMIN_PERMISSIONS,
        inherits_from=Role.MANAGER,  # Inherits manager permissions
    ),
}


def get_role_definition(role: Role) -> Optional[RoleDefinition]:
    """Get the definition for a specific role.

    Args:
        role: Role to get definition for

    Returns:
        RoleDefinition if found, None otherwise
    """
    return ROLE_DEFINITIONS.get(role)


def validate_role(role_name: str) -> bool:
    """Validate if a role name is valid.

    Args:
        role_name: Role name to validate

    Returns:
        True if valid role, False otherwise
    """
    try:
        Role(role_name)
        return True
    except ValueError:
        return False


def get_all_roles() -> List[Role]:
    """Get list of all available roles.

    Returns:
        List of all Role enum values
    """
    return list(Role)


def get_role_hierarchy() -> Dict[Role, int]:
    """Get role hierarchy levels (higher number = more privilege).

    Returns:
        Dictionary mapping roles to hierarchy levels
    """
    return {
        Role.VIEWER: 1,
        Role.USER: 2,
        Role.MANAGER: 3,
        Role.ADMIN: 4,
    }


def is_role_higher_or_equal(role1: Role, role2: Role) -> bool:
    """Check if role1 has equal or higher privilege than role2.

    Args:
        role1: First role to compare
        role2: Second role to compare

    Returns:
        True if role1 >= role2 in hierarchy, False otherwise
    """
    hierarchy = get_role_hierarchy()
    return hierarchy.get(role1, 0) >= hierarchy.get(role2, 0)


def check_permission(
    role: Role, resource_type: ResourceType, action: Action, scope: Optional[str] = None
) -> bool:
    """Check if a role has a specific permission.

    Args:
        role: Role to check
        resource_type: Type of resource
        action: Action to perform
        scope: Optional scope restriction

    Returns:
        True if role has permission, False otherwise

    Example:
        >>> check_permission(Role.USER, ResourceType.AGENTS, Action.CREATE)
        True
        >>> check_permission(Role.VIEWER, ResourceType.AGENTS, Action.DELETE)
        False
    """
    role_def = get_role_definition(role)
    if not role_def:
        logger.warning(f"Unknown role: {role}")
        return False

    # Get all permissions including inherited
    all_permissions = role_def.get_all_permissions()

    # Check exact match
    perm = Permission(resource_type, action, scope)
    if perm in all_permissions:
        return True

    # Check for wildcard scope
    wildcard_perm = Permission(resource_type, action, None)
    if wildcard_perm in all_permissions:
        return True

    # Check for MANAGE action
    manage_perm = Permission(resource_type, Action.MANAGE, scope)
    if manage_perm in all_permissions:
        return True

    wildcard_manage = Permission(resource_type, Action.MANAGE, None)
    if wildcard_manage in all_permissions:
        return True

    return False


def get_role_permissions(role: Role, include_inherited: bool = True) -> Set[Permission]:
    """Get all permissions for a role.

    Args:
        role: Role to get permissions for
        include_inherited: If True, include inherited permissions

    Returns:
        Set of permissions for the role
    """
    role_def = get_role_definition(role)
    if not role_def:
        return set()

    if include_inherited:
        return role_def.get_all_permissions()
    else:
        return role_def.permissions.copy()


def get_role_summary() -> Dict[str, Dict[str, any]]:
    """Get a summary of all roles and their permissions.

    Returns:
        Dictionary with role summaries
    """
    summary = {}

    for role in Role:
        role_def = get_role_definition(role)
        if role_def:
            all_perms = role_def.get_all_permissions()
            summary[role.value] = {
                "display_name": role_def.display_name,
                "description": role_def.description,
                "inherits_from": role_def.inherits_from.value if role_def.inherits_from else None,
                "direct_permissions": len(role_def.permissions),
                "total_permissions": len(all_perms),
                "permissions": [str(p) for p in sorted(all_perms, key=str)],
            }

    return summary
