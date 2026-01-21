"""Task Flow Visualization for Real-Time Task Monitoring.

Implements task flow data structures and real-time updates for visualization.

References:
- Requirements 13: Task Flow Visualization
- Design Section 18.5: Task Flow Visualization
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import UUID

from database.connection import get_db_session
from database.models import Agent
from database.models import Task as TaskModel

logger = logging.getLogger(__name__)


class NodeType(Enum):
    """Types of nodes in task flow."""

    GOAL = "goal"
    TASK = "task"
    SUBTASK = "subtask"


class RelationshipType(Enum):
    """Types of relationships between nodes."""

    PARENT_CHILD = "parent_child"
    DEPENDENCY = "dependency"
    COLLABORATION = "collaboration"


@dataclass
class TaskNode:
    """Represents a task node in the flow visualization."""

    task_id: UUID
    node_type: NodeType
    title: str
    status: str
    progress: float = 0.0
    agent_id: Optional[UUID] = None
    agent_name: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    error_message: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert node to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "task_id": str(self.task_id),
            "node_type": self.node_type.value,
            "title": self.title,
            "status": self.status,
            "progress": self.progress,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "agent_name": self.agent_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


@dataclass
class TaskRelationship:
    """Represents a relationship between tasks."""

    source_id: UUID
    target_id: UUID
    relationship_type: RelationshipType
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert relationship to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "source_id": str(self.source_id),
            "target_id": str(self.target_id),
            "relationship_type": self.relationship_type.value,
            "metadata": self.metadata,
        }


@dataclass
class TaskFlowGraph:
    """Represents the complete task flow graph."""

    root_task_id: UUID
    nodes: Dict[UUID, TaskNode] = field(default_factory=dict)
    relationships: List[TaskRelationship] = field(default_factory=list)

    def add_node(self, node: TaskNode) -> None:
        """Add a node to the graph.

        Args:
            node: Task node to add
        """
        self.nodes[node.task_id] = node

    def add_relationship(self, relationship: TaskRelationship) -> None:
        """Add a relationship to the graph.

        Args:
            relationship: Task relationship to add
        """
        self.relationships.append(relationship)

    def get_node(self, task_id: UUID) -> Optional[TaskNode]:
        """Get a node by task ID.

        Args:
            task_id: Task ID

        Returns:
            Task node or None
        """
        return self.nodes.get(task_id)

    def update_node(self, task_id: UUID, **kwargs) -> None:
        """Update a node's attributes.

        Args:
            task_id: Task ID
            **kwargs: Attributes to update
        """
        if task_id in self.nodes:
            node = self.nodes[task_id]
            for key, value in kwargs.items():
                if hasattr(node, key):
                    setattr(node, key, value)
            node.updated_at = datetime.utcnow()

    def to_dict(self) -> Dict:
        """Convert graph to dictionary for JSON serialization.

        Returns:
            Dictionary representation
        """
        return {
            "root_task_id": str(self.root_task_id),
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "relationships": [rel.to_dict() for rel in self.relationships],
        }


class TaskFlowVisualizer:
    """Manages task flow visualization and real-time updates."""

    def __init__(self):
        """Initialize task flow visualizer."""
        self._graphs: Dict[UUID, TaskFlowGraph] = {}
        self._subscribers: Dict[UUID, Set] = {}

        logger.info("TaskFlowVisualizer initialized")

    def build_task_flow(
        self,
        root_task_id: UUID,
        user_id: UUID,
    ) -> TaskFlowGraph:
        """Build task flow graph from database.

        Args:
            root_task_id: Root task ID
            user_id: User ID for permission checking

        Returns:
            Task flow graph
        """
        graph = TaskFlowGraph(root_task_id=root_task_id)

        with get_db_session() as session:
            # Get root task
            root_task = (
                session.query(TaskModel)
                .filter(
                    TaskModel.task_id == root_task_id,
                    TaskModel.created_by_user_id == user_id,
                )
                .first()
            )

            if not root_task:
                logger.warning(
                    "Root task not found",
                    extra={"task_id": str(root_task_id)},
                )
                return graph

            # Build graph recursively
            self._build_task_tree(session, root_task, graph, user_id)

            # Add dependency relationships
            self._add_dependency_relationships(session, graph, user_id)

        # Cache the graph
        self._graphs[root_task_id] = graph

        logger.info(
            "Task flow built",
            extra={
                "root_task_id": str(root_task_id),
                "node_count": len(graph.nodes),
                "relationship_count": len(graph.relationships),
            },
        )

        return graph

    def _build_task_tree(
        self,
        session,
        task: TaskModel,
        graph: TaskFlowGraph,
        user_id: UUID,
        parent_id: Optional[UUID] = None,
    ) -> None:
        """Recursively build task tree.

        Args:
            session: Database session
            task: Current task
            graph: Task flow graph
            user_id: User ID
            parent_id: Parent task ID
        """
        # Determine node type
        if parent_id is None:
            node_type = NodeType.GOAL
        elif task.parent_task_id == graph.root_task_id:
            node_type = NodeType.TASK
        else:
            node_type = NodeType.SUBTASK

        # Get agent info
        agent_name = None
        if task.assigned_agent_id:
            agent = (
                session.query(Agent)
                .filter(
                    Agent.agent_id == task.assigned_agent_id,
                )
                .first()
            )
            if agent:
                agent_name = agent.name

        # Create node
        node = TaskNode(
            task_id=task.task_id,
            node_type=node_type,
            title=task.goal_text[:100],  # Truncate for display
            status=task.status,
            progress=self._calculate_progress(session, task),
            agent_id=task.assigned_agent_id,
            agent_name=agent_name,
            created_at=task.created_at,
            updated_at=task.updated_at or task.created_at,
            error_message=self._extract_error_message(task),
            metadata={
                "priority": task.priority,
                "has_subtasks": bool(task.subtasks),
            },
        )

        graph.add_node(node)

        # Add parent-child relationship
        if parent_id:
            relationship = TaskRelationship(
                source_id=parent_id,
                target_id=task.task_id,
                relationship_type=RelationshipType.PARENT_CHILD,
            )
            graph.add_relationship(relationship)

        # Process subtasks
        for subtask in task.subtasks:
            self._build_task_tree(session, subtask, graph, user_id, task.task_id)

    def _calculate_progress(self, session, task: TaskModel) -> float:
        """Calculate task progress based on subtasks.

        Args:
            session: Database session
            task: Task model

        Returns:
            Progress percentage (0.0 to 1.0)
        """
        if task.status == "completed":
            return 1.0
        elif task.status == "failed":
            return 0.0
        elif task.status == "pending":
            return 0.0
        elif task.status == "in_progress":
            # If has subtasks, calculate based on subtask completion
            if task.subtasks:
                completed = sum(1 for st in task.subtasks if st.status == "completed")
                total = len(task.subtasks)
                return completed / total if total > 0 else 0.0
            else:
                # No subtasks, assume 50% progress
                return 0.5

        return 0.0

    def _extract_error_message(self, task: TaskModel) -> Optional[str]:
        """Extract error message from task result.

        Args:
            task: Task model

        Returns:
            Error message or None
        """
        if task.status in ["failed", "escalated"] and task.result:
            if isinstance(task.result, dict):
                return task.result.get("error") or task.result.get("escalation_message")

        return None

    def _add_dependency_relationships(
        self,
        session,
        graph: TaskFlowGraph,
        user_id: UUID,
    ) -> None:
        """Add dependency relationships to graph.

        Args:
            session: Database session
            graph: Task flow graph
            user_id: User ID
        """
        # Get all tasks in graph
        task_ids = list(graph.nodes.keys())

        # Query tasks with dependencies
        tasks = (
            session.query(TaskModel)
            .filter(
                TaskModel.task_id.in_(task_ids),
            )
            .all()
        )

        for task in tasks:
            if task.result and isinstance(task.result, dict):
                dependencies = task.result.get("dependencies", [])

                for dep_id_str in dependencies:
                    try:
                        dep_id = UUID(dep_id_str)
                        if dep_id in graph.nodes:
                            relationship = TaskRelationship(
                                source_id=dep_id,
                                target_id=task.task_id,
                                relationship_type=RelationshipType.DEPENDENCY,
                            )
                            graph.add_relationship(relationship)
                    except (ValueError, TypeError):
                        continue

    def get_task_flow(self, root_task_id: UUID) -> Optional[TaskFlowGraph]:
        """Get cached task flow graph.

        Args:
            root_task_id: Root task ID

        Returns:
            Task flow graph or None
        """
        return self._graphs.get(root_task_id)

    def update_task_status(
        self,
        task_id: UUID,
        status: str,
        progress: Optional[float] = None,
        error_message: Optional[str] = None,
    ) -> List[UUID]:
        """Update task status in all graphs containing this task.

        Args:
            task_id: Task ID
            status: New status
            progress: New progress (optional)
            error_message: Error message (optional)

        Returns:
            List of root task IDs that were updated
        """
        updated_roots = []

        for root_id, graph in self._graphs.items():
            if task_id in graph.nodes:
                update_data = {"status": status}

                if progress is not None:
                    update_data["progress"] = progress

                if error_message is not None:
                    update_data["error_message"] = error_message

                graph.update_node(task_id, **update_data)
                updated_roots.append(root_id)

                logger.debug(
                    "Task status updated in graph",
                    extra={
                        "task_id": str(task_id),
                        "root_id": str(root_id),
                        "status": status,
                    },
                )

        return updated_roots

    def update_task_agent(
        self,
        task_id: UUID,
        agent_id: UUID,
        agent_name: str,
    ) -> List[UUID]:
        """Update task agent assignment in all graphs.

        Args:
            task_id: Task ID
            agent_id: Agent ID
            agent_name: Agent name

        Returns:
            List of root task IDs that were updated
        """
        updated_roots = []

        for root_id, graph in self._graphs.items():
            if task_id in graph.nodes:
                graph.update_node(
                    task_id,
                    agent_id=agent_id,
                    agent_name=agent_name,
                )
                updated_roots.append(root_id)

                logger.debug(
                    "Task agent updated in graph",
                    extra={
                        "task_id": str(task_id),
                        "root_id": str(root_id),
                        "agent_id": str(agent_id),
                    },
                )

        return updated_roots

    def add_collaboration_relationship(
        self,
        task_id_1: UUID,
        task_id_2: UUID,
        metadata: Optional[Dict] = None,
    ) -> List[UUID]:
        """Add collaboration relationship between tasks.

        Args:
            task_id_1: First task ID
            task_id_2: Second task ID
            metadata: Additional metadata

        Returns:
            List of root task IDs that were updated
        """
        updated_roots = []
        metadata = metadata or {}

        for root_id, graph in self._graphs.items():
            if task_id_1 in graph.nodes and task_id_2 in graph.nodes:
                relationship = TaskRelationship(
                    source_id=task_id_1,
                    target_id=task_id_2,
                    relationship_type=RelationshipType.COLLABORATION,
                    metadata=metadata,
                )
                graph.add_relationship(relationship)
                updated_roots.append(root_id)

                logger.debug(
                    "Collaboration relationship added",
                    extra={
                        "task_id_1": str(task_id_1),
                        "task_id_2": str(task_id_2),
                        "root_id": str(root_id),
                    },
                )

        return updated_roots

    def clear_graph(self, root_task_id: UUID) -> None:
        """Clear cached graph.

        Args:
            root_task_id: Root task ID
        """
        if root_task_id in self._graphs:
            del self._graphs[root_task_id]

            logger.info(
                "Task flow graph cleared",
                extra={"root_task_id": str(root_task_id)},
            )


# Global instance
_visualizer_instance: Optional[TaskFlowVisualizer] = None


def get_task_flow_visualizer() -> TaskFlowVisualizer:
    """Get global task flow visualizer instance.

    Returns:
        Task flow visualizer instance
    """
    global _visualizer_instance

    if _visualizer_instance is None:
        _visualizer_instance = TaskFlowVisualizer()

    return _visualizer_instance
