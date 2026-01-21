"""Integration tests for Goal submission → Task decomposition → Execution flow.

Tests the complete goal execution pipeline.

References:
- Task 8.2.6: Test Goal submission → Task decomposition → Execution flow
"""

from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest


@pytest.fixture
def mock_goal_analyzer():
    """Mock goal analyzer."""
    with patch("task_manager.goal_analyzer.GoalAnalyzer") as mock:
        analyzer = Mock()
        analyzer.analyze_goal = AsyncMock(
            return_value={
                "is_clear": True,
                "required_capabilities": ["data_analysis", "report_generation"],
                "complexity": "medium",
            }
        )
        mock.return_value = analyzer
        yield analyzer


@pytest.fixture
def mock_task_decomposer():
    """Mock task decomposer."""
    with patch("task_manager.task_decomposer.TaskDecomposer") as mock:
        decomposer = Mock()
        decomposer.decompose = AsyncMock(
            return_value=[
                {
                    "description": "Analyze sales data",
                    "required_capabilities": ["data_analysis"],
                    "priority": 1,
                },
                {
                    "description": "Generate report",
                    "required_capabilities": ["report_generation"],
                    "priority": 2,
                    "dependencies": [0],
                },
            ]
        )
        mock.return_value = decomposer
        yield decomposer


@pytest.fixture
def mock_agent_assigner():
    """Mock agent assigner."""
    with patch("task_manager.agent_assigner.AgentAssigner") as mock:
        assigner = Mock()
        assigner.assign_agent = AsyncMock(
            return_value=Mock(
                agent_id=uuid4(), name="Data Analyst Agent", capabilities=["data_analysis"]
            )
        )
        mock.return_value = assigner
        yield assigner


class TestGoalExecutionFlow:
    """Test Goal submission → Task decomposition → Execution flow."""

    @pytest.mark.asyncio
    async def test_complete_goal_execution_flow(
        self, mock_goal_analyzer, mock_task_decomposer, mock_agent_assigner
    ):
        """Test complete flow from goal submission to execution."""
        from task_manager.task_coordinator import TaskCoordinator

        coordinator = TaskCoordinator()
        user_id = uuid4()

        # Submit goal
        result = await coordinator.submit_goal(
            user_id=user_id, goal_text="Create quarterly sales report with analysis", priority=1
        )

        assert "task_id" in result
        assert result["status"] == "pending"

        # Verify goal was analyzed
        mock_goal_analyzer.analyze_goal.assert_called_once()

        # Verify goal was decomposed
        mock_task_decomposer.decompose.assert_called_once()

        # Verify agents were assigned
        assert mock_agent_assigner.assign_agent.call_count >= 1

    @pytest.mark.asyncio
    async def test_goal_clarification_when_ambiguous(self, mock_goal_analyzer):
        """Test that ambiguous goals trigger clarification."""
        from task_manager.task_coordinator import TaskCoordinator

        # Mock ambiguous goal analysis
        mock_goal_analyzer.analyze_goal = AsyncMock(
            return_value={
                "is_clear": False,
                "clarification_questions": [
                    "Which quarter do you want to analyze?",
                    "What specific metrics should be included?",
                ],
            }
        )

        coordinator = TaskCoordinator()
        user_id = uuid4()

        # Submit ambiguous goal
        result = await coordinator.submit_goal(
            user_id=user_id, goal_text="Create a report", priority=1
        )

        assert result["status"] == "needs_clarification"
        assert "clarification_questions" in result
        assert len(result["clarification_questions"]) > 0

    @pytest.mark.asyncio
    async def test_task_decomposition_respects_dependencies(self, mock_task_decomposer):
        """Test that task decomposition creates proper dependency chains."""
        from task_manager.task_decomposer import TaskDecomposer

        decomposer = TaskDecomposer()

        # Decompose complex goal
        subtasks = await decomposer.decompose(
            goal="Analyze data, create visualizations, and write report",
            available_skills=["data_analysis", "visualization", "writing"],
        )

        assert len(subtasks) >= 3

        # Verify dependencies are set correctly
        # Later tasks should depend on earlier ones
        for i, task in enumerate(subtasks[1:], 1):
            if "dependencies" in task:
                assert all(dep < i for dep in task["dependencies"])

    @pytest.mark.asyncio
    async def test_parallel_task_execution_when_possible(self, mock_agent_assigner):
        """Test that independent tasks can execute in parallel."""
        from task_manager.task_executor import TaskExecutor

        executor = TaskExecutor()

        # Create independent tasks
        task1_id = uuid4()
        task2_id = uuid4()

        with patch("agent_framework.agent_executor.AgentExecutor.execute") as mock_execute:
            mock_execute.return_value = {"success": True, "output": "Done"}

            # Execute tasks in parallel
            results = await executor.execute_parallel(
                [
                    {"task_id": task1_id, "agent_id": uuid4(), "description": "Task 1"},
                    {"task_id": task2_id, "agent_id": uuid4(), "description": "Task 2"},
                ]
            )

            assert len(results) == 2
            assert all(r["success"] for r in results)

            # Verify both tasks were executed
            assert mock_execute.call_count == 2

    @pytest.mark.asyncio
    async def test_task_result_aggregation(self):
        """Test that subtask results are aggregated for parent task."""
        from task_manager.result_collector import ResultCollector

        collector = ResultCollector()
        parent_task_id = uuid4()
        user_id = uuid4()

        # Mock subtask results
        with patch("database.connection.get_db_session") as mock_session:
            session = Mock()
            mock_session.return_value.__enter__.return_value = session

            # Mock subtasks with results
            subtasks = [
                Mock(
                    task_id=uuid4(),
                    result={"output": "Analysis complete", "data": [1, 2, 3]},
                    status="completed",
                ),
                Mock(
                    task_id=uuid4(),
                    result={"output": "Report generated", "file": "report.pdf"},
                    status="completed",
                ),
            ]

            session.query.return_value.filter.return_value.all.return_value = subtasks

            # Aggregate results
            aggregated = await collector.collect_and_aggregate_subtasks(
                parent_task_id=parent_task_id, user_id=user_id
            )

            assert "aggregated_output" in aggregated or "results" in aggregated
            assert aggregated["source_count"] == 2

    @pytest.mark.asyncio
    async def test_task_progress_tracking(self):
        """Test that task progress is tracked throughout execution."""
        from task_manager.progress_tracker import ProgressTracker

        tracker = ProgressTracker()
        task_id = uuid4()

        # Initialize progress
        await tracker.initialize_task(task_id, total_steps=3)

        # Update progress
        await tracker.update_progress(task_id, completed_steps=1)
        progress = await tracker.get_progress(task_id)
        assert progress["percentage"] == 33

        await tracker.update_progress(task_id, completed_steps=2)
        progress = await tracker.get_progress(task_id)
        assert progress["percentage"] == 67

        await tracker.update_progress(task_id, completed_steps=3)
        progress = await tracker.get_progress(task_id)
        assert progress["percentage"] == 100
        assert progress["status"] == "completed"

    @pytest.mark.asyncio
    async def test_task_failure_triggers_recovery(self):
        """Test that task failures trigger recovery mechanisms."""
        from task_manager.recovery_coordinator import RecoveryCoordinator

        coordinator = RecoveryCoordinator()
        task_id = uuid4()

        # Simulate task failure
        recovery_plan = await coordinator.create_recovery_plan(
            task_id=task_id, failure_reason="Agent timeout", attempt=1
        )

        assert recovery_plan["action"] in ["retry", "reassign", "decompose", "fail"]

        if recovery_plan["action"] == "retry":
            assert "retry_delay" in recovery_plan
            assert recovery_plan["retry_delay"] > 0
        elif recovery_plan["action"] == "reassign":
            assert "new_agent_criteria" in recovery_plan
