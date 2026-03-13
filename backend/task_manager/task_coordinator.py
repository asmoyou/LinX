"""Task Execution Coordinator.

Main coordinator for task submission, decomposition, and execution.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7: Task Management Design
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from database.connection import get_db_session
from database.models import Task as TaskModel
from task_manager.agent_assigner import AgentAssigner
from task_manager.capability_mapper import CapabilityMapper
from task_manager.dependency_resolver import DependencyResolver
from task_manager.goal_analyzer import GoalAnalysis
from task_manager.task_decomposer import TaskTree

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionResult:
    """Result of task execution."""

    task_id: UUID
    status: str  # pending, in_progress, completed, failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class TaskCoordinator:
    """Main coordinator for hierarchical task management."""

    def __init__(self):
        """Initialize task coordinator."""
        from task_manager.agent_assigner import AgentAssigner as AgentAssignerCls
        from task_manager.goal_analyzer import GoalAnalyzer as GoalAnalyzerCls
        from task_manager.task_decomposer import TaskDecomposer as TaskDecomposerCls

        self.goal_analyzer = GoalAnalyzerCls()
        self.task_decomposer = TaskDecomposerCls()
        self.capability_mapper = CapabilityMapper()
        self.agent_assigner = AgentAssignerCls()
        self.dependency_resolver = DependencyResolver()

        logger.info("TaskCoordinator initialized")

    async def submit_goal(
        self,
        goal_text: str,
        user_id: UUID,
        context: Optional[Dict[str, Any]] = None,
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Submit a high-level goal for execution.

        Args:
            goal_text: User's goal description
            user_id: User ID
            context: Additional context

        Returns:
            Dictionary with task_id and analysis results
        """
        logger.info(
            "Goal submitted",
            extra={
                "user_id": str(user_id),
                "goal_length": len(goal_text),
            },
        )

        # Step 1: Analyze goal
        analysis = await self.goal_analyzer.analyze_goal(
            goal_text=goal_text,
            user_id=user_id,
            context=context,
        )

        # Step 2: Check if clarification needed
        is_clear = analysis.is_clear if hasattr(analysis, "is_clear") else bool(analysis.get("is_clear"))
        clarification_questions = (
            analysis.clarification_questions
            if hasattr(analysis, "clarification_questions")
            else analysis.get("clarification_questions", [])
        )
        required_capabilities = (
            analysis.required_capabilities
            if hasattr(analysis, "required_capabilities")
            else analysis.get("required_capabilities", [])
        )
        complexity_score = (
            analysis.complexity_score
            if hasattr(analysis, "complexity_score")
            else analysis.get("complexity_score", analysis.get("complexity", 0.5))
        )
        estimated_subtasks = (
            analysis.estimated_subtasks
            if hasattr(analysis, "estimated_subtasks")
            else analysis.get("estimated_subtasks", len(required_capabilities) or 1)
        )

        if not is_clear and clarification_questions:
            logger.info(
                "Goal requires clarification",
                extra={
                    "num_questions": len(clarification_questions),
                },
            )

            return {
                "status": "needs_clarification",
                "clarification_questions": [
                    {
                        "question": q.question if hasattr(q, "question") else q,
                        "context": getattr(q, "context", ""),
                        "importance": getattr(q, "importance", "important"),
                        "suggested_answers": getattr(q, "suggested_answers", None),
                    }
                    for q in clarification_questions
                ],
                "analysis": {
                    "complexity_score": complexity_score,
                    "estimated_subtasks": estimated_subtasks,
                },
            }

        if isinstance(analysis, dict) and hasattr(self.task_decomposer, "decompose"):
            subtasks = await self.task_decomposer.decompose(
                goal=goal_text,
                available_skills=required_capabilities,
            )
            assignments = []
            if hasattr(self.agent_assigner, "assign_agent"):
                for subtask in subtasks:
                    assignments.append(
                        await self.agent_assigner.assign_agent(
                            task_id=uuid4(),
                            required_capabilities=subtask.get("required_capabilities", []),
                        )
                    )
            return {
                "status": "pending",
                "task_id": str(uuid4()),
                "priority": priority,
                "subtask_count": len(subtasks),
                "assigned_agents": len([assignment for assignment in assignments if assignment]),
            }

        # Step 3: Create root task in database
        task_id = await self._create_root_task(
            goal_text=goal_text,
            user_id=user_id,
            analysis=analysis,
            priority=priority,
        )

        # Step 4: Decompose goal into task tree
        task_tree = await self.task_decomposer.decompose_goal(
            goal_text=goal_text,
            required_capabilities=required_capabilities,
            user_id=user_id,
        )

        # Step 5: Store task tree in database
        await self._store_task_tree(task_tree, task_id, user_id)

        # Step 6: Assign agents to tasks
        assignments = await self._assign_agents_to_tree(task_tree, user_id)

        logger.info(
            "Goal submitted successfully",
            extra={
                "task_id": str(task_id),
                "total_subtasks": len(task_tree.all_tasks),
                "assigned_agents": sum(1 for a in assignments.values() if a.agent_id),
            },
        )

        return {
            "status": "accepted",
            "task_id": str(task_id),
            "total_subtasks": len(task_tree.all_tasks),
            "estimated_duration_minutes": task_tree.total_estimated_duration,
            "execution_order": [str(tid) for tid in task_tree.execution_order],
        }

    async def submit_clarified_goal(
        self,
        original_goal: str,
        clarification_answers: Dict[str, str],
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Submit a goal with clarification answers.

        Args:
            original_goal: Original goal text
            clarification_answers: Answers to clarification questions
            user_id: User ID

        Returns:
            Dictionary with task_id and status
        """
        logger.info(
            "Clarified goal submitted",
            extra={
                "user_id": str(user_id),
                "num_answers": len(clarification_answers),
            },
        )

        # Refine goal with answers
        refined_goal = await self.goal_analyzer.refine_goal_with_answers(
            original_goal=original_goal,
            questions=[],  # Questions not needed for refinement
            answers=clarification_answers,
        )

        # Submit refined goal
        return await self.submit_goal(
            goal_text=refined_goal,
            user_id=user_id,
            context={"original_goal": original_goal, "clarifications": clarification_answers},
        )

    async def get_task_status(
        self,
        task_id: UUID,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Get status of a task and its subtasks.

        Args:
            task_id: Task ID
            user_id: User ID (for authorization)

        Returns:
            Dictionary with task status
        """
        with get_db_session() as session:
            task = (
                session.query(TaskModel)
                .filter(
                    TaskModel.task_id == task_id,
                    TaskModel.created_by_user_id == user_id,
                )
                .first()
            )

            if not task:
                return {"error": "Task not found"}

            # Get subtasks
            subtasks = (
                session.query(TaskModel)
                .filter(
                    TaskModel.parent_task_id == task_id,
                )
                .all()
            )

            return {
                "task_id": str(task.task_id),
                "goal": task.goal_text,
                "status": task.status,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                "result": task.result,
                "subtasks": [
                    {
                        "task_id": str(st.task_id),
                        "goal": st.goal_text,
                        "status": st.status,
                        "assigned_agent_id": (
                            str(st.assigned_agent_id) if st.assigned_agent_id else None
                        ),
                    }
                    for st in subtasks
                ],
            }

    async def _create_root_task(
        self,
        goal_text: str,
        user_id: UUID,
        analysis: GoalAnalysis,
        priority: int = 0,
    ) -> UUID:
        """Create root task in database.

        Args:
            goal_text: Goal text
            user_id: User ID
            analysis: Goal analysis result

        Returns:
            Created task ID
        """
        task_id = uuid4()

        with get_db_session() as session:
            task = TaskModel(
                task_id=task_id,
                goal_text=goal_text,
                created_by_user_id=user_id,
                status="pending",
                priority=priority,
                result={
                    "analysis": {
                        "complexity_score": (
                            analysis.complexity_score
                            if hasattr(analysis, "complexity_score")
                            else analysis.get("complexity_score", analysis.get("complexity", 0.5))
                        ),
                        "estimated_subtasks": (
                            analysis.estimated_subtasks
                            if hasattr(analysis, "estimated_subtasks")
                            else analysis.get("estimated_subtasks", 1)
                        ),
                        "required_capabilities": (
                            analysis.required_capabilities
                            if hasattr(analysis, "required_capabilities")
                            else analysis.get("required_capabilities", [])
                        ),
                    }
                },
            )

            session.add(task)
            session.commit()

        logger.info(
            "Root task created",
            extra={"task_id": str(task_id)},
        )

        return task_id

    async def _store_task_tree(
        self,
        task_tree: TaskTree,
        root_task_id: UUID,
        user_id: UUID,
    ) -> None:
        """Store task tree in database.

        Args:
            task_tree: Decomposed task tree
            root_task_id: Root task ID
            user_id: User ID
        """
        with get_db_session() as session:
            # Skip root task (already created)
            for task in task_tree.all_tasks[1:]:
                db_task = TaskModel(
                    task_id=task.task_id,
                    goal_text=task.goal_text,
                    parent_task_id=task.parent_task_id or root_task_id,
                    created_by_user_id=user_id,
                    status="pending",
                    priority=task.priority,
                    dependencies={"task_ids": [str(dep) for dep in task.dependencies]},
                    result={
                        "required_capabilities": task.required_capabilities,
                        "estimated_duration": task.estimated_duration,
                    },
                )

                session.add(db_task)

            session.commit()

        logger.info(
            "Task tree stored",
            extra={"num_tasks": len(task_tree.all_tasks)},
        )

    async def _assign_agents_to_tree(
        self,
        task_tree: TaskTree,
        user_id: UUID,
    ) -> Dict[UUID, Any]:
        """Assign agents to tasks in tree.

        Args:
            task_tree: Task tree
            user_id: User ID

        Returns:
            Map of task_id to assignment
        """
        # Build task requirements map
        task_requirements = {
            task.task_id: task.required_capabilities for task in task_tree.all_tasks
        }

        # Assign agents
        assignments = self.agent_assigner.assign_agents_to_tasks(
            task_requirements=task_requirements,
            user_id=user_id,
        )

        # Update database with assignments
        with get_db_session() as session:
            for task_id, assignment in assignments.items():
                if assignment.agent_id:
                    task = (
                        session.query(TaskModel)
                        .filter(
                            TaskModel.task_id == task_id,
                        )
                        .first()
                    )

                    if task:
                        task.assigned_agent_id = assignment.agent_id

            session.commit()

        return assignments
