"""
Message Authorization

Implements authorization checks for inter-agent messaging.

Task: 1.5.6 Implement message authorization checks
References:
- Requirements 17: Inter-Agent Communication
- Design Section 15.4: Access Control
"""

import logging
from typing import Optional, Set
from dataclasses import dataclass

from .message import Message, MessageType

logger = logging.getLogger(__name__)


@dataclass
class AgentPermissions:
    """
    Permissions for an agent.
    
    Attributes:
        agent_id: Agent ID
        assigned_tasks: Set of task IDs the agent is assigned to
        can_broadcast: Whether agent can send broadcast messages
        can_send_direct: Whether agent can send direct messages
        allowed_recipients: Set of agent IDs this agent can message (None = all)
    """
    agent_id: str
    assigned_tasks: Set[str]
    can_broadcast: bool = True
    can_send_direct: bool = True
    allowed_recipients: Optional[Set[str]] = None


class MessageAuthorizer:
    """
    Authorizes inter-agent messages.
    
    Features:
    - Verify sender is assigned to task
    - Verify recipient permissions
    - Enforce message type restrictions
    - Support for permission policies
    """
    
    def __init__(self):
        """Initialize message authorizer."""
        self._permissions: dict[str, AgentPermissions] = {}
    
    def register_agent(self, permissions: AgentPermissions) -> None:
        """
        Register agent permissions.
        
        Args:
            permissions: Agent permissions
        """
        self._permissions[permissions.agent_id] = permissions
        logger.debug(f"Registered permissions for agent {permissions.agent_id}")
    
    def unregister_agent(self, agent_id: str) -> None:
        """
        Unregister agent permissions.
        
        Args:
            agent_id: Agent ID to unregister
        """
        if agent_id in self._permissions:
            del self._permissions[agent_id]
            logger.debug(f"Unregistered permissions for agent {agent_id}")
    
    def authorize_message(self, message: Message) -> tuple[bool, Optional[str]]:
        """
        Authorize a message.
        
        Args:
            message: Message to authorize
            
        Returns:
            tuple: (authorized: bool, reason: Optional[str])
                   If authorized, reason is None
                   If not authorized, reason contains explanation
        """
        # Get sender permissions
        sender_perms = self._permissions.get(message.from_agent_id)
        if not sender_perms:
            return False, f"Agent {message.from_agent_id} not registered"
        
        # Check if sender is assigned to task
        if message.task_id not in sender_perms.assigned_tasks:
            return False, (
                f"Agent {message.from_agent_id} not assigned to task {message.task_id}"
            )
        
        # Check message type permissions
        if message.is_broadcast():
            if not sender_perms.can_broadcast:
                return False, f"Agent {message.from_agent_id} cannot send broadcast messages"
        else:
            if not sender_perms.can_send_direct:
                return False, f"Agent {message.from_agent_id} cannot send direct messages"
            
            # Check recipient permissions
            if message.to_agent_id:
                if sender_perms.allowed_recipients is not None:
                    if message.to_agent_id not in sender_perms.allowed_recipients:
                        return False, (
                            f"Agent {message.from_agent_id} not allowed to message "
                            f"agent {message.to_agent_id}"
                        )
                
                # Check if recipient is registered and assigned to same task
                recipient_perms = self._permissions.get(message.to_agent_id)
                if not recipient_perms:
                    return False, f"Recipient agent {message.to_agent_id} not registered"
                
                if message.task_id not in recipient_perms.assigned_tasks:
                    return False, (
                        f"Recipient agent {message.to_agent_id} not assigned to "
                        f"task {message.task_id}"
                    )
        
        # All checks passed
        return True, None
    
    def can_agent_send_to_task(self, agent_id: str, task_id: str) -> bool:
        """
        Check if agent can send messages to a task.
        
        Args:
            agent_id: Agent ID
            task_id: Task ID
            
        Returns:
            bool: True if agent can send to task
        """
        perms = self._permissions.get(agent_id)
        if not perms:
            return False
        return task_id in perms.assigned_tasks
    
    def can_agent_message_agent(
        self,
        sender_id: str,
        recipient_id: str,
        task_id: str
    ) -> bool:
        """
        Check if one agent can message another agent.
        
        Args:
            sender_id: Sender agent ID
            recipient_id: Recipient agent ID
            task_id: Task ID
            
        Returns:
            bool: True if sender can message recipient
        """
        sender_perms = self._permissions.get(sender_id)
        if not sender_perms:
            return False
        
        # Check task assignment
        if task_id not in sender_perms.assigned_tasks:
            return False
        
        # Check direct messaging permission
        if not sender_perms.can_send_direct:
            return False
        
        # Check allowed recipients
        if sender_perms.allowed_recipients is not None:
            if recipient_id not in sender_perms.allowed_recipients:
                return False
        
        # Check recipient is assigned to task
        recipient_perms = self._permissions.get(recipient_id)
        if not recipient_perms:
            return False
        
        if task_id not in recipient_perms.assigned_tasks:
            return False
        
        return True
    
    def get_agent_permissions(self, agent_id: str) -> Optional[AgentPermissions]:
        """
        Get permissions for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            AgentPermissions or None if not registered
        """
        return self._permissions.get(agent_id)
    
    def update_agent_tasks(self, agent_id: str, task_ids: Set[str]) -> None:
        """
        Update task assignments for an agent.
        
        Args:
            agent_id: Agent ID
            task_ids: Set of task IDs
        """
        perms = self._permissions.get(agent_id)
        if perms:
            perms.assigned_tasks = task_ids
            logger.debug(
                f"Updated task assignments for agent {agent_id}: {task_ids}"
            )
        else:
            logger.warning(
                f"Cannot update tasks for unregistered agent {agent_id}"
            )
    
    def add_agent_task(self, agent_id: str, task_id: str) -> None:
        """
        Add a task assignment for an agent.
        
        Args:
            agent_id: Agent ID
            task_id: Task ID to add
        """
        perms = self._permissions.get(agent_id)
        if perms:
            perms.assigned_tasks.add(task_id)
            logger.debug(f"Added task {task_id} to agent {agent_id}")
        else:
            logger.warning(
                f"Cannot add task for unregistered agent {agent_id}"
            )
    
    def remove_agent_task(self, agent_id: str, task_id: str) -> None:
        """
        Remove a task assignment for an agent.
        
        Args:
            agent_id: Agent ID
            task_id: Task ID to remove
        """
        perms = self._permissions.get(agent_id)
        if perms:
            perms.assigned_tasks.discard(task_id)
            logger.debug(f"Removed task {task_id} from agent {agent_id}")
        else:
            logger.warning(
                f"Cannot remove task for unregistered agent {agent_id}"
            )
    
    def clear(self) -> None:
        """Clear all registered permissions."""
        self._permissions.clear()
        logger.info("Cleared all agent permissions")


# Global instance
_authorizer: Optional[MessageAuthorizer] = None


def get_message_authorizer() -> MessageAuthorizer:
    """
    Get global message authorizer instance.
    
    Returns:
        MessageAuthorizer: Global authorizer instance
    """
    global _authorizer
    if _authorizer is None:
        _authorizer = MessageAuthorizer()
    return _authorizer
