"""Integration tests for Agent → Knowledge Base.

Tests the integration between Agent Framework and Knowledge Base components.

References:
- Task 8.2.4: Test Agent → Knowledge Base integration
"""

import io
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_knowledge_search():
    """Mock knowledge search."""
    with patch("knowledge_base.knowledge_search.KnowledgeSearch") as mock:
        search = Mock()
        search.search = AsyncMock(
            return_value=[
                {
                    "knowledge_id": str(uuid4()),
                    "title": "Company Policy Document",
                    "content_snippet": "Relevant policy information...",
                    "relevance_score": 0.92,
                }
            ]
        )
        mock.return_value = search
        yield search


@pytest.fixture
def mock_document_upload():
    """Mock document upload."""
    with patch("knowledge_base.document_upload.DocumentUpload") as mock:
        upload = Mock()
        upload.upload_document = AsyncMock(
            return_value={"knowledge_id": str(uuid4()), "status": "processing"}
        )
        mock.return_value = upload
        yield upload


class TestAgentKnowledgeIntegration:
    """Test Agent → Knowledge Base integration."""

    @pytest.mark.asyncio
    async def test_agent_searches_knowledge_base(self, mock_knowledge_search):
        """Test that agent can search the knowledge base."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Research Agent",
            agent_type="researcher",
            owner_user_id=uuid4(),
            capabilities=["knowledge_retrieval"],
        )

        agent = BaseAgent(config=config)

        # Agent searches for relevant documents
        results = await agent.search_knowledge(query="company data retention policy", limit=5)

        assert len(results) > 0
        assert results[0]["relevance_score"] > 0.8

        # Verify knowledge search was called
        mock_knowledge_search.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_retrieves_document_content(self, mock_knowledge_search):
        """Test that agent can retrieve full document content."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Research Agent",
            agent_type="researcher",
            owner_user_id=uuid4(),
            capabilities=["document_analysis"],
        )

        agent = BaseAgent(config=config)
        knowledge_id = uuid4()

        # Mock document retrieval
        with patch("knowledge_base.knowledge_search.KnowledgeSearch.get_document") as mock_get:
            mock_get.return_value = {
                "knowledge_id": str(knowledge_id),
                "title": "Full Document",
                "content": "Complete document content...",
                "metadata": {"pages": 10},
            }

            # Agent retrieves full document
            document = await agent.get_document(knowledge_id)

            assert document is not None
            assert "content" in document
            assert len(document["content"]) > 0

    @pytest.mark.asyncio
    async def test_agent_uploads_generated_document(self, mock_document_upload):
        """Test that agent can upload generated documents to knowledge base."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Report Generator",
            agent_type="generator",
            owner_user_id=uuid4(),
            capabilities=["report_generation"],
        )

        agent = BaseAgent(config=config)

        # Agent generates and uploads a report
        report_content = "# Quarterly Report\n\nAnalysis results..."
        file_data = io.BytesIO(report_content.encode())

        result = await agent.upload_document(
            filename="Q4_Report.md",
            file_data=file_data,
            title="Q4 2024 Report",
            content_type="report",
        )

        assert result["status"] == "processing"
        assert "knowledge_id" in result

        # Verify upload was called
        mock_document_upload.upload_document.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_filters_knowledge_by_access_level(self, mock_knowledge_search):
        """Test that agent only accesses knowledge it has permission for."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        user_id = uuid4()
        config = AgentConfig(
            agent_id=uuid4(),
            name="Limited Agent",
            agent_type="assistant",
            owner_user_id=user_id,
            capabilities=["knowledge_retrieval"],
        )

        agent = BaseAgent(config=config)

        # Mock filtered search results
        mock_knowledge_search.search = AsyncMock(
            return_value=[
                {
                    "knowledge_id": str(uuid4()),
                    "title": "Public Document",
                    "access_level": "public",
                    "relevance_score": 0.90,
                }
            ]
        )

        # Agent searches with access control
        results = await agent.search_knowledge(query="company information", limit=5)

        # Verify only accessible documents are returned
        assert all(doc["access_level"] in ["public", "team"] for doc in results)

        # Verify search included user context
        call_args = mock_knowledge_search.search.call_args
        assert "user_id" in call_args[1] or "owner_user_id" in call_args[1]

    @pytest.mark.asyncio
    async def test_agent_waits_for_document_processing(self, mock_document_upload):
        """Test that agent can wait for document processing to complete."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Document Processor",
            agent_type="processor",
            owner_user_id=uuid4(),
            capabilities=["document_processing"],
        )

        agent = BaseAgent(config=config)
        knowledge_id = uuid4()

        # Mock processing status checks
        with patch(
            "knowledge_base.knowledge_search.KnowledgeSearch.get_processing_status"
        ) as mock_status:
            # First call: processing, second call: completed
            mock_status.side_effect = [
                {"status": "processing", "progress": 50},
                {"status": "completed", "progress": 100},
            ]

            # Agent waits for processing
            status = await agent.wait_for_processing(knowledge_id=knowledge_id, timeout=30)

            assert status["status"] == "completed"
            assert mock_status.call_count == 2
