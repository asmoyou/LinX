"""Memory System Permission Filtering.

This module implements permission filtering for Memory System queries, supporting
both PostgreSQL (metadata) and Milvus (embeddings) filtering based on RBAC and ABAC.

Memory System has three tiers:
- Agent Memory: Private to each agent
- Company Memory: Shared across agents, filtered by user permissions
- User Context: User-specific memories within Company Memory

References:
- Requirements 3, 3.1, 3.2: Multi-Tiered Memory System
- Design Section 8.3: Data Access Control (Memory Access)
- Task 2.2.9: Implement permission filtering for Memory System queries
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from access_control.abac import evaluate_abac_access
from access_control.permissions import CurrentUser
from access_control.rbac import Action, ResourceType, Role, check_permission

logger = logging.getLogger(__name__)


class MemoryType:
    """Memory System types."""

    AGENT_MEMORY = "agent_memory"
    COMPANY_MEMORY = "company_memory"
    USER_CONTEXT = "user_context"


def can_access_agent_memory(
    current_user: CurrentUser, agent_id: str, agent_owner_id: str, action: Action = Action.READ
) -> bool:
    """Check if user can access Agent Memory.

    Agent Memory is private to each agent. Only the agent's owner and
    admins/managers can access it.

    Args:
        current_user: Current authenticated user
        agent_id: Agent ID
        agent_owner_id: Owner of the agent
        action: Action being performed

    Returns:
        True if user can access the agent memory, False otherwise
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return False

    # Admins and managers can access all agent memories
    if check_permission(role, ResourceType.MEMORY, action, None):
        logger.debug(
            f"User {current_user.user_id} granted access to agent memory via unrestricted permission",
            extra={"user_id": current_user.user_id, "agent_id": agent_id},
        )
        return True

    # Agent owner can access their agent's memory
    if str(agent_owner_id) == str(current_user.user_id):
        if check_permission(role, ResourceType.MEMORY, action, "own"):
            logger.debug(
                f"User {current_user.user_id} granted access to agent memory as owner",
                extra={"user_id": current_user.user_id, "agent_id": agent_id},
            )
            return True

    logger.debug(
        f"User {current_user.user_id} denied access to agent memory",
        extra={
            "user_id": current_user.user_id,
            "agent_id": agent_id,
            "agent_owner_id": agent_owner_id,
        },
    )
    return False


def can_access_company_memory(
    current_user: CurrentUser,
    memory_type: str,
    user_id: Optional[str] = None,
    action: Action = Action.READ,
    user_attributes: Optional[Dict[str, Any]] = None,
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """Check if user can access Company Memory.

    Company Memory is shared across agents but filtered by:
    - User Context: Only accessible by the user who created it
    - General memories: Accessible based on RBAC/ABAC policies

    Args:
        current_user: Current authenticated user
        memory_type: Memory type (user_context, task_context, general)
        user_id: User ID for User Context memories
        action: Action being performed
        user_attributes: Optional user attributes for ABAC
        resource_attributes: Optional resource attributes for ABAC

    Returns:
        True if user can access the company memory, False otherwise
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return False

    # Admins and managers can access all company memories
    if check_permission(role, ResourceType.MEMORY, action, None):
        logger.debug(
            f"User {current_user.user_id} granted access to company memory via unrestricted permission",
            extra={"user_id": current_user.user_id, "memory_type": memory_type},
        )
        return True

    # User Context: Only accessible by the user who created it
    if memory_type == MemoryType.USER_CONTEXT:
        if user_id and str(user_id) == str(current_user.user_id):
            if check_permission(role, ResourceType.MEMORY, action, "own"):
                logger.debug(
                    f"User {current_user.user_id} granted access to user context",
                    extra={"user_id": current_user.user_id},
                )
                return True
        else:
            logger.debug(
                f"User {current_user.user_id} denied access to user context",
                extra={"user_id": current_user.user_id, "context_owner": user_id},
            )
            return False

    # General company memories: Check RBAC permitted scope
    if check_permission(role, ResourceType.MEMORY, action, "permitted"):
        logger.debug(
            f"User {current_user.user_id} granted access to company memory via permitted scope",
            extra={"user_id": current_user.user_id, "memory_type": memory_type},
        )
        return True

    # Apply ABAC policies if attributes provided
    if user_attributes and resource_attributes:
        abac_allowed = evaluate_abac_access(
            user_attributes=user_attributes,
            resource_type="memory",
            resource_attributes=resource_attributes,
            action=action.value,
        )

        if abac_allowed:
            logger.debug(
                f"User {current_user.user_id} granted access to company memory via ABAC policy",
                extra={"user_id": current_user.user_id},
            )
            return True

    logger.debug(
        f"User {current_user.user_id} denied access to company memory",
        extra={
            "user_id": current_user.user_id,
            "memory_type": memory_type,
        },
    )
    return False


def build_agent_memory_filter(
    current_user: CurrentUser, agent_id: Optional[str] = None, action: Action = Action.READ
) -> str:
    """Build Milvus filter expression for Agent Memory queries.

    Args:
        current_user: Current authenticated user
        agent_id: Optional specific agent ID to filter
        action: Action being performed

    Returns:
        Milvus filter expression string
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return "id == -1"  # Match nothing

    # Admins and managers can access all agent memories
    if check_permission(role, ResourceType.MEMORY, action, None):
        if agent_id:
            return f'agent_id == "{agent_id}"'
        return ""  # No restrictions

    # Users can only access their own agents' memories
    # This requires joining with agents table to get owner_user_id
    # For Milvus, we need to pre-filter agent_ids in application logic
    if agent_id:
        return f'agent_id == "{agent_id}"'

    # Without specific agent_id, return restrictive filter
    # Caller should provide list of accessible agent_ids
    logger.debug(
        f"User {current_user.user_id} requires agent_id list for memory filtering",
        extra={"user_id": current_user.user_id},
    )
    return "id == -1"  # Match nothing without agent_id


def build_company_memory_filter(
    current_user: CurrentUser,
    memory_type: Optional[str] = None,
    action: Action = Action.READ,
    additional_filters: Optional[str] = None,
) -> str:
    """Build Milvus filter expression for Company Memory queries.

    Args:
        current_user: Current authenticated user
        memory_type: Optional memory type filter
        action: Action being performed
        additional_filters: Optional additional filter expressions

    Returns:
        Milvus filter expression string
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return "id == -1"

    # Admins and managers can access all company memories
    if check_permission(role, ResourceType.MEMORY, action, None):
        if memory_type:
            filter_expr = f'memory_type == "{memory_type}"'
        else:
            filter_expr = ""

        if additional_filters:
            if filter_expr:
                filter_expr = f"({filter_expr}) and ({additional_filters})"
            else:
                filter_expr = additional_filters

        return filter_expr

    # Build filter conditions
    conditions = []

    # User Context: Only user's own context
    if memory_type == MemoryType.USER_CONTEXT or memory_type is None:
        conditions.append(
            f'(memory_type == "{MemoryType.USER_CONTEXT}" and user_id == "{current_user.user_id}")'
        )

    # General company memories: Accessible with permitted scope
    if check_permission(role, ResourceType.MEMORY, action, "permitted"):
        if memory_type and memory_type != MemoryType.USER_CONTEXT:
            conditions.append(f'memory_type == "{memory_type}"')
        elif memory_type is None:
            # Include task_context and general memories
            conditions.append(f'(memory_type == "task_context" or memory_type == "general")')

    if not conditions:
        return "id == -1"  # Match nothing

    # Combine conditions with OR
    filter_expr = " or ".join(conditions)

    # Combine with additional filters
    if additional_filters:
        filter_expr = f"({filter_expr}) and ({additional_filters})"

    logger.debug(
        f"Built company memory filter for user {current_user.user_id}",
        extra={"user_id": current_user.user_id, "filter": filter_expr},
    )

    return filter_expr


def filter_memory_results(
    results: List[Dict[str, Any]],
    current_user: CurrentUser,
    memory_tier: str,
    action: Action = Action.READ,
    user_attributes: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Filter memory results in application logic (post-query filtering).

    Args:
        results: List of memory item dictionaries
        current_user: Current authenticated user
        memory_tier: Memory tier (agent_memory, company_memory)
        action: Action being performed
        user_attributes: Optional user attributes for ABAC

    Returns:
        Filtered list of memory items
    """
    filtered_results = []

    for item in results:
        agent_id = item.get("agent_id")
        agent_owner_id = item.get("agent_owner_id")
        memory_type = item.get("memory_type")
        user_id = item.get("user_id")
        item_metadata = item.get("metadata") or {}

        # Check access based on memory tier
        if memory_tier == MemoryType.AGENT_MEMORY:
            if agent_id and agent_owner_id:
                if can_access_agent_memory(current_user, agent_id, agent_owner_id, action):
                    filtered_results.append(item)

        elif memory_tier == MemoryType.COMPANY_MEMORY:
            resource_attributes = {"memory_type": memory_type, "user_id": user_id, **item_metadata}

            if can_access_company_memory(
                current_user, memory_type, user_id, action, user_attributes, resource_attributes
            ):
                filtered_results.append(item)

    logger.debug(
        f"Filtered {len(results)} memory results to {len(filtered_results)} for user {current_user.user_id}",
        extra={
            "user_id": current_user.user_id,
            "original_count": len(results),
            "filtered_count": len(filtered_results),
            "memory_tier": memory_tier,
        },
    )

    return filtered_results


def check_memory_write_permission(
    current_user: CurrentUser,
    memory_tier: str,
    agent_id: Optional[str] = None,
    agent_owner_id: Optional[str] = None,
) -> bool:
    """Check if user can write/create memory items.

    Args:
        current_user: Current authenticated user
        memory_tier: Memory tier (agent_memory, company_memory)
        agent_id: Optional agent ID for agent memory
        agent_owner_id: Optional agent owner ID for ownership check

    Returns:
        True if user can write, False otherwise
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        return False

    # Check for unrestricted write permission
    if check_permission(role, ResourceType.MEMORY, Action.CREATE, None):
        return True

    # Agent Memory: Only agent owner can write
    if memory_tier == MemoryType.AGENT_MEMORY:
        if agent_owner_id and check_permission(role, ResourceType.MEMORY, Action.CREATE, "own"):
            return str(agent_owner_id) == str(current_user.user_id)

    # Company Memory: Users can create their own memories
    elif memory_tier == MemoryType.COMPANY_MEMORY:
        if check_permission(role, ResourceType.MEMORY, Action.CREATE, "own"):
            return True

    return False


def check_memory_delete_permission(
    current_user: CurrentUser,
    memory_tier: str,
    agent_owner_id: Optional[str] = None,
    memory_user_id: Optional[str] = None,
) -> bool:
    """Check if user can delete a memory item.

    Args:
        current_user: Current authenticated user
        memory_tier: Memory tier (agent_memory, company_memory)
        agent_owner_id: Optional agent owner ID for agent memory
        memory_user_id: Optional user ID for company memory

    Returns:
        True if user can delete, False otherwise
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        return False

    # Check for unrestricted delete permission
    if check_permission(role, ResourceType.MEMORY, Action.DELETE, None):
        return True

    # Agent Memory: Only agent owner can delete
    if memory_tier == MemoryType.AGENT_MEMORY:
        if agent_owner_id and check_permission(role, ResourceType.MEMORY, Action.DELETE, "own"):
            return str(agent_owner_id) == str(current_user.user_id)

    # Company Memory: Users can delete their own memories
    elif memory_tier == MemoryType.COMPANY_MEMORY:
        if memory_user_id and check_permission(role, ResourceType.MEMORY, Action.DELETE, "own"):
            return str(memory_user_id) == str(current_user.user_id)

    return False
