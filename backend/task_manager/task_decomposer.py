"""Task Decomposition Algorithm.

This module decomposes high-level goals into hierarchical task structures.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.1: Task Decomposition Algorithm
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from llm_providers.base import BaseLLMProvider
from llm_providers.router import get_llm_provider

logger = logging.getLogger(__name__)


@dataclass
class DecomposedTask:
    """A task in the decomposed task tree."""

    task_id: UUID
    goal_text: str
    required_capabilities: List[str]
    priority: int = 0
    parent_task_id: Optional[UUID] = None
    dependencies: List[UUID] = field(default_factory=list)
    estimated_duration: Optional[int] = None  # minutes
    metadata: Dict[str, Any] = field(default_factory=dict)
    subtasks: List["DecomposedTask"] = field(default_factory=list)


@dataclass
class TaskTree:
    """Complete hierarchical task structure."""

    root_task: DecomposedTask
    all_tasks: List[DecomposedTask]
    execution_order: List[UUID]  # Topologically sorted task IDs
    total_estimated_duration: int  # minutes


class TaskDecomposer:
    """Decomposes goals into hierarchical task structures."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        """Initialize the task decomposer.

        Args:
            llm_provider: LLM provider for decomposition (uses default if None)
        """
        self.llm_provider = llm_provider or get_llm_provider()

        logger.info("TaskDecomposer initialized")

    async def decompose_goal(
        self,
        goal_text: str,
        required_capabilities: List[str],
        user_id: UUID,
        max_depth: int = 3,
    ) -> TaskTree:
        """Decompose a goal into a hierarchical task tree.

        Args:
            goal_text: The goal to decompose
            required_capabilities: Capabilities identified by goal analyzer
            user_id: User ID for context
            max_depth: Maximum depth of task tree

        Returns:
            TaskTree with hierarchical structure
        """
        logger.info(
            "Decomposing goal",
            extra={
                "user_id": str(user_id),
                "goal_length": len(goal_text),
                "max_depth": max_depth,
            },
        )

        # Create root task
        root_task = DecomposedTask(
            task_id=uuid4(),
            goal_text=goal_text,
            required_capabilities=required_capabilities,
            priority=0,
        )

        # Decompose recursively
        await self._decompose_recursive(root_task, depth=0, max_depth=max_depth)

        # Collect all tasks
        all_tasks = self._collect_all_tasks(root_task)

        # Determine execution order
        execution_order = self._topological_sort(all_tasks)

        # Calculate total duration
        total_duration = sum(task.estimated_duration or 30 for task in all_tasks)

        task_tree = TaskTree(
            root_task=root_task,
            all_tasks=all_tasks,
            execution_order=execution_order,
            total_estimated_duration=total_duration,
        )

        logger.info(
            "Goal decomposition complete",
            extra={
                "total_tasks": len(all_tasks),
                "max_depth_reached": self._get_max_depth(root_task),
                "estimated_duration_minutes": total_duration,
            },
        )

        return task_tree

    async def _decompose_recursive(
        self,
        task: DecomposedTask,
        depth: int,
        max_depth: int,
    ) -> None:
        """Recursively decompose a task into subtasks.

        Args:
            task: Task to decompose
            depth: Current depth in tree
            max_depth: Maximum allowed depth
        """
        # Stop if max depth reached or task is simple enough
        if depth >= max_depth or self._is_atomic_task(task.goal_text):
            logger.debug(
                "Task is atomic or max depth reached",
                extra={"task_id": str(task.task_id), "depth": depth},
            )
            return

        # Build decomposition prompt
        prompt = self._build_decomposition_prompt(task)

        try:
            # Call LLM for decomposition
            response = await self.llm_provider.generate(
                prompt=prompt,
                temperature=0.4,
                max_tokens=1500,
            )

            # Parse subtasks from response
            subtasks = self._parse_subtasks(response, task.task_id)

            if not subtasks:
                logger.debug(
                    "No subtasks generated",
                    extra={"task_id": str(task.task_id)},
                )
                return

            task.subtasks = subtasks

            # Recursively decompose subtasks
            for subtask in subtasks:
                await self._decompose_recursive(subtask, depth + 1, max_depth)

        except Exception as e:
            logger.error(
                "Task decomposition failed",
                extra={"error": str(e), "task_id": str(task.task_id)},
            )
            # Continue without subtasks

    def _build_decomposition_prompt(self, task: DecomposedTask) -> str:
        """Build LLM prompt for task decomposition.

        Args:
            task: Task to decompose

        Returns:
            Formatted prompt string
        """
        capabilities_str = ", ".join(task.required_capabilities)

        prompt = f"""Decompose the following task into smaller, actionable subtasks.

Task: "{task.goal_text}"
Required Capabilities: {capabilities_str}

Please break this down into 2-5 subtasks that:
1. Are specific and actionable
2. Can be executed independently or with clear dependencies
3. Together accomplish the main task

Respond in JSON format:
{{
    "subtasks": [
        {{
            "goal": "specific subtask description",
            "capabilities": ["capability1", "capability2"],
            "priority": 0-10,
            "dependencies": [],
            "estimated_duration_minutes": integer
        }}
    ]
}}"""

        return prompt

    def _parse_subtasks(
        self,
        response: str,
        parent_task_id: UUID,
    ) -> List[DecomposedTask]:
        """Parse LLM response into subtasks.

        Args:
            response: LLM response text
            parent_task_id: Parent task ID

        Returns:
            List of DecomposedTask objects
        """
        import json

        try:
            data = json.loads(response)
            subtasks = []

            for idx, subtask_data in enumerate(data.get("subtasks", [])):
                subtask = DecomposedTask(
                    task_id=uuid4(),
                    goal_text=subtask_data.get("goal", ""),
                    required_capabilities=subtask_data.get("capabilities", ["general"]),
                    priority=subtask_data.get("priority", idx),
                    parent_task_id=parent_task_id,
                    dependencies=[],  # Will be resolved later
                    estimated_duration=subtask_data.get("estimated_duration_minutes", 30),
                )
                subtasks.append(subtask)

            return subtasks

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(
                "Failed to parse subtasks",
                extra={"error": str(e)},
            )
            return []

    def _is_atomic_task(self, goal_text: str) -> bool:
        """Check if a task is atomic (cannot be decomposed further).

        Args:
            goal_text: Task goal text

        Returns:
            True if task is atomic
        """
        # Simple heuristic: short single-action tasks are likely atomic.
        word_count = len(goal_text.split())
        goal_lower = goal_text.lower()

        # Multi-step connectors usually indicate decomposable tasks.
        multi_step_connectors = [" and ", " then ", " after ", " before ", " followed by "]
        if any(connector in goal_lower for connector in multi_step_connectors):
            return False

        # Tasks with very specific action verbs are likely atomic.
        atomic_verbs = [
            "fetch",
            "retrieve",
            "read",
            "write",
            "save",
            "send",
            "receive",
            "calculate",
            "format",
            "validate",
        ]

        has_atomic_verb = any(verb in goal_lower for verb in atomic_verbs)

        if word_count <= 3:
            return True

        return word_count <= 8 and has_atomic_verb

    def _collect_all_tasks(self, root_task: DecomposedTask) -> List[DecomposedTask]:
        """Collect all tasks from tree into flat list.

        Args:
            root_task: Root of task tree

        Returns:
            Flat list of all tasks
        """
        all_tasks = [root_task]

        def collect_recursive(task: DecomposedTask):
            for subtask in task.subtasks:
                all_tasks.append(subtask)
                collect_recursive(subtask)

        collect_recursive(root_task)
        return all_tasks

    def _topological_sort(self, tasks: List[DecomposedTask]) -> List[UUID]:
        """Sort tasks by dependencies (topological sort).

        Args:
            tasks: List of all tasks

        Returns:
            List of task IDs in execution order
        """
        # Build adjacency list
        task_map = {task.task_id: task for task in tasks}
        in_degree = {task.task_id: 0 for task in tasks}

        # Count dependencies
        for task in tasks:
            for dep_id in task.dependencies:
                if dep_id in in_degree:
                    in_degree[task.task_id] += 1

        # Kahn's algorithm
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        result = []

        while queue:
            task_id = queue.pop(0)
            result.append(task_id)

            # Find tasks that depend on this one
            for task in tasks:
                if task_id in task.dependencies:
                    in_degree[task.task_id] -= 1
                    if in_degree[task.task_id] == 0:
                        queue.append(task.task_id)

        # If not all tasks processed, there's a cycle
        if len(result) != len(tasks):
            logger.warning(
                "Circular dependency detected in task tree",
                extra={"processed": len(result), "total": len(tasks)},
            )
            # Return all tasks in original order
            return [task.task_id for task in tasks]

        return result

    def _get_max_depth(self, root_task: DecomposedTask) -> int:
        """Get maximum depth of task tree.

        Args:
            root_task: Root of task tree

        Returns:
            Maximum depth
        """
        if not root_task.subtasks:
            return 0

        return 1 + max(self._get_max_depth(subtask) for subtask in root_task.subtasks)
