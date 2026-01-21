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

from skill_library.default_skills import (
    get_default_skill_definitions,
    register_default_skills,
)
from skill_library.dependency_resolver import (
    DependencyGraph,
    DependencyResolver,
    get_dependency_resolver,
)
from skill_library.dynamic_skill_generator import (
    DynamicSkillGenerator,
    GeneratedSkill,
    get_dynamic_skill_generator,
)
from skill_library.semantic_skill_search import (
    SemanticSkillSearch,
    get_semantic_skill_search,
)
from skill_library.skill_cache import (
    CachedSkill,
    SkillCache,
    get_skill_cache,
)
from skill_library.skill_executor import (
    ExecutionResult,
    SkillExecutor,
    get_skill_executor,
)
from skill_library.skill_model import (
    SkillModel,
    get_skill_model,
)
from skill_library.skill_registry import (
    SkillInfo,
    SkillRegistry,
    get_skill_registry,
)
from skill_library.skill_validator import (
    InterfaceDefinition,
    SkillValidator,
    ValidationResult,
    get_skill_validator,
)
from skill_library.skill_versioning import (
    SkillVersion,
    VersionManager,
    get_version_manager,
)

__all__ = [
    # Skill model
    "SkillModel",
    "get_skill_model",
    # Skill registry
    "SkillRegistry",
    "SkillInfo",
    "get_skill_registry",
    # Skill validation
    "SkillValidator",
    "ValidationResult",
    "InterfaceDefinition",
    "get_skill_validator",
    # Skill versioning
    "SkillVersion",
    "VersionManager",
    "get_version_manager",
    # Dependency resolution
    "DependencyResolver",
    "DependencyGraph",
    "get_dependency_resolver",
    # Skill execution
    "SkillExecutor",
    "ExecutionResult",
    "get_skill_executor",
    # Default skills
    "register_default_skills",
    "get_default_skill_definitions",
    # Dynamic skill generation
    "DynamicSkillGenerator",
    "GeneratedSkill",
    "get_dynamic_skill_generator",
    # Skill caching
    "SkillCache",
    "CachedSkill",
    "get_skill_cache",
    # Semantic search
    "SemanticSkillSearch",
    "get_semantic_skill_search",
]
