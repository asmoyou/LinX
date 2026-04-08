"""Project execution load balancer helpers.

This module is a project_execution-local copy of the legacy task_manager load
balancer so project execution scheduling no longer imports task_manager.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import Task as TaskModel
from shared.datetime_utils import utcnow

logger = logging.getLogger(__name__)


@dataclass
class AgentLoad:
    agent_id: UUID
    active_tasks: int
    total_completed: int
    avg_execution_time: float
    last_task_completed: Optional[datetime]
    load_score: float


class LoadBalancer:
    """Balances task distribution across agents."""

    def __init__(self, max_tasks_per_agent: int = 5):
        self.max_tasks_per_agent = max_tasks_per_agent
        self._agent_loads: Dict[UUID, AgentLoad] = {}
        logger.info(
            "ProjectExecution LoadBalancer initialized",
            extra={"max_tasks_per_agent": max_tasks_per_agent},
        )

    def select_agent(
        self,
        available_agents: List[UUID],
        user_id: UUID,
    ) -> Optional[UUID]:
        if not available_agents:
            return None

        self._update_agent_loads(available_agents, user_id)
        available = [
            agent_id
            for agent_id in available_agents
            if self._agent_loads.get(
                agent_id,
                AgentLoad(
                    agent_id=agent_id,
                    active_tasks=0,
                    total_completed=0,
                    avg_execution_time=0.0,
                    last_task_completed=None,
                    load_score=0.0,
                ),
            ).active_tasks
            < self.max_tasks_per_agent
        ]
        if not available:
            return None

        return min(
            available,
            key=lambda aid: self._agent_loads.get(
                aid,
                AgentLoad(
                    agent_id=aid,
                    active_tasks=0,
                    total_completed=0,
                    avg_execution_time=0.0,
                    last_task_completed=None,
                    load_score=0.0,
                ),
            ).load_score,
        )

    def _update_agent_loads(
        self,
        agent_ids: List[UUID],
        user_id: UUID,
    ) -> None:
        with get_db_session() as session:
            for agent_id in agent_ids:
                active_tasks = (
                    session.query(TaskModel)
                    .filter(
                        TaskModel.assigned_agent_id == agent_id,
                        TaskModel.status.in_(["pending", "in_progress"]),
                    )
                    .count()
                )
                completed_tasks = (
                    session.query(TaskModel)
                    .filter(
                        TaskModel.assigned_agent_id == agent_id,
                        TaskModel.status == "completed",
                    )
                    .all()
                )
                total_completed = len(completed_tasks)
                avg_time = 0.0
                last_completed = None
                if completed_tasks:
                    execution_times = [
                        (task.completed_at - task.created_at).total_seconds()
                        for task in completed_tasks
                        if task.completed_at and task.created_at
                    ]
                    if execution_times:
                        avg_time = sum(execution_times) / len(execution_times)
                    last_completed = max(
                        (task.completed_at for task in completed_tasks if task.completed_at),
                        default=None,
                    )
                self._agent_loads[agent_id] = AgentLoad(
                    agent_id=agent_id,
                    active_tasks=active_tasks,
                    total_completed=total_completed,
                    avg_execution_time=avg_time,
                    last_task_completed=last_completed,
                    load_score=self._calculate_load_score(
                        active_tasks=active_tasks,
                        avg_execution_time=avg_time,
                        last_completed=last_completed,
                    ),
                )

    def _calculate_load_score(
        self,
        active_tasks: int,
        avg_execution_time: float,
        last_completed: Optional[datetime],
    ) -> float:
        task_score = min(1.0, active_tasks / self.max_tasks_per_agent)
        time_penalty = 0.0
        if avg_execution_time > 300:
            time_penalty = min(0.3, (avg_execution_time - 300) / 1000)
        recency_bonus = 0.0
        if last_completed:
            time_since = (utcnow() - last_completed).total_seconds()
            if time_since < 300:
                recency_bonus = -0.1
        return max(0.0, min(1.0, task_score + time_penalty + recency_bonus))

    def get_agent_load(self, agent_id: UUID) -> Optional[AgentLoad]:
        return self._agent_loads.get(agent_id)

    def get_all_loads(self) -> Dict[UUID, AgentLoad]:
        return self._agent_loads.copy()
