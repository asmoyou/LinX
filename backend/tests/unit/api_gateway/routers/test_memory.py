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
from datetime import datetime, timezone
from uuid import UUID, uuid4
from unittest.mock import MagicMock, mock_open, patch

from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from access_control.permissions import CurrentUser
from access_control.rbac import Role
from api_gateway.main import app
from memory_system.memory_interface import MemoryItem, MemoryType, SearchQuery
from memory_system.memory_repository import MemoryRecordData


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

    def test_search_validation_min_score_bounds(self):
        """Test min_score validation."""
        from api_gateway.routers.memory import MemorySearchRequest
        from pydantic import ValidationError

        req = MemorySearchRequest(query="test", min_score=0.35)
        assert req.min_score == 0.35

        with pytest.raises(ValidationError):
            MemorySearchRequest(query="test", min_score=-0.1)

        with pytest.raises(ValidationError):
            MemorySearchRequest(query="test", min_score=1.2)

    def test_extract_memory_query_terms_keeps_mixed_language_keywords(self):
        from api_gateway.routers.memory import _extract_memory_query_terms

        terms = _extract_memory_query_terms("LinX是谁开发的")

        assert "linx" in terms
        assert any("开发" in term for term in terms)

    def test_retrieve_memories_keyword_fallback_returns_scored_result(self):
        from api_gateway.routers import memory as memory_router

        query = SearchQuery(
            query_text="LinX是谁开发的",
            memory_type=MemoryType.COMPANY,
            top_k=10,
            min_similarity=0.3,
        )
        mock_memory_system = MagicMock()
        mock_memory_system.retrieve_memories.return_value = []

        memory_row = MemoryRecordData(
            id=7,
            milvus_id=701,
            memory_type=MemoryType.COMPANY,
            content="LinX是小白客开发的，LinX平台的中文名是灵枢",
            user_id="test-user-id",
            agent_id=None,
            task_id=None,
            owner_user_id="test-user-id",
            owner_agent_id=None,
            department_id=None,
            visibility="department_tree",
            sensitivity="internal",
            source_memory_id=None,
            expires_at=None,
            metadata={},
            timestamp=datetime(2026, 1, 15, 12, 0, 0),
            vector_status="synced",
            vector_error=None,
            vector_updated_at=None,
        )
        mock_repo = MagicMock()
        mock_repo.get_by_milvus_ids.return_value = {}
        mock_repo.search_keywords.return_value = [(memory_row, 4.6, 2)]

        with patch("memory_system.memory_system.get_memory_system", return_value=mock_memory_system):
            with patch("api_gateway.routers.memory._get_memory_repository", return_value=mock_repo):
                with patch(
                    "api_gateway.routers.memory._items_to_responses",
                    side_effect=lambda items: [
                        memory_router._memory_item_to_response(item) for item in items
                    ],
                ):
                    results = memory_router._retrieve_memories_sync(query)

        assert len(results) == 1
        assert results[0]["id"] == "7"
        assert results[0]["relevanceScore"] is not None
        assert float(results[0]["relevanceScore"]) >= 0.3
        assert results[0]["metadata"]["search_method"] == "keyword"

        call_kwargs = mock_repo.search_keywords.call_args.kwargs
        assert "linx" in call_kwargs.get("query_terms", [])

    def test_retrieve_memories_keyword_fallback_respects_min_similarity(self):
        from api_gateway.routers import memory as memory_router

        query = SearchQuery(
            query_text="LinX是谁开发的",
            memory_type=MemoryType.COMPANY,
            top_k=10,
            min_similarity=0.5,
        )
        mock_memory_system = MagicMock()
        mock_memory_system.retrieve_memories.return_value = []

        memory_row = MemoryRecordData(
            id=8,
            milvus_id=702,
            memory_type=MemoryType.COMPANY,
            content="LinX是小白客开发的",
            user_id="test-user-id",
            agent_id=None,
            task_id=None,
            owner_user_id="test-user-id",
            owner_agent_id=None,
            department_id=None,
            visibility="department_tree",
            sensitivity="internal",
            source_memory_id=None,
            expires_at=None,
            metadata={},
            timestamp=datetime(2026, 1, 15, 12, 0, 0),
            vector_status="synced",
            vector_error=None,
            vector_updated_at=None,
        )
        mock_repo = MagicMock()
        mock_repo.get_by_milvus_ids.return_value = {}
        # rank=1.8 -> similarity=1.8/(1.8+4)=0.31
        mock_repo.search_keywords.return_value = [(memory_row, 1.8, 1)]

        with patch("memory_system.memory_system.get_memory_system", return_value=mock_memory_system):
            with patch("api_gateway.routers.memory._get_memory_repository", return_value=mock_repo):
                with patch("api_gateway.routers.memory._items_to_responses", return_value=[]):
                    results = memory_router._retrieve_memories_sync(query)

        assert results == []


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

    def test_share_validation_with_scope_and_expiry(self):
        """Scope, expiry and reason fields should be accepted."""
        from api_gateway.routers.memory import MemoryShareRequest

        req = MemoryShareRequest(
            user_ids=["user-1"],
            scope="department_tree",
            expires_at="2026-12-31T23:59:59+00:00",
            reason="Temporary incident response",
        )
        assert req.scope == "department_tree"
        assert req.expires_at == "2026-12-31T23:59:59+00:00"
        assert req.reason == "Temporary incident response"


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


class TestMemoryPageResponse:
    """Test MemoryPageResponse schema."""

    def test_page_response_model(self):
        from api_gateway.routers.memory import MemoryPageResponse

        payload = MemoryPageResponse(
            items=[
                {
                    "id": "1",
                    "type": "company",
                    "content": "Test content",
                    "createdAt": "2026-01-15T12:00:00",
                }
            ],
            total=11,
            offset=0,
            limit=10,
            hasMore=True,
        )
        assert payload.total == 11
        assert payload.offset == 0
        assert payload.limit == 10
        assert payload.has_more is True


class TestTimestampFormatting:
    """Test helper timestamp conversion used by index inspection."""

    def test_to_iso_timestamp_converts_milvus_milliseconds(self):
        from api_gateway.routers.memory import _to_iso_timestamp

        milvus_ts_ms = 1739407685123
        expected = datetime.fromtimestamp(milvus_ts_ms / 1000.0, tz=timezone.utc).isoformat()
        assert _to_iso_timestamp(milvus_ts_ms) == expected

    def test_to_iso_timestamp_converts_numeric_string_timestamp(self):
        from api_gateway.routers.memory import _to_iso_timestamp

        milvus_ts_ms_str = "1739407685123"
        expected = datetime.fromtimestamp(1739407685.123, tz=timezone.utc).isoformat()
        assert _to_iso_timestamp(milvus_ts_ms_str) == expected

    def test_to_iso_timestamp_preserves_plain_text(self):
        from api_gateway.routers.memory import _to_iso_timestamp

        assert _to_iso_timestamp("not-a-timestamp") == "not-a-timestamp"


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
        assert result["isShared"] is True
        assert result["metadata"]["visibility"] == "department_tree"

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

    def test_conversion_department_visibility_counts_as_shared(self):
        from api_gateway.routers.memory import _memory_item_to_response

        item = MemoryItem(
            id=6,
            content="Department-published content",
            memory_type=MemoryType.COMPANY,
            user_id="user-1",
            timestamp=datetime(2026, 1, 15),
            metadata={
                "visibility": "department_tree",
                "department_id": "dep-1",
            },
        )
        result = _memory_item_to_response(item)
        assert result["isShared"] is True

    def test_conversion_promoted_backlink_counts_as_shared(self):
        from api_gateway.routers.memory import _memory_item_to_response

        item = MemoryItem(
            id=7,
            content="Published from agent memory",
            memory_type=MemoryType.AGENT,
            user_id="user-1",
            agent_id="agent-1",
            timestamp=datetime(2026, 1, 15),
            metadata={
                "visibility": "account",
                "last_promoted_memory_id": 99,
            },
        )
        result = _memory_item_to_response(item)
        assert result["isShared"] is True

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
            "/api/v1/memories/config",
            "/api/v1/memories/shared",
            "/api/v1/memories/search",
            "/api/v1/memories/type/{memory_type}",
            "/api/v1/memories/type/{memory_type}/paged",
            "/api/v1/memories/agent/{agent_id}",
            "/api/v1/memories/diagnostics/agent/{agent_id}",
            "/api/v1/memories/admin/backfill-agent-user-ids",
            "/api/v1/memories/{memory_id}",
            "/api/v1/memories/{memory_id}/share",
            "/api/v1/memories/{memory_id}/publish",
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
        assert "GET" in route_map.get("/api/v1/memories/config", set())
        assert "PUT" in route_map.get("/api/v1/memories/config", set())
        assert "GET" in route_map.get("/api/v1/memories/shared", set())
        assert "GET" in route_map.get("/api/v1/memories/type/{memory_type}/paged", set())
        assert "GET" in route_map.get("/api/v1/memories/diagnostics/agent/{agent_id}", set())
        assert "POST" in route_map.get("/api/v1/memories/admin/backfill-agent-user-ids", set())
        assert "GET" in route_map.get("/api/v1/memories/{memory_id}", set())
        assert "PUT" in route_map.get("/api/v1/memories/{memory_id}", set())
        assert "DELETE" in route_map.get("/api/v1/memories/{memory_id}", set())
        assert "POST" in route_map.get("/api/v1/memories/{memory_id}/share", set())
        assert "POST" in route_map.get("/api/v1/memories/{memory_id}/publish", set())


class TestMemoryPolicyHelpers:
    """Unit tests for memory policy helper functions."""

    def test_resolve_effective_user_id_company_defaults_to_none(self, mock_current_user):
        from api_gateway.routers.memory import _resolve_effective_user_id
        from memory_system.memory_interface import MemoryType

        assert _resolve_effective_user_id(MemoryType.COMPANY, mock_current_user) is None

    def test_resolve_effective_user_id_user_context_is_scoped(self, mock_current_user):
        from api_gateway.routers.memory import _resolve_effective_user_id
        from memory_system.memory_interface import MemoryType

        assert (
            _resolve_effective_user_id(MemoryType.USER_CONTEXT, mock_current_user)
            == mock_current_user.user_id
        )

    def test_visibility_defaults(self):
        from api_gateway.routers.memory import _resolve_memory_visibility

        assert _resolve_memory_visibility("user_context", {}) == "private"
        assert _resolve_memory_visibility("agent", {}) == "private"
        assert _resolve_memory_visibility("company", {}) == "department_tree"

    def test_acl_deny_has_highest_priority_even_for_owner(self, mock_current_user):
        from api_gateway.routers.memory import _can_read_company_memory_item_sync

        item = {
            "id": "100",
            "type": "company",
            "userId": mock_current_user.user_id,
            "metadata": {
                "owner_user_id": mock_current_user.user_id,
                "visibility": "department_tree",
                "department_id": "dep-1",
            },
        }
        acl_entries = [
            {
                "effect": "deny",
                "principal_type": "user",
                "principal_id": mock_current_user.user_id,
            }
        ]
        allowed = _can_read_company_memory_item_sync(
            item=item,
            current_user=mock_current_user,
            user_department_context={"department_id": "dep-1", "managed_department_ids": set()},
            acl_entries=acl_entries,
        )
        assert allowed is False

    def test_acl_agent_principal_matches_owned_agent(self, mock_current_user):
        from api_gateway.routers.memory import _matches_acl_principal

        entry = {
            "effect": "allow",
            "principal_type": "agent",
            "principal_id": "agent-123",
        }
        with patch("api_gateway.routers.memory._agent_owned_by_user_sync", return_value=True):
            assert _matches_acl_principal(entry, mock_current_user, {}) is True

    def test_owner_agent_grants_read(self, mock_current_user):
        from api_gateway.routers.memory import _can_read_company_memory_item_sync

        item = {
            "id": "101",
            "type": "company",
            "metadata": {
                "owner_agent_id": "agent-abc",
                "visibility": "private",
            },
        }
        with patch("api_gateway.routers.memory._agent_owned_by_user_sync", return_value=True):
            allowed = _can_read_company_memory_item_sync(
                item=item,
                current_user=mock_current_user,
                user_department_context={"department_id": None, "managed_department_ids": set()},
                acl_entries=[],
            )
        assert allowed is True

    def test_owner_agent_grants_manage(self, mock_current_user):
        from api_gateway.routers.memory import _can_manage_memory_item_sync

        item = {
            "id": "102",
            "type": "company",
            "metadata": {
                "owner_agent_id": "agent-xyz",
            },
        }
        with patch("api_gateway.routers.memory._agent_owned_by_user_sync", return_value=True):
            assert _can_manage_memory_item_sync(item, mock_current_user) is True


class TestMemoryConfigPayload:
    """Test memory config payload builder behavior."""

    def test_payload_uses_memory_rerank_when_provided(self):
        from api_gateway.routers.memory import _build_memory_config_payload

        memory_section = {
            "embedding": {
                "provider": "memory-embed-provider",
                "model": "memory-embed-model",
                "dimension": 1024,
            },
            "retrieval": {
                "enable_reranking": True,
                "rerank_provider": "memory-rerank-provider",
                "rerank_model": "memory-rerank-model",
            },
        }
        kb_section = {
            "search": {
                "rerank_provider": "kb-rerank-provider",
                "rerank_model": "kb-rerank-model",
            }
        }
        llm_section = {
            "default_provider": "ollama",
            "providers": {
                "ollama": {
                    "models": {
                        "chat": "qwen3",
                    }
                }
            },
        }

        with patch(
            "memory_system.embedding_service.resolve_embedding_settings",
            return_value={
                "provider": "effective-embed-provider",
                "model": "effective-embed-model",
                "dimension": 1024,
                "provider_source": "memory.embedding.provider",
                "model_source": "memory.embedding.model",
                "dimension_source": "memory.embedding.dimension",
            },
        ):
            payload = _build_memory_config_payload(memory_section, kb_section, llm_section)

        assert payload["retrieval"]["rerank_provider"] == "memory-rerank-provider"
        assert payload["retrieval"]["rerank_model"] == "memory-rerank-model"
        assert (
            payload["retrieval"]["sources"]["rerank_provider"] == "memory.retrieval.rerank_provider"
        )
        assert payload["retrieval"]["sources"]["rerank_model"] == "memory.retrieval.rerank_model"
        assert payload["embedding"]["effective"]["provider"] == "effective-embed-provider"
        assert payload["fact_extraction"]["effective"]["provider"] == "ollama"
        assert payload["fact_extraction"]["effective"]["model"] == "qwen3"
        assert payload["fact_extraction"]["sources"]["provider"] == "llm.default_provider"
        assert payload["runtime"]["collection_retry_attempts"] == 3
        assert payload["runtime"]["search_timeout_seconds"] == 2.0

    def test_payload_falls_back_to_kb_rerank_when_memory_not_set(self):
        from api_gateway.routers.memory import _build_memory_config_payload

        memory_section = {
            "embedding": {},
            "retrieval": {
                "enable_reranking": True,
            },
            "enhanced_memory": {
                "fact_extraction": {
                    "provider": "custom-provider",
                    "model": "custom-model",
                }
            },
        }
        kb_section = {
            "search": {
                "rerank_provider": "kb-rerank-provider",
                "rerank_model": "kb-rerank-model",
            }
        }

        with patch(
            "memory_system.embedding_service.resolve_embedding_settings",
            return_value={
                "provider": "fallback-embed-provider",
                "model": "fallback-embed-model",
                "dimension": 1024,
                "provider_source": "knowledge_base.embedding.provider",
                "model_source": "knowledge_base.embedding.model",
                "dimension_source": "knowledge_base.embedding.dimension",
            },
        ):
            payload = _build_memory_config_payload(memory_section, kb_section)

        assert payload["retrieval"]["rerank_provider"] == "kb-rerank-provider"
        assert payload["retrieval"]["rerank_model"] == "kb-rerank-model"
        assert (
            payload["retrieval"]["sources"]["rerank_provider"]
            == "knowledge_base.search.rerank_provider"
        )
        assert (
            payload["retrieval"]["sources"]["rerank_model"] == "knowledge_base.search.rerank_model"
        )
        assert payload["fact_extraction"]["effective"]["provider"] == "custom-provider"
        assert payload["fact_extraction"]["effective"]["model"] == "custom-model"
        assert (
            payload["fact_extraction"]["sources"]["provider"]
            == "memory.enhanced_memory.fact_extraction.provider"
        )
        assert payload["runtime"]["delete_timeout_seconds"] == 2.0

    def test_payload_fact_extraction_limits_support_session_fields(self):
        from api_gateway.routers.memory import _build_memory_config_payload

        memory_section = {
            "enhanced_memory": {
                "fact_extraction": {
                    "max_facts": 9,
                    "max_agent_candidates": 2,
                }
            }
        }

        with patch(
            "memory_system.embedding_service.resolve_embedding_settings",
            return_value={
                "provider": "embed-provider",
                "model": "embed-model",
                "dimension": 1024,
                "provider_source": "memory.embedding.provider",
                "model_source": "memory.embedding.model",
                "dimension_source": "memory.embedding.dimension",
            },
        ):
            payload = _build_memory_config_payload(memory_section, {}, {})

        assert payload["fact_extraction"]["max_facts"] == 9
        assert payload["fact_extraction"]["max_preference_facts"] == 9
        assert payload["fact_extraction"]["max_agent_candidates"] == 2


class TestMemoryConfigEndpoints:
    """Test GET/PUT memory config endpoint behavior."""

    @pytest.mark.asyncio
    async def test_get_memory_config_success(self, mock_current_user):
        from api_gateway.routers.memory import get_memory_config

        mock_config = MagicMock()
        mock_config.get_section.side_effect = lambda section: {
            "memory": {"embedding": {}, "retrieval": {}},
            "knowledge_base": {"search": {}},
            "llm": {"default_provider": "ollama"},
        }.get(section, {})

        payload = {
            "embedding": {
                "provider": "cfg-provider",
                "model": "cfg-model",
                "dimension": 1024,
                "effective": {"provider": "eff-provider", "model": "eff-model", "dimension": 1024},
                "sources": {
                    "provider": "memory.embedding.provider",
                    "model": "memory.embedding.model",
                },
            },
            "retrieval": {"top_k": 10, "enable_reranking": True},
            "fact_extraction": {
                "enabled": True,
                "model_enabled": False,
                "provider": "ollama",
                "model": "qwen3",
            },
            "runtime": {"search_timeout_seconds": 2.0},
            "recommended": {},
        }

        with patch("api_gateway.routers.memory.get_config", return_value=mock_config):
            with patch(
                "api_gateway.routers.memory._build_memory_config_payload", return_value=payload
            ):
                response = await get_memory_config(current_user=mock_current_user)

        assert response.embedding["provider"] == "cfg-provider"
        assert response.retrieval["top_k"] == 10
        assert response.fact_extraction["provider"] == "ollama"
        assert response.runtime["search_timeout_seconds"] == 2.0

    @pytest.mark.asyncio
    async def test_update_memory_config_forbidden_for_non_admin(self, mock_current_user):
        from api_gateway.routers.memory import MemoryConfigUpdateRequest, update_memory_config

        with pytest.raises(HTTPException) as exc_info:
            await update_memory_config(
                update_data=MemoryConfigUpdateRequest(retrieval={"top_k": 20}),
                current_user=mock_current_user,
            )

        assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
        assert "Only admins" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_memory_config_admin_merges_and_returns_payload(self, mock_admin_user):
        from api_gateway.routers.memory import MemoryConfigUpdateRequest, update_memory_config

        initial_config = {
            "memory": {
                "embedding": {"provider": "old-provider", "model": "old-model"},
                "retrieval": {"top_k": 10},
                "enhanced_memory": {
                    "fact_extraction": {
                        "enabled": True,
                        "model_enabled": False,
                        "provider": "old-fact-provider",
                        "model": "old-fact-model",
                    }
                },
                "search_timeout_seconds": 2.0,
            },
            "knowledge_base": {
                "search": {"rerank_provider": "kb-provider", "rerank_model": "kb-model"},
            },
        }

        mock_reloaded = MagicMock()
        mock_reloaded.get_section.side_effect = lambda section: {
            "memory": {
                "embedding": {"provider": "new-provider", "model": "old-model"},
                "retrieval": {"top_k": 20, "rerank_model": "new-rerank-model"},
                "enhanced_memory": {
                    "fact_extraction": {
                        "enabled": True,
                        "model_enabled": True,
                        "provider": "new-fact-provider",
                        "model": "new-fact-model",
                    }
                },
                "search_timeout_seconds": 4,
            },
            "knowledge_base": {"search": {"rerank_provider": "kb-provider"}},
            "llm": {"default_provider": "ollama"},
        }.get(section, {})

        payload = {
            "embedding": {
                "provider": "new-provider",
                "model": "old-model",
                "dimension": 1024,
                "effective": {"provider": "new-provider", "model": "old-model", "dimension": 1024},
                "sources": {"provider": "memory.embedding.provider"},
            },
            "retrieval": {
                "top_k": 20,
                "enable_reranking": True,
                "rerank_model": "new-rerank-model",
            },
            "fact_extraction": {
                "enabled": True,
                "model_enabled": True,
                "provider": "new-fact-provider",
                "model": "new-fact-model",
            },
            "runtime": {"search_timeout_seconds": 4},
            "recommended": {},
        }

        mocked_open = mock_open(read_data="memory: {}\n")

        with patch("builtins.open", mocked_open):
            with patch("yaml.safe_load", return_value=initial_config):
                with patch("yaml.dump") as mock_yaml_dump:
                    with patch("shared.config.reload_config", return_value=mock_reloaded):
                        with patch(
                            "api_gateway.routers.memory._build_memory_config_payload",
                            return_value=payload,
                        ):
                            response = await update_memory_config(
                                update_data=MemoryConfigUpdateRequest(
                                    embedding={"provider": "new-provider"},
                                    retrieval={"top_k": 20, "rerank_model": "new-rerank-model"},
                                    fact_extraction={
                                        "model_enabled": True,
                                        "provider": "new-fact-provider",
                                        "model": "new-fact-model",
                                    },
                                    runtime={"search_timeout_seconds": 4},
                                ),
                                current_user=mock_admin_user,
                            )

        dumped_config = mock_yaml_dump.call_args.args[0]
        assert dumped_config["memory"]["embedding"]["provider"] == "new-provider"
        assert dumped_config["memory"]["embedding"]["model"] == "old-model"
        assert dumped_config["memory"]["retrieval"]["top_k"] == 20
        assert dumped_config["memory"]["retrieval"]["rerank_model"] == "new-rerank-model"
        assert dumped_config["memory"]["enhanced_memory"]["fact_extraction"]["provider"] == (
            "new-fact-provider"
        )
        assert dumped_config["memory"]["enhanced_memory"]["fact_extraction"]["model_enabled"] is True
        assert dumped_config["memory"]["search_timeout_seconds"] == 4
        assert response.embedding["provider"] == "new-provider"
        assert response.retrieval["top_k"] == 20
        assert response.fact_extraction["provider"] == "new-fact-provider"
        assert response.runtime["search_timeout_seconds"] == 4


class TestAgentMemoryAccessHelpers:
    """Test helper utilities for agent-memory query scope and filtering."""

    def test_resolve_effective_user_id_uses_scope_rules(self):
        from api_gateway.routers.memory import _resolve_effective_user_id
        from memory_system.memory_interface import MemoryType

        current_user = CurrentUser(
            user_id=str(uuid4()),
            username="u1",
            role=Role.USER.value,
            token_jti="jti-1",
        )
        requested_1 = str(uuid4())
        requested_2 = str(uuid4())

        assert (
            _resolve_effective_user_id(
                MemoryType.AGENT,
                current_user,
                requested_user_id=requested_1,
            )
            == requested_1
        )
        assert (
            _resolve_effective_user_id(
                None,
                current_user,
                requested_user_id=requested_2,
                agent_id=str(uuid4()),
            )
            == requested_2
        )
        assert (
            _resolve_effective_user_id(
                MemoryType.COMPANY,
                current_user,
            )
            is None
        )
        assert (
            _resolve_effective_user_id(
                MemoryType.AGENT,
                current_user,
            )
            == current_user.user_id
        )

    def test_filter_agent_memory_access_sync_keeps_only_owner_for_user(self):
        from api_gateway.routers.memory import _filter_agent_memory_access_sync

        current_user = CurrentUser(
            user_id=str(uuid4()),
            username="u1",
            role=Role.USER.value,
            token_jti="jti-2",
        )
        own_agent_id = str(uuid4())
        other_agent_id = str(uuid4())

        responses = [
            {"id": "m1", "type": "agent", "agentId": own_agent_id},
            {"id": "m2", "type": "agent", "agentId": other_agent_id},
            {"id": "m3", "type": "company", "agentId": None},
        ]

        row_own = MagicMock(agent_id=UUID(own_agent_id), owner_user_id=UUID(current_user.user_id))
        row_other = MagicMock(agent_id=UUID(other_agent_id), owner_user_id=uuid4())

        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = [row_own, row_other]
        session_ctx = MagicMock()
        session_ctx.__enter__.return_value = session
        session_ctx.__exit__.return_value = False

        with patch("database.connection.get_db_session", return_value=session_ctx):
            filtered = _filter_agent_memory_access_sync(responses, current_user)

        assert {item["id"] for item in filtered} == {"m1", "m3"}

    def test_require_agent_read_access_sync_allows_owner(self):
        from api_gateway.routers.memory import _require_agent_read_access_sync

        agent_id = str(uuid4())
        owner_id = str(uuid4())
        current_user = CurrentUser(
            user_id=owner_id,
            username="owner",
            role=Role.USER.value,
            token_jti="jti-3",
        )

        mock_agent = MagicMock(agent_id=UUID(agent_id), owner_user_id=UUID(owner_id))
        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = mock_agent
        session_ctx = MagicMock()
        session_ctx.__enter__.return_value = session
        session_ctx.__exit__.return_value = False

        with patch("database.connection.get_db_session", return_value=session_ctx):
            with patch(
                "access_control.memory_filter.can_access_agent_memory", return_value=True
            ) as mock_can_access:
                _require_agent_read_access_sync(agent_id, current_user)

        mock_can_access.assert_called_once()

    def test_require_agent_read_access_sync_not_found(self):
        from api_gateway.routers.memory import _require_agent_read_access_sync

        agent_id = str(uuid4())
        current_user = CurrentUser(
            user_id=str(uuid4()),
            username="u1",
            role=Role.USER.value,
            token_jti="jti-4",
        )

        session = MagicMock()
        session.query.return_value.filter.return_value.first.return_value = None
        session_ctx = MagicMock()
        session_ctx.__enter__.return_value = session
        session_ctx.__exit__.return_value = False

        with patch("database.connection.get_db_session", return_value=session_ctx):
            with pytest.raises(HTTPException) as exc_info:
                _require_agent_read_access_sync(agent_id, current_user)

        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


class TestAgentMemoryDiagnosticHints:
    """Test agent memory diagnostics hint inference."""

    def test_diagnostic_hints_detects_missing_user_id_case(self):
        from api_gateway.routers.memory import _infer_agent_memory_diagnostic_hints

        result = _infer_agent_memory_diagnostic_hints(
            active_db_count=12,
            without_user_id_count=12,
            vector_status_counts={"pending": 0, "synced": 12, "failed": 0, "unknown": 0},
            milvus_count=10,
            milvus_error=None,
        )

        assert result["primary"] == "agent_memory_rows_missing_user_id"
        assert "agent_memory_rows_missing_user_id" in result["hints"]

    def test_diagnostic_hints_detects_empty_db_case(self):
        from api_gateway.routers.memory import _infer_agent_memory_diagnostic_hints

        result = _infer_agent_memory_diagnostic_hints(
            active_db_count=0,
            without_user_id_count=0,
            vector_status_counts={"pending": 0, "synced": 0, "failed": 0, "unknown": 0},
            milvus_count=0,
            milvus_error=None,
        )

        assert result["primary"] == "no_agent_memory_in_db"
        assert "no_agent_memory_in_db" in result["hints"]


class TestAgentMemoryCandidateReview:
    """Test review workflow for auto-extracted agent memory candidates."""

    def test_list_agent_candidate_memories_filters_review_status(self, mock_current_user):
        from api_gateway.routers.memory import _list_agent_candidate_memories_sync

        candidate_pending = {
            "id": "11",
            "type": "agent",
            "agentId": "agent-123",
            "createdAt": "2026-02-25T12:00:00+00:00",
            "metadata": {
                "signal_type": "agent_memory_candidate",
                "review_status": "pending",
            },
        }
        candidate_published = {
            "id": "12",
            "type": "agent",
            "agentId": "agent-123",
            "createdAt": "2026-02-25T12:01:00+00:00",
            "metadata": {
                "signal_type": "agent_memory_candidate",
                "review_status": "published",
            },
        }
        normal_agent_memory = {
            "id": "13",
            "type": "agent",
            "agentId": "agent-123",
            "createdAt": "2026-02-25T12:02:00+00:00",
            "metadata": {"signal_type": "other"},
        }

        with patch(
            "api_gateway.routers.memory._list_memories_without_embedding_sync",
            return_value=[candidate_pending, candidate_published, normal_agent_memory],
        ):
            with patch(
                "api_gateway.routers.memory._filter_agent_memory_access_sync",
                side_effect=lambda responses, _user: responses,
            ):
                filtered = _list_agent_candidate_memories_sync(
                    current_user=mock_current_user,
                    agent_id="agent-123",
                    review_status="pending",
                    limit=10,
                )

        assert len(filtered) == 1
        assert filtered[0]["id"] == "11"

    def test_review_agent_candidate_sync_marks_published(self):
        from api_gateway.routers.memory import (
            AgentCandidateReviewRequest,
            _review_agent_candidate_sync,
        )

        current_ts = datetime(2026, 2, 25, 10, 0, 0, tzinfo=timezone.utc)
        record = MemoryRecordData(
            id=77,
            milvus_id=177,
            memory_type=MemoryType.AGENT,
            content="interaction.sop.topic=写旅游攻略\ninteraction.sop.steps=1|2|3",
            user_id="test-user-id",
            agent_id="agent-123",
            task_id=None,
            owner_user_id="test-user-id",
            owner_agent_id="agent-123",
            department_id=None,
            visibility="private",
            sensitivity="internal",
            source_memory_id=None,
            expires_at=None,
            metadata={
                "signal_type": "agent_memory_candidate",
                "review_status": "pending",
            },
            timestamp=current_ts,
            vector_status="synced",
            vector_error=None,
            vector_updated_at=current_ts,
        )

        updated = MemoryRecordData(
            id=77,
            milvus_id=177,
            memory_type=MemoryType.AGENT,
            content=record.content,
            user_id=record.user_id,
            agent_id=record.agent_id,
            task_id=record.task_id,
            owner_user_id=record.owner_user_id,
            owner_agent_id=record.owner_agent_id,
            department_id=record.department_id,
            visibility=record.visibility,
            sensitivity=record.sensitivity,
            source_memory_id=record.source_memory_id,
            expires_at=record.expires_at,
            metadata={
                **dict(record.metadata or {}),
                "review_status": "published",
                "reviewed_by": "reviewer-1",
            },
            timestamp=current_ts,
            vector_status="synced",
            vector_error=None,
            vector_updated_at=current_ts,
        )

        mock_repo = MagicMock()
        mock_repo.get.return_value = record
        mock_repo.get_by_milvus_id.return_value = None
        mock_repo.update_record.return_value = updated

        mock_session = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__enter__.return_value = mock_session
        mock_session_ctx.__exit__.return_value = False

        request = AgentCandidateReviewRequest(action="publish", note="looks good")
        with patch("api_gateway.routers.memory._get_memory_repository", return_value=mock_repo):
            with patch("database.connection.get_db_session", return_value=mock_session_ctx):
                with patch("api_gateway.routers.memory._lookup_agent_name", return_value="Agent X"):
                    with patch("api_gateway.routers.memory._lookup_user_name", return_value="User X"):
                        result = _review_agent_candidate_sync(
                            memory_id=77,
                            request=request,
                            reviewer_user_id="reviewer-1",
                        )

        assert result is not None
        assert result["id"] == "77"
        assert result["metadata"]["review_status"] == "published"
        assert result["metadata"]["reviewed_by"] == "reviewer-1"
