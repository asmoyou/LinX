"""Integration tests for Agent → Memory System.

Tests the integration between Agent Framework and Memory System components.

References:
- Task 8.2.3: Test Agent → Memory System integration
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import numpy as np
import pytest


@pytest.fixture
def mock_memory_interface():
    """Mock memory interface."""
    with patch("memory_system.memory_interface.get_memory_interface") as mock:
        interface = Mock()
        interface.store_agent_memory = AsyncMock(return_value=str(uuid4()))
        interface.retrieve_agent_memory = AsyncMock(
            return_value=[{"content": "Previous interaction", "relevance": 0.95}]
        )
        interface.store_company_memory = AsyncMock(return_value=str(uuid4()))
        interface.retrieve_company_memory = AsyncMock(
            return_value=[{"content": "Company knowledge", "relevance": 0.90}]
        )
        mock.return_value = interface
        yield interface


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    with patch("memory_system.embedding_service.EmbeddingService") as mock:
        service = Mock()
        service.generate_embedding = AsyncMock(return_value=np.random.rand(384).tolist())
        mock.return_value = service
        yield service


class TestAgentMemoryIntegration:
    """Test Agent → Memory System integration."""

    @pytest.mark.asyncio
    async def test_agent_stores_interaction_in_memory(self, mock_memory_interface):
        """Test that agent stores interactions in its private memory."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["conversation"],
        )

        agent = BaseAgent(config=config)

        # Agent processes a task and stores memory
        await agent.store_memory(content="User asked about sales data", memory_type="interaction")

        # Verify memory was stored
        mock_memory_interface.store_agent_memory.assert_called_once()
        call_args = mock_memory_interface.store_agent_memory.call_args
        assert call_args[1]["agent_id"] == config.agent_id
        assert "sales data" in call_args[1]["content"]

    @pytest.mark.asyncio
    async def test_agent_retrieves_relevant_memories(self, mock_memory_interface):
        """Test that agent retrieves relevant memories for context."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["conversation"],
        )

        agent = BaseAgent(config=config)

        # Agent retrieves memories for current task
        memories = await agent.retrieve_memories(query="What did we discuss about sales?", limit=5)

        assert len(memories) > 0
        assert memories[0]["relevance"] > 0.8

        # Verify memory interface was called
        mock_memory_interface.retrieve_agent_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_accesses_company_memory(self, mock_memory_interface):
        """Test that agent can access shared company memory."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["knowledge_retrieval"],
        )

        agent = BaseAgent(config=config)

        # Agent retrieves company knowledge
        knowledge = await agent.retrieve_company_knowledge(
            query="Company policies on data retention", limit=3
        )

        assert len(knowledge) > 0

        # Verify company memory was accessed
        mock_memory_interface.retrieve_company_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_agent_memory_includes_embeddings(
        self, mock_memory_interface, mock_embedding_service
    ):
        """Test that stored memories include vector embeddings."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["conversation"],
        )

        agent = BaseAgent(config=config)

        # Store memory with embedding
        await agent.store_memory(content="Important business decision made", memory_type="decision")

        # Verify embedding was generated
        mock_embedding_service.generate_embedding.assert_called()

        # Verify memory was stored with embedding
        call_args = mock_memory_interface.store_agent_memory.call_args
        assert "embedding" in call_args[1] or "vector" in call_args[1]

    @pytest.mark.asyncio
    async def test_memory_isolation_between_agents(self, mock_memory_interface):
        """Test that agent memories are isolated from each other."""
        from agent_framework.base_agent import AgentConfig, BaseAgent

        agent1_id = uuid4()
        agent2_id = uuid4()

        config1 = AgentConfig(
            agent_id=agent1_id,
            name="Agent 1",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["conversation"],
        )

        config2 = AgentConfig(
            agent_id=agent2_id,
            name="Agent 2",
            agent_type="assistant",
            owner_user_id=uuid4(),
            capabilities=["conversation"],
        )

        agent1 = BaseAgent(config=config1)
        agent2 = BaseAgent(config=config2)

        # Agent 1 stores private memory
        await agent1.store_memory(content="Agent 1 private data", memory_type="private")

        # Agent 2 retrieves memories (should not see Agent 1's private data)
        mock_memory_interface.retrieve_agent_memory = AsyncMock(return_value=[])

        memories = await agent2.retrieve_memories(query="private data", limit=5)

        # Verify Agent 2 doesn't see Agent 1's memories
        assert len(memories) == 0

        # Verify correct agent_id was used in query
        call_args = mock_memory_interface.retrieve_agent_memory.call_args
        assert call_args[1]["agent_id"] == agent2_id
