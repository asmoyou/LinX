"""Tests for Agent Framework.

References:
- Requirements 2, 12: Agent Framework and Lifecycle Management
- Design Section 4: Agent Framework Design
"""

from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest

from agent_framework.agent_executor import AgentExecutor, ExecutionContext
from agent_framework.agent_lifecycle import AgentLifecycleManager, LifecyclePhase
from agent_framework.agent_memory_interface import AgentMemoryInterface
from agent_framework.agent_registry import AgentInfo, AgentRegistry
from agent_framework.agent_status import AgentStatusTracker, StatusUpdate
from agent_framework.agent_tools import AgentToolkit, create_langchain_tools
from agent_framework.base_agent import AgentConfig, AgentStatus, BaseAgent
from agent_framework.capability_matcher import CapabilityMatch, CapabilityMatcher
from memory_system.memory_interface import MemoryItem, MemoryType


class TestBaseAgent:
    """Test BaseAgent class."""

    def test_agent_initialization(self):
        """Test agent initialization."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2"],
        )

        agent = BaseAgent(config=config)

        assert agent.config.name == "Test Agent"
        assert agent.status == AgentStatus.INITIALIZING
        assert len(agent.config.capabilities) == 2

    def test_agent_get_capabilities(self):
        """Test getting agent capabilities."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2", "skill3"],
        )

        agent = BaseAgent(config=config)
        capabilities = agent.get_capabilities()

        assert len(capabilities) == 3
        assert "skill1" in capabilities


class TestAgentRegistry:
    """Test agent registry."""

    @patch("agent_framework.agent_registry.get_db_session")
    def test_register_agent(self, mock_session):
        """Test agent registration."""
        # Mock database session
        mock_db = MagicMock()
        mock_session.return_value.__enter__.return_value = mock_db

        mock_agent = Mock()
        mock_agent.agent_id = uuid4()
        mock_agent.name = "Test Agent"
        mock_agent.agent_type = "test"
        mock_agent.owner_user_id = uuid4()
        mock_agent.capabilities = ["skill1"]
        mock_agent.status = "initializing"
        mock_agent.container_id = None
        mock_agent.created_at = Mock()
        mock_agent.updated_at = Mock()

        mock_db.add = Mock()
        mock_db.commit = Mock()
        mock_db.refresh = Mock()

        # Mock the agent creation
        with patch("agent_framework.agent_registry.Agent", return_value=mock_agent):
            registry = AgentRegistry()
            agent_info = registry.register_agent(
                name="Test Agent",
                agent_type="test",
                owner_user_id=uuid4(),
                capabilities=["skill1"],
            )

        assert agent_info.name == "Test Agent"
        assert mock_db.add.called
        assert mock_db.commit.called


class TestAgentLifecycle:
    """Test agent lifecycle management."""

    @patch("agent_framework.agent_lifecycle.get_agent_registry")
    def test_create_agent(self, mock_registry):
        """Test agent creation."""
        # Mock registry
        mock_agent_info = Mock()
        mock_agent_info.agent_id = uuid4()
        mock_agent_info.name = "Test Agent"
        mock_agent_info.agent_type = "test"
        mock_agent_info.owner_user_id = uuid4()
        mock_agent_info.capabilities = ["skill1"]

        mock_registry.return_value.register_agent.return_value = mock_agent_info

        lifecycle = AgentLifecycleManager(mock_registry.return_value)
        agent = lifecycle.create_agent(
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1"],
        )

        assert isinstance(agent, BaseAgent)
        assert agent.config.name == "Test Agent"


class TestCapabilityMatcher:
    """Test capability matching."""

    def test_calculate_match_score(self):
        """Test match score calculation."""
        matcher = CapabilityMatcher()

        agent_info = AgentInfo(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2", "skill3"],
            status="active",
            container_id=None,
            created_at=Mock(),
            updated_at=Mock(),
        )

        required_capabilities = ["skill1", "skill2"]

        match = matcher._calculate_match(agent_info, required_capabilities)

        assert match.match_score == 1.0
        assert len(match.matched_capabilities) == 2
        assert len(match.missing_capabilities) == 0

    def test_partial_match(self):
        """Test partial capability match."""
        matcher = CapabilityMatcher()

        agent_info = AgentInfo(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=["skill1", "skill2"],
            status="active",
            container_id=None,
            created_at=Mock(),
            updated_at=Mock(),
        )

        required_capabilities = ["skill1", "skill2", "skill3", "skill4"]

        match = matcher._calculate_match(agent_info, required_capabilities)

        assert match.match_score == 0.5  # 2 out of 4
        assert len(match.matched_capabilities) == 2
        assert len(match.missing_capabilities) == 2


class TestAgentTools:
    """Test agent tools."""

    def test_create_default_tools(self):
        """Test creating default tools."""
        tools = create_langchain_tools()

        assert len(tools) > 0
        assert any(tool.name == "calculator" for tool in tools)

    def test_toolkit_add_tool(self):
        """Test adding tool to toolkit."""
        toolkit = AgentToolkit()

        mock_tool = Mock()
        mock_tool.name = "TestTool"

        toolkit.add_tool(mock_tool)

        assert len(toolkit.get_tools()) == 1
        assert toolkit.get_tool_by_name("TestTool") is not None


class TestAgentMemoryInterface:
    """Test AgentMemoryInterface retrieval alignment behavior."""

    @patch("agent_framework.agent_memory_interface.get_memory_repository")
    def test_retrieve_company_memory_drops_unmapped_legacy_vectors(self, mock_get_repository):
        """User-scoped retrieval should ignore unmapped legacy Milvus rows."""
        user_id = uuid4()
        query_text = "Shared Data Fujian Technology Co., Ltd."

        mock_memory_system = Mock()
        mock_memory_system.retrieve_memories.return_value = [
            MemoryItem(
                id=101,
                content="LinX platform details (legacy vector)",
                memory_type=MemoryType.COMPANY,
                user_id=str(user_id),
                similarity_score=0.62,
            )
        ]

        mock_repo = Mock()
        mock_repo.get_by_milvus_ids.return_value = {}
        mock_repo.search_text.return_value = []
        mock_get_repository.return_value = mock_repo

        interface = AgentMemoryInterface(memory_system=mock_memory_system)
        results = interface.retrieve_company_memory(
            user_id=user_id,
            query=query_text,
            top_k=5,
        )

        assert results == []
        mock_repo.search_text.assert_called_once_with(
            query_text,
            memory_type=MemoryType.COMPANY,
            agent_id=None,
            user_id=str(user_id),
            task_id=None,
            limit=5,
        )

    @patch("agent_framework.agent_memory_interface.get_memory_repository")
    def test_retrieve_company_memory_prefers_db_mapped_record(self, mock_get_repository):
        """Mapped DB record should replace semantic row and keep rerank debug fields."""
        user_id = uuid4()

        semantic_item = MemoryItem(
            id=202,
            content="vector content",
            memory_type=MemoryType.COMPANY,
            user_id=str(user_id),
            similarity_score=0.83,
            metadata={"_rerank_score": 0.91, "plain": "ignored"},
        )
        mapped_item = MemoryItem(
            id=2,
            content="Shared Data Fujian supplier profile",
            memory_type=MemoryType.COMPANY,
            user_id=str(user_id),
            metadata={"source": "db"},
        )
        mapped_row = Mock()
        mapped_row.user_id = str(user_id)
        mapped_row.to_memory_item.return_value = mapped_item

        mock_memory_system = Mock()
        mock_memory_system.retrieve_memories.return_value = [semantic_item]

        mock_repo = Mock()
        mock_repo.get_by_milvus_ids.return_value = {202: mapped_row}
        mock_get_repository.return_value = mock_repo

        interface = AgentMemoryInterface(memory_system=mock_memory_system)
        results = interface.retrieve_company_memory(
            user_id=user_id,
            query="Shared Data Fujian Technology Co., Ltd.",
            top_k=5,
        )

        assert len(results) == 1
        assert results[0].content == "Shared Data Fujian supplier profile"
        assert results[0].metadata["source"] == "db"
        assert results[0].metadata["_rerank_score"] == 0.91
        assert "plain" not in results[0].metadata
        mock_repo.search_text.assert_not_called()


class TestAgentExecutor:
    """Test agent executor."""

    @patch("agent_framework.agent_executor.get_agent_memory_interface")
    def test_execute_agent(self, mock_memory):
        """Test agent execution."""
        # Mock memory interface
        mock_memory.return_value.retrieve_agent_memory.return_value = [Mock(content="agent note")]
        mock_memory.return_value.retrieve_company_memory.return_value = [
            Mock(content="company note")
        ]
        mock_memory.return_value.memory_system.retrieve_memories.return_value = [
            Mock(content="user preference")
        ]
        mock_memory.return_value.store_agent_memory.return_value = "memory_id"

        # Create mock agent
        mock_agent = Mock()
        mock_agent.config.name = "Test Agent"
        mock_agent.config.access_level = "team"
        mock_agent.config.allowed_memory = ["agent", "company", "user_context"]
        mock_agent.config.allowed_knowledge = []
        mock_agent.execute_task.return_value = {
            "success": True,
            "output": "Task completed",
        }

        executor = AgentExecutor(mock_memory.return_value)
        context = ExecutionContext(
            agent_id=uuid4(),
            user_id=uuid4(),
            task_description="Test task",
        )

        result = executor.execute(mock_agent, context)

        assert result["success"]
        mock_agent.execute_task.assert_called_once()
        execute_context = mock_agent.execute_task.call_args.kwargs["context"]
        assert execute_context["agent_memories"] == ["agent note"]
        assert execute_context["company_memories"] == ["company note"]
        assert execute_context["user_context_memories"] == ["user preference"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
