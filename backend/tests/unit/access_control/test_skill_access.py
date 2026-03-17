"""Unit tests for skill visibility and share-target access rules."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from access_control.skill_access import (
    SKILL_ACCESS_PRIVATE,
    SKILL_ACCESS_PUBLIC,
    SKILL_ACCESS_TEAM,
    SkillAccessContext,
    can_read_skill,
    can_set_public_skill,
    validate_team_skill_target,
)


class _FakeDepartmentQuery:
    def __init__(self, department):
        self._department = department

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self._department


class _FakeDepartmentSession:
    def __init__(self, department):
        self._department = department

    def query(self, _model):
        return _FakeDepartmentQuery(self._department)


class _FakeDepartmentSessionContext:
    def __init__(self, department):
        self._department = department

    def __enter__(self):
        return _FakeDepartmentSession(self._department)

    def __exit__(self, *_args):
        return False


def _skill(*, created_by: str, access_level: str, department_id: str | None = None):
    return SimpleNamespace(
        created_by=created_by,
        access_level=access_level,
        department_id=department_id,
    )


def test_private_skill_is_only_visible_to_owner_or_admin():
    owner_id = str(uuid4())
    other_id = str(uuid4())
    skill = _skill(created_by=owner_id, access_level=SKILL_ACCESS_PRIVATE)

    owner_context = SkillAccessContext(
        user_id=owner_id,
        role="user",
        department_id=None,
        department_ancestor_ids=[],
        manageable_department_ids=[],
    )
    other_context = SkillAccessContext(
        user_id=other_id,
        role="user",
        department_id=None,
        department_ancestor_ids=[],
        manageable_department_ids=[],
    )
    admin_context = SkillAccessContext(
        user_id=other_id,
        role="admin",
        department_id=None,
        department_ancestor_ids=[],
        manageable_department_ids=[],
    )

    assert can_read_skill(skill, owner_context) is True
    assert can_read_skill(skill, other_context) is False
    assert can_read_skill(skill, admin_context) is True


def test_team_skill_is_visible_to_department_ancestor_chain():
    owner_id = str(uuid4())
    visible_department = str(uuid4())
    hidden_department = str(uuid4())
    skill = _skill(
        created_by=owner_id,
        access_level=SKILL_ACCESS_TEAM,
        department_id=visible_department,
    )

    visible_context = SkillAccessContext(
        user_id=str(uuid4()),
        role="user",
        department_id=str(uuid4()),
        department_ancestor_ids=[visible_department],
        manageable_department_ids=[],
    )
    hidden_context = SkillAccessContext(
        user_id=str(uuid4()),
        role="user",
        department_id=str(uuid4()),
        department_ancestor_ids=[hidden_department],
        manageable_department_ids=[],
    )

    assert can_read_skill(skill, visible_context) is True
    assert can_read_skill(skill, hidden_context) is False


def test_public_skill_is_visible_to_all_logged_in_users():
    skill = _skill(created_by=str(uuid4()), access_level=SKILL_ACCESS_PUBLIC)
    context = SkillAccessContext(
        user_id=str(uuid4()),
        role="user",
        department_id=None,
        department_ancestor_ids=[],
        manageable_department_ids=[],
    )

    assert can_read_skill(skill, context) is True


def test_manager_can_publish_only_owned_skills_publicly():
    owner_id = str(uuid4())
    manager_context = SkillAccessContext(
        user_id=owner_id,
        role="manager",
        department_id=None,
        department_ancestor_ids=[],
        manageable_department_ids=[],
    )
    non_owner_context = SkillAccessContext(
        user_id=str(uuid4()),
        role="manager",
        department_id=None,
        department_ancestor_ids=[],
        manageable_department_ids=[],
    )

    assert can_set_public_skill(owner_user_id=owner_id, context=manager_context) is True
    assert can_set_public_skill(owner_user_id=owner_id, context=non_owner_context) is False


def test_validate_team_skill_target_restricts_regular_user_to_own_department(monkeypatch):
    department_id = str(uuid4())
    other_department_id = str(uuid4())
    monkeypatch.setattr(
        "access_control.skill_access.get_db_session",
        lambda: _FakeDepartmentSessionContext(
            SimpleNamespace(department_id=department_id, status="active")
        ),
    )
    context = SkillAccessContext(
        user_id=str(uuid4()),
        role="user",
        department_id=department_id,
        department_ancestor_ids=[department_id],
        manageable_department_ids=[department_id],
    )

    assert validate_team_skill_target(context=context, department_id=None) == department_id
    assert validate_team_skill_target(context=context, department_id=department_id) == department_id
    with pytest.raises(PermissionError):
        validate_team_skill_target(context=context, department_id=other_department_id)
