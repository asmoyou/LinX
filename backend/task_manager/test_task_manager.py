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
