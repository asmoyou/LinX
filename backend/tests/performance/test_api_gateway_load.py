"""Performance tests for API Gateway load testing.

Tests API Gateway performance under high load (1000 req/s target).

References:
- Task 8.4.1: Load test API Gateway (1000 req/s)
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
def api_client():
    """Create API test client."""
    from api_gateway.main import app
    return TestClient(app)


@pytest.fixture
def authenticated_token(api_client):
    """Get authentication token for load testing."""
    # Register and login
    user_data = {
        "username": f"loadtest_{uuid4()}",
        "email": f"loadtest_{uuid4()}@example.com",
        "password": "LoadTest123!",
        "full_name": "Load Test User"
    }
    
    api_client.post("/api/v1/auth/register", json=user_data)
    login_response = api_client.post(
        "/api/v1/auth/login",
        json={
            "username": user_data["username"],
            "password": user_data["password"]
        }
    )
    
    return login_response.json()["access_token"]


class TestAPIGatewayLoad:
    """Test API Gateway performance under load."""
    
    def test_api_gateway_throughput_1000_rps(self, api_client, authenticated_token):
        """Test API Gateway can handle 1000 requests per second."""
        target_rps = 1000
        duration_seconds = 10
        total_requests = target_rps * duration_seconds
        
        headers = {"Authorization": f"Bearer {authenticated_token}"}
        
        # Prepare test data
        def make_request(request_id):
            start_time = time.time()
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)
                end_time = time.time()
                
                return {
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "latency": end_time - start_time,
                    "success": response.status_code == 200
                }
            except Exception as e:
                end_time = time.time()
                return {
                    "request_id": request_id,
                    "status_code": 0,
                    "latency": end_time - start_time,
                    "success": False,
                    "error": str(e)
                }
        
        # Execute load test
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [
                executor.submit(make_request, i)
                for i in range(total_requests)
            ]
            
            for future in as_completed(futures):
                results.append(future.result())
        
        end_time = time.time()
        total_duration = end_time - start_time
        
        # Analyze results
        successful_requests = sum(1 for r in results if r["success"])
        failed_requests = len(results) - successful_requests
        actual_rps = len(results) / total_duration
        
        latencies = [r["latency"] for r in results if r["success"]]
        
        if latencies:
            avg_latency = statistics.mean(latencies)
            p50_latency = statistics.median(latencies)
            p95_latency = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
            p99_latency = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
            max_latency = max(latencies)
        else:
            avg_latency = p50_latency = p95_latency = p99_latency = max_latency = 0
        
        # Print results
        print(f"\n{'='*60}")
        print(f"API Gateway Load Test Results")
        print(f"{'='*60}")
        print(f"Target RPS: {target_rps}")
        print(f"Actual RPS: {actual_rps:.2f}")
        print(f"Total Requests: {len(results)}")
        print(f"Successful: {successful_requests}")
        print(f"Failed: {failed_requests}")
        print(f"Success Rate: {(successful_requests/len(results)*100):.2f}%")
        print(f"Duration: {total_duration:.2f}s")
        print(f"\nLatency Statistics (ms):")
        print(f"  Average: {avg_latency*1000:.2f}")
        print(f"  P50: {p50_latency*1000:.2f}")
        print(f"  P95: {p95_latency*1000:.2f}")
        print(f"  P99: {p99_latency*1000:.2f}")
        print(f"  Max: {max_latency*1000:.2f}")
        print(f"{'='*60}\n")
        
        # Assertions
        assert actual_rps >= target_rps * 0.8, f"RPS {actual_rps:.2f} is below 80% of target {target_rps}"
        assert (successful_requests / len(results)) >= 0.95, "Success rate below 95%"
        assert p95_latency < 1.0, f"P95 latency {p95_latency*1000:.2f}ms exceeds 1000ms"
    
    def test_api_gateway_concurrent_connections(self, api_client, authenticated_token):
        """Test API Gateway with high concurrent connections."""
        concurrent_connections = 500
        requests_per_connection = 10
        
        headers = {"Authorization": f"Bearer {authenticated_token}"}
        
        def connection_worker(connection_id):
            results = []
            for i in range(requests_per_connection):
                start_time = time.time()
                try:
                    response = api_client.get("/api/v1/users/me", headers=headers)
                    latency = time.time() - start_time
                    results.append({
                        "success": response.status_code == 200,
                        "latency": latency
                    })
                except Exception as e:
                    results.append({
                        "success": False,
                        "latency": time.time() - start_time,
                        "error": str(e)
                    })
            return results
        
        start_time = time.time()
        all_results = []
        
        with ThreadPoolExecutor(max_workers=concurrent_connections) as executor:
            futures = [
                executor.submit(connection_worker, i)
                for i in range(concurrent_connections)
            ]
            
            for future in as_completed(futures):
                all_results.extend(future.result())
        
        duration = time.time() - start_time
        
        # Analyze
        successful = sum(1 for r in all_results if r["success"])
        success_rate = successful / len(all_results)
        
        print(f"\nConcurrent Connections Test:")
        print(f"  Connections: {concurrent_connections}")
        print(f"  Requests per connection: {requests_per_connection}")
        print(f"  Total requests: {len(all_results)}")
        print(f"  Success rate: {success_rate*100:.2f}%")
        print(f"  Duration: {duration:.2f}s")
        
        assert success_rate >= 0.95, "Success rate below 95%"
    
    def test_api_gateway_different_endpoints(self, api_client, authenticated_token):
        """Test load across different API endpoints."""
        endpoints = [
            ("/api/v1/users/me", "GET", None),
            ("/api/v1/agents", "GET", None),
            ("/api/v1/tasks", "GET", None),
            ("/api/v1/knowledge", "GET", None),
        ]
        
        requests_per_endpoint = 250
        headers = {"Authorization": f"Bearer {authenticated_token}"}
        
        def make_request(endpoint, method, data):
            start_time = time.time()
            try:
                if method == "GET":
                    response = api_client.get(endpoint, headers=headers)
                elif method == "POST":
                    response = api_client.post(endpoint, headers=headers, json=data)
                
                return {
                    "endpoint": endpoint,
                    "success": response.status_code in [200, 201],
                    "latency": time.time() - start_time
                }
            except Exception as e:
                return {
                    "endpoint": endpoint,
                    "success": False,
                    "latency": time.time() - start_time,
                    "error": str(e)
                }
        
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for endpoint, method, data in endpoints:
                for _ in range(requests_per_endpoint):
                    futures.append(executor.submit(make_request, endpoint, method, data))
            
            for future in as_completed(futures):
                results.append(future.result())
        
        duration = time.time() - start_time
        
        # Analyze per endpoint
        print(f"\nMulti-Endpoint Load Test:")
        for endpoint, _, _ in endpoints:
            endpoint_results = [r for r in results if r["endpoint"] == endpoint]
            successful = sum(1 for r in endpoint_results if r["success"])
            success_rate = successful / len(endpoint_results) if endpoint_results else 0
            
            latencies = [r["latency"] for r in endpoint_results if r["success"]]
            avg_latency = statistics.mean(latencies) if latencies else 0
            
            print(f"  {endpoint}:")
            print(f"    Success rate: {success_rate*100:.2f}%")
            print(f"    Avg latency: {avg_latency*1000:.2f}ms")
        
        overall_success = sum(1 for r in results if r["success"]) / len(results)
        assert overall_success >= 0.90, "Overall success rate below 90%"
    
    def test_api_gateway_sustained_load(self, api_client, authenticated_token):
        """Test API Gateway under sustained load."""
        duration_seconds = 60
        target_rps = 500
        
        headers = {"Authorization": f"Bearer {authenticated_token}"}
        
        def make_request():
            start_time = time.time()
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)
                return {
                    "success": response.status_code == 200,
                    "latency": time.time() - start_time,
                    "timestamp": start_time
                }
            except:
                return {
                    "success": False,
                    "latency": time.time() - start_time,
                    "timestamp": start_time
                }
        
        start_time = time.time()
        results = []
        
        with ThreadPoolExecutor(max_workers=50) as executor:
            while time.time() - start_time < duration_seconds:
                batch_start = time.time()
                
                # Submit batch of requests
                futures = [executor.submit(make_request) for _ in range(target_rps // 10)]
                
                for future in as_completed(futures):
                    results.append(future.result())
                
                # Rate limiting
                batch_duration = time.time() - batch_start
                sleep_time = max(0, 0.1 - batch_duration)
                time.sleep(sleep_time)
        
        # Analyze sustained performance
        total_duration = time.time() - start_time
        actual_rps = len(results) / total_duration
        success_rate = sum(1 for r in results if r["success"]) / len(results)
        
        # Check for performance degradation over time
        first_half = [r for r in results if r["timestamp"] < start_time + duration_seconds/2]
        second_half = [r for r in results if r["timestamp"] >= start_time + duration_seconds/2]
        
        first_half_success = sum(1 for r in first_half if r["success"]) / len(first_half)
        second_half_success = sum(1 for r in second_half if r["success"]) / len(second_half)
        
        print(f"\nSustained Load Test ({duration_seconds}s):")
        print(f"  Actual RPS: {actual_rps:.2f}")
        print(f"  Overall success rate: {success_rate*100:.2f}%")
        print(f"  First half success: {first_half_success*100:.2f}%")
        print(f"  Second half success: {second_half_success*100:.2f}%")
        
        assert success_rate >= 0.95, "Success rate below 95%"
        assert abs(first_half_success - second_half_success) < 0.05, "Performance degraded over time"
    
    def test_api_gateway_spike_load(self, api_client, authenticated_token):
        """Test API Gateway handling sudden traffic spikes."""
        normal_rps = 100
        spike_rps = 1000
        
        headers = {"Authorization": f"Bearer {authenticated_token}"}
        
        def make_request():
            start_time = time.time()
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)
                return {
                    "success": response.status_code == 200,
                    "latency": time.time() - start_time
                }
            except:
                return {"success": False, "latency": time.time() - start_time}
        
        # Normal load
        print("\nSpike Load Test:")
        print("  Phase 1: Normal load (100 RPS)")
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            normal_futures = [executor.submit(make_request) for _ in range(normal_rps)]
            normal_results = [f.result() for f in as_completed(normal_futures)]
        
        normal_success = sum(1 for r in normal_results if r["success"]) / len(normal_results)
        
        # Spike load
        print("  Phase 2: Spike load (1000 RPS)")
        
        with ThreadPoolExecutor(max_workers=100) as executor:
            spike_futures = [executor.submit(make_request) for _ in range(spike_rps)]
            spike_results = [f.result() for f in as_completed(spike_futures)]
        
        spike_success = sum(1 for r in spike_results if r["success"]) / len(spike_results)
        
        # Recovery
        print("  Phase 3: Recovery (100 RPS)")
        
        with ThreadPoolExecutor(max_workers=20) as executor:
            recovery_futures = [executor.submit(make_request) for _ in range(normal_rps)]
            recovery_results = [f.result() for f in as_completed(recovery_futures)]
        
        recovery_success = sum(1 for r in recovery_results if r["success"]) / len(recovery_results)
        
        print(f"  Normal success rate: {normal_success*100:.2f}%")
        print(f"  Spike success rate: {spike_success*100:.2f}%")
        print(f"  Recovery success rate: {recovery_success*100:.2f}%")
        
        # System should handle spike gracefully
        assert spike_success >= 0.80, "Spike handling below 80%"
        assert recovery_success >= 0.95, "System didn't recover properly"
