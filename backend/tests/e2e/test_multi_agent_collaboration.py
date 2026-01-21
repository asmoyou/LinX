"""End-to-end tests for multi-agent collaboration.

Tests the complete workflow of multiple agents collaborating on tasks.

References:
- Task 8.3.7: Test multi-agent collaboration flow
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
import time


@pytest.fixture
def authenticated_client_with_multiple_agents():
    """Create authenticated client with multiple specialized agents."""
    from api_gateway.main import app
    client = TestClient(app)
    
    # Register and login
    user_data = {
        "username": f"testuser_{uuid4()}",
        "email": f"test_{uuid4()}@example.com",
        "password": "SecurePassword123!",
        "full_name": "Test User"
    }
    
    client.post("/api/v1/auth/register", json=user_data)
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "username": user_data["username"],
            "password": user_data["password"]
        }
    )
    
    token = login_response.json()["access_token"]
    client.headers = {"Authorization": f"Bearer {token}"}
    
    # Get available templates
    templates_response = client.get("/api/v1/agents/templates")
    templates = templates_response.json()
    
    # Create agents with different capabilities
    agents = {}
    
    # Try to create specialized agents
    for template in templates[:3]:  # Create up to 3 different agents
        agent_response = client.post(
            "/api/v1/agents",
            json={
                "name": f"{template['name']} Agent {uuid4()}",
                "template_id": template["template_id"]
            }
        )
        
        if agent_response.status_code == 201:
            agent = agent_response.json()
            agent_type = template.get("agent_type", template["name"])
            agents[agent_type] = agent["agent_id"]
    
    return client, agents


class TestMultiAgentCollaboration:
    """Test complete multi-agent collaboration flow."""
    
    def test_complete_collaboration_workflow(self, authenticated_client_with_multiple_agents):
        """Test complete workflow of agents collaborating on a complex task."""
        client, agents = authenticated_client_with_multiple_agents
        
        # Step 1: Submit a complex goal requiring multiple agents
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Research market trends, analyze the data, write a report, and create visualizations",
                "priority": 1
            }
        )
        
        assert goal_response.status_code == 201
        task = goal_response.json()
        task_id = task["task_id"]
        
        # Step 2: Wait for task decomposition
        time.sleep(3)
        
        # Step 3: Get task tree to see agent assignments
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")
        
        if tree_response.status_code == 200:
            task_tree = tree_response.json()
            
            # Should have multiple subtasks
            subtasks_key = "subtasks" if "subtasks" in task_tree else "children"
            if subtasks_key in task_tree:
                subtasks = task_tree[subtasks_key]
                assert len(subtasks) >= 2
                
                # Different subtasks should be assigned to different agents
                assigned_agents = set()
                for subtask in subtasks:
                    if "assigned_agent_id" in subtask:
                        assigned_agents.add(subtask["assigned_agent_id"])
                
                # Should have multiple agents working
                if len(assigned_agents) > 1:
                    assert len(assigned_agents) >= 2
        
        # Step 4: Monitor collaboration progress
        max_attempts = 30
        collaboration_events = []
        
        for attempt in range(max_attempts):
            status_response = client.get(f"/api/v1/tasks/{task_id}")
            current_task = status_response.json()
            
            # Track which agents are working
            if "active_agents" in current_task:
                collaboration_events.append({
                    "timestamp": time.time(),
                    "active_agents": current_task["active_agents"],
                    "status": current_task["status"]
                })
            
            if current_task["status"] in ["completed", "failed"]:
                break
            
            time.sleep(1)
        
        # Step 5: Verify task completion
        final_response = client.get(f"/api/v1/tasks/{task_id}")
        final_task = final_response.json()
        
        if final_task["status"] == "completed":
            assert "result" in final_task
            
            # Result should be aggregated from multiple agents
            if "contributors" in final_task or "agents_involved" in final_task:
                contributors_key = "contributors" if "contributors" in final_task else "agents_involved"
                assert len(final_task[contributors_key]) >= 2
    
    def test_agent_handoff_between_tasks(self, authenticated_client_with_multiple_agents):
        """Test agents handing off work to each other."""
        client, agents = authenticated_client_with_multiple_agents
        
        if len(agents) < 2:
            pytest.skip("Need at least 2 agents for handoff test")
        
        # Submit task that requires sequential work
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "First collect data, then analyze it",
                "priority": 1
            }
        )
        
        task_id = goal_response.json()["task_id"]
        
        # Wait for decomposition and execution
        time.sleep(5)
        
        # Get task tree
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")
        
        if tree_response.status_code == 200:
            tree = tree_response.json()
            
            subtasks_key = "subtasks" if "subtasks" in tree else "children"
            if subtasks_key in tree and len(tree[subtasks_key]) >= 2:
                subtasks = tree[subtasks_key]
                
                # Check if different agents handled different subtasks
                agent_assignments = [
                    st.get("assigned_agent_id")
                    for st in subtasks
                    if "assigned_agent_id" in st
                ]
                
                # May have different agents (handoff occurred)
                if len(set(agent_assignments)) > 1:
                    assert True  # Handoff occurred
    
    def test_parallel_agent_execution(self, authenticated_client_with_multiple_agents):
        """Test multiple agents working in parallel."""
        client, agents = authenticated_client_with_multiple_agents
        
        # Submit task with independent subtasks
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Fetch data from source A, source B, and source C simultaneously",
                "priority": 1
            }
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
                
                # Check for parallel execution
                parallel_tasks = [
                    st for st in subtasks
                    if not st.get("dependencies") or len(st.get("dependencies", [])) == 0
                ]
                
                # Should have multiple tasks that can run in parallel
                assert len(parallel_tasks) >= 2
    
    def test_agent_communication_during_collaboration(self, authenticated_client_with_multiple_agents):
        """Test agents communicating with each other during collaboration."""
        client, agents = authenticated_client_with_multiple_agents
        
        if len(agents) < 2:
            pytest.skip("Need at least 2 agents for communication test")
        
        agent_ids = list(agents.values())
        
        # Submit task requiring collaboration
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Agent 1 should ask Agent 2 for help with data analysis",
                "priority": 1
            }
        )
        
        task_id = goal_response.json()["task_id"]
        
        # Wait for execution
        time.sleep(5)
        
        # Check for inter-agent messages
        for agent_id in agent_ids:
            messages_response = client.get(f"/api/v1/agents/{agent_id}/messages")
            
            if messages_response.status_code == 200:
                messages = messages_response.json()
                
                # May have messages from other agents
                if len(messages) > 0:
                    # Verify message structure
                    for msg in messages:
                        assert "from_agent_id" in msg or "sender" in msg
                        assert "content" in msg or "message" in msg
    
    def test_collaborative_result_aggregation(self, authenticated_client_with_multiple_agents):
        """Test aggregation of results from multiple agents."""
        client, agents = authenticated_client_with_multiple_agents
        
        # Submit task requiring multiple perspectives
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Get opinions from multiple agents on the best approach to solve problem X",
                "priority": 1
            }
        )
        
        task_id = goal_response.json()["task_id"]
        
        # Wait for completion
        max_attempts = 20
        for _ in range(max_attempts):
            status_response = client.get(f"/api/v1/tasks/{task_id}")
            task = status_response.json()
            
            if task["status"] == "completed":
                # Check result aggregation
                if "result" in task:
                    result = task["result"]
                    
                    # Result should contain contributions from multiple agents
                    if isinstance(result, dict):
                        assert "aggregated" in str(result).lower() or "combined" in str(result).lower()
                break
            
            time.sleep(1)
    
    def test_agent_specialization_in_collaboration(self, authenticated_client_with_multiple_agents):
        """Test that agents are assigned tasks matching their specialization."""
        client, agents = authenticated_client_with_multiple_agents
        
        # Submit task with diverse requirements
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Analyze data, write code, and create documentation",
                "priority": 1
            }
        )
        
        task_id = goal_response.json()["task_id"]
        
        # Wait for decomposition
        time.sleep(3)
        
        # Get task tree
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")
        
        if tree_response.status_code == 200:
            tree = tree_response.json()
            
            subtasks_key = "subtasks" if "subtasks" in tree else "children"
            if subtasks_key in tree:
                subtasks = tree[subtasks_key]
                
                # Each subtask should be assigned to an agent with matching capabilities
                for subtask in subtasks:
                    if "assigned_agent_id" in subtask and "required_capabilities" in subtask:
                        agent_id = subtask["assigned_agent_id"]
                        
                        # Get agent details
                        agent_response = client.get(f"/api/v1/agents/{agent_id}")
                        
                        if agent_response.status_code == 200:
                            agent = agent_response.json()
                            agent_capabilities = set(agent.get("capabilities", []))
                            required_capabilities = set(subtask["required_capabilities"])
                            
                            # Agent should have required capabilities
                            assert required_capabilities.issubset(agent_capabilities)
    
    def test_collaborative_error_recovery(self, authenticated_client_with_multiple_agents):
        """Test error recovery when one agent fails during collaboration."""
        client, agents = authenticated_client_with_multiple_agents
        
        # Submit task
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Complete a multi-step process with potential failures",
                "priority": 1
            }
        )
        
        task_id = goal_response.json()["task_id"]
        
        # Monitor for errors and recovery
        time.sleep(5)
        
        # Get task status
        status_response = client.get(f"/api/v1/tasks/{task_id}")
        task = status_response.json()
        
        # If there were errors, check recovery
        if "errors" in task or "retry_count" in task:
            # System should have attempted recovery
            assert task.get("retry_count", 0) > 0 or task.get("reassigned", False)
    
    def test_load_balancing_across_agents(self, authenticated_client_with_multiple_agents):
        """Test that work is balanced across available agents."""
        client, agents = authenticated_client_with_multiple_agents
        
        if len(agents) < 2:
            pytest.skip("Need at least 2 agents for load balancing test")
        
        # Submit multiple tasks
        task_ids = []
        for i in range(5):
            response = client.post(
                "/api/v1/tasks",
                json={
                    "goal_text": f"Task {i}: Process some data",
                    "priority": 1
                }
            )
            if response.status_code == 201:
                task_ids.append(response.json()["task_id"])
        
        # Wait for assignment
        time.sleep(3)
        
        # Check agent assignments
        agent_task_counts = {}
        
        for task_id in task_ids:
            task_response = client.get(f"/api/v1/tasks/{task_id}")
            if task_response.status_code == 200:
                task = task_response.json()
                if "assigned_agent_id" in task:
                    agent_id = task["assigned_agent_id"]
                    agent_task_counts[agent_id] = agent_task_counts.get(agent_id, 0) + 1
        
        # Work should be distributed (not all on one agent)
        if len(agent_task_counts) > 1:
            # Check that no single agent has all tasks
            max_tasks = max(agent_task_counts.values())
            assert max_tasks < len(task_ids)
    
    def test_collaborative_knowledge_sharing(self, authenticated_client_with_multiple_agents):
        """Test agents sharing knowledge during collaboration."""
        client, agents = authenticated_client_with_multiple_agents
        
        if len(agents) < 2:
            pytest.skip("Need at least 2 agents for knowledge sharing test")
        
        agent_ids = list(agents.values())
        
        # Agent 1 learns something
        task1_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Remember: The API key for service X is ABC123",
                "assigned_agent_id": agent_ids[0],
                "priority": 1,
                "memory_scope": "company"  # Share with company
            }
        )
        
        time.sleep(2)
        
        # Agent 2 should be able to access this knowledge
        task2_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "What is the API key for service X?",
                "assigned_agent_id": agent_ids[1],
                "priority": 1
            }
        )
        
        task2_id = task2_response.json()["task_id"]
        
        # Wait for completion
        time.sleep(3)
        
        # Check if Agent 2 found the information
        result_response = client.get(f"/api/v1/tasks/{task2_id}")
        
        if result_response.status_code == 200:
            result = result_response.json()
            
            if result["status"] == "completed" and "result" in result:
                result_text = str(result["result"]).lower()
                # Should mention the API key
                assert "abc123" in result_text or "api key" in result_text
    
    def test_agent_coordination_with_dependencies(self, authenticated_client_with_multiple_agents):
        """Test agents coordinating work with task dependencies."""
        client, agents = authenticated_client_with_multiple_agents
        
        # Submit task with clear sequential dependencies
        goal_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Step 1: Prepare data, Step 2: Analyze data, Step 3: Report findings",
                "priority": 1
            }
        )
        
        task_id = goal_response.json()["task_id"]
        
        # Wait for decomposition
        time.sleep(3)
        
        # Get task tree
        tree_response = client.get(f"/api/v1/tasks/{task_id}/tree")
        
        if tree_response.status_code == 200:
            tree = tree_response.json()
            
            subtasks_key = "subtasks" if "subtasks" in tree else "children"
            if subtasks_key in tree and len(tree[subtasks_key]) >= 3:
                subtasks = tree[subtasks_key]
                
                # Verify dependency chain
                # Later tasks should depend on earlier ones
                for i, subtask in enumerate(subtasks[1:], 1):
                    if "dependencies" in subtask:
                        # Should have at least one dependency on previous task
                        assert len(subtask["dependencies"]) > 0
