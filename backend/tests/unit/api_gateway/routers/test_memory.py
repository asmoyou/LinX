"""Unit tests for Memory API Router.

Tests cover:
- List memories endpoint
- Get memory by ID
- Create memory
- Search memories
- Update memory
- Delete memory
- Share memory
- Memory stats
- Shared memories
- Validation and error handling

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 6: Memory System Design
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from access_control.permissions import CurrentUser
from access_control.rbac import Role
from api_gateway.main import app
from memory_system.memory_interface import MemoryItem, MemoryType


@pytest.fixture
def mock_current_user():
    """Mock authenticated user."""
    return CurrentUser(
        user_id="test-user-id",
        username="testuser",
        role=Role.USER.value,
        token_jti="test-jti",
    )


@pytest.fixture
def mock_admin_user():
    """Mock admin user."""
    return CurrentUser(
        user_id="admin-user-id",
        username="admin",
        role=Role.ADMIN.value,
        token_jti="admin-jti",
    )


@pytest.fixture
def sample_memory_item():
    """Create a sample MemoryItem."""
    return MemoryItem(
        id=1,
        content="Test memory content",
        memory_type=MemoryType.COMPANY,
        user_id="test-user-id",
        timestamp=datetime(2026, 1, 15, 12, 0, 0),
        metadata={"tags": ["test", "sample"], "summary": "Test summary"},
        similarity_score=0.95,
    )


@pytest.fixture
def sample_agent_memory():
    """Create a sample agent MemoryItem."""
    return MemoryItem(
        id=2,
        content="Agent learning data",
        memory_type=MemoryType.AGENT,
        agent_id="agent-123",
        timestamp=datetime(2026, 1, 15, 12, 0, 0),
        metadata={"tags": ["learning"]},
        similarity_score=0.87,
    )


@pytest.fixture
def mock_memory_system(sample_memory_item, sample_agent_memory):
    """Mock the MemorySystem singleton."""
    mock = MagicMock()
    mock.retrieve_memories.return_value = [sample_memory_item]
    mock.store_memory.return_value = 42
    mock.delete_memory.return_value = True
    mock.share_memory.return_value = True
    mock.get_memory_stats.return_value = {
        "agent_memories": {"row_count": 10},
        "company_memories": {"row_count": 25},
    }
    return mock


@pytest.fixture
def mock_db_session():
    """Mock database session with agent/user lookups."""
    session = MagicMock()

    # Mock user query
    mock_user = MagicMock()
    mock_user.username = "testuser"
    mock_user.attributes = {"display_name": "Test User"}

    # Mock agent query
    mock_agent = MagicMock()
    mock_agent.name = "Test Agent"

    def query_side_effect(model):
        q = MagicMock()
        if model.__name__ == "User":
            q.filter.return_value.first.return_value = mock_user
        elif model.__name__ == "Agent":
            q.filter.return_value.first.return_value = mock_agent
        return q

    session.query.side_effect = query_side_effect
    return session


class TestListMemories:
    """Test GET /api/v1/memories endpoint registration."""

    def test_list_endpoint_registered(self):
        """Verify GET /memories is registered."""
        route_paths = [(r.path, r.methods) for r in app.routes if hasattr(r, "methods")]
        get_memories = [
            (path, methods)
            for path, methods in route_paths
            if path == "/api/v1/memories" and "GET" in methods
        ]
        assert len(get_memories) == 1

    def test_post_endpoint_registered(self):
        """Verify POST /memories is registered."""
        route_paths = [(r.path, r.methods) for r in app.routes if hasattr(r, "methods")]
        post_memories = [
            (path, methods)
            for path, methods in route_paths
            if path == "/api/v1/memories" and "POST" in methods
        ]
        assert len(post_memories) == 1

    def test_unauthenticated_list_returns_401_or_403(self):
        """Unauthenticated request should be rejected."""
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/v1/memories")
        assert response.status_code in (401, 403)


class TestCreateMemory:
    """Test POST /api/v1/memories."""

    def test_create_memory_validation_empty_content(self):
        """Ensure empty content is rejected by Pydantic."""
        from api_gateway.routers.memory import MemoryCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MemoryCreate(type="company", content="")

    def test_create_memory_validation_invalid_type(self):
        """Ensure invalid type is rejected."""
        from api_gateway.routers.memory import MemoryCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MemoryCreate(type="invalid_type", content="Some content")

    def test_create_memory_valid(self):
        """Test valid memory creation schema."""
        from api_gateway.routers.memory import MemoryCreate

        mem = MemoryCreate(
            type="company",
            content="Valid content",
            summary="A summary",
            tags=["tag1", "tag2"],
        )
        assert mem.type == "company"
        assert mem.content == "Valid content"
        assert mem.tags == ["tag1", "tag2"]


class TestSearchMemories:
    """Test POST /api/v1/memories/search."""

    def test_search_validation_empty_query(self):
        """Ensure empty query is rejected."""
        from api_gateway.routers.memory import MemorySearchRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MemorySearchRequest(query="")

    def test_search_validation_valid(self):
        """Test valid search request."""
        from api_gateway.routers.memory import MemorySearchRequest

        req = MemorySearchRequest(query="test search", type="agent", limit=20)
        assert req.query == "test search"
        assert req.type == "agent"
        assert req.limit == 20

    def test_search_validation_limit_bounds(self):
        """Test limit validation."""
        from api_gateway.routers.memory import MemorySearchRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MemorySearchRequest(query="test", limit=0)

        with pytest.raises(ValidationError):
            MemorySearchRequest(query="test", limit=200)


class TestShareMemory:
    """Test POST /api/v1/memories/{memory_id}/share."""

    def test_share_validation_empty_targets_allowed(self):
        """Empty target list is allowed for clearing share settings."""
        from api_gateway.routers.memory import MemoryShareRequest

        req = MemoryShareRequest(user_ids=[], agent_ids=[])
        assert req.user_ids == []
        assert req.agent_ids == []

    def test_share_validation_valid(self):
        """Test valid share request."""
        from api_gateway.routers.memory import MemoryShareRequest

        req = MemoryShareRequest(user_ids=["user-1"], agent_ids=["agent-1", "agent-2"])
        assert len(req.user_ids) == 1
        assert len(req.agent_ids) == 2


class TestMemoryUpdate:
    """Test PUT /api/v1/memories/{memory_id}."""

    def test_update_schema_all_optional(self):
        """All fields in update schema should be optional."""
        from api_gateway.routers.memory import MemoryUpdate

        update = MemoryUpdate()
        assert update.content is None
        assert update.summary is None
        assert update.tags is None
        assert update.metadata is None

    def test_update_schema_with_values(self):
        """Test update with values."""
        from api_gateway.routers.memory import MemoryUpdate

        update = MemoryUpdate(
            content="Updated content",
            tags=["new-tag"],
        )
        assert update.content == "Updated content"
        assert update.tags == ["new-tag"]


class TestMemoryResponse:
    """Test MemoryResponse schema."""

    def test_response_model(self):
        """Test response model creation."""
        from api_gateway.routers.memory import MemoryResponse

        resp = MemoryResponse(
            id="1",
            type="company",
            content="Test content",
            createdAt="2026-01-15T12:00:00",
            tags=["tag1"],
            isShared=False,
        )
        assert resp.id == "1"
        assert resp.type == "company"
        assert resp.tags == ["tag1"]

    def test_response_defaults(self):
        """Test response model default values."""
        from api_gateway.routers.memory import MemoryResponse

        resp = MemoryResponse(
            id="1",
            type="agent",
            content="Content",
            createdAt="2026-01-15T12:00:00",
        )
        assert resp.tags == []
        assert resp.shared_with == []
        assert resp.is_shared is False
        assert resp.relevance_score is None


class TestMemoryIndexInspectResponse:
    """Test MemoryIndexInspectResponse schema."""

    def test_index_inspect_model(self):
        from api_gateway.routers.memory import MemoryIndexInspectResponse

        resp = MemoryIndexInspectResponse(
            memoryId="10",
            milvusId=99,
            collection="company_memories",
            vectorStatus="synced",
            existsInMilvus=True,
            embeddingDimension=1536,
            embeddingPreview=[0.1, 0.2],
        )
        assert resp.memory_id == "10"
        assert resp.milvus_id == 99
        assert resp.vector_status == "synced"
        assert resp.exists_in_milvus is True


class TestMemoryItemToResponse:
    """Test the _memory_item_to_response helper."""

    def test_conversion_basic(self, sample_memory_item):
        from api_gateway.routers.memory import _memory_item_to_response

        result = _memory_item_to_response(
            sample_memory_item, agent_name=None, user_name="Test User"
        )
        assert result["id"] == "1"
        assert result["type"] == "company"
        assert result["content"] == "Test memory content"
        assert result["userName"] == "Test User"
        assert result["tags"] == ["test", "sample"]
        assert result["summary"] == "Test summary"
        assert result["relevanceScore"] == 0.95

    def test_conversion_agent_memory(self, sample_agent_memory):
        from api_gateway.routers.memory import _memory_item_to_response

        result = _memory_item_to_response(sample_agent_memory, agent_name="Test Agent")
        assert result["id"] == "2"
        assert result["type"] == "agent"
        assert result["agentName"] == "Test Agent"
        assert result["tags"] == ["learning"]

    def test_conversion_empty_metadata(self):
        from api_gateway.routers.memory import _memory_item_to_response

        item = MemoryItem(
            id=3,
            content="No metadata",
            memory_type=MemoryType.COMPANY,
            user_id="user-1",
            timestamp=datetime(2026, 1, 15),
            metadata=None,
        )
        result = _memory_item_to_response(item)
        assert result["tags"] == []
        assert result["summary"] is None
        assert result["isShared"] is False

    def test_conversion_shared_memory(self):
        from api_gateway.routers.memory import _memory_item_to_response

        item = MemoryItem(
            id=4,
            content="Shared content",
            memory_type=MemoryType.COMPANY,
            user_id="user-1",
            timestamp=datetime(2026, 1, 15),
            metadata={
                "shared_from": 1,
                "shared_with": ["user-2", "user-3"],
                "tags": ["shared"],
            },
        )
        result = _memory_item_to_response(item)
        assert result["isShared"] is True
        assert result["sharedWith"] == ["user-2", "user-3"]

    def test_internal_scores_removed(self):
        from api_gateway.routers.memory import _memory_item_to_response

        item = MemoryItem(
            id=5,
            content="Scored item",
            memory_type=MemoryType.COMPANY,
            user_id="user-1",
            timestamp=datetime(2026, 1, 15),
            metadata={
                "_combined_score": 0.85,
                "_recency_score": 0.5,
                "tags": [],
            },
        )
        result = _memory_item_to_response(item)
        meta = result["metadata"]
        # Internal scores should be removed
        assert meta is None or "_combined_score" not in meta
        assert meta is None or "_recency_score" not in meta


class TestRouteRegistration:
    """Test that all memory routes are properly registered."""

    def _get_route_methods(self):
        """Build a dict of path -> set of methods across all route objects."""
        route_map = {}
        for route in app.routes:
            if hasattr(route, "methods") and hasattr(route, "path"):
                if route.path not in route_map:
                    route_map[route.path] = set()
                route_map[route.path].update(route.methods)
        return route_map

    def test_routes_exist(self):
        """Verify all expected memory routes are registered."""
        route_map = self._get_route_methods()
        expected_paths = [
            "/api/v1/memories",
            "/api/v1/memories/stats",
            "/api/v1/memories/shared",
            "/api/v1/memories/search",
            "/api/v1/memories/type/{memory_type}",
            "/api/v1/memories/agent/{agent_id}",
            "/api/v1/memories/{memory_id}",
            "/api/v1/memories/{memory_id}/share",
        ]
        for path in expected_paths:
            assert path in route_map, f"Route {path} not found in app routes"

    def test_route_methods(self):
        """Verify routes have correct HTTP methods."""
        route_map = self._get_route_methods()

        assert "GET" in route_map.get("/api/v1/memories", set())
        assert "POST" in route_map.get("/api/v1/memories", set())
        assert "POST" in route_map.get("/api/v1/memories/search", set())
        assert "GET" in route_map.get("/api/v1/memories/stats", set())
        assert "GET" in route_map.get("/api/v1/memories/shared", set())
        assert "GET" in route_map.get("/api/v1/memories/{memory_id}", set())
        assert "PUT" in route_map.get("/api/v1/memories/{memory_id}", set())
        assert "DELETE" in route_map.get("/api/v1/memories/{memory_id}", set())
        assert "POST" in route_map.get("/api/v1/memories/{memory_id}/share", set())
