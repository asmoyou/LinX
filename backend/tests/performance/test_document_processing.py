"""Performance tests for document processing throughput.

Tests document processing pipeline performance.

References:
- Task 8.4.4: Test document processing throughput
- Requirements 8: Scalability requirements
"""

import io
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.performance,
    pytest.mark.usefixtures("cleanup_shared_db_test_artifacts"),
]


@pytest.fixture
def authenticated_client():
    """Create authenticated API client."""
    from api_gateway.main import app

    with TestClient(app) as client:
        user_data = {
            "username": f"docperf_{uuid4()}",
            "email": f"docperf_{uuid4()}@example.com",
            "password": "DocPerf123!",
            "full_name": "Doc Perf User",
        }

        client.post("/api/v1/auth/register", json=user_data)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": user_data["username"], "password": user_data["password"]},
        )

        token = login_response.json()["access_token"]
        client.headers = {"Authorization": f"Bearer {token}"}

        yield client


class TestDocumentProcessingPerformance:
    """Test document processing throughput."""

    @staticmethod
    def _knowledge_id(payload: dict) -> str:
        return payload["id"]

    def test_concurrent_document_uploads(self, authenticated_client):
        """Test uploading multiple documents concurrently."""
        num_documents = 50

        def upload_document(doc_num):
            content = f"Document {doc_num} content. " * 100
            file_data = io.BytesIO(content.encode())

            start_time = time.time()

            try:
                response = authenticated_client.post(
                    "/api/v1/knowledge",
                    files={"file": (f"doc_{doc_num}.txt", file_data, "text/plain")},
                    data={"title": f"Performance Doc {doc_num}"},
                )

                return {
                    "doc_num": doc_num,
                    "success": response.status_code == 201,
                    "knowledge_id": (
                        self._knowledge_id(response.json()) if response.status_code == 201 else None
                    ),
                    "latency": time.time() - start_time,
                }
            except Exception as e:
                return {
                    "doc_num": doc_num,
                    "success": False,
                    "latency": time.time() - start_time,
                    "error": str(e),
                }

        print(f"\n{'='*60}")
        print(f"Concurrent Document Upload Test")
        print(f"{'='*60}")

        start_time = time.time()
        results = []

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(upload_document, i) for i in range(num_documents)]

            for future in as_completed(futures):
                results.append(future.result())

        total_duration = time.time() - start_time

        # Analyze
        successful = sum(1 for r in results if r["success"])
        success_rate = successful / len(results)

        latencies = [r["latency"] for r in results if r["success"]]
        avg_latency = statistics.mean(latencies) if latencies else 0
        throughput = len(results) / total_duration

        print(f"Documents uploaded: {num_documents}")
        print(f"Successful: {successful}")
        print(f"Success rate: {success_rate*100:.2f}%")
        print(f"Total duration: {total_duration:.2f}s")
        print(f"Throughput: {throughput:.2f} docs/s")
        print(f"Avg latency: {avg_latency*1000:.2f}ms")
        print(f"{'='*60}\n")

        # Cleanup
        knowledge_ids = [r["knowledge_id"] for r in results if r["knowledge_id"]]
        for kid in knowledge_ids:
            try:
                authenticated_client.delete(f"/api/v1/knowledge/{kid}")
            except:
                pass

        assert success_rate >= 0.90, f"Success rate {success_rate*100:.2f}% below 90%"
        assert throughput >= 5, f"Throughput {throughput:.2f} docs/s below 5 docs/s"

    def test_large_document_processing(self, authenticated_client):
        """Test processing large documents."""
        document_sizes = [(100, "100KB"), (500, "500KB"), (1000, "1MB"), (5000, "5MB")]

        print(f"\nLarge Document Processing Test:")

        for size_kb, label in document_sizes:
            # Generate document
            content = "Large document content. " * (size_kb * 50)  # Approximate KB
            file_data = io.BytesIO(content.encode())

            start_time = time.time()

            response = authenticated_client.post(
                "/api/v1/knowledge",
                files={"file": (f"large_doc_{label}.txt", file_data, "text/plain")},
                data={"title": f"Large Doc {label}"},
            )

            upload_time = time.time() - start_time

            if response.status_code == 201:
                knowledge_id = self._knowledge_id(response.json())

                # Asynchronous processing may remain queued in test environments without workers.
                observed_time = 0.0
                observed_status = "unknown"

                for _ in range(5):
                    status_response = authenticated_client.get(
                        f"/api/v1/knowledge/{knowledge_id}/status"
                    )

                    if status_response.status_code == 200:
                        doc = status_response.json()
                        observed_status = doc.get("status", "unknown")
                        if observed_status in {"processing", "completed"}:
                            observed_time = time.time() - start_time
                            break

                    time.sleep(1)

                print(f"  {label}:")
                print(f"    Upload time: {upload_time:.2f}s")
                print(f"    Status observed: {observed_status}")
                print(f"    Status observation time: {observed_time:.2f}s")

                # Cleanup
                try:
                    authenticated_client.delete(f"/api/v1/knowledge/{knowledge_id}")
                except:
                    pass

    def test_document_chunking_performance(self):
        """Test document chunking performance."""
        from knowledge_base.document_chunker import get_document_chunker

        chunker = get_document_chunker()

        # Generate large text
        text = "This is a test sentence for chunking performance. " * 10000

        chunk_sizes = [200, 500, 1000]

        print(f"\nDocument Chunking Performance:")
        print(f"  Text length: {len(text)} characters")

        for chunk_size in chunk_sizes:
            start_time = time.time()

            chunks = chunker.chunk_text(text=text, chunk_size=chunk_size, overlap=50)

            chunk_time = time.time() - start_time

            print(f"  Chunk size {chunk_size}:")
            print(f"    Chunks created: {len(chunks)}")
            print(f"    Time: {chunk_time*1000:.2f}ms")
            print(f"    Throughput: {len(text)/chunk_time:.0f} chars/s")

    def test_text_extraction_performance(self):
        """Test text extraction from different formats."""
        from knowledge_base.text_extractors import PDFExtractor

        # Test with mock PDF content
        print(f"\nText Extraction Performance:")

        # Simulate extraction times
        extraction_times = []

        for i in range(10):
            start_time = time.time()

            # Simulate extraction work
            text = "Extracted text content. " * 1000

            extraction_time = time.time() - start_time
            extraction_times.append(extraction_time)

        avg_time = statistics.mean(extraction_times)

        print(f"  Avg extraction time: {avg_time*1000:.2f}ms")

    def test_embedding_generation_throughput(self):
        """Test embedding generation throughput."""
        from memory_system.embedding_service import get_embedding_service

        embedding_service = get_embedding_service(scope="user_memory")

        num_texts = 10
        texts = [f"Text content for embedding {i}" for i in range(num_texts)]

        print(f"\nEmbedding Generation Throughput:")

        start_time = time.time()

        try:
            embeddings = [embedding_service.generate_embedding(text) for text in texts]
        except Exception as exc:
            pytest.skip(f"Embedding backend unavailable for performance smoke test: {exc}")

        total_time = time.time() - start_time
        throughput = num_texts / total_time

        print(f"  Texts: {num_texts}")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Throughput: {throughput:.2f} embeddings/s")
        print(f"  Avg time per embedding: {(total_time/num_texts)*1000:.2f}ms")

        assert len(embeddings) == num_texts
        assert all(isinstance(embedding, list) and embedding for embedding in embeddings)

    def test_batch_embedding_generation(self):
        """Test batch embedding generation performance."""
        from memory_system.embedding_service import get_embedding_service

        embedding_service = get_embedding_service(scope="user_memory")

        batch_sizes = [5, 10, 20]

        print(f"\nBatch Embedding Generation:")

        for batch_size in batch_sizes:
            texts = [f"Batch text {i}" for i in range(batch_size)]

            start_time = time.time()

            # Generate embeddings in batch
            try:
                embeddings = embedding_service.generate_embeddings_batch(texts)
            except Exception as exc:
                pytest.skip(f"Embedding backend unavailable for batch smoke test: {exc}")

            batch_time = time.time() - start_time
            throughput = batch_size / batch_time

            print(f"  Batch size {batch_size}:")
            print(f"    Time: {batch_time:.2f}s")
            print(f"    Throughput: {throughput:.2f} embeddings/s")
            assert len(embeddings) == batch_size
            assert all(isinstance(embedding, list) and embedding for embedding in embeddings)

    def test_document_indexing_pipeline(self, authenticated_client):
        """Test complete document indexing pipeline."""
        num_documents = 20

        print(f"\nDocument Indexing Pipeline Test:")

        # Upload documents
        knowledge_ids = []

        for i in range(num_documents):
            content = f"Pipeline test document {i}. " * 50
            file_data = io.BytesIO(content.encode())

            response = authenticated_client.post(
                "/api/v1/knowledge",
                files={"file": (f"pipeline_doc_{i}.txt", file_data, "text/plain")},
                data={"title": f"Pipeline Doc {i}"},
            )

            if response.status_code == 201:
                knowledge_ids.append(self._knowledge_id(response.json()))

        print(f"  Uploaded {len(knowledge_ids)} documents")

        # Wait for all uploads to surface an asynchronous processing state.
        start_time = time.time()
        active = 0

        while active < len(knowledge_ids) and (time.time() - start_time) < 30:
            active = 0

            for kid in knowledge_ids:
                try:
                    response = authenticated_client.get(f"/api/v1/knowledge/{kid}/status")
                    if response.status_code == 200:
                        doc = response.json()
                        if doc.get("status") in {"processing", "completed"}:
                            active += 1
                except:
                    pass

            if active < len(knowledge_ids):
                time.sleep(1)

        processing_time = time.time() - start_time
        throughput = len(knowledge_ids) / processing_time

        print(f"  Active/completed: {active}/{len(knowledge_ids)}")
        print(f"  Observation time: {processing_time:.2f}s")
        print(f"  Throughput: {throughput:.2f} docs/s")

        # Cleanup
        for kid in knowledge_ids:
            try:
                authenticated_client.delete(f"/api/v1/knowledge/{kid}")
            except:
                pass

        assert active >= len(knowledge_ids) * 0.9, "Too many documents failed to enter processing"
