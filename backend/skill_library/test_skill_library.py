"""Tests for Skill Library.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from skill_library.default_skills import get_default_skill_definitions
from skill_library.dependency_resolver import DependencyResolver
from skill_library.skill_executor import SkillExecutor
from skill_library.skill_registry import SkillInfo, SkillRegistry
from skill_library.skill_validator import SkillValidator, ValidationResult
from skill_library.skill_versioning import SkillVersion, VersionManager


class TestSkillValidator:
    """Test skill validation."""

    def test_validate_valid_skill(self):
        """Test validation of valid skill."""
        validator = SkillValidator()

        result = validator.validate_skill(
            name="test_skill",
            interface_definition={
                "inputs": {"param1": "string", "param2": "integer"},
                "outputs": {"result": "string"},
            },
            dependencies=["pandas", "numpy"],
        )

        assert result.is_valid
        assert len(result.errors) == 0

    def test_validate_invalid_name(self):
        """Test validation fails for invalid name."""
        validator = SkillValidator()

        result = validator.validate_skill(
            name="invalid-name!",
            interface_definition={
                "inputs": {},
                "outputs": {},
            },
            dependencies=[],
        )

        assert not result.is_valid
        assert any("alphanumeric" in error for error in result.errors)

    def test_validate_missing_interface_fields(self):
        """Test validation fails for missing interface fields."""
        validator = SkillValidator()

        result = validator.validate_skill(
            name="test_skill",
            interface_definition={},
            dependencies=[],
        )

        assert not result.is_valid
        assert any("inputs" in error for error in result.errors)
        assert any("outputs" in error for error in result.errors)

    def test_validate_invalid_type(self):
        """Test validation fails for invalid parameter type."""
        validator = SkillValidator()

        result = validator.validate_skill(
            name="test_skill",
            interface_definition={
                "inputs": {"param1": "invalid_type"},
                "outputs": {"result": "string"},
            },
            dependencies=[],
        )

        assert not result.is_valid
        assert any("Invalid input type" in error for error in result.errors)


class TestSkillVersioning:
    """Test skill versioning."""

    def test_parse_version(self):
        """Test version parsing."""
        version = SkillVersion.parse("1.2.3")

        assert version.major == 1
        assert version.minor == 2
        assert version.patch == 3
        assert str(version) == "1.2.3"

    def test_version_comparison(self):
        """Test version comparison."""
        v1 = SkillVersion(1, 0, 0)
        v2 = SkillVersion(1, 1, 0)
        v3 = SkillVersion(2, 0, 0)

        assert v1 < v2
        assert v2 < v3
        assert v1 < v3

    def test_increment_versions(self):
        """Test version incrementing."""
        manager = VersionManager()
        version = SkillVersion(1, 2, 3)

        major = manager.increment_major(version)
        assert str(major) == "2.0.0"

        minor = manager.increment_minor(version)
        assert str(minor) == "1.3.0"

        patch = manager.increment_patch(version)
        assert str(patch) == "1.2.4"

    def test_version_compatibility(self):
        """Test version compatibility checking."""
        manager = VersionManager()

        required = SkillVersion(1, 2, 0)
        compatible = SkillVersion(1, 3, 5)
        incompatible_major = SkillVersion(2, 0, 0)
        incompatible_minor = SkillVersion(1, 1, 0)

        assert manager.is_compatible(required, compatible)
        assert not manager.is_compatible(required, incompatible_major)
        assert not manager.is_compatible(required, incompatible_minor)


class TestDependencyResolver:
    """Test dependency resolution."""

    def test_resolve_simple_dependencies(self):
        """Test resolving simple dependency chain."""
        resolver = DependencyResolver()

        skills = {
            "skill_a": ["skill_b", "skill_c"],
            "skill_b": [],
            "skill_c": ["skill_d"],
            "skill_d": [],
        }

        deps = resolver.resolve_dependencies("skill_a", skills)

        assert "skill_b" in deps
        assert "skill_c" in deps
        assert "skill_d" in deps
        assert deps.index("skill_d") < deps.index("skill_c")

    def test_detect_circular_dependency(self):
        """Test detection of circular dependencies."""
        resolver = DependencyResolver()

        skills = {
            "skill_a": ["skill_b"],
            "skill_b": ["skill_c"],
            "skill_c": ["skill_a"],
        }

        with pytest.raises(ValueError, match="Circular dependency"):
            resolver.resolve_dependencies("skill_a", skills)

    def test_get_load_order(self):
        """Test getting load order for skills."""
        resolver = DependencyResolver()

        skills = {
            "skill_a": ["skill_b"],
            "skill_b": ["skill_c"],
            "skill_c": [],
        }

        order = resolver.get_load_order(skills)

        assert order.index("skill_c") < order.index("skill_b")
        assert order.index("skill_b") < order.index("skill_a")


class TestSkillRegistry:
    """Test skill registry."""

    @patch("skill_library.skill_registry.get_skill_model")
    @patch("skill_library.skill_registry.get_skill_validator")
    def test_register_skill(self, mock_validator, mock_model):
        """Test skill registration."""
        # Mock validator
        mock_validation = Mock()
        mock_validation.is_valid = True
        mock_validation.errors = []
        mock_validator.return_value.validate_skill.return_value = mock_validation

        # Mock model
        mock_skill = Mock()
        mock_skill.skill_id = uuid4()
        mock_skill.name = "test_skill"
        mock_skill.description = "Test description"
        mock_skill.version = "1.0.0"
        mock_skill.interface_definition = {"inputs": {}, "outputs": {}}
        mock_skill.dependencies = []

        mock_model.return_value.get_skill_by_name.return_value = None
        mock_model.return_value.create_skill.return_value = mock_skill

        # Register skill
        registry = SkillRegistry(mock_model.return_value, mock_validator.return_value)
        skill_info = registry.register_skill(
            name="test_skill",
            description="Test description",
            interface_definition={"inputs": {}, "outputs": {}},
        )

        assert skill_info.name == "test_skill"
        assert mock_model.return_value.create_skill.called

    @patch("skill_library.skill_registry.get_skill_model")
    @patch("skill_library.skill_registry.get_skill_validator")
    def test_register_duplicate_skill(self, mock_validator, mock_model):
        """Test registration fails for duplicate skill."""
        # Mock validator
        mock_validation = Mock()
        mock_validation.is_valid = True
        mock_validator.return_value.validate_skill.return_value = mock_validation

        # Mock existing skill
        mock_existing = Mock()
        mock_model.return_value.get_skill_by_name.return_value = mock_existing

        registry = SkillRegistry(mock_model.return_value, mock_validator.return_value)

        with pytest.raises(ValueError, match="already exists"):
            registry.register_skill(
                name="test_skill",
                description="Test",
                interface_definition={"inputs": {}, "outputs": {}},
            )


class TestSkillExecutor:
    """Test skill execution."""

    @patch("skill_library.skill_executor.get_skill_registry")
    def test_execute_skill(self, mock_registry):
        """Test skill execution."""
        # Mock skill info
        skill_id = uuid4()
        mock_skill_info = Mock()
        mock_skill_info.skill_id = skill_id
        mock_skill_info.name = "test_skill"
        mock_skill_info.interface_definition = {
            "inputs": {"param1": "string"},
            "outputs": {"result": "string"},
            "required_inputs": ["param1"],
        }

        mock_registry.return_value.get_skill.return_value = mock_skill_info

        executor = SkillExecutor(mock_registry.return_value)
        result = executor.execute_skill(skill_id, {"param1": "value"})

        assert result.success
        assert result.output is not None
        assert result.execution_time >= 0

    @patch("skill_library.skill_executor.get_skill_registry")
    def test_execute_missing_required_input(self, mock_registry):
        """Test execution fails for missing required input."""
        skill_id = uuid4()
        mock_skill_info = Mock()
        mock_skill_info.skill_id = skill_id
        mock_skill_info.name = "test_skill"
        mock_skill_info.interface_definition = {
            "inputs": {"param1": "string"},
            "outputs": {"result": "string"},
            "required_inputs": ["param1"],
        }

        mock_registry.return_value.get_skill.return_value = mock_skill_info

        executor = SkillExecutor(mock_registry.return_value)
        result = executor.execute_skill(skill_id, {})

        assert not result.success
        assert "Missing required input" in result.error_message


class TestDefaultSkills:
    """Test default skills."""

    def test_get_default_skill_definitions(self):
        """Test getting default skill definitions."""
        skills = get_default_skill_definitions()

        assert len(skills) > 0
        assert any(s["name"] == "data_processing" for s in skills)
        assert any(s["name"] == "sql_query" for s in skills)

        # Verify structure
        for skill in skills:
            assert "name" in skill
            assert "description" in skill
            assert "interface_definition" in skill
            assert "dependencies" in skill
            assert "version" in skill


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
