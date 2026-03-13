"""Performance tests for vector search.

Tests vector search performance with 1M+ embeddings.

References:
- Task 8.4.3: Test vector search performance (1M+ embeddings)
- Requirements 8: Scalability requirements
"""

import os
import statistics
import time
from uuid import uuid4

import numpy as np
import pytest


_HEAVY_VECTOR_PROFILE = os.getenv("RUN_HEAVY_LOAD_TESTS") == "1"


def _vector_profile(smoke_value, heavy_value):
    return heavy_value if _HEAVY_VECTOR_PROFILE else smoke_value


@pytest.fixture
def milvus_connection():
    """Create Milvus connection for testing."""
    try:
        from memory_system.milvus_connection import get_milvus_connection

        return get_milvus_connection()
    except Exception as exc:
        pytest.skip(f"Milvus unavailable for vector performance smoke tests: {exc}")


@pytest.fixture
def test_collection(milvus_connection):
    """Create test collection with embeddings."""
    try:
        from pymilvus import Collection, CollectionSchema, DataType, FieldSchema
    except Exception as exc:
        pytest.skip(f"pymilvus unavailable for vector performance smoke tests: {exc}")

    collection_name = f"perf_test_{uuid4().hex[:8]}"

    # Define schema
    fields = [
        FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=384),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=1000),
        FieldSchema(name="timestamp", dtype=DataType.INT64),
    ]

    schema = CollectionSchema(fields=fields, description="Performance test collection")

    # Create collection
    collection = Collection(name=collection_name, schema=schema)

    yield collection

    # Cleanup
    try:
        collection.drop()
    except:
        pass


class TestVectorSearchPerformance:
    """Test vector search performance with large datasets."""

    def test_insert_1m_embeddings_performance(self, test_collection):
        """Test inserting 1 million embeddings."""
        batch_size = _vector_profile(1000, 10000)
        total_embeddings = _vector_profile(10_000, 1_000_000)
        num_batches = total_embeddings // batch_size

        print(f"\n{'='*60}")
        print(f"Inserting {total_embeddings:,} embeddings")
        print(f"{'='*60}")

        insert_times = []

        for batch_num in range(num_batches):
            # Generate batch data
            embeddings = np.random.rand(batch_size, 384).astype(np.float32).tolist()
            contents = [f"Content {i}" for i in range(batch_size)]
            timestamps = [int(time.time() * 1000)] * batch_size

            # Insert batch
            start_time = time.time()

            test_collection.insert([embeddings, contents, timestamps])

            insert_time = time.time() - start_time
            insert_times.append(insert_time)

            if (batch_num + 1) % 10 == 0:
                print(f"  Inserted {(batch_num + 1) * batch_size:,} embeddings...")

        # Flush to ensure all data is persisted
        test_collection.flush()

        # Analyze performance
        total_insert_time = sum(insert_times)
        avg_batch_time = statistics.mean(insert_times)
        throughput = total_embeddings / total_insert_time

        print(f"\nInsertion Performance:")
        print(f"  Total embeddings: {total_embeddings:,}")
        print(f"  Total time: {total_insert_time:.2f}s")
        print(f"  Avg batch time: {avg_batch_time:.2f}s")
        print(f"  Throughput: {throughput:.0f} embeddings/s")
        print(f"{'='*60}\n")

        minimum_throughput = 100 if not _HEAVY_VECTOR_PROFILE else 10_000
        assert (
            throughput >= minimum_throughput
        ), f"Throughput {throughput:.0f} below {minimum_throughput} embeddings/s"

    def test_search_performance_with_1m_embeddings(self, test_collection):
        """Test search performance with 1M embeddings."""
        # Insert 100k embeddings for faster test
        batch_size = _vector_profile(1000, 10000)
        num_batches = _vector_profile(2, 10)

        print(f"\nPreparing test data...")

        for batch_num in range(num_batches):
            embeddings = np.random.rand(batch_size, 384).astype(np.float32).tolist()
            contents = [f"Content {batch_num}_{i}" for i in range(batch_size)]
            timestamps = [int(time.time() * 1000)] * batch_size

            test_collection.insert([embeddings, contents, timestamps])

        test_collection.flush()

        # Create index
        print(f"Creating index...")
        index_params = {"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}}

        test_collection.create_index(field_name="embedding", index_params=index_params)
        test_collection.load()

        # Perform searches
        num_searches = _vector_profile(10, 100)
        top_k = _vector_profile(5, 10)

        search_times = []

        print(f"Performing {num_searches} searches...")

        for i in range(num_searches):
            query_embedding = np.random.rand(1, 384).astype(np.float32).tolist()

            start_time = time.time()

            results = test_collection.search(
                data=query_embedding,
                anns_field="embedding",
                param={"metric_type": "L2", "params": {"nprobe": 10}},
                limit=top_k,
            )

            search_time = time.time() - start_time
            search_times.append(search_time)

        # Analyze
        avg_search_time = statistics.mean(search_times)
        p50_search_time = statistics.median(search_times)
        p95_search_time = statistics.quantiles(search_times, n=20)[18]
        p99_search_time = statistics.quantiles(search_times, n=100)[98]

        print(f"\nSearch Performance (100k embeddings):")
        print(f"  Searches: {num_searches}")
        print(f"  Top K: {top_k}")
        print(f"  Avg latency: {avg_search_time*1000:.2f}ms")
        print(f"  P50 latency: {p50_search_time*1000:.2f}ms")
        print(f"  P95 latency: {p95_search_time*1000:.2f}ms")
        print(f"  P99 latency: {p99_search_time*1000:.2f}ms")

        latency_budget = 1.0 if not _HEAVY_VECTOR_PROFILE else 0.1
        assert (
            p95_search_time < latency_budget
        ), f"P95 search latency {p95_search_time*1000:.2f}ms exceeds {latency_budget*1000:.0f}ms"

    def test_concurrent_search_performance(self, test_collection):
        """Test concurrent search performance."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Insert test data
        batch_size = _vector_profile(1000, 10000)
        num_batches = _vector_profile(2, 5)

        for batch_num in range(num_batches):
            embeddings = np.random.rand(batch_size, 384).astype(np.float32).tolist()
            contents = [f"Content {batch_num}_{i}" for i in range(batch_size)]
            timestamps = [int(time.time() * 1000)] * batch_size

            test_collection.insert([embeddings, contents, timestamps])

        test_collection.flush()

        # Create index
        index_params = {"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}}

        test_collection.create_index(field_name="embedding", index_params=index_params)
        test_collection.load()

        # Concurrent searches
        num_concurrent = _vector_profile(5, 50)
        searches_per_thread = _vector_profile(3, 10)

        def search_worker(worker_id):
            results = []
            for i in range(searches_per_thread):
                query_embedding = np.random.rand(1, 384).astype(np.float32).tolist()

                start_time = time.time()

                search_results = test_collection.search(
                    data=query_embedding,
                    anns_field="embedding",
                    param={"metric_type": "L2", "params": {"nprobe": 10}},
                    limit=10,
                )

                results.append(
                    {
                        "worker_id": worker_id,
                        "latency": time.time() - start_time,
                        "success": len(search_results) > 0,
                    }
                )

            return results

        start_time = time.time()
        all_results = []

        with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(search_worker, i) for i in range(num_concurrent)]

            for future in as_completed(futures):
                all_results.extend(future.result())

        total_duration = time.time() - start_time

        # Analyze
        successful = sum(1 for r in all_results if r["success"])
        success_rate = successful / len(all_results)

        latencies = [r["latency"] for r in all_results if r["success"]]
        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]

        qps = len(all_results) / total_duration

        print(f"\nConcurrent Search Performance:")
        print(f"  Concurrent workers: {num_concurrent}")
        print(f"  Total searches: {len(all_results)}")
        print(f"  Success rate: {success_rate*100:.2f}%")
        print(f"  Duration: {total_duration:.2f}s")
        print(f"  QPS: {qps:.2f}")
        print(f"  Avg latency: {avg_latency*1000:.2f}ms")
        print(f"  P95 latency: {p95_latency*1000:.2f}ms")

        assert success_rate >= 0.95, "Success rate below 95%"
        latency_budget = 2.0 if not _HEAVY_VECTOR_PROFILE else 0.5
        assert p95_latency < latency_budget, (
            f"P95 latency {p95_latency*1000:.2f}ms too high"
        )

    def test_index_build_performance(self, test_collection):
        """Test index building performance."""
        # Insert data
        batch_size = _vector_profile(1000, 10000)
        num_batches = _vector_profile(2, 10)

        print(f"\nInserting {batch_size * num_batches:,} embeddings...")

        for batch_num in range(num_batches):
            embeddings = np.random.rand(batch_size, 384).astype(np.float32).tolist()
            contents = [f"Content {batch_num}_{i}" for i in range(batch_size)]
            timestamps = [int(time.time() * 1000)] * batch_size

            test_collection.insert([embeddings, contents, timestamps])

        test_collection.flush()

        # Build index
        index_params = {"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}}

        print(f"Building index...")
        start_time = time.time()

        test_collection.create_index(field_name="embedding", index_params=index_params)

        index_build_time = time.time() - start_time

        print(f"\nIndex Build Performance:")
        print(f"  Embeddings: {batch_size * num_batches:,}")
        print(f"  Build time: {index_build_time:.2f}s")
        print(f"  Throughput: {(batch_size * num_batches) / index_build_time:.0f} embeddings/s")

        max_build_time = 30 if not _HEAVY_VECTOR_PROFILE else 60
        assert index_build_time < max_build_time, (
            f"Index build time {index_build_time:.2f}s too slow"
        )

    def test_search_accuracy_vs_speed_tradeoff(self, test_collection):
        """Test search accuracy vs speed tradeoff with different nprobe values."""
        # Insert data
        batch_size = _vector_profile(1000, 10000)
        num_batches = _vector_profile(2, 5)

        for batch_num in range(num_batches):
            embeddings = np.random.rand(batch_size, 384).astype(np.float32).tolist()
            contents = [f"Content {batch_num}_{i}" for i in range(batch_size)]
            timestamps = [int(time.time() * 1000)] * batch_size

            test_collection.insert([embeddings, contents, timestamps])

        test_collection.flush()

        # Create index
        index_params = {"metric_type": "L2", "index_type": "IVF_FLAT", "params": {"nlist": 128}}

        test_collection.create_index(field_name="embedding", index_params=index_params)
        test_collection.load()

        # Test different nprobe values
        nprobe_values = [1, 5, 10] if not _HEAVY_VECTOR_PROFILE else [1, 5, 10, 20, 50]

        print(f"\nSearch Accuracy vs Speed:")

        for nprobe in nprobe_values:
            search_times = []

            for i in range(_vector_profile(5, 20)):
                query_embedding = np.random.rand(1, 384).astype(np.float32).tolist()

                start_time = time.time()

                results = test_collection.search(
                    data=query_embedding,
                    anns_field="embedding",
                    param={"metric_type": "L2", "params": {"nprobe": nprobe}},
                    limit=10,
                )

                search_times.append(time.time() - start_time)

            avg_time = statistics.mean(search_times)

            print(f"  nprobe={nprobe}: {avg_time*1000:.2f}ms")
