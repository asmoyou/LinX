"""Unit tests for Knowledge Base permission filtering.

Tests cover:
- RBAC-based filtering for different roles
- Access level filtering (private, team, public)
- ABAC policy evaluation
- PostgreSQL query filtering
- Milvus filter expression building
- Post-query result filtering

References:
- Requirements 14: User-Based Access Control
- Design Section 8.3: Data Access Control
- Task 2.2.8: Implement permission filtering for Knowledge Base queries
"""

from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest

from access_control.knowledge_filter import (
    KnowledgeAccessLevel,
    build_milvus_filter_expr,
    can_access_knowledge_item,
    check_knowledge_delete_permission,
    check_knowledge_write_permission,
    filter_knowledge_query,
    filter_knowledge_results,
    get_accessible_knowledge_ids,
)
from access_control.permissions import CurrentUser
from access_control.rbac import Action, Role

# Test fixtures


@pytest.fixture
def admin_user():
    """Admin user fixture."""
    return CurrentUser(user_id=str(uuid4()), username="admin", role=Role.ADMIN.value)


@pytest.fixture
def manager_user():
    """Manager user fixture."""
    return CurrentUser(user_id=str(uuid4()), username="manager", role=Role.MANAGER.value)


@pytest.fixture
def regular_user():
    """Regular user fixture."""
    return CurrentUser(user_id=str(uuid4()), username="user", role=Role.USER.value)


@pytest.fixture
def viewer_user():
    """Viewer user fixture."""
    return CurrentUser(user_id=str(uuid4()), username="viewer", role=Role.VIEWER.value)


@pytest.fixture
def engineering_user():
    """User in engineering department."""
    return CurrentUser(user_id=str(uuid4()), username="eng_user", role=Role.USER.value)


@pytest.fixture
def engineering_attributes():
    """Engineering department attributes."""
    return {"department": "engineering", "clearance_level": 2}


@pytest.fixture
def hr_attributes():
    """HR department attributes."""
    return {"department": "hr", "clearance_level": 1}


# Tests for can_access_knowledge_item


def test_admin_can_access_all_knowledge(admin_user):
    """Test that admin can access all knowledge items regardless of access level."""
    owner_id = str(uuid4())

    # Test private knowledge
    assert can_access_knowledge_item(
        admin_user, Action.READ, owner_id, KnowledgeAccessLevel.PRIVATE
    )

    # Test team knowledge
    assert can_access_knowledge_item(admin_user, Action.READ, owner_id, KnowledgeAccessLevel.TEAM)

    # Test public knowledge
    assert can_access_knowledge_item(admin_user, Action.READ, owner_id, KnowledgeAccessLevel.PUBLIC)


def test_manager_can_access_all_knowledge(manager_user):
    """Test that manager can access all knowledge items."""
    owner_id = str(uuid4())

    assert can_access_knowledge_item(
        manager_user, Action.READ, owner_id, KnowledgeAccessLevel.PRIVATE
    )
    assert can_access_knowledge_item(manager_user, Action.READ, owner_id, KnowledgeAccessLevel.TEAM)
    assert can_access_knowledge_item(
        manager_user, Action.READ, owner_id, KnowledgeAccessLevel.PUBLIC
    )


def test_user_can_access_own_knowledge(regular_user):
    """Test that user can access their own knowledge items."""
    # User's own knowledge
    assert can_access_knowledge_item(
        regular_user, Action.READ, regular_user.user_id, KnowledgeAccessLevel.PRIVATE
    )

    # Someone else's private knowledge
    other_user_id = str(uuid4())
    assert not can_access_knowledge_item(
        regular_user, Action.READ, other_user_id, KnowledgeAccessLevel.PRIVATE
    )


def test_user_can_access_public_knowledge(regular_user):
    """Test that user can access public knowledge."""
    owner_id = str(uuid4())

    assert can_access_knowledge_item(
        regular_user, Action.READ, owner_id, KnowledgeAccessLevel.PUBLIC
    )


def test_user_can_access_team_knowledge_with_matching_department(
    engineering_user, engineering_attributes
):
    """Test that user can access team knowledge if department matches."""
    owner_id = str(uuid4())
    resource_attrs = {"department": "engineering", "classification": "internal"}

    assert can_access_knowledge_item(
        engineering_user,
        Action.READ,
        owner_id,
        KnowledgeAccessLevel.TEAM,
        user_attributes=engineering_attributes,
        resource_attributes=resource_attrs,
    )


def test_user_cannot_access_team_knowledge_with_different_department(
    engineering_user, engineering_attributes
):
    """Test that user cannot access team knowledge if department doesn't match."""
    owner_id = str(uuid4())
    resource_attrs = {"department": "hr", "classification": "internal"}  # Different department

    assert not can_access_knowledge_item(
        engineering_user,
        Action.READ,
        owner_id,
        KnowledgeAccessLevel.TEAM,
        user_attributes=engineering_attributes,
        resource_attributes=resource_attrs,
    )


def test_viewer_can_read_public_knowledge(viewer_user):
    """Test that viewer can read public knowledge."""
    owner_id = str(uuid4())

    assert can_access_knowledge_item(
        viewer_user, Action.READ, owner_id, KnowledgeAccessLevel.PUBLIC
    )


def test_viewer_cannot_access_private_knowledge(viewer_user):
    """Test that viewer cannot access private knowledge."""
    owner_id = str(uuid4())

    assert not can_access_knowledge_item(
        viewer_user, Action.READ, owner_id, KnowledgeAccessLevel.PRIVATE
    )


def test_invalid_role_denies_access():
    """Test that invalid role denies access."""
    invalid_user = CurrentUser(user_id=str(uuid4()), username="invalid", role="invalid_role")
    owner_id = str(uuid4())

    assert not can_access_knowledge_item(
        invalid_user, Action.READ, owner_id, KnowledgeAccessLevel.PUBLIC
    )


@patch("access_control.knowledge_filter.evaluate_abac_access")
def test_abac_policy_grants_access(mock_abac, regular_user):
    """Test that ABAC policy can grant access."""
    mock_abac.return_value = True

    owner_id = str(uuid4())
    user_attrs = {"clearance_level": 3}
    resource_attrs = {"required_clearance": 2}

    # User doesn't own it and it's private, but ABAC grants access
    result = can_access_knowledge_item(
        regular_user,
        Action.READ,
        owner_id,
        KnowledgeAccessLevel.PRIVATE,
        user_attributes=user_attrs,
        resource_attributes=resource_attrs,
    )

    # ABAC should be called
    mock_abac.assert_called_once()
    assert result


# Tests for filter_knowledge_query


def test_filter_query_admin_no_filtering(admin_user):
    """Test that admin query is not filtered."""
    mock_query = Mock()

    result = filter_knowledge_query(mock_query, admin_user)

    # Query should not be modified
    assert result == mock_query
    mock_query.filter.assert_not_called()


def test_filter_query_manager_no_filtering(manager_user):
    """Test that manager query is not filtered."""
    mock_query = Mock()

    result = filter_knowledge_query(mock_query, manager_user)

    assert result == mock_query
    mock_query.filter.assert_not_called()


def test_filter_query_user_filters_by_ownership_and_access_level(regular_user):
    """Test that user query is filtered by ownership and access level."""
    mock_query = Mock()
    mock_filtered = Mock()
    mock_query.filter.return_value = mock_filtered

    result = filter_knowledge_query(mock_query, regular_user)

    # Query should be filtered
    mock_query.filter.assert_called_once()
    assert result == mock_filtered


def test_filter_query_viewer_filters_by_permitted_scope(viewer_user):
    """Test that viewer query is filtered by permitted scope."""
    mock_query = Mock()
    mock_filtered = Mock()
    mock_query.filter.return_value = mock_filtered

    result = filter_knowledge_query(mock_query, viewer_user)

    # Query should be filtered
    mock_query.filter.assert_called_once()
    assert result == mock_filtered


def test_filter_query_invalid_role_returns_empty(regular_user):
    """Test that invalid role returns empty result set."""
    invalid_user = CurrentUser(user_id=str(uuid4()), username="invalid", role="invalid_role")
    mock_query = Mock()
    mock_filtered = Mock()
    mock_query.filter.return_value = mock_filtered

    result = filter_knowledge_query(mock_query, invalid_user)

    # Should filter with False (no results)
    mock_query.filter.assert_called_once_with(False)


# Tests for build_milvus_filter_expr


def test_milvus_filter_admin_no_restrictions(admin_user):
    """Test that admin has no Milvus filter restrictions."""
    filter_expr = build_milvus_filter_expr(admin_user)

    assert filter_expr == ""


def test_milvus_filter_manager_no_restrictions(manager_user):
    """Test that manager has no Milvus filter restrictions."""
    filter_expr = build_milvus_filter_expr(manager_user)

    assert filter_expr == ""


def test_milvus_filter_user_includes_own_and_public(regular_user):
    """Test that user filter includes own and public knowledge."""
    filter_expr = build_milvus_filter_expr(regular_user)

    # Should include owner_user_id and public access_level
    assert f'owner_user_id == "{regular_user.user_id}"' in filter_expr
    assert f'access_level == "{KnowledgeAccessLevel.PUBLIC}"' in filter_expr
    assert " or " in filter_expr


def test_milvus_filter_user_includes_team_with_department(engineering_user, engineering_attributes):
    """Test that user filter includes team knowledge when department provided."""
    filter_expr = build_milvus_filter_expr(engineering_user, user_attributes=engineering_attributes)

    # Should include team access level
    assert f'access_level == "{KnowledgeAccessLevel.TEAM}"' in filter_expr


def test_milvus_filter_viewer_only_public(viewer_user):
    """Test that viewer filter only includes public knowledge."""
    filter_expr = build_milvus_filter_expr(viewer_user)

    # Should only include public
    assert f'access_level == "{KnowledgeAccessLevel.PUBLIC}"' in filter_expr


def test_milvus_filter_combines_with_additional_filters(regular_user):
    """Test that Milvus filter combines with additional filters."""
    additional = 'content_type == "document"'
    filter_expr = build_milvus_filter_expr(regular_user, additional_filters=additional)

    # Should combine with AND
    assert additional in filter_expr
    assert " and " in filter_expr


def test_milvus_filter_invalid_role_matches_nothing():
    """Test that invalid role creates filter that matches nothing."""
    invalid_user = CurrentUser(user_id=str(uuid4()), username="invalid", role="invalid_role")

    filter_expr = build_milvus_filter_expr(invalid_user)

    assert filter_expr == "id == -1"


# Tests for filter_knowledge_results


def test_filter_results_admin_returns_all(admin_user):
    """Test that admin gets all results."""
    results = [
        {
            "knowledge_id": "k1",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.PRIVATE,
            "metadata": {},
        },
        {
            "knowledge_id": "k2",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.PUBLIC,
            "metadata": {},
        },
    ]

    filtered = filter_knowledge_results(results, admin_user)

    assert len(filtered) == 2


def test_filter_results_user_filters_by_ownership(regular_user):
    """Test that user only gets own and public knowledge."""
    results = [
        {
            "knowledge_id": "k1",
            "owner_user_id": regular_user.user_id,
            "access_level": KnowledgeAccessLevel.PRIVATE,
            "metadata": {},
        },
        {
            "knowledge_id": "k2",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.PRIVATE,
            "metadata": {},
        },
        {
            "knowledge_id": "k3",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.PUBLIC,
            "metadata": {},
        },
    ]

    filtered = filter_knowledge_results(results, regular_user)

    # Should get own private (k1) and public (k3)
    assert len(filtered) == 2
    knowledge_ids = [r["knowledge_id"] for r in filtered]
    assert "k1" in knowledge_ids
    assert "k3" in knowledge_ids


def test_filter_results_team_knowledge_with_department(engineering_user, engineering_attributes):
    """Test that team knowledge is filtered by department."""
    results = [
        {
            "knowledge_id": "k1",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.TEAM,
            "metadata": {"department": "engineering"},
        },
        {
            "knowledge_id": "k2",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.TEAM,
            "metadata": {"department": "hr"},
        },
    ]

    filtered = filter_knowledge_results(
        results, engineering_user, user_attributes=engineering_attributes
    )

    # Should only get engineering team knowledge
    assert len(filtered) == 1
    assert filtered[0]["knowledge_id"] == "k1"


def test_filter_results_empty_list():
    """Test filtering empty results list."""
    regular_user = CurrentUser(user_id=str(uuid4()), username="user", role=Role.USER.value)

    filtered = filter_knowledge_results([], regular_user)

    assert filtered == []


# Tests for check_knowledge_write_permission


def test_admin_can_write_any_knowledge(admin_user):
    """Test that admin can write any knowledge."""
    other_user_id = str(uuid4())

    assert check_knowledge_write_permission(
        admin_user, knowledge_id="k1", owner_user_id=other_user_id
    )


def test_user_can_write_own_knowledge(regular_user):
    """Test that user can write their own knowledge."""
    assert check_knowledge_write_permission(
        regular_user, knowledge_id="k1", owner_user_id=regular_user.user_id
    )


def test_user_cannot_write_others_knowledge(regular_user):
    """Test that user cannot write others' knowledge."""
    other_user_id = str(uuid4())

    assert not check_knowledge_write_permission(
        regular_user, knowledge_id="k1", owner_user_id=other_user_id
    )


def test_user_can_create_new_knowledge(regular_user):
    """Test that user can create new knowledge."""
    assert check_knowledge_write_permission(
        regular_user, knowledge_id=None, owner_user_id=None  # New knowledge
    )


def test_viewer_cannot_write_knowledge(viewer_user):
    """Test that viewer cannot write knowledge."""
    assert not check_knowledge_write_permission(
        viewer_user, knowledge_id="k1", owner_user_id=viewer_user.user_id
    )


# Tests for check_knowledge_delete_permission


def test_admin_can_delete_any_knowledge(admin_user):
    """Test that admin can delete any knowledge."""
    other_user_id = str(uuid4())

    assert check_knowledge_delete_permission(admin_user, other_user_id)


def test_user_can_delete_own_knowledge(regular_user):
    """Test that user can delete their own knowledge."""
    assert check_knowledge_delete_permission(regular_user, regular_user.user_id)


def test_user_cannot_delete_others_knowledge(regular_user):
    """Test that user cannot delete others' knowledge."""
    other_user_id = str(uuid4())

    assert not check_knowledge_delete_permission(regular_user, other_user_id)


def test_viewer_cannot_delete_knowledge(viewer_user):
    """Test that viewer cannot delete knowledge."""
    assert not check_knowledge_delete_permission(viewer_user, viewer_user.user_id)


# Tests for get_accessible_knowledge_ids


def test_get_accessible_ids_admin_returns_none(admin_user):
    """Test that admin gets None (unrestricted access)."""
    result = get_accessible_knowledge_ids(admin_user)

    assert result is None


def test_get_accessible_ids_manager_returns_none(manager_user):
    """Test that manager gets None (unrestricted access)."""
    result = get_accessible_knowledge_ids(manager_user)

    assert result is None


def test_get_accessible_ids_user_returns_empty_list(regular_user):
    """Test that user gets empty list (use filter_knowledge_query instead)."""
    result = get_accessible_knowledge_ids(regular_user)

    assert result == []


# Integration-style tests


def test_complete_filtering_workflow_for_user(regular_user, engineering_attributes):
    """Test complete filtering workflow for a regular user."""
    # Simulate knowledge items
    all_knowledge = [
        {
            "knowledge_id": "k1",
            "owner_user_id": regular_user.user_id,
            "access_level": KnowledgeAccessLevel.PRIVATE,
            "metadata": {},
        },
        {
            "knowledge_id": "k2",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.PRIVATE,
            "metadata": {},
        },
        {
            "knowledge_id": "k3",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.PUBLIC,
            "metadata": {},
        },
        {
            "knowledge_id": "k4",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.TEAM,
            "metadata": {"department": "engineering"},
        },
        {
            "knowledge_id": "k5",
            "owner_user_id": str(uuid4()),
            "access_level": KnowledgeAccessLevel.TEAM,
            "metadata": {"department": "hr"},
        },
    ]

    # Filter results
    filtered = filter_knowledge_results(
        all_knowledge, regular_user, user_attributes=engineering_attributes
    )

    # Should get: k1 (own), k3 (public), k4 (team with matching dept)
    assert len(filtered) == 3
    knowledge_ids = {r["knowledge_id"] for r in filtered}
    assert knowledge_ids == {"k1", "k3", "k4"}


def test_milvus_filter_with_additional_constraints(regular_user):
    """Test Milvus filter with additional constraints."""
    additional = 'content_type == "document" and created_at > 1234567890'

    filter_expr = build_milvus_filter_expr(regular_user, additional_filters=additional)

    # Should include permission filters AND additional constraints
    assert f'owner_user_id == "{regular_user.user_id}"' in filter_expr
    assert f'access_level == "{KnowledgeAccessLevel.PUBLIC}"' in filter_expr
    assert additional in filter_expr
    assert filter_expr.count(" and ") >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
