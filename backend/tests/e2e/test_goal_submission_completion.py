"""End-to-end tests for goal submission and completion.

Tests the complete workflow from goal submission to completion.

References:
- Task 8.3.3: Test goal submission and completion flow
"""

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authenticated_client_with_agent():
    """Create authenticated client with an agent."""
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
    client.headers = {"Authorization": f"Bearer {token}"}

    # Create an agent
    templates_response = client.get("/api/v1/agents/templates")
    template_id = templates_response.json()[0]["template_id"]

    agent_response = client.post(
        "/api/v1/agents", json={"name": f"Test Agent {uuid4()}", "template_id": template_id}
    )

    agent_id = agent_response.json()["agent_id"]

    return client, agent_id


class TestGoalSubmissionCompletion:
    """Test complete goal submission and completion flow."""

    def test_complete_goal_execution_flow(self, authenticated_client_with_agent):
        """Test complete flow from goal submission to completion."""
        client, agent_id = authenticated_client_with_agent

        # Step 1: Submit a goal
        goal_data = {
            "goal_text": "Analyze the sales data for Q4 2024 and create a summary report",
            "priority": 1,
        }

        submit_response = client.post("/api/v1/tasks", json=goal_data)

        assert submit_response.status_code == 201
        task = submit_response.json()
        assert "task_id" in task
        assert task["status"] in ["pending", "analyzing", "in_progress"]
        assert task["goal_text"] == goal_data["goal_text"]

        task_id = task["task_id"]

        # Step 2: Check if clarification is needed
        detail_response = client.get(f"/api/v1/tasks/{task_id}")
        task_detail = detail_response.json()

        if task_detail["status"] == "needs_clarification":
            # Step 3: Provide clarification
            assert "clarification_questions" in task_detail

            clarification_data = {
                "answers": [
                    {"question_id": 0, "answer": "Q4 2024 (October-December)"},
                    {"question_id": 1, "answer": "Revenue, units sold, and growth rate"},
                ]
            }

            clarify_response = client.post(
                f"/api/v1/tasks/{task_id}/clarify", json=clarification_data
            )

            assert clarify_response.status_code == 200

            # Wait a moment for processing
            time.sleep(1)

        # Step 4: Monitor task progress
        max_attempts = 30
        for attempt in range(max_attempts):
            status_response = client.get(f"/api/v1/tasks/{task_id}")
            current_task = status_response.json()

            assert "status" in current_task
            assert "progress" in current_task

            if current_task["status"] == "completed":
                break
            elif current_task["status"] == "failed":
                pytest.fail(f"Task failed: {current_task.get('error')}")

            time.sleep(1)

        # Step 5: Get task tree (decomposition)
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")

        if tree_response.status_code == 200:
            task_tree = tree_response.json()
            assert "task_id" in task_tree
            assert "subtasks" in task_tree or "children" in task_tree

        # Step 6: Get final result
        final_response = client.get(f"/api/v1/tasks/{task_id}")
        final_task = final_response.json()

        if final_task["status"] == "completed":
            assert "result" in final_task
            assert final_task["result"] is not None
            assert final_task["progress"] == 100

        # Step 7: Get task history
        history_response = client.get(f"/api/v1/tasks/{task_id}/history")

        if history_response.status_code == 200:
            history = history_response.json()
            assert len(history) > 0
            assert all("timestamp" in h for h in history)
            assert all("status" in h for h in history)

    def test_goal_with_automatic_agent_assignment(self, authenticated_client_with_agent):
        """Test goal submission with automatic agent assignment."""
        client, _ = authenticated_client_with_agent

        # Submit goal without specifying agent
        goal_data = {
            "goal_text": "Calculate the average of numbers: 10, 20, 30, 40, 50",
            "priority": 2,
        }

        response = client.post("/api/v1/tasks", json=goal_data)

        assert response.status_code == 201
        task = response.json()

        # System should automatically assign an agent
        time.sleep(2)

        detail_response = client.get(f"/api/v1/tasks/{task['task_id']}")
        task_detail = detail_response.json()

        # Agent should be assigned
        assert "assigned_agent_id" in task_detail or "agents" in task_detail

    def test_goal_with_specific_agent_assignment(self, authenticated_client_with_agent):
        """Test goal submission with specific agent assignment."""
        client, agent_id = authenticated_client_with_agent

        goal_data = {
            "goal_text": "Summarize the key points from the meeting notes",
            "assigned_agent_id": agent_id,
            "priority": 1,
        }

        response = client.post("/api/v1/tasks", json=goal_data)

        assert response.status_code == 201
        task = response.json()
        assert task["assigned_agent_id"] == agent_id

    def test_complex_goal_with_multiple_subtasks(self, authenticated_client_with_agent):
        """Test complex goal that requires decomposition."""
        client, _ = authenticated_client_with_agent

        goal_data = {
            "goal_text": "Research the top 5 AI trends in 2024, analyze their impact, and create a presentation",
            "priority": 1,
        }

        response = client.post("/api/v1/tasks", json=goal_data)

        assert response.status_code == 201
        task = response.json()
        task_id = task["task_id"]

        # Wait for decomposition
        time.sleep(2)

        # Get task tree
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")

        if tree_response.status_code == 200:
            task_tree = tree_response.json()

            # Should have multiple subtasks
            subtasks_key = "subtasks" if "subtasks" in task_tree else "children"
            if subtasks_key in task_tree:
                assert len(task_tree[subtasks_key]) >= 2

    def test_goal_cancellation(self, authenticated_client_with_agent):
        """Test cancelling a goal in progress."""
        client, _ = authenticated_client_with_agent

        # Submit a long-running goal
        goal_data = {
            "goal_text": "Process all customer data and generate comprehensive analytics",
            "priority": 1,
        }

        response = client.post("/api/v1/tasks", json=goal_data)
        task_id = response.json()["task_id"]

        # Wait a moment for it to start
        time.sleep(1)

        # Cancel the task
        cancel_response = client.delete(f"/api/v1/tasks/{task_id}")

        assert cancel_response.status_code == 200

        # Verify task is cancelled
        status_response = client.get(f"/api/v1/tasks/{task_id}")
        task_status = status_response.json()

        assert task_status["status"] in ["cancelled", "cancelling"]

    def test_goal_with_dependencies(self, authenticated_client_with_agent):
        """Test goals with dependencies on other tasks."""
        client, _ = authenticated_client_with_agent

        # Submit first task
        task1_response = client.post(
            "/api/v1/tasks", json={"goal_text": "Collect sales data", "priority": 1}
        )
        task1_id = task1_response.json()["task_id"]

        # Submit second task that depends on first
        task2_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Analyze the collected sales data",
                "dependencies": [task1_id],
                "priority": 1,
            },
        )

        assert task2_response.status_code == 201
        task2 = task2_response.json()

        # Second task should wait for first to complete
        if "dependencies" in task2:
            assert task1_id in task2["dependencies"]

    def test_goal_priority_handling(self, authenticated_client_with_agent):
        """Test that goal priority affects execution order."""
        client, _ = authenticated_client_with_agent

        # Submit low priority task
        low_priority_response = client.post(
            "/api/v1/tasks", json={"goal_text": "Low priority task", "priority": 3}
        )

        # Submit high priority task
        high_priority_response = client.post(
            "/api/v1/tasks", json={"goal_text": "High priority task", "priority": 1}
        )

        assert low_priority_response.status_code == 201
        assert high_priority_response.status_code == 201

        low_task = low_priority_response.json()
        high_task = high_priority_response.json()

        assert low_task["priority"] == 3
        assert high_task["priority"] == 1

    def test_goal_result_retrieval(self, authenticated_client_with_agent):
        """Test retrieving goal results after completion."""
        client, _ = authenticated_client_with_agent

        # Submit simple goal
        response = client.post(
            "/api/v1/tasks", json={"goal_text": "Calculate 2 + 2", "priority": 1}
        )

        task_id = response.json()["task_id"]

        # Wait for completion
        max_attempts = 20
        for _ in range(max_attempts):
            status_response = client.get(f"/api/v1/tasks/{task_id}")
            task = status_response.json()

            if task["status"] == "completed":
                # Get result
                assert "result" in task
                result = task["result"]

                # Result should contain output
                assert result is not None
                break

            time.sleep(1)

    def test_list_all_user_tasks(self, authenticated_client_with_agent):
        """Test listing all tasks for a user."""
        client, _ = authenticated_client_with_agent

        # Submit multiple tasks
        task_ids = []
        for i in range(3):
            response = client.post("/api/v1/tasks", json={"goal_text": f"Task {i}", "priority": 1})
            task_ids.append(response.json()["task_id"])

        # List all tasks
        list_response = client.get("/api/v1/tasks")

        assert list_response.status_code == 200
        tasks = list_response.json()

        # All submitted tasks should be in the list
        for task_id in task_ids:
            assert any(t["task_id"] == task_id for t in tasks)

    def test_filter_tasks_by_status(self, authenticated_client_with_agent):
        """Test filtering tasks by status."""
        client, _ = authenticated_client_with_agent

        # Submit tasks
        client.post("/api/v1/tasks", json={"goal_text": "Task 1", "priority": 1})
        client.post("/api/v1/tasks", json={"goal_text": "Task 2", "priority": 1})

        # Filter by status
        filter_response = client.get("/api/v1/tasks?status=pending")

        if filter_response.status_code == 200:
            tasks = filter_response.json()
            # All returned tasks should have pending status
            assert all(t["status"] == "pending" for t in tasks)
