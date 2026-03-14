"""Builder for learned skill proposals."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from user_memory.builder import UserMemoryBuilder, get_user_memory_builder


class SkillProposalBuilder:
    """Extract and project reusable successful paths."""

    def __init__(self, builder: Optional[UserMemoryBuilder] = None):
        self._builder = builder or get_user_memory_builder()

    def extract_candidates(
        self, turns: List[Dict[str, Any]], agent_name: str
    ) -> List[Dict[str, Any]]:
        """Extract skill proposals from session turns."""

        return self._builder.extract_skill_proposals(turns, agent_name)

    def build_proposals(
        self,
        *,
        agent_id: str,
        agent_name: str,
        turns: List[Dict[str, Any]],
        extracted_candidates: List[Dict[str, Any]],
    ) -> Tuple[List[Any], List[Any]]:
        """Build observation/projection rows for skill proposals."""

        return self._builder.build_skill_proposal_observations(
            agent_id=agent_id,
            agent_name=agent_name,
            turns=turns,
            extracted_agent_candidates=extracted_candidates,
        )


_skill_proposal_builder: Optional[SkillProposalBuilder] = None


def get_skill_proposal_builder() -> SkillProposalBuilder:
    """Return the shared skill-proposal builder."""

    global _skill_proposal_builder
    if _skill_proposal_builder is None:
        _skill_proposal_builder = SkillProposalBuilder()
    return _skill_proposal_builder
