"""Skills API router.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from access_control.permissions import get_current_user, CurrentUser
from skill_library.default_skills import register_default_skills
from skill_library.skill_registry import SkillInfo, get_skill_registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["skills"])


# Request/Response Models
class InterfaceDefinition(BaseModel):
    """Skill interface definition."""

    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    required_inputs: Optional[List[str]] = Field(default_factory=list)


class CreateSkillRequest(BaseModel):
    """Request to create a new skill."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(..., min_length=1, max_length=500)
    interface_definition: InterfaceDefinition
    dependencies: Optional[List[str]] = Field(default_factory=list)
    version: str = Field(default="1.0.0")


class UpdateSkillRequest(BaseModel):
    """Request to update a skill."""

    description: Optional[str] = Field(None, min_length=1, max_length=500)
    interface_definition: Optional[InterfaceDefinition] = None
    dependencies: Optional[List[str]] = None


class SkillResponse(BaseModel):
    """Skill response model."""

    skill_id: str
    name: str
    description: str
    version: str
    interface_definition: InterfaceDefinition
    dependencies: List[str]
    created_at: Optional[str] = None

    @classmethod
    def from_skill_info(cls, skill_info: SkillInfo) -> "SkillResponse":
        """Create response from SkillInfo."""
        return cls(
            skill_id=str(skill_info.skill_id),
            name=skill_info.name,
            description=skill_info.description,
            version=skill_info.version,
            interface_definition=InterfaceDefinition(
                inputs=skill_info.interface_definition.get("inputs", {}),
                outputs=skill_info.interface_definition.get("outputs", {}),
                required_inputs=skill_info.interface_definition.get("required_inputs", []),
            ),
            dependencies=skill_info.dependencies,
        )


class RegisterDefaultsResponse(BaseModel):
    """Response for registering default skills."""

    registered_count: int
    message: str


@router.get("", response_model=List[SkillResponse])
async def list_skills(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all skills with pagination.

    Args:
        limit: Maximum number of skills to return
        offset: Number of skills to skip
        current_user: Authenticated user

    Returns:
        List of skills
    """
    try:
        registry = get_skill_registry()
        skills = registry.list_skills(limit=limit, offset=offset)

        return [SkillResponse.from_skill_info(skill) for skill in skills]

    except Exception as e:
        logger.error(f"Failed to list skills: {e}")
        raise HTTPException(status_code=500, detail="Failed to list skills")


@router.get("/search", response_model=List[SkillResponse])
async def search_skills(
    query: str = Query(..., min_length=1),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Search skills by name or description.

    Args:
        query: Search query
        current_user: Authenticated user

    Returns:
        List of matching skills
    """
    try:
        registry = get_skill_registry()
        skills = registry.search_skills(query)

        return [SkillResponse.from_skill_info(skill) for skill in skills]

    except Exception as e:
        logger.error(f"Failed to search skills: {e}")
        raise HTTPException(status_code=500, detail="Failed to search skills")


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get skill by ID.

    Args:
        skill_id: Skill UUID
        current_user: Authenticated user

    Returns:
        Skill details
    """
    try:
        skill_uuid = UUID(skill_id)
        registry = get_skill_registry()
        skill = registry.get_skill(skill_uuid)

        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        return SkillResponse.from_skill_info(skill)

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill: {e}")
        raise HTTPException(status_code=500, detail="Failed to get skill")


@router.post("", response_model=SkillResponse, status_code=201)
async def create_skill(
    request: CreateSkillRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create a new skill.

    Args:
        request: Skill creation request
        current_user: Authenticated user

    Returns:
        Created skill
    """
    try:
        registry = get_skill_registry()

        # Convert interface definition to dict
        interface_def = {
            "inputs": request.interface_definition.inputs,
            "outputs": request.interface_definition.outputs,
            "required_inputs": request.interface_definition.required_inputs or [],
        }

        skill = registry.register_skill(
            name=request.name,
            description=request.description,
            interface_definition=interface_def,
            dependencies=request.dependencies or [],
            version=request.version,
            validate=True,
        )

        logger.info(
            f"Skill created by user {current_user.user_id}",
            extra={"skill_id": str(skill.skill_id), "name": request.name},
        )

        return SkillResponse.from_skill_info(skill)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create skill: {e}")
        raise HTTPException(status_code=500, detail="Failed to create skill")


@router.put("/{skill_id}", response_model=SkillResponse)
async def update_skill(
    skill_id: str,
    request: UpdateSkillRequest,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Update a skill.

    Args:
        skill_id: Skill UUID
        request: Skill update request
        current_user: Authenticated user

    Returns:
        Updated skill
    """
    try:
        skill_uuid = UUID(skill_id)
        registry = get_skill_registry()

        # Check if skill exists
        existing = registry.get_skill(skill_uuid)
        if not existing:
            raise HTTPException(status_code=404, detail="Skill not found")

        # Convert interface definition if provided
        interface_def = None
        if request.interface_definition:
            interface_def = {
                "inputs": request.interface_definition.inputs,
                "outputs": request.interface_definition.outputs,
                "required_inputs": request.interface_definition.required_inputs or [],
            }

        # Update skill via model
        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        updated = skill_model.update_skill(
            skill_id=skill_uuid,
            description=request.description,
            interface_definition=interface_def,
            dependencies=request.dependencies,
        )

        if not updated:
            raise HTTPException(status_code=404, detail="Skill not found")

        # Get updated skill info
        skill = registry.get_skill(skill_uuid)
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")

        logger.info(
            f"Skill updated by user {current_user.user_id}",
            extra={"skill_id": skill_id},
        )

        return SkillResponse.from_skill_info(skill)

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update skill: {e}")
        raise HTTPException(status_code=500, detail="Failed to update skill")


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Delete a skill.

    Args:
        skill_id: Skill UUID
        current_user: Authenticated user
    """
    try:
        skill_uuid = UUID(skill_id)

        from skill_library.skill_model import get_skill_model

        skill_model = get_skill_model()
        deleted = skill_model.delete_skill(skill_uuid)

        if not deleted:
            raise HTTPException(status_code=404, detail="Skill not found")

        logger.info(
            f"Skill deleted by user {current_user.user_id}",
            extra={"skill_id": skill_id},
        )

    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete skill: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete skill")


@router.post("/register-defaults", response_model=RegisterDefaultsResponse)
async def register_defaults(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Register default skills.

    Args:
        current_user: Authenticated user

    Returns:
        Number of skills registered
    """
    try:
        count = register_default_skills(skip_existing=True)

        logger.info(
            f"Default skills registered by user {current_user.user_id}",
            extra={"count": count},
        )

        return RegisterDefaultsResponse(
            registered_count=count,
            message=f"Successfully registered {count} default skills",
        )

    except Exception as e:
        logger.error(f"Failed to register default skills: {e}")
        raise HTTPException(status_code=500, detail="Failed to register default skills")
