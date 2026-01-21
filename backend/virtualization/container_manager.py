"""Container Manager for agent virtualization.

This module manages Docker containers for agent execution with security isolation
and resource limits.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5: Code Execution Environment and Security Isolation
"""

import logging
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4

from virtualization.sandbox_selector import SandboxType, get_sandbox_selector
from virtualization.resource_limits import ResourceLimits, ResourceUsage, get_default_limits

logger = logging.getLogger(__name__)


class ContainerStatus(Enum):
    """Container status states."""
    
    CREATING = "creating"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class ContainerConfig:
    """Configuration for agent container."""
    
    # Container identification
    container_id: str = field(default_factory=lambda: str(uuid4()))
    agent_id: Optional[UUID] = None
    name: str = ""
    
    # Sandbox configuration
    sandbox_type: SandboxType = SandboxType.DOCKER_ENHANCED
    image: str = "agent-runtime:latest"
    
    # Resource limits
    resource_limits: ResourceLimits = field(default_factory=lambda: get_default_limits())
    
    # Security configuration
    read_only_root: bool = True
    no_new_privileges: bool = True
    drop_capabilities: List[str] = field(default_factory=lambda: ["ALL"])
    add_capabilities: List[str] = field(default_factory=lambda: ["CHOWN", "SETUID", "SETGID"])
    
    # Network configuration
    network_mode: str = "isolated-network"
    network_disabled: bool = False
    
    # Filesystem configuration
    tmpfs_mounts: Dict[str, str] = field(default_factory=lambda: {
        "/tmp": "size=50M,mode=1777",
        "/output": "size=10M,mode=1777",
    })
    
    # Environment variables
    environment: Dict[str, str] = field(default_factory=dict)
    
    # Platform-specific settings
    seccomp_profile: Optional[str] = None  # Linux only
    apparmor_profile: str = "docker-default"  # Linux only
    
    def to_docker_config(self) -> Dict[str, Any]:
        """Convert to Docker container creation configuration.
        
        Returns:
            Dictionary with Docker API configuration
        """
        config = {
            "name": self.name or f"agent-{self.container_id[:8]}",
            "image": self.image,
            "detach": True,
            "environment": self.environment,
            "network_mode": self.network_mode,
            "network_disabled": self.network_disabled,
            "read_only": self.read_only_root,
            "tmpfs": self.tmpfs_mounts,
            "host_config": {
                **self.resource_limits.to_docker_config(),
                "security_opt": [
                    "no-new-privileges:true" if self.no_new_privileges else "",
                ],
                "cap_drop": self.drop_capabilities,
                "cap_add": self.add_capabilities,
            },
        }
        
        # Add Linux-specific security options
        import platform
        if platform.system() == "Linux":
            if self.seccomp_profile:
                config["host_config"]["security_opt"].append(
                    f"seccomp={self.seccomp_profile}"
                )
            if self.apparmor_profile:
                config["host_config"]["security_opt"].append(
                    f"apparmor={self.apparmor_profile}"
                )
        
        # Add runtime for gVisor
        if self.sandbox_type == SandboxType.GVISOR:
            config["runtime"] = "runsc"
        
        return config


class ContainerManager:
    """Manager for agent container lifecycle."""
    
    def __init__(self):
        """Initialize the container manager."""
        self.logger = logging.getLogger(__name__)
        self.sandbox_selector = get_sandbox_selector()
        self.containers: Dict[str, Dict[str, Any]] = {}
        
        # Detect best sandbox
        self.default_sandbox = self.sandbox_selector.detect_best_sandbox()
        self.logger.info(
            "ContainerManager initialized",
            extra={"default_sandbox": self.default_sandbox.value},
        )
    
    def create_container(
        self,
        agent_id: UUID,
        config: Optional[ContainerConfig] = None,
    ) -> str:
        """Create a new container for an agent.
        
        Args:
            agent_id: Agent UUID
            config: Container configuration (uses defaults if None)
        
        Returns:
            Container ID
        
        Raises:
            RuntimeError: If container creation fails
        """
        if config is None:
            config = ContainerConfig(
                agent_id=agent_id,
                sandbox_type=self.default_sandbox,
            )
        
        container_id = config.container_id
        
        self.logger.info(
            "Creating container for agent",
            extra={
                "agent_id": str(agent_id),
                "container_id": container_id,
                "sandbox_type": config.sandbox_type.value,
            },
        )
        
        try:
            # In a real implementation, this would call Docker API
            # For now, we simulate container creation
            self.containers[container_id] = {
                "id": container_id,
                "agent_id": str(agent_id),
                "status": ContainerStatus.CREATING.value,
                "config": config,
                "created_at": datetime.utcnow().isoformat(),
                "started_at": None,
                "stopped_at": None,
            }
            
            self.logger.info(
                "Container created successfully",
                extra={
                    "container_id": container_id,
                    "agent_id": str(agent_id),
                },
            )
            
            return container_id
            
        except Exception as e:
            self.logger.error(
                "Failed to create container",
                extra={
                    "agent_id": str(agent_id),
                    "error": str(e),
                },
            )
            raise RuntimeError(f"Container creation failed: {e}")
    
    def start_container(self, container_id: str) -> bool:
        """Start a container.
        
        Args:
            container_id: Container ID
        
        Returns:
            True if started successfully, False otherwise
        """
        if container_id not in self.containers:
            self.logger.error(
                "Container not found",
                extra={"container_id": container_id},
            )
            return False
        
        try:
            # In a real implementation, this would call Docker API
            self.containers[container_id]["status"] = ContainerStatus.RUNNING.value
            self.containers[container_id]["started_at"] = datetime.utcnow().isoformat()
            
            self.logger.info(
                "Container started",
                extra={"container_id": container_id},
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to start container",
                extra={
                    "container_id": container_id,
                    "error": str(e),
                },
            )
            self.containers[container_id]["status"] = ContainerStatus.FAILED.value
            return False
    
    def stop_container(self, container_id: str, timeout: int = 10) -> bool:
        """Stop a running container.
        
        Args:
            container_id: Container ID
            timeout: Timeout in seconds before force kill
        
        Returns:
            True if stopped successfully, False otherwise
        """
        if container_id not in self.containers:
            self.logger.error(
                "Container not found",
                extra={"container_id": container_id},
            )
            return False
        
        try:
            # In a real implementation, this would call Docker API
            self.containers[container_id]["status"] = ContainerStatus.STOPPED.value
            self.containers[container_id]["stopped_at"] = datetime.utcnow().isoformat()
            
            self.logger.info(
                "Container stopped",
                extra={
                    "container_id": container_id,
                    "timeout": timeout,
                },
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to stop container",
                extra={
                    "container_id": container_id,
                    "error": str(e),
                },
            )
            return False
    
    def terminate_container(self, container_id: str) -> bool:
        """Terminate and remove a container.
        
        Args:
            container_id: Container ID
        
        Returns:
            True if terminated successfully, False otherwise
        """
        if container_id not in self.containers:
            self.logger.error(
                "Container not found",
                extra={"container_id": container_id},
            )
            return False
        
        try:
            # Stop container first if running
            status = self.containers[container_id]["status"]
            if status == ContainerStatus.RUNNING.value:
                self.stop_container(container_id)
            
            # In a real implementation, this would call Docker API to remove container
            self.containers[container_id]["status"] = ContainerStatus.TERMINATED.value
            
            self.logger.info(
                "Container terminated",
                extra={"container_id": container_id},
            )
            
            return True
            
        except Exception as e:
            self.logger.error(
                "Failed to terminate container",
                extra={
                    "container_id": container_id,
                    "error": str(e),
                },
            )
            return False
    
    def get_container_status(self, container_id: str) -> Optional[ContainerStatus]:
        """Get current status of a container.
        
        Args:
            container_id: Container ID
        
        Returns:
            ContainerStatus enum or None if not found
        """
        if container_id not in self.containers:
            return None
        
        status_str = self.containers[container_id]["status"]
        return ContainerStatus(status_str)
    
    def get_container_stats(self, container_id: str) -> Optional[ResourceUsage]:
        """Get resource usage statistics for a container.
        
        Args:
            container_id: Container ID
        
        Returns:
            ResourceUsage instance or None if not found
        """
        if container_id not in self.containers:
            return None
        
        # In a real implementation, this would call Docker stats API
        # For now, return mock data
        return ResourceUsage(
            cpu_percent=25.5,
            memory_mb=256.0,
            memory_percent=50.0,
            execution_time_seconds=5.0,
        )
    
    def list_containers(
        self,
        agent_id: Optional[UUID] = None,
        status: Optional[ContainerStatus] = None,
    ) -> List[Dict[str, Any]]:
        """List containers with optional filtering.
        
        Args:
            agent_id: Filter by agent ID (optional)
            status: Filter by status (optional)
        
        Returns:
            List of container information dictionaries
        """
        containers = list(self.containers.values())
        
        if agent_id is not None:
            containers = [c for c in containers if c["agent_id"] == str(agent_id)]
        
        if status is not None:
            containers = [c for c in containers if c["status"] == status.value]
        
        return containers
    
    def cleanup_terminated_containers(self) -> int:
        """Remove terminated containers from tracking.
        
        Returns:
            Number of containers cleaned up
        """
        terminated = [
            cid for cid, info in self.containers.items()
            if info["status"] == ContainerStatus.TERMINATED.value
        ]
        
        for container_id in terminated:
            del self.containers[container_id]
        
        if terminated:
            self.logger.info(
                "Cleaned up terminated containers",
                extra={"count": len(terminated)},
            )
        
        return len(terminated)


# Global container manager instance
_container_manager: Optional[ContainerManager] = None


def get_container_manager() -> ContainerManager:
    """Get the global container manager instance.
    
    Returns:
        ContainerManager instance
    """
    global _container_manager
    if _container_manager is None:
        _container_manager = ContainerManager()
    return _container_manager
