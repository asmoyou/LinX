"""Agent Ownership Validation.

This module implements ownership validation for agent operations, ensuring
users can only access and control agents they own (unless they have admin privileges).

References:
- Requirements 14: User-Based Access Control
- Design Section 8.3: Data Access Control (Agent Access)
- Task 2.2.10: Add agent ownership validation
"""

import logging
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from access_control.rbac import Role, ResourceType, Action, check_permission
from access_control.permissions import CurrentUser, PermissionDeniedError
from database.models import Agent as DBAgent

logger = logging.getLogger(__name__)


def verify_agent_ownership(
    session: Session,
    agent_id: str,
    current_user: CurrentUser,
    action: Action = Action.READ
) -> bool:
    """Verify that user has permission to access an agent.
    
    This function checks:
    1. If user is admin/manager (unrestricted access)
    2. If user owns the agent (own scope)
    3. If user has department-level access (for managers)
    
    Args:
        session: SQLAlchemy database session
        agent_id: Agent ID to check
        current_user: Current authenticated user
        action: Action being performed
        
    Returns:
        True if user has permission, False otherwise
        
    Example:
        with get_db_session() as session:
            if verify_agent_ownership(session, agent_id, current_user):
                # User can access this agent
                agent = session.query(Agent).filter_by(agent_id=agent_id).first()
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return False
    
    # Admins and managers can access all agents
    if check_permission(role, ResourceType.AGENT, action, None):
        logger.debug(
            f"User {current_user.user_id} granted access to agent {agent_id} via unrestricted permission",
            extra={
                "user_id": current_user.user_id,
                "agent_id": agent_id,
                "role": current_user.role,
            }
        )
        return True
    
    # Check agent ownership
    agent = session.query(DBAgent).filter_by(agent_id=UUID(agent_id)).first()
    
    if not agent:
        logger.warning(
            f"Agent {agent_id} not found",
            extra={"agent_id": agent_id, "user_id": current_user.user_id}
        )
        return False
    
    # Check if user owns the agent
    if str(agent.owner_user_id) == str(current_user.user_id):
        if check_permission(role, ResourceType.AGENT, action, "own"):
            logger.debug(
                f"User {current_user.user_id} granted access to agent {agent_id} as owner",
                extra={
                    "user_id": current_user.user_id,
                    "agent_id": agent_id,
                }
            )
            return True
    
    logger.debug(
        f"User {current_user.user_id} denied access to agent {agent_id}",
        extra={
            "user_id": current_user.user_id,
            "agent_id": agent_id,
            "agent_owner_id": str(agent.owner_user_id),
        }
    )
    return False


def require_agent_ownership(
    session: Session,
    agent_id: str,
    current_user: CurrentUser,
    action: Action = Action.READ
) -> DBAgent:
    """Require agent ownership and return agent if authorized.
    
    This function verifies ownership and raises PermissionDeniedError if unauthorized.
    Use this in API endpoints to enforce ownership checks.
    
    Args:
        session: SQLAlchemy database session
        agent_id: Agent ID to check
        current_user: Current authenticated user
        action: Action being performed
        
    Returns:
        Agent object if authorized
        
    Raises:
        PermissionDeniedError: If user doesn't have permission
        
    Example:
        @app.get("/agents/{agent_id}")
        def get_agent(agent_id: str, current_user: CurrentUser = Depends(get_current_user)):
            with get_db_session() as session:
                agent = require_agent_ownership(session, agent_id, current_user)
                return agent.to_dict()
    """
    if not verify_agent_ownership(session, agent_id, current_user, action):
        logger.warning(
            f"Permission denied: User {current_user.user_id} attempted to {action.value} agent {agent_id}",
            extra={
                "user_id": current_user.user_id,
                "agent_id": agent_id,
                "action": action.value,
            }
        )
        raise PermissionDeniedError(
            f"You do not have permission to {action.value} this agent"
        )
    
    # Get and return agent
    agent = session.query(DBAgent).filter_by(agent_id=UUID(agent_id)).first()
    
    if not agent:
        raise PermissionDeniedError(f"Agent {agent_id} not found")
    
    return agent


def get_user_agents(
    session: Session,
    current_user: CurrentUser
) -> list:
    """Get all agents accessible to the user.
    
    Args:
        session: SQLAlchemy database session
        current_user: Current authenticated user
        
    Returns:
        List of Agent objects accessible to the user
        
    Example:
        with get_db_session() as session:
            agents = get_user_agents(session, current_user)
            for agent in agents:
                print(f"Agent: {agent.name}")
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return []
    
    # Admins and managers can see all agents
    if check_permission(role, ResourceType.AGENT, Action.READ, None):
        agents = session.query(DBAgent).all()
        logger.debug(
            f"User {current_user.user_id} retrieved all agents (unrestricted access)",
            extra={"user_id": current_user.user_id, "count": len(agents)}
        )
        return agents
    
    # Users can only see their own agents
    if check_permission(role, ResourceType.AGENT, Action.READ, "own"):
        agents = session.query(DBAgent).filter_by(
            owner_user_id=UUID(current_user.user_id)
        ).all()
        logger.debug(
            f"User {current_user.user_id} retrieved own agents",
            extra={"user_id": current_user.user_id, "count": len(agents)}
        )
        return agents
    
    # No permission
    logger.debug(
        f"User {current_user.user_id} has no agent access permissions",
        extra={"user_id": current_user.user_id}
    )
    return []


def can_create_agent(
    session: Session,
    current_user: CurrentUser
) -> bool:
    """Check if user can create a new agent.
    
    This also checks resource quotas to ensure user hasn't exceeded limits.
    
    Args:
        session: SQLAlchemy database session
        current_user: Current authenticated user
        
    Returns:
        True if user can create agent, False otherwise
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        return False
    
    # Check RBAC permission
    if not check_permission(role, ResourceType.AGENT, Action.CREATE, None):
        logger.debug(
            f"User {current_user.user_id} denied agent creation (no permission)",
            extra={"user_id": current_user.user_id}
        )
        return False
    
    # Check resource quota
    from database.models import ResourceQuota
    
    quota = session.query(ResourceQuota).filter_by(
        user_id=UUID(current_user.user_id)
    ).first()
    
    if quota:
        if quota.current_agents >= quota.max_agents:
            logger.warning(
                f"User {current_user.user_id} exceeded agent quota",
                extra={
                    "user_id": current_user.user_id,
                    "current": quota.current_agents,
                    "max": quota.max_agents,
                }
            )
            return False
    
    logger.debug(
        f"User {current_user.user_id} can create agent",
        extra={"user_id": current_user.user_id}
    )
    return True


def can_update_agent(
    session: Session,
    agent_id: str,
    current_user: CurrentUser
) -> bool:
    """Check if user can update an agent.
    
    Args:
        session: SQLAlchemy database session
        agent_id: Agent ID to update
        current_user: Current authenticated user
        
    Returns:
        True if user can update agent, False otherwise
    """
    return verify_agent_ownership(session, agent_id, current_user, Action.UPDATE)


def can_delete_agent(
    session: Session,
    agent_id: str,
    current_user: CurrentUser
) -> bool:
    """Check if user can delete an agent.
    
    Args:
        session: SQLAlchemy database session
        agent_id: Agent ID to delete
        current_user: Current authenticated user
        
    Returns:
        True if user can delete agent, False otherwise
    """
    return verify_agent_ownership(session, agent_id, current_user, Action.DELETE)


def can_control_agent(
    session: Session,
    agent_id: str,
    current_user: CurrentUser
) -> bool:
    """Check if user can control an agent (start, stop, restart).
    
    Args:
        session: SQLAlchemy database session
        agent_id: Agent ID to control
        current_user: Current authenticated user
        
    Returns:
        True if user can control agent, False otherwise
    """
    # Control requires UPDATE permission
    return verify_agent_ownership(session, agent_id, current_user, Action.UPDATE)


def get_agent_owner_id(
    session: Session,
    agent_id: str
) -> Optional[str]:
    """Get the owner user ID of an agent.
    
    Args:
        session: SQLAlchemy database session
        agent_id: Agent ID
        
    Returns:
        Owner user ID or None if agent not found
    """
    agent = session.query(DBAgent).filter_by(agent_id=UUID(agent_id)).first()
    
    if agent:
        return str(agent.owner_user_id)
    
    return None
