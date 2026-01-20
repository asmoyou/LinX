"""Unit tests for agent ownership validation.

Tests cover:
- Agent ownership verification
- Permission checks for different roles
- Resource quota validation
- CRUD operation permissions
- Agent control permissions

References:
- Requirements 14: User-Based Access Control
- Design Section 8.3: Data Access Control
- Task 2.2.10: Add agent ownership validation
"""

import pytest
from uuid import uuid4, UUID
from unittest.mock import Mock, MagicMock

from access_control.agent_ownership import (
    verify_agent_ownership,
    require_agent_ownership,
    get_user_agents,
    can_create_agent,
    can_update_agent,
    can_delete_agent,
    can_control_agent,
    get_agent_owner_id,
)
from access_control.rbac import Role, Action
from access_control.permissions import CurrentUser, PermissionDeniedError
from database.models import Agent as DBAgent, ResourceQuota


# Test fixtures

@pytest.fixture
def mock_session():
    """Mock database session."""
    return Mock()


@pytest.fixture
def admin_user():
    """Admin user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="admin",
        role=Role.ADMIN.value
    )


@pytest.fixture
def manager_user():
    """Manager user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="manager",
        role=Role.MANAGER.value
    )


@pytest.fixture
def regular_user():
    """Regular user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="user",
        role=Role.USER.value
    )


@pytest.fixture
def viewer_user():
    """Viewer user fixture."""
    return CurrentUser(
        user_id=str(uuid4()),
        username="viewer",
        role=Role.VIEWER.value
    )


@pytest.fixture
def mock_agent(regular_user):
    """Mock agent owned by regular_user."""
    agent = Mock(spec=DBAgent)
    agent.agent_id = UUID(str(uuid4()))
    agent.name = "Test Agent"
    agent.owner_user_id = UUID(regular_user.user_id)
    agent.status = "active"
    return agent


@pytest.fixture
def mock_other_agent():
    """Mock agent owned by another user."""
    agent = Mock(spec=DBAgent)
    agent.agent_id = UUID(str(uuid4()))
    agent.name = "Other Agent"
    agent.owner_user_id = UUID(str(uuid4()))
    agent.status = "active"
    return agent


# Tests for verify_agent_ownership

def test_admin_can_access_any_agent(mock_session, admin_user, mock_other_agent):
    """Test that admin can access any agent."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = verify_agent_ownership(
        mock_session,
        str(mock_other_agent.agent_id),
        admin_user
    )
    
    assert result is True


def test_manager_can_access_any_agent(mock_session, manager_user, mock_other_agent):
    """Test that manager can access any agent."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = verify_agent_ownership(
        mock_session,
        str(mock_other_agent.agent_id),
        manager_user
    )
    
    assert result is True


def test_user_can_access_own_agent(mock_session, regular_user, mock_agent):
    """Test that user can access their own agent."""
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = verify_agent_ownership(
        mock_session,
        str(mock_agent.agent_id),
        regular_user
    )
    
    assert result is True


def test_user_cannot_access_others_agent(mock_session, regular_user, mock_other_agent):
    """Test that user cannot access other users' agents."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = verify_agent_ownership(
        mock_session,
        str(mock_other_agent.agent_id),
        regular_user
    )
    
    assert result is False


def test_viewer_cannot_access_agent(mock_session, viewer_user, mock_agent):
    """Test that viewer cannot access agents."""
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = verify_agent_ownership(
        mock_session,
        str(mock_agent.agent_id),
        viewer_user
    )
    
    assert result is False


def test_verify_ownership_agent_not_found(mock_session, regular_user):
    """Test verification when agent doesn't exist."""
    mock_session.query().filter_by().first.return_value = None
    
    result = verify_agent_ownership(
        mock_session,
        str(uuid4()),
        regular_user
    )
    
    assert result is False


def test_verify_ownership_invalid_role(mock_session, mock_agent):
    """Test verification with invalid role."""
    invalid_user = CurrentUser(
        user_id=str(uuid4()),
        username="invalid",
        role="invalid_role"
    )
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = verify_agent_ownership(
        mock_session,
        str(mock_agent.agent_id),
        invalid_user
    )
    
    assert result is False


# Tests for require_agent_ownership

def test_require_ownership_success(mock_session, regular_user, mock_agent):
    """Test require_agent_ownership returns agent when authorized."""
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = require_agent_ownership(
        mock_session,
        str(mock_agent.agent_id),
        regular_user
    )
    
    assert result == mock_agent


def test_require_ownership_raises_on_unauthorized(mock_session, regular_user, mock_other_agent):
    """Test require_agent_ownership raises PermissionDeniedError when unauthorized."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    with pytest.raises(PermissionDeniedError):
        require_agent_ownership(
            mock_session,
            str(mock_other_agent.agent_id),
            regular_user
        )


def test_require_ownership_raises_on_not_found(mock_session, regular_user):
    """Test require_agent_ownership raises when agent not found."""
    mock_session.query().filter_by().first.return_value = None
    
    with pytest.raises(PermissionDeniedError):
        require_agent_ownership(
            mock_session,
            str(uuid4()),
            regular_user
        )


# Tests for get_user_agents

def test_get_user_agents_admin_returns_all(mock_session, admin_user):
    """Test that admin gets all agents."""
    mock_agents = [Mock(spec=DBAgent) for _ in range(3)]
    mock_session.query().all.return_value = mock_agents
    
    result = get_user_agents(mock_session, admin_user)
    
    assert len(result) == 3
    assert result == mock_agents


def test_get_user_agents_user_returns_own(mock_session, regular_user):
    """Test that user gets only their own agents."""
    mock_agents = [Mock(spec=DBAgent) for _ in range(2)]
    mock_session.query().filter_by().all.return_value = mock_agents
    
    result = get_user_agents(mock_session, regular_user)
    
    assert len(result) == 2
    assert result == mock_agents


def test_get_user_agents_viewer_returns_empty(mock_session, viewer_user):
    """Test that viewer gets no agents."""
    result = get_user_agents(mock_session, viewer_user)
    
    assert result == []


def test_get_user_agents_invalid_role(mock_session):
    """Test get_user_agents with invalid role."""
    invalid_user = CurrentUser(
        user_id=str(uuid4()),
        username="invalid",
        role="invalid_role"
    )
    
    result = get_user_agents(mock_session, invalid_user)
    
    assert result == []


# Tests for can_create_agent

def test_can_create_agent_admin(mock_session, admin_user):
    """Test that admin can create agents."""
    mock_quota = Mock(spec=ResourceQuota)
    mock_quota.current_agents = 5
    mock_quota.max_agents = 10
    mock_session.query().filter_by().first.return_value = mock_quota
    
    result = can_create_agent(mock_session, admin_user)
    
    assert result is True


def test_can_create_agent_user_within_quota(mock_session, regular_user):
    """Test that user can create agent within quota."""
    mock_quota = Mock(spec=ResourceQuota)
    mock_quota.current_agents = 5
    mock_quota.max_agents = 10
    mock_session.query().filter_by().first.return_value = mock_quota
    
    result = can_create_agent(mock_session, regular_user)
    
    assert result is True


def test_can_create_agent_user_exceeds_quota(mock_session, regular_user):
    """Test that user cannot create agent when quota exceeded."""
    mock_quota = Mock(spec=ResourceQuota)
    mock_quota.current_agents = 10
    mock_quota.max_agents = 10
    mock_session.query().filter_by().first.return_value = mock_quota
    
    result = can_create_agent(mock_session, regular_user)
    
    assert result is False


def test_can_create_agent_no_quota(mock_session, regular_user):
    """Test agent creation when no quota exists."""
    mock_session.query().filter_by().first.return_value = None
    
    result = can_create_agent(mock_session, regular_user)
    
    # Should allow creation if no quota exists
    assert result is True


def test_can_create_agent_viewer(mock_session, viewer_user):
    """Test that viewer cannot create agents."""
    result = can_create_agent(mock_session, viewer_user)
    
    assert result is False


# Tests for can_update_agent

def test_can_update_own_agent(mock_session, regular_user, mock_agent):
    """Test that user can update their own agent."""
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = can_update_agent(
        mock_session,
        str(mock_agent.agent_id),
        regular_user
    )
    
    assert result is True


def test_cannot_update_others_agent(mock_session, regular_user, mock_other_agent):
    """Test that user cannot update other users' agents."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = can_update_agent(
        mock_session,
        str(mock_other_agent.agent_id),
        regular_user
    )
    
    assert result is False


def test_admin_can_update_any_agent(mock_session, admin_user, mock_other_agent):
    """Test that admin can update any agent."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = can_update_agent(
        mock_session,
        str(mock_other_agent.agent_id),
        admin_user
    )
    
    assert result is True


# Tests for can_delete_agent

def test_can_delete_own_agent(mock_session, regular_user, mock_agent):
    """Test that user can delete their own agent."""
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = can_delete_agent(
        mock_session,
        str(mock_agent.agent_id),
        regular_user
    )
    
    assert result is True


def test_cannot_delete_others_agent(mock_session, regular_user, mock_other_agent):
    """Test that user cannot delete other users' agents."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = can_delete_agent(
        mock_session,
        str(mock_other_agent.agent_id),
        regular_user
    )
    
    assert result is False


def test_admin_can_delete_any_agent(mock_session, admin_user, mock_other_agent):
    """Test that admin can delete any agent."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = can_delete_agent(
        mock_session,
        str(mock_other_agent.agent_id),
        admin_user
    )
    
    assert result is True


# Tests for can_control_agent

def test_can_control_own_agent(mock_session, regular_user, mock_agent):
    """Test that user can control their own agent."""
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = can_control_agent(
        mock_session,
        str(mock_agent.agent_id),
        regular_user
    )
    
    assert result is True


def test_cannot_control_others_agent(mock_session, regular_user, mock_other_agent):
    """Test that user cannot control other users' agents."""
    mock_session.query().filter_by().first.return_value = mock_other_agent
    
    result = can_control_agent(
        mock_session,
        str(mock_other_agent.agent_id),
        regular_user
    )
    
    assert result is False


# Tests for get_agent_owner_id

def test_get_agent_owner_id_success(mock_session, mock_agent):
    """Test getting agent owner ID."""
    mock_session.query().filter_by().first.return_value = mock_agent
    
    result = get_agent_owner_id(
        mock_session,
        str(mock_agent.agent_id)
    )
    
    assert result == str(mock_agent.owner_user_id)


def test_get_agent_owner_id_not_found(mock_session):
    """Test getting owner ID when agent doesn't exist."""
    mock_session.query().filter_by().first.return_value = None
    
    result = get_agent_owner_id(
        mock_session,
        str(uuid4())
    )
    
    assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
