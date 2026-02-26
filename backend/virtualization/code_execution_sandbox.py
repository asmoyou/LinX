"""Code Execution Sandbox for secure code execution.

This module provides a secure sandbox environment for executing agent-generated code
with resource limits, security policies, monitoring, and dependency management.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.4: Code Execution Workflow
- Design: .kiro/specs/code-execution-improvement/design.md
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from virtualization.code_validator import ValidationResult, get_code_validator
from virtualization.container_manager import ContainerConfig, ContainerStatus, get_container_manager
from virtualization.dependency_manager import DependencyManager, get_dependency_manager
from virtualization.resource_limits import ResourceLimits, ResourceUsage, get_default_limits
from virtualization.sandbox_selector import SandboxType, get_sandbox_selector

logger = logging.getLogger(__name__)


class ExecutionStatus(Enum):
    """Execution status states."""

    PENDING = "pending"
    VALIDATING = "validating"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    MEMORY_EXCEEDED = "memory_exceeded"


@dataclass
class ExecutionResult:
    """Result of code execution."""

    execution_id: str
    success: bool
    status: ExecutionStatus
    output: str = ""
    error: str = ""
    return_value: Any = None
    metrics: Optional[ResourceUsage] = None
    execution_time_seconds: float = 0.0
    sandbox_id: Optional[str] = None
    validation_result: Optional[ValidationResult] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dictionary with execution result data
        """
        return {
            "execution_id": self.execution_id,
            "success": self.success,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "return_value": self.return_value,
            "metrics": self.metrics.to_dict() if self.metrics else None,
            "execution_time_seconds": round(self.execution_time_seconds, 3),
            "sandbox_id": self.sandbox_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SecurityException(Exception):
    """Exception raised for security violations."""

    pass


class ExecutionTimeoutException(Exception):
    """Exception raised when execution times out."""

    pass


class MemoryExceededException(Exception):
    """Exception raised when memory limit is exceeded."""

    pass


class CodeExecutionSandbox:
    """Secure sandbox for executing agent-generated code."""

    def __init__(
        self,
        sandbox_type: str = "auto",
        resource_limits: Optional[ResourceLimits] = None,
        enable_dependency_management: bool = True,
    ):
        """Initialize the code execution sandbox.

        Args:
            sandbox_type: Sandbox type ("auto", "gvisor", "firecracker", "docker_enhanced")
            resource_limits: Resource limits for execution (uses defaults if None)
            enable_dependency_management: Enable automatic dependency detection and installation
        """
        self.logger = logging.getLogger(__name__)
        self.sandbox_selector = get_sandbox_selector()
        self.container_manager = get_container_manager()
        self.code_validator = get_code_validator()
        self.dependency_manager = get_dependency_manager() if enable_dependency_management else None

        # Auto-detect best sandbox if not specified
        if sandbox_type == "auto":
            self.sandbox_type = self.sandbox_selector.detect_best_sandbox()
        else:
            self.sandbox_type = SandboxType(sandbox_type)

        self.config = self.sandbox_selector.get_sandbox_config(self.sandbox_type)
        self.resource_limits = resource_limits or get_default_limits("code_execution")

        self.logger.info(
            "CodeExecutionSandbox initialized",
            extra={
                "sandbox_type": self.sandbox_type.value,
                "security_level": self.config["security_level"],
                "cpu_cores": self.resource_limits.cpu_cores,
                "memory_mb": self.resource_limits.memory_mb,
                "timeout_seconds": self.resource_limits.execution_timeout_seconds,
                "dependency_management": enable_dependency_management,
            },
        )

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
        explicit_dependencies: Optional[List[str]] = None,
    ) -> ExecutionResult:
        """Execute code in isolated sandbox.

        Args:
            code: Source code to execute
            language: Programming language (python, javascript, etc.)
            context: Execution context and input data
            timeout: Execution timeout in seconds (uses default if None)
            explicit_dependencies: List of explicit dependencies to install

        Returns:
            ExecutionResult with output, errors, and metrics

        Raises:
            SecurityException: If code validation fails
            ExecutionTimeoutException: If execution times out
            MemoryExceededException: If memory limit is exceeded
        """
        execution_id = str(uuid4())
        started_at = datetime.utcnow()

        if context is None:
            context = {}

        if timeout is None:
            timeout = self.resource_limits.execution_timeout_seconds

        self.logger.info(
            "Starting code execution",
            extra={
                "execution_id": execution_id,
                "language": language,
                "code_length": len(code),
                "timeout": timeout,
                "has_explicit_deps": bool(explicit_dependencies),
            },
        )

        # 1. Validate code (static analysis)
        validation_result = self.code_validator.validate_code(code, language)

        if not validation_result.safe:
            self.logger.warning(
                "Code validation failed",
                extra={
                    "execution_id": execution_id,
                    "issues": validation_result.issues,
                },
            )

            return ExecutionResult(
                execution_id=execution_id,
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"Security validation failed: {', '.join(validation_result.issues)}",
                validation_result=validation_result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

        # Log warnings if any
        if validation_result.warnings:
            self.logger.info(
                "Code validation warnings",
                extra={
                    "execution_id": execution_id,
                    "warnings": validation_result.warnings,
                },
            )

        sandbox_id = None
        owns_sandbox = False

        try:
            # 2. Detect and manage dependencies
            dependencies_installed = False
            if self.dependency_manager:
                dependencies = self.dependency_manager.get_dependencies(
                    code=code,
                    language=language,
                    explicit_deps=explicit_dependencies,
                )

                if dependencies:
                    self.logger.info(
                        f"Detected {len(dependencies)} dependencies",
                        extra={
                            "execution_id": execution_id,
                            "dependencies": [dep.name for dep in dependencies],
                        },
                    )

                    # Check if dependencies are cached
                    if self.dependency_manager.is_cached(dependencies):
                        self.logger.info("Using cached dependencies")
                        cached_image = self.dependency_manager.get_cached_image(dependencies)
                        # TODO: Use cached image when creating sandbox
                    else:
                        self.logger.info("Dependencies not cached, will install")
                        dependencies_installed = True

            runtime_environment: Dict[str, str] = {}
            raw_environment = context.get("environment")
            if isinstance(raw_environment, dict):
                for key, value in raw_environment.items():
                    env_key = str(key).strip()
                    if not env_key or value is None:
                        continue
                    runtime_environment[env_key] = str(value)

            # 3. Resolve sandbox environment (reuse session sandbox when provided)
            existing_sandbox_id = str(context.get("existing_sandbox_id") or "").strip()
            network_enabled = bool(context.get("network_access", True))
            workspace_root_value = context.get("workspace_root")
            workspace_root = (
                str(workspace_root_value).strip() if workspace_root_value is not None else None
            )
            if existing_sandbox_id:
                sandbox_id = existing_sandbox_id
                sandbox_status = self.container_manager.get_container_status(sandbox_id)
                if sandbox_status != ContainerStatus.RUNNING:
                    started = self.container_manager.start_container(sandbox_id)
                    if not started:
                        raise RuntimeError(
                            f"Failed to start existing sandbox container: {sandbox_id}"
                        )
                self.logger.info(
                    "Reusing existing sandbox container",
                    extra={"execution_id": execution_id, "sandbox_id": sandbox_id},
                )
            else:
                sandbox_id = await self._create_sandbox(
                    execution_id,
                    network_enabled=network_enabled,
                    workspace_root=workspace_root or None,
                )
                owns_sandbox = True

            # 4. Install dependencies if needed
            if dependencies_installed and self.dependency_manager and dependencies:
                install_script = self.dependency_manager.generate_install_script(
                    dependencies=dependencies,
                    language=language,
                )

                if install_script:
                    self.logger.info("Installing dependencies in sandbox")
                    await self._install_dependencies(
                        sandbox_id,
                        install_script,
                        environment=runtime_environment or None,
                    )

                    # Cache the dependencies
                    self.dependency_manager.cache_dependencies(
                        dependencies=dependencies,
                        image_tag=None,  # TODO: Create and cache Docker image
                    )

            # 5. Inject code and context into sandbox
            code_file, execution_workdir = await self._inject_code(
                sandbox_id, code, context, language
            )

            # 6. Execute with resource limits and timeout
            start_time = time.time()

            result = await asyncio.wait_for(
                self._run_code(
                    sandbox_id,
                    language,
                    code_file=code_file,
                    workdir=execution_workdir,
                    environment=runtime_environment or None,
                ),
                timeout=timeout,
            )

            execution_time = time.time() - start_time

            # 7. Collect output and metrics
            output = result.get("output", "")
            error = result.get("error", "")
            return_value = result.get("return_value")

            metrics = self.container_manager.get_container_stats(sandbox_id)
            if metrics:
                metrics.execution_time_seconds = execution_time

            completed_at = datetime.utcnow()

            success = error == ""
            status = ExecutionStatus.COMPLETED if success else ExecutionStatus.FAILED

            self.logger.info(
                "Code execution completed",
                extra={
                    "execution_id": execution_id,
                    "success": success,
                    "execution_time": execution_time,
                    "sandbox_id": sandbox_id,
                },
            )

            return ExecutionResult(
                execution_id=execution_id,
                success=success,
                status=status,
                output=output,
                error=error,
                return_value=return_value,
                metrics=metrics,
                execution_time_seconds=execution_time,
                sandbox_id=sandbox_id,
                validation_result=validation_result,
                started_at=started_at,
                completed_at=completed_at,
            )

        except asyncio.TimeoutError:
            self.logger.warning(
                "Code execution timeout",
                extra={
                    "execution_id": execution_id,
                    "timeout": timeout,
                    "sandbox_id": sandbox_id,
                },
            )

            if sandbox_id and owns_sandbox:
                await self._kill_sandbox(sandbox_id)

            return ExecutionResult(
                execution_id=execution_id,
                success=False,
                status=ExecutionStatus.TIMEOUT,
                error=f"Execution timeout after {timeout} seconds",
                sandbox_id=sandbox_id,
                validation_result=validation_result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

        except MemoryExceededException as e:
            self.logger.warning(
                "Memory limit exceeded",
                extra={
                    "execution_id": execution_id,
                    "sandbox_id": sandbox_id,
                },
            )

            if sandbox_id and owns_sandbox:
                await self._kill_sandbox(sandbox_id)

            return ExecutionResult(
                execution_id=execution_id,
                success=False,
                status=ExecutionStatus.MEMORY_EXCEEDED,
                error=str(e),
                sandbox_id=sandbox_id,
                validation_result=validation_result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

        except Exception as e:
            self.logger.error(
                "Code execution failed",
                extra={
                    "execution_id": execution_id,
                    "error": str(e),
                    "sandbox_id": sandbox_id,
                },
            )

            return ExecutionResult(
                execution_id=execution_id,
                success=False,
                status=ExecutionStatus.FAILED,
                error=f"Execution error: {str(e)}",
                sandbox_id=sandbox_id,
                validation_result=validation_result,
                started_at=started_at,
                completed_at=datetime.utcnow(),
            )

        finally:
            # 7. Collect output and metrics
            if sandbox_id and owns_sandbox:
                await self._destroy_sandbox(sandbox_id)

    async def _create_sandbox(
        self,
        execution_id: str,
        *,
        network_enabled: bool = False,
        workspace_root: Optional[str] = None,
    ) -> str:
        """Create isolated sandbox environment.

        Args:
            execution_id: Execution ID for tracking

        Returns:
            Sandbox container ID
        """
        # Create a temporary agent ID for the sandbox
        from uuid import UUID

        temp_agent_id = UUID(execution_id)

        volume_mounts: Dict[str, str] = {}
        if workspace_root:
            try:
                host_workspace = Path(workspace_root).expanduser().resolve()
                host_workspace.mkdir(parents=True, exist_ok=True)
                volume_mounts[str(host_workspace)] = "/workspace"
            except Exception as workspace_error:
                self.logger.warning(
                    "Failed to mount workspace for code execution sandbox",
                    extra={
                        "execution_id": execution_id,
                        "workspace_root": workspace_root,
                        "error": str(workspace_error),
                    },
                )

        config = ContainerConfig(
            agent_id=temp_agent_id,
            name=f"code-exec-{execution_id[:8]}",
            sandbox_type=self.sandbox_type,
            resource_limits=self.resource_limits,
            network_disabled=not network_enabled,
            network_mode="bridge" if network_enabled else "none",
            volume_mounts=volume_mounts,
        )

        container_id = self.container_manager.create_container(
            agent_id=temp_agent_id,
            config=config,
        )

        # Start the container
        self.container_manager.start_container(container_id)

        self.logger.debug(
            "Sandbox created",
            extra={
                "execution_id": execution_id,
                "container_id": container_id,
            },
        )

        return container_id

    async def _inject_code(
        self,
        sandbox_id: str,
        code: str,
        context: Dict[str, Any],
        language: str,
    ) -> Tuple[str, str]:
        """Inject code and context into sandbox.

        Args:
            sandbox_id: Sandbox container ID
            code: Source code
            context: Execution context
            language: Programming language

        Returns:
            Tuple of (code_file_path, execution_workdir)
        """
        # Determine file extension and path
        extensions = {
            "python": ".py",
            "py": ".py",
            "javascript": ".js",
            "js": ".js",
            "typescript": ".ts",
            "ts": ".ts",
            "bash": ".sh",
            "sh": ".sh",
        }

        ext = extensions.get(language.lower(), ".txt")
        execution_workdir = "/workspace" if context.get("workspace_root") else "/tmp"
        code_file = f"{execution_workdir}/code{ext}"
        context_file = f"{execution_workdir}/context.json"

        try:
            self.container_manager.exec_in_container(
                container_id=sandbox_id,
                command=f"mkdir -p {execution_workdir}",
            )

            # 1. Write code to container
            self.container_manager.write_file_to_container(
                container_id=sandbox_id,
                file_path=code_file,
                content=code,
                mode=0o755 if ext == ".sh" else 0o644,
            )

            # 2. Write context as JSON
            import json

            context_json = json.dumps(context, indent=2)
            self.container_manager.write_file_to_container(
                container_id=sandbox_id,
                file_path=context_file,
                content=context_json,
                mode=0o644,
            )

            self.logger.debug(
                "Code and context injected into sandbox",
                extra={
                    "sandbox_id": sandbox_id,
                    "language": language,
                    "code_file": code_file,
                    "code_size": len(code),
                    "execution_workdir": execution_workdir,
                },
            )
            return code_file, execution_workdir

        except Exception as e:
            self.logger.error(
                f"Failed to inject code into sandbox: {e}",
                extra={"sandbox_id": sandbox_id},
            )
            raise

    async def _install_dependencies(
        self,
        sandbox_id: str,
        install_script: str,
        environment: Optional[Dict[str, str]] = None,
    ) -> None:
        """Install dependencies in sandbox.

        Args:
            sandbox_id: Sandbox container ID
            install_script: Shell script to install dependencies

        Raises:
            RuntimeError: If installation fails
        """
        self.logger.info(
            "Installing dependencies in sandbox",
            extra={
                "sandbox_id": sandbox_id,
                "script_length": len(install_script),
            },
        )

        try:
            # Write install script to container
            script_path = "/tmp/install_deps.sh"
            self.container_manager.write_file_to_container(
                container_id=sandbox_id,
                file_path=script_path,
                content=install_script,
                mode=0o755,
            )

            # Execute install script
            exit_code, stdout, stderr = self.container_manager.exec_in_container(
                container_id=sandbox_id,
                command=f"/bin/bash {script_path}",
                environment=environment,
            )

            if exit_code != 0:
                error_msg = f"Dependency installation failed with exit code {exit_code}"
                if stderr:
                    error_msg += f"\nError: {stderr}"
                if stdout:
                    error_msg += f"\nOutput: {stdout}"

                self.logger.error(
                    "Dependency installation failed",
                    extra={
                        "sandbox_id": sandbox_id,
                        "exit_code": exit_code,
                        "stdout": stdout[:500],
                        "stderr": stderr[:500],
                    },
                )
                raise RuntimeError(error_msg)

            self.logger.info(
                "Dependencies installed successfully",
                extra={
                    "sandbox_id": sandbox_id,
                    "output": stdout[:200] if stdout else "",
                },
            )

        except Exception as e:
            self.logger.error(
                f"Failed to install dependencies: {e}",
                extra={"sandbox_id": sandbox_id},
            )
            raise

    async def _run_code(
        self,
        sandbox_id: str,
        language: str,
        *,
        code_file: Optional[str] = None,
        workdir: str = "/tmp",
        environment: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Run code in sandbox.

        Args:
            sandbox_id: Sandbox container ID
            language: Programming language

        Returns:
            Dictionary with execution results
        """
        # Map language to interpreter and file
        language = language.lower()

        interpreters = {
            "python": "python3",
            "py": "python3",
            "javascript": "node",
            "js": "node",
            "typescript": "ts-node",
            "ts": "ts-node",
            "bash": "/bin/bash",
            "sh": "/bin/bash",
        }
        default_code_files = {
            "python": "/tmp/code.py",
            "py": "/tmp/code.py",
            "javascript": "/tmp/code.js",
            "js": "/tmp/code.js",
            "typescript": "/tmp/code.ts",
            "ts": "/tmp/code.ts",
            "bash": "/tmp/code.sh",
            "sh": "/tmp/code.sh",
        }

        if language not in interpreters:
            return {
                "output": "",
                "error": f"Unsupported language: {language}",
                "return_value": None,
            }

        interpreter = interpreters[language]
        target_code_file = code_file or default_code_files[language]

        try:
            # Execute code in container
            command = f"{interpreter} {target_code_file}"

            self.logger.debug(
                f"Executing code in sandbox",
                extra={
                    "sandbox_id": sandbox_id,
                    "command": command,
                    "workdir": workdir,
                },
            )

            exit_code, stdout, stderr = self.container_manager.exec_in_container(
                container_id=sandbox_id,
                command=command,
                workdir=workdir,
                environment=environment,
            )

            # Parse results
            output = stdout if stdout else ""
            error = stderr if stderr else ""

            # If exit code is non-zero, treat as error
            if exit_code != 0 and not error:
                error = f"Process exited with code {exit_code}"

            # Try to extract return value from output
            # For Python, we could look for special markers
            return_value = None

            self.logger.debug(
                f"Code execution completed",
                extra={
                    "sandbox_id": sandbox_id,
                    "exit_code": exit_code,
                    "output_length": len(output),
                    "error_length": len(error),
                },
            )

            return {
                "output": output,
                "error": error,
                "return_value": return_value,
            }

        except Exception as e:
            self.logger.error(
                f"Failed to run code in sandbox: {e}",
                extra={"sandbox_id": sandbox_id},
            )
            return {
                "output": "",
                "error": f"Execution error: {str(e)}",
                "return_value": None,
            }

    async def _kill_sandbox(self, sandbox_id: str) -> None:
        """Force kill a sandbox.

        Args:
            sandbox_id: Sandbox container ID
        """
        self.container_manager.stop_container(sandbox_id, timeout=1)

        self.logger.debug(
            "Sandbox killed",
            extra={"sandbox_id": sandbox_id},
        )

    async def _destroy_sandbox(self, sandbox_id: str) -> None:
        """Destroy and cleanup sandbox.

        Args:
            sandbox_id: Sandbox container ID
        """
        self.container_manager.terminate_container(sandbox_id)

        self.logger.debug(
            "Sandbox destroyed",
            extra={"sandbox_id": sandbox_id},
        )


# Global sandbox instance
_code_execution_sandbox: Optional[CodeExecutionSandbox] = None


def get_code_execution_sandbox(
    sandbox_type: str = "auto",
    resource_limits: Optional[ResourceLimits] = None,
) -> CodeExecutionSandbox:
    """Get the global code execution sandbox instance.

    Args:
        sandbox_type: Sandbox type (only used on first call)
        resource_limits: Resource limits (only used on first call)

    Returns:
        CodeExecutionSandbox instance
    """
    global _code_execution_sandbox
    if _code_execution_sandbox is None:
        _code_execution_sandbox = CodeExecutionSandbox(
            sandbox_type=sandbox_type,
            resource_limits=resource_limits,
        )
    return _code_execution_sandbox
