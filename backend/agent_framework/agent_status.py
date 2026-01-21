"""Agent status tracking.

References:
- Requirements 12: Agent Lifecycle Management
- Design Section 4.3: Agent Lifecycle
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from uuid import UUID

from agent_framework.agent_registry import AgentRegistry, get_agent_registry

logger = logging.getLogger(__name__)


@dataclass
class StatusUpdate:
    """Agent status update."""
    
    agent_id: UUID
    old_status: str
    new_status: str
    timestamp: datetime
    reason: Optional[str] = None


class AgentStatusTracker:
    """Track agent status changes."""
    
    def __init__(self, agent_registry: Optional[AgentRegistry] = None):
        """Initialize status tracker.
        
        Args:
            agent_registry: AgentRegistry instance
        """
        self.agent_registry = agent_registry or get_agent_registry()
        logger.info("AgentStatusTracker initialized")
    
    def update_status(
        self,
        agent_id: UUID,
        new_status: str,
        reason: Optional[str] = None,
    ) -> Optional[StatusUpdate]:
        """Update agent status.
        
        Args:
            agent_id: Agent UUID
            new_status: New status value
            reason: Optional reason for status change
            
        Returns:
            StatusUpdate or None if agent not found
        """
        # Get current agent info
        agent_info = self.agent_registry.get_agent(agent_id)
        if not agent_info:
            logger.warning(f"Agent not found: {agent_id}")
            return None
        
        old_status = agent_info.status
        
        # Update status
        self.agent_registry.update_agent(agent_id, status=new_status)
        
        status_update = StatusUpdate(
            agent_id=agent_id,
            old_status=old_status,
            new_status=new_status,
            timestamp=datetime.utcnow(),
            reason=reason,
        )
        
        logger.info(
            f"Agent status updated: {agent_id}",
            extra={
                "old_status": old_status,
                "new_status": new_status,
                "reason": reason,
            }
        )
        
        return status_update
    
    def get_status(self, agent_id: UUID) -> Optional[str]:
        """Get current agent status.
        
        Args:
            agent_id: Agent UUID
            
        Returns:
            Status string or None if not found
        """
        agent_info = self.agent_registry.get_agent(agent_id)
        return agent_info.status if agent_info else None


# Singleton instance
_status_tracker: Optional[AgentStatusTracker] = None


def get_status_tracker() -> AgentStatusTracker:
    """Get or create the status tracker singleton.
    
    Returns:
        AgentStatusTracker instance
    """
    global _status_tracker
    if _status_tracker is None:
        _status_tracker = AgentStatusTracker()
    return _status_tracker
