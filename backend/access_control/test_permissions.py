"""Unit tests for RBAC permission checking middleware and utilities.

References:
- Requirements 14: User-Based Access Control
- Design Section 8: Access Control System
- Task 2.2.4: Implement RBAC permission checking
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from access_control.permissions import (
    CurrentUser,
    PermissionDeniedError,
    get_current_user,
    require_permission,
    require_role,
    check_resource_ownership,
    check_user_permission,
    log_permission_denial,
    filter_by_permission,
    get_permission_scope,
    verify_resource_access,
)
from access_control.rbac import Role, ResourceType, Action
from access_control.jwt_auth import create_access_token
import uuid


class TestCurrentUser:
    """Tests for CurrentUser class."""
    
    def test_current_user_creation(self):
        """Test creating a CurrentUser instance."""
        user = CurrentUser(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            username="john_doe",
            role="user",
            token_jti="token-123"
        )
        
        assert user.user_id == "123e4567-e89b-12d3-a456-426614174000"
        assert user.username == "john_doe"
        assert user.role == "user"
        assert user.token_jti == "token-123"
    
    def test_has_permission_valid_role(self):
        """Test checking permission with valid role."""
        user = CurrentUser(
            user_id="123",
            username="john",
            role="user"
        )
        
        # User should have permission to create agents
        assert user.has_permission(ResourceType.AGENTS, Action.CREATE)
        
        # User should have permission to read own agents
        assert user.has_permission(ResourceType.AGENTS, Action.READ, "own")
        
        # User should not have permission to read all agents
        assert not user.has_permission(ResourceType.AGENTS, Action.READ, None)
    
    def test_has_permission_admin_role(self):
        """Test that admin has all permissions."""
        admin = CurrentUser(
            user_id="123",
            username="admin",
            role="admin"
        )
        
        # Admin should have all permissions
        assert admin.has_permission(ResourceType.AGENTS, Action.MANAGE)
        assert admin.has_permission(ResourceType.TASKS, Action.DELETE)
        assert admin.has_permission(ResourceType.SYSTEM, Action.MANAGE)
    
    def test_has_permission_invalid_role(self):
        """Test checking permission with invalid role."""
        user = CurrentUser(
            user_id="123",
            username="john",
            role="invalid_role"
        )
        
        # Should return False for invalid role
        assert not user.has_permission(ResourceType.AGENTS, Action.CREATE)
    
    def test_can_access_resource_unrestricted(self):
        """Test resource access with unrestricted permission."""
        manager = CurrentUser(
            user_id="123",
            username="manager",
            role="manager"
        )
        
        # Manager has unrestricted access to agents
        assert manager.can_access_resource(
            ResourceType.AGENTS,
            Action.READ,
            resource_owner_id="456"
        )
    
    def test_can_access_resource_own_scope_owner(self):
        """Test resource access with 'own' scope when user is owner."""
        user = CurrentUser(
            user_id="123",
            username="john",
            role="user"
        )
        
        # User can access their own resource
        assert user.can_access_resource(
            ResourceType.AGENTS,
            Action.READ,
            resource_owner_id="123"
        )
    
    def test_can_access_resource_own_scope_not_owner(self):
        """Test resource access with 'own' scope when user is not owner."""
        user = CurrentUser(
            user_id="123",
            username="john",
            role="user"
        )
        
        # User cannot access someone else's resource
        assert not user.can_access_resource(
            ResourceType.AGENTS,
            Action.READ,
            resource_owner_id="456"
        )
    
    def test_can_access_resource_no_permission(self):
        """Test resource access with no permission."""
        viewer = CurrentUser(
            user_id="123",
            username="viewer",
            role="viewer"
        )
        
        # Viewer cannot create agents
        assert not viewer.can_access_resource(
            ResourceType.AGENTS,
            Action.CREATE,
            resource_owner_id="123"
        )
    
    def test_to_dict(self):
        """Test converting CurrentUser to dictionary."""
        user = CurrentUser(
            user_id="123",
            username="john",
            role="user"
        )
        
        user_dict = user.to_dict()
        
        assert user_dict["user_id"] == "123"
        assert user_dict["username"] == "john"
        assert user_dict["role"] == "user"


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""
    
    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        """Test getting current user with valid token."""
        # Create a valid token
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "john_doe", "user")
        
        # Create credentials
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        
        # Get current user
        current_user = await get_current_user(credentials)
        
        assert current_user.username == "john_doe"
        assert current_user.role == "user"
        assert str(current_user.user_id) == str(user_id)
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Test getting current user with invalid token."""
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials="invalid_token"
        )
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials)
        
        assert exc_info.value.status_code == 401
        assert "Invalid authentication credentials" in exc_info.value.detail


class TestRequirePermission:
    """Tests for require_permission decorator."""
    
    @pytest.mark.asyncio
    async def test_require_permission_granted(self):
        """Test decorator when permission is granted."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        @require_permission(ResourceType.AGENTS, Action.CREATE)
        async def create_agent(current_user: CurrentUser):
            return {"status": "created"}
        
        result = await create_agent(current_user=user)
        assert result["status"] == "created"
    
    @pytest.mark.asyncio
    async def test_require_permission_denied(self):
        """Test decorator when permission is denied."""
        viewer = CurrentUser(user_id="123", username="viewer", role="viewer")
        
        @require_permission(ResourceType.AGENTS, Action.CREATE)
        async def create_agent(current_user: CurrentUser):
            return {"status": "created"}
        
        with pytest.raises(HTTPException) as exc_info:
            await create_agent(current_user=viewer)
        
        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_require_permission_no_user(self):
        """Test decorator when no user is provided."""
        @require_permission(ResourceType.AGENTS, Action.CREATE)
        async def create_agent():
            return {"status": "created"}
        
        with pytest.raises(HTTPException) as exc_info:
            await create_agent()
        
        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_require_permission_with_ownership_check(self):
        """Test decorator with resource ownership check."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        async def get_agent_owner(agent_id: str):
            return "123"  # User owns this agent
        
        @require_permission(
            ResourceType.AGENTS,
            Action.DELETE,
            scope="own",
            get_resource_owner=get_agent_owner
        )
        async def delete_agent(agent_id: str, current_user: CurrentUser):
            return {"status": "deleted"}
        
        result = await delete_agent(agent_id="agent-1", current_user=user)
        assert result["status"] == "deleted"
    
    @pytest.mark.asyncio
    async def test_require_permission_ownership_check_fails(self):
        """Test decorator when ownership check fails."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        async def get_agent_owner(agent_id: str):
            return "456"  # Different owner
        
        @require_permission(
            ResourceType.AGENTS,
            Action.DELETE,
            scope="own",
            get_resource_owner=get_agent_owner
        )
        async def delete_agent(agent_id: str, current_user: CurrentUser):
            return {"status": "deleted"}
        
        with pytest.raises(HTTPException) as exc_info:
            await delete_agent(agent_id="agent-1", current_user=user)
        
        assert exc_info.value.status_code == 403


class TestRequireRole:
    """Tests for require_role decorator."""
    
    @pytest.mark.asyncio
    async def test_require_role_single_role_granted(self):
        """Test decorator with single role when granted."""
        admin = CurrentUser(user_id="123", username="admin", role="admin")
        
        @require_role(Role.ADMIN)
        async def admin_function(current_user: CurrentUser):
            return {"status": "success"}
        
        result = await admin_function(current_user=admin)
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_require_role_single_role_denied(self):
        """Test decorator with single role when denied."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        @require_role(Role.ADMIN)
        async def admin_function(current_user: CurrentUser):
            return {"status": "success"}
        
        with pytest.raises(HTTPException) as exc_info:
            await admin_function(current_user=user)
        
        assert exc_info.value.status_code == 403
        assert "Requires one of roles" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_require_role_multiple_roles_granted(self):
        """Test decorator with multiple roles when one matches."""
        manager = CurrentUser(user_id="123", username="manager", role="manager")
        
        @require_role([Role.ADMIN, Role.MANAGER])
        async def admin_or_manager_function(current_user: CurrentUser):
            return {"status": "success"}
        
        result = await admin_or_manager_function(current_user=manager)
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_require_role_multiple_roles_denied(self):
        """Test decorator with multiple roles when none match."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        @require_role([Role.ADMIN, Role.MANAGER])
        async def admin_or_manager_function(current_user: CurrentUser):
            return {"status": "success"}
        
        with pytest.raises(HTTPException) as exc_info:
            await admin_or_manager_function(current_user=user)
        
        assert exc_info.value.status_code == 403


class TestCheckResourceOwnership:
    """Tests for check_resource_ownership function."""
    
    def test_check_resource_ownership_match(self):
        """Test ownership check when IDs match."""
        assert check_resource_ownership("123", "123")
    
    def test_check_resource_ownership_no_match(self):
        """Test ownership check when IDs don't match."""
        assert not check_resource_ownership("123", "456")
    
    def test_check_resource_ownership_uuid_match(self):
        """Test ownership check with UUID strings."""
        user_id = str(uuid.uuid4())
        assert check_resource_ownership(user_id, user_id)
    
    def test_check_resource_ownership_type_conversion(self):
        """Test ownership check with type conversion."""
        # Should convert both to strings for comparison
        assert check_resource_ownership("123", "123")


class TestCheckUserPermission:
    """Tests for check_user_permission utility function."""
    
    def test_check_user_permission_granted(self):
        """Test permission check when granted."""
        result = check_user_permission(
            user_role="user",
            resource_type=ResourceType.AGENTS,
            action=Action.CREATE
        )
        assert result is True
    
    def test_check_user_permission_denied(self):
        """Test permission check when denied."""
        result = check_user_permission(
            user_role="viewer",
            resource_type=ResourceType.AGENTS,
            action=Action.CREATE
        )
        assert result is False
    
    def test_check_user_permission_with_ownership(self):
        """Test permission check with ownership verification."""
        result = check_user_permission(
            user_role="user",
            resource_type=ResourceType.AGENTS,
            action=Action.DELETE,
            scope="own",
            resource_owner_id="123",
            user_id="123"
        )
        assert result is True
    
    def test_check_user_permission_ownership_fails(self):
        """Test permission check when ownership verification fails."""
        result = check_user_permission(
            user_role="user",
            resource_type=ResourceType.AGENTS,
            action=Action.DELETE,
            scope="own",
            resource_owner_id="456",
            user_id="123"
        )
        assert result is False
    
    def test_check_user_permission_invalid_role(self):
        """Test permission check with invalid role."""
        result = check_user_permission(
            user_role="invalid_role",
            resource_type=ResourceType.AGENTS,
            action=Action.CREATE
        )
        assert result is False


class TestLogPermissionDenial:
    """Tests for log_permission_denial function."""
    
    def test_log_permission_denial_basic(self):
        """Test logging permission denial with basic info."""
        # Should not raise any exceptions
        log_permission_denial(
            user_id="123",
            resource_type=ResourceType.AGENTS,
            action=Action.CREATE
        )
    
    def test_log_permission_denial_with_scope(self):
        """Test logging permission denial with scope."""
        log_permission_denial(
            user_id="123",
            resource_type=ResourceType.AGENTS,
            action=Action.DELETE,
            scope="own"
        )
    
    def test_log_permission_denial_with_context(self):
        """Test logging permission denial with additional context."""
        log_permission_denial(
            user_id="123",
            resource_type=ResourceType.AGENTS,
            action=Action.DELETE,
            reason="resource_not_found",
            additional_context={"agent_id": "agent-123"}
        )
    
    def test_log_permission_denial_string_types(self):
        """Test logging with string types instead of enums."""
        log_permission_denial(
            user_id="123",
            resource_type="agents",
            action="create"
        )


class TestFilterByPermission:
    """Tests for filter_by_permission function."""
    
    def test_filter_by_permission_unrestricted(self):
        """Test filtering with unrestricted permission."""
        admin = CurrentUser(user_id="123", username="admin", role="admin")
        
        items = [
            {"id": "1", "owner_user_id": "123"},
            {"id": "2", "owner_user_id": "456"},
            {"id": "3", "owner_user_id": "789"},
        ]
        
        filtered = filter_by_permission(
            items,
            admin,
            ResourceType.AGENTS,
            Action.READ
        )
        
        # Admin should see all items
        assert len(filtered) == 3
    
    def test_filter_by_permission_own_scope(self):
        """Test filtering with 'own' scope."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        items = [
            {"id": "1", "owner_user_id": "123"},
            {"id": "2", "owner_user_id": "456"},
            {"id": "3", "owner_user_id": "123"},
        ]
        
        filtered = filter_by_permission(
            items,
            user,
            ResourceType.AGENTS,
            Action.READ
        )
        
        # User should only see their own items
        assert len(filtered) == 2
        assert all(item["owner_user_id"] == "123" for item in filtered)
    
    def test_filter_by_permission_no_permission(self):
        """Test filtering with no permission."""
        viewer = CurrentUser(user_id="123", username="viewer", role="viewer")
        
        items = [
            {"id": "1", "owner_user_id": "123"},
            {"id": "2", "owner_user_id": "456"},
        ]
        
        filtered = filter_by_permission(
            items,
            viewer,
            ResourceType.AGENTS,
            Action.CREATE
        )
        
        # Viewer cannot create, should see nothing
        assert len(filtered) == 0
    
    def test_filter_by_permission_custom_owner_field(self):
        """Test filtering with custom owner field name."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        items = [
            {"id": "1", "created_by": "123"},
            {"id": "2", "created_by": "456"},
        ]
        
        filtered = filter_by_permission(
            items,
            user,
            ResourceType.TASKS,
            Action.READ,
            owner_id_field="created_by"
        )
        
        assert len(filtered) == 1
        assert filtered[0]["created_by"] == "123"


class TestGetPermissionScope:
    """Tests for get_permission_scope function."""
    
    def test_get_permission_scope_unrestricted(self):
        """Test getting scope for unrestricted permission."""
        admin = CurrentUser(user_id="123", username="admin", role="admin")
        
        scope = get_permission_scope(
            admin,
            ResourceType.AGENTS,
            Action.READ
        )
        
        assert scope is None  # Unrestricted
    
    def test_get_permission_scope_own(self):
        """Test getting scope for 'own' permission."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        scope = get_permission_scope(
            user,
            ResourceType.AGENTS,
            Action.READ
        )
        
        assert scope == "own"
    
    def test_get_permission_scope_permitted(self):
        """Test getting scope for 'permitted' permission."""
        viewer = CurrentUser(user_id="123", username="viewer", role="viewer")
        
        scope = get_permission_scope(
            viewer,
            ResourceType.AGENTS,
            Action.READ
        )
        
        assert scope == "permitted"
    
    def test_get_permission_scope_none(self):
        """Test getting scope when no permission."""
        viewer = CurrentUser(user_id="123", username="viewer", role="viewer")
        
        scope = get_permission_scope(
            viewer,
            ResourceType.AGENTS,
            Action.CREATE
        )
        
        assert scope == "none"


class TestVerifyResourceAccess:
    """Tests for verify_resource_access function."""
    
    @pytest.mark.asyncio
    async def test_verify_resource_access_granted(self):
        """Test verifying access when granted."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        result = await verify_resource_access(
            user,
            ResourceType.AGENTS,
            Action.READ,
            resource_owner_id="123",
            raise_on_deny=False
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_verify_resource_access_denied_no_raise(self):
        """Test verifying access when denied without raising."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        result = await verify_resource_access(
            user,
            ResourceType.AGENTS,
            Action.READ,
            resource_owner_id="456",
            raise_on_deny=False
        )
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_verify_resource_access_denied_with_raise(self):
        """Test verifying access when denied with raising."""
        user = CurrentUser(user_id="123", username="john", role="user")
        
        with pytest.raises(HTTPException) as exc_info:
            await verify_resource_access(
                user,
                ResourceType.AGENTS,
                Action.READ,
                resource_owner_id="456",
                raise_on_deny=True
            )
        
        assert exc_info.value.status_code == 403
        assert "Insufficient permissions" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_verify_resource_access_unrestricted(self):
        """Test verifying access with unrestricted permission."""
        admin = CurrentUser(user_id="123", username="admin", role="admin")
        
        result = await verify_resource_access(
            admin,
            ResourceType.AGENTS,
            Action.READ,
            resource_owner_id="456",
            raise_on_deny=False
        )
        
        assert result is True


class TestPermissionDeniedError:
    """Tests for PermissionDeniedError exception."""
    
    def test_permission_denied_error_creation(self):
        """Test creating PermissionDeniedError."""
        error = PermissionDeniedError(
            message="Access denied",
            user_id="123",
            resource_type="agents",
            action="delete"
        )
        
        assert error.message == "Access denied"
        assert error.user_id == "123"
        assert error.resource_type == "agents"
        assert error.action == "delete"
        assert str(error) == "Access denied"
