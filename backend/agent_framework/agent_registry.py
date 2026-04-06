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

from access_control.agent_access import normalize_agent_access_level
from database.connection import get_db_session
from database.models import Agent

logger = logging.getLogger(__name__)


@dataclass
class AgentInfo:
    """Agent information from registry."""

    agent_id: UUID
    name: str
    agent_type: str
    avatar: Optional[str]
    owner_user_id: UUID
    capabilities: List[str]
    status: str
    container_id: Optional[str]
    
    # LLM Configuration
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2000
    top_p: float = 0.9
    
    # Access Control
    access_level: str = "private"
    allowed_knowledge: List[str] = None
    
    # Retrieval Configuration
    top_k: Optional[int] = None
    similarity_threshold: Optional[float] = None

    # Department
    department_id: Optional[UUID] = None

    is_ephemeral: bool = False
    lifecycle_scope: Optional[str] = None
    runtime_preference: Optional[str] = None
    project_scope_id: Optional[UUID] = None
    retired_at: Optional[datetime] = None
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        """Initialize default values for mutable fields."""
        if self.allowed_knowledge is None:
            self.allowed_knowledge = []


class AgentRegistry:
    """Agent registry for managing agent metadata in PostgreSQL."""

    def register_agent(
        self,
        name: str,
        agent_type: str,
        owner_user_id: UUID,
        capabilities: List[str],
        container_id: Optional[str] = None,
        avatar: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        top_p: float = 0.9,
        access_level: str = "private",
        allowed_knowledge: Optional[List[str]] = None,
        department_id: Optional[str] = None,
        is_ephemeral: bool = False,
        lifecycle_scope: Optional[str] = None,
        runtime_preference: Optional[str] = None,
        project_scope_id: Optional[UUID] = None,
        retired_at: Optional[datetime] = None,
    ) -> AgentInfo:
        """Register a new agent in the registry.

        Args:
            name: Agent name
            agent_type: Agent type/template
            owner_user_id: Owner user ID
            capabilities: List of skill names
            container_id: Optional container ID
            avatar: Avatar image URL or path
            llm_provider: LLM provider name
            llm_model: LLM model name
            system_prompt: Custom system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            top_p: Top-p sampling
            access_level: Access level (private, department, public)
            allowed_knowledge: List of allowed knowledge collection IDs

        Returns:
            AgentInfo with registered agent details
        """
        with get_db_session() as session:
            agent = Agent(
                name=name,
                agent_type=agent_type,
                avatar=avatar,
                owner_user_id=owner_user_id,
                capabilities=capabilities,
                status="initializing",
                container_id=container_id,
                llm_provider=llm_provider,
                llm_model=llm_model,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                access_level=normalize_agent_access_level(access_level),
                allowed_knowledge=allowed_knowledge or [],
                department_id=UUID(department_id) if department_id else None,
                is_ephemeral=is_ephemeral,
                lifecycle_scope=lifecycle_scope,
                runtime_preference=runtime_preference,
                project_scope_id=project_scope_id,
                retired_at=retired_at,
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
        avatar: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        status: Optional[str] = None,
        container_id: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        top_p: Optional[float] = None,
        access_level: Optional[str] = None,
        allowed_knowledge: Optional[List[str]] = None,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        department_id: Optional[str] = None,
        runtime_preference: Optional[str] = None,
        project_scope_id: Optional[UUID] = None,
        is_ephemeral: Optional[bool] = None,
        lifecycle_scope: Optional[str] = None,
        retired_at: Optional[datetime] = None,
    ) -> Optional[AgentInfo]:
        """Update agent properties.

        Args:
            agent_id: Agent UUID
            name: New name
            avatar: Avatar image URL or path
            capabilities: New capabilities
            status: New status
            container_id: New container ID
            llm_provider: LLM provider name
            llm_model: LLM model name
            system_prompt: Custom system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            top_p: Top-p sampling
            access_level: Access level
            allowed_knowledge: List of allowed knowledge collection IDs
            top_k: Top K results for retrieval
            similarity_threshold: Similarity threshold for retrieval
            department_id: Department UUID string (empty string or None to clear)

        Returns:
            Updated AgentInfo or None if not found
        """
        with get_db_session() as session:
            agent = session.query(Agent).filter(Agent.agent_id == agent_id).first()

            if not agent:
                return None

            if name is not None:
                agent.name = name
            if avatar is not None:
                agent.avatar = avatar
            if capabilities is not None:
                agent.capabilities = capabilities
            if status is not None:
                agent.status = status
            if container_id is not None:
                agent.container_id = container_id
            if llm_provider is not None:
                agent.llm_provider = llm_provider
            if llm_model is not None:
                agent.llm_model = llm_model
            if system_prompt is not None:
                agent.system_prompt = system_prompt
            if temperature is not None:
                agent.temperature = temperature
            if max_tokens is not None:
                agent.max_tokens = max_tokens
            if top_p is not None:
                agent.top_p = top_p
            if access_level is not None:
                agent.access_level = normalize_agent_access_level(access_level)
            if allowed_knowledge is not None:
                agent.allowed_knowledge = allowed_knowledge
            if top_k is not None:
                agent.top_k = top_k
            if similarity_threshold is not None:
                agent.similarity_threshold = similarity_threshold
            if department_id is not None:
                agent.department_id = UUID(department_id) if department_id else None
            if runtime_preference is not None:
                agent.runtime_preference = runtime_preference
            if project_scope_id is not None:
                agent.project_scope_id = project_scope_id
            if is_ephemeral is not None:
                agent.is_ephemeral = is_ephemeral
            if lifecycle_scope is not None:
                agent.lifecycle_scope = lifecycle_scope
            if retired_at is not None:
                agent.retired_at = retired_at

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
            avatar=agent.avatar,
            owner_user_id=agent.owner_user_id,
            capabilities=agent.capabilities or [],
            status=agent.status,
            container_id=agent.container_id,
            llm_provider=agent.llm_provider,
            llm_model=agent.llm_model,
            system_prompt=agent.system_prompt,
            temperature=agent.temperature or 0.7,
            max_tokens=agent.max_tokens or 2000,
            top_p=agent.top_p or 0.9,
            access_level=normalize_agent_access_level(agent.access_level),
            allowed_knowledge=agent.allowed_knowledge or [],
            top_k=getattr(agent, 'top_k', None),
            similarity_threshold=getattr(agent, 'similarity_threshold', None),
            department_id=getattr(agent, 'department_id', None),
            is_ephemeral=getattr(agent, 'is_ephemeral', False),
            lifecycle_scope=getattr(agent, 'lifecycle_scope', None),
            runtime_preference=getattr(agent, 'runtime_preference', None),
            project_scope_id=getattr(agent, 'project_scope_id', None),
            retired_at=getattr(agent, 'retired_at', None),
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
