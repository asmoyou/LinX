"""Agent lifecycle management.

References:
- Requirements 12: Agent Lifecycle Management
- Design Section 4.3: Agent Lifecycle
"""

import logging
from enum import Enum
from typing import Optional
from uuid import UUID

from agent_framework.agent_registry import AgentRegistry, get_agent_registry
from agent_framework.base_agent import BaseAgent, AgentConfig, AgentStatus

logger = logging.getLogger(__name__)


class LifecyclePhase(Enum):
    """Agent lifecycle phases."""
    
    CREATION = "creation"
    INITIALIZATION = "initialization"
    EXECUTION = "execution"
    TERMINATION = "termination"


class AgentLifecycleManager:
    """Manage agent lifecycle (create, update, terminate)."""
    
    def __init__(self, agent_registry: Optional[AgentRegistry] = None):
        """Initialize lifecycle manager.
        
        Args:
            agent_registry: AgentRegistry instance
        """
        self.agent_registry = agent_registry or get_agent_registry()
        logger.info("AgentLifecycleManager initialized")
    
    def create_agent(
        self,
        name: str,
        agent_type: str,
        owner_user_id: UUID,
        capabilities: list[str],
    ) -> BaseAgent:
        """Create a new agent.
        
        Args:
            name: Agent name
            agent_type: Agent type/template
            owner_user_id: Owner user ID
            capabilities: List of skill names
            
        Returns:
            BaseAgent instance
        """
        logger.info(f"Creating agent: {name}")
        
        # Register agent in database
        agent_info = self.agent_registry.register_agent(
            name=name,
            agent_type=agent_type,
            owner_user_id=owner_user_id,
            capabilities=capabilities,
        )
        
        # Create agent config
        config = AgentConfig(
            agent_id=agent_info.agent_id,
            name=name,
            agent_type=agent_type,
            owner_user_id=owner_user_id,
            capabilities=capabilities,
        )
        
        # Create BaseAgent instance
        agent = BaseAgent(config=config)
        
        logger.info(f"Agent created: {name} ({agent_info.agent_id})")
        return agent
    
    def initialize_agent(self, agent: BaseAgent) -> None:
        """Initialize agent with LangChain components.
        
        Args:
            agent: BaseAgent instance
        """
        logger.info(f"Initializing agent: {agent.config.name}")
        
        # Update status to initializing
        self.agent_registry.update_agent(
            agent.config.agent_id,
            status='initializing',
        )
        
        # Initialize agent
        agent.initialize()
        
        # Update status to active
        self.agent_registry.update_agent(
            agent.config.agent_id,
            status='active',
        )
        
        logger.info(f"Agent initialized: {agent.config.name}")
    
    def terminate_agent(self, agent_id: UUID) -> bool:
        """Terminate an agent.
        
        Args:
            agent_id: Agent UUID
            
        Returns:
            True if terminated successfully
        """
        logger.info(f"Terminating agent: {agent_id}")
        
        # Update status to terminated
        result = self.agent_registry.update_agent(
            agent_id,
            status='terminated',
        )
        
        if result:
            logger.info(f"Agent terminated: {agent_id}")
            return True
        else:
            logger.warning(f"Agent not found: {agent_id}")
            return False
    
    def update_agent_status(self, agent_id: UUID, status: str) -> bool:
        """Update agent status.
        
        Args:
            agent_id: Agent UUID
            status: New status
            
        Returns:
            True if updated successfully
        """
        result = self.agent_registry.update_agent(agent_id, status=status)
        return result is not None


# Singleton instance
_lifecycle_manager: Optional[AgentLifecycleManager] = None


def get_lifecycle_manager() -> AgentLifecycleManager:
    """Get or create the lifecycle manager singleton.
    
    Returns:
        AgentLifecycleManager instance
    """
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = AgentLifecycleManager()
    return _lifecycle_manager
