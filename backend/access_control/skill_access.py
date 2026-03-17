"""Skill visibility and sharing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence
from uuid import UUID

from database.connection import get_db_session
from database.models import Department, User


SKILL_ACCESS_PRIVATE = "private"
SKILL_ACCESS_TEAM = "team"
SKILL_ACCESS_PUBLIC = "public"


@dataclass(frozen=True)
class SkillAccessContext:
    """Resolved skill access context for one user."""

    user_id: str
    role: str
    department_id: Optional[str]
    department_ancestor_ids: tuple[str, ...]
    manageable_department_ids: tuple[str, ...]

    @property
    def is_admin(self) -> bool:
        return str(self.role).strip().lower() == "admin"

    @property
    def is_manager(self) -> bool:
        return str(self.role).strip().lower() == "manager"


@dataclass(frozen=True)
class ShareTarget:
    department_id: str
    name: str


def _normalize_uuid_str(value: object) -> Optional[str]:
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError):
        return None


def get_department_ancestor_ids(session, department_id: object) -> List[str]:
    """Return one department id plus all ancestors up to the root."""
    current_id = _normalize_uuid_str(department_id)
    if not current_id:
        return []

    ancestor_ids: List[str] = []
    seen: set[str] = set()
    while current_id and current_id not in seen:
        seen.add(current_id)
        ancestor_ids.append(current_id)
        row = (
            session.query(Department.parent_id)
            .filter(Department.department_id == UUID(current_id))
            .first()
        )
        current_id = _normalize_uuid_str(row[0]) if row else None
    return ancestor_ids


def get_department_subtree_ids(session, department_id: object) -> List[str]:
    """Return one department id plus all descendant departments."""
    root_id = _normalize_uuid_str(department_id)
    if not root_id:
        return []

    subtree_ids: List[str] = []
    queue: List[str] = [root_id]
    seen: set[str] = set()

    while queue:
        current_id = queue.pop(0)
        if current_id in seen:
            continue
        seen.add(current_id)
        subtree_ids.append(current_id)
        child_rows = (
            session.query(Department.department_id)
            .filter(Department.parent_id == UUID(current_id))
            .all()
        )
        queue.extend(
            child_id
            for (raw_child_id,) in child_rows
            if (child_id := _normalize_uuid_str(raw_child_id)) is not None
        )

    return subtree_ids


def build_skill_access_context_for_user_id(session, *, user_id: str, role: str) -> SkillAccessContext:
    """Resolve department context used by skill visibility and sharing rules."""
    normalized_user_id = _normalize_uuid_str(user_id)
    user = None
    if normalized_user_id:
        user = session.query(User).filter(User.user_id == UUID(normalized_user_id)).first()

    department_id = _normalize_uuid_str(getattr(user, "department_id", None))
    ancestor_ids = tuple(get_department_ancestor_ids(session, department_id))

    manageable_ids: set[str] = set()
    managed_roots = (
        session.query(Department.department_id)
        .filter(Department.manager_id == UUID(normalized_user_id))
        .all()
        if normalized_user_id
        else []
    )
    for (raw_department_id,) in managed_roots:
        manageable_ids.update(get_department_subtree_ids(session, raw_department_id))
    if department_id and not manageable_ids:
        manageable_ids.add(department_id)

    return SkillAccessContext(
        user_id=str(user_id),
        role=str(role or ""),
        department_id=department_id,
        department_ancestor_ids=ancestor_ids,
        manageable_department_ids=tuple(sorted(manageable_ids)),
    )


def build_skill_access_context(current_user) -> SkillAccessContext:
    """Resolve a skill access context from a CurrentUser."""
    with get_db_session() as session:
        return build_skill_access_context_for_user_id(
            session,
            user_id=str(current_user.user_id),
            role=str(current_user.role),
        )


def _skill_owner_id(skill: object) -> Optional[str]:
    return _normalize_uuid_str(getattr(skill, "created_by", None))


def can_read_skill(skill: object, context: SkillAccessContext) -> bool:
    """Return whether the user can view the skill."""
    if skill is None:
        return False
    if context.is_admin:
        return True
    if _skill_owner_id(skill) == context.user_id:
        return True

    access_level = str(getattr(skill, "access_level", SKILL_ACCESS_PRIVATE) or "").strip().lower()
    if access_level == SKILL_ACCESS_PUBLIC:
        return True
    if access_level == SKILL_ACCESS_TEAM:
        department_id = _normalize_uuid_str(getattr(skill, "department_id", None))
        return bool(department_id and department_id in context.department_ancestor_ids)
    return False


def can_execute_skill(skill: object, context: SkillAccessContext) -> bool:
    """Execution follows the same visibility scope as reads."""
    return can_read_skill(skill, context)


def can_update_skill(skill: object, context: SkillAccessContext) -> bool:
    if skill is None:
        return False
    return context.is_admin or _skill_owner_id(skill) == context.user_id


def can_delete_skill(skill: object, context: SkillAccessContext) -> bool:
    return can_update_skill(skill, context)


def can_set_public_skill(*, owner_user_id: object, context: SkillAccessContext) -> bool:
    owner_id = _normalize_uuid_str(owner_user_id)
    if context.is_admin:
        return True
    return context.is_manager and owner_id == context.user_id


def get_allowed_team_department_ids(context: SkillAccessContext) -> Sequence[str]:
    """Return allowed department ids for team-scoped skills."""
    if context.is_admin:
        return ()
    return context.manageable_department_ids


def list_allowed_share_targets(context: SkillAccessContext) -> List[ShareTarget]:
    """List department targets available for team-shared skills."""
    with get_db_session() as session:
        query = session.query(Department).filter(Department.status == "active")

        if context.is_admin:
            departments = query.order_by(Department.sort_order, Department.name).all()
        else:
            allowed_ids = list(get_allowed_team_department_ids(context))
            if not allowed_ids:
                return []
            departments = (
                query.filter(Department.department_id.in_([UUID(item) for item in allowed_ids]))
                .order_by(Department.sort_order, Department.name)
                .all()
            )

    return [
        ShareTarget(department_id=str(department.department_id), name=department.name)
        for department in departments
    ]


def validate_team_skill_target(*, context: SkillAccessContext, department_id: object) -> str:
    """Validate and normalize one department id for a team-scoped skill."""
    normalized_department_id = _normalize_uuid_str(department_id) or _normalize_uuid_str(
        context.department_id
    )
    if not normalized_department_id:
        raise ValueError("department_id is required for team skills")

    with get_db_session() as session:
        department = (
            session.query(Department)
            .filter(Department.department_id == UUID(normalized_department_id))
            .first()
        )
        if department is None or str(department.status or "") != "active":
            raise ValueError("department_id does not reference an active department")

    if context.is_admin:
        return normalized_department_id

    if normalized_department_id not in set(get_allowed_team_department_ids(context)):
        raise PermissionError("department_id is outside the user's allowed team scope")

    return normalized_department_id


def filter_readable_skills(skills: Iterable[object], context: SkillAccessContext) -> List[object]:
    """Filter a skill collection down to readable items."""
    return [skill for skill in skills if can_read_skill(skill, context)]
