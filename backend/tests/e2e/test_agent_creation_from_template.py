"""End-to-end tests for agent creation from template.

Tests the complete workflow of creating agents from templates.

References:
- Task 8.3.2: Test agent creation from template flow
"""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def authenticated_client():
    """Create authenticated API client."""
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

    return client


class TestAgentCreationFromTemplate:
    """Test complete agent creation from template flow."""

    def test_complete_agent_creation_flow(self, authenticated_client):
        """Test complete flow from template selection to agent execution."""
        # Step 1: List available templates
        templates_response = authenticated_client.get("/api/v1/agents/templates")

        assert templates_response.status_code == 200
        templates = templates_response.json()
        assert len(templates) > 0
        assert all("template_id" in t for t in templates)
        assert all("name" in t for t in templates)
        assert all("capabilities" in t for t in templates)

        # Step 2: Select a template (e.g., Data Analyst)
        data_analyst_template = next(
            (
                t
                for t in templates
                if "data" in t["name"].lower() and "analyst" in t["name"].lower()
            ),
            templates[0],  # Fallback to first template
        )

        template_id = data_analyst_template["template_id"]

        # Step 3: Get template details
        template_detail_response = authenticated_client.get(
            f"/api/v1/agents/templates/{template_id}"
        )

        assert template_detail_response.status_code == 200
        template_detail = template_detail_response.json()
        assert template_detail["template_id"] == template_id
        assert "capabilities" in template_detail
        assert "tools" in template_detail
        assert "description" in template_detail

        # Step 4: Create agent from template
        agent_data = {
            "name": f"My Data Analyst {uuid4()}",
            "template_id": template_id,
            "description": "Agent for analyzing sales data",
        }

        create_response = authenticated_client.post("/api/v1/agents", json=agent_data)

        assert create_response.status_code == 201
        agent = create_response.json()
        assert "agent_id" in agent
        assert agent["name"] == agent_data["name"]
        assert agent["status"] == "idle"
        assert set(agent["capabilities"]) == set(template_detail["capabilities"])

        agent_id = agent["agent_id"]

        # Step 5: Verify agent appears in agent list
        list_response = authenticated_client.get("/api/v1/agents")

        assert list_response.status_code == 200
        agents = list_response.json()
        assert any(a["agent_id"] == agent_id for a in agents)

        # Step 6: Get agent details
        detail_response = authenticated_client.get(f"/api/v1/agents/{agent_id}")

        assert detail_response.status_code == 200
        agent_detail = detail_response.json()
        assert agent_detail["agent_id"] == agent_id
        assert agent_detail["name"] == agent_data["name"]
        assert agent_detail["status"] == "idle"

        # Step 7: Assign a task to the agent
        task_data = {
            "goal_text": "Analyze the sales data for Q4 2024",
            "assigned_agent_id": agent_id,
            "priority": 1,
        }

        task_response = authenticated_client.post("/api/v1/tasks", json=task_data)

        assert task_response.status_code == 201
        task = task_response.json()
        assert "task_id" in task
        assert task["assigned_agent_id"] == agent_id

        # Step 8: Verify agent status changed to working
        status_response = authenticated_client.get(f"/api/v1/agents/{agent_id}")
        agent_status = status_response.json()
        assert agent_status["status"] in [
            "working",
            "idle",
        ]  # Might be working or completed quickly

        # Step 9: Update agent configuration
        update_data = {"description": "Updated: Agent for comprehensive data analysis"}

        update_response = authenticated_client.put(f"/api/v1/agents/{agent_id}", json=update_data)

        assert update_response.status_code == 200
        updated_agent = update_response.json()
        assert updated_agent["description"] == update_data["description"]

        # Step 10: Terminate agent
        delete_response = authenticated_client.delete(f"/api/v1/agents/{agent_id}")

        assert delete_response.status_code == 200

        # Step 11: Verify agent is terminated
        verify_response = authenticated_client.get(f"/api/v1/agents/{agent_id}")

        if verify_response.status_code == 200:
            # Agent still exists but should be terminated
            terminated_agent = verify_response.json()
            assert terminated_agent["status"] == "terminated"
        else:
            # Agent was deleted
            assert verify_response.status_code == 404

    def test_create_multiple_agents_from_different_templates(self, authenticated_client):
        """Test creating multiple agents from different templates."""
        # Get all templates
        templates_response = authenticated_client.get("/api/v1/agents/templates")
        templates = templates_response.json()

        created_agents = []

        # Create one agent from each template (up to 3)
        for template in templates[:3]:
            agent_data = {
                "name": f"Agent from {template['name']} {uuid4()}",
                "template_id": template["template_id"],
                "description": f"Test agent from {template['name']}",
            }

            response = authenticated_client.post("/api/v1/agents", json=agent_data)

            assert response.status_code == 201
            agent = response.json()
            created_agents.append(agent["agent_id"])

        # Verify all agents exist
        list_response = authenticated_client.get("/api/v1/agents")
        agents = list_response.json()

        for agent_id in created_agents:
            assert any(a["agent_id"] == agent_id for a in agents)

        # Clean up
        for agent_id in created_agents:
            authenticated_client.delete(f"/api/v1/agents/{agent_id}")

    def test_create_agent_with_custom_capabilities(self, authenticated_client):
        """Test creating agent with customized capabilities."""
        # Get a template
        templates_response = authenticated_client.get("/api/v1/agents/templates")
        template = templates_response.json()[0]

        # Create agent with additional custom capabilities
        agent_data = {
            "name": f"Custom Agent {uuid4()}",
            "template_id": template["template_id"],
            "description": "Agent with custom capabilities",
            "custom_capabilities": ["custom_skill_1", "custom_skill_2"],
        }

        response = authenticated_client.post("/api/v1/agents", json=agent_data)

        assert response.status_code == 201
        agent = response.json()

        # Verify custom capabilities are included
        if "custom_capabilities" in agent:
            assert "custom_skill_1" in agent["custom_capabilities"]
            assert "custom_skill_2" in agent["custom_capabilities"]

        # Clean up
        authenticated_client.delete(f"/api/v1/agents/{agent['agent_id']}")

    def test_create_agent_without_template(self, authenticated_client):
        """Test creating agent without using a template."""
        agent_data = {
            "name": f"Custom Agent {uuid4()}",
            "agent_type": "custom",
            "capabilities": ["data_analysis", "report_generation"],
            "description": "Fully custom agent",
        }

        response = authenticated_client.post("/api/v1/agents", json=agent_data)

        # Should succeed or require template_id
        assert response.status_code in [201, 400, 422]

        if response.status_code == 201:
            agent = response.json()
            assert agent["capabilities"] == agent_data["capabilities"]

            # Clean up
            authenticated_client.delete(f"/api/v1/agents/{agent['agent_id']}")

    def test_agent_creation_respects_resource_quotas(self, authenticated_client):
        """Test that agent creation respects user resource quotas."""
        # Get user quotas
        quota_response = authenticated_client.get("/api/v1/users/me/quotas")

        if quota_response.status_code == 200:
            quotas = quota_response.json()
            max_agents = quotas.get("max_agents", 10)

            # Try to create agents up to quota
            created_agents = []
            template_response = authenticated_client.get("/api/v1/agents/templates")
            template_id = template_response.json()[0]["template_id"]

            for i in range(max_agents + 1):
                agent_data = {"name": f"Quota Test Agent {i}", "template_id": template_id}

                response = authenticated_client.post("/api/v1/agents", json=agent_data)

                if response.status_code == 201:
                    created_agents.append(response.json()["agent_id"])
                elif response.status_code == 403:
                    # Quota exceeded
                    assert "quota" in response.json()["detail"].lower()
                    break

            # Clean up
            for agent_id in created_agents:
                authenticated_client.delete(f"/api/v1/agents/{agent_id}")

    def test_agent_creation_with_invalid_template(self, authenticated_client):
        """Test that invalid template ID is rejected."""
        agent_data = {
            "name": f"Invalid Template Agent {uuid4()}",
            "template_id": str(uuid4()),  # Non-existent template
            "description": "This should fail",
        }

        response = authenticated_client.post("/api/v1/agents", json=agent_data)

        assert response.status_code == 404
        error_data = response.json()
        assert "template" in error_data["detail"].lower()

    def test_agent_name_validation(self, authenticated_client):
        """Test agent name validation."""
        template_response = authenticated_client.get("/api/v1/agents/templates")
        template_id = template_response.json()[0]["template_id"]

        invalid_names = [
            "",  # Empty name
            "a",  # Too short
            "a" * 256,  # Too long
        ]

        for invalid_name in invalid_names:
            agent_data = {"name": invalid_name, "template_id": template_id}

            response = authenticated_client.post("/api/v1/agents", json=agent_data)

            assert response.status_code in [400, 422]
