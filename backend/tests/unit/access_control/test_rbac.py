"""Unit tests for RBAC role definitions and permissions.

References:
- Requirements 14: User-Based Access Control
- Design Section 8: Access Control System
- Task 2.2.3: Create RBAC role definitions
"""

import pytest

from access_control.rbac import (
    ROLE_DEFINITIONS,
    Action,
    Permission,
    ResourceType,
    Role,
    RoleDefinition,
    check_permission,
    get_all_roles,
    get_role_definition,
    get_role_hierarchy,
    get_role_permissions,
    get_role_summary,
    is_role_higher_or_equal,
    validate_role,
)


class TestPermission:
    """Tests for Permission class."""

    def test_permission_creation(self):
        """Test creating a permission."""
        perm = Permission(ResourceType.AGENTS, Action.CREATE, "own", "Create own agents")

        assert perm.resource_type == ResourceType.AGENTS
        assert perm.action == Action.CREATE
        assert perm.scope == "own"
        assert perm.description == "Create own agents"

    def test_permission_string_representation(self):
        """Test permission string representation."""
        perm1 = Permission(ResourceType.AGENTS, Action.READ, "own")
        assert str(perm1) == "agents:read:own"

        perm2 = Permission(ResourceType.TASKS, Action.CREATE, None)
        assert str(perm2) == "tasks:create"

    def test_permission_equality(self):
        """Test permission equality comparison."""
        perm1 = Permission(ResourceType.AGENTS, Action.READ, "own")
        perm2 = Permission(ResourceType.AGENTS, Action.READ, "own")
        perm3 = Permission(ResourceType.AGENTS, Action.READ, None)

        assert perm1 == perm2
        assert perm1 != perm3

    def test_permission_hashable(self):
        """Test that permissions can be used in sets."""
        perm1 = Permission(ResourceType.AGENTS, Action.READ, "own")
        perm2 = Permission(ResourceType.TASKS, Action.CREATE, None)

        perm_set = {perm1, perm2}
        assert len(perm_set) == 2
        assert perm1 in perm_set


class TestRoleDefinition:
    """Tests for RoleDefinition class."""

    def test_role_definition_creation(self):
        """Test creating a role definition."""
        perms = {
            Permission(ResourceType.AGENTS, Action.READ, "own"),
            Permission(ResourceType.TASKS, Action.READ, "own"),
        }

        role_def = RoleDefinition(
            name=Role.USER,
            display_name="User",
            description="Standard user",
            permissions=perms,
        )

        assert role_def.name == Role.USER
        assert role_def.display_name == "User"
        assert len(role_def.permissions) == 2

    def test_has_permission_exact_match(self):
        """Test checking for exact permission match."""
        perms = {Permission(ResourceType.AGENTS, Action.READ, "own")}
        role_def = RoleDefinition(
            name=Role.USER,
            display_name="User",
            description="Test",
            permissions=perms,
        )

        assert role_def.has_permission(ResourceType.AGENTS, Action.READ, "own")
        assert not role_def.has_permission(ResourceType.AGENTS, Action.CREATE, "own")

    def test_has_permission_wildcard_scope(self):
        """Test that None scope grants all scopes."""
        perms = {Permission(ResourceType.AGENTS, Action.READ, None)}
        role_def = RoleDefinition(
            name=Role.USER,
            display_name="User",
            description="Test",
            permissions=perms,
        )

        # None scope should grant any scope
        assert role_def.has_permission(ResourceType.AGENTS, Action.READ, "own")
        assert role_def.has_permission(ResourceType.AGENTS, Action.READ, "all")
        assert role_def.has_permission(ResourceType.AGENTS, Action.READ, None)

    def test_has_permission_manage_action(self):
        """Test that MANAGE action grants all actions."""
        perms = {Permission(ResourceType.AGENTS, Action.MANAGE, None)}
        role_def = RoleDefinition(
            name=Role.ADMIN,
            display_name="Admin",
            description="Test",
            permissions=perms,
        )

        # MANAGE should grant any action
        assert role_def.has_permission(ResourceType.AGENTS, Action.READ, None)
        assert role_def.has_permission(ResourceType.AGENTS, Action.CREATE, None)
        assert role_def.has_permission(ResourceType.AGENTS, Action.DELETE, "own")

    def test_get_all_permissions_no_inheritance(self):
        """Test getting permissions without inheritance."""
        perms = {Permission(ResourceType.AGENTS, Action.READ, "own")}
        role_def = RoleDefinition(
            name=Role.USER,
            display_name="User",
            description="Test",
            permissions=perms,
            inherits_from=None,
        )

        all_perms = role_def.get_all_permissions()
        assert len(all_perms) == 1


class TestRoleValidation:
    """Tests for role validation functions."""

    def test_validate_role_valid(self):
        """Test validating valid role names."""
        assert validate_role("admin")
        assert validate_role("manager")
        assert validate_role("user")
        assert validate_role("viewer")

    def test_validate_role_invalid(self):
        """Test validating invalid role names."""
        assert not validate_role("superuser")
        assert not validate_role("guest")
        assert not validate_role("")
        assert not validate_role("ADMIN")  # Case sensitive

    def test_get_all_roles(self):
        """Test getting all available roles."""
        roles = get_all_roles()

        assert len(roles) == 4
        assert Role.ADMIN in roles
        assert Role.MANAGER in roles
        assert Role.USER in roles
        assert Role.VIEWER in roles


class TestRoleHierarchy:
    """Tests for role hierarchy functions."""

    def test_get_role_hierarchy(self):
        """Test getting role hierarchy levels."""
        hierarchy = get_role_hierarchy()

        assert hierarchy[Role.VIEWER] == 1
        assert hierarchy[Role.USER] == 2
        assert hierarchy[Role.MANAGER] == 3
        assert hierarchy[Role.ADMIN] == 4

    def test_is_role_higher_or_equal_same_role(self):
        """Test comparing same roles."""
        assert is_role_higher_or_equal(Role.USER, Role.USER)
        assert is_role_higher_or_equal(Role.ADMIN, Role.ADMIN)

    def test_is_role_higher_or_equal_higher_role(self):
        """Test comparing higher privilege roles."""
        assert is_role_higher_or_equal(Role.ADMIN, Role.MANAGER)
        assert is_role_higher_or_equal(Role.ADMIN, Role.USER)
        assert is_role_higher_or_equal(Role.MANAGER, Role.USER)
        assert is_role_higher_or_equal(Role.USER, Role.VIEWER)

    def test_is_role_higher_or_equal_lower_role(self):
        """Test comparing lower privilege roles."""
        assert not is_role_higher_or_equal(Role.VIEWER, Role.USER)
        assert not is_role_higher_or_equal(Role.USER, Role.MANAGER)
        assert not is_role_higher_or_equal(Role.MANAGER, Role.ADMIN)


class TestRoleDefinitions:
    """Tests for predefined role definitions."""

    def test_all_roles_defined(self):
        """Test that all roles have definitions."""
        for role in Role:
            assert role in ROLE_DEFINITIONS
            assert get_role_definition(role) is not None

    def test_viewer_role_definition(self):
        """Test viewer role definition."""
        viewer = get_role_definition(Role.VIEWER)

        assert viewer.name == Role.VIEWER
        assert viewer.display_name == "Viewer"
        assert viewer.inherits_from is None
        assert len(viewer.permissions) > 0

        # Viewer should have read-only permissions
        assert any(p.action == Action.READ for p in viewer.permissions)
        assert not any(p.action == Action.CREATE for p in viewer.permissions)
        assert not any(p.action == Action.DELETE for p in viewer.permissions)

    def test_user_role_definition(self):
        """Test user role definition."""
        user = get_role_definition(Role.USER)

        assert user.name == Role.USER
        assert user.display_name == "User"
        assert user.inherits_from == Role.VIEWER
        assert len(user.permissions) > 0

        # User should have create/update/delete on own resources
        assert any(p.action == Action.CREATE for p in user.permissions)
        assert any(p.action == Action.UPDATE and p.scope == "own" for p in user.permissions)
        assert any(p.action == Action.DELETE and p.scope == "own" for p in user.permissions)

    def test_manager_role_definition(self):
        """Test manager role definition."""
        manager = get_role_definition(Role.MANAGER)

        assert manager.name == Role.MANAGER
        assert manager.display_name == "Manager"
        assert manager.inherits_from == Role.USER
        assert len(manager.permissions) > 0

        # Manager should have broader permissions (no scope or all scope)
        assert any(p.scope is None for p in manager.permissions)

    def test_admin_role_definition(self):
        """Test admin role definition."""
        admin = get_role_definition(Role.ADMIN)

        assert admin.name == Role.ADMIN
        assert admin.display_name == "Administrator"
        assert admin.inherits_from == Role.MANAGER
        assert len(admin.permissions) > 0

        # Admin should have MANAGE permissions
        assert any(p.action == Action.MANAGE for p in admin.permissions)

        # Admin should have system permissions
        assert any(p.resource_type == ResourceType.SYSTEM for p in admin.permissions)


class TestPermissionChecking:
    """Tests for permission checking functions."""

    def test_check_permission_viewer_can_read(self):
        """Test that viewer can read permitted resources."""
        assert check_permission(Role.VIEWER, ResourceType.AGENTS, Action.READ, "permitted")
        assert check_permission(Role.VIEWER, ResourceType.TASKS, Action.READ, "permitted")
        assert check_permission(Role.VIEWER, ResourceType.KNOWLEDGE, Action.READ, "permitted")

    def test_check_permission_viewer_cannot_write(self):
        """Test that viewer cannot create/update/delete."""
        assert not check_permission(Role.VIEWER, ResourceType.AGENTS, Action.CREATE)
        assert not check_permission(Role.VIEWER, ResourceType.AGENTS, Action.UPDATE)
        assert not check_permission(Role.VIEWER, ResourceType.AGENTS, Action.DELETE)

    def test_check_permission_user_can_manage_own(self):
        """Test that user can manage own resources."""
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.CREATE)
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.READ, "own")
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.UPDATE, "own")
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.DELETE, "own")
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.EXECUTE, "own")

    def test_check_permission_user_inherits_viewer(self):
        """Test that user inherits viewer permissions."""
        # User should inherit viewer's read permissions
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.READ, "permitted")
        assert check_permission(Role.USER, ResourceType.USERS, Action.READ, "own")

    def test_check_permission_manager_can_manage_all(self):
        """Test that manager can manage all agents and tasks."""
        assert check_permission(Role.MANAGER, ResourceType.AGENTS, Action.CREATE)
        assert check_permission(Role.MANAGER, ResourceType.AGENTS, Action.READ)
        assert check_permission(Role.MANAGER, ResourceType.AGENTS, Action.UPDATE)
        assert check_permission(Role.MANAGER, ResourceType.AGENTS, Action.DELETE)

        assert check_permission(Role.MANAGER, ResourceType.TASKS, Action.READ)
        assert check_permission(Role.MANAGER, ResourceType.TASKS, Action.UPDATE)

    def test_check_permission_manager_can_manage_users(self):
        """Test that manager can manage users."""
        assert check_permission(Role.MANAGER, ResourceType.USERS, Action.READ)
        assert check_permission(Role.MANAGER, ResourceType.USERS, Action.CREATE)
        assert check_permission(Role.MANAGER, ResourceType.USERS, Action.UPDATE, "non-admin")

    def test_check_permission_admin_has_all_permissions(self):
        """Test that admin has all permissions via MANAGE."""
        # Admin should have MANAGE on all resource types
        for resource_type in ResourceType:
            assert check_permission(Role.ADMIN, resource_type, Action.MANAGE)
            assert check_permission(Role.ADMIN, resource_type, Action.CREATE)
            assert check_permission(Role.ADMIN, resource_type, Action.READ)
            assert check_permission(Role.ADMIN, resource_type, Action.UPDATE)
            assert check_permission(Role.ADMIN, resource_type, Action.DELETE)

    def test_check_permission_invalid_role(self):
        """Test checking permission with invalid role."""
        # Should return False for unknown role (after logging warning)
        result = check_permission("invalid_role", ResourceType.AGENTS, Action.READ)
        assert result is False


class TestGetRolePermissions:
    """Tests for getting role permissions."""

    def test_get_role_permissions_without_inheritance(self):
        """Test getting direct permissions only."""
        perms = get_role_permissions(Role.USER, include_inherited=False)

        assert len(perms) > 0
        # Should only include USER's direct permissions
        assert all(isinstance(p, Permission) for p in perms)

    def test_get_role_permissions_with_inheritance(self):
        """Test getting all permissions including inherited."""
        user_perms = get_role_permissions(Role.USER, include_inherited=True)
        user_direct = get_role_permissions(Role.USER, include_inherited=False)

        # With inheritance should have more permissions
        assert len(user_perms) > len(user_direct)

        # Should include viewer permissions
        viewer_perms = get_role_permissions(Role.VIEWER, include_inherited=False)
        for perm in viewer_perms:
            assert perm in user_perms

    def test_get_role_permissions_admin_includes_all(self):
        """Test that admin permissions include all inherited permissions."""
        admin_perms = get_role_permissions(Role.ADMIN, include_inherited=True)
        manager_perms = get_role_permissions(Role.MANAGER, include_inherited=True)

        # Admin should have at least as many permissions as manager
        assert len(admin_perms) >= len(manager_perms)

        # Admin should include all manager permissions
        for perm in manager_perms:
            # Check if admin has equivalent or better permission
            has_perm = any(
                p.resource_type == perm.resource_type
                and (p.action == Action.MANAGE or p.action == perm.action)
                for p in admin_perms
            )
            assert has_perm

    def test_get_role_permissions_invalid_role(self):
        """Test getting permissions for invalid role."""
        perms = get_role_permissions("invalid_role")
        assert len(perms) == 0


class TestRoleSummary:
    """Tests for role summary function."""

    def test_get_role_summary_structure(self):
        """Test that role summary has correct structure."""
        summary = get_role_summary()

        assert len(summary) == 4
        assert "admin" in summary
        assert "manager" in summary
        assert "user" in summary
        assert "viewer" in summary

        for role_name, role_info in summary.items():
            assert "display_name" in role_info
            assert "description" in role_info
            assert "inherits_from" in role_info
            assert "direct_permissions" in role_info
            assert "total_permissions" in role_info
            assert "permissions" in role_info

            assert isinstance(role_info["permissions"], list)
            assert role_info["total_permissions"] >= role_info["direct_permissions"]

    def test_get_role_summary_inheritance(self):
        """Test that role summary shows correct inheritance."""
        summary = get_role_summary()

        assert summary["viewer"]["inherits_from"] is None
        assert summary["user"]["inherits_from"] == "viewer"
        assert summary["manager"]["inherits_from"] == "user"
        assert summary["admin"]["inherits_from"] == "manager"

    def test_get_role_summary_permission_counts(self):
        """Test that permission counts increase with hierarchy."""
        summary = get_role_summary()

        # Higher roles should have more total permissions
        assert summary["user"]["total_permissions"] > summary["viewer"]["total_permissions"]
        assert summary["manager"]["total_permissions"] > summary["user"]["total_permissions"]
        assert summary["admin"]["total_permissions"] > summary["manager"]["total_permissions"]


class TestResourceTypes:
    """Tests for ResourceType enum."""

    def test_all_resource_types_defined(self):
        """Test that all expected resource types are defined."""
        expected_types = ["agents", "tasks", "knowledge", "memory", "users", "system"]

        for expected in expected_types:
            assert any(rt.value == expected for rt in ResourceType)

    def test_resource_type_values(self):
        """Test resource type string values."""
        assert ResourceType.AGENTS.value == "agents"
        assert ResourceType.TASKS.value == "tasks"
        assert ResourceType.KNOWLEDGE.value == "knowledge"
        assert ResourceType.MEMORY.value == "memory"
        assert ResourceType.USERS.value == "users"
        assert ResourceType.SYSTEM.value == "system"


class TestActions:
    """Tests for Action enum."""

    def test_all_actions_defined(self):
        """Test that all expected actions are defined."""
        expected_actions = ["create", "read", "update", "delete", "execute", "manage"]

        for expected in expected_actions:
            assert any(a.value == expected for a in Action)

    def test_action_values(self):
        """Test action string values."""
        assert Action.CREATE.value == "create"
        assert Action.READ.value == "read"
        assert Action.UPDATE.value == "update"
        assert Action.DELETE.value == "delete"
        assert Action.EXECUTE.value == "execute"
        assert Action.MANAGE.value == "manage"


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_permission_with_empty_description(self):
        """Test creating permission with empty description."""
        perm = Permission(ResourceType.AGENTS, Action.READ)
        assert perm.description == ""

    def test_role_definition_with_empty_permissions(self):
        """Test role definition with no permissions."""
        role_def = RoleDefinition(
            name=Role.VIEWER,
            display_name="Empty",
            description="Test",
            permissions=set(),
        )

        assert len(role_def.permissions) == 0
        assert not role_def.has_permission(ResourceType.AGENTS, Action.READ)

    def test_check_permission_with_none_scope(self):
        """Test checking permission with None scope."""
        # User has CREATE permission with None scope
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.CREATE, None)
        assert check_permission(Role.USER, ResourceType.AGENTS, Action.CREATE, "any_scope")
