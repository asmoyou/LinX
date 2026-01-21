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
        validate: bool = True,
    ) -> SkillInfo:
        """Register a new skill.
        
        Args:
            name: Unique skill name
            description: Skill description
            interface_definition: Interface definition
            dependencies: List of dependencies
            version: Skill version
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
            )
            for skill in skills
        ]


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
