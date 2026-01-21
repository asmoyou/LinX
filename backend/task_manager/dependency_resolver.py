"""Dependency Resolution for Tasks.

Resolves task dependencies and determines execution order.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.1: Task Decomposition Algorithm
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Set
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class DependencyGraph:
    """Task dependency graph."""

    tasks: List[UUID]
    dependencies: Dict[UUID, List[UUID]]  # task_id -> list of dependency task_ids
    execution_order: List[UUID]
    has_cycles: bool


class DependencyResolver:
    """Resolves task dependencies and execution order."""

    def __init__(self):
        """Initialize dependency resolver."""
        logger.info("DependencyResolver initialized")

    def resolve_dependencies(
        self,
        tasks: List[UUID],
        dependencies: Dict[UUID, List[UUID]],
    ) -> DependencyGraph:
        """Resolve task dependencies and determine execution order.

        Args:
            tasks: List of all task IDs
            dependencies: Map of task_id to list of dependency task_ids

        Returns:
            DependencyGraph with execution order
        """
        logger.info(
            "Resolving dependencies",
            extra={"num_tasks": len(tasks)},
        )

        # Detect cycles
        has_cycles = self._has_cycles(tasks, dependencies)

        if has_cycles:
            logger.warning("Circular dependencies detected")
            # Return tasks in original order
            return DependencyGraph(
                tasks=tasks,
                dependencies=dependencies,
                execution_order=tasks,
                has_cycles=True,
            )

        # Topological sort
        execution_order = self._topological_sort(tasks, dependencies)

        logger.info(
            "Dependencies resolved",
            extra={
                "execution_order_length": len(execution_order),
                "has_cycles": has_cycles,
            },
        )

        return DependencyGraph(
            tasks=tasks,
            dependencies=dependencies,
            execution_order=execution_order,
            has_cycles=False,
        )

    def _has_cycles(
        self,
        tasks: List[UUID],
        dependencies: Dict[UUID, List[UUID]],
    ) -> bool:
        """Check if dependency graph has cycles.

        Args:
            tasks: List of task IDs
            dependencies: Dependency map

        Returns:
            True if cycles exist
        """
        visited = set()
        rec_stack = set()

        def visit(task_id: UUID) -> bool:
            visited.add(task_id)
            rec_stack.add(task_id)

            for dep_id in dependencies.get(task_id, []):
                if dep_id not in visited:
                    if visit(dep_id):
                        return True
                elif dep_id in rec_stack:
                    return True

            rec_stack.remove(task_id)
            return False

        for task_id in tasks:
            if task_id not in visited:
                if visit(task_id):
                    return True

        return False

    def _topological_sort(
        self,
        tasks: List[UUID],
        dependencies: Dict[UUID, List[UUID]],
    ) -> List[UUID]:
        """Perform topological sort on tasks.

        Args:
            tasks: List of task IDs
            dependencies: Dependency map

        Returns:
            Sorted list of task IDs
        """
        # Calculate in-degree for each task
        in_degree = {task_id: 0 for task_id in tasks}

        for task_id, deps in dependencies.items():
            for dep_id in deps:
                if dep_id in in_degree:
                    in_degree[task_id] += 1

        # Kahn's algorithm
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            task_id = queue.pop(0)
            result.append(task_id)

            # Find tasks that depend on this one
            for other_task_id in tasks:
                if task_id in dependencies.get(other_task_id, []):
                    in_degree[other_task_id] -= 1
                    if in_degree[other_task_id] == 0:
                        queue.append(other_task_id)

        return result

    def get_ready_tasks(
        self,
        all_tasks: List[UUID],
        dependencies: Dict[UUID, List[UUID]],
        completed_tasks: Set[UUID],
    ) -> List[UUID]:
        """Get tasks that are ready to execute.

        Args:
            all_tasks: All task IDs
            dependencies: Dependency map
            completed_tasks: Set of completed task IDs

        Returns:
            List of task IDs ready to execute
        """
        ready = []

        for task_id in all_tasks:
            if task_id in completed_tasks:
                continue

            # Check if all dependencies are completed
            deps = dependencies.get(task_id, [])
            if all(dep_id in completed_tasks for dep_id in deps):
                ready.append(task_id)

        logger.debug(
            "Ready tasks identified",
            extra={"num_ready": len(ready)},
        )

        return ready
