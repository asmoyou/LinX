"""Agent Assignment Logic.

Assigns agents to tasks based on capabilities and availability.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.1: Task Decomposition Algorithm
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import Agent
from task_manager.capability_mapper import CapabilityMapper

logger = logging.getLogger(__name__)


@dataclass
class AgentAssignment:
    """Result of agent assignment."""

    task_id: UUID
    agent_id: Optional[UUID]
    match_score: float
    reason: str


class AgentAssigner:
    """Assigns agents to tasks based on capabilities."""

    def __init__(self):
        """Initialize agent assigner."""
        self.capability_mapper = CapabilityMapper()

        logger.info("AgentAssigner initialized")

    def assign_agent_to_task(
        self,
        task_id: UUID,
        required_capabilities: List[str],
        user_id: UUID,
        exclude_agent_ids: Optional[List[UUID]] = None,
    ) -> AgentAssignment:
        """Assign an agent to a task.

        Args:
            task_id: Task ID
            required_capabilities: Required capabilities
            user_id: User ID (for filtering agents)
            exclude_agent_ids: Agent IDs to exclude

        Returns:
            AgentAssignment with selected agent
        """
        logger.info(
            "Assigning agent to task",
            extra={
                "task_id": str(task_id),
                "required_capabilities": required_capabilities,
                "user_id": str(user_id),
            },
        )

        exclude_agent_ids = exclude_agent_ids or []

        # Query available agents
        with get_db_session() as session:
            agents = (
                session.query(Agent)
                .filter(
                    Agent.owner_user_id == user_id,
                    Agent.status.in_(["idle", "active"]),
                    ~Agent.agent_id.in_(exclude_agent_ids),
                )
                .all()
            )

            if not agents:
                logger.warning(
                    "No available agents found",
                    extra={"user_id": str(user_id)},
                )
                return AgentAssignment(
                    task_id=task_id,
                    agent_id=None,
                    match_score=0.0,
                    reason="No available agents",
                )

            # Find best matching agent
            best_agent = None
            best_score = 0.0

            for agent in agents:
                agent_capabilities = agent.capabilities.get("skills", [])
                score = self.capability_mapper.calculate_capability_match_score(
                    required=required_capabilities,
                    available=agent_capabilities,
                )

                if score > best_score:
                    best_score = score
                    best_agent = agent

            if best_agent:
                logger.info(
                    "Agent assigned to task",
                    extra={
                        "task_id": str(task_id),
                        "agent_id": str(best_agent.agent_id),
                        "match_score": best_score,
                    },
                )

                return AgentAssignment(
                    task_id=task_id,
                    agent_id=best_agent.agent_id,
                    match_score=best_score,
                    reason=f"Best match with score {best_score:.2f}",
                )
            else:
                return AgentAssignment(
                    task_id=task_id,
                    agent_id=None,
                    match_score=0.0,
                    reason="No suitable agent found",
                )

    def assign_agents_to_tasks(
        self,
        task_requirements: Dict[UUID, List[str]],
        user_id: UUID,
    ) -> Dict[UUID, AgentAssignment]:
        """Assign agents to multiple tasks.

        Args:
            task_requirements: Map of task_id to required capabilities
            user_id: User ID

        Returns:
            Map of task_id to AgentAssignment
        """
        assignments = {}
        used_agents = []

        # Sort tasks by number of required capabilities (most specific first)
        sorted_tasks = sorted(
            task_requirements.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )

        for task_id, capabilities in sorted_tasks:
            assignment = self.assign_agent_to_task(
                task_id=task_id,
                required_capabilities=capabilities,
                user_id=user_id,
                exclude_agent_ids=used_agents,
            )

            assignments[task_id] = assignment

            if assignment.agent_id:
                used_agents.append(assignment.agent_id)

        logger.info(
            "Batch agent assignment complete",
            extra={
                "total_tasks": len(task_requirements),
                "assigned": sum(1 for a in assignments.values() if a.agent_id),
            },
        )

        return assignments
