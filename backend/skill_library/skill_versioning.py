"""Skill versioning support.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from dataclasses import dataclass
from typing import List, Optional
import re

logger = logging.getLogger(__name__)


@dataclass
class SkillVersion:
    """Semantic version for skills."""
    
    major: int
    minor: int
    patch: int
    
    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"
    
    def __lt__(self, other: 'SkillVersion') -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
    
    def __eq__(self, other: 'SkillVersion') -> bool:
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)
    
    @classmethod
    def parse(cls, version_str: str) -> 'SkillVersion':
        """Parse version string.
        
        Args:
            version_str: Version string (e.g., "1.2.3")
            
        Returns:
            SkillVersion object
            
        Raises:
            ValueError: If version string is invalid
        """
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)$', version_str)
        if not match:
            raise ValueError(f"Invalid version string: {version_str}")
        
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )


class VersionManager:
    """Manage skill versions."""
    
    def __init__(self):
        """Initialize version manager."""
        logger.info("VersionManager initialized")
    
    def increment_major(self, version: SkillVersion) -> SkillVersion:
        """Increment major version (breaking changes).
        
        Args:
            version: Current version
            
        Returns:
            New version with incremented major
        """
        return SkillVersion(major=version.major + 1, minor=0, patch=0)
    
    def increment_minor(self, version: SkillVersion) -> SkillVersion:
        """Increment minor version (new features).
        
        Args:
            version: Current version
            
        Returns:
            New version with incremented minor
        """
        return SkillVersion(major=version.major, minor=version.minor + 1, patch=0)
    
    def increment_patch(self, version: SkillVersion) -> SkillVersion:
        """Increment patch version (bug fixes).
        
        Args:
            version: Current version
            
        Returns:
            New version with incremented patch
        """
        return SkillVersion(major=version.major, minor=version.minor, patch=version.patch + 1)
    
    def is_compatible(self, required: SkillVersion, available: SkillVersion) -> bool:
        """Check if available version is compatible with required version.
        
        Uses semantic versioning rules:
        - Major version must match
        - Minor version must be >= required
        - Patch version doesn't matter
        
        Args:
            required: Required version
            available: Available version
            
        Returns:
            True if compatible
        """
        if available.major != required.major:
            return False
        
        if available.minor < required.minor:
            return False
        
        return True
    
    def get_latest_compatible(
        self,
        required: SkillVersion,
        available_versions: List[SkillVersion],
    ) -> Optional[SkillVersion]:
        """Get latest compatible version from available versions.
        
        Args:
            required: Required version
            available_versions: List of available versions
            
        Returns:
            Latest compatible version or None
        """
        compatible = [
            v for v in available_versions
            if self.is_compatible(required, v)
        ]
        
        if not compatible:
            return None
        
        return max(compatible)


# Singleton instance
_version_manager: Optional[VersionManager] = None


def get_version_manager() -> VersionManager:
    """Get or create the version manager singleton.
    
    Returns:
        VersionManager instance
    """
    global _version_manager
    if _version_manager is None:
        _version_manager = VersionManager()
    return _version_manager
