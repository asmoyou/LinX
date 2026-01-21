"""Virtualization module for Digital Workforce Platform.

This module provides containerized agent execution with multi-layer security isolation:
- Automatic sandbox selection (gVisor, Firecracker, Docker Enhanced)
- Container provisioning and lifecycle management
- Resource limits enforcement (CPU, memory, network)
- Security policies and network isolation
- Sandbox pool management for performance

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5: Code Execution Environment and Security Isolation
"""

from virtualization.sandbox_selector import (
    SandboxType,
    SandboxSelector,
    get_sandbox_selector,
)

from virtualization.container_manager import (
    ContainerManager,
    ContainerConfig,
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

__all__ = [
    # Sandbox selection
    'SandboxType',
    'SandboxSelector',
    'get_sandbox_selector',
    
    # Container management
    'ContainerManager',
    'ContainerConfig',
    'ContainerStatus',
    'get_container_manager',
    
    # Resource limits
    'ResourceLimits',
    'ResourceUsage',
    'get_default_limits',
    
    # Sandbox pool
    'SandboxPool',
    'get_sandbox_pool',
]
