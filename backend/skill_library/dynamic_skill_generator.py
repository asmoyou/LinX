"""Dynamic skill generation using LLM.

References:
- Design Section 5.6: Dynamic Skill Generation
- Requirements 4: Skill Library
"""

import ast
import hashlib
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from llm_providers.router import get_llm_provider
from skill_library.skill_registry import SkillRegistry, get_skill_registry
from skill_library.skill_validator import get_skill_validator
from virtualization.code_execution_sandbox import CodeExecutionSandbox

logger = logging.getLogger(__name__)


@dataclass
class GeneratedSkill:
    """Result of skill generation."""

    skill_id: Optional[UUID]
    name: str
    description: str
    code: str
    interface_definition: dict
    dependencies: List[str]
    is_valid: bool
    validation_errors: List[str]
    test_results: Optional[Dict[str, Any]] = None


class DynamicSkillGenerator:
    """Generate skills on-the-fly using LLM."""

    def __init__(
        self,
        llm_provider=None,
        skill_registry: Optional[SkillRegistry] = None,
        sandbox: Optional[CodeExecutionSandbox] = None,
    ):
        """Initialize dynamic skill generator.

        Args:
            llm_provider: LLM provider for code generation
            skill_registry: SkillRegistry for skill registration
            sandbox: CodeExecutionSandbox for testing
        """
        self.llm_provider = llm_provider or get_llm_provider()
        self.skill_registry = skill_registry or get_skill_registry()
        self.skill_validator = get_skill_validator()
        self.sandbox = sandbox or CodeExecutionSandbox()
        logger.info("DynamicSkillGenerator initialized")

    def generate_skill(
        self,
        description: str,
        examples: Optional[List[Dict[str, Any]]] = None,
        register: bool = True,
    ) -> GeneratedSkill:
        """Generate a skill from natural language description.

        Args:
            description: Natural language description of desired skill
            examples: Optional input/output examples
            register: Whether to register the skill after generation

        Returns:
            GeneratedSkill with generated code and metadata
        """
        logger.info(f"Generating skill from description: {description}")

        # Generate skill code using LLM
        skill_code = self._generate_skill_code(description, examples)

        # Extract interface definition from code
        interface_def = self._extract_interface(skill_code)

        # Generate skill name from description
        skill_name = self._generate_skill_name(description)

        # Extract dependencies
        dependencies = self._extract_dependencies(skill_code)

        # Validate generated code
        validation_errors = self._validate_code(skill_code)
        is_valid = len(validation_errors) == 0

        # Test skill in sandbox if valid
        test_results = None
        if is_valid and examples:
            test_results = self._test_skill(skill_code, examples)
            if not test_results.get("success"):
                is_valid = False
                validation_errors.append(f"Test failed: {test_results.get('error')}")

        # Register skill if requested and valid
        skill_id = None
        if register and is_valid:
            try:
                skill_info = self.skill_registry.register_skill(
                    skill_slug=skill_name,
                    display_name=skill_name.replace("_", " ").title(),
                    description=description,
                    interface_definition=interface_def,
                    dependencies=dependencies,
                    version="1.0.0",
                )
                skill_id = skill_info.skill_id
                logger.info(f"Skill registered: {skill_name}")
            except Exception as e:
                logger.error(f"Failed to register skill: {e}")
                validation_errors.append(f"Registration failed: {e}")
                is_valid = False

        return GeneratedSkill(
            skill_id=skill_id,
            name=skill_name,
            description=description,
            code=skill_code,
            interface_definition=interface_def,
            dependencies=dependencies,
            is_valid=is_valid,
            validation_errors=validation_errors,
            test_results=test_results,
        )

    def _generate_skill_code(
        self,
        description: str,
        examples: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Generate skill code using LLM.

        Args:
            description: Skill description
            examples: Optional input/output examples

        Returns:
            Generated Python code
        """
        # Build prompt for LLM
        prompt = self._build_generation_prompt(description, examples)

        # Generate code using LLM
        try:
            response = self.llm_provider.generate(
                prompt=prompt,
                max_tokens=2000,
                temperature=0.2,  # Lower temperature for more deterministic code
            )

            # Extract code from response
            code = self._extract_code_from_response(response)
            return code

        except Exception as e:
            logger.error(f"Failed to generate skill code: {e}")
            raise ValueError(f"Code generation failed: {e}")

    def _build_generation_prompt(
        self,
        description: str,
        examples: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build prompt for skill code generation.

        Args:
            description: Skill description
            examples: Optional input/output examples

        Returns:
            Formatted prompt
        """
        prompt = f"""Generate a Python function that implements the following skill:

Description: {description}

Requirements:
1. The function should be named 'execute'
2. It should accept a dictionary of inputs as parameter
3. It should return a dictionary with the results
4. Include proper error handling
5. Add docstring with parameter descriptions
6. Keep the code simple and efficient

"""

        if examples:
            prompt += "Examples:\n"
            for i, example in enumerate(examples, 1):
                prompt += f"\nExample {i}:\n"
                prompt += f"Input: {example.get('input')}\n"
                prompt += f"Expected Output: {example.get('output')}\n"

        prompt += "\nGenerate only the Python function code, no explanations:"

        return prompt

    def _extract_code_from_response(self, response: str) -> str:
        """Extract code from LLM response.

        Args:
            response: LLM response text

        Returns:
            Extracted Python code
        """
        # Remove markdown code blocks if present
        code = response.strip()

        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()

        return code

    def _extract_interface(self, code: str) -> dict:
        """Extract interface definition from code.

        Args:
            code: Python code

        Returns:
            Interface definition dictionary
        """
        try:
            tree = ast.parse(code)

            # Find the execute function
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "execute":
                    # Extract parameters
                    inputs = {}
                    for arg in node.args.args:
                        inputs[arg.arg] = {"type": "any"}

                    return {
                        "inputs": inputs,
                        "outputs": {"result": {"type": "any"}},
                        "required_inputs": list(inputs.keys()),
                    }

            # Default interface if execute function not found
            return {
                "inputs": {"data": {"type": "any"}},
                "outputs": {"result": {"type": "any"}},
                "required_inputs": ["data"],
            }

        except Exception as e:
            logger.warning(f"Failed to extract interface: {e}")
            return {
                "inputs": {"data": {"type": "any"}},
                "outputs": {"result": {"type": "any"}},
                "required_inputs": ["data"],
            }

    def _generate_skill_name(self, description: str) -> str:
        """Generate skill name from description.

        Args:
            description: Skill description

        Returns:
            Generated skill name
        """
        # Create hash of description for uniqueness
        desc_hash = hashlib.md5(description.encode()).hexdigest()[:8]

        # Extract key words from description
        words = description.lower().split()
        key_words = [w for w in words if len(w) > 3][:3]

        if key_words:
            name = "_".join(key_words) + f"_{desc_hash}"
        else:
            name = f"generated_skill_{desc_hash}"

        return name

    def _extract_dependencies(self, code: str) -> List[str]:
        """Extract dependencies from code.

        Args:
            code: Python code

        Returns:
            List of dependencies
        """
        dependencies = []

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dependencies.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        dependencies.append(node.module)

        except Exception as e:
            logger.warning(f"Failed to extract dependencies: {e}")

        return list(set(dependencies))

    def _validate_code(self, code: str) -> List[str]:
        """Validate generated code.

        Args:
            code: Python code

        Returns:
            List of validation errors
        """
        errors = []

        # Check if code can be parsed
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            errors.append(f"Syntax error: {e}")
            return errors

        # Check for dangerous runtime calls without flagging safe identifiers like `execute`.
        dangerous_calls = {
            "eval": "Use of eval() is not allowed",
            "exec": "Use of exec() is not allowed",
            "__import__": "Use of __import__() is not allowed",
            "open": "Direct file operations not allowed",
        }

        found_messages = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func_name = None
            if isinstance(node.func, ast.Name):
                func_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                func_name = node.func.attr

            if func_name in dangerous_calls:
                found_messages.append(dangerous_calls[func_name])

        errors.extend(list(dict.fromkeys(found_messages)))

        return errors

    def _test_skill(
        self,
        code: str,
        examples: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Test skill with examples in sandbox.

        Args:
            code: Skill code
            examples: Test examples

        Returns:
            Test results
        """
        try:
            # Prepare test code
            test_code = code + "\n\n"
            test_code += "# Test execution\n"
            test_code += f"test_input = {examples[0]['input']}\n"
            test_code += "result = execute(test_input)\n"
            test_code += "print(result)\n"

            # Execute in sandbox
            result = self.sandbox.execute(
                code=test_code,
                timeout=5,
                memory_limit="256m",
            )

            return {
                "success": result.get("status") == "success",
                "output": result.get("output"),
                "error": result.get("error"),
            }

        except Exception as e:
            logger.error(f"Skill test failed: {e}")
            return {
                "success": False,
                "error": str(e),
            }


# Singleton instance
_dynamic_skill_generator: Optional[DynamicSkillGenerator] = None


def get_dynamic_skill_generator() -> DynamicSkillGenerator:
    """Get or create the dynamic skill generator singleton.

    Returns:
        DynamicSkillGenerator instance
    """
    global _dynamic_skill_generator
    if _dynamic_skill_generator is None:
        _dynamic_skill_generator = DynamicSkillGenerator()
    return _dynamic_skill_generator
