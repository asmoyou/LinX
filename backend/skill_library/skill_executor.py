"""Skill execution wrapper.

References:
- Requirements 4: Skill Library
- Design Section 4.4: Skill Library
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from uuid import UUID
import importlib
import time

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
            
            # Execute skill (placeholder - actual implementation would load and run skill code)
            output = self._execute_skill_logic(skill_info.name, inputs)
            
            execution_time = time.time() - start_time
            
            logger.info(
                f"Skill executed: {skill_info.name}",
                extra={"execution_time": execution_time}
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
    
    def execute_skill_by_name(
        self,
        skill_name: str,
        inputs: Dict[str, Any],
        version: Optional[str] = None,
    ) -> ExecutionResult:
        """Execute a skill by name.
        
        Args:
            skill_name: Skill name
            inputs: Input parameters
            version: Optional specific version
            
        Returns:
            ExecutionResult with output or error
        """
        skill_info = self.skill_registry.get_skill_by_name(skill_name, version)
        
        if not skill_info:
            return ExecutionResult(
                success=False,
                output=None,
                execution_time=0.0,
                error_message=f"Skill not found: {skill_name}",
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
        if 'inputs' not in interface_def:
            return None
        
        required_inputs = interface_def.get('required_inputs', [])
        defined_inputs = interface_def['inputs']
        
        # Check required inputs
        for required in required_inputs:
            if required not in inputs:
                return f"Missing required input: {required}"
        
        # Check input types (basic validation)
        for input_name, input_value in inputs.items():
            if input_name not in defined_inputs:
                return f"Unknown input parameter: {input_name}"
        
        return None
    
    def _execute_skill_logic(self, skill_name: str, inputs: Dict[str, Any]) -> Any:
        """Execute skill logic (placeholder).
        
        In a real implementation, this would:
        1. Load skill code from storage
        2. Execute in sandbox
        3. Return results
        
        Args:
            skill_name: Skill name
            inputs: Input parameters
            
        Returns:
            Skill output
        """
        # Placeholder implementation
        logger.info(f"Executing skill: {skill_name} with inputs: {inputs}")
        
        # Return mock result
        return {
            "status": "completed",
            "result": f"Executed {skill_name}",
            "inputs_received": inputs,
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
