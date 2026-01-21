"""Virtualization module for Digital Workforce Platform.

This module provides containerized agent execution with multi-layer security isolation:
- Automatic sandbox selection (gVisor, Firecracker, Docker Enhanced)
- Container provisioning and lifecycle management
- Resource limits enforcement (CPU, memory, network)
- Security policies and network isolation
- Sandbox pool management for performance
- Code execution sandbox with validation and monitoring

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5: Code Execution Environment and Security Isolation
"""

from virtualization.code_execution_sandbox import (
    CodeExecutionSandbox,
    ExecutionResult,
    ExecutionStatus,
    ExecutionTimeoutException,
    MemoryExceededException,
    SecurityException,
    get_code_execution_sandbox,
)
from virtualization.code_validator import (
    CodeValidator,
    ValidationResult,
    get_code_validator,
)
from virtualization.container_manager import (
    ContainerConfig,
    ContainerManager,
    ContainerStatus,
    get_container_manager,
)
from virtualization.resource_limits import (
    ResourceLimits,
    ResourceUsage,
    get_default_limits,
)
from virtualization.sandbox_pool import (
    SandboxPool,
    get_sandbox_pool,
)
from virtualization.sandbox_selector import (
    SandboxSelector,
    SandboxType,
    get_sandbox_selector,
)

__all__ = [
    # Sandbox selection
    "SandboxType",
    "SandboxSelector",
    "get_sandbox_selector",
    # Container management
    "ContainerManager",
    "ContainerConfig",
    "ContainerStatus",
    "get_container_manager",
    # Resource limits
    "ResourceLimits",
    "ResourceUsage",
    "get_default_limits",
    # Sandbox pool
    "SandboxPool",
    "get_sandbox_pool",
    # Code validation
    "CodeValidator",
    "ValidationResult",
    "get_code_validator",
    # Code execution
    "CodeExecutionSandbox",
    "ExecutionResult",
    "ExecutionStatus",
    "SecurityException",
    "ExecutionTimeoutException",
    "MemoryExceededException",
    "get_code_execution_sandbox",
]
