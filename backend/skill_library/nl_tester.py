"""
Natural Language Tester for Agent Skills.

This module provides functionality to test Agent Skills using natural language input.
It parses commands from SKILL.md instructions and simulates or executes them.

References:
- Requirements 1.2: Natural language testing interface
- Design Section 4: Natural Language Tester
"""

import re
import time
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from enum import Enum


class CommandType(str, Enum):
    """Type of command extracted from instructions."""

    BASH = "bash"
    PYTHON = "python"
    API = "api"
    UNKNOWN = "unknown"


@dataclass
class TestCommand:
    """Parsed command from skill instructions."""

    command_type: CommandType
    command: str
    description: str
    language: Optional[str] = None  # Language from code fence (bash, python, etc.)


@dataclass
class TestResult:
    """Result of skill test."""

    success: bool
    input: str
    parsed_commands: List[TestCommand]
    simulated_output: str
    actual_output: Optional[str] = None  # If dry_run=False
    execution_time: float = 0.0
    error: Optional[str] = None


class NaturalLanguageTester:
    """Test Agent Skills with natural language input."""

    def __init__(self):
        """Initialize the natural language tester."""
        self.code_block_pattern = re.compile(
            r"```(\w+)?\n(.*?)```", re.DOTALL | re.MULTILINE
        )
        self.placeholder_pattern = re.compile(r"\{(\w+)\}|\$\{(\w+)\}|\$(\w+)")

    def test_skill(
        self, skill_md_content: str, natural_input: str, dry_run: bool = True
    ) -> TestResult:
        """Test skill with natural language input.

        Args:
            skill_md_content: Full SKILL.md content
            natural_input: Natural language test input
            dry_run: If True, simulate execution without running commands

        Returns:
            Test result with parsed commands and output
        """
        start_time = time.time()

        try:
            # Parse commands from instructions
            parsed_commands = self.parse_commands(skill_md_content)

            if not parsed_commands:
                return TestResult(
                    success=False,
                    input=natural_input,
                    parsed_commands=[],
                    simulated_output="",
                    error="No executable commands found in SKILL.md",
                    execution_time=time.time() - start_time,
                )

            # Simulate or execute
            if dry_run:
                output = self.simulate_execution(parsed_commands, natural_input)
                return TestResult(
                    success=True,
                    input=natural_input,
                    parsed_commands=parsed_commands,
                    simulated_output=output,
                    execution_time=time.time() - start_time,
                )
            else:
                # TODO: Implement actual execution in sandbox
                output = self.simulate_execution(parsed_commands, natural_input)
                return TestResult(
                    success=True,
                    input=natural_input,
                    parsed_commands=parsed_commands,
                    simulated_output=output,
                    actual_output="[Actual execution not yet implemented]",
                    execution_time=time.time() - start_time,
                )

        except Exception as e:
            return TestResult(
                success=False,
                input=natural_input,
                parsed_commands=[],
                simulated_output="",
                error=str(e),
                execution_time=time.time() - start_time,
            )

    def parse_commands(self, skill_md_content: str) -> List[TestCommand]:
        """Parse commands from skill instructions.

        Args:
            skill_md_content: Full SKILL.md content

        Returns:
            List of parsed commands
        """
        commands = []

        # Find all code blocks
        matches = self.code_block_pattern.finditer(skill_md_content)

        for match in matches:
            language = match.group(1) or "unknown"
            code = match.group(2).strip()

            if not code:
                continue

            # Determine command type
            command_type = self._determine_command_type(language, code)

            # Extract description (text before code block)
            start_pos = match.start()
            # Look back for description (previous paragraph)
            text_before = skill_md_content[:start_pos]
            lines_before = text_before.split("\n")
            description = ""
            for line in reversed(lines_before):
                line = line.strip()
                if line and not line.startswith("#"):
                    description = line
                    break

            commands.append(
                TestCommand(
                    command_type=command_type,
                    command=code,
                    description=description or f"Execute {language} code",
                    language=language,
                )
            )

        return commands

    def simulate_execution(
        self, commands: List[TestCommand], natural_input: str
    ) -> str:
        """Simulate command execution.

        Args:
            commands: Parsed commands
            natural_input: Natural language input

        Returns:
            Simulated output
        """
        output_parts = []

        # Extract parameters from natural input
        params = self._extract_parameters(natural_input)

        for i, cmd in enumerate(commands, 1):
            output_parts.append(f"[Command {i}] {cmd.description}")
            output_parts.append(f"Type: {cmd.command_type.value}")

            # Replace placeholders
            executed_command = self._replace_placeholders(cmd.command, params)
            output_parts.append(f"Command: {executed_command}")

            # Generate mock output based on command type
            mock_output = self._generate_mock_output(cmd.command_type, executed_command)
            output_parts.append(f"Output: {mock_output}")
            output_parts.append("")  # Empty line

        return "\n".join(output_parts)

    def _determine_command_type(self, language: str, code: str) -> CommandType:
        """Determine command type from language and code content.

        Args:
            language: Language from code fence
            code: Code content

        Returns:
            Command type
        """
        language_lower = language.lower()

        # Check for API calls first (based on content)
        if "curl" in code or "http" in code.lower() or "api" in language_lower:
            return CommandType.API
        # Then check language-specific types
        elif language_lower in ("bash", "sh", "shell", "zsh"):
            return CommandType.BASH
        elif language_lower in ("python", "py"):
            return CommandType.PYTHON
        else:
            return CommandType.UNKNOWN

    def _extract_parameters(self, natural_input: str) -> Dict[str, str]:
        """Extract parameters from natural language input.

        Args:
            natural_input: Natural language input

        Returns:
            Dictionary of parameter names to values
        """
        params = {}

        # Simple extraction: look for common patterns
        # "for London" -> location=London
        # "with API key abc123" -> api_key=abc123
        # "using model gpt-4" -> model=gpt-4

        patterns = [
            (r"for\s+(\w+)", "location"),
            (r"in\s+(\w+)", "location"),
            (r"with\s+api\s+key\s+(\S+)", "api_key"),
            (r"using\s+model\s+(\S+)", "model"),
            (r"model\s+(\S+)", "model"),
            (r"key\s+(\S+)", "api_key"),
        ]

        for pattern, param_name in patterns:
            match = re.search(pattern, natural_input, re.IGNORECASE)
            if match:
                params[param_name] = match.group(1)

        # Also add the full input as "query"
        params["query"] = natural_input
        params["input"] = natural_input

        return params

    def _replace_placeholders(self, command: str, params: Dict[str, str]) -> str:
        """Replace placeholders in command with parameter values.

        Args:
            command: Command with placeholders
            params: Parameter values

        Returns:
            Command with placeholders replaced
        """

        def replace_match(match):
            # Try all groups (different placeholder formats)
            param_name = match.group(1) or match.group(2) or match.group(3)
            return params.get(param_name, match.group(0))

        return self.placeholder_pattern.sub(replace_match, command)

    def _generate_mock_output(self, command_type: CommandType, command: str) -> str:
        """Generate mock output based on command type.

        Args:
            command_type: Type of command
            command: Command string

        Returns:
            Mock output
        """
        if command_type == CommandType.BASH:
            return "[Simulated bash output: Command executed successfully]"
        elif command_type == CommandType.PYTHON:
            return "[Simulated Python output: Script executed successfully]"
        elif command_type == CommandType.API:
            if "weather" in command.lower():
                return '{"temperature": 72, "condition": "sunny", "location": "London"}'
            else:
                return '{"status": "success", "data": {...}}'
        else:
            return "[Simulated output]"
