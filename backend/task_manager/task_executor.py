"""Task Execution Engine.

Implements sequential, parallel, and collaborative task execution strategies.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.2: Task Execution Flow
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from uuid import UUID
from enum import Enum

from database.connection import get_db_session
from database.models import Task as TaskModel, Agent
from agent_framework import BaseAgent

logger = logging.getLogger(__name__)


class ExecutionStrategy(Enum):
    """Task execution strategy."""
    
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    COLLABORATIVE = "collaborative"


@dataclass
class TaskExecutionContext:
    """Context for task execution."""
    
    task_id: UUID
    agent_id: UUID
    timeout_seconds: int = 300  # 5 minutes default
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = None


@dataclass
class ExecutionResult:
    """Result of task execution."""
    
    task_id: UUID
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time_seconds: float = 0.0
    retry_count: int = 0


class TaskExecutor:
    """Executes tasks using different strategies."""
    
    def __init__(self):
        """Initialize task executor."""
        self._active_executions: Dict[UUID, asyncio.Task] = {}
        
        logger.info("TaskExecutor initialized")
    
    async def execute_sequential(
        self,
        task_ids: List[UUID],
        user_id: UUID,
    ) -> List[ExecutionResult]:
        """Execute tasks sequentially in order.
        
        Args:
            task_ids: List of task IDs to execute
            user_id: User ID for authorization
        
        Returns:
            List of execution results
        """
        logger.info(
            "Starting sequential execution",
            extra={
                "num_tasks": len(task_ids),
                "user_id": str(user_id),
            },
        )
        
        results = []
        
        for task_id in task_ids:
            result = await self._execute_single_task(task_id, user_id)
            results.append(result)
            
            # Stop if task failed
            if not result.success:
                logger.warning(
                    "Sequential execution stopped due to failure",
                    extra={"failed_task_id": str(task_id)},
                )
                break
        
        logger.info(
            "Sequential execution complete",
            extra={
                "total_tasks": len(task_ids),
                "executed": len(results),
                "successful": sum(1 for r in results if r.success),
            },
        )
        
        return results
    
    async def execute_parallel(
        self,
        task_ids: List[UUID],
        user_id: UUID,
        max_concurrent: int = 5,
    ) -> List[ExecutionResult]:
        """Execute tasks in parallel with concurrency limit.
        
        Args:
            task_ids: List of task IDs to execute
            user_id: User ID for authorization
            max_concurrent: Maximum concurrent executions
        
        Returns:
            List of execution results
        """
        logger.info(
            "Starting parallel execution",
            extra={
                "num_tasks": len(task_ids),
                "max_concurrent": max_concurrent,
                "user_id": str(user_id),
            },
        )
        
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def execute_with_semaphore(task_id: UUID) -> ExecutionResult:
            async with semaphore:
                return await self._execute_single_task(task_id, user_id)
        
        # Execute all tasks concurrently
        tasks = [execute_with_semaphore(task_id) for task_id in task_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "Task execution raised exception",
                    extra={"task_id": str(task_ids[i]), "error": str(result)},
                )
                processed_results.append(
                    ExecutionResult(
                        task_id=task_ids[i],
                        success=False,
                        error=str(result),
                    )
                )
            else:
                processed_results.append(result)
        
        logger.info(
            "Parallel execution complete",
            extra={
                "total_tasks": len(task_ids),
                "successful": sum(1 for r in processed_results if r.success),
            },
        )
        
        return processed_results
    
    async def execute_collaborative(
        self,
        task_ids: List[UUID],
        user_id: UUID,
    ) -> List[ExecutionResult]:
        """Execute tasks collaboratively with shared context.
        
        Args:
            task_ids: List of task IDs to execute
            user_id: User ID for authorization
        
        Returns:
            List of execution results
        """
        logger.info(
            "Starting collaborative execution",
            extra={
                "num_tasks": len(task_ids),
                "user_id": str(user_id),
            },
        )
        
        # Execute tasks in parallel with shared context
        # Agents can communicate via message bus and shared memory
        results = await self.execute_parallel(
            task_ids=task_ids,
            user_id=user_id,
            max_concurrent=len(task_ids),  # All tasks run concurrently
        )
        
        logger.info(
            "Collaborative execution complete",
            extra={
                "total_tasks": len(task_ids),
                "successful": sum(1 for r in results if r.success),
            },
        )
        
        return results
    
    async def _execute_single_task(
        self,
        task_id: UUID,
        user_id: UUID,
    ) -> ExecutionResult:
        """Execute a single task.
        
        Args:
            task_id: Task ID
            user_id: User ID
        
        Returns:
            Execution result
        """
        start_time = datetime.utcnow()
        
        logger.info(
            "Executing task",
            extra={"task_id": str(task_id)},
        )
        
        # Get task from database
        with get_db_session() as session:
            task = session.query(TaskModel).filter(
                TaskModel.task_id == task_id,
                TaskModel.created_by_user_id == user_id,
            ).first()
            
            if not task:
                return ExecutionResult(
                    task_id=task_id,
                    success=False,
                    error="Task not found",
                )
            
            if not task.assigned_agent_id:
                return ExecutionResult(
                    task_id=task_id,
                    success=False,
                    error="No agent assigned to task",
                )
            
            # Update task status
            task.status = "in_progress"
            session.commit()
            
            agent_id = task.assigned_agent_id
            goal_text = task.goal_text
        
        # Execute task with timeout and retry
        context = TaskExecutionContext(
            task_id=task_id,
            agent_id=agent_id,
            timeout_seconds=300,
            max_retries=3,
        )
        
        result = await self._execute_with_retry(goal_text, context)
        
        # Update task in database
        with get_db_session() as session:
            task = session.query(TaskModel).filter(
                TaskModel.task_id == task_id,
            ).first()
            
            if task:
                if result.success:
                    task.status = "completed"
                    task.completed_at = datetime.utcnow()
                    task.result = result.result
                else:
                    task.status = "failed"
                    task.result = {"error": result.error}
                
                session.commit()
        
        execution_time = (datetime.utcnow() - start_time).total_seconds()
        result.execution_time_seconds = execution_time
        
        logger.info(
            "Task execution complete",
            extra={
                "task_id": str(task_id),
                "success": result.success,
                "execution_time": execution_time,
            },
        )
        
        return result
    
    async def _execute_with_retry(
        self,
        goal_text: str,
        context: TaskExecutionContext,
    ) -> ExecutionResult:
        """Execute task with retry logic.
        
        Args:
            goal_text: Task goal
            context: Execution context
        
        Returns:
            Execution result
        """
        last_error = None
        
        for attempt in range(context.max_retries):
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    self._execute_task_logic(goal_text, context),
                    timeout=context.timeout_seconds,
                )
                
                return ExecutionResult(
                    task_id=context.task_id,
                    success=True,
                    result=result,
                    retry_count=attempt,
                )
                
            except asyncio.TimeoutError:
                last_error = f"Task timeout after {context.timeout_seconds} seconds"
                logger.warning(
                    "Task execution timeout",
                    extra={
                        "task_id": str(context.task_id),
                        "attempt": attempt + 1,
                    },
                )
                
            except Exception as e:
                last_error = str(e)
                logger.error(
                    "Task execution error",
                    extra={
                        "task_id": str(context.task_id),
                        "attempt": attempt + 1,
                        "error": str(e),
                    },
                )
            
            # Wait before retry (exponential backoff)
            if attempt < context.max_retries - 1:
                wait_time = 2 ** attempt
                await asyncio.sleep(wait_time)
        
        return ExecutionResult(
            task_id=context.task_id,
            success=False,
            error=last_error,
            retry_count=context.max_retries,
        )
    
    async def _execute_task_logic(
        self,
        goal_text: str,
        context: TaskExecutionContext,
    ) -> Dict[str, Any]:
        """Execute the actual task logic.
        
        Args:
            goal_text: Task goal
            context: Execution context
        
        Returns:
            Task result
        """
        # This is a placeholder for actual agent execution
        # In a real implementation, this would:
        # 1. Get the agent instance
        # 2. Execute the agent with the goal
        # 3. Return the agent's result
        
        logger.debug(
            "Executing task logic",
            extra={
                "task_id": str(context.task_id),
                "agent_id": str(context.agent_id),
            },
        )
        
        # Simulate task execution
        await asyncio.sleep(0.1)
        
        return {
            "status": "completed",
            "output": f"Task completed: {goal_text}",
            "agent_id": str(context.agent_id),
        }
    
    def cancel_task(self, task_id: UUID) -> bool:
        """Cancel a running task.
        
        Args:
            task_id: Task ID to cancel
        
        Returns:
            True if task was cancelled
        """
        if task_id in self._active_executions:
            task = self._active_executions[task_id]
            task.cancel()
            del self._active_executions[task_id]
            
            logger.info(
                "Task cancelled",
                extra={"task_id": str(task_id)},
            )
            
            return True
        
        return False
    
    def get_active_executions(self) -> List[UUID]:
        """Get list of currently executing tasks.
        
        Returns:
            List of task IDs
        """
        return list(self._active_executions.keys())
