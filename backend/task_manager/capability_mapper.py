"""Capability Mapping for Tasks.

Maps task requirements to agent capabilities.

References:
- Requirements 1: Hierarchical Task Management
- Design Section 7.1: Task Decomposition Algorithm
"""

import logging
from typing import Dict, List, Set
from uuid import UUID

logger = logging.getLogger(__name__)


class CapabilityMapper:
    """Maps task requirements to agent capabilities."""

    def __init__(self):
        """Initialize capability mapper."""
        # Capability synonyms and mappings
        self.capability_synonyms: Dict[str, Set[str]] = {
            "data_analysis": {"data_analyst", "analyst", "statistics", "data_processing"},
            "content_writing": {"writer", "content_writer", "copywriter", "editor"},
            "code_generation": {"coder", "programmer", "developer", "code_assistant"},
            "research": {"researcher", "research_assistant", "information_gathering"},
            "sql_query": {"database", "sql", "data_query"},
        }

        logger.info("CapabilityMapper initialized")

    def map_requirements_to_capabilities(
        self,
        required_capabilities: List[str],
    ) -> List[str]:
        """Map task requirements to standardized capabilities.

        Args:
            required_capabilities: Raw capability requirements

        Returns:
            List of standardized capability names
        """
        standardized = set()

        for req in required_capabilities:
            req_lower = req.lower().strip()

            # Check if it matches a standard capability
            for standard, synonyms in self.capability_synonyms.items():
                if req_lower == standard or req_lower in synonyms:
                    standardized.add(standard)
                    break
            else:
                # Keep original if no match found
                standardized.add(req_lower)

        result = list(standardized)

        logger.debug(
            "Mapped capabilities",
            extra={
                "input": required_capabilities,
                "output": result,
            },
        )

        return result

    def calculate_capability_match_score(
        self,
        required: List[str],
        available: List[str],
    ) -> float:
        """Calculate how well available capabilities match requirements.

        Args:
            required: Required capabilities
            available: Available capabilities

        Returns:
            Match score from 0.0 to 1.0
        """
        if not required:
            return 1.0

        required_set = set(self.map_requirements_to_capabilities(required))
        available_set = set(self.map_requirements_to_capabilities(available))

        # Calculate Jaccard similarity
        intersection = required_set & available_set
        union = required_set | available_set

        if not union:
            return 0.0

        score = len(intersection) / len(required_set)

        logger.debug(
            "Capability match score",
            extra={
                "required": list(required_set),
                "available": list(available_set),
                "score": score,
            },
        )

        return score
