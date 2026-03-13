"""Task Progress Tracking.

Tracks and reports task execution progress.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.2: Task Execution Flow
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import Task as TaskModel
from shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)


class _AwaitableResult:
    """Tiny awaitable wrapper for backward-compatible async test helpers."""

    def __init__(self, value):
        self.value = value

    def __await__(self):
        async def _resolve():
            return self.value

        return _resolve().__await__()


@dataclass
class TaskProgress:
    """Progress information for a task."""

    task_id: UUID
    status: str
    progress_percentage: float  # 0.0 to 100.0
    started_at: Optional[datetime]
    estimated_completion: Optional[datetime]
    subtasks_completed: int
    subtasks_total: int
    current_step: Optional[str]


class ProgressTracker:
    """Tracks task execution progress."""

    def __init__(self):
        """Initialize progress tracker."""
        self._progress_cache: Dict[UUID, TaskProgress] = {}

        logger.info("ProgressTracker initialized")

    async def initialize_task(self, task_id: UUID, total_steps: int) -> Dict[str, int]:
        """Backward-compatible async initializer."""
        self._progress_cache[task_id] = TaskProgress(
            task_id=task_id,
            status="in_progress",
            progress_percentage=0.0,
            started_at=utcnow(),
            estimated_completion=None,
            subtasks_completed=0,
            subtasks_total=total_steps,
            current_step=None,
        )
        return {"task_id": str(task_id), "total_steps": total_steps}

    def update_progress(
        self,
        task_id: UUID,
        progress_percentage: Optional[float] = None,
        current_step: Optional[str] = None,
        completed_steps: Optional[int] = None,
    ):
        """Update task progress.

        Args:
            task_id: Task ID
            progress_percentage: Progress from 0.0 to 100.0
            current_step: Current execution step
        """
        if task_id in self._progress_cache:
            progress = self._progress_cache[task_id]
            if completed_steps is not None and progress.subtasks_total:
                progress.subtasks_completed = completed_steps
                progress_percentage = (completed_steps / progress.subtasks_total) * 100.0
            progress.progress_percentage = progress_percentage or 0.0
            progress.current_step = current_step
            if progress.progress_percentage >= 100.0:
                progress.status = "completed"
        else:
            progress = TaskProgress(
                task_id=task_id,
                status="in_progress",
                progress_percentage=progress_percentage or 0.0,
                started_at=utcnow(),
                estimated_completion=None,
                subtasks_completed=completed_steps or 0,
                subtasks_total=completed_steps or 0,
                current_step=current_step,
            )
            self._progress_cache[task_id] = progress

        logger.debug(
            "Progress updated",
            extra={
                "task_id": str(task_id),
                "progress": progress.progress_percentage,
            },
        )
        return _AwaitableResult(None)

    def get_progress(
        self,
        task_id: UUID,
        user_id: Optional[UUID] = None,
    ):
        """Get progress for a task.

        Args:
            task_id: Task ID
            user_id: User ID for authorization

        Returns:
            TaskProgress or None
        """
        # Check cache first
        if task_id in self._progress_cache:
            cached = self._progress_cache[task_id]
            if user_id is None:
                return _AwaitableResult(
                    {
                        "percentage": round(cached.progress_percentage),
                        "status": cached.status,
                    }
                )
            return cached

        # Calculate from database
        from database.connection import get_db_session as get_db_session_fn

        with get_db_session_fn() as session:
            task = (
                session.query(TaskModel)
                .filter(
                    TaskModel.task_id == task_id,
                    TaskModel.created_by_user_id == user_id,
                )
                .first()
            )

            if not task:
                return None

            # Get subtasks
            subtasks = (
                session.query(TaskModel)
                .filter(
                    TaskModel.parent_task_id == task_id,
                )
                .all()
            )

            subtasks_total = len(subtasks)
            subtasks_completed = sum(1 for st in subtasks if st.status == "completed")

            # Calculate progress
            if subtasks_total > 0:
                progress_pct = (subtasks_completed / subtasks_total) * 100.0
            elif task.status == "completed":
                progress_pct = 100.0
            elif task.status == "in_progress":
                progress_pct = 50.0
            else:
                progress_pct = 0.0

            progress = TaskProgress(
                task_id=task_id,
                status=task.status,
                progress_percentage=progress_pct,
                started_at=task.created_at,
                estimated_completion=None,
                subtasks_completed=subtasks_completed,
                subtasks_total=subtasks_total,
                current_step=None,
            )

            self._progress_cache[task_id] = progress
            if user_id is None:
                return _AwaitableResult(
                    {
                        "percentage": round(progress.progress_percentage),
                        "status": progress.status,
                    }
                )
            return progress

    def get_tree_progress(
        self,
        root_task_id: UUID,
        user_id: UUID,
    ) -> Dict[UUID, TaskProgress]:
        """Get progress for entire task tree.

        Args:
            root_task_id: Root task ID
            user_id: User ID

        Returns:
            Dictionary of task_id to TaskProgress
        """
        progress_map = {}

        with get_db_session() as session:
            # Get all tasks in tree
            tasks = (
                session.query(TaskModel)
                .filter(
                    TaskModel.created_by_user_id == user_id,
                )
                .all()
            )

            # Build tree
            task_map = {task.task_id: task for task in tasks}

            def collect_tree(task_id: UUID):
                if task_id not in task_map:
                    return

                progress = self.get_progress(task_id, user_id)
                if progress:
                    progress_map[task_id] = progress

                # Collect subtasks
                for task in tasks:
                    if task.parent_task_id == task_id:
                        collect_tree(task.task_id)

            collect_tree(root_task_id)

        return progress_map
