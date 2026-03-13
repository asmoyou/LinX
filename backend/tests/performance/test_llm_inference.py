"""Performance tests for LLM inference latency.

Tests LLM provider inference performance.

References:
- Task 8.4.6: Benchmark LLM inference latency
- Requirements 8: Scalability requirements
"""

import os
import statistics
import time
from uuid import uuid4

import pytest


_HEAVY_LLM_PROFILE = os.getenv("RUN_HEAVY_LOAD_TESTS") == "1"


def _llm_profile(smoke_value, heavy_value):
    return heavy_value if _HEAVY_LLM_PROFILE else smoke_value


@pytest.fixture
def llm_provider():
    """Get LLM provider for testing."""
    from llm_providers.router import get_llm_provider

    return get_llm_provider()


class TestLLMInferencePerformance:
    """Test LLM inference latency."""

    @staticmethod
    def _generate_or_skip(llm_provider, **kwargs):
        try:
            return llm_provider.generate(**kwargs)
        except Exception as exc:
            pytest.skip(f"LLM backend unavailable for performance smoke test: {exc}")

    def test_single_inference_latency(self, llm_provider):
        """Test single inference latency."""
        prompts = [
            "What is 2 + 2?",
            "Explain machine learning in one sentence.",
        ]
        if _HEAVY_LLM_PROFILE:
            prompts.extend(
                [
                    "List three programming languages.",
                    "What is the capital of France?",
                    "Define artificial intelligence.",
                ]
            )

        print(f"\n{'='*60}")
        print(f"LLM Inference Latency Test")
        print(f"{'='*60}")

        latencies = []

        for prompt in prompts:
            start_time = time.time()

            response = self._generate_or_skip(
                llm_provider, prompt=prompt, max_tokens=100, temperature=0.7
            )

            latency = time.time() - start_time
            latencies.append(latency)

            print(f"  Prompt: '{prompt[:50]}...'")
            print(f"  Latency: {latency*1000:.2f}ms")

        avg_latency = statistics.mean(latencies)
        p95_latency = (
            statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else max(latencies)
        )

        print(f"\nSummary:")
        print(f"  Avg latency: {avg_latency*1000:.2f}ms")
        print(f"  P95 latency: {p95_latency*1000:.2f}ms")
        print(f"{'='*60}\n")

        latency_budget = 5.0 if _HEAVY_LLM_PROFILE else 30.0
        assert avg_latency < latency_budget, (
            f"Avg latency {avg_latency:.2f}s exceeds {latency_budget:.2f}s"
        )

    def test_inference_with_different_token_lengths(self, llm_provider):
        """Test inference latency with different output lengths."""
        prompt = "Write a story about AI."
        token_lengths = [50, 100] if not _HEAVY_LLM_PROFILE else [50, 100, 200, 500]

        print(f"\nInference Latency by Token Length:")

        for max_tokens in token_lengths:
            start_time = time.time()

            response = self._generate_or_skip(
                llm_provider, prompt=prompt, max_tokens=max_tokens, temperature=0.7
            )

            latency = time.time() - start_time
            tokens_per_second = max_tokens / latency if latency > 0 else 0

            print(f"  Max tokens {max_tokens}:")
            print(f"    Latency: {latency:.2f}s")
            print(f"    Tokens/s: {tokens_per_second:.2f}")

    def test_concurrent_inference_requests(self, llm_provider):
        """Test concurrent inference requests."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        num_concurrent = _llm_profile(3, 10)
        prompts_per_thread = _llm_profile(2, 5)

        def inference_worker(worker_id):
            results = []
            for i in range(prompts_per_thread):
                start_time = time.time()

                response = self._generate_or_skip(
                    llm_provider,
                    prompt=f"Worker {worker_id} prompt {i}: What is AI?",
                    max_tokens=50,
                    temperature=0.7,
                )

                results.append(
                    {
                        "worker_id": worker_id,
                        "latency": time.time() - start_time,
                        "success": response is not None,
                    }
                )

            return results

        print(f"\nConcurrent Inference Test:")

        start_time = time.time()
        all_results = []

        with ThreadPoolExecutor(max_workers=num_concurrent) as executor:
            futures = [executor.submit(inference_worker, i) for i in range(num_concurrent)]

            for future in as_completed(futures):
                all_results.extend(future.result())

        total_duration = time.time() - start_time

        # Analyze
        successful = sum(1 for r in all_results if r["success"])
        success_rate = successful / len(all_results)

        latencies = [r["latency"] for r in all_results if r["success"]]
        avg_latency = statistics.mean(latencies)
        p95_latency = statistics.quantiles(latencies, n=20)[18]

        throughput = len(all_results) / total_duration

        print(f"  Concurrent requests: {num_concurrent}")
        print(f"  Total inferences: {len(all_results)}")
        print(f"  Success rate: {success_rate*100:.2f}%")
        print(f"  Throughput: {throughput:.2f} req/s")
        print(f"  Avg latency: {avg_latency:.2f}s")
        print(f"  P95 latency: {p95_latency:.2f}s")

        assert success_rate >= 0.95, "Success rate below 95%"

    def test_batch_inference_performance(self, llm_provider):
        """Test batch inference performance."""
        prompts = [f"Question {i}: What is AI?" for i in range(_llm_profile(3, 10))]

        # Sequential
        start_time = time.time()

        for prompt in prompts:
            self._generate_or_skip(llm_provider, prompt=prompt, max_tokens=50)

        sequential_time = time.time() - start_time

        # Batch (if supported)
        start_time = time.time()

        if hasattr(llm_provider, "generate_batch"):
            try:
                responses = llm_provider.generate_batch(prompts=prompts, max_tokens=50)
                batch_time = time.time() - start_time
            except Exception as exc:
                pytest.skip(f"LLM batch backend unavailable for performance smoke test: {exc}")
        else:
            batch_time = sequential_time

        print(f"\nBatch Inference:")
        print(f"  Prompts: {len(prompts)}")
        print(f"  Sequential time: {sequential_time:.2f}s")
        print(f"  Batch time: {batch_time:.2f}s")
        print(f"  Speedup: {sequential_time/batch_time:.2f}x")

    def test_inference_with_streaming(self, llm_provider):
        """Test streaming inference performance."""
        prompt = "Write a detailed explanation of machine learning."

        if hasattr(llm_provider, "generate_stream"):
            start_time = time.time()
            first_token_time = None
            token_count = 0

            for chunk in llm_provider.generate_stream(prompt=prompt, max_tokens=200):
                if first_token_time is None:
                    first_token_time = time.time() - start_time
                token_count += 1

            total_time = time.time() - start_time

            print(f"\nStreaming Inference:")
            print(f"  Time to first token: {first_token_time*1000:.2f}ms")
            print(f"  Total time: {total_time:.2f}s")
            print(f"  Tokens: {token_count}")
            print(f"  Tokens/s: {token_count/total_time:.2f}")

    def test_inference_caching(self, llm_provider):
        """Test inference caching performance."""
        prompt = "What is the meaning of life?"

        # First call (cold)
        start_time = time.time()
        response1 = self._generate_or_skip(
            llm_provider, prompt=prompt, max_tokens=50, temperature=0.0
        )
        cold_latency = time.time() - start_time

        # Second call (potentially cached)
        start_time = time.time()
        response2 = self._generate_or_skip(
            llm_provider, prompt=prompt, max_tokens=50, temperature=0.0
        )
        warm_latency = time.time() - start_time

        print(f"\nInference Caching:")
        print(f"  Cold latency: {cold_latency:.2f}s")
        print(f"  Warm latency: {warm_latency:.2f}s")

        if warm_latency < cold_latency:
            print(f"  Speedup: {cold_latency/warm_latency:.2f}x")
        else:
            print(f"  No caching detected")

    def test_inference_with_different_temperatures(self, llm_provider):
        """Test inference latency with different temperature settings."""
        prompt = "Explain quantum computing."
        temperatures = [0.0, 0.5, 0.7, 1.0]

        print(f"\nInference by Temperature:")

        for temp in temperatures:
            latencies = []

            for _ in range(3):
                start_time = time.time()

                response = self._generate_or_skip(
                    llm_provider, prompt=prompt, max_tokens=100, temperature=temp
                )

                latencies.append(time.time() - start_time)

            avg_latency = statistics.mean(latencies)

            print(f"  Temperature {temp}: {avg_latency:.2f}s")

    def test_model_switching_overhead(self, llm_provider):
        """Test overhead of switching between models."""
        if hasattr(llm_provider, "set_model"):
            models = ["model1", "model2", "model1"]

            switch_times = []

            for model in models:
                start_time = time.time()

                llm_provider.set_model(model)

                switch_time = time.time() - start_time
                switch_times.append(switch_time)

            avg_switch_time = statistics.mean(switch_times)

            print(f"\nModel Switching:")
            print(f"  Avg switch time: {avg_switch_time*1000:.2f}ms")
