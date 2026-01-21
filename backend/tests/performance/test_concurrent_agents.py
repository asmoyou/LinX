"""Performance tests for concurrent agent execution.

Tests system performance with 100+ concurrent agents.

References:
- Task 8.4.2: Test concurrent agent execution (100 agents)
- Requirements 8: Scalability requirements
"""

import pytest
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4
from fastapi.testclient import TestClient
import statistics


@pytest.fixture
def authenticated_client():
    """Create authenticated API client."""
    from api_gateway.main import app
    client = TestClient(app)
    
    user_data = {
        "username": f"perftest_{uuid4()}",
        "email": f"perftest_{uuid4()}@example.com",
        "password": "PerfTest123!",
        "full_name": "Performance Test User"
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
    
    return client


class TestConcurrentAgents:
    """Test concurrent agent execution performance."""
    
    def test_create_100_agents_concurrently(self, authenticated_client):
        """Test creating 100 agents concurrently."""
        num_agents = 100
        
        # Get template
        templates_response = authenticated_client.get("/api/v1/agents/templates")
        template_id = templates_response.json()[0]["template_id"]
        
        def create_agent(agent_num):
            start_time = time.time()
            try:
                response = authenticated_client.post(
                    "/api/v1/agents",
                    json={
                        "name": f"Perf Agent {agent_num}",
                        "template_id": template_id
                    }
                )
                
                return {
                    "agent_num": agent_num,
                    "success": response.status_code == 201,
                    "agent_id": response.json().get("agent_id") if response.status_code == 201 else None,
                    "latency": time.time() - start_time
                }
            except Exception as e:
                return {
                    "agent_num": agent_num,
                    "success": False,
                    "latency": time.time() - start_time,
                    "error": str(e)
                }
        
        # Create agents concurrently
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [executor.submit(create_agent, i) for i in range(num_agents)]
            
            for future in as_completed(futures):
                results.append(future.result())
        
        total_duration = time.time() - start_time
        
        # Analyze results
        successful = sum(1 for r in results if r["success"])
        success_rate = successful / len(results)
        
        latencies = [r["latency"] for r in results if r["success"]]
        avg_latency = statistics.mean(latencies) if latencies else 0
        p95_latency = statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else 0
        
        print(f"\n{'='*60}")
        print(f"Concurrent Agent Creation Test")
        print(f"{'='*60}")
        print(f"Agents created: {num_agents}")
        print(f"Successful: {successful}")
        print(f"Success rate: {success_rate*100:.2f}%")
        print(f"Total duration: {total_duration:.2f}s")
        print(f"Avg latency: {avg_latency*1000:.2f}ms")
        print(f"P95 latency: {p95_latency*1000:.2f}ms")
        print(f"{'='*60}\n")
        
        # Cleanup
        agent_ids = [r["agent_id"] for r in results if r["agent_id"]]
        for agent_id in agent_ids:
            try:
                authenticated_client.delete(f"/api/v1/agents/{agent_id}")
            except:
                pass
        
        assert success_rate >= 0.95, f"Success rate {success_rate*100:.2f}% below 95%"
        assert avg_latency < 5.0, f"Average latency {avg_latency:.2f}s exceeds 5s"
    
    def test_100_agents_executing_tasks_concurrently(self, authenticated_client):
        """Test 100 agents executing tasks concurrently."""
        num_agents = 100
        
        # Get template
        templates_response = authenticated_client.get("/api/v1/agents/templates")
        template_id = templates_response.json()[0]["template_id"]
        
        # Create agents
        print(f"\nCreating {num_agents} agents...")
        agent_ids = []
        
        for i in range(num_agents):
            response = authenticated_client.post(
                "/api/v1/agents",
                json={
                    "name": f"Exec Agent {i}",
                    "template_id": template_id
                }
            )
            if response.status_code == 201:
                agent_ids.append(response.json()["agent_id"])
        
        print(f"Created {len(agent_ids)} agents")
        
        # Assign tasks to agents
        def assign_and_execute_task(agent_id, task_num):
            start_time = time.time()
            try:
                response = authenticated_client.post(
                    "/api/v1/tasks",
                    json={
                        "goal_text": f"Calculate {task_num} + {task_num}",
                        "assigned_agent_id": agent_id,
                        "priority": 1
                    }
                )
                
                return {
                    "agent_id": agent_id,
                    "task_num": task_num,
                    "success": response.status_code == 201,
                    "task_id": response.json().get("task_id") if response.status_code == 201 else None,
                    "latency": time.time() - start_time
                }
            except Exception as e:
                return {
                    "agent_id": agent_id,
                    "task_num": task_num,
                    "success": False,
                    "latency": time.time() - start_time,
                    "error": str(e)
                }
        
        # Execute tasks concurrently
        print(f"Executing {len(agent_ids)} tasks concurrently...")
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = [
                executor.submit(assign_and_execute_task, agent_id, i)
                for i, agent_id in enumerate(agent_ids)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())
        
        execution_duration = time.time() - start_time
        
        # Analyze
        successful = sum(1 for r in results if r["success"])
        success_rate = successful / len(results)
        
        latencies = [r["latency"] for r in results if r["success"]]
        avg_latency = statistics.mean(latencies) if latencies else 0
        
        print(f"\nConcurrent Task Execution Test:")
        print(f"  Agents: {len(agent_ids)}")
        print(f"  Tasks submitted: {len(results)}")
        print(f"  Successful: {successful}")
        print(f"  Success rate: {success_rate*100:.2f}%")
        print(f"  Execution duration: {execution_duration:.2f}s")
        print(f"  Avg submission latency: {avg_latency*1000:.2f}ms")
        
        # Cleanup
        for agent_id in agent_ids:
            try:
                authenticated_client.delete(f"/api/v1/agents/{agent_id}")
            except:
                pass
        
        assert success_rate >= 0.90, f"Success rate {success_rate*100:.2f}% below 90%"
    
    def test_agent_resource_utilization(self, authenticated_client):
        """Test resource utilization with many concurrent agents."""
        num_agents = 50
        
        # Get template
        templates_response = authenticated_client.get("/api/v1/agents/templates")
        template_id = templates_response.json()[0]["template_id"]
        
        # Create agents
        agent_ids = []
        for i in range(num_agents):
            response = authenticated_client.post(
                "/api/v1/agents",
                json={
                    "name": f"Resource Agent {i}",
                    "template_id": template_id
                }
            )
            if response.status_code == 201:
                agent_ids.append(response.json()["agent_id"])
        
        # Monitor agent status
        time.sleep(2)
        
        active_agents = 0
        for agent_id in agent_ids:
            try:
                response = authenticated_client.get(f"/api/v1/agents/{agent_id}")
                if response.status_code == 200:
                    agent = response.json()
                    if agent.get("status") in ["idle", "active"]:
                        active_agents += 1
            except:
                pass
        
        print(f"\nResource Utilization Test:")
        print(f"  Agents created: {len(agent_ids)}")
        print(f"  Active agents: {active_agents}")
        print(f"  Utilization: {(active_agents/len(agent_ids)*100):.2f}%")
        
        # Cleanup
        for agent_id in agent_ids:
            try:
                authenticated_client.delete(f"/api/v1/agents/{agent_id}")
            except:
                pass
        
        assert active_agents >= len(agent_ids) * 0.95, "Too many agents failed to initialize"
    
    def test_agent_lifecycle_performance(self, authenticated_client):
        """Test agent creation, execution, and termination performance."""
        num_cycles = 20
        
        templates_response = authenticated_client.get("/api/v1/agents/templates")
        template_id = templates_response.json()[0]["template_id"]
        
        cycle_times = []
        
        for cycle in range(num_cycles):
            cycle_start = time.time()
            
            # Create agent
            create_response = authenticated_client.post(
                "/api/v1/agents",
                json={
                    "name": f"Lifecycle Agent {cycle}",
                    "template_id": template_id
                }
            )
            
            if create_response.status_code == 201:
                agent_id = create_response.json()["agent_id"]
                
                # Execute task
                task_response = authenticated_client.post(
                    "/api/v1/tasks",
                    json={
                        "goal_text": f"Task {cycle}",
                        "assigned_agent_id": agent_id,
                        "priority": 1
                    }
                )
                
                # Terminate agent
                authenticated_client.delete(f"/api/v1/agents/{agent_id}")
                
                cycle_time = time.time() - cycle_start
                cycle_times.append(cycle_time)
        
        avg_cycle_time = statistics.mean(cycle_times)
        
        print(f"\nAgent Lifecycle Performance:")
        print(f"  Cycles: {num_cycles}")
        print(f"  Avg cycle time: {avg_cycle_time:.2f}s")
        print(f"  Throughput: {1/avg_cycle_time:.2f} cycles/s")
        
        assert avg_cycle_time < 10.0, f"Cycle time {avg_cycle_time:.2f}s too slow"
    
    def test_agent_communication_overhead(self, authenticated_client):
        """Test overhead of inter-agent communication with many agents."""
        num_agents = 20
        
        templates_response = authenticated_client.get("/api/v1/agents/templates")
        template_id = templates_response.json()[0]["template_id"]
        
        # Create agents
        agent_ids = []
        for i in range(num_agents):
            response = authenticated_client.post(
                "/api/v1/agents",
                json={
                    "name": f"Comm Agent {i}",
                    "template_id": template_id
                }
            )
            if response.status_code == 201:
                agent_ids.append(response.json()["agent_id"])
        
        # Test communication between agents
        start_time = time.time()
        
        for i in range(len(agent_ids) - 1):
            # Agent i sends message to agent i+1
            try:
                authenticated_client.post(
                    f"/api/v1/agents/{agent_ids[i]}/messages",
                    json={
                        "to_agent_id": agent_ids[i+1],
                        "message": f"Test message {i}",
                        "message_type": "info"
                    }
                )
            except:
                pass
        
        communication_time = time.time() - start_time
        
        print(f"\nAgent Communication Test:")
        print(f"  Agents: {len(agent_ids)}")
        print(f"  Messages sent: {len(agent_ids)-1}")
        print(f"  Total time: {communication_time:.2f}s")
        print(f"  Avg per message: {communication_time/(len(agent_ids)-1)*1000:.2f}ms")
        
        # Cleanup
        for agent_id in agent_ids:
            try:
                authenticated_client.delete(f"/api/v1/agents/{agent_id}")
            except:
                pass
        
        avg_message_time = communication_time / (len(agent_ids) - 1)
        assert avg_message_time < 1.0, f"Message time {avg_message_time:.2f}s too slow"
