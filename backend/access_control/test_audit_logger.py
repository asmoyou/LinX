"""Unit tests for access control audit logging.

Tests cover:
- Audit log creation for various events
- Authentication event logging
- Permission check logging
- Resource access logging
- ABAC policy evaluation logging
- Audit log retrieval and filtering

References:
- Requirements 7, 11: Security and Monitoring
- Design Section 8: Access Control System
- Task 2.2.11: Create audit logging for all access control decisions
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from access_control.audit_logger import (
    AuditEventType,
    get_audit_logs,
    log_abac_policy_evaluation,
    log_access_control_event,
    log_agent_access,
    log_authentication_event,
    log_knowledge_access,
    log_memory_access,
    log_permission_check,
    log_resource_access,
    log_user_management_event,
)
from access_control.permissions import CurrentUser
from access_control.rbac import Action, ResourceType, Role
from database.models import AuditLog

# Test fixtures


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = Mock()
    session.add = Mock()
    session.flush = Mock()
    session.query = Mock()
    return session


@pytest.fixture
def current_user():
    """Current user fixture."""
    return CurrentUser(user_id=str(uuid4()), username="testuser", role=Role.USER.value)


# Tests for log_access_control_event


def test_log_access_control_event_basic(mock_session, current_user):
    """Test basic access control event logging."""
    log_access_control_event(
        mock_session,
        AuditEventType.PERMISSION_GRANTED,
        user_id=current_user.user_id,
        resource_type="knowledge",
        resource_id="k123",
        action="read",
        result="success",
    )

    # Verify session.add was called
    mock_session.add.assert_called_once()
    mock_session.flush.assert_called_once()


def test_log_access_control_event_with_details(mock_session, current_user):
    """Test logging with additional details."""
    details = {"custom_field": "value", "metadata": {"key": "data"}}

    log_access_control_event(
        mock_session,
        AuditEventType.PERMISSION_DENIED,
        user_id=current_user.user_id,
        resource_type="agent",
        action="delete",
        result="denied",
        details=details,
        reason="Insufficient permissions",
    )

    mock_session.add.assert_called_once()


def test_log_access_control_event_with_agent(mock_session, current_user):
    """Test logging event with agent ID."""
    agent_id = str(uuid4())

    log_access_control_event(
        mock_session,
        AuditEventType.AGENT_ACCESSED,
        user_id=current_user.user_id,
        agent_id=agent_id,
        resource_type="agent",
        resource_id=agent_id,
        action="read",
    )

    mock_session.add.assert_called_once()


def test_log_access_control_event_handles_exception(mock_session, current_user):
    """Test that logging handles exceptions gracefully."""
    mock_session.add.side_effect = Exception("Database error")

    # Should not raise exception
    log_access_control_event(
        mock_session, AuditEventType.PERMISSION_GRANTED, user_id=current_user.user_id
    )


# Tests for log_authentication_event


def test_log_authentication_success(mock_session):
    """Test logging successful authentication."""
    log_authentication_event(
        mock_session,
        AuditEventType.LOGIN_SUCCESS,
        username="testuser",
        user_id=str(uuid4()),
        success=True,
        ip_address="192.168.1.1",
        user_agent="Mozilla/5.0",
    )

    mock_session.add.assert_called_once()


def test_log_authentication_failure(mock_session):
    """Test logging failed authentication."""
    log_authentication_event(
        mock_session,
        AuditEventType.LOGIN_FAILURE,
        username="testuser",
        success=False,
        reason="Invalid password",
        ip_address="192.168.1.1",
    )

    mock_session.add.assert_called_once()


def test_log_token_events(mock_session):
    """Test logging token-related events."""
    user_id = str(uuid4())

    # Token refresh
    log_authentication_event(
        mock_session,
        AuditEventType.TOKEN_REFRESH,
        username="testuser",
        user_id=user_id,
        success=True,
    )

    # Token expired
    log_authentication_event(
        mock_session,
        AuditEventType.TOKEN_EXPIRED,
        username="testuser",
        user_id=user_id,
        success=False,
        reason="Token expired",
    )

    assert mock_session.add.call_count == 2


# Tests for log_permission_check


def test_log_permission_granted(mock_session, current_user):
    """Test logging granted permission."""
    log_permission_check(
        mock_session,
        current_user,
        ResourceType.KNOWLEDGE,
        Action.READ,
        resource_id="k123",
        granted=True,
        scope="own",
    )

    mock_session.add.assert_called_once()


def test_log_permission_denied(mock_session, current_user):
    """Test logging denied permission."""
    log_permission_check(
        mock_session,
        current_user,
        ResourceType.AGENT,
        Action.DELETE,
        resource_id="a123",
        granted=False,
        reason="User does not own this agent",
        scope="own",
    )

    mock_session.add.assert_called_once()


# Tests for log_resource_access


def test_log_resource_access_granted(mock_session, current_user):
    """Test logging granted resource access."""
    log_resource_access(
        mock_session,
        current_user,
        "knowledge",
        "k123",
        "read",
        granted=True,
        owner_id=current_user.user_id,
    )

    mock_session.add.assert_called_once()


def test_log_resource_access_denied(mock_session, current_user):
    """Test logging denied resource access."""
    owner_id = str(uuid4())

    log_resource_access(
        mock_session,
        current_user,
        "knowledge",
        "k123",
        "delete",
        granted=False,
        reason="Not the owner",
        owner_id=owner_id,
    )

    mock_session.add.assert_called_once()


# Tests for log_agent_access


def test_log_agent_access_read(mock_session, current_user):
    """Test logging agent read access."""
    agent_id = str(uuid4())

    log_agent_access(
        mock_session,
        current_user,
        agent_id,
        "read",
        granted=True,
        agent_owner_id=current_user.user_id,
    )

    mock_session.add.assert_called_once()


def test_log_agent_creation(mock_session, current_user):
    """Test logging agent creation."""
    agent_id = str(uuid4())

    log_agent_access(mock_session, current_user, agent_id, "create", granted=True)

    mock_session.add.assert_called_once()


def test_log_agent_control(mock_session, current_user):
    """Test logging agent control action."""
    agent_id = str(uuid4())

    log_agent_access(
        mock_session,
        current_user,
        agent_id,
        "control",
        granted=True,
        agent_owner_id=current_user.user_id,
    )

    mock_session.add.assert_called_once()


def test_log_agent_access_denied(mock_session, current_user):
    """Test logging denied agent access."""
    agent_id = str(uuid4())
    owner_id = str(uuid4())

    log_agent_access(
        mock_session,
        current_user,
        agent_id,
        "delete",
        granted=False,
        reason="Not the owner",
        agent_owner_id=owner_id,
    )

    mock_session.add.assert_called_once()


# Tests for log_knowledge_access


def test_log_knowledge_access_read(mock_session, current_user):
    """Test logging knowledge read access."""
    log_knowledge_access(
        mock_session,
        current_user,
        "k123",
        "read",
        granted=True,
        access_level="public",
        owner_id=str(uuid4()),
    )

    mock_session.add.assert_called_once()


def test_log_knowledge_creation(mock_session, current_user):
    """Test logging knowledge creation."""
    log_knowledge_access(
        mock_session,
        current_user,
        "k123",
        "create",
        granted=True,
        access_level="private",
        owner_id=current_user.user_id,
    )

    mock_session.add.assert_called_once()


def test_log_knowledge_access_denied(mock_session, current_user):
    """Test logging denied knowledge access."""
    log_knowledge_access(
        mock_session,
        current_user,
        "k123",
        "delete",
        granted=False,
        reason="Insufficient permissions",
        access_level="private",
        owner_id=str(uuid4()),
    )

    mock_session.add.assert_called_once()


# Tests for log_memory_access


def test_log_memory_access_agent_memory(mock_session, current_user):
    """Test logging agent memory access."""
    agent_id = str(uuid4())

    log_memory_access(
        mock_session, current_user, "m123", "agent_memory", "read", granted=True, agent_id=agent_id
    )

    mock_session.add.assert_called_once()


def test_log_memory_access_company_memory(mock_session, current_user):
    """Test logging company memory access."""
    log_memory_access(mock_session, current_user, "m123", "company_memory", "read", granted=True)

    mock_session.add.assert_called_once()


def test_log_memory_creation(mock_session, current_user):
    """Test logging memory creation."""
    log_memory_access(mock_session, current_user, "m123", "company_memory", "create", granted=True)

    mock_session.add.assert_called_once()


# Tests for log_abac_policy_evaluation


def test_log_abac_policy_matched(mock_session, current_user):
    """Test logging matched ABAC policy."""
    log_abac_policy_evaluation(
        mock_session,
        current_user,
        "policy-123",
        "Engineering Access Policy",
        "knowledge",
        "read",
        matched=True,
        effect="allow",
    )

    mock_session.add.assert_called_once()


def test_log_abac_policy_denied(mock_session, current_user):
    """Test logging denied ABAC policy."""
    log_abac_policy_evaluation(
        mock_session,
        current_user,
        "policy-456",
        "Restricted Access Policy",
        "knowledge",
        "write",
        matched=True,
        effect="deny",
    )

    mock_session.add.assert_called_once()


def test_log_abac_policy_no_match(mock_session, current_user):
    """Test logging ABAC policy that didn't match."""
    log_abac_policy_evaluation(
        mock_session,
        current_user,
        "policy-789",
        "Department Policy",
        "knowledge",
        "read",
        matched=False,
        effect="allow",
    )

    mock_session.add.assert_called_once()


# Tests for log_user_management_event


def test_log_user_created(mock_session):
    """Test logging user creation."""
    target_user_id = str(uuid4())
    admin_id = str(uuid4())

    log_user_management_event(
        mock_session,
        AuditEventType.USER_CREATED,
        target_user_id,
        "newuser",
        performed_by_user_id=admin_id,
        role="user",
    )

    mock_session.add.assert_called_once()


def test_log_role_assigned(mock_session):
    """Test logging role assignment."""
    target_user_id = str(uuid4())
    admin_id = str(uuid4())

    log_user_management_event(
        mock_session,
        AuditEventType.ROLE_ASSIGNED,
        target_user_id,
        "testuser",
        performed_by_user_id=admin_id,
        role="manager",
    )

    mock_session.add.assert_called_once()


# Tests for get_audit_logs


def test_get_audit_logs_all(mock_session):
    """Test retrieving all audit logs."""
    mock_logs = [Mock(spec=AuditLog) for _ in range(5)]
    mock_session.query().order_by().limit().all.return_value = mock_logs

    result = get_audit_logs(mock_session)

    assert len(result) == 5


def test_get_audit_logs_filter_by_user(mock_session):
    """Test filtering audit logs by user."""
    user_id = str(uuid4())
    mock_logs = [Mock(spec=AuditLog)]
    mock_session.query().filter().order_by().limit().all.return_value = mock_logs

    result = get_audit_logs(mock_session, user_id=user_id)

    assert len(result) == 1


def test_get_audit_logs_filter_by_resource_type(mock_session):
    """Test filtering audit logs by resource type."""
    mock_logs = [Mock(spec=AuditLog) for _ in range(3)]
    mock_session.query().filter().order_by().limit().all.return_value = mock_logs

    result = get_audit_logs(mock_session, resource_type="knowledge")

    assert len(result) == 3


def test_get_audit_logs_filter_by_date_range(mock_session):
    """Test filtering audit logs by date range."""
    start_date = datetime.utcnow() - timedelta(days=7)
    end_date = datetime.utcnow()
    mock_logs = [Mock(spec=AuditLog) for _ in range(10)]
    mock_session.query().filter().filter().order_by().limit().all.return_value = mock_logs

    result = get_audit_logs(mock_session, start_date=start_date, end_date=end_date)

    assert len(result) == 10


def test_get_audit_logs_with_limit(mock_session):
    """Test retrieving audit logs with custom limit."""
    mock_logs = [Mock(spec=AuditLog) for _ in range(50)]
    mock_session.query().order_by().limit().all.return_value = mock_logs

    result = get_audit_logs(mock_session, limit=50)

    assert len(result) == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
