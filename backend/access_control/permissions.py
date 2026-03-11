"""RBAC Permission Checking Middleware and Utilities.

This module provides permission checking functionality including FastAPI middleware,
decorators for endpoint protection, and utility functions for programmatic permission checks.

References:
- Requirements 14: User-Based Access Control
- Design Section 8: Access Control System
- Task 2.2.4: Implement RBAC permission checking
"""

import logging
import uuid
from functools import wraps
from typing import Any, Callable, List, Optional, Union

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from access_control.jwt_auth import JWTTokenExpiredError, JWTTokenInvalidError, decode_token
from access_control.rbac import Action, ResourceType, Role, check_permission

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme for FastAPI
security = HTTPBearer()


class PermissionDeniedError(Exception):
    """Raised when a user lacks required permissions."""

    def __init__(self, message: str, user_id: str, resource_type: str, action: str):
        self.message = message
        self.user_id = user_id
        self.resource_type = resource_type
        self.action = action
        super().__init__(self.message)


class CurrentUser:
    """Container for current authenticated user information.

    Attributes:
        user_id: User's unique identifier
        username: User's username
        role: User's role for RBAC
        token_jti: JWT token ID for tracking
        session_id: Logical login session identifier shared across token refreshes
    """

    def __init__(
        self,
        user_id: str,
        username: str,
        role: str,
        token_jti: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        self.user_id = user_id
        self.username = username
        self.role = role
        self.token_jti = token_jti
        self.session_id = session_id or token_jti

    def has_permission(
        self, resource_type: ResourceType, action: Action, scope: Optional[str] = None
    ) -> bool:
        """Check if user has a specific permission.

        Args:
            resource_type: Type of resource
            action: Action to perform
            scope: Optional scope restriction

        Returns:
            True if user has permission, False otherwise
        """
        try:
            role = Role(self.role)
            return check_permission(role, resource_type, action, scope)
        except ValueError:
            logger.warning(f"Invalid role: {self.role}")
            return False

    def can_access_resource(
        self, resource_type: ResourceType, action: Action, resource_owner_id: Optional[str] = None
    ) -> bool:
        """Check if user can access a specific resource.

        This method handles scope checking:
        - If user has permission with no scope, access granted
        - If user has "own" scope, check if resource_owner_id matches user_id
        - If user has "permitted" scope, additional permission checks needed

        Args:
            resource_type: Type of resource
            action: Action to perform
            resource_owner_id: Owner of the resource (for "own" scope checking)

        Returns:
            True if user can access resource, False otherwise
        """
        # Check for unrestricted permission (no scope)
        if self.has_permission(resource_type, action, None):
            return True

        # Check for "own" scope
        if resource_owner_id and self.has_permission(resource_type, action, "own"):
            return str(self.user_id) == str(resource_owner_id)

        # Check for "permitted" scope (requires additional permission checks)
        if self.has_permission(resource_type, action, "permitted"):
            # This would need additional logic to check specific permissions
            # For now, return True if user has the permitted scope
            return True

        return False

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "role": self.role,
        }


def _get_user_security_attributes(user_id: str) -> dict[str, Any]:
    """Load security-related user attributes from persistent storage."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise JWTTokenInvalidError("User not found")

        attributes = user.attributes
        if isinstance(attributes, dict):
            return attributes
        return {}


def ensure_session_not_revoked(user_id: str, session_id: Optional[str]) -> None:
    """Reject tokens that belong to a persistently revoked login session."""
    if not session_id:
        return

    try:
        attributes = _get_user_security_attributes(user_id)
    except JWTTokenInvalidError:
        raise
    except Exception as exc:
        logger.error(
            "Failed to validate persistent session state",
            extra={"user_id": user_id, "session_id": session_id, "error": str(exc)},
            exc_info=True,
        )
        raise JWTTokenInvalidError("Unable to validate session state") from exc

    revoked_session_ids = set(attributes.get("revoked_session_ids", []))
    if session_id in revoked_session_ids:
        raise JWTTokenInvalidError("Session has been revoked")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """FastAPI dependency to get current authenticated user from JWT token.

    Args:
        credentials: HTTP Bearer token credentials

    Returns:
        CurrentUser object with user information

    Raises:
        HTTPException: If token is invalid, expired, or missing

    Example:
        @app.get("/protected")
        async def protected_route(current_user: CurrentUser = Depends(get_current_user)):
            return {"user": current_user.username}
    """
    try:
        token = credentials.credentials
        token_data = decode_token(token)
        ensure_session_not_revoked(token_data.user_id, token_data.session_id)

        current_user = CurrentUser(
            user_id=token_data.user_id,
            username=token_data.username,
            role=token_data.role,
            token_jti=token_data.jti,
            session_id=token_data.session_id,
        )

        logger.debug(
            "User authenticated",
            extra={
                "user_id": current_user.user_id,
                "username": current_user.username,
                "role": current_user.role,
            },
        )

        return current_user

    except JWTTokenExpiredError:
        logger.warning("Token expired")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except JWTTokenInvalidError as e:
        logger.warning(f"Invalid token: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_permission(
    resource_type: ResourceType,
    action: Action,
    scope: Optional[str] = None,
    get_resource_owner: Optional[Callable] = None,
):
    """Decorator to require specific permission for an endpoint.

    Args:
        resource_type: Type of resource being accessed
        action: Action being performed
        scope: Optional scope restriction
        get_resource_owner: Optional function to extract resource owner ID from request

    Returns:
        Decorator function

    Example:
        @app.delete("/agents/{agent_id}")
        @require_permission(ResourceType.AGENTS, Action.DELETE, scope="own")
        async def delete_agent(
            agent_id: str,
            current_user: CurrentUser = Depends(get_current_user)
        ):
            # Only users with agents:delete:own permission can access
            pass
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = kwargs.get("current_user")

            if not current_user or not isinstance(current_user, CurrentUser):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            # If get_resource_owner is provided, check resource ownership
            if get_resource_owner and scope == "own":
                # Filter kwargs to only pass non-current_user arguments
                filtered_kwargs = {k: v for k, v in kwargs.items() if k != "current_user"}
                resource_owner_id = await get_resource_owner(*args, **filtered_kwargs)

                if not current_user.can_access_resource(resource_type, action, resource_owner_id):
                    log_permission_denial(
                        current_user.user_id,
                        resource_type,
                        action,
                        scope,
                        reason="resource_ownership_check_failed",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient permissions to {action.value} {resource_type.value}",
                    )
            else:
                # Check permission without resource ownership
                if not current_user.has_permission(resource_type, action, scope):
                    log_permission_denial(
                        current_user.user_id,
                        resource_type,
                        action,
                        scope,
                        reason="insufficient_permissions",
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient permissions to {action.value} {resource_type.value}",
                    )

            # Permission granted, execute function
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_role(required_roles: Union[Role, List[Role]]):
    """Decorator to require specific role(s) for an endpoint.

    Args:
        required_roles: Single role or list of roles that are allowed

    Returns:
        Decorator function

    Example:
        @app.get("/admin/users")
        @require_role([Role.ADMIN, Role.MANAGER])
        async def list_all_users(current_user: CurrentUser = Depends(get_current_user)):
            # Only admins and managers can access
            pass
    """
    # Normalize to list
    if isinstance(required_roles, Role):
        required_roles = [required_roles]

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = kwargs.get("current_user")

            if not current_user or not isinstance(current_user, CurrentUser):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            # Check if user has one of the required roles
            try:
                user_role = Role(current_user.role)
                if user_role not in required_roles:
                    logger.warning(
                        "Role check failed",
                        extra={
                            "user_id": current_user.user_id,
                            "user_role": current_user.role,
                            "required_roles": [r.value for r in required_roles],
                        },
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Requires one of roles: {', '.join(r.value for r in required_roles)}",
                    )
            except ValueError:
                logger.error(f"Invalid role: {current_user.role}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Invalid user role",
                )

            # Role check passed, execute function
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def check_resource_ownership(user_id: str, resource_owner_id: str) -> bool:
    """Check if user owns a resource.

    Args:
        user_id: User's ID
        resource_owner_id: Resource owner's ID

    Returns:
        True if user owns resource, False otherwise
    """
    return str(user_id) == str(resource_owner_id)


def check_user_permission(
    user_role: str,
    resource_type: ResourceType,
    action: Action,
    scope: Optional[str] = None,
    resource_owner_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> bool:
    """Programmatic permission check utility.

    This function provides a simple way to check permissions in application code
    without using decorators.

    Args:
        user_role: User's role
        resource_type: Type of resource
        action: Action to perform
        scope: Optional scope restriction
        resource_owner_id: Optional resource owner ID for ownership checks
        user_id: Optional user ID for ownership checks

    Returns:
        True if user has permission, False otherwise

    Example:
        if check_user_permission(
            user_role="user",
            resource_type=ResourceType.AGENTS,
            action=Action.DELETE,
            scope="own",
            resource_owner_id=agent.owner_id,
            user_id=current_user.user_id
        ):
            # User can delete this agent
            pass
    """
    try:
        role = Role(user_role)

        # Check basic permission
        has_perm = check_permission(role, resource_type, action, scope)

        if not has_perm:
            return False

        # If scope is "own", verify ownership
        if scope == "own" and resource_owner_id and user_id:
            return check_resource_ownership(user_id, resource_owner_id)

        return True

    except ValueError:
        logger.warning(f"Invalid role: {user_role}")
        return False


def log_permission_denial(
    user_id: str,
    resource_type: Union[ResourceType, str],
    action: Union[Action, str],
    scope: Optional[str] = None,
    reason: str = "insufficient_permissions",
    additional_context: Optional[dict] = None,
) -> None:
    """Log permission denial for audit purposes.

    Args:
        user_id: User who was denied
        resource_type: Type of resource
        action: Action that was denied
        scope: Optional scope
        reason: Reason for denial
        additional_context: Optional additional context
    """
    resource_str = resource_type.value if isinstance(resource_type, ResourceType) else resource_type
    action_str = action.value if isinstance(action, Action) else action

    log_data = {
        "event": "permission_denied",
        "user_id": user_id,
        "resource_type": resource_str,
        "action": action_str,
        "scope": scope,
        "reason": reason,
    }

    if additional_context:
        log_data.update(additional_context)

    logger.warning("Permission denied", extra=log_data)


def filter_by_permission(
    items: List[dict],
    current_user: CurrentUser,
    resource_type: ResourceType,
    action: Action,
    owner_id_field: str = "owner_user_id",
) -> List[dict]:
    """Filter a list of resources based on user permissions.

    This utility function filters resources based on the user's permissions:
    - If user has unrestricted permission, return all items
    - If user has "own" scope, return only items they own
    - If user has "permitted" scope, return items they have access to

    Args:
        items: List of resource dictionaries
        current_user: Current authenticated user
        resource_type: Type of resources being filtered
        action: Action being performed
        owner_id_field: Field name containing owner ID (default: "owner_user_id")

    Returns:
        Filtered list of resources

    Example:
        agents = get_all_agents()
        accessible_agents = filter_by_permission(
            agents,
            current_user,
            ResourceType.AGENTS,
            Action.READ,
            owner_id_field="owner_user_id"
        )
    """
    # If user has unrestricted permission, return all
    if current_user.has_permission(resource_type, action, None):
        return items

    # If user has "own" scope, filter by ownership
    if current_user.has_permission(resource_type, action, "own"):
        return [
            item for item in items if str(item.get(owner_id_field)) == str(current_user.user_id)
        ]

    # If user has "permitted" scope, return items they can access
    if current_user.has_permission(resource_type, action, "permitted"):
        # This would need additional logic to check specific permissions
        # For now, return items they own
        return [
            item for item in items if str(item.get(owner_id_field)) == str(current_user.user_id)
        ]

    # No permission, return empty list
    log_permission_denial(
        current_user.user_id, resource_type, action, reason="no_permission_to_list"
    )
    return []


def get_permission_scope(
    current_user: CurrentUser, resource_type: ResourceType, action: Action
) -> Optional[str]:
    """Get the permission scope for a user's action on a resource type.

    Returns the most permissive scope the user has:
    - None: Unrestricted access to all resources
    - "own": Access only to own resources
    - "permitted": Access to specifically permitted resources

    Args:
        current_user: Current authenticated user
        resource_type: Type of resource
        action: Action to perform

    Returns:
        Permission scope string or None for unrestricted access

    Example:
        scope = get_permission_scope(current_user, ResourceType.AGENTS, Action.READ)
        if scope is None:
            # User can read all agents
            agents = get_all_agents()
        elif scope == "own":
            # User can only read own agents
            agents = get_user_agents(current_user.user_id)
    """
    # Check for unrestricted permission
    if current_user.has_permission(resource_type, action, None):
        return None

    # Check for "own" scope
    if current_user.has_permission(resource_type, action, "own"):
        return "own"

    # Check for "permitted" scope
    if current_user.has_permission(resource_type, action, "permitted"):
        return "permitted"

    # No permission
    return "none"


async def verify_resource_access(
    current_user: CurrentUser,
    resource_type: ResourceType,
    action: Action,
    resource_owner_id: Optional[str] = None,
    raise_on_deny: bool = True,
) -> bool:
    """Verify user has access to a specific resource.

    Args:
        current_user: Current authenticated user
        resource_type: Type of resource
        action: Action to perform
        resource_owner_id: Owner of the resource
        raise_on_deny: If True, raise HTTPException on denial

    Returns:
        True if access granted, False otherwise

    Raises:
        HTTPException: If raise_on_deny is True and access is denied
    """
    has_access = current_user.can_access_resource(resource_type, action, resource_owner_id)

    if not has_access:
        log_permission_denial(
            current_user.user_id,
            resource_type,
            action,
            reason="resource_access_denied",
            additional_context={"resource_owner_id": resource_owner_id},
        )

        if raise_on_deny:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions to {action.value} this {resource_type.value}",
            )

    return has_access
