"""
Unit tests for Department Management API Routes.

Tests CRUD operations, resource endpoints, and access control
for the departments router.

References:
- Spec: .kiro/specs/department-management/
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from api_gateway.routers.departments import (
    DepartmentCreate,
    DepartmentResponse,
    DepartmentUpdate,
    _build_tree,
    _department_to_response,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────


def _make_dept(
    name="Engineering",
    code="eng",
    parent_id=None,
    manager=None,
    manager_id=None,
    status="active",
    sort_order=0,
    description="Engineering department",
):
    """Create a mock Department object."""
    dept = MagicMock()
    dept.department_id = uuid.uuid4()
    dept.name = name
    dept.code = code
    dept.description = description
    dept.parent_id = parent_id
    dept.manager_id = manager_id
    dept.manager = manager
    dept.status = status
    dept.sort_order = sort_order
    dept.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    dept.updated_at = datetime(2024, 1, 2, tzinfo=timezone.utc)
    return dept


# ─── Schema Validation Tests ──────────────────────────────────────────────


class TestDepartmentSchemas:
    """Test Pydantic schema validation."""

    def test_create_valid(self):
        data = DepartmentCreate(name="Engineering", code="eng")
        assert data.name == "Engineering"
        assert data.code == "eng"
        assert data.description is None
        assert data.parent_id is None
        assert data.sort_order == 0

    def test_create_with_all_fields(self):
        parent = uuid.uuid4()
        manager = uuid.uuid4()
        data = DepartmentCreate(
            name="Backend Team",
            code="backend-team",
            description="Backend engineering",
            parent_id=parent,
            manager_id=manager,
            sort_order=10,
        )
        assert data.parent_id == parent
        assert data.manager_id == manager
        assert data.sort_order == 10

    def test_create_invalid_code(self):
        with pytest.raises(Exception):
            DepartmentCreate(name="Test", code="has spaces")

    def test_create_empty_name(self):
        with pytest.raises(Exception):
            DepartmentCreate(name="", code="test")

    def test_create_code_with_special_chars(self):
        """Code allows alphanumeric, hyphens, and underscores."""
        data = DepartmentCreate(name="Test", code="my_dept-01")
        assert data.code == "my_dept-01"

    def test_update_partial(self):
        data = DepartmentUpdate(name="New Name")
        assert data.name == "New Name"
        assert data.description is None
        assert data.status is None

    def test_update_status_valid(self):
        data = DepartmentUpdate(status="archived")
        assert data.status == "archived"

    def test_update_status_invalid(self):
        with pytest.raises(Exception):
            DepartmentUpdate(status="deleted")


# ─── Helper Function Tests ────────────────────────────────────────────────


class TestDepartmentToResponse:
    """Test _department_to_response helper."""

    def test_basic_conversion(self):
        dept = _make_dept()
        result = _department_to_response(dept)

        assert result["name"] == "Engineering"
        assert result["code"] == "eng"
        assert result["description"] == "Engineering department"
        assert result["status"] == "active"
        assert result["sort_order"] == 0
        assert result["member_count"] == 0
        assert result["agent_count"] == 0
        assert result["knowledge_count"] == 0
        assert result["children"] == []
        assert result["parent_id"] is None
        assert result["manager_id"] is None
        assert result["manager_name"] is None

    def test_with_manager(self):
        manager = MagicMock()
        manager.username = "jdoe"
        manager.attributes = {"display_name": "John Doe"}
        manager_id = uuid.uuid4()

        dept = _make_dept(manager=manager, manager_id=manager_id)
        result = _department_to_response(dept)

        assert result["manager_id"] == str(manager_id)
        assert result["manager_name"] == "John Doe"

    def test_with_manager_no_display_name(self):
        manager = MagicMock()
        manager.username = "jdoe"
        manager.attributes = {}
        manager_id = uuid.uuid4()

        dept = _make_dept(manager=manager, manager_id=manager_id)
        result = _department_to_response(dept)

        assert result["manager_name"] == "jdoe"

    def test_with_counts(self):
        dept = _make_dept()
        result = _department_to_response(dept, member_count=5, agent_count=3, knowledge_count=10)

        assert result["member_count"] == 5
        assert result["agent_count"] == 3
        assert result["knowledge_count"] == 10

    def test_with_parent_id(self):
        parent_id = uuid.uuid4()
        dept = _make_dept(parent_id=parent_id)
        result = _department_to_response(dept)

        assert result["parent_id"] == str(parent_id)

    def test_timestamps_isoformat(self):
        dept = _make_dept()
        result = _department_to_response(dept)

        assert "2024-01-01" in result["created_at"]
        assert "2024-01-02" in result["updated_at"]


class TestBuildTree:
    """Test _build_tree helper for hierarchical department view."""

    def test_flat_departments(self):
        """All root-level departments."""
        dept1 = _make_dept(name="Eng", code="eng")
        dept2 = _make_dept(name="Sales", code="sales")
        counts = {
            str(dept1.department_id): {"members": 5, "agents": 2, "knowledge": 3},
            str(dept2.department_id): {"members": 3, "agents": 1, "knowledge": 1},
        }

        tree = _build_tree([dept1, dept2], counts)
        assert len(tree) == 2
        assert tree[0]["name"] == "Eng"
        assert tree[0]["member_count"] == 5
        assert tree[1]["name"] == "Sales"

    def test_parent_child_structure(self):
        """Parent department with children."""
        parent = _make_dept(name="Engineering", code="eng")
        child = _make_dept(
            name="Backend",
            code="backend",
            parent_id=parent.department_id,
        )
        counts = {
            str(parent.department_id): {"members": 0, "agents": 0, "knowledge": 0},
            str(child.department_id): {"members": 3, "agents": 1, "knowledge": 0},
        }

        tree = _build_tree([parent, child], counts)
        assert len(tree) == 1
        assert tree[0]["name"] == "Engineering"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["name"] == "Backend"
        assert tree[0]["children"][0]["member_count"] == 3

    def test_orphan_child(self):
        """Child whose parent_id doesn't match any department is treated as root."""
        orphan = _make_dept(
            name="Orphan",
            code="orphan",
            parent_id=uuid.uuid4(),
        )
        counts = {
            str(orphan.department_id): {"members": 0, "agents": 0, "knowledge": 0},
        }

        tree = _build_tree([orphan], counts)
        assert len(tree) == 1
        assert tree[0]["name"] == "Orphan"

    def test_empty_list(self):
        tree = _build_tree([], {})
        assert tree == []


# ─── Response Model Tests ─────────────────────────────────────────────────


class TestDepartmentResponseModel:
    """Test DepartmentResponse Pydantic model."""

    def test_from_dict(self):
        dept = _make_dept()
        data = _department_to_response(dept, member_count=2, agent_count=1)
        response = DepartmentResponse(**data)

        assert response.name == "Engineering"
        assert response.code == "eng"
        assert response.member_count == 2
        assert response.agent_count == 1
        assert response.children == []

    def test_defaults(self):
        response = DepartmentResponse(
            department_id=str(uuid.uuid4()),
            name="Test",
            code="test",
            status="active",
            sort_order=0,
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
        )
        assert response.member_count == 0
        assert response.agent_count == 0
        assert response.knowledge_count == 0
        assert response.children == []
        assert response.description is None
        assert response.parent_id is None
        assert response.manager_id is None
        assert response.manager_name is None
