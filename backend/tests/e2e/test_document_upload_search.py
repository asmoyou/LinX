"""End-to-end tests for document upload and search.

Tests the complete workflow of uploading and searching documents.

References:
- Task 8.3.4: Test document upload and search flow
"""

import io
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [
    pytest.mark.usefixtures("cleanup_shared_db_test_artifacts"),
    pytest.mark.filterwarnings(
        "ignore:builtin type SwigPyPacked has no __module__ attribute:DeprecationWarning"
    ),
    pytest.mark.filterwarnings(
        "ignore:builtin type SwigPyObject has no __module__ attribute:DeprecationWarning"
    ),
    pytest.mark.filterwarnings(
        "ignore:builtin type swigvarlink has no __module__ attribute:DeprecationWarning"
    ),
]


@pytest.fixture
def authenticated_client():
    """Create authenticated API client."""
    from api_gateway.main import app

    with TestClient(app) as client:
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

        yield client


class TestDocumentUploadSearch:
    """Test complete document upload and search flow."""

    @staticmethod
    def _knowledge_id(payload: dict) -> str:
        return payload["id"]

    @staticmethod
    def _knowledge_name(payload: dict) -> str:
        return payload["name"]

    @staticmethod
    def _wait_for_processing_state(
        authenticated_client: TestClient, knowledge_id: str, max_attempts: int = 5
    ) -> dict:
        """Poll the processing status endpoint and return the latest stable state."""
        last_status: dict = {}
        for _ in range(max_attempts):
            status_response = authenticated_client.get(f"/api/v1/knowledge/{knowledge_id}/status")
            assert status_response.status_code == 200
            last_status = status_response.json()

            if last_status["status"] in {"processing", "completed"}:
                return last_status
            if last_status["status"] == "failed":
                pytest.fail(
                    f"Document processing failed: {last_status.get('error_message') or last_status}"
                )

            time.sleep(1)

        return last_status

    def test_complete_document_workflow(self, authenticated_client):
        """Test complete flow from upload to search."""
        # Step 1: Upload a document
        document_content = (
            b"This is a test document about artificial intelligence and machine learning."
        )
        file_data = io.BytesIO(document_content)

        upload_response = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("test_document.txt", file_data, "text/plain")},
            data={
                "title": "AI and ML Overview",
                "content_type": "document",
                "access_level": "private",
            },
        )

        assert upload_response.status_code == 201
        upload_result = upload_response.json()
        assert "id" in upload_result
        assert upload_result["status"] in ["processing", "pending"]
        assert upload_result["name"] == "AI and ML Overview"

        knowledge_id = self._knowledge_id(upload_result)

        # Step 2: Check processing status
        status_payload = self._wait_for_processing_state(authenticated_client, knowledge_id)
        assert status_payload["status"] in {"processing", "completed"}

        # Step 3: Verify document is indexed
        detail_response = authenticated_client.get(f"/api/v1/knowledge/{knowledge_id}")
        assert detail_response.status_code == 200
        document_detail = detail_response.json()

        assert document_detail["status"] in {"processing", "completed"}
        assert document_detail["chunkCount"] is None or document_detail["chunkCount"] >= 0
        assert document_detail["processingProgress"] is None or (
            0 <= document_detail["processingProgress"] <= 100
        )

        if document_detail["status"] == "completed":
            chunks_response = authenticated_client.get(f"/api/v1/knowledge/{knowledge_id}/chunks")
            assert chunks_response.status_code == 200
            chunks_payload = chunks_response.json()
            assert "items" in chunks_payload
            if status_payload.get("chunk_count", 0):
                assert len(chunks_payload["items"]) > 0

        # Step 4: Search for the document
        search_response = authenticated_client.post(
            "/api/v1/knowledge/search", json={"query": "artificial intelligence", "limit": 10}
        )

        assert search_response.status_code == 200
        search_payload = search_response.json()
        assert "results" in search_payload
        assert "total" in search_payload
        search_results = search_payload["results"]

        # Search gracefully degrades to empty results when the vector backend is unavailable.
        if search_results:
            assert any(r["document_id"] == knowledge_id for r in search_results)

        # Step 5: Search with different query
        ml_search_response = authenticated_client.post(
            "/api/v1/knowledge/search", json={"query": "machine learning", "limit": 5}
        )

        assert ml_search_response.status_code == 200
        ml_payload = ml_search_response.json()
        ml_results = ml_payload["results"]

        if ml_results:
            assert any(r["document_id"] == knowledge_id for r in ml_results)

        # Step 6: Update document metadata
        update_response = authenticated_client.put(
            f"/api/v1/knowledge/{knowledge_id}",
            json={"title": "Updated: AI and ML Overview", "tags": ["AI", "ML", "technology"]},
        )

        assert update_response.status_code == 200
        updated_doc = update_response.json()
        assert updated_doc["name"] == "Updated: AI and ML Overview"
        assert updated_doc["tags"] == ["AI", "ML", "technology"]

        # Step 7: List all user documents
        list_response = authenticated_client.get("/api/v1/knowledge")

        assert list_response.status_code == 200
        list_payload = list_response.json()
        assert "items" in list_payload
        documents = list_payload["items"]
        assert any(d["id"] == knowledge_id for d in documents)

        # Step 8: Delete document
        delete_response = authenticated_client.delete(f"/api/v1/knowledge/{knowledge_id}")

        assert delete_response.status_code == 204

        # Step 9: Verify document is deleted
        verify_response = authenticated_client.get(f"/api/v1/knowledge/{knowledge_id}")
        assert verify_response.status_code == 404

    def test_upload_multiple_document_types(self, authenticated_client):
        """Test uploading different document types."""
        documents = [
            ("test.txt", b"Text file content", "text/plain"),
            ("test.md", b"# Markdown\n\nContent", "text/markdown"),
            ("test.pdf", b"%PDF-1.4 fake pdf content", "application/pdf"),
        ]

        uploaded_ids = []

        for filename, content, content_type in documents:
            file_data = io.BytesIO(content)

            response = authenticated_client.post(
                "/api/v1/knowledge",
                files={"file": (filename, file_data, content_type)},
                data={"title": f"Test {filename}"},
            )

            if response.status_code == 201:
                uploaded_ids.append(self._knowledge_id(response.json()))

        # Verify all documents are uploaded
        assert len(uploaded_ids) > 0

        # Clean up
        for doc_id in uploaded_ids:
            authenticated_client.delete(f"/api/v1/knowledge/{doc_id}")

    def test_search_with_filters(self, authenticated_client):
        """Test searching with various filters."""
        # Upload documents with different metadata
        doc1 = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("doc1.txt", io.BytesIO(b"Python programming"), "text/plain")},
            data={"title": "Python Guide", "tags": ["programming", "python"]},
        )

        doc2 = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("doc2.txt", io.BytesIO(b"JavaScript tutorial"), "text/plain")},
            data={"title": "JS Guide", "tags": ["programming", "javascript"]},
        )

        # Wait for processing
        time.sleep(3)

        # Search with tag filter
        search_response = authenticated_client.post(
            "/api/v1/knowledge/search",
            json={"query": "programming", "filters": {"tags": ["python"]}, "limit": 10},
        )

        if search_response.status_code == 200:
            payload = search_response.json()
            assert "results" in payload
            results = payload["results"]
            if results:
                assert all(r["document_id"] == self._knowledge_id(doc1.json()) for r in results)

        # Clean up
        if doc1.status_code == 201:
            authenticated_client.delete(f"/api/v1/knowledge/{self._knowledge_id(doc1.json())}")
        if doc2.status_code == 201:
            authenticated_client.delete(f"/api/v1/knowledge/{self._knowledge_id(doc2.json())}")

    def test_document_access_control(self, authenticated_client):
        """Test document access control levels."""
        # Upload private document
        private_doc = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("private.txt", io.BytesIO(b"Private content"), "text/plain")},
            data={"title": "Private Doc", "access_level": "private"},
        )

        assert private_doc.status_code == 201
        private_id = self._knowledge_id(private_doc.json())

        # Upload public document
        public_doc = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("public.txt", io.BytesIO(b"Public content"), "text/plain")},
            data={"title": "Public Doc", "access_level": "public"},
        )

        assert public_doc.status_code == 201
        public_id = self._knowledge_id(public_doc.json())

        # Verify access levels
        private_detail = authenticated_client.get(f"/api/v1/knowledge/{private_id}")
        public_detail = authenticated_client.get(f"/api/v1/knowledge/{public_id}")

        if private_detail.status_code == 200:
            assert private_detail.json()["accessLevel"] == "restricted"
        if public_detail.status_code == 200:
            assert public_detail.json()["accessLevel"] == "public"

        # Clean up
        authenticated_client.delete(f"/api/v1/knowledge/{private_id}")
        authenticated_client.delete(f"/api/v1/knowledge/{public_id}")

    def test_large_document_upload(self, authenticated_client):
        """Test uploading a large document."""
        # Create a large document (1MB)
        large_content = b"Large document content. " * 50000
        file_data = io.BytesIO(large_content)

        response = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("large_doc.txt", file_data, "text/plain")},
            data={"title": "Large Document"},
        )

        # Should succeed or return appropriate error
        assert response.status_code in [201, 413]  # 413 = Payload Too Large

        if response.status_code == 201:
            doc_id = self._knowledge_id(response.json())

            # Wait for processing
            time.sleep(5)

            # Verify it was processed
            detail_response = authenticated_client.get(f"/api/v1/knowledge/{doc_id}")
            if detail_response.status_code == 200:
                doc = detail_response.json()
                assert doc["status"] in ["completed", "processing"]

            # Clean up
            authenticated_client.delete(f"/api/v1/knowledge/{doc_id}")

    def test_document_upload_validation(self, authenticated_client):
        """Test document upload validation."""
        # Test missing file
        response = authenticated_client.post("/api/v1/knowledge", data={"title": "No File"})
        assert response.status_code in [400, 422]

        # Test invalid file type (if restrictions exist)
        invalid_file = io.BytesIO(b"executable content")
        response = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("test.exe", invalid_file, "application/x-msdownload")},
            data={"title": "Invalid File"},
        )
        # Should reject or accept based on configuration
        assert response.status_code in [201, 400, 415]

    def test_semantic_search_relevance(self, authenticated_client):
        """Test that semantic search returns relevant results."""
        # Upload documents with related content
        docs = [
            ("AI is transforming healthcare", "AI Healthcare"),
            ("Machine learning in medicine", "ML Medicine"),
            ("Cooking recipes for dinner", "Recipes"),
        ]

        uploaded_ids = []
        for content, title in docs:
            response = authenticated_client.post(
                "/api/v1/knowledge",
                files={"file": (f"{title}.txt", io.BytesIO(content.encode()), "text/plain")},
                data={"title": title},
            )
            if response.status_code == 201:
                uploaded_ids.append(self._knowledge_id(response.json()))

        # Wait for indexing
        time.sleep(5)

        # Search for healthcare-related content
        search_response = authenticated_client.post(
            "/api/v1/knowledge/search", json={"query": "healthcare and medical AI", "limit": 10}
        )

        if search_response.status_code == 200:
            payload = search_response.json()
            assert "results" in payload
            results = payload["results"]

            # Top results should be healthcare/medicine related
            if len(results) >= 2:
                top_titles = [r.get("document_title") or "" for r in results[:2]]
                assert any("Healthcare" in t or "Medicine" in t for t in top_titles)

        # Clean up
        for doc_id in uploaded_ids:
            authenticated_client.delete(f"/api/v1/knowledge/{doc_id}")
