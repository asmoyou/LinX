"""SKILL.md parser for Agent Skills.

Parses AgentSkills.io-compatible SKILL.md files with YAML frontmatter
and natural language instructions.

References:
- Requirements: Agent Skills Redesign
- Design: SKILL.md Parser component
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import frontmatter

logger = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """Parsed skill metadata from frontmatter."""

    name: str
    description: str
    homepage: Optional[str] = None
    emoji: Optional[str] = None
    requires_bins: List[str] = field(default_factory=list)
    requires_env: List[str] = field(default_factory=list)
    requires_config: List[str] = field(default_factory=list)
    os_filter: Optional[List[str]] = None  # darwin, linux, win32


@dataclass
class ParsedSkill:
    """Parsed SKILL.md content."""

    metadata: SkillMetadata
    instructions: str  # Markdown content after frontmatter
    raw_content: str  # Full SKILL.md content


class SkillMdParser:
    """Parser for SKILL.md files."""

    def parse(self, content: str) -> ParsedSkill:
        """Parse SKILL.md content.

        Args:
            content: Raw SKILL.md file content

        Returns:
            Parsed skill with metadata and instructions

        Raises:
            ValueError: If SKILL.md format is invalid
        """
        try:
            # Parse frontmatter
            post = frontmatter.loads(content)
            
            # Extract required fields
            name = post.get('name')
            description = post.get('description')
            
            if not name:
                raise ValueError("Missing required field: name")
            if not description:
                raise ValueError("Missing required field: description")
            
            # Extract optional fields
            homepage = post.get('homepage')
            
            # Parse metadata JSON (moltbot format)
            metadata_json = post.get('metadata', {})
            if isinstance(metadata_json, str):
                try:
                    metadata_json = json.loads(metadata_json)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid metadata JSON: {e}")
            
            # Extract moltbot-specific metadata
            moltbot_meta = metadata_json.get('moltbot', {}) if isinstance(metadata_json, dict) else {}
            
            # Extract requirements
            requires = moltbot_meta.get('requires', {})
            requires_bins = requires.get('bins', []) if isinstance(requires, dict) else []
            requires_env = requires.get('env', []) if isinstance(requires, dict) else []
            requires_config = requires.get('config', []) if isinstance(requires, dict) else []
            
            # Extract other metadata
            emoji = moltbot_meta.get('emoji')
            os_filter = moltbot_meta.get('os')
            
            # Create metadata object
            metadata = SkillMetadata(
                name=name,
                description=description,
                homepage=homepage,
                emoji=emoji,
                requires_bins=requires_bins,
                requires_env=requires_env,
                requires_config=requires_config,
                os_filter=os_filter,
            )
            
            # Extract instructions (content after frontmatter)
            instructions = post.content.strip()
            
            return ParsedSkill(
                metadata=metadata,
                instructions=instructions,
                raw_content=content,
            )
            
        except Exception as e:
            logger.error(f"Failed to parse SKILL.md: {e}")
            raise ValueError(f"Invalid SKILL.md format: {e}")

    def validate(self, parsed: ParsedSkill) -> List[str]:
        """Validate parsed skill.

        Args:
            parsed: Parsed skill

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check required fields
        if not parsed.metadata.name:
            errors.append("name is required")
        if not parsed.metadata.description:
            errors.append("description is required")
        
        # Check instructions
        if not parsed.instructions:
            errors.append("instructions cannot be empty")
        
        # Validate name format (alphanumeric, underscore, hyphen)
        if parsed.metadata.name:
            import re
            if not re.match(r'^[a-zA-Z0-9_-]+$', parsed.metadata.name):
                errors.append("name must contain only alphanumeric characters, underscores, and hyphens")
        
        # Validate homepage URL format
        if parsed.metadata.homepage:
            if not parsed.metadata.homepage.startswith(('http://', 'https://')):
                errors.append("homepage must be a valid HTTP(S) URL")
        
        # Validate OS filter values
        if parsed.metadata.os_filter:
            valid_os = {'darwin', 'linux', 'win32'}
            invalid_os = set(parsed.metadata.os_filter) - valid_os
            if invalid_os:
                errors.append(f"invalid OS values: {', '.join(invalid_os)}. Must be one of: {', '.join(valid_os)}")
        
        return errors
