"""Unit tests for Memory System permission filtering.

Tests cover:
- Agent Memory access control (private to agent owner)
- Company Memory access control (shared with filtering)
- User Context access control (private to user)
- Milvus filter expression building
- Post-query result filtering
- Write/delete permission checks

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 8.3: Data Access Control
- Task 2.2.9: Implement permission filtering for Memory System queries
"""

import pytest
from uuid import uuid4
from unittest.mock import patch

from access_control.memory_filter import (
    can_access_agent_memory,
    can_access_company_memory,
    build_agent_memory_filter,
    build_company_memory_filter,
    filter_memory_results,
    check_memory_write_permission,
    check_memory_delete_permission,
    MemoryType,
)
from access_control.rbac import Role, Action
from access_control.permissions import CurrentUser


# Test fixtures

@pytest.fixture
def admin_user():
    """Admin user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="admin",
        role=Role.ADMIN.value
    )


@pytest.fixture
def manager_user():
    """Manager user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="manager",
        role=Role.MANAGER.value
    )


@pytest.fixture
def regular_user():
    """Regular user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="user",
        role=Role.USER.value
    )


@pytest.fixture
def viewer_user():
    """Viewer user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="viewer",
        role=Role.VIEWER.value
    )


# Tests for can_access_agent_memory

def test_admin_can_access_any_agent_memory(admin_user):
    """Test that admin can access any agent's memory."""
    agent_id = str(uuid4())
    agent_owner_id = str(uuid4())
    
    assert can_access_agent_memory(admin_user, agent_id, agent_owner_id)


def test_manager_can_access_any_agent_memory(manager_user):
    """Test that manager can access any agent's memory."""
    agent_id = str(uuid4())
    agent_owner_id = str(uuid4())
    
    assert can_access_agent_memory(manager_user, agent_id, agent_owner_id)


def test_user_can_access_own_agent_memory(regular_user):
    """Test that user can access their own agent's memory."""
    agent_id = str(uuid4())
    
    assert can_access_agent_memory(
        regular_user, agent_id, regular_user.user_id
    )


def test_user_cannot_access_others_agent_memory(regular_user):
    """Test that user cannot access other users' agent memory."""
    agent_id = str(uuid4())
    other_user_id = str(uuid4())
    
    assert not can_access_agent_memory(
        regular_user, agent_id, other_user_id
    )


def test_viewer_cannot_access_agent_memory(viewer_user):
    """Test that viewer cannot access agent memory."""
    agent_id = str(uuid4())
    agent_owner_id = str(uuid4())
    
    assert not can_access_agent_memory(
        viewer_user, agent_id, agent_owner_id
    )


def test_invalid_role_denies_agent_memory_access():
    """Test that invalid role denies agent memory access."""
    invalid_user = CurrentUser(
        user_id=str(uuid4()),
        username="invalid",
        role="invalid_role"
    )
    agent_id = str(uuid4())
    agent_owner_id = str(uuid4())
    
    assert not can_access_agent_memory(
        invalid_user, agent_id, agent_owner_id
    )


# Tests for can_access_company_memory

def test_admin_can_access_all_company_memory(admin_user):
    """Test that admin can access all company memory."""
    assert can_access_company_memory(
        admin_user, MemoryType.USER_CONTEXT, str(uuid4())
    )
    assert can_access_company_memory(
        admin_user, "task_context"
    )
    assert can_access_company_memory(
        admin_user, "general"
    )


def test_manager_can_access_all_company_memory(manager_user):
    """Test that manager can access all company memory."""
    assert can_access_company_memory(
        manager_user, MemoryType.USER_CONTEXT, str(uuid4())
    )
    assert can_access_company_memory(
        manager_user, "task_context"
    )


def test_user_can_access_own_user_context(regular_user):
    """Test that user can access their own user context."""
    assert can_access_company_memory(
        regular_user,
        MemoryType.USER_CONTEXT,
        regular_user.user_id
    )


def test_user_cannot_access_others_user_context(regular_user):
    """Test that user cannot access other users' context."""
    other_user_id = str(uuid4())
    
    assert not can_access_company_memory(
        regular_user,
        MemoryType.USER_CONTEXT,
        other_user_id
    )


def test_user_can_access_general_company_memory(regular_user):
    """Test that user can access general company memory."""
    assert can_access_company_memory(
        regular_user,
        "general"
    )


def test_user_can_access_task_context(regular_user):
    """Test that user can access task context."""
    assert can_access_company_memory(
        regular_user,
        "task_context"
    )


def test_viewer_cannot_access_user_context(viewer_user):
    """Test that viewer cannot access user context."""
    assert not can_access_company_memory(
        viewer_user,
        MemoryType.USER_CONTEXT,
        viewer_user.user_id
    )


@patch('access_control.memory_filter.evaluate_abac_access')
def test_abac_policy_grants_company_memory_access(mock_abac, regular_user):
    """Test that ABAC policy can grant company memory access."""
    mock_abac.return_value = True
    
    user_attrs = {"clearance_level": 3}
    resource_attrs = {"required_clearance": 2}
    
    result = can_access_company_memory(
        regular_user,
        "confidential",
        user_attributes=user_attrs,
        resource_attributes=resource_attrs
    )
    
    mock_abac.assert_called_once()
    assert result


# Tests for build_agent_memory_filter

def test_agent_memory_filter_admin_no_restrictions(admin_user):
    """Test that admin has no agent memory filter restrictions."""
    filter_expr = build_agent_memory_filter(admin_user)
    
    assert filter_expr == ""


def test_agent_memory_filter_with_agent_id(admin_user):
    """Test agent memory filter with specific agent ID."""
    agent_id = str(uuid4())
    filter_expr = build_agent_memory_filter(admin_user, agent_id=agent_id)
    
    assert f'agent_id == "{agent_id}"' in filter_expr


def test_agent_memory_filter_user_requires_agent_id(regular_user):
    """Test that user requires agent_id for filtering."""
    filter_expr = build_agent_memory_filter(regular_user)
    
    # Should return restrictive filter without agent_id
    assert filter_expr == "id == -1"


def test_agent_memory_filter_invalid_role(regular_user):
    """Test agent memory filter with invalid role."""
    invalid_user = CurrentUser(
        user_id=str(uuid4()),
        username="invalid",
        role="invalid_role"
    )
    
    filter_expr = build_agent_memory_filter(invalid_user)
    
    assert filter_expr == "id == -1"


# Tests for build_company_memory_filter

def test_company_memory_filter_admin_no_restrictions(admin_user):
    """Test that admin has no company memory filter restrictions."""
    filter_expr = build_company_memory_filter(admin_user)
    
    assert filter_expr == ""


def test_company_memory_filter_admin_with_memory_type(admin_user):
    """Test admin filter with specific memory type."""
    filter_expr = build_company_memory_filter(
        admin_user,
        memory_type="task_context"
    )
    
    assert 'memory_type == "task_context"' in filter_expr


def test_company_memory_filter_user_includes_own_context(regular_user):
    """Test that user filter includes their own user context."""
    filter_expr = build_company_memory_filter(regular_user)
    
    assert MemoryType.USER_CONTEXT in filter_expr
    assert regular_user.user_id in filter_expr


def test_company_memory_filter_user_includes_general_memories(regular_user):
    """Test that user filter includes general company memories."""
    filter_expr = build_company_memory_filter(regular_user)
    
    assert "task_context" in filter_expr or "general" in filter_expr


def test_company_memory_filter_with_additional_filters(regular_user):
    """Test company memory filter with additional constraints."""
    additional = 'timestamp > 1234567890'
    filter_expr = build_company_memory_filter(
        regular_user,
        additional_filters=additional
    )
    
    assert additional in filter_expr
    assert " and " in filter_expr


def test_company_memory_filter_specific_memory_type(regular_user):
    """Test filter with specific memory type."""
    filter_expr = build_company_memory_filter(
        regular_user,
        memory_type="task_context"
    )
    
    assert "task_context" in filter_expr


# Tests for filter_memory_results

def test_filter_agent_memory_results_admin_returns_all(admin_user):
    """Test that admin gets all agent memory results."""
    results = [
        {
            "memory_id": "m1",
            "agent_id": str(uuid4()),
            "agent_owner_id": str(uuid4()),
            "content": "memory 1"
        },
        {
            "memory_id": "m2",
            "agent_id": str(uuid4()),
            "agent_owner_id": str(uuid4()),
            "content": "memory 2"
        }
    ]
    
    filtered = filter_memory_results(
        results, admin_user, MemoryType.AGENT_MEMORY
    )
    
    assert len(filtered) == 2


def test_filter_agent_memory_results_user_filters_by_ownership(regular_user):
    """Test that user only gets their own agent memories."""
    results = [
        {
            "memory_id": "m1",
            "agent_id": str(uuid4()),
            "agent_owner_id": regular_user.user_id,
            "content": "my agent memory"
        },
        {
            "memory_id": "m2",
            "agent_id": str(uuid4()),
            "agent_owner_id": str(uuid4()),
            "content": "other agent memory"
        }
    ]
    
    filtered = filter_memory_results(
        results, regular_user, MemoryType.AGENT_MEMORY
    )
    
    assert len(filtered) == 1
    assert filtered[0]["memory_id"] == "m1"


def test_filter_company_memory_results_user_context(regular_user):
    """Test filtering company memory with user context."""
    results = [
        {
            "memory_id": "m1",
            "memory_type": MemoryType.USER_CONTEXT,
            "user_id": regular_user.user_id,
            "content": "my context"
        },
        {
            "memory_id": "m2",
            "memory_type": MemoryType.USER_CONTEXT,
            "user_id": str(uuid4()),
            "content": "other context"
        },
        {
            "memory_id": "m3",
            "memory_type": "general",
            "user_id": None,
            "content": "general memory"
        }
    ]
    
    filtered = filter_memory_results(
        results, regular_user, MemoryType.COMPANY_MEMORY
    )
    
    # Should get own user context (m1) and general memory (m3)
    assert len(filtered) == 2
    memory_ids = {r["memory_id"] for r in filtered}
    assert "m1" in memory_ids
    assert "m3" in memory_ids


def test_filter_memory_results_empty_list(regular_user):
    """Test filtering empty results list."""
    filtered = filter_memory_results(
        [], regular_user, MemoryType.AGENT_MEMORY
    )
    
    assert filtered == []


# Tests for check_memory_write_permission

def test_admin_can_write_any_memory(admin_user):
    """Test that admin can write any memory."""
    assert check_memory_write_permission(
        admin_user, MemoryType.AGENT_MEMORY
    )
    assert check_memory_write_permission(
        admin_user, MemoryType.COMPANY_MEMORY
    )


def test_user_can_write_own_agent_memory(regular_user):
    """Test that user can write their own agent's memory."""
    agent_id = str(uuid4())
    
    assert check_memory_write_permission(
        regular_user,
        MemoryType.AGENT_MEMORY,
        agent_id=agent_id,
        agent_owner_id=regular_user.user_id
    )


def test_user_cannot_write_others_agent_memory(regular_user):
    """Test that user cannot write other users' agent memory."""
    agent_id = str(uuid4())
    other_user_id = str(uuid4())
    
    assert not check_memory_write_permission(
        regular_user,
        MemoryType.AGENT_MEMORY,
        agent_id=agent_id,
        agent_owner_id=other_user_id
    )


def test_user_can_write_company_memory(regular_user):
    """Test that user can write company memory."""
    assert check_memory_write_permission(
        regular_user,
        MemoryType.COMPANY_MEMORY
    )


def test_viewer_cannot_write_memory(viewer_user):
    """Test that viewer cannot write memory."""
    assert not check_memory_write_permission(
        viewer_user,
        MemoryType.AGENT_MEMORY
    )
    assert not check_memory_write_permission(
        viewer_user,
        MemoryType.COMPANY_MEMORY
    )


# Tests for check_memory_delete_permission

def test_admin_can_delete_any_memory(admin_user):
    """Test that admin can delete any memory."""
    assert check_memory_delete_permission(
        admin_user,
        MemoryType.AGENT_MEMORY,
        agent_owner_id=str(uuid4())
    )
    assert check_memory_delete_permission(
        admin_user,
        MemoryType.COMPANY_MEMORY,
        memory_user_id=str(uuid4())
    )


def test_user_can_delete_own_agent_memory(regular_user):
    """Test that user can delete their own agent's memory."""
    assert check_memory_delete_permission(
        regular_user,
        MemoryType.AGENT_MEMORY,
        agent_owner_id=regular_user.user_id
    )


def test_user_cannot_delete_others_agent_memory(regular_user):
    """Test that user cannot delete other users' agent memory."""
    other_user_id = str(uuid4())
    
    assert not check_memory_delete_permission(
        regular_user,
        MemoryType.AGENT_MEMORY,
        agent_owner_id=other_user_id
    )


def test_user_can_delete_own_company_memory(regular_user):
    """Test that user can delete their own company memory."""
    assert check_memory_delete_permission(
        regular_user,
        MemoryType.COMPANY_MEMORY,
        memory_user_id=regular_user.user_id
    )


def test_user_cannot_delete_others_company_memory(regular_user):
    """Test that user cannot delete other users' company memory."""
    other_user_id = str(uuid4())
    
    assert not check_memory_delete_permission(
        regular_user,
        MemoryType.COMPANY_MEMORY,
        memory_user_id=other_user_id
    )


def test_viewer_cannot_delete_memory(viewer_user):
    """Test that viewer cannot delete memory."""
    assert not check_memory_delete_permission(
        viewer_user,
        MemoryType.AGENT_MEMORY,
        agent_owner_id=viewer_user.user_id
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
