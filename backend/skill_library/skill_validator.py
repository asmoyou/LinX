"""Skill validation for interface and dependencies.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InterfaceDefinition:
    """Skill interface definition."""

    inputs: Dict[str, str]  # parameter_name: type
    outputs: Dict[str, str]  # output_name: type
    required_inputs: List[str]


@dataclass
class ValidationResult:
    """Result of skill validation."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]


class SkillValidator:
    """Validate skill definitions."""

    def __init__(self):
        """Initialize skill validator."""
        self.valid_types = {
            "string",
            "integer",
            "float",
            "boolean",
            "array",
            "object",
            "dict",
            "list",
            "any",
            "str",
            "int",
            "bool",
        }
        logger.info("SkillValidator initialized")

    def validate_skill(
        self,
        name: str,
        interface_definition: dict,
        dependencies: List[str],
    ) -> ValidationResult:
        """Validate a skill definition.

        Args:
            name: Skill name
            interface_definition: Interface definition
            dependencies: List of dependencies

        Returns:
            ValidationResult with validation status
        """
        errors = []
        warnings = []

        # Validate name
        if not name or not isinstance(name, str):
            errors.append("Skill name must be a non-empty string")
        else:
            normalized = name.replace("_", "").replace("-", "")
            if not normalized.isalnum():
                errors.append(
                    "Skill name must contain only alphanumeric characters, hyphens, and underscores"
                )

        # Validate interface
        interface_errors = self._validate_interface(interface_definition)
        errors.extend(interface_errors)

        # Validate dependencies
        dep_errors, dep_warnings = self._validate_dependencies(dependencies)
        errors.extend(dep_errors)
        warnings.extend(dep_warnings)

        is_valid = len(errors) == 0

        if is_valid:
            logger.info(f"Skill validation passed: {name}")
        else:
            logger.warning(f"Skill validation failed: {name}", extra={"errors": errors})

        return ValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
        )

    def _validate_interface(self, interface_def: dict) -> List[str]:
        """Validate interface definition.

        Args:
            interface_def: Interface definition dictionary

        Returns:
            List of error messages
        """
        errors = []

        if not isinstance(interface_def, dict):
            errors.append("Interface definition must be a dictionary")
            return errors

        # Check required fields
        if "inputs" not in interface_def:
            errors.append("Interface must define 'inputs'")
        if "outputs" not in interface_def:
            errors.append("Interface must define 'outputs'")

        # Validate inputs
        if "inputs" in interface_def:
            inputs = interface_def["inputs"]
            if not isinstance(inputs, dict):
                errors.append("Inputs must be a dictionary")
            else:
                for param_name, param_type in inputs.items():
                    if not isinstance(param_name, str):
                        errors.append(f"Input parameter name must be string: {param_name}")
                    if param_type.lower() not in self.valid_types:
                        errors.append(
                            f"Invalid input type '{param_type}' for parameter '{param_name}'"
                        )

        # Validate outputs
        if "outputs" in interface_def:
            outputs = interface_def["outputs"]
            if not isinstance(outputs, dict):
                errors.append("Outputs must be a dictionary")
            else:
                for output_name, output_type in outputs.items():
                    if not isinstance(output_name, str):
                        errors.append(f"Output name must be string: {output_name}")
                    if output_type.lower() not in self.valid_types:
                        errors.append(
                            f"Invalid output type '{output_type}' for output '{output_name}'"
                        )

        return errors

    def _validate_dependencies(self, dependencies: List[str]) -> tuple[List[str], List[str]]:
        """Validate dependencies.

        Args:
            dependencies: List of dependency names

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        if not isinstance(dependencies, list):
            errors.append("Dependencies must be a list")
            return errors, warnings

        for dep in dependencies:
            if not isinstance(dep, str):
                errors.append(f"Dependency must be string: {dep}")
            elif not dep.strip():
                errors.append("Dependency name cannot be empty")

        # Check for duplicates
        if len(dependencies) != len(set(dependencies)):
            warnings.append("Duplicate dependencies detected")

        return errors, warnings


# Singleton instance
_skill_validator: Optional[SkillValidator] = None


def get_skill_validator() -> SkillValidator:
    """Get or create the skill validator singleton.

    Returns:
        SkillValidator instance
    """
    global _skill_validator
    if _skill_validator is None:
        _skill_validator = SkillValidator()
    return _skill_validator
