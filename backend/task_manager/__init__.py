"""Task Manager module for hierarchical task management.

This module implements the Task Manager component responsible for:
- Goal submission and validation
- Task decomposition using LLM
- Agent assignment based on capabilities
- Task execution coordination
- Result aggregation

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7: Task Management Design
"""

from task_manager.goal_analyzer import GoalAnalyzer, ClarificationQuestion
from task_manager.task_decomposer import TaskDecomposer, DecomposedTask
from task_manager.capability_mapper import CapabilityMapper
from task_manager.agent_assigner import AgentAssigner
from task_manager.dependency_resolver import DependencyResolver
from task_manager.task_coordinator import TaskCoordinator, TaskExecutionResult
from task_manager.task_executor import TaskExecutor, ExecutionStrategy, ExecutionResult
from task_manager.task_queue import TaskQueue, TaskPriority, QueuedTask
from task_manager.load_balancer import LoadBalancer, AgentLoad
from task_manager.progress_tracker import ProgressTracker, TaskProgress
from task_manager.result_collector import ResultCollector, AggregationStrategy, CollectedResult

__all__ = [
    "GoalAnalyzer",
    "ClarificationQuestion",
    "TaskDecomposer",
    "DecomposedTask",
    "CapabilityMapper",
    "AgentAssigner",
    "DependencyResolver",
    "TaskCoordinator",
    "TaskExecutionResult",
    "TaskExecutor",
    "ExecutionStrategy",
    "ExecutionResult",
    "TaskQueue",
    "TaskPriority",
    "QueuedTask",
    "LoadBalancer",
    "AgentLoad",
    "ProgressTracker",
    "TaskProgress",
    "ResultCollector",
    "AggregationStrategy",
    "CollectedResult",
]
