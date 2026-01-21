"""Load Balancer for Agent Task Distribution.

Distributes tasks across agents based on availability and load.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.2: Task Execution Flow
"""

import logging
from dataclasses import dataclass
from typing import List, Dict, Optional
from uuid import UUID
from datetime import datetime, timedelta

from database.connection import get_db_session
from database.models import Agent, Task as TaskModel

logger = logging.getLogger(__name__)


@dataclass
class AgentLoad:
    """Agent load information."""
    
    agent_id: UUID
    active_tasks: int
    total_completed: int
    avg_execution_time: float  # seconds
    last_task_completed: Optional[datetime]
    load_score: float  # 0.0 to 1.0, higher means more loaded


class LoadBalancer:
    """Balances task distribution across agents."""
    
    def __init__(self, max_tasks_per_agent: int = 5):
        """Initialize load balancer.
        
        Args:
            max_tasks_per_agent: Maximum concurrent tasks per agent
        """
        self.max_tasks_per_agent = max_tasks_per_agent
        self._agent_loads: Dict[UUID, AgentLoad] = {}
        
        logger.info(
            "LoadBalancer initialized",
            extra={"max_tasks_per_agent": max_tasks_per_agent},
        )
    
    def select_agent(
        self,
        available_agents: List[UUID],
        user_id: UUID,
    ) -> Optional[UUID]:
        """Select the best agent for a new task.
        
        Args:
            available_agents: List of available agent IDs
            user_id: User ID for filtering
        
        Returns:
            Selected agent ID or None
        """
        if not available_agents:
            return None
        
        # Update agent loads
        self._update_agent_loads(available_agents, user_id)
        
        # Filter agents that haven't reached max capacity
        available = [
            agent_id for agent_id in available_agents
            if self._agent_loads.get(agent_id, AgentLoad(
                agent_id=agent_id,
                active_tasks=0,
                total_completed=0,
                avg_execution_time=0.0,
                last_task_completed=None,
                load_score=0.0,
            )).active_tasks < self.max_tasks_per_agent
        ]
        
        if not available:
            logger.warning("All agents at max capacity")
            return None
        
        # Select agent with lowest load score
        best_agent = min(
            available,
            key=lambda aid: self._agent_loads.get(aid, AgentLoad(
                agent_id=aid,
                active_tasks=0,
                total_completed=0,
                avg_execution_time=0.0,
                last_task_completed=None,
                load_score=0.0,
            )).load_score,
        )
        
        logger.info(
            "Agent selected for task",
            extra={
                "agent_id": str(best_agent),
                "load_score": self._agent_loads[best_agent].load_score,
            },
        )
        
        return best_agent
    
    def _update_agent_loads(
        self,
        agent_ids: List[UUID],
        user_id: UUID,
    ) -> None:
        """Update load information for agents.
        
        Args:
            agent_ids: List of agent IDs
            user_id: User ID
        """
        with get_db_session() as session:
            for agent_id in agent_ids:
                # Count active tasks
                active_tasks = session.query(TaskModel).filter(
                    TaskModel.assigned_agent_id == agent_id,
                    TaskModel.status.in_(['pending', 'in_progress']),
                ).count()
                
                # Get completed tasks stats
                completed_tasks = session.query(TaskModel).filter(
                    TaskModel.assigned_agent_id == agent_id,
                    TaskModel.status == 'completed',
                ).all()
                
                total_completed = len(completed_tasks)
                
                # Calculate average execution time
                avg_time = 0.0
                last_completed = None
                
                if completed_tasks:
                    execution_times = []
                    for task in completed_tasks:
                        if task.completed_at and task.created_at:
                            exec_time = (task.completed_at - task.created_at).total_seconds()
                            execution_times.append(exec_time)
                    
                    if execution_times:
                        avg_time = sum(execution_times) / len(execution_times)
                    
                    last_completed = max(
                        (task.completed_at for task in completed_tasks if task.completed_at),
                        default=None,
                    )
                
                # Calculate load score (0.0 to 1.0)
                load_score = self._calculate_load_score(
                    active_tasks=active_tasks,
                    avg_execution_time=avg_time,
                    last_completed=last_completed,
                )
                
                self._agent_loads[agent_id] = AgentLoad(
                    agent_id=agent_id,
                    active_tasks=active_tasks,
                    total_completed=total_completed,
                    avg_execution_time=avg_time,
                    last_task_completed=last_completed,
                    load_score=load_score,
                )
    
    def _calculate_load_score(
        self,
        active_tasks: int,
        avg_execution_time: float,
        last_completed: Optional[datetime],
    ) -> float:
        """Calculate agent load score.
        
        Args:
            active_tasks: Number of active tasks
            avg_execution_time: Average execution time
            last_completed: Last task completion time
        
        Returns:
            Load score from 0.0 to 1.0
        """
        # Base score from active tasks
        task_score = min(1.0, active_tasks / self.max_tasks_per_agent)
        
        # Penalty for slow execution
        time_penalty = 0.0
        if avg_execution_time > 300:  # 5 minutes
            time_penalty = min(0.3, (avg_execution_time - 300) / 1000)
        
        # Bonus for recent activity (agent is "warmed up")
        recency_bonus = 0.0
        if last_completed:
            time_since = (datetime.utcnow() - last_completed).total_seconds()
            if time_since < 300:  # Within 5 minutes
                recency_bonus = -0.1
        
        score = task_score + time_penalty + recency_bonus
        
        return max(0.0, min(1.0, score))
    
    def get_agent_load(self, agent_id: UUID) -> Optional[AgentLoad]:
        """Get load information for an agent.
        
        Args:
            agent_id: Agent ID
        
        Returns:
            AgentLoad or None
        """
        return self._agent_loads.get(agent_id)
    
    def get_all_loads(self) -> Dict[UUID, AgentLoad]:
        """Get load information for all tracked agents.
        
        Returns:
            Dictionary of agent_id to AgentLoad
        """
        return self._agent_loads.copy()
    
    def get_least_loaded_agents(
        self,
        agent_ids: List[UUID],
        count: int = 3,
    ) -> List[UUID]:
        """Get the least loaded agents.
        
        Args:
            agent_ids: List of agent IDs to consider
            count: Number of agents to return
        
        Returns:
            List of agent IDs sorted by load (least loaded first)
        """
        sorted_agents = sorted(
            agent_ids,
            key=lambda aid: self._agent_loads.get(aid, AgentLoad(
                agent_id=aid,
                active_tasks=0,
                total_completed=0,
                avg_execution_time=0.0,
                last_task_completed=None,
                load_score=0.0,
            )).load_score,
        )
        
        return sorted_agents[:count]
