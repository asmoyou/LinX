"""Skill Library module for Digital Workforce Platform.

This module provides skill management including:
- Skill registration and retrieval
- Skill validation (interface, dependencies)
- Skill versioning
- Dependency resolution
- Skill execution wrapper
- Default skills

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

from skill_library.skill_model import (
    SkillModel,
    get_skill_model,
)

from skill_library.skill_registry import (
    SkillRegistry,
    SkillInfo,
    get_skill_registry,
)

from skill_library.skill_validator import (
    SkillValidator,
    ValidationResult,
    InterfaceDefinition,
    get_skill_validator,
)

from skill_library.skill_versioning import (
    SkillVersion,
    VersionManager,
    get_version_manager,
)

from skill_library.dependency_resolver import (
    DependencyResolver,
    DependencyGraph,
    get_dependency_resolver,
)

from skill_library.skill_executor import (
    SkillExecutor,
    ExecutionResult,
    get_skill_executor,
)

from skill_library.default_skills import (
    register_default_skills,
    get_default_skill_definitions,
)

__all__ = [
    # Skill model
    'SkillModel',
    'get_skill_model',
    
    # Skill registry
    'SkillRegistry',
    'SkillInfo',
    'get_skill_registry',
    
    # Skill validation
    'SkillValidator',
    'ValidationResult',
    'InterfaceDefinition',
    'get_skill_validator',
    
    # Skill versioning
    'SkillVersion',
    'VersionManager',
    'get_version_manager',
    
    # Dependency resolution
    'DependencyResolver',
    'DependencyGraph',
    'get_dependency_resolver',
    
    # Skill execution
    'SkillExecutor',
    'ExecutionResult',
    'get_skill_executor',
    
    # Default skills
    'register_default_skills',
    'get_default_skill_definitions',
]
