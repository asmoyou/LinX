"""Integration tests for Task Manager → Agent Framework.

Tests the integration between Task Manager and Agent Framework components.

References:
- Task 8.2.2: Test Task Manager → Agent Framework integration
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, patch, AsyncMock


@pytest.fixture
def mock_agent_registry():
    """Mock agent registry."""
    with patch('agent_framework.agent_registry.get_agent_registry') as mock:
        registry = Mock()
        registry.find_agents_by_capabilities = Mock(return_value=[
            Mock(agent_id=uuid4(), name="Test Agent", capabilities=["data_analysis"])
        ])
        mock.return_value = registry
        yield registry


@pytest.fixture
def mock_agent_executor():
    """Mock agent executor."""
    with patch('agent_framework.agent_executor.get_agent_executor') as mock:
        executor = Mock()
        executor.execute = AsyncMock(return_value={
            'success': True,
            'output': 'Task completed successfully'
        })
        mock.return_value = executor
        yield executor


class TestTaskAgentIntegration:
    """Test Task Manager → Agent Framework integration."""
    
    @pytest.mark.asyncio
    async def test_task_assignment_finds_capable_agent(self, mock_agent_registry):
        """Test that task assignment finds agents with required capabilities."""
        from task_manager.agent_assigner import AgentAssigner
        
        assigner = AgentAssigner()
        
        # Assign task requiring data_analysis capability
        agent = await assigner.assign_agent(
            task_id=uuid4(),
            required_capabilities=["data_analysis"]
        )
        
        assert agent is not None
        assert "data_analysis" in agent.capabilities
        
        # Verify registry was queried
        mock_agent_registry.find_agents_by_capabilities.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_task_execution_invokes_agent(self, mock_agent_executor):
        """Test that task execution invokes the assigned agent."""
        from task_manager.task_executor import TaskExecutor
        
        executor = TaskExecutor()
        task_id = uuid4()
        agent_id = uuid4()
        
        # Execute task with assigned agent
        result = await executor.execute_task(
            task_id=task_id,
            agent_id=agent_id,
            task_description="Analyze sales data"
        )
        
        assert result['success'] is True
        assert 'output' in result
        
        # Verify agent executor was called
        mock_agent_executor.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_task_decomposition_creates_subtasks_for_agents(self):
        """Test that task decomposition creates subtasks that can be assigned to agents."""
        from task_manager.task_decomposer import TaskDecomposer
        
        decomposer = TaskDecomposer()
        
        # Decompose complex goal
        subtasks = await decomposer.decompose(
            goal="Create quarterly report with charts and analysis",
            available_skills=["data_analysis", "chart_generation", "report_writing"]
        )
        
        assert len(subtasks) > 1
        assert all('required_capabilities' in task for task in subtasks)
        assert all('description' in task for task in subtasks)
    
    @pytest.mark.asyncio
    async def test_agent_failure_triggers_task_retry(self, mock_agent_executor):
        """Test that agent execution failure triggers task retry logic."""
        from task_manager.error_handler import ErrorHandler
        
        # Simulate agent failure
        mock_agent_executor.execute = AsyncMock(side_effect=Exception("Agent failed"))
        
        error_handler = ErrorHandler()
        task_id = uuid4()
        
        # Handle error should trigger retry
        retry_decision = await error_handler.handle_task_error(
            task_id=task_id,
            error=Exception("Agent failed"),
            attempt=1
        )
        
        assert retry_decision['should_retry'] is True
        assert retry_decision['retry_delay'] > 0
    
    @pytest.mark.asyncio
    async def test_task_result_stored_after_agent_completion(self, mock_agent_executor):
        """Test that task results are stored after agent completes execution."""
        from task_manager.task_executor import TaskExecutor
        from database.models import Task
        
        with patch('database.connection.get_db_session') as mock_session:
            session = Mock()
            mock_session.return_value.__enter__.return_value = session
            
            task_mock = Mock(spec=Task)
            task_mock.task_id = uuid4()
            task_mock.result = None
            session.query.return_value.filter.return_value.first.return_value = task_mock
            
            executor = TaskExecutor()
            
            # Execute task
            await executor.execute_task(
                task_id=task_mock.task_id,
                agent_id=uuid4(),
                task_description="Test task"
            )
            
            # Verify result was stored
            assert task_mock.result is not None
            session.commit.assert_called()
