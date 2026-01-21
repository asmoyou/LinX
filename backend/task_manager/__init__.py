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

from task_manager.agent_assigner import AgentAssigner
from task_manager.capability_mapper import CapabilityMapper
from task_manager.dependency_resolver import DependencyResolver
from task_manager.error_handler import (
    AlertManager,
    CircuitBreaker,
    EscalationManager,
    FailureDetector,
    FailureLogger,
    FailureRecord,
    FailureType,
    RecoveryStrategy,
    RetryManager,
    RetryPolicy,
    TaskReassigner,
)
from task_manager.goal_analyzer import ClarificationQuestion, GoalAnalyzer
from task_manager.load_balancer import AgentLoad, LoadBalancer
from task_manager.progress_tracker import ProgressTracker, TaskProgress
from task_manager.recovery_coordinator import RecoveryCoordinator
from task_manager.result_collector import (
    AggregationStrategy,
    CollectedResult,
    ResultCollector,
    ResultDelivery,
)
from task_manager.task_coordinator import TaskCoordinator, TaskExecutionResult
from task_manager.task_decomposer import DecomposedTask, TaskDecomposer
from task_manager.task_executor import ExecutionResult, ExecutionStrategy, TaskExecutor
from task_manager.task_flow_visualizer import (
    NodeType,
    RelationshipType,
    TaskFlowGraph,
    TaskFlowVisualizer,
    TaskNode,
    TaskRelationship,
    get_task_flow_visualizer,
)
from task_manager.task_queue import QueuedTask, TaskPriority, TaskQueue

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
    "ResultDelivery",
    "FailureDetector",
    "RetryManager",
    "TaskReassigner",
    "EscalationManager",
    "CircuitBreaker",
    "FailureLogger",
    "AlertManager",
    "FailureRecord",
    "FailureType",
    "RecoveryStrategy",
    "RetryPolicy",
    "RecoveryCoordinator",
    "TaskFlowVisualizer",
    "TaskNode",
    "TaskRelationship",
    "TaskFlowGraph",
    "NodeType",
    "RelationshipType",
    "get_task_flow_visualizer",
]
