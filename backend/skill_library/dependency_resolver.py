"""Skill dependency resolution.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class DependencyGraph:
    """Dependency graph for skills."""

    nodes: Set[str]  # Skill names
    edges: Dict[str, List[str]]  # skill_name -> [dependencies]


class DependencyResolver:
    """Resolve skill dependencies."""

    def __init__(self):
        """Initialize dependency resolver."""
        logger.info("DependencyResolver initialized")

    def resolve_dependencies(
        self,
        skill_name: str,
        all_skills: Dict[str, List[str]],
    ) -> List[str]:
        """Resolve all dependencies for a skill.

        Args:
            skill_name: Name of the skill
            all_skills: Dict mapping skill names to their dependencies

        Returns:
            Ordered list of dependencies (topologically sorted)

        Raises:
            ValueError: If circular dependency detected
        """
        visited = set()
        visiting = set()
        result = []

        def visit(name: str):
            if name in visiting:
                raise ValueError(f"Circular dependency detected involving: {name}")

            if name in visited:
                return

            visiting.add(name)

            # Visit dependencies first
            if name in all_skills:
                for dep in all_skills[name]:
                    visit(dep)

            visiting.remove(name)
            visited.add(name)
            result.append(name)

        visit(skill_name)

        # Remove the skill itself from result
        result.remove(skill_name)

        logger.info(f"Dependencies resolved for {skill_name}", extra={"dependencies": result})

        return result

    def build_dependency_graph(
        self,
        skills: Dict[str, List[str]],
    ) -> DependencyGraph:
        """Build dependency graph from skills.

        Args:
            skills: Dict mapping skill names to their dependencies

        Returns:
            DependencyGraph object
        """
        nodes = set(skills.keys())

        # Add all dependencies as nodes
        for deps in skills.values():
            nodes.update(deps)

        return DependencyGraph(nodes=nodes, edges=skills)

    def detect_circular_dependencies(
        self,
        skills: Dict[str, List[str]],
    ) -> List[List[str]]:
        """Detect circular dependencies in skill graph.

        Args:
            skills: Dict mapping skill names to their dependencies

        Returns:
            List of circular dependency chains
        """
        cycles = []
        visited = set()
        rec_stack = []

        def visit(name: str) -> bool:
            visited.add(name)
            rec_stack.append(name)

            if name in skills:
                for dep in skills[name]:
                    if dep not in visited:
                        if visit(dep):
                            return True
                    elif dep in rec_stack:
                        # Found cycle
                        cycle_start = rec_stack.index(dep)
                        cycles.append(rec_stack[cycle_start:] + [dep])
                        return True

            rec_stack.pop()
            return False

        for skill_name in skills:
            if skill_name not in visited:
                visit(skill_name)

        return cycles

    def get_load_order(
        self,
        skills: Dict[str, List[str]],
    ) -> List[str]:
        """Get load order for skills (topological sort).

        Args:
            skills: Dict mapping skill names to their dependencies

        Returns:
            Ordered list of skill names

        Raises:
            ValueError: If circular dependency detected
        """
        # Check for cycles first
        cycles = self.detect_circular_dependencies(skills)
        if cycles:
            raise ValueError(f"Circular dependencies detected: {cycles}")

        visited = set()
        result = []

        def visit(name: str):
            if name in visited:
                return

            visited.add(name)

            # Visit dependencies first
            if name in skills:
                for dep in skills[name]:
                    visit(dep)

            result.append(name)

        for skill_name in skills:
            visit(skill_name)

        return result


# Singleton instance
_dependency_resolver: Optional[DependencyResolver] = None


def get_dependency_resolver() -> DependencyResolver:
    """Get or create the dependency resolver singleton.

    Returns:
        DependencyResolver instance
    """
    global _dependency_resolver
    if _dependency_resolver is None:
        _dependency_resolver = DependencyResolver()
    return _dependency_resolver
