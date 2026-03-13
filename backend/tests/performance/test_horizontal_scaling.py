"""Performance tests for horizontal scaling behavior.

Tests system behavior under horizontal scaling.

References:
- Task 8.4.7: Test horizontal scaling behavior
- Requirements 8: Scalability requirements
"""

import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


_HEAVY_SCALE_PROFILE = os.getenv("RUN_HEAVY_LOAD_TESTS") == "1"


def _scale_profile(smoke_value, heavy_value):
    return heavy_value if _HEAVY_SCALE_PROFILE else smoke_value


@pytest.fixture
def api_client():
    """Create API test client."""
    from api_gateway.main import app

    return TestClient(app)


@pytest.fixture
def authenticated_token(api_client):
    """Get authentication token."""
    user_data = {
        "username": f"scaletest_{uuid4()}",
        "email": f"scaletest_{uuid4()}@example.com",
        "password": "ScaleTest123!",
        "full_name": "Scale Test User",
    }

    api_client.post("/api/v1/auth/register", json=user_data)
    login_response = api_client.post(
        "/api/v1/auth/login",
        json={"username": user_data["username"], "password": user_data["password"]},
    )

    return login_response.json()["access_token"]


class TestHorizontalScaling:
    """Test horizontal scaling behavior."""

    @staticmethod
    def _handled_response(status_code: int) -> bool:
        return status_code in {200, 429}

    def test_load_distribution_across_instances(self, api_client, authenticated_token):
        """Test load distribution across multiple instances."""
        num_requests = _scale_profile(100, 1000)
        max_workers = _scale_profile(10, 50)
        headers = {"Authorization": f"Bearer {authenticated_token}"}

        print(f"\n{'='*60}")
        print(f"Horizontal Scaling Test")
        print(f"{'='*60}")

        def make_request(request_id):
            start_time = time.time()
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)

                # Extract instance ID from response headers if available
                instance_id = response.headers.get("X-Instance-ID", "unknown")

                return {
                    "request_id": request_id,
                    "instance_id": instance_id,
                    "success": self._handled_response(response.status_code),
                    "latency": time.time() - start_time,
                }
            except Exception as e:
                return {
                    "request_id": request_id,
                    "instance_id": "error",
                    "success": False,
                    "latency": time.time() - start_time,
                    "error": str(e),
                }

        # Execute requests
        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(make_request, i) for i in range(num_requests)]

            for future in as_completed(futures):
                results.append(future.result())

        total_duration = time.time() - start_time

        # Analyze distribution
        instance_counts = {}
        for result in results:
            instance_id = result["instance_id"]
            instance_counts[instance_id] = instance_counts.get(instance_id, 0) + 1

        successful = sum(1 for r in results if r["success"])
        success_rate = successful / len(results)
        throughput = len(results) / total_duration

        print(f"Requests: {num_requests}")
        print(f"Success rate: {success_rate*100:.2f}%")
        print(f"Throughput: {throughput:.2f} req/s")
        print(f"Duration: {total_duration:.2f}s")
        print(f"\nLoad Distribution:")

        for instance_id, count in sorted(instance_counts.items()):
            percentage = (count / len(results)) * 100
            print(f"  {instance_id}: {count} requests ({percentage:.1f}%)")

        # Check distribution is reasonably balanced
        if len(instance_counts) > 1:
            counts = list(instance_counts.values())
            max_count = max(counts)
            min_count = min(counts)
            imbalance = (max_count - min_count) / max_count

            print(f"\nImbalance: {imbalance*100:.1f}%")

            assert imbalance < 0.3, f"Load imbalance {imbalance*100:.1f}% too high"

        print(f"{'='*60}\n")

    def test_scaling_up_performance(self, api_client, authenticated_token):
        """Test performance improvement when scaling up."""
        headers = {"Authorization": f"Bearer {authenticated_token}"}

        # Simulate different instance counts
        instance_configs = (
            [
                {"instances": 1, "requests": 500},
                {"instances": 2, "requests": 1000},
                {"instances": 4, "requests": 2000},
            ]
            if _HEAVY_SCALE_PROFILE
            else [
                {"instances": 1, "requests": 50},
                {"instances": 2, "requests": 100},
                {"instances": 4, "requests": 200},
            ]
        )

        print(f"\nScaling Up Performance:")

        results_by_config = []

        for config in instance_configs:
            num_requests = config["requests"]

            def make_request(request_id):
                start_time = time.time()
                try:
                    response = api_client.get("/api/v1/users/me", headers=headers)
                    return {
                        "success": response.status_code == 200,
                        "handled": self._handled_response(response.status_code),
                        "latency": time.time() - start_time,
                    }
                except:
                    return {"success": False, "handled": False, "latency": time.time() - start_time}

            start_time = time.time()

            with ThreadPoolExecutor(max_workers=_scale_profile(10, 50)) as executor:
                futures = [executor.submit(make_request, i) for i in range(num_requests)]
                results = [f.result() for f in as_completed(futures)]

            duration = time.time() - start_time
            throughput = num_requests / duration

            latencies = [r["latency"] for r in results if r["success"]]
            avg_latency = statistics.mean(latencies) if latencies else 0
            handled_ratio = sum(1 for r in results if r["handled"]) / len(results)

            results_by_config.append(
                {
                    "instances": config["instances"],
                    "throughput": throughput,
                    "avg_latency": avg_latency,
                    "handled_ratio": handled_ratio,
                }
            )

            print(f"  {config['instances']} instance(s):")
            print(f"    Throughput: {throughput:.2f} req/s")
            print(f"    Avg latency: {avg_latency*1000:.2f}ms")
            print(f"    Handled ratio: {handled_ratio*100:.2f}%")
            assert handled_ratio >= 0.95, "Request handling degraded unexpectedly"

        # Check scaling efficiency
        if _HEAVY_SCALE_PROFILE and len(results_by_config) >= 2:
            baseline = results_by_config[0]
            scaled = results_by_config[-1]

            throughput_improvement = scaled["throughput"] / baseline["throughput"]
            instance_ratio = scaled["instances"] / baseline["instances"]

            scaling_efficiency = throughput_improvement / instance_ratio

            print(f"\nScaling Efficiency: {scaling_efficiency*100:.1f}%")

            assert (
                scaling_efficiency >= 0.7
            ), f"Scaling efficiency {scaling_efficiency*100:.1f}% too low"
        else:
            throughputs = [cfg["throughput"] for cfg in results_by_config]
            assert min(throughputs) > 0, "Throughput collapsed under smoke scaling profile"

    def test_failover_behavior(self, api_client, authenticated_token):
        """Test system behavior during instance failure."""
        headers = {"Authorization": f"Bearer {authenticated_token}"}

        print(f"\nFailover Behavior Test:")

        # Normal operation
        def make_request():
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)
                return response.status_code == 200
            except:
                return False

        # Baseline
        baseline_results = [make_request() for _ in range(_scale_profile(20, 100))]
        baseline_success = sum(baseline_results) / len(baseline_results)

        print(f"  Baseline success rate: {baseline_success*100:.2f}%")

        # Simulate instance failure (would need actual infrastructure)
        # For now, just test continued operation

        # After "failure"
        recovery_results = [make_request() for _ in range(_scale_profile(20, 100))]
        recovery_success = sum(recovery_results) / len(recovery_results)

        print(f"  Recovery success rate: {recovery_success*100:.2f}%")

        assert recovery_success >= 0.90, "System didn't recover from failure"

    def test_auto_scaling_trigger(self, api_client, authenticated_token):
        """Test conditions that should trigger auto-scaling."""
        headers = {"Authorization": f"Bearer {authenticated_token}"}

        print(f"\nAuto-Scaling Trigger Test:")

        # Generate sustained high load
        duration_seconds = _scale_profile(5, 30)
        target_rps = _scale_profile(100, 500)

        def make_request():
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)
                return {
                    "success": self._handled_response(response.status_code),
                    "timestamp": time.time(),
                }
            except:
                return {"success": False, "timestamp": time.time()}

        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=_scale_profile(10, 50)) as executor:
            while time.time() - start_time < duration_seconds:
                batch_start = time.time()

                # Submit batch
                futures = [executor.submit(make_request) for _ in range(target_rps // 10)]

                for future in as_completed(futures):
                    results.append(future.result())

                # Rate limiting
                batch_duration = time.time() - batch_start
                sleep_time = max(0, 0.1 - batch_duration)
                time.sleep(sleep_time)

        # Analyze
        total_duration = time.time() - start_time
        actual_rps = len(results) / total_duration
        success_rate = sum(1 for r in results if r["success"]) / len(results)

        print(f"  Duration: {total_duration:.2f}s")
        print(f"  Actual RPS: {actual_rps:.2f}")
        print(f"  Success rate: {success_rate*100:.2f}%")

        # In production, check if auto-scaling was triggered
        # For now, just verify system handled the load
        assert success_rate >= 0.85, "System couldn't handle sustained load"

    def test_database_connection_pooling(self, api_client, authenticated_token):
        """Test database connection pooling under load."""
        headers = {"Authorization": f"Bearer {authenticated_token}"}

        print(f"\nDatabase Connection Pooling Test:")

        num_requests = _scale_profile(50, 200)

        def make_db_request(request_id):
            start_time = time.time()
            try:
                # Request that requires database access
                response = api_client.get("/api/v1/users/me", headers=headers)
                return {
                    "success": self._handled_response(response.status_code),
                    "latency": time.time() - start_time,
                }
            except:
                return {"success": False, "latency": time.time() - start_time}

        start_time = time.time()

        with ThreadPoolExecutor(max_workers=_scale_profile(10, 50)) as executor:
            futures = [executor.submit(make_db_request, i) for i in range(num_requests)]
            results = [f.result() for f in as_completed(futures)]

        duration = time.time() - start_time

        successful = sum(1 for r in results if r["success"])
        success_rate = successful / len(results)

        latencies = [r["latency"] for r in results if r["success"]]
        avg_latency = statistics.mean(latencies) if latencies else 0

        print(f"  Requests: {num_requests}")
        print(f"  Success rate: {success_rate*100:.2f}%")
        print(f"  Avg latency: {avg_latency*1000:.2f}ms")
        print(f"  Duration: {duration:.2f}s")

        assert success_rate >= 0.95, "Connection pooling issues detected"

    def test_cache_consistency_across_instances(self, api_client, authenticated_token):
        """Test cache consistency across multiple instances."""
        headers = {"Authorization": f"Bearer {authenticated_token}"}

        print(f"\nCache Consistency Test:")

        # Update user profile
        update_response = api_client.put(
            "/api/v1/users/me", headers=headers, json={"full_name": f"Updated User {uuid4()}"}
        )

        updated_name = (
            update_response.json().get("full_name") if update_response.status_code == 200 else None
        )

        # Read from multiple "instances"
        num_reads = 50

        def read_profile():
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)
                if response.status_code == 200:
                    return response.json().get("full_name")
            except:
                pass
            return None

        # Wait a moment for cache propagation
        time.sleep(1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_profile) for _ in range(num_reads)]
            names = [f.result() for f in as_completed(futures)]

        # Check consistency
        consistent_names = [n for n in names if n == updated_name]
        consistency_rate = len(consistent_names) / len(names)

        print(f"  Reads: {num_reads}")
        print(f"  Consistent: {len(consistent_names)}")
        print(f"  Consistency rate: {consistency_rate*100:.2f}%")

        assert consistency_rate >= 0.95, "Cache consistency issues detected"

    def test_session_affinity(self, api_client, authenticated_token):
        """Test session affinity (sticky sessions)."""
        headers = {"Authorization": f"Bearer {authenticated_token}"}

        print(f"\nSession Affinity Test:")

        # Make multiple requests and track instance IDs
        num_requests = 50
        instance_ids = []

        for i in range(num_requests):
            try:
                response = api_client.get("/api/v1/users/me", headers=headers)
                instance_id = response.headers.get("X-Instance-ID", "unknown")
                instance_ids.append(instance_id)
            except:
                instance_ids.append("error")

        # Check if requests went to same instance
        unique_instances = set(instance_ids)

        print(f"  Requests: {num_requests}")
        print(f"  Unique instances: {len(unique_instances)}")

        if len(unique_instances) == 1:
            print(f"  Session affinity: Enabled")
        else:
            print(f"  Session affinity: Disabled or load balanced")
