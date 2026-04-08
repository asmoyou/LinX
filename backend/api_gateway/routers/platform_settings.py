"""Platform-level settings endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status

from access_control.permissions import CurrentUser, get_current_user
from api_gateway.ui_experience import UiExperienceSettings
from pydantic import BaseModel, Field
from database.connection import get_db_session
from shared.platform_settings import get_project_execution_settings, get_ui_experience_settings, upsert_project_execution_settings, upsert_ui_experience_settings

router = APIRouter()


class ProjectExecutionSettings(BaseModel):
    planner_provider: str = Field(default="")
    planner_model: str = Field(default="")
    planner_temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    planner_max_tokens: int = Field(default=4000, ge=1)


def _ensure_platform_settings_access(current_user: CurrentUser) -> None:
    if current_user.role not in {"admin", "manager"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to manage platform UI settings",
        )


@router.get("/settings/ui-experience", response_model=UiExperienceSettings)
async def get_ui_experience(current_user: CurrentUser = Depends(get_current_user)):
    """Return platform-wide UI experience settings."""
    _ensure_platform_settings_access(current_user)

    with get_db_session() as session:
        return UiExperienceSettings.from_mapping(get_ui_experience_settings(session))


@router.put("/settings/ui-experience", response_model=UiExperienceSettings)
async def update_ui_experience(
    request: UiExperienceSettings,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update platform-wide UI experience settings."""
    _ensure_platform_settings_access(current_user)

    with get_db_session() as session:
        upsert_ui_experience_settings(session, request.dict())
        session.commit()

    return request


@router.get("/settings/project-execution", response_model=ProjectExecutionSettings)
async def get_project_execution(current_user: CurrentUser = Depends(get_current_user)):
    _ensure_platform_settings_access(current_user)
    with get_db_session() as session:
        settings = get_project_execution_settings(session)
        return ProjectExecutionSettings(
            planner_provider=str(settings.get("planner_provider") or ""),
            planner_model=str(settings.get("planner_model") or ""),
            planner_temperature=float(settings.get("planner_temperature") or 0.2),
            planner_max_tokens=int(settings.get("planner_max_tokens") or 4000),
        )


@router.put("/settings/project-execution", response_model=ProjectExecutionSettings)
async def update_project_execution(
    request: ProjectExecutionSettings,
    current_user: CurrentUser = Depends(get_current_user),
):
    _ensure_platform_settings_access(current_user)
    with get_db_session() as session:
        existing = get_project_execution_settings(session)
        upsert_project_execution_settings(
            session,
            {
                **existing,
                **request.model_dump(),
            },
        )
        session.commit()
    return request
