"""
Unit tests for Natural Language Tester.

Tests cover:
- Command parsing from SKILL.md
- Bash command extraction
- Python code extraction
- API call extraction
- Simulation logic
- Placeholder replacement
- Dry run mode
"""

import pytest
from skill_library.nl_tester import (
    NaturalLanguageTester,
    TestCommand,
    TestResult,
    CommandType,
)


class TestNaturalLanguageTester:
    """Test suite for NaturalLanguageTester."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tester = NaturalLanguageTester()

    def test_parse_bash_command(self):
        """Test parsing bash command from SKILL.md."""
        skill_md = """
# Echo Skill

Print a message.

```bash
echo "Hello ${name}"
```
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 1
        assert commands[0].command_type == CommandType.BASH
        assert "echo" in commands[0].command
        assert "${name}" in commands[0].command
        assert commands[0].language == "bash"

    def test_parse_python_command(self):
        """Test parsing Python code from SKILL.md."""
        skill_md = """
# Data Processing Skill

Process data using Python.

```python
import pandas as pd
df = pd.read_csv("data.csv")
print(df.head())
```
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 1
        assert commands[0].command_type == CommandType.PYTHON
        assert "import pandas" in commands[0].command
        assert commands[0].language == "python"

    def test_parse_api_call(self):
        """Test parsing API call from SKILL.md."""
        skill_md = """
# API Skill

Make an API call.

```bash
curl -X POST https://api.example.com/endpoint \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 1
        assert commands[0].command_type == CommandType.API
        assert "curl" in commands[0].command
        assert "https://api.example.com" in commands[0].command

    def test_parse_multiple_commands(self):
        """Test parsing multiple commands from SKILL.md."""
        skill_md = """
# Multi-Step Skill

First, fetch data:

```bash
curl https://api.example.com/data
```

Then, process it:

```python
import json
data = json.loads(response)
print(data)
```
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 2
        assert commands[0].command_type == CommandType.API
        assert commands[1].command_type == CommandType.PYTHON

    def test_parse_command_with_description(self):
        """Test extracting command description."""
        skill_md = """
# Weather Skill

Fetch current weather data for the specified location.

```bash
curl "https://api.weather.com/v1/current?location=${location}"
```
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 1
        assert "location" in commands[0].description.lower()

    def test_parse_empty_code_block(self):
        """Test handling empty code blocks."""
        skill_md = """
# Empty Skill

```bash
```
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 0

    def test_parse_no_code_blocks(self):
        """Test handling SKILL.md with no code blocks."""
        skill_md = """
# Text Only Skill

This skill has no code blocks.
Just plain text instructions.
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 0

    def test_simulate_execution(self):
        """Test simulating command execution."""
        commands = [
            TestCommand(
                command_type=CommandType.BASH,
                command='echo "Hello ${name}"',
                description="Print greeting",
                language="bash",
            )
        ]

        output = self.tester.simulate_execution(commands, "for John")

        assert "Command 1" in output
        assert "Print greeting" in output
        assert "bash" in output
        assert "Hello" in output

    def test_placeholder_replacement(self):
        """Test replacing placeholders in commands."""
        params = {"location": "London", "api_key": "abc123"}

        # Test ${var} format
        result = self.tester._replace_placeholders(
            "curl https://api.weather.com?location=${location}", params
        )
        assert "location=London" in result

        # Test {var} format
        result = self.tester._replace_placeholders(
            "curl https://api.weather.com?location={location}", params
        )
        assert "location=London" in result

        # Test $var format
        result = self.tester._replace_placeholders(
            "curl https://api.weather.com?key=$api_key", params
        )
        assert "key=abc123" in result

    def test_extract_parameters_from_natural_input(self):
        """Test extracting parameters from natural language input."""
        # Test location extraction
        params = self.tester._extract_parameters("Get weather for London")
        assert params["location"] == "London"

        # Test API key extraction
        params = self.tester._extract_parameters("with API key abc123")
        assert params["api_key"] == "abc123"

        # Test model extraction
        params = self.tester._extract_parameters("using model gpt-4")
        assert params["model"] == "gpt-4"

        # Test query is always included
        params = self.tester._extract_parameters("any input")
        assert params["query"] == "any input"
        assert params["input"] == "any input"

    def test_generate_mock_output_bash(self):
        """Test generating mock output for bash commands."""
        output = self.tester._generate_mock_output(CommandType.BASH, "ls -la")
        assert "bash" in output.lower()
        assert "success" in output.lower()

    def test_generate_mock_output_python(self):
        """Test generating mock output for Python commands."""
        output = self.tester._generate_mock_output(CommandType.PYTHON, "print('hello')")
        assert "python" in output.lower()
        assert "success" in output.lower()

    def test_generate_mock_output_api_weather(self):
        """Test generating mock output for weather API calls."""
        output = self.tester._generate_mock_output(
            CommandType.API, "curl https://api.weather.com"
        )
        assert "temperature" in output
        assert "condition" in output
        assert "location" in output

    def test_generate_mock_output_api_generic(self):
        """Test generating mock output for generic API calls."""
        output = self.tester._generate_mock_output(
            CommandType.API, "curl https://api.example.com"
        )
        assert "status" in output
        assert "success" in output

    def test_test_skill_dry_run(self):
        """Test testing skill in dry run mode."""
        skill_md = """
# Weather Skill

```bash
curl "https://api.weather.com/v1/current?location=${location}"
```
"""
        result = self.tester.test_skill(skill_md, "Get weather for London", dry_run=True)

        assert result.success is True
        assert result.input == "Get weather for London"
        assert len(result.parsed_commands) == 1
        assert result.simulated_output != ""
        assert result.actual_output is None
        assert result.execution_time >= 0

    def test_test_skill_no_commands(self):
        """Test testing skill with no executable commands."""
        skill_md = """
# Text Only Skill

This skill has no code blocks.
"""
        result = self.tester.test_skill(skill_md, "test input", dry_run=True)

        assert result.success is False
        assert "No executable commands" in result.error
        assert len(result.parsed_commands) == 0

    def test_test_skill_with_error(self):
        """Test handling errors during skill testing."""
        # Pass invalid input that will cause an error
        result = self.tester.test_skill(None, "test input", dry_run=True)

        assert result.success is False
        assert result.error is not None

    def test_determine_command_type_bash(self):
        """Test determining bash command type."""
        assert (
            self.tester._determine_command_type("bash", "ls -la") == CommandType.BASH
        )
        assert self.tester._determine_command_type("sh", "echo hello") == CommandType.BASH
        assert (
            self.tester._determine_command_type("shell", "pwd") == CommandType.BASH
        )

    def test_determine_command_type_python(self):
        """Test determining Python command type."""
        assert (
            self.tester._determine_command_type("python", "print('hello')")
            == CommandType.PYTHON
        )
        assert (
            self.tester._determine_command_type("py", "import os") == CommandType.PYTHON
        )

    def test_determine_command_type_api(self):
        """Test determining API command type."""
        assert (
            self.tester._determine_command_type("bash", "curl https://api.example.com")
            == CommandType.API
        )
        assert (
            self.tester._determine_command_type("api", "GET /endpoint")
            == CommandType.API
        )

    def test_determine_command_type_unknown(self):
        """Test determining unknown command type."""
        assert (
            self.tester._determine_command_type("unknown", "some code")
            == CommandType.UNKNOWN
        )

    def test_parse_commands_with_language_variants(self):
        """Test parsing commands with different language identifiers."""
        skill_md = """
```sh
echo "shell"
```

```zsh
echo "zsh"
```

```py
print("python")
```
"""
        commands = self.tester.parse_commands(skill_md)

        assert len(commands) == 3
        assert commands[0].command_type == CommandType.BASH
        assert commands[1].command_type == CommandType.BASH
        assert commands[2].command_type == CommandType.PYTHON

    def test_full_workflow_weather_example(self):
        """Test full workflow with weather skill example."""
        skill_md = """
---
name: Weather Lookup
description: Get current weather for a location
metadata: {"requires": {"bins": ["curl"]}, "emoji": "🌤️"}
---

# Weather Lookup Skill

This skill fetches current weather data for a specified location.

To use this skill, provide a location name.

```bash
curl "https://api.weather.com/v1/current?location=${location}&apikey=${api_key}"
```

The API will return JSON with temperature, condition, and forecast.
"""
        result = self.tester.test_skill(
            skill_md, "Get weather for London with API key abc123", dry_run=True
        )

        assert result.success is True
        assert len(result.parsed_commands) == 1
        assert result.parsed_commands[0].command_type == CommandType.API
        assert "London" in result.simulated_output or "location" in result.simulated_output
        assert result.execution_time >= 0

    def test_placeholder_replacement_preserves_unmatched(self):
        """Test that unmatched placeholders are preserved."""
        params = {"location": "London"}

        result = self.tester._replace_placeholders(
            "curl https://api.weather.com?location=${location}&key=${api_key}", params
        )

        assert "location=London" in result
        assert "${api_key}" in result  # Unmatched placeholder preserved
