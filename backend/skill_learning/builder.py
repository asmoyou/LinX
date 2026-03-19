"""Builder for learned skill candidates."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from user_memory.builder import UserMemoryBuilder, get_user_memory_builder


class SkillCandidateBuilder:
    """Extract and project reusable successful paths."""

    def __init__(self, builder: Optional[UserMemoryBuilder] = None):
        self._builder = builder or get_user_memory_builder()

    def extract_candidates(
        self, turns: List[Dict[str, Any]], agent_name: str
    ) -> List[Dict[str, Any]]:
        """Extract skill candidates from session turns."""

        return self._builder.extract_skill_candidates(turns, agent_name)

    def build_candidates(
        self,
        *,
        agent_id: str,
        agent_name: str,
        turns: List[Dict[str, Any]],
        extracted_candidates: List[Dict[str, Any]],
    ) -> Tuple[List[Any], List[Any]]:
        """Build observation/projection rows for skill candidates."""

        return self._builder.build_skill_candidate_observations(
            agent_id=agent_id,
            agent_name=agent_name,
            turns=turns,
            extracted_agent_candidates=extracted_candidates,
        )


_skill_candidate_builder: Optional[SkillCandidateBuilder] = None


def get_skill_candidate_builder() -> SkillCandidateBuilder:
    """Return the shared skill-candidate builder."""

    global _skill_candidate_builder
    if _skill_candidate_builder is None:
        _skill_candidate_builder = SkillCandidateBuilder()
    return _skill_candidate_builder
