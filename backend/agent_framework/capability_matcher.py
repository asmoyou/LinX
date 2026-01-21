"""Agent capability matching algorithm.

References:
- Requirements 12: Agent Lifecycle Management
- Design Section 4: Agent Framework Design
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
from uuid import UUID

from agent_framework.agent_registry import AgentInfo, AgentRegistry, get_agent_registry

logger = logging.getLogger(__name__)


@dataclass
class CapabilityMatch:
    """Result of capability matching."""

    agent_info: AgentInfo
    match_score: float  # 0.0 to 1.0
    matched_capabilities: List[str]
    missing_capabilities: List[str]


class CapabilityMatcher:
    """Match agents to required capabilities."""

    def __init__(self, agent_registry: Optional[AgentRegistry] = None):
        """Initialize capability matcher.

        Args:
            agent_registry: AgentRegistry instance
        """
        self.agent_registry = agent_registry or get_agent_registry()
        logger.info("CapabilityMatcher initialized")

    def find_matching_agents(
        self,
        required_capabilities: List[str],
        owner_user_id: Optional[UUID] = None,
        min_match_score: float = 0.5,
    ) -> List[CapabilityMatch]:
        """Find agents matching required capabilities.

        Args:
            required_capabilities: List of required skill names
            owner_user_id: Optional filter by owner
            min_match_score: Minimum match score (0.0 to 1.0)

        Returns:
            List of CapabilityMatch objects sorted by match score
        """
        # Get all active agents
        agents = self.agent_registry.list_agents(
            owner_user_id=owner_user_id,
            status="active",
        )

        matches = []
        for agent_info in agents:
            match = self._calculate_match(agent_info, required_capabilities)
            if match.match_score >= min_match_score:
                matches.append(match)

        # Sort by match score (descending)
        matches.sort(key=lambda m: m.match_score, reverse=True)

        logger.info(
            f"Found {len(matches)} matching agents",
            extra={"required_capabilities": required_capabilities},
        )

        return matches

    def find_best_agent(
        self,
        required_capabilities: List[str],
        owner_user_id: Optional[UUID] = None,
    ) -> Optional[CapabilityMatch]:
        """Find best matching agent.

        Args:
            required_capabilities: List of required skill names
            owner_user_id: Optional filter by owner

        Returns:
            Best CapabilityMatch or None if no match found
        """
        matches = self.find_matching_agents(
            required_capabilities,
            owner_user_id,
            min_match_score=0.0,
        )

        return matches[0] if matches else None

    def _calculate_match(
        self,
        agent_info: AgentInfo,
        required_capabilities: List[str],
    ) -> CapabilityMatch:
        """Calculate match score for an agent.

        Args:
            agent_info: Agent information
            required_capabilities: Required capabilities

        Returns:
            CapabilityMatch with score and details
        """
        agent_caps = set(agent_info.capabilities)
        required_caps = set(required_capabilities)

        matched = agent_caps.intersection(required_caps)
        missing = required_caps.difference(agent_caps)

        # Calculate match score
        if not required_capabilities:
            match_score = 1.0
        else:
            match_score = len(matched) / len(required_capabilities)

        return CapabilityMatch(
            agent_info=agent_info,
            match_score=match_score,
            matched_capabilities=list(matched),
            missing_capabilities=list(missing),
        )


# Singleton instance
_capability_matcher: Optional[CapabilityMatcher] = None


def get_capability_matcher() -> CapabilityMatcher:
    """Get or create the capability matcher singleton.

    Returns:
        CapabilityMatcher instance
    """
    global _capability_matcher
    if _capability_matcher is None:
        _capability_matcher = CapabilityMatcher()
    return _capability_matcher
