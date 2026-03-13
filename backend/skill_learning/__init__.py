"""Lazy exports for the skill-learning package."""

from importlib import import_module

_EXPORTS = {
    "SkillProposalBuilder": ("skill_learning.builder", "SkillProposalBuilder"),
    "get_skill_proposal_builder": ("skill_learning.builder", "get_skill_proposal_builder"),
    "SkillProposalRepository": ("skill_learning.repository", "SkillProposalRepository"),
    "SkillProposalService": ("skill_learning.service", "SkillProposalService"),
    "get_skill_proposal_repository": ("skill_learning.repository", "get_skill_proposal_repository"),
    "get_skill_proposal_service": ("skill_learning.service", "get_skill_proposal_service"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'skill_learning' has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
