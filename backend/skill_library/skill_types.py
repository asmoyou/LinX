"""Skill types and enums.

References:
- docs/backend/dynamic-skill-system.md
- docs/backend/flexible-skill-architecture.md
"""

from enum import Enum


class SkillCategory(str, Enum):
    """Skill category - top level classification."""
    
    # Claude Code style - highly flexible agent skills
    AGENT_SKILL = "agent_skill"
    
    # LangChain standard tools - simple functions
    LANGCHAIN_TOOL = "langchain_tool"


class SkillType(str, Enum):
    """Skill type enumeration - detailed implementation type."""
    
    # === Agent Skills (Claude Code Style) ===
    # Single Python file with @tool decorator (inline storage)
    AGENT_SKILL_SIMPLE = "agent_skill_simple"
    
    # Multiple Python files with entry point (MinIO storage)
    AGENT_SKILL_MODULE = "agent_skill_module"
    
    # Full project with manifest, deps, config, data (MinIO storage)
    AGENT_SKILL_PACKAGE = "agent_skill_package"
    
    # === LangChain Tools (Simple Functions) ===
    # Standard LangChain tool with @tool decorator
    LANGCHAIN_TOOL = "langchain_tool"


class StorageType(str, Enum):
    """Storage type for skills."""
    
    # Code stored inline in database
    INLINE = "inline"
    
    # Full project stored in MinIO
    MINIO = "minio"


def get_storage_type(skill_type: SkillType) -> StorageType:
    """Get storage type based on skill type.
    
    Args:
        skill_type: The skill type
        
    Returns:
        Appropriate storage type
    """
    if skill_type in [SkillType.AGENT_SKILL_SIMPLE, SkillType.LANGCHAIN_TOOL]:
        return StorageType.INLINE
    else:
        return StorageType.MINIO


def get_category(skill_type: SkillType) -> SkillCategory:
    """Get category based on skill type.
    
    Args:
        skill_type: The skill type
        
    Returns:
        Skill category
    """
    if skill_type.value.startswith("agent_skill"):
        return SkillCategory.AGENT_SKILL
    else:
        return SkillCategory.LANGCHAIN_TOOL

