"""Task Queue Management.

Manages task queues for execution scheduling.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.2: Task Execution Flow
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set
from uuid import UUID

logger = logging.getLogger(__name__)


class TaskPriority(Enum):
    """Task priority levels."""

    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 15


@dataclass
class QueuedTask:
    """A task in the queue."""

    task_id: UUID
    priority: int
    queued_at: datetime
    dependencies: List[UUID] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def __lt__(self, other):
        """Compare tasks for priority queue."""
        # Higher priority first, then earlier queued_at
        if self.priority != other.priority:
            return self.priority > other.priority
        return self.queued_at < other.queued_at


class TaskQueue:
    """Manages task execution queue."""

    def __init__(self, max_size: int = 1000):
        """Initialize task queue.

        Args:
            max_size: Maximum queue size
        """
        self.max_size = max_size
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._pending_tasks: Dict[UUID, QueuedTask] = {}
        self._completed_tasks: Set[UUID] = set()
        self._failed_tasks: Set[UUID] = set()

        logger.info(
            "TaskQueue initialized",
            extra={"max_size": max_size},
        )

    async def enqueue(
        self,
        task_id: UUID,
        priority: int = TaskPriority.NORMAL.value,
        dependencies: Optional[List[UUID]] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Add a task to the queue.

        Args:
            task_id: Task ID
            priority: Task priority
            dependencies: List of dependency task IDs
            metadata: Additional metadata

        Returns:
            True if task was enqueued
        """
        if task_id in self._pending_tasks:
            logger.warning(
                "Task already in queue",
                extra={"task_id": str(task_id)},
            )
            return False

        if self._queue.full():
            logger.error(
                "Task queue is full",
                extra={"max_size": self.max_size},
            )
            return False

        queued_task = QueuedTask(
            task_id=task_id,
            priority=priority,
            queued_at=datetime.utcnow(),
            dependencies=dependencies or [],
            metadata=metadata or {},
        )

        self._pending_tasks[task_id] = queued_task

        # Only add to queue if dependencies are met
        if self._are_dependencies_met(queued_task):
            await self._queue.put((priority, queued_task))

            logger.info(
                "Task enqueued",
                extra={
                    "task_id": str(task_id),
                    "priority": priority,
                    "queue_size": self._queue.qsize(),
                },
            )
        else:
            logger.info(
                "Task pending dependencies",
                extra={
                    "task_id": str(task_id),
                    "dependencies": [str(d) for d in queued_task.dependencies],
                },
            )

        return True

    async def dequeue(self, timeout: Optional[float] = None) -> Optional[QueuedTask]:
        """Remove and return the highest priority task.

        Args:
            timeout: Timeout in seconds (None for blocking)

        Returns:
            QueuedTask or None if timeout
        """
        try:
            if timeout is not None:
                priority, task = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=timeout,
                )
            else:
                priority, task = await self._queue.get()

            logger.info(
                "Task dequeued",
                extra={
                    "task_id": str(task.task_id),
                    "priority": priority,
                    "queue_size": self._queue.qsize(),
                },
            )

            return task

        except asyncio.TimeoutError:
            return None

    def mark_completed(self, task_id: UUID) -> None:
        """Mark a task as completed.

        Args:
            task_id: Task ID
        """
        self._completed_tasks.add(task_id)

        if task_id in self._pending_tasks:
            del self._pending_tasks[task_id]

        # Check if any pending tasks can now be queued
        asyncio.create_task(self._check_pending_tasks())

        logger.info(
            "Task marked completed",
            extra={"task_id": str(task_id)},
        )

    def mark_failed(self, task_id: UUID) -> None:
        """Mark a task as failed.

        Args:
            task_id: Task ID
        """
        self._failed_tasks.add(task_id)

        if task_id in self._pending_tasks:
            del self._pending_tasks[task_id]

        logger.info(
            "Task marked failed",
            extra={"task_id": str(task_id)},
        )

    async def _check_pending_tasks(self) -> None:
        """Check pending tasks and queue those with met dependencies."""
        tasks_to_queue = []

        for task_id, task in list(self._pending_tasks.items()):
            if self._are_dependencies_met(task):
                tasks_to_queue.append(task)

        for task in tasks_to_queue:
            if not self._queue.full():
                await self._queue.put((task.priority, task))

                logger.info(
                    "Pending task now ready",
                    extra={"task_id": str(task.task_id)},
                )

    def _are_dependencies_met(self, task: QueuedTask) -> bool:
        """Check if task dependencies are met.

        Args:
            task: Queued task

        Returns:
            True if all dependencies are completed
        """
        for dep_id in task.dependencies:
            if dep_id not in self._completed_tasks:
                return False
        return True

    def get_queue_size(self) -> int:
        """Get current queue size.

        Returns:
            Number of tasks in queue
        """
        return self._queue.qsize()

    def get_pending_count(self) -> int:
        """Get number of pending tasks.

        Returns:
            Number of pending tasks
        """
        return len(self._pending_tasks)

    def get_completed_count(self) -> int:
        """Get number of completed tasks.

        Returns:
            Number of completed tasks
        """
        return len(self._completed_tasks)

    def get_failed_count(self) -> int:
        """Get number of failed tasks.

        Returns:
            Number of failed tasks
        """
        return len(self._failed_tasks)

    def get_stats(self) -> Dict:
        """Get queue statistics.

        Returns:
            Dictionary with queue stats
        """
        return {
            "queue_size": self.get_queue_size(),
            "pending_count": self.get_pending_count(),
            "completed_count": self.get_completed_count(),
            "failed_count": self.get_failed_count(),
            "max_size": self.max_size,
        }

    def clear(self) -> None:
        """Clear all tasks from queue."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        self._pending_tasks.clear()
        self._completed_tasks.clear()
        self._failed_tasks.clear()

        logger.info("Task queue cleared")
