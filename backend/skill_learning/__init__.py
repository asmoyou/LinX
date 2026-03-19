"""Lazy exports for the skill-learning package."""

from importlib import import_module

_EXPORTS = {
    "SkillCandidateService": ("skill_learning.candidate_service", "SkillCandidateService"),
    "get_skill_candidate_service": ("skill_learning.candidate_service", "get_skill_candidate_service"),
    "SkillCandidateBuilder": ("skill_learning.builder", "SkillCandidateBuilder"),
    "get_skill_candidate_builder": ("skill_learning.builder", "get_skill_candidate_builder"),
    "SkillCandidateRepository": ("skill_learning.repository", "SkillCandidateRepository"),
    "get_skill_candidate_repository": ("skill_learning.repository", "get_skill_candidate_repository"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'skill_learning' has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
