"""Admin User Management Endpoints for API Gateway.

Provides CRUD operations for user administration including
listing, creating, updating, disabling, and deleting users.

References:
- Requirements 14: User-Based Access Control
- Design Section 8: Access Control System
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


class AdminUserResponse(BaseModel):
    """Admin user detail response."""

    user_id: str
    username: str
    email: str
    role: str
    department_id: Optional[str] = None
    department_name: Optional[str] = None
    is_disabled: bool = False
    display_name: Optional[str] = None
    created_at: str
    updated_at: str


class AdminUserListResponse(BaseModel):
    """Paginated user list response."""

    users: List[AdminUserResponse]
    total: int
    page: int
    page_size: int


class CreateUserRequest(BaseModel):
    """Create user request."""

    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)
    role: str = Field(default="user", pattern=r"^(admin|manager|user|viewer)$")
    department_id: Optional[UUID] = None


class UpdateUserRequest(BaseModel):
    """Update user request."""

    email: Optional[str] = None
    role: Optional[str] = Field(None, pattern=r"^(admin|manager|user|viewer)$")
    department_id: Optional[UUID] = None
    is_disabled: Optional[bool] = None


class ResetPasswordRequest(BaseModel):
    """Reset password request."""

    new_password: str = Field(..., min_length=8)


class BatchActionRequest(BaseModel):
    """Batch action request."""

    user_ids: List[UUID]
    action: str = Field(..., pattern=r"^(disable|enable|delete|change_role)$")
    role: Optional[str] = Field(None, pattern=r"^(admin|manager|user|viewer)$")


# ─── Helper Functions ────────────────────────────────────────────────────────


def _user_to_response(user) -> AdminUserResponse:
    """Convert a User model to AdminUserResponse."""
    attrs = user.attributes or {}
    dept_name = None
    if user.department:
        dept_name = user.department.name

    return AdminUserResponse(
        user_id=str(user.user_id),
        username=user.username,
        email=user.email,
        role=user.role,
        department_id=str(user.department_id) if user.department_id else None,
        department_name=dept_name,
        is_disabled=attrs.get("is_disabled", False),
        display_name=attrs.get("display_name"),
        created_at=user.created_at.isoformat() if user.created_at else "",
        updated_at=user.updated_at.isoformat() if user.updated_at else "",
    )


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("", response_model=AdminUserListResponse)
@require_role([Role.ADMIN, Role.MANAGER])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=100),
    role_filter: Optional[str] = Query(None, alias="role"),
    department_id: Optional[UUID] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status", pattern=r"^(active|disabled)$"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List users with pagination, search, and filtering.

    Managers see only users in their own department.
    """
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        query = session.query(User)

        # Managers can only see their own department's users
        if current_user.role == Role.MANAGER.value:
            me = session.query(User).filter(User.user_id == current_user.user_id).first()
            if me and me.department_id:
                query = query.filter(User.department_id == me.department_id)
            else:
                # Manager without department sees only self
                query = query.filter(User.user_id == current_user.user_id)

        # Search by username or email
        if search:
            query = query.filter(
                User.username.ilike(f"%{search}%") | User.email.ilike(f"%{search}%")
            )

        # Filter by role
        if role_filter:
            query = query.filter(User.role == role_filter)

        # Filter by department
        if department_id:
            query = query.filter(User.department_id == department_id)

        # Filter by status (active/disabled)
        if status_filter == "disabled":
            query = query.filter(User.attributes["is_disabled"].astext == "true")
        elif status_filter == "active":
            query = query.filter(
                (User.attributes["is_disabled"].astext != "true")
                | (User.attributes["is_disabled"].is_(None))
            )

        # Get total count
        total = query.count()

        # Pagination
        offset = (page - 1) * page_size
        users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

        return AdminUserListResponse(
            users=[_user_to_response(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
        )


@router.get("/{user_id}", response_model=AdminUserResponse)
@require_role([Role.ADMIN, Role.MANAGER])
async def get_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get user detail by ID."""
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Managers can only see users in their own department
        if current_user.role == Role.MANAGER.value:
            me = session.query(User).filter(User.user_id == current_user.user_id).first()
            if not me or str(me.department_id) != str(user.department_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Managers can only view users in their own department",
                )

        return _user_to_response(user)


@router.post("", response_model=AdminUserResponse, status_code=status.HTTP_201_CREATED)
@require_role([Role.ADMIN])
async def create_user(
    request: CreateUserRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new user. Admin only."""
    from access_control.audit_logger import AuditEventType, log_user_management_event
    from access_control.registration import (
        DuplicateUserError,
        RegistrationError,
    )
    from access_control.registration import ValidationError as RegValidationError
    from access_control.registration import (
        register_user_admin,
    )
    from database.connection import get_db_session
    from database.models import Department, User

    with get_db_session() as session:
        # Validate department_id if provided
        if request.department_id:
            dept = (
                session.query(Department)
                .filter(Department.department_id == request.department_id)
                .first()
            )
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department not found",
                )

        try:
            reg_response = register_user_admin(
                session=session,
                username=request.username,
                email=request.email,
                password=request.password,
                role=request.role,
            )
        except DuplicateUserError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        except RegValidationError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(e))
        except RegistrationError as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

        # Set department if provided
        if request.department_id:
            user = session.query(User).filter(User.user_id == reg_response.user_id).first()
            if user:
                user.department_id = request.department_id

        session.commit()

        # Fetch full user for response
        user = session.query(User).filter(User.user_id == reg_response.user_id).first()

        # Audit log
        log_user_management_event(
            session=session,
            event_type=AuditEventType.USER_CREATED,
            target_user_id=str(user.user_id),
            target_username=user.username,
            performed_by_user_id=current_user.user_id,
            role=user.role,
        )
        session.commit()

        logger.info(
            "Admin created user",
            extra={
                "user_id": str(user.user_id),
                "username": user.username,
                "created_by": current_user.user_id,
            },
        )

        return _user_to_response(user)


@router.put("/{user_id}", response_model=AdminUserResponse)
@require_role([Role.ADMIN])
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a user. Admin only."""
    from sqlalchemy.orm.attributes import flag_modified

    from access_control.audit_logger import AuditEventType, log_user_management_event
    from database.connection import get_db_session
    from database.models import Department, User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Update email
        if request.email is not None:
            existing = (
                session.query(User)
                .filter(User.email == request.email, User.user_id != user_id)
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already in use",
                )
            user.email = request.email

        # Update role
        if request.role is not None:
            user.role = request.role

        # Update department
        if request.department_id is not None:
            dept = (
                session.query(Department)
                .filter(Department.department_id == request.department_id)
                .first()
            )
            if not dept:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Department not found",
                )
            user.department_id = request.department_id

        # Update disabled status
        if request.is_disabled is not None:
            attrs = dict(user.attributes) if user.attributes else {}
            attrs["is_disabled"] = request.is_disabled
            user.attributes = attrs
            flag_modified(user, "attributes")

        session.commit()
        session.refresh(user)

        # Audit log
        log_user_management_event(
            session=session,
            event_type=AuditEventType.USER_UPDATED,
            target_user_id=str(user.user_id),
            target_username=user.username,
            performed_by_user_id=current_user.user_id,
            role=user.role,
        )
        session.commit()

        logger.info(
            "Admin updated user",
            extra={
                "user_id": str(user.user_id),
                "updated_by": current_user.user_id,
            },
        )

        return _user_to_response(user)


@router.put("/{user_id}/reset-password", status_code=status.HTTP_200_OK)
@require_role([Role.ADMIN])
async def reset_password(
    user_id: UUID,
    request: ResetPasswordRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Reset a user's password. Admin only."""
    from access_control.audit_logger import AuditEventType, log_user_management_event
    from access_control.models import hash_password
    from database.connection import get_db_session
    from database.models import User

    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        user.password_hash = hash_password(request.new_password)
        session.commit()

        # Audit log
        log_user_management_event(
            session=session,
            event_type=AuditEventType.USER_UPDATED,
            target_user_id=str(user.user_id),
            target_username=user.username,
            performed_by_user_id=current_user.user_id,
            details={"action": "reset_password"},
        )
        session.commit()

        logger.info(
            "Admin reset user password",
            extra={
                "user_id": str(user.user_id),
                "reset_by": current_user.user_id,
            },
        )

        return {"message": "Password reset successfully"}


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_role([Role.ADMIN])
async def delete_user(
    user_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a user. Admin only. Cannot delete self."""
    from access_control.audit_logger import AuditEventType, log_user_management_event
    from database.connection import get_db_session
    from database.models import User

    # Prevent self-deletion
    if str(user_id) == str(current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account",
        )

    user_memory_cleanup = None
    with get_db_session() as session:
        user = session.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        username = user.username

        # Audit log before deletion
        log_user_management_event(
            session=session,
            event_type=AuditEventType.USER_DELETED,
            target_user_id=str(user.user_id),
            target_username=username,
            performed_by_user_id=current_user.user_id,
        )

        from user_memory.storage_cleanup import prepare_user_memory_rows_for_user_deletion

        user_memory_cleanup = prepare_user_memory_rows_for_user_deletion(
            session,
            user_id=str(user.user_id),
        )
        session.delete(user)
        session.commit()

    logger.info(
        "Admin deleted user",
        extra={
            "user_id": str(user_id),
            "username": username,
            "deleted_by": current_user.user_id,
            "user_memory_entries_deleted": len((user_memory_cleanup or {}).get("entry_ids") or []),
            "user_memory_relations_deleted": (user_memory_cleanup or {}).get("memory_relations"),
            "user_memory_views_deleted": (user_memory_cleanup or {}).get("memory_views"),
            "skill_candidates_deleted": (user_memory_cleanup or {}).get("skill_candidates"),
            "session_ledgers_deleted": (user_memory_cleanup or {}).get("session_ledgers"),
            "user_memory_vector_delete_job_enqueued": (
                user_memory_cleanup or {}
            ).get("vector_delete_job_enqueued"),
        },
    )


@router.post("/batch", status_code=status.HTTP_200_OK)
@require_role([Role.ADMIN])
async def batch_action(
    request: BatchActionRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Perform batch actions on users. Admin only."""
    from sqlalchemy.orm.attributes import flag_modified

    from access_control.audit_logger import AuditEventType, log_user_management_event
    from database.connection import get_db_session
    from database.models import User

    if request.action == "change_role" and not request.role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role is required for change_role action",
        )

    with get_db_session() as session:
        users = session.query(User).filter(User.user_id.in_(request.user_ids)).all()
        if not users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No users found",
            )

        processed = 0
        skipped = 0
        for user in users:
            # Skip self for destructive actions
            if str(user.user_id) == str(current_user.user_id):
                skipped += 1
                continue

            if request.action == "disable":
                attrs = dict(user.attributes) if user.attributes else {}
                attrs["is_disabled"] = True
                user.attributes = attrs
                flag_modified(user, "attributes")
                processed += 1

            elif request.action == "enable":
                attrs = dict(user.attributes) if user.attributes else {}
                attrs["is_disabled"] = False
                user.attributes = attrs
                flag_modified(user, "attributes")
                processed += 1

            elif request.action == "delete":
                log_user_management_event(
                    session=session,
                    event_type=AuditEventType.USER_DELETED,
                    target_user_id=str(user.user_id),
                    target_username=user.username,
                    performed_by_user_id=current_user.user_id,
                )
                from user_memory.storage_cleanup import prepare_user_memory_rows_for_user_deletion

                cleanup_summary = prepare_user_memory_rows_for_user_deletion(
                    session,
                    user_id=str(user.user_id),
                )
                session.delete(user)
                processed += 1

            elif request.action == "change_role":
                user.role = request.role
                processed += 1

        session.commit()

    logger.info(
        "Admin batch action completed",
        extra={
            "action": request.action,
            "processed": processed,
            "skipped": skipped,
            "performed_by": current_user.user_id,
        },
    )

    return {
        "action": request.action,
        "processed": processed,
        "skipped": skipped,
    }
