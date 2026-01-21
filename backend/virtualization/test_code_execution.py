"""Tests for Code Execution Sandbox.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.4: Code Execution Workflow
"""

import asyncio

import pytest

from virtualization.code_execution_sandbox import (
    CodeExecutionSandbox,
    ExecutionResult,
    ExecutionStatus,
    SecurityException,
    get_code_execution_sandbox,
)
from virtualization.code_validator import (
    CodeValidator,
    ValidationResult,
    get_code_validator,
)
from virtualization.resource_limits import ResourceLimits


class TestCodeValidator:
    """Test CodeValidator functionality."""

    def test_code_validator_initialization(self):
        """Test code validator initializes correctly."""
        validator = CodeValidator()
        assert validator is not None

    def test_validate_safe_python_code(self):
        """Test validating safe Python code."""
        validator = CodeValidator()

        safe_code = """
def add(a, b):
    return a + b

result = add(2, 3)
print(result)
"""

        result = validator.validate_code(safe_code, "python")

        assert isinstance(result, ValidationResult)
        assert result.safe is True
        assert len(result.issues) == 0

    def test_validate_dangerous_python_code(self):
        """Test detecting dangerous Python code."""
        validator = CodeValidator()

        dangerous_code = """
import os
os.system('rm -rf /')
"""

        result = validator.validate_code(dangerous_code, "python")

        assert result.safe is False
        assert len(result.issues) > 0
        assert any("os" in issue.lower() for issue in result.issues)

    def test_detect_eval_exec(self):
        """Test detecting eval and exec."""
        validator = CodeValidator()

        code_with_eval = "result = eval('2 + 2')"
        result = validator.validate_code(code_with_eval, "python")
        assert not result.safe

        code_with_exec = "exec('print(\"hello\")')"
        result = validator.validate_code(code_with_exec, "python")
        assert not result.safe

    def test_detect_file_operations(self):
        """Test detecting file operations."""
        validator = CodeValidator()

        code_with_open = "f = open('file.txt', 'r')"
        result = validator.validate_code(code_with_open, "python")

        assert not result.safe
        assert any("file" in issue.lower() or "open" in issue.lower() for issue in result.issues)

    def test_detect_subprocess(self):
        """Test detecting subprocess imports."""
        validator = CodeValidator()

        code_with_subprocess = """
import subprocess
subprocess.run(['ls', '-la'])
"""

        result = validator.validate_code(code_with_subprocess, "python")

        assert not result.safe
        assert any("subprocess" in issue.lower() for issue in result.issues)

    def test_detect_network_access(self):
        """Test detecting network access."""
        validator = CodeValidator()

        code_with_socket = """
import socket
s = socket.socket()
"""

        result = validator.validate_code(code_with_socket, "python")

        assert not result.safe
        assert any("socket" in issue.lower() for issue in result.issues)

    def test_python_syntax_error(self):
        """Test detecting Python syntax errors."""
        validator = CodeValidator()

        invalid_code = """
def broken_function(
    print("missing closing parenthesis"
"""

        result = validator.validate_code(invalid_code, "python")

        assert not result.safe
        assert any("syntax" in issue.lower() for issue in result.issues)

    def test_safe_python_modules(self):
        """Test allowing safe Python modules."""
        validator = CodeValidator()

        code_with_math = """
import math
result = math.sqrt(16)
"""

        result = validator.validate_code(code_with_math, "python")

        # Should be safe (math is in SAFE_PYTHON_MODULES)
        assert result.safe is True

    def test_validate_javascript_code(self):
        """Test validating JavaScript code."""
        validator = CodeValidator()

        safe_js = """
function add(a, b) {
    return a + b;
}
const result = add(2, 3);
console.log(result);
"""

        result = validator.validate_code(safe_js, "javascript")

        # Should pass basic validation
        assert isinstance(result, ValidationResult)

    def test_detect_javascript_require(self):
        """Test detecting JavaScript require."""
        validator = CodeValidator()

        code_with_require = "const fs = require('fs');"
        result = validator.validate_code(code_with_require, "javascript")

        assert not result.safe
        assert any("require" in issue.lower() for issue in result.issues)

    def test_detect_javascript_eval(self):
        """Test detecting JavaScript eval."""
        validator = CodeValidator()

        code_with_eval = "eval('alert(1)');"
        result = validator.validate_code(code_with_eval, "javascript")

        assert not result.safe

    def test_code_length_warning(self):
        """Test warning for very long code."""
        validator = CodeValidator()

        long_code = "x = 1\n" * 10000
        result = validator.validate_code(long_code, "python")

        assert len(result.warnings) > 0
        assert any("long" in warning.lower() for warning in result.warnings)

    def test_get_safe_builtins(self):
        """Test getting safe builtins."""
        validator = CodeValidator()

        safe_builtins = validator.get_safe_builtins()

        assert "int" in safe_builtins
        assert "str" in safe_builtins
        assert "print" in safe_builtins
        assert "eval" not in safe_builtins
        assert "exec" not in safe_builtins

    def test_get_code_validator_singleton(self):
        """Test global code validator is singleton."""
        validator1 = get_code_validator()
        validator2 = get_code_validator()

        assert validator1 is validator2


class TestCodeExecutionSandbox:
    """Test CodeExecutionSandbox functionality."""

    def test_sandbox_initialization(self):
        """Test sandbox initializes correctly."""
        sandbox = CodeExecutionSandbox()

        assert sandbox is not None
        assert sandbox.sandbox_type is not None
        assert sandbox.resource_limits is not None

    def test_sandbox_with_custom_limits(self):
        """Test sandbox with custom resource limits."""
        limits = ResourceLimits(
            cpu_cores=1.0,
            memory_mb=1024,
            execution_timeout_seconds=60,
        )

        sandbox = CodeExecutionSandbox(resource_limits=limits)

        assert sandbox.resource_limits.cpu_cores == 1.0
        assert sandbox.resource_limits.memory_mb == 1024
        assert sandbox.resource_limits.execution_timeout_seconds == 60

    @pytest.mark.asyncio
    async def test_execute_safe_code(self):
        """Test executing safe code."""
        sandbox = CodeExecutionSandbox()

        code = """
def add(a, b):
    return a + b

result = add(2, 3)
print(f"Result: {result}")
"""

        result = await sandbox.execute_code(code, language="python")

        assert isinstance(result, ExecutionResult)
        assert result.execution_id is not None
        assert result.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]

    @pytest.mark.asyncio
    async def test_execute_dangerous_code_blocked(self):
        """Test that dangerous code is blocked."""
        sandbox = CodeExecutionSandbox()

        dangerous_code = """
import os
os.system('echo "hacked"')
"""

        result = await sandbox.execute_code(dangerous_code, language="python")

        assert result.success is False
        assert result.status == ExecutionStatus.FAILED
        assert "validation failed" in result.error.lower()
        assert result.validation_result is not None
        assert not result.validation_result.safe

    @pytest.mark.asyncio
    async def test_execute_with_context(self):
        """Test executing code with context."""
        sandbox = CodeExecutionSandbox()

        code = """
x = context.get('x', 0)
y = context.get('y', 0)
result = x + y
"""

        context = {"x": 10, "y": 20}

        result = await sandbox.execute_code(
            code,
            language="python",
            context=context,
        )

        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_execute_with_custom_timeout(self):
        """Test executing code with custom timeout."""
        sandbox = CodeExecutionSandbox()

        code = "result = 2 + 2"

        result = await sandbox.execute_code(
            code,
            language="python",
            timeout=5,
        )

        assert isinstance(result, ExecutionResult)

    @pytest.mark.asyncio
    async def test_execution_result_to_dict(self):
        """Test converting execution result to dictionary."""
        sandbox = CodeExecutionSandbox()

        code = "print('hello')"

        result = await sandbox.execute_code(code, language="python")
        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert "execution_id" in result_dict
        assert "success" in result_dict
        assert "status" in result_dict
        assert "output" in result_dict
        assert "error" in result_dict
        assert "execution_time_seconds" in result_dict

    @pytest.mark.asyncio
    async def test_multiple_executions(self):
        """Test multiple code executions."""
        sandbox = CodeExecutionSandbox()

        codes = [
            "result = 1 + 1",
            "result = 2 * 3",
            "result = 10 / 2",
        ]

        results = []
        for code in codes:
            result = await sandbox.execute_code(code, language="python")
            results.append(result)

        assert len(results) == 3
        assert all(isinstance(r, ExecutionResult) for r in results)

        # Each should have unique execution ID
        execution_ids = [r.execution_id for r in results]
        assert len(set(execution_ids)) == 3

    def test_get_code_execution_sandbox_singleton(self):
        """Test global sandbox is singleton."""
        sandbox1 = get_code_execution_sandbox()
        sandbox2 = get_code_execution_sandbox()

        assert sandbox1 is sandbox2


class TestExecutionResult:
    """Test ExecutionResult functionality."""

    def test_execution_result_creation(self):
        """Test creating execution result."""
        result = ExecutionResult(
            execution_id="test-123",
            success=True,
            status=ExecutionStatus.COMPLETED,
            output="Hello, World!",
        )

        assert result.execution_id == "test-123"
        assert result.success is True
        assert result.status == ExecutionStatus.COMPLETED
        assert result.output == "Hello, World!"

    def test_execution_result_with_error(self):
        """Test execution result with error."""
        result = ExecutionResult(
            execution_id="test-456",
            success=False,
            status=ExecutionStatus.FAILED,
            error="Division by zero",
        )

        assert result.success is False
        assert result.status == ExecutionStatus.FAILED
        assert result.error == "Division by zero"

    def test_execution_result_to_dict(self):
        """Test converting result to dictionary."""
        result = ExecutionResult(
            execution_id="test-789",
            success=True,
            status=ExecutionStatus.COMPLETED,
            output="Success",
            execution_time_seconds=1.5,
        )

        result_dict = result.to_dict()

        assert result_dict["execution_id"] == "test-789"
        assert result_dict["success"] is True
        assert result_dict["status"] == "completed"
        assert result_dict["output"] == "Success"
        assert result_dict["execution_time_seconds"] == 1.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
