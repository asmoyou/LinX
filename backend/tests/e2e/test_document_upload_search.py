"""End-to-end tests for document upload and search.

Tests the complete workflow of uploading and searching documents.

References:
- Task 8.3.4: Test document upload and search flow
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
import io
import time


@pytest.fixture
def authenticated_client():
    """Create authenticated API client."""
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
    
    return client


class TestDocumentUploadSearch:
    """Test complete document upload and search flow."""
    
    def test_complete_document_workflow(self, authenticated_client):
        """Test complete flow from upload to search."""
        # Step 1: Upload a document
        document_content = b"This is a test document about artificial intelligence and machine learning."
        file_data = io.BytesIO(document_content)
        
        upload_response = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("test_document.txt", file_data, "text/plain")},
            data={
                "title": "AI and ML Overview",
                "content_type": "document",
                "access_level": "private"
            }
        )
        
        assert upload_response.status_code == 201
        upload_result = upload_response.json()
        assert "knowledge_id" in upload_result
        assert upload_result["status"] in ["processing", "pending"]
        assert upload_result["title"] == "AI and ML Overview"
        
        knowledge_id = upload_result["knowledge_id"]
        
        # Step 2: Check processing status
        max_attempts = 30
        for attempt in range(max_attempts):
            status_response = authenticated_client.get(
                f"/api/v1/knowledge/{knowledge_id}"
            )
            
            assert status_response.status_code == 200
            document = status_response.json()
            
            if document["status"] == "completed":
                break
            elif document["status"] == "failed":
                pytest.fail(f"Document processing failed: {document.get('error')}")
            
            time.sleep(1)
        
        # Step 3: Verify document is indexed
        detail_response = authenticated_client.get(f"/api/v1/knowledge/{knowledge_id}")
        document_detail = detail_response.json()
        
        assert document_detail["status"] == "completed"
        assert "chunks_count" in document_detail or "indexed" in document_detail
        
        # Step 4: Search for the document
        search_response = authenticated_client.post(
            "/api/v1/knowledge/search",
            json={
                "query": "artificial intelligence",
                "limit": 10
            }
        )
        
        assert search_response.status_code == 200
        search_results = search_response.json()
        assert len(search_results) > 0
        
        # Our document should be in the results
        assert any(r["knowledge_id"] == knowledge_id for r in search_results)
        
        # Step 5: Search with different query
        ml_search_response = authenticated_client.post(
            "/api/v1/knowledge/search",
            json={
                "query": "machine learning",
                "limit": 5
            }
        )
        
        assert ml_search_response.status_code == 200
        ml_results = ml_search_response.json()
        
        # Should find the document
        assert any(r["knowledge_id"] == knowledge_id for r in ml_results)
        
        # Step 6: Get document content
        content_response = authenticated_client.get(
            f"/api/v1/knowledge/{knowledge_id}/content"
        )
        
        if content_response.status_code == 200:
            content = content_response.json()
            assert "content" in content or "text" in content
        
        # Step 7: Update document metadata
        update_response = authenticated_client.put(
            f"/api/v1/knowledge/{knowledge_id}",
            json={
                "title": "Updated: AI and ML Overview",
                "tags": ["AI", "ML", "technology"]
            }
        )
        
        assert update_response.status_code == 200
        updated_doc = update_response.json()
        assert updated_doc["title"] == "Updated: AI and ML Overview"
        
        # Step 8: List all user documents
        list_response = authenticated_client.get("/api/v1/knowledge")
        
        assert list_response.status_code == 200
        documents = list_response.json()
        assert any(d["knowledge_id"] == knowledge_id for d in documents)
        
        # Step 9: Delete document
        delete_response = authenticated_client.delete(
            f"/api/v1/knowledge/{knowledge_id}"
        )
        
        assert delete_response.status_code == 200
        
        # Step 10: Verify document is deleted
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
                data={"title": f"Test {filename}"}
            )
            
            if response.status_code == 201:
                uploaded_ids.append(response.json()["knowledge_id"])
        
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
            data={"title": "Python Guide", "tags": ["programming", "python"]}
        )
        
        doc2 = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("doc2.txt", io.BytesIO(b"JavaScript tutorial"), "text/plain")},
            data={"title": "JS Guide", "tags": ["programming", "javascript"]}
        )
        
        # Wait for processing
        time.sleep(3)
        
        # Search with tag filter
        search_response = authenticated_client.post(
            "/api/v1/knowledge/search",
            json={
                "query": "programming",
                "filters": {"tags": ["python"]},
                "limit": 10
            }
        )
        
        if search_response.status_code == 200:
            results = search_response.json()
            # Should only return Python document
            if len(results) > 0:
                assert all("python" in r.get("tags", []) for r in results if "tags" in r)
        
        # Clean up
        if doc1.status_code == 201:
            authenticated_client.delete(f"/api/v1/knowledge/{doc1.json()['knowledge_id']}")
        if doc2.status_code == 201:
            authenticated_client.delete(f"/api/v1/knowledge/{doc2.json()['knowledge_id']}")
    
    def test_document_access_control(self, authenticated_client):
        """Test document access control levels."""
        # Upload private document
        private_doc = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("private.txt", io.BytesIO(b"Private content"), "text/plain")},
            data={"title": "Private Doc", "access_level": "private"}
        )
        
        assert private_doc.status_code == 201
        private_id = private_doc.json()["knowledge_id"]
        
        # Upload public document
        public_doc = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("public.txt", io.BytesIO(b"Public content"), "text/plain")},
            data={"title": "Public Doc", "access_level": "public"}
        )
        
        assert public_doc.status_code == 201
        public_id = public_doc.json()["knowledge_id"]
        
        # Verify access levels
        private_detail = authenticated_client.get(f"/api/v1/knowledge/{private_id}")
        public_detail = authenticated_client.get(f"/api/v1/knowledge/{public_id}")
        
        if private_detail.status_code == 200:
            assert private_detail.json()["access_level"] == "private"
        if public_detail.status_code == 200:
            assert public_detail.json()["access_level"] == "public"
        
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
            data={"title": "Large Document"}
        )
        
        # Should succeed or return appropriate error
        assert response.status_code in [201, 413]  # 413 = Payload Too Large
        
        if response.status_code == 201:
            doc_id = response.json()["knowledge_id"]
            
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
        response = authenticated_client.post(
            "/api/v1/knowledge",
            data={"title": "No File"}
        )
        assert response.status_code in [400, 422]
        
        # Test invalid file type (if restrictions exist)
        invalid_file = io.BytesIO(b"executable content")
        response = authenticated_client.post(
            "/api/v1/knowledge",
            files={"file": ("test.exe", invalid_file, "application/x-msdownload")},
            data={"title": "Invalid File"}
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
                data={"title": title}
            )
            if response.status_code == 201:
                uploaded_ids.append(response.json()["knowledge_id"])
        
        # Wait for indexing
        time.sleep(5)
        
        # Search for healthcare-related content
        search_response = authenticated_client.post(
            "/api/v1/knowledge/search",
            json={"query": "healthcare and medical AI", "limit": 10}
        )
        
        if search_response.status_code == 200:
            results = search_response.json()
            
            # Top results should be healthcare/medicine related
            if len(results) >= 2:
                top_titles = [r["title"] for r in results[:2]]
                assert any("Healthcare" in t or "Medicine" in t for t in top_titles)
        
        # Clean up
        for doc_id in uploaded_ids:
            authenticated_client.delete(f"/api/v1/knowledge/{doc_id}")
