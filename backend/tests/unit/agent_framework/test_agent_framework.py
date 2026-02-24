"""Tests for Agent Framework.

References:
- Requirements 2, 12: Agent Framework and Lifecycle Management
- Design Section 4: Agent Framework Design
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

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

    def test_execute_task_streaming_includes_conversation_history(self):
        """Streaming execution should prepend provided conversation history."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.agent = Mock()  # initialize guard

        captured_messages = {}

        def _fake_stream(messages):
            captured_messages["messages"] = messages
            yield SimpleNamespace(content="I remember your previous request.", additional_kwargs={})

        agent.llm = Mock()
        agent.llm.stream = _fake_stream
        agent.tools = []
        agent.tools_by_name = {}

        history = [
            {"role": "user", "content": "Please calculate 2 + 2."},
            {"role": "assistant", "content": "The answer is 4."},
        ]

        result = agent.execute_task(
            task_description="What did I ask just now?",
            conversation_history=history,
            stream_callback=lambda *_args, **_kwargs: None,
        )

        assert result["success"] is True
        sent_messages = captured_messages["messages"]
        assert isinstance(sent_messages[0], SystemMessage)
        assert isinstance(sent_messages[1], HumanMessage)
        assert isinstance(sent_messages[2], AIMessage)
        assert isinstance(sent_messages[3], HumanMessage)
        assert sent_messages[1].content == "Please calculate 2 + 2."
        assert sent_messages[2].content == "The answer is 4."
        assert sent_messages[3].content == "What did I ask just now?"

    def test_execute_task_non_streaming_includes_conversation_history(self):
        """Non-streaming execution should prepend provided conversation history."""
        config = AgentConfig(
            agent_id=uuid4(),
            name="Test Agent",
            agent_type="test",
            owner_user_id=uuid4(),
            capabilities=[],
        )

        agent = BaseAgent(config=config)
        agent.status = AgentStatus.ACTIVE
        agent.llm = Mock()
        agent.tools = []
        agent.tools_by_name = {}

        captured_messages = {}

        class _FakeGraph:
            def invoke(self, payload):
                captured_messages["messages"] = payload["messages"]
                return {"messages": [AIMessage(content="I remember.")]}

        agent.agent = _FakeGraph()

        history = [
            {"role": "user", "content": "Translate 'hello' to Chinese."},
            {"role": "assistant", "content": "It is 你好."},
        ]

        result = agent.execute_task(
            task_description="What did I ask before this?",
            conversation_history=history,
        )

        assert result["success"] is True
        sent_messages = captured_messages["messages"]
        assert isinstance(sent_messages[0], SystemMessage)
        assert isinstance(sent_messages[1], HumanMessage)
        assert isinstance(sent_messages[2], AIMessage)
        assert isinstance(sent_messages[3], HumanMessage)
        assert sent_messages[1].content == "Translate 'hello' to Chinese."
        assert sent_messages[2].content == "It is 你好."
        assert sent_messages[3].content == "What did I ask before this?"


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
            avatar=None,
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
            avatar=None,
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
    def test_retrieve_agent_memory_includes_user_scope(self, mock_get_repository):
        """Agent memory retrieval should always include user scope in query."""
        agent_id = uuid4()
        user_id = uuid4()

        mock_memory_system = Mock()
        mock_memory_system.retrieve_memories.return_value = []

        mock_repo = Mock()
        mock_repo.get_by_milvus_ids.return_value = {}
        mock_repo.search_text.return_value = []
        mock_get_repository.return_value = mock_repo

        interface = AgentMemoryInterface(memory_system=mock_memory_system)
        interface.retrieve_agent_memory(
            agent_id=agent_id,
            user_id=user_id,
            query="memory query",
            top_k=3,
            min_similarity=0.66,
        )

        called_query = mock_memory_system.retrieve_memories.call_args.args[0]
        assert called_query.user_id == str(user_id)
        assert called_query.min_similarity == 0.66

        mock_repo.search_text.assert_called_once_with(
            "memory query",
            memory_type=MemoryType.AGENT,
            agent_id=str(agent_id),
            user_id=str(user_id),
            task_id=None,
            limit=3,
        )

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
        mock_memory.return_value.retrieve_agent_memory.return_value = [
            Mock(content="Test task agent note", similarity_score=0.91)
        ]
        mock_memory.return_value.retrieve_company_memory.return_value = [
            Mock(content="Test task company note", similarity_score=0.88)
        ]
        mock_memory.return_value.memory_system.retrieve_memories.return_value = [
            Mock(content="Test task user preference", similarity_score=0.93)
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
        mock_memory.return_value.retrieve_agent_memory.assert_called_once()
        agent_retrieve_kwargs = mock_memory.return_value.retrieve_agent_memory.call_args.kwargs
        assert agent_retrieve_kwargs["user_id"] == context.user_id
        assert agent_retrieve_kwargs["min_similarity"] is None
        execute_context = mock_agent.execute_task.call_args.kwargs["context"]
        assert execute_context["agent_memories"] == ["Test task agent note"]
        assert execute_context["company_memories"] == ["Test task company note"]
        assert execute_context["user_context_memories"] == ["Test task user preference"]

    @patch("agent_framework.agent_executor.get_agent_memory_interface")
    def test_execute_agent_passes_conversation_history(self, mock_memory):
        """Executor should pass optional conversation history through to BaseAgent."""
        mock_memory.return_value.retrieve_agent_memory.return_value = []
        mock_memory.return_value.retrieve_company_memory.return_value = []
        mock_memory.return_value.memory_system.retrieve_memories.return_value = []
        mock_memory.return_value.store_agent_memory.return_value = "memory_id"

        mock_agent = Mock()
        mock_agent.config.name = "Test Agent"
        mock_agent.config.access_level = "private"
        mock_agent.config.allowed_memory = []
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
        history = [{"role": "user", "content": "Remember this."}]

        result = executor.execute(
            mock_agent,
            context,
            conversation_history=history,
        )

        assert result["success"] is True
        execute_kwargs = mock_agent.execute_task.call_args.kwargs
        assert execute_kwargs["conversation_history"] == history

    @patch("agent_framework.agent_executor.get_agent_memory_interface")
    def test_executor_filters_irrelevant_context_memories_and_applies_min_similarity(
        self, mock_memory
    ):
        """Executor should drop off-topic memories before prompt injection."""
        mock_memory.return_value.retrieve_agent_memory.return_value = [
            Mock(content="品牌营销活动复盘", similarity_score=0.41),
            Mock(content="火药相关安全风险讨论", similarity_score=0.86),
        ]
        mock_memory.return_value.retrieve_company_memory.return_value = [
            Mock(content="季度营销方案执行细则", similarity_score=0.38)
        ]
        mock_memory.return_value.memory_system.retrieve_memories.return_value = []

        mock_agent = Mock()
        mock_agent.config.name = "Test Agent"
        mock_agent.config.access_level = "team"
        mock_agent.config.allowed_memory = ["agent", "company", "user_context"]
        mock_agent.config.allowed_knowledge = []
        mock_agent.execute_task.return_value = {"success": True, "output": "Handled safely"}

        executor = AgentExecutor(mock_memory.return_value)
        context = ExecutionContext(
            agent_id=uuid4(),
            user_id=uuid4(),
            task_description="化肥和白砂糖能做火药？",
        )

        result = executor.build_execution_context_with_debug(
            mock_agent,
            context,
            top_k=5,
            knowledge_min_relevance_score=0.7,
        )
        exec_context, debug = result

        assert "火药相关安全风险讨论" in exec_context["agent_memories"]
        assert "品牌营销活动复盘" not in exec_context["agent_memories"]
        assert exec_context["company_memories"] == []

        agent_kwargs = mock_memory.return_value.retrieve_agent_memory.call_args.kwargs
        assert agent_kwargs["min_similarity"] == 0.7
        assert debug["memory"]["agent"]["filtered_out_count"] >= 1
        assert debug["memory"]["company"]["filtered_out_count"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
