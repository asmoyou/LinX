"""Tests for Code Execution Sandbox.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.4: Code Execution Workflow
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from virtualization.container_manager import ContainerStatus
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
from virtualization.dependency_manager import DependencyInfo
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
        """Test file operations are allowed with warnings in sandbox mode."""
        validator = CodeValidator()

        code_with_open = "f = open('file.txt', 'r')"
        result = validator.validate_code(code_with_open, "python")

        assert result.safe
        assert any(
            "file operation detected" in warning.lower() for warning in (result.warnings or [])
        )

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
        """Network calls are governed by sandbox policy, not static validator."""
        validator = CodeValidator()

        code_with_socket = """
import socket
s = socket.socket()
"""

        result = validator.validate_code(code_with_socket, "python")

        assert result.safe

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
    async def test_create_sandbox_mounts_workspace_root(self, tmp_path):
        """Workspace root should be mounted to /workspace when provided."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.create_container.return_value = "container-123"

        execution_id = "12345678-1234-5678-1234-567812345678"
        workspace_root = tmp_path / "session_workspace"

        container_id = await sandbox._create_sandbox(
            execution_id,
            workspace_root=str(workspace_root),
        )

        assert container_id == "container-123"
        assert sandbox.container_manager.create_container.called
        _, kwargs = sandbox.container_manager.create_container.call_args
        config = kwargs["config"]
        assert str(workspace_root.resolve()) in config.volume_mounts
        assert config.volume_mounts[str(workspace_root.resolve())] == "/workspace"
        assert config.network_disabled is True
        assert config.network_mode == "none"
        sandbox.container_manager.start_container.assert_called_once_with("container-123")

    @pytest.mark.asyncio
    async def test_create_sandbox_enables_bridge_network_when_requested(self):
        """Network-enabled sandboxes should use Docker bridge network."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.create_container.return_value = "container-123"

        execution_id = "12345678-1234-5678-1234-567812345678"
        await sandbox._create_sandbox(execution_id, network_enabled=True)

        _, kwargs = sandbox.container_manager.create_container.call_args
        config = kwargs["config"]
        assert config.network_disabled is False
        assert config.network_mode == "bridge"

    @pytest.mark.asyncio
    async def test_create_sandbox_uses_dependency_base_image(self):
        """Dependency cached image should override sandbox base image."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.create_container.return_value = "container-123"

        execution_id = "12345678-1234-5678-1234-567812345678"
        base_image = "linx/code-exec-deps:python-abc123"

        await sandbox._create_sandbox(execution_id, base_image=base_image)

        _, kwargs = sandbox.container_manager.create_container.call_args
        config = kwargs["config"]
        assert config.image == base_image
        assert config.environment.get("PIP_CACHE_DIR") == "/opt/linx_pip_cache"
        assert config.environment.get("LINX_DEP_WORKDIR") == "/opt/linx_runtime"
        assert config.environment.get("PIP_TARGET") == "/opt/linx_python_deps"
        assert config.environment.get("PYTHONPATH") == "/opt/linx_python_deps"
        assert config.environment.get("PYTHONNOUSERSITE") == "1"
        assert config.read_only_root is False
        assert config.tmpfs_mounts == {"/tmp": "size=1G,mode=1777"}

    def test_dependencies_available_in_container_checks_python_packages(self):
        """Existing sandbox dependency check should rely on pip show exit code."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.exec_in_container.return_value = (0, "", "")
        deps = {DependencyInfo(name="requests", language="python")}

        installed = sandbox._dependencies_available_in_container("sandbox-1", deps, "python")

        assert installed is True
        sandbox.container_manager.exec_in_container.assert_called_once()

    def test_dependencies_available_in_container_checks_javascript_packages(self):
        """JavaScript dependency check should use Node require.resolve."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.exec_in_container.return_value = (0, "", "")
        deps = {DependencyInfo(name="axios", language="javascript")}

        installed = sandbox._dependencies_available_in_container("sandbox-1", deps, "javascript")

        assert installed is True
        _, kwargs = sandbox.container_manager.exec_in_container.call_args
        assert kwargs["container_id"] == "sandbox-1"
        assert "node -e" in kwargs["command"]
        assert "require.resolve" in kwargs["command"]

    @pytest.mark.asyncio
    async def test_run_code_normalizes_node_alias_to_javascript_runtime(self):
        """`node` alias should execute using Node.js interpreter."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.exec_in_container.return_value = (0, "ok", "")

        result = await sandbox._run_code("sandbox-1", "node")

        assert result["error"] == ""
        _, kwargs = sandbox.container_manager.exec_in_container.call_args
        assert kwargs["command"].startswith("node ")
        assert kwargs["command"].endswith("/tmp/code.js")

    @pytest.mark.asyncio
    async def test_run_code_supports_typescript_runtime_command(self):
        """TypeScript should execute through ts-node with .ts code target."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.exec_in_container.return_value = (0, "ok", "")

        result = await sandbox._run_code("sandbox-1", "ts")

        assert result["error"] == ""
        _, kwargs = sandbox.container_manager.exec_in_container.call_args
        assert kwargs["command"].startswith("ts-node ")
        assert kwargs["command"].endswith("/tmp/code.ts")

    def test_cache_dependency_image_commits_container(self):
        """Installed dependencies should be snapshot as reusable Docker image."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.docker_available = True
        sandbox.container_manager.docker_client = MagicMock()
        docker_container = MagicMock()
        sandbox.container_manager.containers = {
            "sandbox-1": {"docker_container": docker_container}
        }
        deps = {DependencyInfo(name="requests", language="python")}

        image_tag = sandbox._cache_dependency_image(
            sandbox_id="sandbox-1",
            dependencies=deps,
            language="python",
        )

        assert image_tag is not None
        assert image_tag.startswith("linx/code-exec-deps:python-")
        docker_container.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_code_reuses_existing_sandbox(self):
        """When existing sandbox ID is provided, do not create/destroy new one."""
        sandbox = CodeExecutionSandbox()
        sandbox.container_manager = MagicMock()
        sandbox.container_manager.get_container_status.return_value = ContainerStatus.RUNNING
        sandbox._create_sandbox = MagicMock()
        sandbox._destroy_sandbox = MagicMock()
        sandbox.dependency_manager = None
        sandbox.code_validator = MagicMock()
        sandbox.code_validator.validate_code.return_value = ValidationResult(
            safe=True,
            issues=[],
            warnings=[],
        )

        async def _fake_inject(*args, **kwargs):
            return ("/workspace/code.py", "/workspace")

        async def _fake_run(*args, **kwargs):
            return {"output": "ok", "error": "", "return_value": None}

        sandbox._inject_code = _fake_inject
        sandbox._run_code = _fake_run

        result = await sandbox.execute_code(
            code="print('ok')",
            language="python",
            context={
                "existing_sandbox_id": "session-sandbox-1",
                "workspace_root": "/tmp/agent_sessions/test-session",
            },
        )

        assert result.success is True
        assert result.status == ExecutionStatus.COMPLETED
        sandbox._create_sandbox.assert_not_called()
        sandbox._destroy_sandbox.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_code_injects_writable_python_dependency_env(self):
        """Dependency installs should run with writable pip target and PYTHONPATH."""
        sandbox = CodeExecutionSandbox()
        sandbox.code_validator = MagicMock()
        sandbox.code_validator.validate_code.return_value = ValidationResult(
            safe=True,
            issues=[],
            warnings=[],
        )

        dep_manager = MagicMock()
        dep_manager.get_dependencies.return_value = {
            DependencyInfo(name="requests", language="python")
        }
        dep_manager.get_cached_image.return_value = None
        dep_manager.is_cached.return_value = False
        dep_manager.generate_install_script.return_value = "#!/bin/bash\necho deps\n"
        sandbox.dependency_manager = dep_manager

        async def _fake_create_sandbox(*args, **kwargs):
            return "sandbox-1"

        async def _fake_inject(*args, **kwargs):
            return ("/tmp/code.py", "/tmp")

        async def _fake_run(*args, **kwargs):
            return {"output": "ok", "error": "", "return_value": None}

        async def _fake_destroy(*args, **kwargs):
            return None

        captured_environment = {}

        async def _fake_install(sandbox_id, install_script, environment=None):
            if environment:
                captured_environment.update(environment)

        sandbox._create_sandbox = _fake_create_sandbox
        sandbox._inject_code = _fake_inject
        sandbox._run_code = _fake_run
        sandbox._destroy_sandbox = _fake_destroy
        sandbox._install_dependencies = _fake_install
        sandbox._cache_dependency_image = MagicMock(return_value="img:python-deps")

        result = await sandbox.execute_code(
            code="import requests\nprint('ok')",
            language="python",
            context={},
        )

        assert result.success is True
        assert captured_environment.get("PIP_TARGET") == "/opt/linx_python_deps"
        assert captured_environment.get("PIP_USER") == "0"
        assert captured_environment.get("PYTHONNOUSERSITE") == "1"
        assert captured_environment.get("PYTHONPATH", "").startswith("/opt/linx_python_deps")

    @pytest.mark.asyncio
    async def test_execute_code_recovers_cached_image_without_metadata(self):
        """Deterministic dependency image tag should be reused even if metadata is missing."""
        sandbox = CodeExecutionSandbox()
        sandbox.code_validator = MagicMock()
        sandbox.code_validator.validate_code.return_value = ValidationResult(
            safe=True,
            issues=[],
            warnings=[],
        )

        dep_manager = MagicMock()
        dependencies = {DependencyInfo(name="requests", language="python")}
        dep_manager.get_dependencies.return_value = dependencies
        dep_manager.get_cached_image.return_value = None
        dep_manager.build_dependency_image_tag.return_value = "linx/code-exec-deps:python-deadbeef"
        dep_manager.generate_install_script.return_value = "#!/bin/bash\necho deps\n"
        sandbox.dependency_manager = dep_manager
        sandbox._dependency_image_available = MagicMock(return_value=True)

        captured_base_image = {}

        async def _fake_create_sandbox(*args, **kwargs):
            captured_base_image["value"] = kwargs.get("base_image")
            return "sandbox-1"

        async def _fake_inject(*args, **kwargs):
            return ("/tmp/code.py", "/tmp")

        async def _fake_run(*args, **kwargs):
            return {"output": "ok", "error": "", "return_value": None}

        async def _fake_destroy(*args, **kwargs):
            return None

        install_called = {"value": False}

        async def _fake_install(*args, **kwargs):
            install_called["value"] = True

        sandbox._create_sandbox = _fake_create_sandbox
        sandbox._inject_code = _fake_inject
        sandbox._run_code = _fake_run
        sandbox._destroy_sandbox = _fake_destroy
        sandbox._install_dependencies = _fake_install

        result = await sandbox.execute_code(
            code="import requests\nprint('ok')",
            language="python",
            context={},
        )

        assert result.success is True
        assert captured_base_image["value"] == "linx/code-exec-deps:python-deadbeef"
        assert install_called["value"] is False
        dep_manager.cache_dependencies.assert_called_once_with(
            dependencies=dependencies,
            image_tag="linx/code-exec-deps:python-deadbeef",
            cache_scope=sandbox.dependency_cache_scope,
        )

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
