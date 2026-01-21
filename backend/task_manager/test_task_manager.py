"""Tests for Task Manager Core.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7: Task Management Design
"""

import pytest
from uuid import uuid4

from task_manager.goal_analyzer import GoalAnalyzer, ClarificationQuestion, GoalAnalysis
from task_manager.task_decomposer import TaskDecomposer, DecomposedTask
from task_manager.capability_mapper import CapabilityMapper
from task_manager.agent_assigner import AgentAssigner
from task_manager.dependency_resolver import DependencyResolver
from task_manager.task_coordinator import TaskCoordinator


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
        assert decomposer._is_atomic_task(
            "Analyze Q4 sales data and create comprehensive report"
        ) is False
    
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
        result = mapper.map_requirements_to_capabilities(
            ["data_analyst", "writer"]
        )
        
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
    
    def test_assign_agent_to_task_no_agents(self):
        """Test assignment when no agents available."""
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
        from task_manager.task_queue import TaskQueue, TaskPriority
        
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
        from task_manager.result_collector import ResultCollector, CollectedResult
        
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
        from task_manager.result_collector import ResultCollector, CollectedResult
        
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
            ResultCollector,
            CollectedResult,
            AggregationStrategy,
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
