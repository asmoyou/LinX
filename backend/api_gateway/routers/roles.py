"""Role Management Endpoints for API Gateway.

Read-only endpoints exposing RBAC role definitions, permission matrix,
and role hierarchy.

References:
- Requirements 14: User-Based Access Control
- Design Section 8: Access Control System
"""

from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from access_control.permissions import CurrentUser, get_current_user, require_role
from access_control.rbac import (
    Action,
    ResourceType,
    Role,
    get_role_definition,
    get_role_hierarchy,
    get_role_permissions,
    get_role_summary,
)
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ─── Pydantic Schemas ───────────────────────────────────────────────────────


class RoleResponse(BaseModel):
    """Single role detail response."""

    name: str
    display_name: str
    description: str
    inherits_from: Optional[str] = None
    direct_permissions: int
    total_permissions: int
    permissions: List[str]


class RoleListResponse(BaseModel):
    """List of all roles."""

    roles: List[RoleResponse]


class PermissionMatrixResponse(BaseModel):
    """Permission matrix response."""

    resources: List[str]
    actions: List[str]
    roles: List[str]
    matrix: Dict[str, Dict[str, Dict[str, bool]]]


class RoleHierarchyResponse(BaseModel):
    """Role hierarchy response."""

    hierarchy: Dict[str, int]
    order: List[str]


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=RoleListResponse)
async def list_roles(
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all roles with their permissions."""
    summary = get_role_summary()

    roles = []
    for role_name, role_info in summary.items():
        roles.append(
            RoleResponse(
                name=role_name,
                display_name=role_info["display_name"],
                description=role_info["description"],
                inherits_from=role_info.get("inherits_from"),
                direct_permissions=role_info["direct_permissions"],
                total_permissions=role_info["total_permissions"],
                permissions=role_info["permissions"],
            )
        )

    return RoleListResponse(roles=roles)


@router.get("/matrix", response_model=PermissionMatrixResponse)
@require_role([Role.ADMIN, Role.MANAGER])
async def get_permission_matrix(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get permission matrix (resource x action x role). Admin/manager only."""
    resources = [r.value for r in ResourceType]
    actions = [a.value for a in Action]
    roles = [r.value for r in Role]

    matrix: Dict[str, Dict[str, Dict[str, bool]]] = {}

    for resource_type in ResourceType:
        matrix[resource_type.value] = {}
        for action in Action:
            matrix[resource_type.value][action.value] = {}
            for role in Role:
                # Check if the role has this permission (including inherited)
                all_perms = get_role_permissions(role, include_inherited=True)
                has_perm = False
                for perm in all_perms:
                    if perm.resource_type == resource_type and (
                        perm.action == action or perm.action == Action.MANAGE
                    ):
                        has_perm = True
                        break
                matrix[resource_type.value][action.value][role.value] = has_perm

    return PermissionMatrixResponse(
        resources=resources,
        actions=actions,
        roles=roles,
        matrix=matrix,
    )


@router.get("/hierarchy", response_model=RoleHierarchyResponse)
async def get_hierarchy(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get role hierarchy with privilege levels."""
    hierarchy = get_role_hierarchy()
    hierarchy_str = {role.value: level for role, level in hierarchy.items()}

    # Order from highest to lowest
    order = sorted(hierarchy_str.keys(), key=lambda r: hierarchy_str[r], reverse=True)

    return RoleHierarchyResponse(
        hierarchy=hierarchy_str,
        order=order,
    )


@router.get("/{role_name}", response_model=RoleResponse)
async def get_role(
    role_name: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get detailed information for a specific role."""
    try:
        role = Role(role_name)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role '{role_name}' not found. Valid roles: {', '.join(r.value for r in Role)}",
        )

    role_def = get_role_definition(role)
    if not role_def:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Role definition for '{role_name}' not found",
        )

    all_perms = role_def.get_all_permissions()

    return RoleResponse(
        name=role_def.name.value,
        display_name=role_def.display_name,
        description=role_def.description,
        inherits_from=role_def.inherits_from.value if role_def.inherits_from else None,
        direct_permissions=len(role_def.permissions),
        total_permissions=len(all_perms),
        permissions=sorted([str(p) for p in all_perms]),
    )
