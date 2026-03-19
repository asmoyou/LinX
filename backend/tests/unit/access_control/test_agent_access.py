from types import SimpleNamespace
from uuid import uuid4

from access_control.agent_access import (
    AGENT_ACCESS_DEPARTMENT,
    AGENT_ACCESS_PRIVATE,
    AGENT_ACCESS_PUBLIC,
    AgentAccessContext,
    can_execute_agent,
    can_manage_agent,
    can_read_agent,
    normalize_agent_access_level,
)


def _build_agent(
    *,
    owner_user_id=None,
    access_level: str = AGENT_ACCESS_PRIVATE,
    department_id=None,
):
    return SimpleNamespace(
        owner_user_id=owner_user_id or uuid4(),
        access_level=access_level,
        department_id=department_id,
    )


def _build_context(
    *,
    user_id,
    role: str = "user",
    department_id=None,
    department_ancestor_ids=(),
):
    return AgentAccessContext(
        user_id=str(user_id),
        role=role,
        department_id=str(department_id) if department_id else None,
        department_ancestor_ids=tuple(str(value) for value in department_ancestor_ids),
    )


def test_normalize_agent_access_level_maps_legacy_team_to_department():
    assert normalize_agent_access_level("team") == AGENT_ACCESS_DEPARTMENT
    assert normalize_agent_access_level("department") == AGENT_ACCESS_DEPARTMENT


def test_owner_can_read_execute_and_manage_private_agent():
    owner_id = uuid4()
    agent = _build_agent(owner_user_id=owner_id, access_level=AGENT_ACCESS_PRIVATE)
    context = _build_context(user_id=owner_id)

    assert can_read_agent(agent, context) is True
    assert can_execute_agent(agent, context) is True
    assert can_manage_agent(agent, context) is True


def test_public_agent_is_readable_and_executable_for_non_owner():
    agent = _build_agent(access_level=AGENT_ACCESS_PUBLIC)
    context = _build_context(user_id=uuid4())

    assert can_read_agent(agent, context) is True
    assert can_execute_agent(agent, context) is True
    assert can_manage_agent(agent, context) is False


def test_department_agent_is_accessible_from_child_department_context():
    root_department_id = uuid4()
    parent_department_id = uuid4()
    child_department_id = uuid4()
    agent = _build_agent(
        access_level=AGENT_ACCESS_DEPARTMENT,
        department_id=parent_department_id,
    )
    context = _build_context(
        user_id=uuid4(),
        department_id=child_department_id,
        department_ancestor_ids=[
            child_department_id,
            parent_department_id,
            root_department_id,
        ],
    )

    assert can_read_agent(agent, context) is True
    assert can_execute_agent(agent, context) is True


def test_department_agent_rejects_sibling_department_access():
    current_department_id = uuid4()
    sibling_department_id = uuid4()
    parent_department_id = uuid4()
    agent = _build_agent(
        access_level=AGENT_ACCESS_DEPARTMENT,
        department_id=sibling_department_id,
    )
    context = _build_context(
        user_id=uuid4(),
        department_id=current_department_id,
        department_ancestor_ids=[current_department_id, parent_department_id],
    )

    assert can_read_agent(agent, context) is False
    assert can_execute_agent(agent, context) is False
    assert can_manage_agent(agent, context) is False


def test_admin_can_manage_any_agent():
    agent = _build_agent(access_level=AGENT_ACCESS_PRIVATE)
    context = _build_context(user_id=uuid4(), role="admin")

    assert can_read_agent(agent, context) is True
    assert can_execute_agent(agent, context) is True
    assert can_manage_agent(agent, context) is True

