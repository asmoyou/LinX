"""Skills API router.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
- docs/backend/skill-type-classification.md
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from access_control.permissions import get_current_user, CurrentUser
from skill_library.skill_registry import SkillInfo, get_skill_registry
from skill_library.skill_types import SkillType, StorageType
from skill_library.templates import get_skill_templates, get_template_by_id
from skill_library.execution_engine import get_execution_engine

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
    skill_type: Optional[str] = Field(default="langchain_tool")
    code: Optional[str] = Field(default=None)
    interface_definition: Optional[InterfaceDefinition] = None
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
    skill_type: Optional[str] = "langchain_tool"
    storage_type: Optional[str] = None
    code: Optional[str] = None
    interface_definition: InterfaceDefinition
    dependencies: List[str]
    is_active: Optional[bool] = True
    execution_count: Optional[int] = 0
    average_execution_time: Optional[float] = 0.0
    last_executed_at: Optional[str] = None
    created_at: Optional[str] = None
    created_by: Optional[str] = None

    @classmethod
    def from_skill_info(cls, skill_info: SkillInfo, include_code: bool = False) -> "SkillResponse":
        """Create response from SkillInfo.
        
        Args:
            skill_info: Skill information
            include_code: Whether to include code in response
        """
        return cls(
            skill_id=str(skill_info.skill_id),
            name=skill_info.name,
            description=skill_info.description,
            version=skill_info.version,
            skill_type=skill_info.skill_type,
            storage_type=skill_info.storage_type,
            code=skill_info.code if include_code else None,
            interface_definition=InterfaceDefinition(
                inputs=skill_info.interface_definition.get("inputs", {}),
                outputs=skill_info.interface_definition.get("outputs", {}),
                required_inputs=skill_info.interface_definition.get("required_inputs", []),
            ),
            dependencies=skill_info.dependencies,
            is_active=skill_info.is_active,
            execution_count=skill_info.execution_count,
            average_execution_time=skill_info.average_execution_time,
            last_executed_at=skill_info.last_executed_at.isoformat() if skill_info.last_executed_at else None,
            created_at=skill_info.created_at.isoformat() if skill_info.created_at else None,
            created_by=str(skill_info.created_by) if skill_info.created_by else None,
        )


class RegisterDefaultsResponse(BaseModel):
    """Response for registering default skills."""

    registered_count: int
    message: str


@router.get("", response_model=List[SkillResponse])
async def list_skills(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_code: bool = Query(False, description="Include code in response"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """List all skills with pagination.

    Args:
        limit: Maximum number of skills to return
        offset: Number of skills to skip
        include_code: Whether to include code in response
        current_user: Authenticated user

    Returns:
        List of skills
    """
    try:
        registry = get_skill_registry()
        skills = registry.list_skills(limit=limit, offset=offset)

        return [SkillResponse.from_skill_info(skill, include_code=include_code) for skill in skills]

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


@router.get("/templates", response_model=List[Dict])
async def get_templates(
    category: Optional[str] = Query(None, description="Filter by category (agent_skill or langchain_tool)"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get all skill templates.
    
    Args:
        category: Optional category filter
        current_user: Authenticated user
        
    Returns:
        List of skill templates
    """
    try:
        templates = get_skill_templates()
        
        # Filter by category if provided
        if category:
            templates = [t for t in templates if t["category"] == category]
        
        return templates
        
    except Exception as e:
        logger.error(f"Failed to get templates: {e}")
        raise HTTPException(status_code=500, detail="Failed to get templates")


@router.get("/templates/package-example")
async def download_package_template(
    current_user: CurrentUser = Depends(get_current_user),
):
    """Download a reference package template for Agent Skills.
    
    Returns a ZIP file containing:
    - main.py: Entry point with @tool decorated function
    - requirements.txt: Dependencies
    - config.yaml: Optional configuration
    - README.md: Usage instructions
    """
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    
    try:
        # Create in-memory ZIP file
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # main.py
            main_py = '''"""Agent Skill Package Example

This is a reference template for creating Agent Skill packages.
"""

from langchain_core.tools import tool
import requests
from typing import Dict, Any, Optional


@tool
def my_agent_skill(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 30
) -> str:
    """Example agent skill that makes HTTP requests.
    
    This is a flexible agent skill that can be customized for your needs.
    
    Args:
        url: The API endpoint URL
        method: HTTP method (GET, POST, PUT, DELETE)
        headers: Optional request headers
        timeout: Request timeout in seconds
        
    Returns:
        API response as string
    """
    try:
        response = requests.request(
            method=method.upper(),
            url=url,
            headers=headers or {},
            timeout=timeout
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        return f"Error: Request timed out after {timeout} seconds"
    except requests.exceptions.RequestException as e:
        return f"Error: {str(e)}"


# You can add more functions and helper code here
def helper_function():
    """Helper functions don't need @tool decorator."""
    pass
'''
            zip_file.writestr('main.py', main_py)
            
            # requirements.txt
            requirements = '''# Python dependencies for this skill
requests>=2.31.0
langchain-core>=0.1.0
'''
            zip_file.writestr('requirements.txt', requirements)
            
            # config.yaml (optional)
            config = '''# Optional configuration file
skill:
  name: my_agent_skill
  version: 1.0.0
  timeout: 30
  
# Add your custom configuration here
'''
            zip_file.writestr('config.yaml', config)
            
            # README.md
            readme = '''# Agent Skill Package Template

This is a reference template for creating Agent Skill packages.

## Structure

```
my-skill-package/
├── main.py              # Main entry point with @tool decorated function
├── requirements.txt     # Python dependencies
├── config.yaml          # Optional configuration
└── README.md           # This file
```

## Usage

1. **Modify main.py**: Update the `my_agent_skill` function with your logic
2. **Add dependencies**: List required packages in `requirements.txt`
3. **Configure**: Add any configuration in `config.yaml`
4. **Package**: Zip all files together
5. **Upload**: Upload the ZIP file through the LinX interface

## Requirements

- The main file must contain at least one function decorated with `@tool`
- Function must have proper docstring with Args and Returns sections
- All dependencies must be listed in `requirements.txt`

## Example

```python
from langchain_core.tools import tool

@tool
def my_skill(param: str) -> str:
    """Skill description.
    
    Args:
        param: Parameter description
        
    Returns:
        Result description
    """
    # Your implementation
    return result
```

## Tips

- Keep the main function simple and focused
- Use helper functions for complex logic
- Add proper error handling
- Test locally before uploading
- Document all parameters clearly
'''
            zip_file.writestr('README.md', readme)
        
        # Prepare response
        zip_buffer.seek(0)
        
        return StreamingResponse(
            io.BytesIO(zip_buffer.getvalue()),
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=agent-skill-package-template.zip",
                "Access-Control-Expose-Headers": "Content-Disposition",
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to generate package template: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate package template")


@router.get("/{skill_id}", response_model=SkillResponse)
async def get_skill(
    skill_id: str,
    include_code: bool = Query(True, description="Include code in response"),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get skill by ID.

    Args:
        skill_id: Skill UUID
        include_code: Whether to include code in response
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

        return SkillResponse.from_skill_info(skill, include_code=include_code)

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

        # Convert interface definition to dict, or use default
        if request.interface_definition:
            interface_def = {
                "inputs": request.interface_definition.inputs,
                "outputs": request.interface_definition.outputs,
                "required_inputs": request.interface_definition.required_inputs or [],
            }
        else:
            # Default interface for skills without explicit definition
            interface_def = {
                "inputs": {},
                "outputs": {"result": "string"},
                "required_inputs": [],
            }

        # Determine storage type based on code presence and size
        storage_type = "inline"  # Default for now, MinIO support coming later
        
        skill = registry.register_skill(
            name=request.name,
            description=request.description,
            interface_definition=interface_def,
            dependencies=request.dependencies or [],
            version=request.version,
            skill_type=request.skill_type or "langchain_tool",
            storage_type=storage_type,
            code=request.code,
            is_active=True,
            is_system=False,
            created_by=str(current_user.user_id),
            validate=False,  # Skip validation for now
        )

        logger.info(
            f"Skill created by user {current_user.user_id}",
            extra={"skill_id": str(skill.skill_id), "skill_name": request.name},
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


@router.post("/from-template", response_model=SkillResponse, status_code=201)
async def create_from_template(
    template_id: str = Body(..., embed=True),
    name: str = Body(..., embed=True),
    description: Optional[str] = Body(None, embed=True),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Create skill from template.
    
    Args:
        template_id: Template identifier
        name: Custom name for the skill
        description: Optional custom description
        current_user: Authenticated user
        
    Returns:
        Created skill
    """
    try:
        # Get template
        template = get_template_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template {template_id} not found")
        
        # Create skill from template
        registry = get_skill_registry()
        
        # Extract interface from code (simplified - in production, parse AST)
        interface_def = {
            "inputs": {},
            "outputs": {"result": "string"},
            "required_inputs": []
        }
        
        skill = registry.register_skill(
            name=name,
            description=description or template["description"],
            interface_definition=interface_def,
            dependencies=template.get("dependencies", []),
            version="1.0.0",
            skill_type=template["skill_type"],
            code=template["code"],
            validate=False  # Skip validation for templates
        )
        
        logger.info(
            f"Skill created from template by user {current_user.user_id}",
            extra={"skill_id": str(skill.skill_id), "template_id": template_id}
        )
        
        return SkillResponse.from_skill_info(skill)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create skill from template: {e}")
        raise HTTPException(status_code=500, detail="Failed to create skill from template")


@router.post("/{skill_id}/test")
async def test_skill(
    skill_id: str,
    inputs: Dict[str, Any] = Body(...),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Test skill execution.
    
    Args:
        skill_id: Skill UUID
        inputs: Input parameters for the skill
        current_user: Authenticated user
        
    Returns:
        Execution result
    """
    try:
        skill_uuid = UUID(skill_id)
        
        # Get skill
        from skill_library.skill_model import get_skill_model
        skill_model = get_skill_model()
        skill = skill_model.get_skill_by_id(skill_uuid)
        
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        
        # Execute skill
        engine = get_execution_engine()
        result = await engine.execute_skill(skill, inputs)
        
        logger.info(
            f"Skill tested by user {current_user.user_id}",
            extra={
                "skill_id": skill_id,
                "success": result.success,
                "execution_time": result.execution_time
            }
        )
        
        return result.to_dict()
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test skill: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to test skill: {str(e)}")


@router.post("/{skill_id}/activate", status_code=204)
async def activate_skill(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Activate a skill.
    
    Args:
        skill_id: Skill UUID
        current_user: Authenticated user
    """
    try:
        skill_uuid = UUID(skill_id)
        
        from database.connection import get_db_session
        from database.models import Skill as SkillModel
        
        # Update skill status in database
        with get_db_session() as session:
            db_skill = session.query(SkillModel).filter(
                SkillModel.skill_id == skill_uuid
            ).first()
            
            if not db_skill:
                raise HTTPException(status_code=404, detail="Skill not found")
            
            db_skill.is_active = True
            session.commit()
        
        logger.info(
            f"Skill activated by user {current_user.user_id}",
            extra={"skill_id": skill_id}
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to activate skill: {str(e)}")


@router.post("/{skill_id}/deactivate", status_code=204)
async def deactivate_skill(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Deactivate a skill.
    
    Args:
        skill_id: Skill UUID
        current_user: Authenticated user
    """
    try:
        skill_uuid = UUID(skill_id)
        
        from database.connection import get_db_session
        from database.models import Skill as SkillModel
        
        # Update skill status in database
        with get_db_session() as session:
            db_skill = session.query(SkillModel).filter(
                SkillModel.skill_id == skill_uuid
            ).first()
            
            if not db_skill:
                raise HTTPException(status_code=404, detail="Skill not found")
            
            db_skill.is_active = False
            session.commit()
        
        # Clear from execution engine cache
        try:
            engine = get_execution_engine()
            engine.clear_cache(skill_uuid)
        except Exception as e:
            logger.warning(f"Failed to clear execution engine cache: {e}")
        
        logger.info(
            f"Skill deactivated by user {current_user.user_id}",
            extra={"skill_id": skill_id}
        )
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to deactivate skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to deactivate skill: {str(e)}")


@router.get("/{skill_id}/stats")
async def get_skill_stats(
    skill_id: str,
    current_user: CurrentUser = Depends(get_current_user),
):
    """Get skill execution statistics.
    
    Args:
        skill_id: Skill UUID
        current_user: Authenticated user
        
    Returns:
        Skill statistics
    """
    try:
        skill_uuid = UUID(skill_id)
        
        from skill_library.skill_model import get_skill_model
        skill_model = get_skill_model()
        skill = skill_model.get_skill_by_id(skill_uuid)
        
        if not skill:
            raise HTTPException(status_code=404, detail="Skill not found")
        
        return {
            "skill_id": str(skill.skill_id),
            "name": skill.name,
            "execution_count": skill.execution_count,
            "last_executed_at": skill.last_executed_at.isoformat() if skill.last_executed_at else None,
            "average_execution_time": skill.average_execution_time,
            "is_active": skill.is_active,
            "created_at": skill.created_at.isoformat() if skill.created_at else None
        }
        
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid skill ID format")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get skill stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to get skill stats")


@router.post("/validate")
async def validate_skill_code(
    code: str = Body(..., embed=True),
    current_user: CurrentUser = Depends(get_current_user),
):
    """Validate skill code for safety and syntax.
    
    Args:
        code: Python code to validate
        current_user: Authenticated user
        
    Returns:
        Validation result
    """
    try:
        engine = get_execution_engine()
        
        # Try to validate the code
        try:
            engine._validate_code_safety(code)
            
            # Also check if it can be parsed
            import ast
            ast.parse(code)
            
            # Check if it has a @tool decorated function
            namespace = {'tool': lambda f: f}
            exec(code, namespace)
            
            has_tool = False
            for name, obj in namespace.items():
                if callable(obj) and name not in ['tool']:
                    has_tool = True
                    break
            
            return {
                "valid": True,
                "has_tool_decorator": has_tool,
                "message": "Code validation passed",
                "warnings": []
            }
            
        except SyntaxError as e:
            return {
                "valid": False,
                "has_tool_decorator": False,
                "message": f"Syntax error: {str(e)}",
                "warnings": []
            }
        except ValueError as e:
            return {
                "valid": False,
                "has_tool_decorator": False,
                "message": str(e),
                "warnings": []
            }
            
    except Exception as e:
        logger.error(f"Failed to validate code: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate code")
