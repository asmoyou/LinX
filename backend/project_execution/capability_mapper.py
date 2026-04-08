"""Project execution capability mapping helpers.

This module is a project_execution-local copy of the legacy task_manager
capability mapper so planner/scheduler logic no longer depends on the old
task_manager planning package.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Set

logger = logging.getLogger(__name__)


class CapabilityMapper:
    """Maps task requirements to agent capabilities."""

    def __init__(self):
        self.capability_synonyms: Dict[str, Set[str]] = {
            "data_analysis": {"data_analyst", "analyst", "statistics", "data_processing"},
            "content_writing": {"writer", "content_writer", "copywriter", "editor"},
            "code_generation": {"coder", "programmer", "developer", "code_assistant"},
            "research": {"researcher", "research_assistant", "information_gathering"},
            "sql_query": {"database", "sql", "data_query"},
            "implementation": {"implementation", "coding", "developer", "code_generation"},
            "review": {"review", "qa", "verification", "testing"},
            "ops": {"ops", "shell", "deployment", "host_execution"},
        }

        logger.info("ProjectExecution CapabilityMapper initialized")

    def map_requirements_to_capabilities(
        self,
        required_capabilities: List[str],
    ) -> List[str]:
        standardized = set()

        for req in required_capabilities:
            req_lower = str(req or "").lower().strip()
            if not req_lower:
                continue

            for standard, synonyms in self.capability_synonyms.items():
                if req_lower == standard or req_lower in synonyms:
                    standardized.add(standard)
                    break
            else:
                standardized.add(req_lower)

        return list(standardized)

    def calculate_capability_match_score(
        self,
        required: List[str],
        available: List[str],
    ) -> float:
        if not required:
            return 1.0

        required_set = set(self.map_requirements_to_capabilities(required))
        available_set = set(self.map_requirements_to_capabilities(available))
        if not required_set:
            return 1.0
        if not available_set:
            return 0.0

        intersection = required_set & available_set
        return len(intersection) / len(required_set)
