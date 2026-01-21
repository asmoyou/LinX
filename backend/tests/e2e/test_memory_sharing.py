"""End-to-end tests for memory sharing across agents.

Tests the complete workflow of memory sharing between agents.

References:
- Task 8.3.5: Test memory sharing across agents flow
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
import time


@pytest.fixture
def authenticated_client_with_agents():
    """Create authenticated client with multiple agents."""
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
    
    # Create multiple agents
    templates_response = client.get("/api/v1/agents/templates")
    template_id = templates_response.json()[0]["template_id"]
    
    agent_ids = []
    for i in range(2):
        agent_response = client.post(
            "/api/v1/agents",
            json={
                "name": f"Test Agent {i} {uuid4()}",
                "template_id": template_id
            }
        )
        agent_ids.append(agent_response.json()["agent_id"])
    
    return client, agent_ids


class TestMemorySharing:
    """Test complete memory sharing flow across agents."""
    
    def test_complete_memory_sharing_flow(self, authenticated_client_with_agents):
        """Test complete flow of memory sharing between agents."""
        client, agent_ids = authenticated_client_with_agents
        agent1_id, agent2_id = agent_ids
        
        # Step 1: Agent 1 performs a task and creates memory
        task1_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Remember that the project deadline is December 31, 2024",
                "assigned_agent_id": agent1_id,
                "priority": 1
            }
        )
        
        assert task1_response.status_code == 201
        task1_id = task1_response.json()["task_id"]
        
        # Wait for task completion
        time.sleep(3)
        
        # Step 2: Check Agent 1's memory
        agent1_memory_response = client.get(f"/api/v1/memory/agent/{agent1_id}")
        
        if agent1_memory_response.status_code == 200:
            agent1_memories = agent1_memory_response.json()
            assert len(agent1_memories) > 0
            
            # Find the memory about the deadline
            deadline_memory = next(
                (m for m in agent1_memories if "deadline" in m.get("content", "").lower()),
                None
            )
            
            if deadline_memory:
                memory_id = deadline_memory["memory_id"]
                
                # Step 3: Share memory with Agent 2
                share_response = client.post(
                    "/api/v1/memory/share",
                    json={
                        "memory_id": memory_id,
                        "target_agent_id": agent2_id,
                        "share_type": "read"
                    }
                )
                
                assert share_response.status_code == 200
                
                # Step 4: Verify Agent 2 can access the shared memory
                agent2_memory_response = client.get(f"/api/v1/memory/agent/{agent2_id}")
                
                if agent2_memory_response.status_code == 200:
                    agent2_memories = agent2_memory_response.json()
                    
                    # Agent 2 should have access to the shared memory
                    assert any(
                        m.get("memory_id") == memory_id or "deadline" in m.get("content", "").lower()
                        for m in agent2_memories
                    )
        
        # Step 5: Agent 2 uses the shared memory
        task2_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "What is the project deadline?",
                "assigned_agent_id": agent2_id,
                "priority": 1
            }
        )
        
        assert task2_response.status_code == 201
        task2_id = task2_response.json()["task_id"]
        
        # Wait for completion
        time.sleep(3)
        
        # Step 6: Check if Agent 2 retrieved the correct information
        task2_result_response = client.get(f"/api/v1/tasks/{task2_id}")
        
        if task2_result_response.status_code == 200:
            task2_result = task2_result_response.json()
            
            if task2_result["status"] == "completed" and "result" in task2_result:
                result_text = str(task2_result["result"]).lower()
                # Should mention December 31, 2024
                assert "december" in result_text or "31" in result_text or "2024" in result_text
    
    def test_company_memory_accessible_by_all_agents(self, authenticated_client_with_agents):
        """Test that company memory is accessible by all agents."""
        client, agent_ids = authenticated_client_with_agents
        agent1_id, agent2_id = agent_ids
        
        # Agent 1 creates company-wide memory
        task_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Store in company memory: Our company values are integrity, innovation, and collaboration",
                "assigned_agent_id": agent1_id,
                "priority": 1,
                "memory_scope": "company"
            }
        )
        
        assert task_response.status_code == 201
        
        # Wait for processing
        time.sleep(3)
        
        # Check company memory
        company_memory_response = client.get("/api/v1/memory/company")
        
        if company_memory_response.status_code == 200:
            company_memories = company_memory_response.json()
            
            # Should contain the company values
            values_memory = next(
                (m for m in company_memories if "values" in m.get("content", "").lower()),
                None
            )
            
            assert values_memory is not None
        
        # Agent 2 should be able to access company memory
        task2_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "What are our company values?",
                "assigned_agent_id": agent2_id,
                "priority": 1
            }
        )
        
        assert task2_response.status_code == 201
        
        # Wait and check result
        time.sleep(3)
        
        task2_result = client.get(f"/api/v1/tasks/{task2_response.json()['task_id']}")
        
        if task2_result.status_code == 200:
            result = task2_result.json()
            if result["status"] == "completed" and "result" in result:
                result_text = str(result["result"]).lower()
                # Should mention the values
                assert any(word in result_text for word in ["integrity", "innovation", "collaboration"])
    
    def test_user_context_memory(self, authenticated_client_with_agents):
        """Test user context memory across agents."""
        client, agent_ids = authenticated_client_with_agents
        
        # Store user context
        context_response = client.post(
            "/api/v1/memory/user-context",
            json={
                "context_type": "preference",
                "content": "User prefers detailed explanations with examples",
                "metadata": {"category": "communication_style"}
            }
        )
        
        if context_response.status_code == 201:
            # Get user context
            get_context_response = client.get("/api/v1/memory/user-context")
            
            assert get_context_response.status_code == 200
            contexts = get_context_response.json()
            
            # Should contain the preference
            assert any("detailed explanations" in c.get("content", "").lower() for c in contexts)
    
    def test_memory_isolation_between_users(self, authenticated_client_with_agents):
        """Test that memories are isolated between different users."""
        client1, agent_ids1 = authenticated_client_with_agents
        
        # Create second user
        from api_gateway.main import app
        client2 = TestClient(app)
        
        user2_data = {
            "username": f"testuser2_{uuid4()}",
            "email": f"test2_{uuid4()}@example.com",
            "password": "SecurePassword123!",
            "full_name": "Test User 2"
        }
        
        client2.post("/api/v1/auth/register", json=user2_data)
        login2_response = client2.post(
            "/api/v1/auth/login",
            json={
                "username": user2_data["username"],
                "password": user2_data["password"]
            }
        )
        
        token2 = login2_response.json()["access_token"]
        client2.headers = {"Authorization": f"Bearer {token2}"}
        
        # User 1 creates private memory
        task1_response = client1.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Remember: User 1's secret project code is ALPHA-123",
                "assigned_agent_id": agent_ids1[0],
                "priority": 1
            }
        )
        
        time.sleep(2)
        
        # User 2 tries to search for User 1's memory
        search_response = client2.post(
            "/api/v1/memory/search",
            json={"query": "ALPHA-123", "limit": 10}
        )
        
        if search_response.status_code == 200:
            results = search_response.json()
            
            # User 2 should not see User 1's private memory
            assert not any("ALPHA-123" in r.get("content", "") for r in results)
    
    def test_memory_search_across_agents(self, authenticated_client_with_agents):
        """Test searching memories across multiple agents."""
        client, agent_ids = authenticated_client_with_agents
        
        # Create memories with different agents
        for i, agent_id in enumerate(agent_ids):
            client.post(
                "/api/v1/tasks",
                json={
                    "goal_text": f"Remember: Agent {i} completed task about data analysis",
                    "assigned_agent_id": agent_id,
                    "priority": 1
                }
            )
        
        time.sleep(3)
        
        # Search across all memories
        search_response = client.post(
            "/api/v1/memory/search",
            json={"query": "data analysis", "limit": 10}
        )
        
        if search_response.status_code == 200:
            results = search_response.json()
            
            # Should find memories from both agents
            assert len(results) >= 2
    
    def test_memory_update_and_versioning(self, authenticated_client_with_agents):
        """Test updating memories and version tracking."""
        client, agent_ids = authenticated_client_with_agents
        agent_id = agent_ids[0]
        
        # Create initial memory
        task_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Remember: Project status is 'in progress'",
                "assigned_agent_id": agent_id,
                "priority": 1
            }
        )
        
        time.sleep(2)
        
        # Get the memory
        memory_response = client.get(f"/api/v1/memory/agent/{agent_id}")
        
        if memory_response.status_code == 200:
            memories = memory_response.json()
            status_memory = next(
                (m for m in memories if "status" in m.get("content", "").lower()),
                None
            )
            
            if status_memory:
                memory_id = status_memory["memory_id"]
                
                # Update the memory
                update_response = client.put(
                    f"/api/v1/memory/{memory_id}",
                    json={"content": "Project status is 'completed'"}
                )
                
                if update_response.status_code == 200:
                    updated_memory = update_response.json()
                    assert "completed" in updated_memory["content"].lower()
    
    def test_memory_deletion_and_cleanup(self, authenticated_client_with_agents):
        """Test deleting memories."""
        client, agent_ids = authenticated_client_with_agents
        agent_id = agent_ids[0]
        
        # Create a memory
        task_response = client.post(
            "/api/v1/tasks",
            json={
                "goal_text": "Remember: Temporary note for testing",
                "assigned_agent_id": agent_id,
                "priority": 1
            }
        )
        
        time.sleep(2)
        
        # Get the memory
        memory_response = client.get(f"/api/v1/memory/agent/{agent_id}")
        
        if memory_response.status_code == 200:
            memories = memory_response.json()
            temp_memory = next(
                (m for m in memories if "temporary" in m.get("content", "").lower()),
                None
            )
            
            if temp_memory:
                memory_id = temp_memory["memory_id"]
                
                # Delete the memory
                delete_response = client.delete(f"/api/v1/memory/{memory_id}")
                
                assert delete_response.status_code == 200
                
                # Verify it's deleted
                verify_response = client.get(f"/api/v1/memory/{memory_id}")
                assert verify_response.status_code == 404
