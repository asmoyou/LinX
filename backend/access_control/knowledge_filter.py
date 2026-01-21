"""Knowledge Base Permission Filtering.

This module implements permission filtering for Knowledge Base queries, supporting
both PostgreSQL (metadata) and Milvus (embeddings) filtering based on RBAC and ABAC.

References:
- Requirements 14: User-Based Access Control (Acceptance Criteria 4)
- Design Section 8.3: Data Access Control (Knowledge Base Access)
- Task 2.2.8: Implement permission filtering for Knowledge Base queries
"""

import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.orm import Query

from access_control.abac import evaluate_abac_access
from access_control.permissions import CurrentUser
from access_control.rbac import Action, ResourceType, Role, check_permission

logger = logging.getLogger(__name__)


class KnowledgeAccessLevel:
    """Knowledge Base access levels."""

    PRIVATE = "private"
    TEAM = "team"
    PUBLIC = "public"


def can_access_knowledge_item(
    current_user: CurrentUser,
    action: Action,
    owner_user_id: str,
    access_level: str,
    user_attributes: Optional[Dict[str, Any]] = None,
    resource_attributes: Optional[Dict[str, Any]] = None,
) -> bool:
    """Check if user can access a specific knowledge item.

    This function combines RBAC and ABAC checks to determine access:
    1. Check RBAC permissions first (fast path)
    2. Apply access_level filtering (private, team, public)
    3. Apply ABAC policies if configured

    Args:
        current_user: Current authenticated user
        action: Action being performed (read, write, delete)
        owner_user_id: Owner of the knowledge item
        access_level: Access level (private, team, public)
        user_attributes: Optional user attributes for ABAC
        resource_attributes: Optional resource attributes for ABAC

    Returns:
        True if user can access the knowledge item, False otherwise

    Example:
        can_access = can_access_knowledge_item(
            current_user=current_user,
            action=Action.READ,
            owner_user_id="user-123",
            access_level="team",
            user_attributes={"department": "engineering"},
            resource_attributes={"classification": "internal"}
        )
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return False

    # Check RBAC permissions
    # Admins and managers can access all knowledge
    if check_permission(role, ResourceType.KNOWLEDGE, action, None):
        logger.debug(
            f"User {current_user.user_id} granted access via unrestricted RBAC permission",
            extra={
                "user_id": current_user.user_id,
                "role": current_user.role,
                "action": action.value,
            },
        )
        return True

    # Check if user owns the knowledge item
    if str(owner_user_id) == str(current_user.user_id):
        if check_permission(role, ResourceType.KNOWLEDGE, action, "own"):
            logger.debug(
                f"User {current_user.user_id} granted access as owner",
                extra={
                    "user_id": current_user.user_id,
                    "knowledge_owner": owner_user_id,
                    "action": action.value,
                },
            )
            return True

    # Apply access_level filtering
    if access_level == KnowledgeAccessLevel.PUBLIC:
        # Public knowledge is accessible to all authenticated users with read permission
        if action == Action.READ and check_permission(
            role, ResourceType.KNOWLEDGE, action, "permitted"
        ):
            logger.debug(
                f"User {current_user.user_id} granted read access to public knowledge",
                extra={
                    "user_id": current_user.user_id,
                    "access_level": access_level,
                },
            )
            return True

    elif access_level == KnowledgeAccessLevel.TEAM:
        # Team knowledge requires matching department attribute
        if user_attributes and resource_attributes:
            user_dept = user_attributes.get("department")
            resource_dept = resource_attributes.get("department")

            if user_dept and resource_dept and user_dept == resource_dept:
                if check_permission(role, ResourceType.KNOWLEDGE, action, "permitted"):
                    logger.debug(
                        f"User {current_user.user_id} granted access via team membership",
                        extra={
                            "user_id": current_user.user_id,
                            "department": user_dept,
                            "action": action.value,
                        },
                    )
                    return True

    elif access_level == KnowledgeAccessLevel.PRIVATE:
        # Private knowledge only accessible to owner (already checked above)
        pass

    # Apply ABAC policies if attributes provided
    if user_attributes and resource_attributes:
        abac_allowed = evaluate_abac_access(
            user_attributes=user_attributes,
            resource_type="knowledge",
            resource_attributes=resource_attributes,
            action=action.value,
        )

        if abac_allowed:
            logger.debug(
                f"User {current_user.user_id} granted access via ABAC policy",
                extra={
                    "user_id": current_user.user_id,
                    "action": action.value,
                },
            )
            return True

    # Access denied
    logger.debug(
        f"User {current_user.user_id} denied access to knowledge item",
        extra={
            "user_id": current_user.user_id,
            "role": current_user.role,
            "action": action.value,
            "owner_user_id": owner_user_id,
            "access_level": access_level,
        },
    )
    return False


def filter_knowledge_query(
    query: Query,
    current_user: CurrentUser,
    action: Action = Action.READ,
    user_attributes: Optional[Dict[str, Any]] = None,
) -> Query:
    """Filter a SQLAlchemy query for knowledge items based on user permissions.

    This function applies RBAC-based filtering to PostgreSQL queries for knowledge items.
    It modifies the query to only return items the user has permission to access.

    Filtering logic:
    1. Admins/Managers: No filtering (can access all)
    2. Users with "own" scope: Filter by owner_user_id
    3. Users with "permitted" scope: Filter by access_level and ownership
    4. No permission: Return empty result set

    Args:
        query: SQLAlchemy query object for KnowledgeItem
        current_user: Current authenticated user
        action: Action being performed (default: READ)
        user_attributes: Optional user attributes for team filtering

    Returns:
        Filtered SQLAlchemy query

    Example:
        from database.models import KnowledgeItem
        from database.connection import get_db_session

        with get_db_session() as session:
            query = session.query(KnowledgeItem)
            filtered_query = filter_knowledge_query(query, current_user)
            results = filtered_query.all()
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        # Return query that returns no results
        return query.filter(False)

    # Check for unrestricted permission (admins, managers)
    if check_permission(role, ResourceType.KNOWLEDGE, action, None):
        logger.debug(
            f"User {current_user.user_id} has unrestricted access, no filtering applied",
            extra={"user_id": current_user.user_id, "role": current_user.role},
        )
        return query

    # Build filter conditions
    conditions = []

    # Check for "own" scope - user can access their own knowledge
    if check_permission(role, ResourceType.KNOWLEDGE, action, "own"):
        from database.models import KnowledgeItem

        conditions.append(KnowledgeItem.owner_user_id == UUID(current_user.user_id))

    # Check for "permitted" scope - user can access based on access_level
    if check_permission(role, ResourceType.KNOWLEDGE, action, "permitted"):
        from database.models import KnowledgeItem

        # Public knowledge accessible to all
        conditions.append(KnowledgeItem.access_level == KnowledgeAccessLevel.PUBLIC)

        # Team knowledge accessible if department matches
        if user_attributes and user_attributes.get("department"):
            # For team knowledge, we need to check if user's department matches
            # This requires the knowledge item to have department in metadata
            # We'll include team knowledge and filter further in application logic
            conditions.append(KnowledgeItem.access_level == KnowledgeAccessLevel.TEAM)

    # Apply conditions
    if conditions:
        query = query.filter(or_(*conditions))
        logger.debug(
            f"Applied permission filters for user {current_user.user_id}",
            extra={
                "user_id": current_user.user_id,
                "role": current_user.role,
                "num_conditions": len(conditions),
            },
        )
    else:
        # No permissions, return empty result
        logger.debug(
            f"User {current_user.user_id} has no knowledge access permissions",
            extra={"user_id": current_user.user_id, "role": current_user.role},
        )
        query = query.filter(False)

    return query


def build_milvus_filter_expr(
    current_user: CurrentUser,
    action: Action = Action.READ,
    user_attributes: Optional[Dict[str, Any]] = None,
    additional_filters: Optional[str] = None,
) -> str:
    """Build Milvus filter expression for knowledge embeddings based on permissions.

    This function creates a Milvus filter expression string that enforces permission
    filtering on vector search queries.

    Milvus filter syntax:
    - Equality: field == "value"
    - OR: (condition1) or (condition2)
    - AND: (condition1) and (condition2)

    Args:
        current_user: Current authenticated user
        action: Action being performed (default: READ)
        user_attributes: Optional user attributes for team filtering
        additional_filters: Optional additional filter expressions to combine

    Returns:
        Milvus filter expression string

    Example:
        filter_expr = build_milvus_filter_expr(
            current_user=current_user,
            user_attributes={"department": "engineering"}
        )
        # Returns: '(owner_user_id == "user-123") or (access_level == "public") or (access_level == "team")'

        results = collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "L2", "params": {"nprobe": 10}},
            limit=10,
            expr=filter_expr
        )
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        # Return filter that matches nothing
        return "id == -1"

    # Check for unrestricted permission (admins, managers)
    if check_permission(role, ResourceType.KNOWLEDGE, action, None):
        logger.debug(
            f"User {current_user.user_id} has unrestricted Milvus access",
            extra={"user_id": current_user.user_id, "role": current_user.role},
        )
        # No filtering needed, but combine with additional filters if provided
        if additional_filters:
            return additional_filters
        return ""  # Empty filter means no restrictions

    # Build filter conditions
    conditions = []

    # Check for "own" scope - user can access their own knowledge
    if check_permission(role, ResourceType.KNOWLEDGE, action, "own"):
        conditions.append(f'owner_user_id == "{current_user.user_id}"')

    # Check for "permitted" scope - user can access based on access_level
    if check_permission(role, ResourceType.KNOWLEDGE, action, "permitted"):
        # Public knowledge accessible to all
        conditions.append(f'access_level == "{KnowledgeAccessLevel.PUBLIC}"')

        # Team knowledge accessible if department matches
        if user_attributes and user_attributes.get("department"):
            # Include team knowledge (further filtering in application logic)
            conditions.append(f'access_level == "{KnowledgeAccessLevel.TEAM}"')

    # Combine conditions
    if not conditions:
        logger.debug(
            f"User {current_user.user_id} has no Milvus access permissions",
            extra={"user_id": current_user.user_id, "role": current_user.role},
        )
        return "id == -1"  # Match nothing

    # Combine with OR
    filter_expr = " or ".join(f"({cond})" for cond in conditions)

    # Combine with additional filters using AND
    if additional_filters:
        filter_expr = f"({filter_expr}) and ({additional_filters})"

    logger.debug(
        f"Built Milvus filter for user {current_user.user_id}",
        extra={
            "user_id": current_user.user_id,
            "role": current_user.role,
            "filter_expr": filter_expr,
        },
    )

    return filter_expr


def filter_knowledge_results(
    results: List[Dict[str, Any]],
    current_user: CurrentUser,
    action: Action = Action.READ,
    user_attributes: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Filter knowledge results in application logic (post-query filtering).

    This function provides additional filtering for cases where database/Milvus
    filtering is insufficient (e.g., team knowledge with department matching).

    Use this for:
    - Team knowledge with department attribute matching
    - ABAC policy evaluation requiring complex logic
    - Post-processing of search results

    Args:
        results: List of knowledge item dictionaries
        current_user: Current authenticated user
        action: Action being performed
        user_attributes: Optional user attributes for ABAC

    Returns:
        Filtered list of knowledge items

    Example:
        results = [
            {"knowledge_id": "k1", "owner_user_id": "u1", "access_level": "team",
             "metadata": {"department": "engineering"}},
            {"knowledge_id": "k2", "owner_user_id": "u2", "access_level": "public"},
        ]

        filtered = filter_knowledge_results(
            results,
            current_user,
            user_attributes={"department": "engineering"}
        )
    """
    filtered_results = []

    for item in results:
        owner_user_id = item.get("owner_user_id")
        access_level = item.get("access_level")
        item_metadata = item.get("metadata") or item.get("item_metadata") or {}

        # Build resource attributes for ABAC
        resource_attributes = {
            "access_level": access_level,
            "owner_user_id": owner_user_id,
            **item_metadata,
        }

        # Check access
        if can_access_knowledge_item(
            current_user=current_user,
            action=action,
            owner_user_id=owner_user_id,
            access_level=access_level,
            user_attributes=user_attributes,
            resource_attributes=resource_attributes,
        ):
            filtered_results.append(item)

    logger.debug(
        f"Filtered {len(results)} results to {len(filtered_results)} for user {current_user.user_id}",
        extra={
            "user_id": current_user.user_id,
            "original_count": len(results),
            "filtered_count": len(filtered_results),
        },
    )

    return filtered_results


def get_accessible_knowledge_ids(
    current_user: CurrentUser,
    action: Action = Action.READ,
    user_attributes: Optional[Dict[str, Any]] = None,
) -> Optional[List[str]]:
    """Get list of knowledge IDs accessible to user.

    This is useful for bulk operations or when you need to check access
    for multiple knowledge items efficiently.

    Args:
        current_user: Current authenticated user
        action: Action being performed
        user_attributes: Optional user attributes

    Returns:
        List of accessible knowledge_ids, or None if user has unrestricted access

    Example:
        accessible_ids = get_accessible_knowledge_ids(current_user)
        if accessible_ids is None:
            # User can access all knowledge
            query = session.query(KnowledgeItem)
        else:
            # Filter by accessible IDs
            query = session.query(KnowledgeItem).filter(
                KnowledgeItem.knowledge_id.in_(accessible_ids)
            )
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        logger.warning(f"Invalid role: {current_user.role}")
        return []

    # Check for unrestricted permission
    if check_permission(role, ResourceType.KNOWLEDGE, action, None):
        return None  # None means unrestricted access

    # For restricted access, we need to query the database
    # This is a helper function, actual implementation would query DB
    # For now, return empty list to indicate restricted access
    logger.debug(
        f"User {current_user.user_id} has restricted knowledge access",
        extra={"user_id": current_user.user_id, "role": current_user.role},
    )

    # Caller should use filter_knowledge_query instead
    return []


def check_knowledge_write_permission(
    current_user: CurrentUser,
    knowledge_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> bool:
    """Check if user can write/update knowledge items.

    Args:
        current_user: Current authenticated user
        knowledge_id: Optional knowledge ID for update operations
        owner_user_id: Optional owner ID for ownership check

    Returns:
        True if user can write, False otherwise
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        return False

    # Check for unrestricted write permission
    if check_permission(role, ResourceType.KNOWLEDGE, Action.UPDATE, None):
        return True

    # Check for "own" scope write permission
    if owner_user_id and check_permission(role, ResourceType.KNOWLEDGE, Action.UPDATE, "own"):
        return str(owner_user_id) == str(current_user.user_id)

    # Check for create permission (new knowledge items)
    if not knowledge_id and check_permission(role, ResourceType.KNOWLEDGE, Action.CREATE, None):
        return True

    return False


def check_knowledge_delete_permission(current_user: CurrentUser, owner_user_id: str) -> bool:
    """Check if user can delete a knowledge item.

    Args:
        current_user: Current authenticated user
        owner_user_id: Owner of the knowledge item

    Returns:
        True if user can delete, False otherwise
    """
    try:
        role = Role(current_user.role)
    except ValueError:
        return False

    # Check for unrestricted delete permission
    if check_permission(role, ResourceType.KNOWLEDGE, Action.DELETE, None):
        return True

    # Check for "own" scope delete permission
    if check_permission(role, ResourceType.KNOWLEDGE, Action.DELETE, "own"):
        return str(owner_user_id) == str(current_user.user_id)

    return False
