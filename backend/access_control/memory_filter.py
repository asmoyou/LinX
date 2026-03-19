"""Access checks for reset-era skill-learning data."""

import logging
from typing import Optional

from access_control.permissions import CurrentUser
from access_control.rbac import Action, ResourceType, Role, check_permission

logger = logging.getLogger(__name__)


def _coerce_role(current_user: CurrentUser) -> Optional[Role]:
    try:
        return Role(current_user.role)
    except ValueError:
        logger.warning("Invalid role for skill-learning access: %s", current_user.role)
        return None


def can_access_skill_learning(
    current_user: CurrentUser,
    agent_id: str,
    agent_owner_id: str,
    action: Action = Action.READ,
) -> bool:
    """Check whether a user can access skill candidates for an agent."""

    role = _coerce_role(current_user)
    if role is None:
        return False

    if check_permission(role, ResourceType.MEMORY, action, None):
        logger.debug(
            "User %s granted unrestricted skill-learning access",
            current_user.user_id,
            extra={"user_id": current_user.user_id, "agent_id": agent_id},
        )
        return True

    if str(agent_owner_id) == str(current_user.user_id) and check_permission(
        role, ResourceType.MEMORY, action, "own"
    ):
        logger.debug(
            "User %s granted owned skill-learning access",
            current_user.user_id,
            extra={"user_id": current_user.user_id, "agent_id": agent_id},
        )
        return True

    logger.debug(
        "User %s denied skill-learning access",
        current_user.user_id,
        extra={
            "user_id": current_user.user_id,
            "agent_id": agent_id,
            "agent_owner_id": agent_owner_id,
        },
    )
    return False


def check_skill_learning_write_permission(
    current_user: CurrentUser,
    *,
    agent_owner_id: Optional[str] = None,
) -> bool:
    """Check whether a user can create/update skill-learning rows."""

    role = _coerce_role(current_user)
    if role is None:
        return False

    if check_permission(role, ResourceType.MEMORY, Action.CREATE, None):
        return True

    return bool(
        agent_owner_id
        and str(agent_owner_id) == str(current_user.user_id)
        and check_permission(role, ResourceType.MEMORY, Action.CREATE, "own")
    )


def check_skill_learning_delete_permission(
    current_user: CurrentUser,
    *,
    agent_owner_id: Optional[str] = None,
) -> bool:
    """Check whether a user can delete skill-learning rows."""

    role = _coerce_role(current_user)
    if role is None:
        return False

    if check_permission(role, ResourceType.MEMORY, Action.DELETE, None):
        return True

    return bool(
        agent_owner_id
        and str(agent_owner_id) == str(current_user.user_id)
        and check_permission(role, ResourceType.MEMORY, Action.DELETE, "own")
    )


__all__ = [
    "can_access_skill_learning",
    "check_skill_learning_delete_permission",
    "check_skill_learning_write_permission",
]
