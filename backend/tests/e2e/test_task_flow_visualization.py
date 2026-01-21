"""End-to-end tests for task flow visualization.

Tests the complete workflow of task flow visualization updates.

References:
- Task 8.3.6: Test task flow visualization updates
"""

import json
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authenticated_client_with_websocket():
    """Create authenticated client with WebSocket support."""
    from api_gateway.main import app

    client = TestClient(app)

    # Register and login
    user_data = {
        "username": f"testuser_{uuid4()}",
        "email": f"test_{uuid4()}@example.com",
        "password": "SecurePassword123!",
        "full_name": "Test User",
    }

    client.post("/api/v1/auth/register", json=user_data)
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": user_data["username"], "password": user_data["password"]},
    )

    token = login_response.json()["access_token"]
    user_id = login_response.json().get("user_id")

    client.headers = {"Authorization": f"Bearer {token}"}

    return client, token, user_id


class TestTaskFlowVisualization:
    """Test complete task flow visualization flow."""

    def test_complete_task_visualization_flow(self, authenticated_client_with_websocket):
        """Test complete flow of task visualization with real-time updates."""
        client, token, user_id = authenticated_client_with_websocket

        # Step 1: Submit a complex goal that will be decomposed
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Research AI trends, analyze the data, and create a presentation",
                "priority": 1,
            },
        )

        assert goal_response.status_code == 201
        task = goal_response.json()
        task_id = task["task_id"]

        # Step 2: Get initial task tree structure
        time.sleep(2)  # Wait for decomposition

        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")

        if tree_response.status_code == 200:
            task_tree = tree_response.json()

            # Verify tree structure
            assert "task_id" in task_tree
            assert task_tree["task_id"] == task_id

            # Should have subtasks
            subtasks_key = "subtasks" if "subtasks" in task_tree else "children"
            if subtasks_key in task_tree:
                subtasks = task_tree[subtasks_key]
                assert len(subtasks) > 0

                # Each subtask should have required fields
                for subtask in subtasks:
                    assert "task_id" in subtask
                    assert "status" in subtask
                    assert "description" in subtask or "goal_text" in subtask

                    # Check for agent assignment
                    if "assigned_agent_id" in subtask:
                        assert subtask["assigned_agent_id"] is not None

        # Step 3: Monitor task progress updates
        max_attempts = 20
        previous_status = None
        status_changes = []

        for attempt in range(max_attempts):
            status_response = client.get(f"/api/v1/tasks/{task_id}")
            current_task = status_response.json()

            current_status = current_task["status"]

            # Track status changes
            if current_status != previous_status:
                status_changes.append(
                    {
                        "status": current_status,
                        "progress": current_task.get("progress", 0),
                        "timestamp": time.time(),
                    }
                )
                previous_status = current_status

            if current_status in ["completed", "failed"]:
                break

            time.sleep(1)

        # Verify we saw status progression
        assert len(status_changes) > 0

        # Step 4: Get updated task tree with progress
        final_tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")

        if final_tree_response.status_code == 200:
            final_tree = final_tree_response.json()

            # Verify progress information
            assert "progress" in final_tree or "status" in final_tree

            # Check subtasks progress
            subtasks_key = "subtasks" if "subtasks" in final_tree else "children"
            if subtasks_key in final_tree:
                for subtask in final_tree[subtasks_key]:
                    assert "status" in subtask
                    assert "progress" in subtask or subtask["status"] in [
                        "completed",
                        "failed",
                        "pending",
                    ]

        # Step 5: Get task execution timeline
        timeline_response = client.get(f"/api/v1/tasks/{task_id}/timeline")

        if timeline_response.status_code == 200:
            timeline = timeline_response.json()

            # Should have timeline events
            assert len(timeline) > 0

            # Each event should have timestamp and description
            for event in timeline:
                assert "timestamp" in event
                assert "event_type" in event or "description" in event

        # Step 6: Get dependency graph
        dependencies_response = client.get(f"/api/v1/tasks/{task_id}/dependencies")

        if dependencies_response.status_code == 200:
            dependencies = dependencies_response.json()

            # Should show task relationships
            assert "nodes" in dependencies or "tasks" in dependencies
            assert "edges" in dependencies or "dependencies" in dependencies

    def test_websocket_real_time_updates(self, authenticated_client_with_websocket):
        """Test receiving real-time task updates via WebSocket."""
        client, token, user_id = authenticated_client_with_websocket

        # Connect to WebSocket
        with client.websocket_connect(f"/ws/{user_id}?token={token}") as websocket:
            # Submit a task
            task_response = client.post(
                "/api/v1/tasks", json={"goal_text": "Calculate the sum of 1 to 100", "priority": 1}
            )

            task_id = task_response.json()["task_id"]

            # Listen for updates
            updates_received = []
            timeout = time.time() + 10  # 10 second timeout

            while time.time() < timeout:
                try:
                    data = websocket.receive_json(timeout=1)

                    # Check if it's a task update
                    if data.get("type") == "task_update" and data.get("task_id") == task_id:
                        updates_received.append(data)

                        # If task is completed, we can stop
                        if data.get("status") == "completed":
                            break
                except:
                    # Timeout or connection closed
                    break

            # Should have received at least one update
            assert len(updates_received) > 0

            # Updates should contain status information
            for update in updates_received:
                assert "status" in update
                assert "task_id" in update

    def test_task_flow_with_parallel_execution(self, authenticated_client_with_websocket):
        """Test visualization of parallel task execution."""
        client, token, user_id = authenticated_client_with_websocket

        # Submit goal that can be parallelized
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Fetch data from 3 different sources and combine results",
                "priority": 1,
            },
        )

        task_id = goal_response.json()["task_id"]

        # Wait for decomposition
        time.sleep(2)

        # Get task tree
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")

        if tree_response.status_code == 200:
            tree = tree_response.json()

            subtasks_key = "subtasks" if "subtasks" in tree else "children"
            if subtasks_key in tree:
                subtasks = tree[subtasks_key]

                # Check for parallel execution indicators
                parallel_tasks = [
                    st
                    for st in subtasks
                    if st.get("execution_mode") == "parallel" or not st.get("dependencies")
                ]

                # Should have tasks that can run in parallel
                assert len(parallel_tasks) > 0

    def test_task_flow_with_dependencies(self, authenticated_client_with_websocket):
        """Test visualization of task dependencies."""
        client, token, user_id = authenticated_client_with_websocket

        # Submit goal with clear dependencies
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "First collect data, then analyze it, finally create a report",
                "priority": 1,
            },
        )

        task_id = goal_response.json()["task_id"]

        # Wait for decomposition
        time.sleep(2)

        # Get dependency graph
        dependencies_response = client.get(f"/api/v1/tasks/{task_id}/dependencies")

        if dependencies_response.status_code == 200:
            dep_graph = dependencies_response.json()

            # Should show sequential dependencies
            if "edges" in dep_graph:
                assert len(dep_graph["edges"]) > 0

                # Edges should connect tasks
                for edge in dep_graph["edges"]:
                    assert "from" in edge or "source" in edge
                    assert "to" in edge or "target" in edge

    def test_task_flow_error_visualization(self, authenticated_client_with_websocket):
        """Test visualization of task errors."""
        client, token, user_id = authenticated_client_with_websocket

        # Submit a task that might fail
        goal_response = client.post(
            "/api/v1/tasks",
            json={"goal_text": "Divide 100 by 0", "priority": 1},  # Will cause error
        )

        task_id = goal_response.json()["task_id"]

        # Wait for execution
        time.sleep(3)

        # Get task status
        status_response = client.get(f"/api/v1/tasks/{task_id}")
        task_status = status_response.json()

        # If task failed, check error information
        if task_status["status"] == "failed":
            assert "error" in task_status or "error_message" in task_status

            # Get task tree to see error propagation
            tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")

            if tree_response.status_code == 200:
                tree = tree_response.json()

                # Error should be visible in tree
                assert tree.get("status") == "failed"

    def test_task_flow_agent_visualization(self, authenticated_client_with_websocket):
        """Test visualization of agent assignments in task flow."""
        client, token, user_id = authenticated_client_with_websocket

        # Create an agent first
        templates_response = client.get("/api/v1/agents/templates")
        template_id = templates_response.json()[0]["template_id"]

        agent_response = client.post(
            "/api/v1/agents", json={"name": f"Viz Test Agent {uuid4()}", "template_id": template_id}
        )

        agent_id = agent_response.json()["agent_id"]

        # Submit task
        goal_response = client.post(
            "/api/v1/tasks",
            json={"goal_text": "Analyze some data", "assigned_agent_id": agent_id, "priority": 1},
        )

        task_id = goal_response.json()["task_id"]

        # Get task tree
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")

        if tree_response.status_code == 200:
            tree = tree_response.json()

            # Should show agent assignment
            assert "assigned_agent_id" in tree
            assert tree["assigned_agent_id"] == agent_id

            # May also have agent details
            if "agent" in tree:
                assert tree["agent"]["agent_id"] == agent_id

        # Clean up
        client.delete(f"/api/v1/agents/{agent_id}")

    def test_task_flow_progress_tracking(self, authenticated_client_with_websocket):
        """Test detailed progress tracking in task flow."""
        client, token, user_id = authenticated_client_with_websocket

        # Submit task
        goal_response = client.post(
            "/api/v1/tasks", json={"goal_text": "Process a multi-step workflow", "priority": 1}
        )

        task_id = goal_response.json()["task_id"]

        # Monitor progress over time
        progress_history = []

        for _ in range(10):
            status_response = client.get(f"/api/v1/tasks/{task_id}")
            task = status_response.json()

            progress_history.append(
                {
                    "progress": task.get("progress", 0),
                    "status": task["status"],
                    "timestamp": time.time(),
                }
            )

            if task["status"] in ["completed", "failed"]:
                break

            time.sleep(1)

        # Progress should increase over time (or stay at 0 if not started)
        if len(progress_history) > 1:
            # Check that progress doesn't decrease
            for i in range(1, len(progress_history)):
                if progress_history[i]["status"] == progress_history[i - 1]["status"]:
                    assert progress_history[i]["progress"] >= progress_history[i - 1]["progress"]
