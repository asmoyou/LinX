"""Unit tests for gating engine.

References:
- Requirements: Agent Skills Redesign
- Design: Gating Engine component
"""

import os
import platform
import pytest
from unittest.mock import patch, MagicMock

from skill_library.gating_engine import GatingEngine, GatingResult
from skill_library.skill_md_parser import SkillMetadata


class TestGatingEngine:
    """Test gating engine."""

    def test_check_binary_exists(self):
        """Test checking for existing binary."""
        engine = GatingEngine()
        
        # Python should exist
        assert engine.check_binary("python") or engine.check_binary("python3")

    def test_check_binary_not_exists(self):
        """Test checking for non-existent binary."""
        engine = GatingEngine()
        
        # This binary should not exist
        assert not engine.check_binary("nonexistent_binary_xyz123")

    def test_check_binary_caching(self):
        """Test binary check caching."""
        engine = GatingEngine()
        
        # First check
        result1 = engine.check_binary("python")
        
        # Second check should use cache
        result2 = engine.check_binary("python")
        
        assert result1 == result2
        assert "python" in engine._binary_cache

    def test_clear_cache(self):
        """Test clearing binary cache."""
        engine = GatingEngine()
        
        # Add to cache
        engine.check_binary("python")
        assert len(engine._binary_cache) > 0
        
        # Clear cache
        engine.clear_cache()
        assert len(engine._binary_cache) == 0

    def test_check_env_var_exists(self):
        """Test checking for existing environment variable."""
        engine = GatingEngine()
        
        # Set test env var
        os.environ["TEST_GATING_VAR"] = "test_value"
        
        try:
            assert engine.check_env_var("TEST_GATING_VAR")
        finally:
            del os.environ["TEST_GATING_VAR"]

    def test_check_env_var_not_exists(self):
        """Test checking for non-existent environment variable."""
        engine = GatingEngine()
        
        assert not engine.check_env_var("NONEXISTENT_VAR_XYZ123")

    @patch('skill_library.gating_engine.get_config')
    def test_check_config_exists(self, mock_get_config):
        """Test checking for existing config value."""
        # Mock config
        mock_get_config.return_value = {
            "browser": {
                "enabled": True
            }
        }
        
        engine = GatingEngine()
        assert engine.check_config("browser.enabled")

    @patch('skill_library.gating_engine.get_config')
    def test_check_config_not_exists(self, mock_get_config):
        """Test checking for non-existent config value."""
        mock_get_config.return_value = {}
        
        engine = GatingEngine()
        assert not engine.check_config("nonexistent.config")

    @patch('skill_library.gating_engine.get_config')
    def test_check_config_falsy_value(self, mock_get_config):
        """Test checking for falsy config value."""
        mock_get_config.return_value = {
            "feature": {
                "disabled": False
            }
        }
        
        engine = GatingEngine()
        assert not engine.check_config("feature.disabled")

    def test_check_os_compatibility_no_filter(self):
        """Test OS compatibility with no filter."""
        engine = GatingEngine()
        
        # No filter means compatible
        assert engine.check_os_compatibility(None)
        assert engine.check_os_compatibility([])

    def test_check_os_compatibility_compatible(self):
        """Test OS compatibility with compatible OS."""
        engine = GatingEngine()
        
        # Get current OS
        current_os = platform.system().lower()
        os_map = {
            'darwin': 'darwin',
            'linux': 'linux',
            'windows': 'win32',
        }
        current_os_name = os_map.get(current_os, current_os)
        
        # Should be compatible with current OS
        assert engine.check_os_compatibility([current_os_name])

    def test_check_os_compatibility_incompatible(self):
        """Test OS compatibility with incompatible OS."""
        engine = GatingEngine()
        
        # Get current OS
        current_os = platform.system().lower()
        
        # Create filter with only incompatible OS
        if current_os == 'darwin':
            incompatible_filter = ['linux', 'win32']
        elif current_os == 'linux':
            incompatible_filter = ['darwin', 'win32']
        else:  # windows
            incompatible_filter = ['darwin', 'linux']
        
        assert not engine.check_os_compatibility(incompatible_filter)

    def test_check_eligibility_all_requirements_met(self):
        """Test eligibility when all requirements are met."""
        engine = GatingEngine()
        
        # Create metadata with requirements that should be met
        metadata = SkillMetadata(
            name="test_skill",
            description="Test skill",
            requires_bins=["python"],  # Should exist
            requires_env=[],
            requires_config=[],
            os_filter=None,  # No OS filter
        )
        
        result = engine.check_eligibility(metadata)
        
        assert result.eligible
        assert len(result.missing_bins) == 0
        assert len(result.missing_env) == 0
        assert len(result.missing_config) == 0
        assert result.os_compatible
        assert result.reason is None

    def test_check_eligibility_missing_binary(self):
        """Test eligibility when binary is missing."""
        engine = GatingEngine()
        
        metadata = SkillMetadata(
            name="test_skill",
            description="Test skill",
            requires_bins=["nonexistent_binary_xyz123"],
            requires_env=[],
            requires_config=[],
        )
        
        result = engine.check_eligibility(metadata)
        
        assert not result.eligible
        assert "nonexistent_binary_xyz123" in result.missing_bins
        assert "missing binaries" in result.reason

    def test_check_eligibility_missing_env_var(self):
        """Test eligibility when env var is missing."""
        engine = GatingEngine()
        
        metadata = SkillMetadata(
            name="test_skill",
            description="Test skill",
            requires_bins=[],
            requires_env=["NONEXISTENT_VAR_XYZ123"],
            requires_config=[],
        )
        
        result = engine.check_eligibility(metadata)
        
        assert not result.eligible
        assert "NONEXISTENT_VAR_XYZ123" in result.missing_env
        assert "missing env vars" in result.reason

    @patch('skill_library.gating_engine.get_config')
    def test_check_eligibility_missing_config(self, mock_get_config):
        """Test eligibility when config is missing."""
        mock_get_config.return_value = {}
        
        engine = GatingEngine()
        
        metadata = SkillMetadata(
            name="test_skill",
            description="Test skill",
            requires_bins=[],
            requires_env=[],
            requires_config=["nonexistent.config"],
        )
        
        result = engine.check_eligibility(metadata)
        
        assert not result.eligible
        assert "nonexistent.config" in result.missing_config
        assert "missing config" in result.reason

    def test_check_eligibility_incompatible_os(self):
        """Test eligibility when OS is incompatible."""
        engine = GatingEngine()
        
        # Get current OS and create incompatible filter
        current_os = platform.system().lower()
        if current_os == 'darwin':
            incompatible_filter = ['linux']
        elif current_os == 'linux':
            incompatible_filter = ['darwin']
        else:  # windows
            incompatible_filter = ['darwin']
        
        metadata = SkillMetadata(
            name="test_skill",
            description="Test skill",
            requires_bins=[],
            requires_env=[],
            requires_config=[],
            os_filter=incompatible_filter,
        )
        
        result = engine.check_eligibility(metadata)
        
        assert not result.eligible
        assert not result.os_compatible
        assert "incompatible OS" in result.reason

    def test_check_eligibility_multiple_missing(self):
        """Test eligibility when multiple requirements are missing."""
        engine = GatingEngine()
        
        metadata = SkillMetadata(
            name="test_skill",
            description="Test skill",
            requires_bins=["nonexistent_binary"],
            requires_env=["NONEXISTENT_VAR"],
            requires_config=[],
        )
        
        result = engine.check_eligibility(metadata)
        
        assert not result.eligible
        assert len(result.missing_bins) > 0
        assert len(result.missing_env) > 0
        assert "missing binaries" in result.reason
        assert "missing env vars" in result.reason
