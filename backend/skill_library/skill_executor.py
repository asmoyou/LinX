"""Skill execution wrapper.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
- Design: .kiro/specs/code-execution-improvement/design.md
"""

import asyncio
import importlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID

from skill_library.skill_loader import SkillLoader, get_skill_loader
from skill_library.skill_registry import SkillRegistry, get_skill_registry

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of skill execution."""

    success: bool
    output: Any
    execution_time: float
    error_message: Optional[str] = None


class SkillExecutor:
    """Execute skills with proper error handling."""

    def __init__(self, skill_registry: Optional[SkillRegistry] = None):
        """Initialize skill executor.

        Args:
            skill_registry: SkillRegistry for retrieving skills
        """
        self.skill_registry = skill_registry or get_skill_registry()
        self.skill_loader = get_skill_loader()
        logger.info("SkillExecutor initialized")

    def execute_skill(
        self,
        skill_id: UUID,
        inputs: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute a skill with given inputs.

        Args:
            skill_id: Skill UUID
            inputs: Input parameters
            timeout: Optional execution timeout in seconds

        Returns:
            ExecutionResult with output or error
        """
        start_time = time.time()

        try:
            # Get skill info
            skill_info = self.skill_registry.get_skill(skill_id)
            if not skill_info:
                return ExecutionResult(
                    success=False,
                    output=None,
                    execution_time=0.0,
                    error_message=f"Skill not found: {skill_id}",
                )

            # Validate inputs
            validation_error = self._validate_inputs(skill_info.interface_definition, inputs)
            if validation_error:
                return ExecutionResult(
                    success=False,
                    output=None,
                    execution_time=time.time() - start_time,
                    error_message=validation_error,
                )

            # Execute skill (real implementation with code execution)
            output = self._execute_skill_logic(skill_info, inputs)

            execution_time = time.time() - start_time

            logger.info(
                "Skill executed",
                extra={
                    "skill_slug": skill_info.skill_slug,
                    "execution_time": execution_time,
                },
            )

            return ExecutionResult(
                success=True,
                output=output,
                execution_time=execution_time,
            )

        except Exception as e:
            logger.error(f"Skill execution failed: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                output=None,
                execution_time=time.time() - start_time,
                error_message=str(e),
            )

    def execute_skill_by_slug(
        self,
        skill_slug: str,
        inputs: Dict[str, Any],
        version: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a skill by slug.

        Args:
            skill_slug: Skill slug
            inputs: Input parameters
            version: Optional specific version

        Returns:
            ExecutionResult with output or error
        """
        skill_info = self.skill_registry.get_skill_by_slug(skill_slug, version)

        if not skill_info:
            return ExecutionResult(
                success=False,
                output=None,
                execution_time=0.0,
                error_message=f"Skill not found: {skill_slug}",
            )

        return self.execute_skill(skill_info.skill_id, inputs)

    def _validate_inputs(self, interface_def: dict, inputs: Dict[str, Any]) -> Optional[str]:
        """Validate inputs against interface definition.

        Args:
            interface_def: Interface definition
            inputs: Input parameters

        Returns:
            Error message if validation fails, None otherwise
        """
        if "inputs" not in interface_def:
            return None

        required_inputs = interface_def.get("required_inputs", [])
        defined_inputs = interface_def["inputs"]

        # Check required inputs
        for required in required_inputs:
            if required not in inputs:
                return f"Missing required input: {required}"

        # Check input types (basic validation)
        for input_name, input_value in inputs.items():
            if input_name not in defined_inputs:
                return f"Unknown input parameter: {input_name}"

        return None

    def _execute_skill_logic(self, skill_info: Any, inputs: Dict[str, Any]) -> Any:
        """Execute skill logic with real code execution.

        This implementation:
        1. Loads skill code from storage
        2. Executes in sandbox environment
        3. Returns actual results

        Args:
            skill_info: SkillInfo object with skill details
            inputs: Input parameters

        Returns:
            Skill output
        """
        logger.info(f"Executing skill: {skill_info.name} with inputs: {inputs}")

        try:
            # Load skill package with code extraction
            skill_package = self.skill_loader.load_skill(
                skill_id=skill_info.skill_id,
                skill_name=skill_info.skill_slug,
                skill_md_content=getattr(skill_info, 'skill_md_content', None),
                storage_path=skill_info.storage_path,
                manifest=skill_info.manifest,
                package_files=getattr(skill_info, "package_files", None),
            )

            # Check if skill has executable code
            if not skill_package.code_blocks:
                logger.warning(f"Skill {skill_info.skill_slug} has no executable code blocks")
                return {
                    "status": "completed",
                    "result": f"Skill {skill_info.skill_slug} is a documentation-only skill",
                    "inputs_received": inputs,
                }

            # Get Python code (primary execution language)
            python_code = skill_package.get_executable_code('python')
            
            if python_code:
                # Execute Python code in sandbox
                result = self._execute_python_code(python_code, inputs)
                return result
            
            # Get Bash code as fallback
            bash_code = skill_package.get_executable_code('bash')
            
            if bash_code:
                # Execute Bash code in sandbox
                result = self._execute_bash_code(bash_code, inputs)
                return result

            # No executable code found
            logger.warning(f"Skill {skill_info.skill_slug} has no Python or Bash executable code")
            return {
                "status": "completed",
                "result": f"Skill {skill_info.skill_slug} has code blocks but none are executable",
                "inputs_received": inputs,
                "available_languages": [cb.language for cb in skill_package.code_blocks],
            }

        except Exception as e:
            logger.error(f"Skill execution error: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
                "inputs_received": inputs,
            }

    def _execute_python_code(self, code: str, inputs: Dict[str, Any]) -> Any:
        """Execute Python code in sandbox.

        Args:
            code: Python code to execute
            inputs: Input parameters

        Returns:
            Execution result
        """
        # Import sandbox here to avoid circular imports
        from virtualization.code_execution_sandbox import get_code_execution_sandbox

        try:
            sandbox = get_code_execution_sandbox()
            
            # Prepare code with input injection
            wrapped_code = f"""
import json
import sys

# Injected inputs
inputs = {repr(inputs)}

# User code
{code}

# Try to get result if main() or execute() function exists
result = None
if 'main' in dir():
    result = main(inputs)
elif 'execute' in dir():
    result = execute(inputs)
elif 'run' in dir():
    result = run(inputs)

# Output result as JSON
if result is not None:
    print(json.dumps({{"result": result}}))
"""
            
            # Execute in sandbox (async)
            loop = asyncio.get_event_loop()
            execution_result = loop.run_until_complete(
                sandbox.execute_code(
                    code=wrapped_code,
                    language='python',
                    context=inputs,
                    timeout=30,
                )
            )

            if execution_result.success:
                # Try to parse JSON output
                try:
                    import json
                    output_data = json.loads(execution_result.output)
                    return {
                        "status": "completed",
                        "result": output_data.get("result"),
                        "output": execution_result.output,
                    }
                except json.JSONDecodeError:
                    # Return raw output
                    return {
                        "status": "completed",
                        "result": execution_result.output,
                        "output": execution_result.output,
                    }
            else:
                return {
                    "status": "failed",
                    "error": execution_result.error,
                    "output": execution_result.output,
                }

        except Exception as e:
            logger.error(f"Python code execution failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
            }

    def _execute_bash_code(self, code: str, inputs: Dict[str, Any]) -> Any:
        """Execute Bash code in sandbox.

        Args:
            code: Bash code to execute
            inputs: Input parameters

        Returns:
            Execution result
        """
        # Import sandbox here to avoid circular imports
        from virtualization.code_execution_sandbox import get_code_execution_sandbox

        try:
            sandbox = get_code_execution_sandbox()
            
            # Execute in sandbox (async)
            loop = asyncio.get_event_loop()
            execution_result = loop.run_until_complete(
                sandbox.execute_code(
                    code=code,
                    language='bash',
                    context=inputs,
                    timeout=30,
                )
            )

            if execution_result.success:
                return {
                    "status": "completed",
                    "result": execution_result.output,
                    "output": execution_result.output,
                }
            else:
                return {
                    "status": "failed",
                    "error": execution_result.error,
                    "output": execution_result.output,
                }

        except Exception as e:
            logger.error(f"Bash code execution failed: {e}", exc_info=True)
            return {
                "status": "failed",
                "error": str(e),
            }


# Singleton instance
_skill_executor: Optional[SkillExecutor] = None


def get_skill_executor() -> SkillExecutor:
    """Get or create the skill executor singleton.

    Returns:
        SkillExecutor instance
    """
    global _skill_executor
    if _skill_executor is None:
        _skill_executor = SkillExecutor()
    return _skill_executor
