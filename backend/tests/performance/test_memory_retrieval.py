"""Performance tests for memory retrieval latency.

Tests memory system retrieval performance.

References:
- Task 8.4.5: Test memory retrieval latency
- Requirements 8: Scalability requirements
"""

import statistics
import time
from uuid import uuid4

import numpy as np
import pytest


@pytest.fixture
def memory_interface():
    """Get memory interface for testing."""
    from memory_system.memory_interface import MemoryInterface

    return MemoryInterface()


class TestMemoryRetrievalPerformance:
    """Test memory retrieval latency."""

    def test_agent_memory_retrieval_latency(self, memory_interface):
        """Test agent memory retrieval latency."""
        agent_id = uuid4()
        user_id = uuid4()

        # Store memories
        num_memories = 100

        print(f"\n{'='*60}")
        print(f"Agent Memory Retrieval Test")
        print(f"{'='*60}")

        print(f"Storing {num_memories} memories...")

        for i in range(num_memories):
            memory_interface.store_agent_memory(
                agent_id=agent_id,
                user_id=user_id,
                content=f"Agent memory content {i}",
                memory_type="interaction",
                metadata={"index": i},
            )

        # Retrieve memories
        num_retrievals = 50
        retrieval_times = []

        print(f"Performing {num_retrievals} retrievals...")

        for i in range(num_retrievals):
            start_time = time.time()

            memories = memory_interface.retrieve_agent_memory(
                agent_id=agent_id, query=f"memory content {i}", limit=10
            )

            retrieval_time = time.time() - start_time
            retrieval_times.append(retrieval_time)

        # Analyze
        avg_latency = statistics.mean(retrieval_times)
        p50_latency = statistics.median(retrieval_times)
        p95_latency = statistics.quantiles(retrieval_times, n=20)[18]
        p99_latency = (
            statistics.quantiles(retrieval_times, n=100)[98]
            if len(retrieval_times) >= 100
            else max(retrieval_times)
        )

        print(f"\nRetrieval Latency:")
        print(f"  Retrievals: {num_retrievals}")
        print(f"  Avg: {avg_latency*1000:.2f}ms")
        print(f"  P50: {p50_latency*1000:.2f}ms")
        print(f"  P95: {p95_latency*1000:.2f}ms")
        print(f"  P99: {p99_latency*1000:.2f}ms")
        print(f"{'='*60}\n")

        assert p95_latency < 0.5, f"P95 latency {p95_latency*1000:.2f}ms exceeds 500ms"

    def test_company_memory_retrieval_latency(self, memory_interface):
        """Test company memory retrieval latency."""
        user_id = uuid4()

        # Store company memories
        num_memories = 200

        print(f"\nStoring {num_memories} company memories...")

        for i in range(num_memories):
            memory_interface.store_company_memory(
                user_id=user_id,
                content=f"Company memory content {i}",
                memory_type="knowledge",
                metadata={"index": i},
            )

        # Retrieve
        num_retrievals = 50
        retrieval_times = []

        for i in range(num_retrievals):
            start_time = time.time()

            memories = memory_interface.retrieve_company_memory(
                query=f"company content {i}", limit=10
            )

            retrieval_times.append(time.time() - start_time)

        # Analyze
        avg_latency = statistics.mean(retrieval_times)
        p95_latency = statistics.quantiles(retrieval_times, n=20)[18]

        print(f"\nCompany Memory Retrieval:")
        print(f"  Avg latency: {avg_latency*1000:.2f}ms")
        print(f"  P95 latency: {p95_latency*1000:.2f}ms")

        assert p95_latency < 0.5, f"P95 latency {p95_latency*1000:.2f}ms too high"

    def test_memory_retrieval_with_filters(self, memory_interface):
        """Test memory retrieval with filters."""
        agent_id = uuid4()
        user_id = uuid4()

        # Store memories with different types
        memory_types = ["interaction", "decision", "knowledge", "task"]

        for i in range(100):
            memory_type = memory_types[i % len(memory_types)]

            memory_interface.store_agent_memory(
                agent_id=agent_id,
                user_id=user_id,
                content=f"Memory {i} of type {memory_type}",
                memory_type=memory_type,
                metadata={"index": i, "type": memory_type},
            )

        # Retrieve with filters
        retrieval_times = []

        for memory_type in memory_types:
            start_time = time.time()

            memories = memory_interface.retrieve_agent_memory(
                agent_id=agent_id, query="memory", filters={"memory_type": memory_type}, limit=10
            )

            retrieval_times.append(time.time() - start_time)

        avg_latency = statistics.mean(retrieval_times)

        print(f"\nFiltered Retrieval:")
        print(f"  Avg latency: {avg_latency*1000:.2f}ms")

        assert avg_latency < 0.5, "Filtered retrieval too slow"

    def test_concurrent_memory_retrievals(self, memory_interface):
        """Test concurrent memory retrievals."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        agent_id = uuid4()
        user_id = uuid4()

        # Store memories
        for i in range(100):
            memory_interface.store_agent_memory(
                agent_id=agent_id,
                user_id=user_id,
                content=f"Concurrent test memory {i}",
                memory_type="interaction",
            )

        # Concurrent retrievals
        num_concurrent = 20
        retrievals_per_thread = 10

        def retrieval_worker(worker_id):
            results = []
            for i in range(retrievals_per_thread):
                start_time = time.time()

                memories = memory_interface.retrieve_agent_memory(
                    agent_id=agent_id, query=f"memory {i}", limit=10
                )

                results.append(
                    {
                        "worker_id": worker_id,
                        "latency": time.time() - start_time,
                        "success": len(memories) >= 0,
                    }
                )

            return results

        start_time = time.time()
        all_results = []

        with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(retrieval_worker, i) for i in range(num_concurrent)]

            for future in as_completed(futures):
                all_results.extend(future.result())

        total_duration = time.time() - start_time

        # Analyze
        latencies = [r["latency"] for r in all_results]
        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]
        qps = len(all_results) / total_duration

        print(f"\nConcurrent Retrieval:")
        print(f"  Concurrent workers: {num_concurrent}")
        print(f"  Total retrievals: {len(all_results)}")
        print(f"  QPS: {qps:.2f}")
        print(f"  Avg latency: {avg_latency*1000:.2f}ms")
        print(f"  P95 latency: {p95_latency*1000:.2f}ms")

        assert p95_latency < 1.0, f"P95 latency {p95_latency*1000:.2f}ms too high"

    def test_memory_cache_performance(self, memory_interface):
        """Test memory caching performance."""
        agent_id = uuid4()
        user_id = uuid4()

        # Store memory
        memory_interface.store_agent_memory(
            agent_id=agent_id,
            user_id=user_id,
            content="Cached memory content",
            memory_type="interaction",
        )

        # First retrieval (cold)
        start_time = time.time()
        memories1 = memory_interface.retrieve_agent_memory(
            agent_id=agent_id, query="cached memory", limit=10
        )
        cold_latency = time.time() - start_time

        # Second retrieval (warm/cached)
        start_time = time.time()
        memories2 = memory_interface.retrieve_agent_memory(
            agent_id=agent_id, query="cached memory", limit=10
        )
        warm_latency = time.time() - start_time

        print(f"\nCache Performance:")
        print(f"  Cold latency: {cold_latency*1000:.2f}ms")
        print(f"  Warm latency: {warm_latency*1000:.2f}ms")
        print(f"  Speedup: {cold_latency/warm_latency:.2f}x")

    def test_large_result_set_retrieval(self, memory_interface):
        """Test retrieving large result sets."""
        agent_id = uuid4()
        user_id = uuid4()

        # Store many memories
        num_memories = 1000

        for i in range(num_memories):
            memory_interface.store_agent_memory(
                agent_id=agent_id,
                user_id=user_id,
                content=f"Large set memory {i}",
                memory_type="interaction",
            )

        # Retrieve different sizes
        result_sizes = [10, 50, 100, 500]

        print(f"\nLarge Result Set Retrieval:")

        for size in result_sizes:
            start_time = time.time()

            memories = memory_interface.retrieve_agent_memory(
                agent_id=agent_id, query="memory", limit=size
            )

            retrieval_time = time.time() - start_time

            print(f"  Limit {size}: {retrieval_time*1000:.2f}ms")
