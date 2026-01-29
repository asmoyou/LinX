"""Gating engine for Agent Skills.

Checks if skill requirements are met (binaries, environment variables, config).

References:
- Requirements: Agent Skills Redesign
- Design: Gating Engine component
"""

import logging
import platform
import shutil
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from shared.config import get_config
from skill_library.skill_md_parser import SkillMetadata

logger = logging.getLogger(__name__)


@dataclass
class GatingResult:
    """Result of gating check."""

    eligible: bool
    missing_bins: List[str]
    missing_env: List[str]
    missing_config: List[str]
    os_compatible: bool
    reason: Optional[str] = None


class GatingEngine:
    """Check skill eligibility based on requirements."""

    def __init__(self):
        """Initialize gating engine with caches."""
        self._binary_cache: Dict[str, bool] = {}
        self._config = get_config()

    def check_binary(self, binary_name: str) -> bool:
        """Check if binary exists on PATH.

        Args:
            binary_name: Name of binary to check

        Returns:
            True if binary exists on PATH
        """
        # Check cache first
        if binary_name in self._binary_cache:
            return self._binary_cache[binary_name]

        # Check PATH
        exists = shutil.which(binary_name) is not None

        # Cache result
        self._binary_cache[binary_name] = exists

        logger.debug(f"Binary check: {binary_name} = {exists}")
        return exists

    def check_env_var(self, var_name: str) -> bool:
        """Check if environment variable is set.

        Checks both os.environ and config overrides.

        Args:
            var_name: Name of environment variable

        Returns:
            True if variable is set
        """
        import os

        # Check os.environ first
        if var_name in os.environ:
            return True

        # Check config overrides (skills.entries.*.env)
        # This would require knowing the skill name, so for now just check env
        # TODO: Add skill-specific env override support

        return False

    def check_config(self, config_path: str) -> bool:
        """Check if config value is truthy.

        Supports dot-notation paths (e.g., "browser.enabled").

        Args:
            config_path: Dot-notation config path

        Returns:
            True if config value is truthy
        """
        try:
            # Split path into parts
            parts = config_path.split('.')

            # Navigate config
            value = self._config
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return False

                if value is None:
                    return False

            # Check if truthy
            return bool(value)

        except Exception as e:
            logger.warning(f"Failed to check config {config_path}: {e}")
            return False

    def check_os_compatibility(self, os_filter: Optional[List[str]]) -> bool:
        """Check if current OS is compatible.

        Args:
            os_filter: List of compatible OS names (darwin, linux, win32)

        Returns:
            True if OS is compatible or no filter specified
        """
        if not os_filter:
            return True

        # Get current OS
        current_os = platform.system().lower()

        # Map platform names
        os_map = {
            'darwin': 'darwin',
            'linux': 'linux',
            'windows': 'win32',
        }

        current_os_name = os_map.get(current_os, current_os)

        # Check if current OS is in filter
        compatible = current_os_name in os_filter

        logger.debug(f"OS compatibility check: {current_os_name} in {os_filter} = {compatible}")
        return compatible

    def check_eligibility(self, metadata: SkillMetadata) -> GatingResult:
        """Check if skill requirements are met.

        Args:
            metadata: Skill metadata with requirements

        Returns:
            Gating result with eligibility status
        """
        missing_bins = []
        missing_env = []
        missing_config = []

        # Check binaries
        for binary in metadata.requires_bins:
            if not self.check_binary(binary):
                missing_bins.append(binary)

        # Check environment variables
        for env_var in metadata.requires_env:
            if not self.check_env_var(env_var):
                missing_env.append(env_var)

        # Check config values
        for config_path in metadata.requires_config:
            if not self.check_config(config_path):
                missing_config.append(config_path)

        # Check OS compatibility
        os_compatible = self.check_os_compatibility(metadata.os_filter)

        # Determine eligibility
        eligible = (
            len(missing_bins) == 0
            and len(missing_env) == 0
            and len(missing_config) == 0
            and os_compatible
        )

        # Build reason if not eligible
        reason = None
        if not eligible:
            reasons = []
            if missing_bins:
                reasons.append(f"missing binaries: {', '.join(missing_bins)}")
            if missing_env:
                reasons.append(f"missing env vars: {', '.join(missing_env)}")
            if missing_config:
                reasons.append(f"missing config: {', '.join(missing_config)}")
            if not os_compatible:
                current_os = platform.system().lower()
                reasons.append(f"incompatible OS: {current_os} not in {metadata.os_filter}")
            reason = "; ".join(reasons)

        logger.info(
            f"Gating check for {metadata.name}: eligible={eligible}",
            extra={
                "skill_name": metadata.name,
                "eligible": eligible,
                "missing_bins": missing_bins,
                "missing_env": missing_env,
                "missing_config": missing_config,
                "os_compatible": os_compatible,
            },
        )

        return GatingResult(
            eligible=eligible,
            missing_bins=missing_bins,
            missing_env=missing_env,
            missing_config=missing_config,
            os_compatible=os_compatible,
            reason=reason,
        )

    def clear_cache(self):
        """Clear binary cache.

        Useful when binaries are installed/removed during runtime.
        """
        self._binary_cache.clear()
        logger.debug("Binary cache cleared")
