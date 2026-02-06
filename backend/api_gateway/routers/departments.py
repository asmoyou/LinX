"""Department Management Endpoints for API Gateway.

Provides CRUD operations for departments, member/agent listing,
and department statistics.

References:
- Spec: .kiro/specs/department-management/
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from access_control.permissions import CurrentUser, get_current_user, require_role
from access_control.rbac import Role
from shared.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


# ─── Pydantic Schemas ───────────────────────────────────────────────────────


class DepartmentCreate(BaseModel):
    """Create department request."""

    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    sort_order: int = 0


class DepartmentUpdate(BaseModel):
    """Update department request."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    parent_id: Optional[UUID] = None
    manager_id: Optional[UUID] = None
    status: Optional[str] = Field(None, pattern=r"^(active|archived)$")
    sort_order: Optional[int] = None


class DepartmentResponse(BaseModel):
    """Department response model."""

    department_id: str
    name: str
    code: str
    description: Optional[str] = None
    parent_id: Optional[str] = None
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    status: str
    sort_order: int
    member_count: int = 0
    agent_count: int = 0
    knowledge_count: int = 0
    children: List["DepartmentResponse"] = []
    created_at: str
    updated_at: str


class DepartmentStats(BaseModel):
    """Department statistics."""

    member_count: int
    agent_count: int
    knowledge_count: int
    active_task_count: int


class MemberResponse(BaseModel):
    """Department member response."""

    user_id: str
    username: str
    email: str
    role: str
    display_name: Optional[str] = None


class AgentResponse(BaseModel):
    """Department agent response."""

    agent_id: str
    name: str
    agent_type: str
    status: str
    access_level: Optional[str] = None
    owner_username: Optional[str] = None


# ─── Helper Functions ────────────────────────────────────────────────────────


def _department_to_response(dept, member_count: int = 0, agent_count: int = 0,
                            knowledge_count: int = 0) -> dict:
    """Convert Department model to response dict."""
    manager_name = None
    if dept.manager:
        attrs = dept.manager.attributes or {}
        manager_name = attrs.get("display_name") or dept.manager.username

    return {
        "department_id": str(dept.department_id),
        "name": dept.name,
        "code": dept.code,
        "description": dept.description,
        "parent_id": str(dept.parent_id) if dept.parent_id else None,
        "manager_id": str(dept.manager_id) if dept.manager_id else None,
        "manager_name": manager_name,
        "status": dept.status,
        "sort_order": dept.sort_order,
        "member_count": member_count,
        "agent_count": agent_count,
        "knowledge_count": knowledge_count,
        "children": [],
        "created_at": dept.created_at.isoformat() if dept.created_at else "",
        "updated_at": dept.updated_at.isoformat() if dept.updated_at else "",
    }


def _build_tree(departments: list, counts: dict) -> List[dict]:
    """Build tree structure from flat department list."""
    dept_map = {}
    roots = []

    for dept in departments:
        dept_id = str(dept.department_id)
        c = counts.get(dept_id, {})
        node = _department_to_response(
            dept,
            member_count=c.get("members", 0),
            agent_count=c.get("agents", 0),
            knowledge_count=c.get("knowledge", 0),
        )
        dept_map[dept_id] = node

    for dept in departments:
        dept_id = str(dept.department_id)
        parent_id = str(dept.parent_id) if dept.parent_id else None
        if parent_id and parent_id in dept_map:
            dept_map[parent_id]["children"].append(dept_map[dept_id])
        else:
            roots.append(dept_map[dept_id])

    return roots


def _get_counts(session, department_ids: list) -> dict:
    """Get member/agent/knowledge counts per department."""
    from sqlalchemy import func as sqlfunc

    from database.models import Agent, KnowledgeItem, User

    counts = {str(did): {"members": 0, "agents": 0, "knowledge": 0} for did in department_ids}

    # Member counts
    member_rows = (
        session.query(User.department_id, sqlfunc.count(User.user_id))
        .filter(User.department_id.in_(department_ids))
        .group_by(User.department_id)
        .all()
    )
    for dept_id, cnt in member_rows:
        counts[str(dept_id)]["members"] = cnt

    # Agent counts
    agent_rows = (
        session.query(Agent.department_id, sqlfunc.count(Agent.agent_id))
        .filter(Agent.department_id.in_(department_ids))
        .group_by(Agent.department_id)
        .all()
    )
    for dept_id, cnt in agent_rows:
        counts[str(dept_id)]["agents"] = cnt

    # Knowledge counts
    knowledge_rows = (
        session.query(KnowledgeItem.department_id, sqlfunc.count(KnowledgeItem.knowledge_id))
        .filter(KnowledgeItem.department_id.in_(department_ids))
        .group_by(KnowledgeItem.department_id)
        .all()
    )
    for dept_id, cnt in knowledge_rows:
        counts[str(dept_id)]["knowledge"] = cnt

    return counts


# ─── CRUD Endpoints ──────────────────────────────────────────────────────────


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
@require_role([Role.ADMIN])
async def create_department(
    request: DepartmentCreate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new department. Admin only."""
    from database.connection import get_db_session
    from database.models import Department, User

    with get_db_session() as session:
        # Check code uniqueness
        existing = session.query(Department).filter(Department.code == request.code).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Department code '{request.code}' already exists",
            )

        # Validate parent_id
        if request.parent_id:
            parent = (
                session.query(Department)
                .filter(Department.department_id == request.parent_id)
                .first()
            )
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Parent department not found",
                )

        # Validate manager_id
        if request.manager_id:
            manager = (
                session.query(User).filter(User.user_id == request.manager_id).first()
            )
            if not manager:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Manager user not found",
                )

        dept = Department(
            name=request.name,
            code=request.code,
            description=request.description,
            parent_id=request.parent_id,
            manager_id=request.manager_id,
            sort_order=request.sort_order,
        )
        session.add(dept)
        session.commit()
        session.refresh(dept)

        logger.info(
            "Department created",
            extra={"department_id": str(dept.department_id), "code": dept.code},
        )

        return DepartmentResponse(**_department_to_response(dept))


@router.get("", response_model=List[DepartmentResponse])
async def list_departments(
    view: str = Query("flat", pattern="^(flat|tree)$"),
    status_filter: Optional[str] = Query(None, alias="status", pattern="^(active|archived)$"),
    search: Optional[str] = Query(None, max_length=100),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all departments. Supports flat and tree view."""
    from database.connection import get_db_session
    from database.models import Department

    with get_db_session() as session:
        query = session.query(Department)

        if status_filter:
            query = query.filter(Department.status == status_filter)

        if search:
            query = query.filter(
                Department.name.ilike(f"%{search}%")
                | Department.code.ilike(f"%{search}%")
            )

        query = query.order_by(Department.sort_order, Department.name)
        departments = query.all()

        if not departments:
            return []

        dept_ids = [d.department_id for d in departments]
        counts = _get_counts(session, dept_ids)

        if view == "tree":
            tree = _build_tree(departments, counts)
            return [DepartmentResponse(**node) for node in tree]

        result = []
        for dept in departments:
            did = str(dept.department_id)
            c = counts.get(did, {})
            result.append(
                DepartmentResponse(
                    **_department_to_response(
                        dept,
                        member_count=c.get("members", 0),
                        agent_count=c.get("agents", 0),
                        knowledge_count=c.get("knowledge", 0),
                    )
                )
            )
        return result


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get department detail with resource counts."""
    from database.connection import get_db_session
    from database.models import Department

    with get_db_session() as session:
        dept = (
            session.query(Department)
            .filter(Department.department_id == department_id)
            .first()
        )
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found",
            )

        counts = _get_counts(session, [department_id])
        c = counts.get(str(department_id), {})

        return DepartmentResponse(
            **_department_to_response(
                dept,
                member_count=c.get("members", 0),
                agent_count=c.get("agents", 0),
                knowledge_count=c.get("knowledge", 0),
            )
        )


@router.put("/{department_id}", response_model=DepartmentResponse)
@require_role([Role.ADMIN])
async def update_department(
    department_id: UUID,
    request: DepartmentUpdate,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a department. Admin only. Code is immutable."""
    from database.connection import get_db_session
    from database.models import Department, User

    with get_db_session() as session:
        dept = (
            session.query(Department)
            .filter(Department.department_id == department_id)
            .first()
        )
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found",
            )

        # Validate parent_id (prevent circular reference)
        if request.parent_id is not None:
            if request.parent_id == department_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department cannot be its own parent",
                )
            if request.parent_id:
                parent = (
                    session.query(Department)
                    .filter(Department.department_id == request.parent_id)
                    .first()
                )
                if not parent:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Parent department not found",
                    )

        # Validate manager_id
        if request.manager_id is not None and request.manager_id:
            manager = (
                session.query(User).filter(User.user_id == request.manager_id).first()
            )
            if not manager:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Manager user not found",
                )

        # Apply updates
        if request.name is not None:
            dept.name = request.name
        if request.description is not None:
            dept.description = request.description
        if request.parent_id is not None:
            dept.parent_id = request.parent_id or None
        if request.manager_id is not None:
            dept.manager_id = request.manager_id or None
        if request.status is not None:
            dept.status = request.status
        if request.sort_order is not None:
            dept.sort_order = request.sort_order

        session.commit()
        session.refresh(dept)

        counts = _get_counts(session, [department_id])
        c = counts.get(str(department_id), {})

        logger.info(
            "Department updated",
            extra={"department_id": str(department_id)},
        )

        return DepartmentResponse(
            **_department_to_response(
                dept,
                member_count=c.get("members", 0),
                agent_count=c.get("agents", 0),
                knowledge_count=c.get("knowledge", 0),
            )
        )


@router.delete("/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_role([Role.ADMIN])
async def delete_department(
    department_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete an empty department. Admin only."""
    from database.connection import get_db_session
    from database.models import Agent, Department, KnowledgeItem, User

    with get_db_session() as session:
        dept = (
            session.query(Department)
            .filter(Department.department_id == department_id)
            .first()
        )
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found",
            )

        # Check for associated resources
        member_count = (
            session.query(User).filter(User.department_id == department_id).count()
        )
        agent_count = (
            session.query(Agent).filter(Agent.department_id == department_id).count()
        )
        knowledge_count = (
            session.query(KnowledgeItem)
            .filter(KnowledgeItem.department_id == department_id)
            .count()
        )
        child_count = (
            session.query(Department)
            .filter(Department.parent_id == department_id)
            .count()
        )

        if member_count + agent_count + knowledge_count + child_count > 0:
            details = []
            if member_count:
                details.append(f"{member_count} members")
            if agent_count:
                details.append(f"{agent_count} agents")
            if knowledge_count:
                details.append(f"{knowledge_count} knowledge items")
            if child_count:
                details.append(f"{child_count} child departments")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot delete department with associated resources: {', '.join(details)}",
            )

        session.delete(dept)
        session.commit()

        logger.info(
            "Department deleted",
            extra={"department_id": str(department_id), "code": dept.code},
        )


# ─── Resource Endpoints ──────────────────────────────────────────────────────


@router.get("/{department_id}/members", response_model=List[MemberResponse])
@require_role([Role.ADMIN, Role.MANAGER])
async def get_department_members(
    department_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List members of a department. Admin or manager only."""
    from database.connection import get_db_session
    from database.models import Department, User

    with get_db_session() as session:
        dept = (
            session.query(Department)
            .filter(Department.department_id == department_id)
            .first()
        )
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found",
            )

        # Managers can only see their own department
        if current_user.role == Role.MANAGER.value:
            user = (
                session.query(User)
                .filter(User.user_id == current_user.user_id)
                .first()
            )
            if not user or str(user.department_id) != str(department_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers can only view their own department members",
                )

        members = (
            session.query(User)
            .filter(User.department_id == department_id)
            .order_by(User.username)
            .all()
        )

        result = []
        for m in members:
            attrs = m.attributes or {}
            result.append(
                MemberResponse(
                    user_id=str(m.user_id),
                    username=m.username,
                    email=m.email,
                    role=m.role,
                    display_name=attrs.get("display_name"),
                )
            )
        return result


@router.get("/{department_id}/agents", response_model=List[AgentResponse])
@require_role([Role.ADMIN, Role.MANAGER])
async def get_department_agents(
    department_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """List agents of a department. Admin or manager only."""
    from database.connection import get_db_session
    from database.models import Agent, Department, User

    with get_db_session() as session:
        dept = (
            session.query(Department)
            .filter(Department.department_id == department_id)
            .first()
        )
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found",
            )

        # Managers can only see their own department
        if current_user.role == Role.MANAGER.value:
            user = (
                session.query(User)
                .filter(User.user_id == current_user.user_id)
                .first()
            )
            if not user or str(user.department_id) != str(department_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers can only view their own department agents",
                )

        agents = (
            session.query(Agent)
            .filter(Agent.department_id == department_id)
            .order_by(Agent.name)
            .all()
        )

        result = []
        for a in agents:
            owner_username = None
            if a.owner:
                owner_username = a.owner.username
            result.append(
                AgentResponse(
                    agent_id=str(a.agent_id),
                    name=a.name,
                    agent_type=a.agent_type,
                    status=a.status,
                    access_level=a.access_level,
                    owner_username=owner_username,
                )
            )
        return result


@router.get("/{department_id}/stats", response_model=DepartmentStats)
@require_role([Role.ADMIN, Role.MANAGER])
async def get_department_stats(
    department_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get department statistics. Admin or manager only."""
    from database.connection import get_db_session
    from database.models import Agent, Department, KnowledgeItem, Task, User

    with get_db_session() as session:
        dept = (
            session.query(Department)
            .filter(Department.department_id == department_id)
            .first()
        )
        if not dept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Department not found",
            )

        # Managers can only see their own department
        if current_user.role == Role.MANAGER.value:
            user = (
                session.query(User)
                .filter(User.user_id == current_user.user_id)
                .first()
            )
            if not user or str(user.department_id) != str(department_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers can only view their own department stats",
                )

        member_count = (
            session.query(User).filter(User.department_id == department_id).count()
        )
        agent_count = (
            session.query(Agent).filter(Agent.department_id == department_id).count()
        )
        knowledge_count = (
            session.query(KnowledgeItem)
            .filter(KnowledgeItem.department_id == department_id)
            .count()
        )

        # Active tasks: tasks created by department members that are in_progress
        dept_user_ids = (
            session.query(User.user_id)
            .filter(User.department_id == department_id)
            .subquery()
        )
        active_task_count = (
            session.query(Task)
            .filter(
                Task.created_by_user_id.in_(dept_user_ids),
                Task.status == "in_progress",
            )
            .count()
        )

        return DepartmentStats(
            member_count=member_count,
            agent_count=agent_count,
            knowledge_count=knowledge_count,
            active_task_count=active_task_count,
        )
