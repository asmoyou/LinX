"""Semantic search for similar existing skills.

References:
- Design Section 5.6: Dynamic Skill Generation
- Requirements 4: Skill Library
"""

import logging
from typing import List, Optional, Tuple
from uuid import UUID

from memory_system.embedding_service import get_embedding_service
from skill_library.skill_registry import SkillInfo, SkillRegistry, get_skill_registry

logger = logging.getLogger(__name__)


class SemanticSkillSearch:
    """Search for similar skills using semantic similarity."""

    def __init__(
        self,
        skill_registry: Optional[SkillRegistry] = None,
        embedding_service=None,
    ):
        """Initialize semantic skill search.

        Args:
            skill_registry: SkillRegistry for skill retrieval
            embedding_service: EmbeddingService for generating embeddings
        """
        self.skill_registry = skill_registry or get_skill_registry()
        self.embedding_service = embedding_service or get_embedding_service()
        logger.info("SemanticSkillSearch initialized")

    def find_similar_skills(
        self,
        description: str,
        threshold: float = 0.7,
        limit: int = 5,
    ) -> List[Tuple[SkillInfo, float]]:
        """Find skills similar to the given description.

        Args:
            description: Skill description to search for
            threshold: Minimum similarity score (0-1)
            limit: Maximum number of results

        Returns:
            List of (SkillInfo, similarity_score) tuples
        """
        logger.info(f"Searching for skills similar to: {description}")

        # Generate embedding for query description
        query_embedding = self.embedding_service.generate_embedding(description)

        # Get all skills
        all_skills = self.skill_registry.list_skills(limit=1000)

        # Calculate similarity for each skill
        similar_skills = []
        for skill in all_skills:
            # Generate embedding for skill description
            skill_embedding = self.embedding_service.generate_embedding(skill.description)

            # Calculate cosine similarity
            similarity = self._cosine_similarity(query_embedding, skill_embedding)

            if similarity >= threshold:
                similar_skills.append((skill, similarity))

        # Sort by similarity (descending)
        similar_skills.sort(key=lambda x: x[1], reverse=True)

        # Return top results
        results = similar_skills[:limit]
        logger.info(f"Found {len(results)} similar skills")

        return results

    def find_exact_match(self, description: str) -> Optional[SkillInfo]:
        """Find exact match for skill description.

        Args:
            description: Skill description

        Returns:
            SkillInfo if exact match found, None otherwise
        """
        # Search for skills with very high similarity (>0.95)
        similar_skills = self.find_similar_skills(
            description=description,
            threshold=0.95,
            limit=1,
        )

        if similar_skills:
            skill, similarity = similar_skills[0]
            logger.info(f"Found exact match: {skill.name} (similarity={similarity})")
            return skill

        return None

    def suggest_existing_skill(
        self,
        description: str,
    ) -> Optional[Tuple[SkillInfo, float]]:
        """Suggest an existing skill instead of generating new one.

        Args:
            description: Desired skill description

        Returns:
            (SkillInfo, similarity_score) if good match found, None otherwise
        """
        # Find similar skills with high threshold
        similar_skills = self.find_similar_skills(
            description=description,
            threshold=0.8,
            limit=1,
        )

        if similar_skills:
            skill, similarity = similar_skills[0]
            logger.info(f"Suggesting existing skill: {skill.name} " f"(similarity={similarity})")
            return (skill, similarity)

        return None

    def _cosine_similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        # Calculate dot product
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))

        # Calculate magnitudes
        magnitude1 = sum(a * a for a in embedding1) ** 0.5
        magnitude2 = sum(b * b for b in embedding2) ** 0.5

        # Calculate cosine similarity
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        similarity = dot_product / (magnitude1 * magnitude2)

        # Normalize to 0-1 range
        return (similarity + 1) / 2


# Singleton instance
_semantic_skill_search: Optional[SemanticSkillSearch] = None


def get_semantic_skill_search() -> SemanticSkillSearch:
    """Get or create the semantic skill search singleton.

    Returns:
        SemanticSkillSearch instance
    """
    global _semantic_skill_search
    if _semantic_skill_search is None:
        _semantic_skill_search = SemanticSkillSearch()
    return _semantic_skill_search
