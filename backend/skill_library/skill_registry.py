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
    skill_type: str = "langchain_tool"
    storage_type: str = "inline"
    code: Optional[str] = None
    config: Optional[dict] = None
    storage_path: Optional[str] = None
    manifest: Optional[dict] = None
    skill_md_content: Optional[str] = None
    homepage: Optional[str] = None
    skill_metadata: Optional[dict] = None
    gating_status: Optional[dict] = None
    is_active: bool = True
    is_system: bool = False
    execution_count: int = 0
    last_executed_at: Optional[object] = None  # datetime
    average_execution_time: Optional[float] = None
    created_at: Optional[object] = None  # datetime
    updated_at: Optional[object] = None  # datetime
    created_by: Optional[str] = None


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

    @staticmethod
    def _to_skill_info(skill) -> SkillInfo:
        return SkillInfo(
            skill_id=skill.skill_id,
            name=skill.name,
            description=skill.description,
            version=skill.version,
            interface_definition=skill.interface_definition,
            dependencies=skill.dependencies or [],
            skill_type=skill.skill_type,
            storage_type=skill.storage_type,
            code=skill.code,
            config=skill.config,
            storage_path=skill.storage_path,
            manifest=skill.manifest,
            skill_md_content=getattr(skill, "skill_md_content", None),
            homepage=getattr(skill, "homepage", None),
            skill_metadata=getattr(skill, "skill_metadata", None),
            gating_status=getattr(skill, "gating_status", None),
            is_active=skill.is_active,
            is_system=skill.is_system,
            execution_count=skill.execution_count,
            last_executed_at=skill.last_executed_at,
            average_execution_time=skill.average_execution_time,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            created_by=str(skill.created_by) if getattr(skill, "created_by", None) else None,
        )

    def register_skill(
        self,
        name: str,
        description: str,
        interface_definition: dict,
        dependencies: Optional[List[str]] = None,
        version: str = "1.0.0",
        skill_type: str = "langchain_tool",
        storage_type: str = "inline",
        code: Optional[str] = None,
        config: Optional[dict] = None,
        storage_path: Optional[str] = None,
        manifest: Optional[dict] = None,
        skill_md_content: Optional[str] = None,
        homepage: Optional[str] = None,
        skill_metadata: Optional[dict] = None,
        gating_status: Optional[dict] = None,
        is_active: bool = True,
        is_system: bool = False,
        created_by: Optional[str] = None,
        validate: bool = True,
    ) -> SkillInfo:
        """Register a new skill.

        Args:
            name: Unique skill name
            description: Skill description
            interface_definition: Interface definition
            dependencies: List of dependencies
            version: Skill version
            skill_type: Type of skill (langchain_tool, agent_skill)
            storage_type: Storage type (inline, minio)
            code: Python code for inline skills
            config: Configuration for API/DB skills
            storage_path: MinIO path for package skills
            manifest: Parsed manifest for package skills
            skill_md_content: SKILL.md content for agent_skill (required for agent_skill)
            homepage: Homepage URL for agent_skill
            skill_metadata: Additional metadata (emoji, tags, etc.)
            gating_status: Gating check results
            is_active: Whether skill is active
            is_system: Whether skill is system skill
            created_by: User ID who created the skill
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
            skill_type=skill_type,
            storage_type=storage_type,
            code=code,
            config=config,
            storage_path=storage_path,
            manifest=manifest,
            skill_md_content=skill_md_content,
            homepage=homepage,
            skill_metadata=skill_metadata,
            gating_status=gating_status,
            is_active=is_active,
            is_system=is_system,
            created_by=created_by,
        )

        logger.info(
            f"Skill registered: {name} v{version} (type: {skill_type}, storage: {storage_type})"
        )

        return self._to_skill_info(skill)

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

        return self._to_skill_info(skill)

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

        return self._to_skill_info(skill)

    def list_skills(self, limit: int = 100, offset: int = 0) -> List[SkillInfo]:
        """List all skills.

        Args:
            limit: Maximum number of skills
            offset: Number of skills to skip

        Returns:
            List of SkillInfo objects
        """
        skills = self.skill_model.list_skills(limit, offset)

        return [self._to_skill_info(skill) for skill in skills]

    def search_skills(self, query: str) -> List[SkillInfo]:
        """Search skills by name or description.

        Args:
            query: Search query

        Returns:
            List of matching SkillInfo objects
        """
        skills = self.skill_model.search_skills(query)

        return [self._to_skill_info(skill) for skill in skills]

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

        return self._to_skill_info(skill)

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
