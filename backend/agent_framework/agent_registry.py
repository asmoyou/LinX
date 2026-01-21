"""Agent registry in PostgreSQL.

References:
- Requirements 12: Agent Lifecycle Management
- Design Section 4.3: Agent Lifecycle
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from database.connection import get_db_session
from database.models import Agent

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """Agent information from registry."""

    agent_id: UUID
    name: str
    agent_type: str
    owner_user_id: UUID
    capabilities: List[str]
    status: str
    container_id: Optional[str]
    created_at: datetime
    updated_at: datetime


class AgentRegistry:
    """Agent registry for managing agent metadata in PostgreSQL."""

    def register_agent(
        self,
        name: str,
        agent_type: str,
        owner_user_id: UUID,
        capabilities: List[str],
        container_id: Optional[str] = None,
    ) -> AgentInfo:
        """Register a new agent in the registry.

        Args:
            name: Agent name
            agent_type: Agent type/template
            owner_user_id: Owner user ID
            capabilities: List of skill names
            container_id: Optional container ID

        Returns:
            AgentInfo with registered agent details
        """
        with get_db_session() as session:
            agent = Agent(
                name=name,
                agent_type=agent_type,
                owner_user_id=owner_user_id,
                capabilities=capabilities,
                status="initializing",
                container_id=container_id,
            )
            session.add(agent)
            session.commit()
            session.refresh(agent)

            logger.info(
                f"Agent registered: {name}",
                extra={"agent_id": str(agent.agent_id), "type": agent_type},
            )

            return self._to_agent_info(agent)

    def get_agent(self, agent_id: UUID) -> Optional[AgentInfo]:
        """Get agent by ID.

        Args:
            agent_id: Agent UUID

        Returns:
            AgentInfo or None if not found
        """
        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()
            return self._to_agent_info(agent) if agent else None

    def list_agents(
        self,
        owner_user_id: Optional[UUID] = None,
        status: Optional[str] = None,
        agent_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AgentInfo]:
        """List agents with optional filters.

        Args:
            owner_user_id: Filter by owner
            status: Filter by status
            agent_type: Filter by type
            limit: Maximum number of agents
            offset: Number of agents to skip

        Returns:
            List of AgentInfo objects
        """
        with get_db_session() as session:
            query = session.query(Agent)

            if owner_user_id:
                query = query.filter(Agent.owner_user_id == owner_user_id)
            if status:
                query = query.filter(Agent.status == status)
            if agent_type:
                query = query.filter(Agent.agent_type == agent_type)

            agents = query.limit(limit).offset(offset).all()
            return [self._to_agent_info(agent) for agent in agents]

    def update_agent(
        self,
        agent_id: UUID,
        name: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        status: Optional[str] = None,
        container_id: Optional[str] = None,
    ) -> Optional[AgentInfo]:
        """Update agent properties.

        Args:
            agent_id: Agent UUID
            name: New name
            capabilities: New capabilities
            status: New status
            container_id: New container ID

        Returns:
            Updated AgentInfo or None if not found
        """
        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()

            if not agent:
                return None

            if name is not None:
                agent.name = name
            if capabilities is not None:
                agent.capabilities = capabilities
            if status is not None:
                agent.status = status
            if container_id is not None:
                agent.container_id = container_id

            session.commit()
            session.refresh(agent)

            logger.info(f"Agent updated: {agent_id}")
            return self._to_agent_info(agent)

    def delete_agent(self, agent_id: UUID) -> bool:
        """Delete an agent from registry.

        Args:
            agent_id: Agent UUID

        Returns:
            True if deleted, False if not found
        """
        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()

            if not agent:
                return False

            session.delete(agent)
            session.commit()

            logger.info(f"Agent deleted: {agent_id}")
            return True

    def search_by_capability(self, capability: str) -> List[AgentInfo]:
        """Search agents by capability.

        Args:
            capability: Skill name to search for

        Returns:
            List of AgentInfo objects with the capability
        """
        with get_db_session() as session:
            # Use JSONB contains operator
            agents = session.query(Agent).filter(Agent.capabilities.contains([capability])).all()

            return [self._to_agent_info(agent) for agent in agents]

    def _to_agent_info(self, agent: Agent) -> AgentInfo:
        """Convert Agent model to AgentInfo.

        Args:
            agent: Agent database model

        Returns:
            AgentInfo dataclass
        """
        return AgentInfo(
            agent_id=agent.agent_id,
            name=agent.name,
            agent_type=agent.agent_type,
            owner_user_id=agent.owner_user_id,
            capabilities=agent.capabilities or [],
            status=agent.status,
            container_id=agent.container_id,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )


# Singleton instance
_agent_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """Get or create the agent registry singleton.

    Returns:
        AgentRegistry instance
    """
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry
