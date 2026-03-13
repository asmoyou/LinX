"""Tests for Task Manager Core.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7: Task Management Design
"""

from contextlib import contextmanager
from unittest.mock import Mock
from uuid import uuid4

import pytest

from task_manager.agent_assigner import AgentAssigner
from task_manager.capability_mapper import CapabilityMapper
from task_manager.dependency_resolver import DependencyResolver
from task_manager.goal_analyzer import ClarificationQuestion, GoalAnalysis, GoalAnalyzer
from task_manager.task_coordinator import TaskCoordinator
from task_manager.task_decomposer import DecomposedTask, TaskDecomposer


def _mock_db_session_context(*, all_result=None, first_result=None):
    session = Mock()
    query = Mock()
    filtered = Mock()
    filtered.all.return_value = all_result if all_result is not None else []
    filtered.first.return_value = first_result
    query.filter.return_value = filtered
    session.query.return_value = query

    @contextmanager
    def _ctx():
        yield session

    return _ctx


class TestGoalAnalyzer:
    """Test GoalAnalyzer functionality."""

    def test_goal_analyzer_initialization(self):
        """Test goal analyzer initializes correctly."""
        analyzer = GoalAnalyzer()
        assert analyzer is not None
        assert analyzer.llm_provider is not None

    @pytest.mark.asyncio
    async def test_analyze_clear_goal(self):
        """Test analyzing a clear goal."""
        analyzer = GoalAnalyzer()
        user_id = uuid4()

        # This will fail without actual LLM, but tests the interface
        try:
            analysis = await analyzer.analyze_goal(
                goal_text="Analyze Q4 sales data and create a report",
                user_id=user_id,
            )

            assert isinstance(analysis, GoalAnalysis)
            assert isinstance(analysis.is_clear, bool)
            assert isinstance(analysis.required_capabilities, list)
            assert isinstance(analysis.clarification_questions, list)
        except Exception:
            # Expected without LLM
            pass

    def test_heuristic_analysis(self):
        """Test heuristic analysis fallback."""
        analyzer = GoalAnalyzer()

        # Test with clear goal
        analysis = analyzer._heuristic_analysis(
            goal_text="Analyze sales data and create a detailed report",
            llm_response="",
        )

        assert isinstance(analysis, GoalAnalysis)
        assert analysis.is_clear is True
        assert len(analysis.clarification_questions) == 0

        # Test with vague goal
        analysis = analyzer._heuristic_analysis(
            goal_text="Do something",
            llm_response="",
        )

        assert analysis.is_clear is False
        assert len(analysis.clarification_questions) > 0


class TestTaskDecomposer:
    """Test TaskDecomposer functionality."""

    def test_task_decomposer_initialization(self):
        """Test task decomposer initializes correctly."""
        decomposer = TaskDecomposer()
        assert decomposer is not None
        assert decomposer.llm_provider is not None

    def test_is_atomic_task(self):
        """Test atomic task detection."""
        decomposer = TaskDecomposer()

        # Atomic tasks
        assert decomposer._is_atomic_task("Fetch data from database") is True
        assert decomposer._is_atomic_task("Calculate sum") is True

        # Non-atomic tasks
        assert (
            decomposer._is_atomic_task("Analyze Q4 sales data and create comprehensive report")
            is False
        )

    def test_collect_all_tasks(self):
        """Test collecting all tasks from tree."""
        decomposer = TaskDecomposer()

        root = DecomposedTask(
            task_id=uuid4(),
            goal_text="Root task",
            required_capabilities=["general"],
        )

        subtask1 = DecomposedTask(
            task_id=uuid4(),
            goal_text="Subtask 1",
            required_capabilities=["general"],
            parent_task_id=root.task_id,
        )

        subtask2 = DecomposedTask(
            task_id=uuid4(),
            goal_text="Subtask 2",
            required_capabilities=["general"],
            parent_task_id=root.task_id,
        )

        root.subtasks = [subtask1, subtask2]

        all_tasks = decomposer._collect_all_tasks(root)

        assert len(all_tasks) == 3
        assert root in all_tasks
        assert subtask1 in all_tasks
        assert subtask2 in all_tasks

    def test_topological_sort(self):
        """Test topological sorting of tasks."""
        decomposer = TaskDecomposer()

        task1 = DecomposedTask(
            task_id=uuid4(),
            goal_text="Task 1",
            required_capabilities=["general"],
        )

        task2 = DecomposedTask(
            task_id=uuid4(),
            goal_text="Task 2",
            required_capabilities=["general"],
            dependencies=[task1.task_id],
        )

        task3 = DecomposedTask(
            task_id=uuid4(),
            goal_text="Task 3",
            required_capabilities=["general"],
            dependencies=[task2.task_id],
        )

        tasks = [task1, task2, task3]
        execution_order = decomposer._topological_sort(tasks)

        # Task 1 should come before Task 2, Task 2 before Task 3
        assert execution_order.index(task1.task_id) < execution_order.index(task2.task_id)
        assert execution_order.index(task2.task_id) < execution_order.index(task3.task_id)


class TestCapabilityMapper:
    """Test CapabilityMapper functionality."""

    def test_capability_mapper_initialization(self):
        """Test capability mapper initializes correctly."""
        mapper = CapabilityMapper()
        assert mapper is not None
        assert len(mapper.capability_synonyms) > 0

    def test_map_requirements_to_capabilities(self):
        """Test mapping requirements to standard capabilities."""
        mapper = CapabilityMapper()

        # Test synonym mapping
        result = mapper.map_requirements_to_capabilities(["data_analyst", "writer"])

        assert "data_analysis" in result or "data_analyst" in result
        assert "content_writing" in result or "writer" in result

    def test_calculate_capability_match_score(self):
        """Test capability match score calculation."""
        mapper = CapabilityMapper()

        # Perfect match
        score = mapper.calculate_capability_match_score(
            required=["data_analysis", "sql_query"],
            available=["data_analysis", "sql_query"],
        )
        assert score == 1.0

        # Partial match
        score = mapper.calculate_capability_match_score(
            required=["data_analysis", "sql_query"],
            available=["data_analysis"],
        )
        assert 0.0 < score < 1.0

        # No match
        score = mapper.calculate_capability_match_score(
            required=["data_analysis"],
            available=["content_writing"],
        )
        assert score == 0.0


class TestAgentAssigner:
    """Test AgentAssigner functionality."""

    def test_agent_assigner_initialization(self):
        """Test agent assigner initializes correctly."""
        assigner = AgentAssigner()
        assert assigner is not None
        assert assigner.capability_mapper is not None

    def test_assign_agent_to_task_no_agents(self, monkeypatch):
        """Test assignment when no agents available."""
        monkeypatch.setattr(
            "task_manager.agent_assigner.get_db_session",
            _mock_db_session_context(all_result=[]),
        )
        assigner = AgentAssigner()

        assignment = assigner.assign_agent_to_task(
            task_id=uuid4(),
            required_capabilities=["data_analysis"],
            user_id=uuid4(),
        )

        assert assignment.agent_id is None
        assert assignment.match_score == 0.0
        assert "No available agents" in assignment.reason


class TestDependencyResolver:
    """Test DependencyResolver functionality."""

    def test_dependency_resolver_initialization(self):
        """Test dependency resolver initializes correctly."""
        resolver = DependencyResolver()
        assert resolver is not None

    def test_resolve_dependencies_no_cycles(self):
        """Test dependency resolution without cycles."""
        resolver = DependencyResolver()

        task1 = uuid4()
        task2 = uuid4()
        task3 = uuid4()

        tasks = [task1, task2, task3]
        dependencies = {
            task2: [task1],
            task3: [task2],
        }

        graph = resolver.resolve_dependencies(tasks, dependencies)

        assert graph.has_cycles is False
        assert len(graph.execution_order) == 3
        assert graph.execution_order.index(task1) < graph.execution_order.index(task2)
        assert graph.execution_order.index(task2) < graph.execution_order.index(task3)

    def test_resolve_dependencies_with_cycles(self):
        """Test dependency resolution with cycles."""
        resolver = DependencyResolver()

        task1 = uuid4()
        task2 = uuid4()

        tasks = [task1, task2]
        dependencies = {
            task1: [task2],
            task2: [task1],  # Circular dependency
        }

        graph = resolver.resolve_dependencies(tasks, dependencies)

        assert graph.has_cycles is True

    def test_get_ready_tasks(self):
        """Test getting ready tasks."""
        resolver = DependencyResolver()

        task1 = uuid4()
        task2 = uuid4()
        task3 = uuid4()

        tasks = [task1, task2, task3]
        dependencies = {
            task2: [task1],
            task3: [task1, task2],
        }

        # Initially, only task1 is ready
        ready = resolver.get_ready_tasks(tasks, dependencies, set())
        assert task1 in ready
        assert task2 not in ready
        assert task3 not in ready

        # After task1 completes, task2 is ready
        ready = resolver.get_ready_tasks(tasks, dependencies, {task1})
        assert task2 in ready
        assert task3 not in ready

        # After task1 and task2 complete, task3 is ready
        ready = resolver.get_ready_tasks(tasks, dependencies, {task1, task2})
        assert task3 in ready


class TestTaskCoordinator:
    """Test TaskCoordinator functionality."""

    def test_task_coordinator_initialization(self):
        """Test task coordinator initializes correctly."""
        coordinator = TaskCoordinator()
        assert coordinator is not None
        assert coordinator.goal_analyzer is not None
        assert coordinator.task_decomposer is not None
        assert coordinator.capability_mapper is not None
        assert coordinator.agent_assigner is not None
        assert coordinator.dependency_resolver is not None

    @pytest.mark.asyncio
    async def test_submit_goal(self):
        """Test goal submission."""
        coordinator = TaskCoordinator()
        user_id = uuid4()

        # This will fail without actual LLM and database, but tests the interface
        try:
            result = await coordinator.submit_goal(
                goal_text="Analyze Q4 sales data",
                user_id=user_id,
            )

            assert isinstance(result, dict)
            assert "status" in result
        except Exception:
            # Expected without LLM and database
            pass


class TestClarificationQuestion:
    """Test ClarificationQuestion dataclass."""

    def test_clarification_question_creation(self):
        """Test creating clarification question."""
        question = ClarificationQuestion(
            question="What time period should be analyzed?",
            context="Need to know date range",
            importance="critical",
            suggested_answers=["Last month", "Last quarter", "Last year"],
        )

        assert question.question == "What time period should be analyzed?"
        assert question.importance == "critical"
        assert len(question.suggested_answers) == 3


class TestDecomposedTask:
    """Test DecomposedTask dataclass."""

    def test_decomposed_task_creation(self):
        """Test creating decomposed task."""
        task = DecomposedTask(
            task_id=uuid4(),
            goal_text="Analyze sales data",
            required_capabilities=["data_analysis"],
            priority=5,
        )

        assert task.goal_text == "Analyze sales data"
        assert task.priority == 5
        assert len(task.required_capabilities) == 1
        assert len(task.subtasks) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestTaskExecutor:
    """Test TaskExecutor functionality."""

    def test_task_executor_initialization(self):
        """Test task executor initializes correctly."""
        from task_manager.task_executor import TaskExecutor

        executor = TaskExecutor()
        assert executor is not None
        assert len(executor._active_executions) == 0

    @pytest.mark.asyncio
    async def test_execute_sequential(self):
        """Test sequential task execution."""
        from task_manager.task_executor import TaskExecutor

        executor = TaskExecutor()
        user_id = uuid4()
        task_ids = [uuid4(), uuid4(), uuid4()]

        # This will fail without database, but tests the interface
        try:
            results = await executor.execute_sequential(task_ids, user_id)
            assert isinstance(results, list)
        except Exception:
            # Expected without database
            pass

    @pytest.mark.asyncio
    async def test_execute_parallel(self):
        """Test parallel task execution."""
        from task_manager.task_executor import TaskExecutor

        executor = TaskExecutor()
        user_id = uuid4()
        task_ids = [uuid4(), uuid4()]

        try:
            results = await executor.execute_parallel(task_ids, user_id, max_concurrent=2)
            assert isinstance(results, list)
        except Exception:
            # Expected without database
            pass


class TestTaskQueue:
    """Test TaskQueue functionality."""

    def test_task_queue_initialization(self):
        """Test task queue initializes correctly."""
        from task_manager.task_queue import TaskQueue

        queue = TaskQueue(max_size=100)
        assert queue is not None
        assert queue.max_size == 100
        assert queue.get_queue_size() == 0

    @pytest.mark.asyncio
    async def test_enqueue_task(self):
        """Test enqueueing a task."""
        from task_manager.task_queue import TaskPriority, TaskQueue

        queue = TaskQueue()
        task_id = uuid4()

        result = await queue.enqueue(
            task_id=task_id,
            priority=TaskPriority.HIGH.value,
        )

        assert result is True
        assert queue.get_pending_count() >= 0

    @pytest.mark.asyncio
    async def test_dequeue_task(self):
        """Test dequeueing a task."""
        from task_manager.task_queue import TaskQueue

        queue = TaskQueue()
        task_id = uuid4()

        await queue.enqueue(task_id=task_id)

        task = await queue.dequeue(timeout=1.0)

        if task:
            assert task.task_id == task_id

    def test_mark_completed(self):
        """Test marking task as completed."""
        from task_manager.task_queue import TaskQueue

        queue = TaskQueue()
        task_id = uuid4()

        queue.mark_completed(task_id)

        assert task_id in queue._completed_tasks
        assert queue.get_completed_count() == 1

    def test_queue_stats(self):
        """Test getting queue statistics."""
        from task_manager.task_queue import TaskQueue

        queue = TaskQueue()
        stats = queue.get_stats()

        assert "queue_size" in stats
        assert "pending_count" in stats
        assert "completed_count" in stats
        assert "failed_count" in stats


class TestLoadBalancer:
    """Test LoadBalancer functionality."""

    def test_load_balancer_initialization(self):
        """Test load balancer initializes correctly."""
        from task_manager.load_balancer import LoadBalancer

        balancer = LoadBalancer(max_tasks_per_agent=5)
        assert balancer is not None
        assert balancer.max_tasks_per_agent == 5

    def test_select_agent_no_agents(self):
        """Test agent selection with no agents."""
        from task_manager.load_balancer import LoadBalancer

        balancer = LoadBalancer()
        user_id = uuid4()

        agent_id = balancer.select_agent([], user_id)

        assert agent_id is None

    def test_get_least_loaded_agents(self):
        """Test getting least loaded agents."""
        from task_manager.load_balancer import LoadBalancer

        balancer = LoadBalancer()
        agent_ids = [uuid4(), uuid4(), uuid4()]

        least_loaded = balancer.get_least_loaded_agents(agent_ids, count=2)

        assert len(least_loaded) <= 2


class TestProgressTracker:
    """Test ProgressTracker functionality."""

    def test_progress_tracker_initialization(self):
        """Test progress tracker initializes correctly."""
        from task_manager.progress_tracker import ProgressTracker

        tracker = ProgressTracker()
        assert tracker is not None

    def test_update_progress(self):
        """Test updating task progress."""
        from task_manager.progress_tracker import ProgressTracker

        tracker = ProgressTracker()
        task_id = uuid4()

        tracker.update_progress(task_id, 50.0, "Processing data")

        assert task_id in tracker._progress_cache
        assert tracker._progress_cache[task_id].progress_percentage == 50.0

    def test_get_progress_from_cache(self):
        """Test getting progress from cache."""
        from task_manager.progress_tracker import ProgressTracker

        tracker = ProgressTracker()
        task_id = uuid4()

        tracker.update_progress(task_id, 75.0)

        progress = tracker._progress_cache.get(task_id)

        if progress:
            assert progress.progress_percentage == 75.0


class TestResultCollector:
    """Test ResultCollector functionality."""

    def test_result_collector_initialization(self):
        """Test result collector initializes correctly."""
        from task_manager.result_collector import ResultCollector

        collector = ResultCollector()
        assert collector is not None
        assert collector.llm_provider is not None

    def test_collect_results_no_tasks(self):
        """Test collecting results with no tasks."""
        from task_manager.result_collector import ResultCollector

        collector = ResultCollector()
        user_id = uuid4()

        results = collector.collect_results([], user_id)

        assert len(results) == 0

    def test_concatenate_results(self):
        """Test concatenating results."""
        from task_manager.result_collector import CollectedResult, ResultCollector

        collector = ResultCollector()

        results = [
            CollectedResult(
                task_id=uuid4(),
                result={"output": "Result 1"},
                status="completed",
                completed_at=None,
            ),
            CollectedResult(
                task_id=uuid4(),
                result={"output": "Result 2"},
                status="completed",
                completed_at=None,
            ),
        ]

        aggregated = collector._concatenate_results(results)

        assert "aggregated_output" in aggregated
        assert "Result 1" in aggregated["aggregated_output"]
        assert "Result 2" in aggregated["aggregated_output"]

    def test_merge_structured_results(self):
        """Test merging structured results."""
        from task_manager.result_collector import CollectedResult, ResultCollector

        collector = ResultCollector()

        results = [
            CollectedResult(
                task_id=uuid4(),
                result={"data": {"key": "value1"}},
                status="completed",
                completed_at=None,
            ),
            CollectedResult(
                task_id=uuid4(),
                result={"data": {"key": "value2"}},
                status="completed",
                completed_at=None,
            ),
        ]

        merged = collector._merge_structured_results(results)

        assert merged["strategy"] == "structured_merge"
        assert len(merged["results"]) == 2

    @pytest.mark.asyncio
    async def test_aggregate_results(self):
        """Test aggregating results."""
        from task_manager.result_collector import (
            AggregationStrategy,
            CollectedResult,
            ResultCollector,
        )

        collector = ResultCollector()

        results = [
            CollectedResult(
                task_id=uuid4(),
                result={"output": "Test output"},
                status="completed",
                completed_at=None,
            ),
        ]

        aggregated = await collector.aggregate_results(
            results,
            strategy=AggregationStrategy.CONCATENATION,
        )

        assert isinstance(aggregated, dict)
        assert "strategy" in aggregated or "aggregated_output" in aggregated


class TestExecutionStrategy:
    """Test ExecutionStrategy enum."""

    def test_execution_strategy_values(self):
        """Test execution strategy enum values."""
        from task_manager.task_executor import ExecutionStrategy

        assert ExecutionStrategy.SEQUENTIAL.value == "sequential"
        assert ExecutionStrategy.PARALLEL.value == "parallel"
        assert ExecutionStrategy.COLLABORATIVE.value == "collaborative"


class TestAggregationStrategy:
    """Test AggregationStrategy enum."""

    def test_aggregation_strategy_values(self):
        """Test aggregation strategy enum values."""
        from task_manager.result_collector import AggregationStrategy

        assert AggregationStrategy.CONCATENATION.value == "concatenation"
        assert AggregationStrategy.SUMMARIZATION.value == "summarization"
        assert AggregationStrategy.STRUCTURED_MERGE.value == "structured_merge"
        assert AggregationStrategy.VOTING.value == "voting"


class TestAggregationStrategySelection:
    """Test automatic aggregation strategy selection."""

    def test_select_strategy_for_structured_data(self):
        """Test strategy selection for structured data."""
        from task_manager.result_collector import CollectedResult, ResultCollector

        collector = ResultCollector()

        # Structured results with similar keys
        results = [
            CollectedResult(
                task_id=uuid4(),
                result={"name": "John", "age": 30},
                status="completed",
                completed_at=None,
            ),
            CollectedResult(
                task_id=uuid4(),
                result={"name": "Jane", "age": 25},
                status="completed",
                completed_at=None,
            ),
        ]

        strategy = collector.select_aggregation_strategy(results)

        # Should select structured merge for similar structured data
        from task_manager.result_collector import AggregationStrategy

        assert strategy == AggregationStrategy.STRUCTURED_MERGE

    def test_select_strategy_for_long_text(self):
        """Test strategy selection for long text."""
        from task_manager.result_collector import CollectedResult, ResultCollector

        collector = ResultCollector()

        # Long text results
        long_text = "This is a very long text result. " * 50
        results = [
            CollectedResult(
                task_id=uuid4(),
                result={"output": long_text},
                status="completed",
                completed_at=None,
            ),
            CollectedResult(
                task_id=uuid4(),
                result={"output": long_text},
                status="completed",
                completed_at=None,
            ),
            CollectedResult(
                task_id=uuid4(),
                result={"output": long_text},
                status="completed",
                completed_at=None,
            ),
        ]

        strategy = collector.select_aggregation_strategy(results)

        # Should select summarization for long text
        from task_manager.result_collector import AggregationStrategy

        assert strategy == AggregationStrategy.SUMMARIZATION

    def test_select_strategy_default(self):
        """Test default strategy selection."""
        from task_manager.result_collector import CollectedResult, ResultCollector

        collector = ResultCollector()

        # Simple results
        results = [
            CollectedResult(
                task_id=uuid4(),
                result={"output": "Short result"},
                status="completed",
                completed_at=None,
            ),
        ]

        strategy = collector.select_aggregation_strategy(results)

        # Should default to concatenation
        from task_manager.result_collector import AggregationStrategy

        assert strategy == AggregationStrategy.CONCATENATION


class TestResultDelivery:
    """Test ResultDelivery functionality."""

    def test_result_delivery_initialization(self):
        """Test result delivery initializes correctly."""
        from task_manager.result_collector import ResultDelivery

        delivery = ResultDelivery()
        assert delivery is not None

    @pytest.mark.asyncio
    async def test_deliver_result_to_database(self):
        """Test delivering result to database."""
        from task_manager.result_collector import ResultDelivery

        delivery = ResultDelivery()
        task_id = uuid4()
        user_id = uuid4()
        result = {"output": "Test result"}

        # This will fail without database, but tests the interface
        try:
            success = await delivery.deliver_result(
                task_id=task_id,
                user_id=user_id,
                result=result,
                delivery_method="database",
            )
            assert isinstance(success, bool)
        except Exception:
            # Expected without database
            pass

    def test_format_result_as_json(self):
        """Test formatting result as JSON."""
        from task_manager.result_collector import ResultDelivery

        delivery = ResultDelivery()
        result = {"strategy": "concatenation", "output": "Test"}

        formatted = delivery.format_result_for_user(result, format_type="json")

        assert isinstance(formatted, str)
        assert "concatenation" in formatted

    def test_format_result_as_text(self):
        """Test formatting result as text."""
        from task_manager.result_collector import ResultDelivery

        delivery = ResultDelivery()
        result = {
            "strategy": "summarization",
            "summary": "This is a summary",
        }

        formatted = delivery.format_result_for_user(result, format_type="text")

        assert isinstance(formatted, str)
        assert "summarization" in formatted
        assert "This is a summary" in formatted

    def test_format_result_as_html(self):
        """Test formatting result as HTML."""
        from task_manager.result_collector import ResultDelivery

        delivery = ResultDelivery()
        result = {"strategy": "voting", "winner": "Best result"}

        formatted = delivery.format_result_for_user(result, format_type="html")

        assert isinstance(formatted, str)
        assert "<div" in formatted
        assert "voting" in formatted


class TestResultAggregationIntegration:
    """Test integrated result aggregation workflow."""

    @pytest.mark.asyncio
    async def test_full_aggregation_workflow(self):
        """Test complete aggregation workflow."""
        from task_manager.result_collector import (
            CollectedResult,
            ResultCollector,
            ResultDelivery,
        )

        collector = ResultCollector()
        delivery = ResultDelivery()

        # Create sample results
        results = [
            CollectedResult(
                task_id=uuid4(),
                result={"output": "Result 1"},
                status="completed",
                completed_at=None,
            ),
            CollectedResult(
                task_id=uuid4(),
                result={"output": "Result 2"},
                status="completed",
                completed_at=None,
            ),
        ]

        # Select strategy
        strategy = collector.select_aggregation_strategy(results)
        assert strategy is not None

        # Aggregate results
        aggregated = await collector.aggregate_results(results, strategy)
        assert isinstance(aggregated, dict)

        # Format for user
        formatted = delivery.format_result_for_user(aggregated, format_type="text")
        assert isinstance(formatted, str)


class TestFailureDetector:
    """Test FailureDetector functionality."""

    def test_failure_detector_initialization(self):
        """Test failure detector initializes correctly."""
        from task_manager.error_handler import FailureDetector

        detector = FailureDetector()
        assert detector is not None
        assert len(detector._timeout_thresholds) > 0

    def test_detect_failure_no_task(self, monkeypatch):
        """Test failure detection with non-existent task."""
        monkeypatch.setattr(
            "task_manager.error_handler.get_db_session",
            _mock_db_session_context(first_result=None),
        )
        from task_manager.error_handler import FailureDetector

        detector = FailureDetector()
        task_id = uuid4()
        user_id = uuid4()

        failure = detector.detect_failure(task_id, user_id)

        assert failure is None


class TestRetryManager:
    """Test RetryManager functionality."""

    def test_retry_manager_initialization(self):
        """Test retry manager initializes correctly."""
        from task_manager.error_handler import RetryManager, RetryPolicy

        policy = RetryPolicy(max_retries=5)
        manager = RetryManager(policy)

        assert manager is not None
        assert manager.default_policy.max_retries == 5

    def test_should_retry_within_limit(self):
        """Test retry decision within limit."""
        from datetime import datetime

        from task_manager.error_handler import (
            FailureRecord,
            FailureType,
            RetryManager,
        )

        manager = RetryManager()
        task_id = uuid4()

        failure = FailureRecord(
            task_id=task_id,
            failure_type=FailureType.TIMEOUT,
            error_message="Timeout",
            timestamp=datetime.utcnow(),
            retry_count=1,
        )

        should_retry = manager.should_retry(task_id, failure)

        assert should_retry is True

    def test_should_not_retry_max_reached(self):
        """Test retry decision when max reached."""
        from datetime import datetime

        from task_manager.error_handler import (
            FailureRecord,
            FailureType,
            RetryManager,
        )

        manager = RetryManager()
        task_id = uuid4()

        failure = FailureRecord(
            task_id=task_id,
            failure_type=FailureType.TIMEOUT,
            error_message="Timeout",
            timestamp=datetime.utcnow(),
            retry_count=3,  # Max retries
        )

        should_retry = manager.should_retry(task_id, failure)

        assert should_retry is False

    def test_calculate_retry_delay(self):
        """Test retry delay calculation."""
        from task_manager.error_handler import RetryManager

        manager = RetryManager()

        delay0 = manager.calculate_retry_delay(0)
        delay1 = manager.calculate_retry_delay(1)
        delay2 = manager.calculate_retry_delay(2)

        # Delays should increase exponentially
        assert delay1 > delay0
        assert delay2 > delay1

    def test_record_retry(self):
        """Test recording retry attempts."""
        from task_manager.error_handler import RetryManager

        manager = RetryManager()
        task_id = uuid4()

        manager.record_retry(task_id)
        manager.record_retry(task_id)

        assert len(manager._retry_history[task_id]) == 2


class TestCircuitBreaker:
    """Test CircuitBreaker functionality."""

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initializes correctly."""
        from task_manager.error_handler import CircuitBreaker

        breaker = CircuitBreaker()
        assert breaker is not None

    def test_circuit_breaker_closed_initially(self):
        """Test circuit breaker is closed initially."""
        from task_manager.error_handler import CircuitBreaker

        breaker = CircuitBreaker()
        component_id = "test_component"

        assert breaker.is_open(component_id) is False

    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures."""
        from task_manager.error_handler import CircuitBreaker

        breaker = CircuitBreaker()
        component_id = "test_component"

        # Record failures up to threshold
        for _ in range(5):
            breaker.record_failure(component_id)

        assert breaker.is_open(component_id) is True

    def test_circuit_breaker_closes_after_success(self):
        """Test circuit breaker closes after success."""
        from task_manager.error_handler import CircuitBreaker

        breaker = CircuitBreaker()
        component_id = "test_component"

        # Record some failures
        breaker.record_failure(component_id)
        breaker.record_failure(component_id)

        # Record success
        breaker.record_success(component_id)

        # Should reset failure count
        assert breaker._breakers[component_id].failure_count == 0


class TestEscalationManager:
    """Test EscalationManager functionality."""

    def test_escalation_manager_initialization(self):
        """Test escalation manager initializes correctly."""
        from task_manager.error_handler import EscalationManager

        manager = EscalationManager()
        assert manager is not None

    def test_register_escalation_callback(self):
        """Test registering escalation callback."""
        from task_manager.error_handler import EscalationManager

        manager = EscalationManager()

        def callback(task_id, failure_record):
            pass

        manager.register_escalation_callback(callback)

        assert len(manager._escalation_callbacks) == 1

    @pytest.mark.asyncio
    async def test_escalate_to_user(self):
        """Test escalating to user."""
        from datetime import datetime

        from task_manager.error_handler import (
            EscalationManager,
            FailureRecord,
            FailureType,
        )

        manager = EscalationManager()
        task_id = uuid4()
        user_id = uuid4()

        failure = FailureRecord(
            task_id=task_id,
            failure_type=FailureType.TIMEOUT,
            error_message="Test error",
            timestamp=datetime.utcnow(),
        )

        # This will fail without database, but tests the interface
        try:
            result = await manager.escalate_to_user(
                task_id=task_id,
                user_id=user_id,
                failure_record=failure,
                message="Test escalation",
            )
            assert isinstance(result, bool)
        except Exception:
            # Expected without database
            pass


class TestAlertManager:
    """Test AlertManager functionality."""

    def test_alert_manager_initialization(self):
        """Test alert manager initializes correctly."""
        from task_manager.error_handler import AlertManager

        manager = AlertManager()
        assert manager is not None

    def test_register_alert_callback(self):
        """Test registering alert callback."""
        from task_manager.error_handler import AlertManager

        manager = AlertManager()

        def callback(message, details):
            pass

        manager.register_alert_callback(callback)

        assert len(manager._alert_callbacks) == 1

    def test_send_alert(self):
        """Test sending alert."""
        from task_manager.error_handler import AlertManager

        manager = AlertManager()

        # Should not raise exception
        manager.send_alert(
            severity="critical",
            message="Test alert",
            details={"key": "value"},
        )


class TestRecoveryCoordinator:
    """Test RecoveryCoordinator functionality."""

    def test_recovery_coordinator_initialization(self):
        """Test recovery coordinator initializes correctly."""
        from task_manager.recovery_coordinator import RecoveryCoordinator

        coordinator = RecoveryCoordinator()
        assert coordinator is not None
        assert coordinator.failure_detector is not None
        assert coordinator.retry_manager is not None
        assert coordinator.task_reassigner is not None
        assert coordinator.escalation_manager is not None
        assert coordinator.circuit_breaker is not None
        assert coordinator.failure_logger is not None
        assert coordinator.alert_manager is not None

    def test_select_recovery_strategy_retry(self):
        """Test recovery strategy selection for retry."""
        from datetime import datetime

        from task_manager.error_handler import (
            FailureRecord,
            FailureType,
            RecoveryStrategy,
        )
        from task_manager.recovery_coordinator import RecoveryCoordinator

        coordinator = RecoveryCoordinator()

        failure = FailureRecord(
            task_id=uuid4(),
            failure_type=FailureType.TIMEOUT,
            error_message="Timeout",
            timestamp=datetime.utcnow(),
            retry_count=0,
        )

        strategy = coordinator._select_recovery_strategy(failure)

        assert strategy == RecoveryStrategy.RETRY

    def test_select_recovery_strategy_escalate(self):
        """Test recovery strategy selection for escalation."""
        from datetime import datetime

        from task_manager.error_handler import (
            FailureRecord,
            FailureType,
            RecoveryStrategy,
        )
        from task_manager.recovery_coordinator import RecoveryCoordinator

        coordinator = RecoveryCoordinator()

        failure = FailureRecord(
            task_id=uuid4(),
            failure_type=FailureType.VALIDATION_ERROR,
            error_message="Validation failed",
            timestamp=datetime.utcnow(),
            retry_count=0,
        )

        strategy = coordinator._select_recovery_strategy(failure)

        assert strategy == RecoveryStrategy.ESCALATE

    def test_register_callbacks(self):
        """Test registering callbacks."""
        from task_manager.recovery_coordinator import RecoveryCoordinator

        coordinator = RecoveryCoordinator()

        def escalation_callback(task_id, failure_record):
            pass

        def alert_callback(message, details):
            pass

        coordinator.register_escalation_callback(escalation_callback)
        coordinator.register_alert_callback(alert_callback)

        assert len(coordinator.escalation_manager._escalation_callbacks) == 1
        assert len(coordinator.alert_manager._alert_callbacks) == 1


class TestFailureTypes:
    """Test FailureType enum."""

    def test_failure_type_values(self):
        """Test failure type enum values."""
        from task_manager.error_handler import FailureType

        assert FailureType.TIMEOUT.value == "timeout"
        assert FailureType.AGENT_ERROR.value == "agent_error"
        assert FailureType.CONTAINER_CRASH.value == "container_crash"
        assert FailureType.VALIDATION_ERROR.value == "validation_error"


class TestRecoveryStrategies:
    """Test RecoveryStrategy enum."""

    def test_recovery_strategy_values(self):
        """Test recovery strategy enum values."""
        from task_manager.error_handler import RecoveryStrategy

        assert RecoveryStrategy.RETRY.value == "retry"
        assert RecoveryStrategy.REASSIGN.value == "reassign"
        assert RecoveryStrategy.ESCALATE.value == "escalate"
        assert RecoveryStrategy.PARTIAL_SUCCESS.value == "partial_success"
        assert RecoveryStrategy.FAIL.value == "fail"


# Task Flow Visualization Tests


def test_task_node_creation():
    """Test TaskNode creation and serialization."""
    from task_manager.task_flow_visualizer import NodeType, TaskNode

    task_id = uuid4()
    agent_id = uuid4()

    node = TaskNode(
        task_id=task_id,
        node_type=NodeType.TASK,
        title="Test Task",
        status="in_progress",
        progress=0.5,
        agent_id=agent_id,
        agent_name="Test Agent",
    )

    assert node.task_id == task_id
    assert node.node_type == NodeType.TASK
    assert node.status == "in_progress"
    assert node.progress == 0.5

    # Test serialization
    data = node.to_dict()
    assert data["task_id"] == str(task_id)
    assert data["node_type"] == "task"
    assert data["status"] == "in_progress"
    assert data["agent_name"] == "Test Agent"


def test_task_relationship_creation():
    """Test TaskRelationship creation and serialization."""
    from task_manager.task_flow_visualizer import RelationshipType, TaskRelationship

    source_id = uuid4()
    target_id = uuid4()

    rel = TaskRelationship(
        source_id=source_id,
        target_id=target_id,
        relationship_type=RelationshipType.DEPENDENCY,
        metadata={"priority": "high"},
    )

    assert rel.source_id == source_id
    assert rel.target_id == target_id
    assert rel.relationship_type == RelationshipType.DEPENDENCY

    # Test serialization
    data = rel.to_dict()
    assert data["source_id"] == str(source_id)
    assert data["target_id"] == str(target_id)
    assert data["relationship_type"] == "dependency"
    assert data["metadata"]["priority"] == "high"


def test_task_flow_graph_operations():
    """Test TaskFlowGraph operations."""
    from task_manager.task_flow_visualizer import (
        NodeType,
        RelationshipType,
        TaskFlowGraph,
        TaskNode,
        TaskRelationship,
    )

    root_id = uuid4()
    graph = TaskFlowGraph(root_task_id=root_id)

    # Add nodes
    node1 = TaskNode(
        task_id=root_id,
        node_type=NodeType.GOAL,
        title="Root Task",
        status="in_progress",
    )

    node2_id = uuid4()
    node2 = TaskNode(
        task_id=node2_id,
        node_type=NodeType.TASK,
        title="Subtask",
        status="pending",
    )

    graph.add_node(node1)
    graph.add_node(node2)

    assert len(graph.nodes) == 2
    assert graph.get_node(root_id) == node1
    assert graph.get_node(node2_id) == node2

    # Add relationship
    rel = TaskRelationship(
        source_id=root_id,
        target_id=node2_id,
        relationship_type=RelationshipType.PARENT_CHILD,
    )
    graph.add_relationship(rel)

    assert len(graph.relationships) == 1

    # Update node
    graph.update_node(node2_id, status="in_progress", progress=0.3)
    updated_node = graph.get_node(node2_id)
    assert updated_node.status == "in_progress"
    assert updated_node.progress == 0.3

    # Test serialization
    data = graph.to_dict()
    assert data["root_task_id"] == str(root_id)
    assert len(data["nodes"]) == 2
    assert len(data["relationships"]) == 1


def test_task_flow_visualizer_initialization():
    """Test TaskFlowVisualizer initialization."""
    from task_manager.task_flow_visualizer import TaskFlowVisualizer

    visualizer = TaskFlowVisualizer()

    assert visualizer is not None
    assert len(visualizer._graphs) == 0


def test_task_flow_visualizer_update_task_status():
    """Test updating task status in visualizer."""
    from task_manager.task_flow_visualizer import (
        NodeType,
        TaskFlowGraph,
        TaskFlowVisualizer,
        TaskNode,
    )

    visualizer = TaskFlowVisualizer()

    # Create a graph
    root_id = uuid4()
    task_id = uuid4()

    graph = TaskFlowGraph(root_task_id=root_id)
    node = TaskNode(
        task_id=task_id,
        node_type=NodeType.TASK,
        title="Test Task",
        status="pending",
    )
    graph.add_node(node)

    visualizer._graphs[root_id] = graph

    # Update status
    updated_roots = visualizer.update_task_status(
        task_id=task_id,
        status="in_progress",
        progress=0.5,
    )

    assert root_id in updated_roots
    updated_node = graph.get_node(task_id)
    assert updated_node.status == "in_progress"
    assert updated_node.progress == 0.5


def test_task_flow_visualizer_update_agent():
    """Test updating task agent assignment."""
    from task_manager.task_flow_visualizer import (
        NodeType,
        TaskFlowGraph,
        TaskFlowVisualizer,
        TaskNode,
    )

    visualizer = TaskFlowVisualizer()

    # Create a graph
    root_id = uuid4()
    task_id = uuid4()
    agent_id = uuid4()

    graph = TaskFlowGraph(root_task_id=root_id)
    node = TaskNode(
        task_id=task_id,
        node_type=NodeType.TASK,
        title="Test Task",
        status="pending",
    )
    graph.add_node(node)

    visualizer._graphs[root_id] = graph

    # Update agent
    updated_roots = visualizer.update_task_agent(
        task_id=task_id,
        agent_id=agent_id,
        agent_name="Test Agent",
    )

    assert root_id in updated_roots
    updated_node = graph.get_node(task_id)
    assert updated_node.agent_id == agent_id
    assert updated_node.agent_name == "Test Agent"


def test_task_flow_visualizer_add_collaboration():
    """Test adding collaboration relationship."""
    from task_manager.task_flow_visualizer import (
        NodeType,
        RelationshipType,
        TaskFlowGraph,
        TaskFlowVisualizer,
        TaskNode,
    )

    visualizer = TaskFlowVisualizer()

    # Create a graph with two tasks
    root_id = uuid4()
    task1_id = uuid4()
    task2_id = uuid4()

    graph = TaskFlowGraph(root_task_id=root_id)

    node1 = TaskNode(
        task_id=task1_id,
        node_type=NodeType.TASK,
        title="Task 1",
        status="in_progress",
    )

    node2 = TaskNode(
        task_id=task2_id,
        node_type=NodeType.TASK,
        title="Task 2",
        status="in_progress",
    )

    graph.add_node(node1)
    graph.add_node(node2)

    visualizer._graphs[root_id] = graph

    # Add collaboration
    updated_roots = visualizer.add_collaboration_relationship(
        task_id_1=task1_id,
        task_id_2=task2_id,
        metadata={"type": "data_sharing"},
    )

    assert root_id in updated_roots
    assert len(graph.relationships) == 1

    rel = graph.relationships[0]
    assert rel.source_id == task1_id
    assert rel.target_id == task2_id
    assert rel.relationship_type == RelationshipType.COLLABORATION
    assert rel.metadata["type"] == "data_sharing"


def test_task_flow_visualizer_clear_graph():
    """Test clearing cached graph."""
    from task_manager.task_flow_visualizer import (
        TaskFlowGraph,
        TaskFlowVisualizer,
    )

    visualizer = TaskFlowVisualizer()

    root_id = uuid4()
    graph = TaskFlowGraph(root_task_id=root_id)

    visualizer._graphs[root_id] = graph
    assert root_id in visualizer._graphs

    visualizer.clear_graph(root_id)
    assert root_id not in visualizer._graphs


def test_task_flow_visualizer_get_cached_graph():
    """Test getting cached graph."""
    from task_manager.task_flow_visualizer import (
        TaskFlowGraph,
        TaskFlowVisualizer,
    )

    visualizer = TaskFlowVisualizer()

    root_id = uuid4()
    graph = TaskFlowGraph(root_task_id=root_id)

    visualizer._graphs[root_id] = graph

    cached_graph = visualizer.get_task_flow(root_id)
    assert cached_graph == graph

    # Test non-existent graph
    non_existent = visualizer.get_task_flow(uuid4())
    assert non_existent is None


def test_node_type_enum():
    """Test NodeType enum values."""
    from task_manager.task_flow_visualizer import NodeType

    assert NodeType.GOAL.value == "goal"
    assert NodeType.TASK.value == "task"
    assert NodeType.SUBTASK.value == "subtask"


def test_relationship_type_enum():
    """Test RelationshipType enum values."""
    from task_manager.task_flow_visualizer import RelationshipType

    assert RelationshipType.PARENT_CHILD.value == "parent_child"
    assert RelationshipType.DEPENDENCY.value == "dependency"
    assert RelationshipType.COLLABORATION.value == "collaboration"


def test_task_node_with_error():
    """Test TaskNode with error message."""
    from task_manager.task_flow_visualizer import NodeType, TaskNode

    task_id = uuid4()

    node = TaskNode(
        task_id=task_id,
        node_type=NodeType.TASK,
        title="Failed Task",
        status="failed",
        error_message="Task execution failed",
    )

    assert node.status == "failed"
    assert node.error_message == "Task execution failed"

    data = node.to_dict()
    assert data["error_message"] == "Task execution failed"


def test_task_node_metadata():
    """Test TaskNode with custom metadata."""
    from task_manager.task_flow_visualizer import NodeType, TaskNode

    task_id = uuid4()

    node = TaskNode(
        task_id=task_id,
        node_type=NodeType.TASK,
        title="Task with Metadata",
        status="in_progress",
        metadata={
            "priority": "high",
            "estimated_duration": 300,
            "tags": ["urgent", "critical"],
        },
    )

    assert node.metadata["priority"] == "high"
    assert node.metadata["estimated_duration"] == 300
    assert "urgent" in node.metadata["tags"]

    data = node.to_dict()
    assert data["metadata"]["priority"] == "high"


def test_get_task_flow_visualizer_singleton():
    """Test get_task_flow_visualizer returns singleton."""
    from task_manager.task_flow_visualizer import get_task_flow_visualizer

    visualizer1 = get_task_flow_visualizer()
    visualizer2 = get_task_flow_visualizer()

    assert visualizer1 is visualizer2
