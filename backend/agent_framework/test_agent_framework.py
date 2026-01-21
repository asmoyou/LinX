"""Tests for Agent Framework.

References:
- Requirements 2, 12: Agent Framework and Lifecycle Management
- Design Section 4: Agent Framework Design
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

from agent_framework.base_agent import BaseAgent, AgentConfig, AgentStatus
from agent_framework.agent_registry import AgentRegistry, AgentInfo
from agent_framework.agent_lifecycle import AgentLifecycleManager, LifecyclePhase
from agent_framework.agent_status import AgentStatusTracker, StatusUpdate
from agent_framework.capability_matcher import CapabilityMatcher, CapabilityMatch
from agent_framework.agent_memory_interface import AgentMemoryInterface
from agent_framework.agent_tools import AgentToolkit, create_langchain_tools
from agent_framework.agent_executor import AgentExecutor, ExecutionContext


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
    
    @patch('agent_framework.agent_registry.get_db_session')
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
        with patch('agent_framework.agent_registry.Agent', return_value=mock_agent):
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
    
    @patch('agent_framework.agent_lifecycle.get_agent_registry')
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


class TestAgentExecutor:
    """Test agent executor."""
    
    @patch('agent_framework.agent_executor.get_agent_memory_interface')
    def test_execute_agent(self, mock_memory):
        """Test agent execution."""
        # Mock memory interface
        mock_memory.return_value.retrieve_agent_memory.return_value = []
        mock_memory.return_value.retrieve_company_memory.return_value = []
        mock_memory.return_value.store_agent_memory.return_value = "memory_id"
        
        # Create mock agent
        mock_agent = Mock()
        mock_agent.config.name = "Test Agent"
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
        assert mock_agent.execute_task.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
