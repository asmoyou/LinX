"""Unit tests for reset-era skill-learning access checks."""

from uuid import uuid4

import pytest

from access_control.memory_filter import (
    can_access_skill_learning,
    check_skill_learning_delete_permission,
    check_skill_learning_write_permission,
)
from access_control.permissions import CurrentUser
from access_control.rbac import Role


@pytest.fixture
def admin_user():
    return CurrentUser(user_id=str(uuid4()), username="admin", role=Role.ADMIN.value)


@pytest.fixture
def manager_user():
    return CurrentUser(user_id=str(uuid4()), username="manager", role=Role.MANAGER.value)


@pytest.fixture
def regular_user():
    return CurrentUser(user_id=str(uuid4()), username="user", role=Role.USER.value)


@pytest.fixture
def viewer_user():
    return CurrentUser(user_id=str(uuid4()), username="viewer", role=Role.VIEWER.value)


def test_admin_can_access_any_skill_learning(admin_user):
    assert can_access_skill_learning(admin_user, str(uuid4()), str(uuid4()))


def test_manager_can_access_any_skill_learning(manager_user):
    assert can_access_skill_learning(manager_user, str(uuid4()), str(uuid4()))


def test_owner_can_access_owned_skill_learning(regular_user):
    assert can_access_skill_learning(regular_user, str(uuid4()), regular_user.user_id)


def test_user_cannot_access_other_users_skill_learning(regular_user):
    assert not can_access_skill_learning(regular_user, str(uuid4()), str(uuid4()))


def test_invalid_role_denies_skill_learning_access():
    invalid_user = CurrentUser(user_id=str(uuid4()), username="invalid", role="invalid_role")
    assert not can_access_skill_learning(invalid_user, str(uuid4()), str(uuid4()))


def test_owner_can_write_skill_learning(regular_user):
    assert check_skill_learning_write_permission(
        regular_user,
        agent_owner_id=regular_user.user_id,
    )


def test_user_cannot_write_other_users_skill_learning(regular_user):
    assert not check_skill_learning_write_permission(regular_user, agent_owner_id=str(uuid4()))


def test_viewer_cannot_write_skill_learning(viewer_user):
    assert not check_skill_learning_write_permission(
        viewer_user,
        agent_owner_id=viewer_user.user_id,
    )


def test_admin_can_delete_any_skill_learning(admin_user):
    assert check_skill_learning_delete_permission(admin_user, agent_owner_id=str(uuid4()))


def test_owner_can_delete_owned_skill_learning(regular_user):
    assert check_skill_learning_delete_permission(
        regular_user,
        agent_owner_id=regular_user.user_id,
    )


def test_user_cannot_delete_other_users_skill_learning(regular_user):
    assert not check_skill_learning_delete_permission(regular_user, agent_owner_id=str(uuid4()))
