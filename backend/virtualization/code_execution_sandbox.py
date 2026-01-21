"""Code Execution Sandbox for secure code execution.

This module provides a secure sandbox environment for executing agent-generated code
with resource limits, security policies, and monitoring.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.4: Code Execution Workflow
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from uuid import uuid4

from virtualization.code_validator import ValidationResult, get_code_validator
from virtualization.container_manager import ContainerConfig, get_container_manager
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
    ):
        """Initialize the code execution sandbox.

        Args:
            sandbox_type: Sandbox type ("auto", "gvisor", "firecracker", "docker_enhanced")
            resource_limits: Resource limits for execution (uses defaults if None)
        """
        self.logger = logging.getLogger(__name__)
        self.sandbox_selector = get_sandbox_selector()
        self.container_manager = get_container_manager()
        self.code_validator = get_code_validator()

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
            },
        )

    async def execute_code(
        self,
        code: str,
        language: str = "python",
        context: Optional[Dict[str, Any]] = None,
        timeout: Optional[int] = None,
    ) -> ExecutionResult:
        """Execute code in isolated sandbox.

        Args:
            code: Source code to execute
            language: Programming language (python, javascript, etc.)
            context: Execution context and input data
            timeout: Execution timeout in seconds (uses default if None)

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

        try:
            # 2. Create isolated sandbox environment
            sandbox_id = await self._create_sandbox(execution_id)

            # 3. Inject code and context into sandbox
            await self._inject_code(sandbox_id, code, context, language)

            # 4. Execute with resource limits and timeout
            start_time = time.time()

            result = await asyncio.wait_for(
                self._run_code(sandbox_id, language),
                timeout=timeout,
            )

            execution_time = time.time() - start_time

            # 5. Collect output and metrics
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

            if sandbox_id:
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

            if sandbox_id:
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
            # 6. Cleanup sandbox
            if sandbox_id:
                await self._destroy_sandbox(sandbox_id)

    async def _create_sandbox(self, execution_id: str) -> str:
        """Create isolated sandbox environment.

        Args:
            execution_id: Execution ID for tracking

        Returns:
            Sandbox container ID
        """
        # Create a temporary agent ID for the sandbox
        from uuid import UUID

        temp_agent_id = UUID(execution_id)

        config = ContainerConfig(
            agent_id=temp_agent_id,
            name=f"code-exec-{execution_id[:8]}",
            sandbox_type=self.sandbox_type,
            resource_limits=self.resource_limits,
            network_disabled=True,  # Disable network for code execution
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
    ) -> None:
        """Inject code and context into sandbox.

        Args:
            sandbox_id: Sandbox container ID
            code: Source code
            context: Execution context
            language: Programming language
        """
        # In a real implementation, this would:
        # 1. Write code to a file in the container
        # 2. Write context data as JSON
        # 3. Set up execution environment

        self.logger.debug(
            "Code injected into sandbox",
            extra={
                "sandbox_id": sandbox_id,
                "language": language,
            },
        )

    async def _run_code(self, sandbox_id: str, language: str) -> Dict[str, Any]:
        """Run code in sandbox.

        Args:
            sandbox_id: Sandbox container ID
            language: Programming language

        Returns:
            Dictionary with execution results
        """
        # In a real implementation, this would:
        # 1. Execute the code in the container
        # 2. Capture stdout, stderr
        # 3. Get return value
        # 4. Monitor resource usage

        # Simulate execution
        await asyncio.sleep(0.1)

        return {
            "output": "Execution completed successfully",
            "error": "",
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
