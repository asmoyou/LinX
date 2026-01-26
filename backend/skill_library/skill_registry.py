"""Skill registration and retrieval.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from skill_library.skill_model import SkillModel, get_skill_model
from skill_library.skill_validator import SkillValidator, get_skill_validator

logger = logging.getLogger(__name__)


@dataclass
class SkillInfo:
    """Skill information."""

    skill_id: UUID
    name: str
    description: str
    version: str
    interface_definition: dict
    dependencies: List[str]
    skill_type: str = "python_function"
    code: Optional[str] = None
    config: Optional[dict] = None
    is_active: bool = True
    is_system: bool = False
    execution_count: int = 0
    last_executed_at: Optional[object] = None  # datetime
    average_execution_time: Optional[float] = None
    created_at: Optional[object] = None  # datetime
    updated_at: Optional[object] = None  # datetime


class SkillRegistry:
    """Skill registration and retrieval service."""

    def __init__(
        self,
        skill_model: Optional[SkillModel] = None,
        skill_validator: Optional[SkillValidator] = None,
    ):
        """Initialize skill registry.

        Args:
            skill_model: SkillModel for database operations
            skill_validator: SkillValidator for validation
        """
        self.skill_model = skill_model or get_skill_model()
        self.skill_validator = skill_validator or get_skill_validator()
        logger.info("SkillRegistry initialized")

    def register_skill(
        self,
        name: str,
        description: str,
        interface_definition: dict,
        dependencies: Optional[List[str]] = None,
        version: str = "1.0.0",
        skill_type: str = "python_function",
        code: Optional[str] = None,
        config: Optional[dict] = None,
        validate: bool = True,
    ) -> SkillInfo:
        """Register a new skill.

        Args:
            name: Unique skill name
            description: Skill description
            interface_definition: Interface definition
            dependencies: List of dependencies
            version: Skill version
            skill_type: Type of skill (python_function, api_wrapper, etc.)
            code: Python code for function skills
            config: Configuration for API/DB skills
            validate: Whether to validate before registration

        Returns:
            SkillInfo with registered skill details

        Raises:
            ValueError: If validation fails
        """
        # Validate skill if requested
        if validate:
            validation = self.skill_validator.validate_skill(
                name=name,
                interface_definition=interface_definition,
                dependencies=dependencies or [],
            )

            if not validation.is_valid:
                raise ValueError(f"Skill validation failed: {validation.errors}")

        # Check if skill already exists
        existing = self.skill_model.get_skill_by_name(name, version)
        if existing:
            raise ValueError(f"Skill {name} version {version} already exists")

        # Create skill
        skill = self.skill_model.create_skill(
            name=name,
            description=description,
            interface_definition=interface_definition,
            dependencies=dependencies,
            version=version,
        )

        logger.info(f"Skill registered: {name} v{version}")

        return SkillInfo(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            interface_definition=skill.interface_definition,
            dependencies=skill.dependencies or [],
            skill_type=getattr(skill, 'skill_type', 'python_function'),
            code=getattr(skill, 'code', None),
            config=getattr(skill, 'config', None),
            is_active=getattr(skill, 'is_active', True),
            is_system=getattr(skill, 'is_system', False),
            execution_count=getattr(skill, 'execution_count', 0),
            last_executed_at=getattr(skill, 'last_executed_at', None),
            average_execution_time=getattr(skill, 'average_execution_time', None),
            created_at=getattr(skill, 'created_at', None),
            updated_at=getattr(skill, 'updated_at', None),
        )

    def get_skill(self, skill_id: UUID) -> Optional[SkillInfo]:
        """Get skill by ID.

        Args:
            skill_id: Skill UUID

        Returns:
            SkillInfo or None if not found
        """
        skill = self.skill_model.get_skill_by_id(skill_id)

        if not skill:
            return None

        return SkillInfo(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            interface_definition=skill.interface_definition,
            dependencies=skill.dependencies or [],
            skill_type=getattr(skill, 'skill_type', 'python_function'),
            code=getattr(skill, 'code', None),
            config=getattr(skill, 'config', None),
            is_active=getattr(skill, 'is_active', True),
            is_system=getattr(skill, 'is_system', False),
            execution_count=getattr(skill, 'execution_count', 0),
            last_executed_at=getattr(skill, 'last_executed_at', None),
            average_execution_time=getattr(skill, 'average_execution_time', None),
            created_at=getattr(skill, 'created_at', None),
            updated_at=getattr(skill, 'updated_at', None),
        )

    def get_skill_by_name(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> Optional[SkillInfo]:
        """Get skill by name and optional version.

        Args:
            name: Skill name
            version: Optional specific version (defaults to latest)

        Returns:
            SkillInfo or None if not found
        """
        skill = self.skill_model.get_skill_by_name(name, version)

        if not skill:
            return None

        return SkillInfo(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            interface_definition=skill.interface_definition,
            dependencies=skill.dependencies or [],
            skill_type=getattr(skill, 'skill_type', 'python_function'),
            code=getattr(skill, 'code', None),
            config=getattr(skill, 'config', None),
            is_active=getattr(skill, 'is_active', True),
            is_system=getattr(skill, 'is_system', False),
            execution_count=getattr(skill, 'execution_count', 0),
            last_executed_at=getattr(skill, 'last_executed_at', None),
            average_execution_time=getattr(skill, 'average_execution_time', None),
            created_at=getattr(skill, 'created_at', None),
            updated_at=getattr(skill, 'updated_at', None),
        )

    def list_skills(self, limit: int = 100, offset: int = 0) -> List[SkillInfo]:
        """List all skills.

        Args:
            limit: Maximum number of skills
            offset: Number of skills to skip

        Returns:
            List of SkillInfo objects
        """
        skills = self.skill_model.list_skills(limit, offset)

        return [
            SkillInfo(
                skill_id=skill.skill_id,
                name=skill.name,
                description=skill.description,
                version=skill.version,
                interface_definition=skill.interface_definition,
                dependencies=skill.dependencies or [],
                skill_type=getattr(skill, 'skill_type', 'python_function'),
                code=getattr(skill, 'code', None),
                config=getattr(skill, 'config', None),
                is_active=getattr(skill, 'is_active', True),
                is_system=getattr(skill, 'is_system', False),
                execution_count=getattr(skill, 'execution_count', 0),
                last_executed_at=getattr(skill, 'last_executed_at', None),
                average_execution_time=getattr(skill, 'average_execution_time', None),
                created_at=getattr(skill, 'created_at', None),
                updated_at=getattr(skill, 'updated_at', None),
            )
            for skill in skills
        ]

    def search_skills(self, query: str) -> List[SkillInfo]:
        """Search skills by name or description.

        Args:
            query: Search query

        Returns:
            List of matching SkillInfo objects
        """
        skills = self.skill_model.search_skills(query)

        return [
            SkillInfo(
                skill_id=skill.skill_id,
                name=skill.name,
                description=skill.description,
                version=skill.version,
                interface_definition=skill.interface_definition,
                dependencies=skill.dependencies or [],
                skill_type=getattr(skill, 'skill_type', 'python_function'),
                code=getattr(skill, 'code', None),
                config=getattr(skill, 'config', None),
                is_active=getattr(skill, 'is_active', True),
                is_system=getattr(skill, 'is_system', False),
                execution_count=getattr(skill, 'execution_count', 0),
                last_executed_at=getattr(skill, 'last_executed_at', None),
                average_execution_time=getattr(skill, 'average_execution_time', None),
                created_at=getattr(skill, 'created_at', None),
                updated_at=getattr(skill, 'updated_at', None),
            )
            for skill in skills
        ]

    def update_skill(
        self,
        skill_id: UUID,
        description: Optional[str] = None,
        interface_definition: Optional[dict] = None,
        dependencies: Optional[List[str]] = None,
        code: Optional[str] = None,
        config: Optional[dict] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[SkillInfo]:
        """Update a skill.

        Args:
            skill_id: Skill UUID
            description: New description
            interface_definition: New interface definition
            dependencies: New dependencies
            code: New code
            config: New config
            is_active: New active status

        Returns:
            Updated SkillInfo or None if not found
        """
        skill = self.skill_model.update_skill(
            skill_id=skill_id,
            description=description,
            interface_definition=interface_definition,
            dependencies=dependencies,
        )

        if not skill:
            return None

        return SkillInfo(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            interface_definition=skill.interface_definition,
            dependencies=skill.dependencies or [],
            skill_type=getattr(skill, 'skill_type', 'python_function'),
            code=getattr(skill, 'code', None),
            config=getattr(skill, 'config', None),
            is_active=getattr(skill, 'is_active', True),
            is_system=getattr(skill, 'is_system', False),
            execution_count=getattr(skill, 'execution_count', 0),
            last_executed_at=getattr(skill, 'last_executed_at', None),
            average_execution_time=getattr(skill, 'average_execution_time', None),
            created_at=getattr(skill, 'created_at', None),
            updated_at=getattr(skill, 'updated_at', None),
        )

    def delete_skill(self, skill_id: UUID) -> bool:
        """Delete a skill.

        Args:
            skill_id: Skill UUID

        Returns:
            True if deleted, False if not found
        """
        return self.skill_model.delete_skill(skill_id)


# Singleton instance
_skill_registry: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """Get or create the skill registry singleton.

    Returns:
        SkillRegistry instance
    """
    global _skill_registry
    if _skill_registry is None:
        _skill_registry = SkillRegistry()
    return _skill_registry
