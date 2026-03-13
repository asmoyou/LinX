"""Access Control Audit Logging.

This module implements comprehensive audit logging for all access control decisions,
including permission checks, authentication events, and authorization failures.

References:
- Requirements 7, 11: Security and Monitoring
- Design Section 8: Access Control System
- Task 2.2.11: Create audit logging for all access control decisions
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from access_control.permissions import CurrentUser
from access_control.rbac import Action, ResourceType
from database.models import AuditLog

logger = logging.getLogger(__name__)


class AuditEventType:
    """Audit event types for access control."""

    # Authentication events
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILURE = "login_failure"
    LOGOUT = "logout"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"

    # Authorization events
    PERMISSION_GRANTED = "permission_granted"
    PERMISSION_DENIED = "permission_denied"
    ROLE_CHECK_SUCCESS = "role_check_success"
    ROLE_CHECK_FAILURE = "role_check_failure"

    # Resource access events
    RESOURCE_ACCESS_GRANTED = "resource_access_granted"
    RESOURCE_ACCESS_DENIED = "resource_access_denied"
    OWNERSHIP_VERIFIED = "ownership_verified"
    OWNERSHIP_DENIED = "ownership_denied"

    # Policy events
    ABAC_POLICY_MATCHED = "abac_policy_matched"
    ABAC_POLICY_DENIED = "abac_policy_denied"
    RBAC_PERMISSION_GRANTED = "rbac_permission_granted"
    RBAC_PERMISSION_DENIED = "rbac_permission_denied"

    # User management events
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"
    USER_DELETED = "user_deleted"
    ROLE_ASSIGNED = "role_assigned"
    ROLE_REVOKED = "role_revoked"

    # Agent events
    AGENT_CREATED = "agent_created"
    AGENT_ACCESSED = "agent_accessed"
    AGENT_UPDATED = "agent_updated"
    AGENT_DELETED = "agent_deleted"
    AGENT_CONTROLLED = "agent_controlled"

    # Knowledge Base events
    KNOWLEDGE_ACCESSED = "knowledge_accessed"
    KNOWLEDGE_CREATED = "knowledge_created"
    KNOWLEDGE_UPDATED = "knowledge_updated"
    KNOWLEDGE_DELETED = "knowledge_deleted"

    # Memory System events
    MEMORY_ACCESSED = "memory_accessed"
    MEMORY_CREATED = "memory_created"
    MEMORY_DELETED = "memory_deleted"


def log_access_control_event(
    session: Session,
    event_type: str,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    result: str = "success",
    details: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> None:
    """Log an access control event to the audit log.

    This is the main function for logging all access control decisions.

    Args:
        session: SQLAlchemy database session
        event_type: Type of event (from AuditEventType)
        user_id: User ID involved in the event
        agent_id: Agent ID involved in the event (if applicable)
        resource_type: Type of resource being accessed
        resource_id: ID of resource being accessed
        action: Action being performed
        result: Result of the event (success, denied, error)
        details: Additional details as dictionary
        reason: Reason for denial (if applicable)

    Example:
        log_access_control_event(
            session,
            AuditEventType.PERMISSION_DENIED,
            user_id=current_user.user_id,
            resource_type="knowledge",
            resource_id="k123",
            action="delete",
            result="denied",
            reason="User does not own this resource"
        )
    """
    try:
        # Build details dictionary
        audit_details = details or {}
        audit_details.update(
            {
                "event_type": event_type,
                "result": result,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

        if action:
            audit_details["action"] = action

        if reason:
            audit_details["reason"] = reason

        # Create audit log entry
        audit_log = AuditLog(
            user_id=UUID(user_id) if user_id else None,
            agent_id=UUID(agent_id) if agent_id else None,
            action=event_type,
            resource_type=resource_type or "access_control",
            resource_id=UUID(resource_id) if resource_id else None,
            details=audit_details,
        )

        session.add(audit_log)
        session.flush()

        # Also log to application logger
        log_level = logging.INFO if result == "success" else logging.WARNING
        logger.log(
            log_level,
            f"Access control event: {event_type}",
            extra={
                "event_type": event_type,
                "user_id": user_id,
                "agent_id": agent_id,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                "result": result,
                "reason": reason,
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to log access control event: {e}",
            extra={"event_type": event_type, "error": str(e)},
            exc_info=True,
        )


def log_authentication_event(
    session: Session,
    event_type: str,
    username: str,
    user_id: Optional[str] = None,
    success: bool = True,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Log an authentication event.

    Args:
        session: SQLAlchemy database session
        event_type: Authentication event type
        username: Username attempting authentication
        user_id: User ID (if authentication successful)
        success: Whether authentication succeeded
        reason: Reason for failure (if applicable)
        ip_address: Client IP address
        user_agent: Client user agent string
    """
    details = {
        "username": username,
        "ip_address": ip_address,
        "user_agent": user_agent,
    }

    log_access_control_event(
        session,
        event_type,
        user_id=user_id,
        result="success" if success else "denied",
        details=details,
        reason=reason,
    )


def log_permission_check(
    session: Session,
    current_user: CurrentUser,
    resource_type: ResourceType,
    action: Action,
    resource_id: Optional[str] = None,
    granted: bool = True,
    reason: Optional[str] = None,
    scope: Optional[str] = None,
) -> None:
    """Log a permission check event.

    Args:
        session: SQLAlchemy database session
        current_user: User performing the action
        resource_type: Type of resource
        action: Action being performed
        resource_id: ID of specific resource
        granted: Whether permission was granted
        reason: Reason for denial
        scope: Permission scope (None, own, permitted)
    """
    event_type = AuditEventType.PERMISSION_GRANTED if granted else AuditEventType.PERMISSION_DENIED

    details = {
        "role": current_user.role,
        "scope": scope,
    }

    log_access_control_event(
        session,
        event_type,
        user_id=current_user.user_id,
        resource_type=resource_type.value,
        resource_id=resource_id,
        action=action.value,
        result="success" if granted else "denied",
        details=details,
        reason=reason,
    )


def log_resource_access(
    session: Session,
    current_user: CurrentUser,
    resource_type: str,
    resource_id: str,
    action: str,
    granted: bool = True,
    reason: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> None:
    """Log a resource access event.

    Args:
        session: SQLAlchemy database session
        current_user: User accessing the resource
        resource_type: Type of resource
        resource_id: ID of resource
        action: Action being performed
        granted: Whether access was granted
        reason: Reason for denial
        owner_id: Owner of the resource
    """
    event_type = (
        AuditEventType.RESOURCE_ACCESS_GRANTED if granted else AuditEventType.RESOURCE_ACCESS_DENIED
    )

    details = {
        "role": current_user.role,
        "owner_id": owner_id,
    }

    log_access_control_event(
        session,
        event_type,
        user_id=current_user.user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        result="success" if granted else "denied",
        details=details,
        reason=reason,
    )


def log_agent_access(
    session: Session,
    current_user: CurrentUser,
    agent_id: str,
    action: str,
    granted: bool = True,
    reason: Optional[str] = None,
    agent_owner_id: Optional[str] = None,
) -> None:
    """Log an agent access event.

    Args:
        session: SQLAlchemy database session
        current_user: User accessing the agent
        agent_id: Agent ID
        action: Action being performed
        granted: Whether access was granted
        reason: Reason for denial
        agent_owner_id: Owner of the agent
    """
    event_type_map = {
        "read": AuditEventType.AGENT_ACCESSED,
        "create": AuditEventType.AGENT_CREATED,
        "update": AuditEventType.AGENT_UPDATED,
        "delete": AuditEventType.AGENT_DELETED,
        "control": AuditEventType.AGENT_CONTROLLED,
    }

    event_type = event_type_map.get(action.lower(), AuditEventType.AGENT_ACCESSED)

    if not granted:
        event_type = AuditEventType.RESOURCE_ACCESS_DENIED

    details = {
        "role": current_user.role,
        "agent_owner_id": agent_owner_id,
    }

    log_access_control_event(
        session,
        event_type,
        user_id=current_user.user_id,
        agent_id=agent_id,
        resource_type="agent",
        resource_id=agent_id,
        action=action,
        result="success" if granted else "denied",
        details=details,
        reason=reason,
    )


def log_knowledge_access(
    session: Session,
    current_user: CurrentUser,
    knowledge_id: str,
    action: str,
    granted: bool = True,
    reason: Optional[str] = None,
    access_level: Optional[str] = None,
    owner_id: Optional[str] = None,
) -> None:
    """Log a knowledge base access event.

    Args:
        session: SQLAlchemy database session
        current_user: User accessing knowledge
        knowledge_id: Knowledge item ID
        action: Action being performed
        granted: Whether access was granted
        reason: Reason for denial
        access_level: Access level of knowledge item
        owner_id: Owner of the knowledge item
    """
    event_type_map = {
        "read": AuditEventType.KNOWLEDGE_ACCESSED,
        "create": AuditEventType.KNOWLEDGE_CREATED,
        "update": AuditEventType.KNOWLEDGE_UPDATED,
        "delete": AuditEventType.KNOWLEDGE_DELETED,
    }

    event_type = event_type_map.get(action.lower(), AuditEventType.KNOWLEDGE_ACCESSED)

    if not granted:
        event_type = AuditEventType.RESOURCE_ACCESS_DENIED

    details = {
        "role": current_user.role,
        "access_level": access_level,
        "owner_id": owner_id,
    }

    log_access_control_event(
        session,
        event_type,
        user_id=current_user.user_id,
        resource_type="knowledge",
        resource_id=knowledge_id,
        action=action,
        result="success" if granted else "denied",
        details=details,
        reason=reason,
    )


def log_memory_access(
    session: Session,
    current_user: CurrentUser,
    memory_id: str,
    memory_tier: str,
    action: str,
    granted: bool = True,
    reason: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> None:
    """Log an access event for reset-era memory products.

    Args:
        session: SQLAlchemy database session
        current_user: User accessing memory
        memory_id: Memory item ID
        memory_tier: Memory product surface (for example ``user_memory`` or ``skill_learning``)
        action: Action being performed
        granted: Whether access was granted
        reason: Reason for denial
        agent_id: Agent ID when the memory product is agent-owned
    """
    event_type_map = {
        "read": AuditEventType.MEMORY_ACCESSED,
        "create": AuditEventType.MEMORY_CREATED,
        "delete": AuditEventType.MEMORY_DELETED,
    }

    event_type = event_type_map.get(action.lower(), AuditEventType.MEMORY_ACCESSED)

    if not granted:
        event_type = AuditEventType.RESOURCE_ACCESS_DENIED

    details = {
        "role": current_user.role,
        "memory_tier": memory_tier,
    }

    log_access_control_event(
        session,
        event_type,
        user_id=current_user.user_id,
        agent_id=agent_id,
        resource_type="memory",
        resource_id=memory_id,
        action=action,
        result="success" if granted else "denied",
        details=details,
        reason=reason,
    )


def log_abac_policy_evaluation(
    session: Session,
    current_user: CurrentUser,
    policy_id: str,
    policy_name: str,
    resource_type: str,
    action: str,
    matched: bool,
    effect: str,
) -> None:
    """Log an ABAC policy evaluation.

    Args:
        session: SQLAlchemy database session
        current_user: User being evaluated
        policy_id: Policy ID
        policy_name: Policy name
        resource_type: Resource type
        action: Action being performed
        matched: Whether policy conditions matched
        effect: Policy effect (allow, deny)
    """
    event_type = (
        AuditEventType.ABAC_POLICY_MATCHED if matched else AuditEventType.ABAC_POLICY_DENIED
    )

    details = {
        "policy_id": policy_id,
        "policy_name": policy_name,
        "effect": effect,
        "matched": matched,
    }

    log_access_control_event(
        session,
        event_type,
        user_id=current_user.user_id,
        resource_type=resource_type,
        action=action,
        result="success" if matched else "no_match",
        details=details,
    )


def log_user_management_event(
    session: Session,
    event_type: str,
    target_user_id: str,
    target_username: str,
    performed_by_user_id: Optional[str] = None,
    role: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a user management event.

    Args:
        session: SQLAlchemy database session
        event_type: Event type (user_created, role_assigned, etc.)
        target_user_id: User being managed
        target_username: Username being managed
        performed_by_user_id: User performing the action
        role: Role being assigned/revoked
        details: Additional details
    """
    audit_details = details or {}
    audit_details.update(
        {
            "target_username": target_username,
            "role": role,
        }
    )

    log_access_control_event(
        session,
        event_type,
        user_id=performed_by_user_id,
        resource_type="user",
        resource_id=target_user_id,
        result="success",
        details=audit_details,
    )


def get_audit_logs(
    session: Session,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
) -> list:
    """Retrieve audit logs with filtering.

    Args:
        session: SQLAlchemy database session
        user_id: Filter by user ID
        resource_type: Filter by resource type
        action: Filter by action
        start_date: Filter by start date
        end_date: Filter by end date
        limit: Maximum number of results

    Returns:
        List of AuditLog objects
    """
    query = session.query(AuditLog)

    if user_id:
        query = query.filter(AuditLog.user_id == UUID(user_id))

    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)

    if action:
        query = query.filter(AuditLog.action == action)

    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)

    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)

    query = query.order_by(AuditLog.timestamp.desc()).limit(limit)

    return query.all()
