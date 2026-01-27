"""Skill types and enums.

Simplified two-tier classification system:
1. LangChain Tool - Simple standardized functions
2. Agent Skill - Flexible skills (auto-detects storage based on complexity)

References:
- docs/backend/skill-type-classification.md
"""

from enum import Enum


class SkillType(str, Enum):
    """Skill type classification.
    
    Simplified system with only two types:
    - LANGCHAIN_TOOL: Simple, standardized single-function tools
    - AGENT_SKILL: Flexible skills (storage auto-detected)
    """
    # LangChain Tool - Simple standardized tool with @tool decorator
    LANGCHAIN_TOOL = "langchain_tool"
    
    # Agent Skill - Flexible skill (can be single or multi-file)
    # Storage is automatically determined based on size/complexity
    AGENT_SKILL = "agent_skill"


class StorageType(str, Enum):
    """Storage type for skills."""
    
    # Code stored inline in database (for small skills)
    INLINE = "inline"
    
    # Full project stored in MinIO (for large/complex skills)
    MINIO = "minio"


def get_default_storage_type(skill_type: SkillType) -> StorageType:
    """Get default storage type based on skill type.
    
    Args:
        skill_type: The skill type
        
    Returns:
        Default storage type (can be overridden based on actual size)
    """
    # LangChain tools are always inline
    if skill_type == SkillType.LANGCHAIN_TOOL:
        return StorageType.INLINE
    
    # Agent skills default to inline, but can be MinIO if large
    return StorageType.INLINE


def should_use_minio(code_size: int, has_multiple_files: bool = False) -> bool:
    """Determine if MinIO storage should be used.
    
    Args:
        code_size: Size of code in bytes
        has_multiple_files: Whether skill has multiple files
        
    Returns:
        True if MinIO should be used, False for inline storage
    """
    # Use MinIO if:
    # 1. Multiple files (module/package)
    # 2. Single file but > 100KB
    if has_multiple_files:
        return True
    
    if code_size > 100 * 1024:  # 100KB threshold
        return True
    
    return False

