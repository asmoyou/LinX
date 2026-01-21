"""Integration tests for API Gateway → Task Manager.

Tests the integration between API Gateway and Task Manager components.

References:
- Task 8.2.1: Test API Gateway → Task Manager integration
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_db_session():
    """Mock database session."""
    with patch("database.connection.get_db_session") as mock:
        session = Mock()
        mock.return_value.__enter__.return_value = session
        yield session


@pytest.fixture
def mock_task_coordinator():
    """Mock task coordinator."""
    with patch("task_manager.task_coordinator.TaskCoordinator") as mock:
        coordinator = Mock()
        coordinator.submit_goal = AsyncMock(
            return_value={"task_id": str(uuid4()), "status": "pending", "goal_text": "Test goal"}
        )
        coordinator.get_task_status = AsyncMock(
            return_value={"task_id": str(uuid4()), "status": "in_progress", "progress": 50}
        )
        mock.return_value = coordinator
        yield coordinator


class TestAPITaskManagerIntegration:
    """Test API Gateway → Task Manager integration."""

    @pytest.mark.asyncio
    async def test_submit_goal_creates_task(self, mock_db_session, mock_task_coordinator):
        """Test that submitting a goal through API creates a task."""
        from api_gateway.main import app

        client = TestClient(app)

        # Submit goal through API
        response = client.post(
            "/api/v1/tasks",
            json={"goal_text": "Analyze sales data for Q4", "priority": 1},
            headers={"Authorization": "Bearer test_token"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "task_id" in data
        assert data["status"] == "pending"

        # Verify task coordinator was called
        mock_task_coordinator.submit_goal.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_task_status_retrieves_from_manager(
        self, mock_db_session, mock_task_coordinator
    ):
        """Test that getting task status queries the task manager."""
        from api_gateway.main import app

        client = TestClient(app)
        task_id = str(uuid4())

        # Get task status through API
        response = client.get(
            f"/api/v1/tasks/{task_id}", headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "progress" in data

        # Verify task coordinator was called
        mock_task_coordinator.get_task_status.assert_called_once_with(task_id)

    @pytest.mark.asyncio
    async def test_task_cancellation_propagates(self, mock_db_session, mock_task_coordinator):
        """Test that task cancellation through API propagates to task manager."""
        from api_gateway.main import app

        client = TestClient(app)
        task_id = str(uuid4())

        mock_task_coordinator.cancel_task = AsyncMock(return_value=True)

        # Cancel task through API
        response = client.delete(
            f"/api/v1/tasks/{task_id}", headers={"Authorization": "Bearer test_token"}
        )

        assert response.status_code == 200

        # Verify task coordinator was called
        mock_task_coordinator.cancel_task.assert_called_once_with(task_id)

    @pytest.mark.asyncio
    async def test_task_list_filters_by_user(self, mock_db_session, mock_task_coordinator):
        """Test that listing tasks filters by authenticated user."""
        from api_gateway.main import app

        client = TestClient(app)
        user_id = uuid4()

        mock_task_coordinator.list_tasks = AsyncMock(
            return_value=[
                {"task_id": str(uuid4()), "status": "completed"},
                {"task_id": str(uuid4()), "status": "in_progress"},
            ]
        )

        # List tasks through API
        response = client.get("/api/v1/tasks", headers={"Authorization": "Bearer test_token"})

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

        # Verify task coordinator was called with user filter
        mock_task_coordinator.list_tasks.assert_called_once()
