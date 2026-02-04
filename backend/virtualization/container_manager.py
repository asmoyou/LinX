"""Container Manager for agent virtualization.

This module manages Docker containers for agent execution with security isolation
and resource limits.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5: Code Execution Environment and Security Isolation
"""

import json
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

import docker
from docker.errors import DockerException, NotFound

from virtualization.resource_limits import ResourceLimits, ResourceUsage, get_default_limits
from virtualization.sandbox_selector import SandboxType, get_sandbox_selector

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
    image: str = "python:3.11-slim"  # Default to Python image with common tools

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
    tmpfs_mounts: Dict[str, str] = field(
        default_factory=lambda: {
            "/tmp": "size=50M,mode=1777",
            "/output": "size=10M,mode=1777",
        }
    )

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
        # Get resource limits config
        resource_config = self.resource_limits.to_docker_config()
        
        # Build security options
        security_opt = []
        if self.no_new_privileges:
            security_opt.append("no-new-privileges:true")
        
        # Add Linux-specific security options
        import platform
        if platform.system() == "Linux":
            if self.seccomp_profile:
                security_opt.append(f"seccomp={self.seccomp_profile}")
            if self.apparmor_profile:
                security_opt.append(f"apparmor={self.apparmor_profile}")
        
        config = {
            "image": self.image,
            "name": self.name or f"agent-{self.container_id[:8]}",
            "detach": True,
            "command": ["/bin/sleep", "infinity"],  # Keep container running
            "environment": self.environment,
            "read_only": self.read_only_root,
            "tmpfs": self.tmpfs_mounts,
            "security_opt": security_opt,
            "cap_drop": self.drop_capabilities,
            "cap_add": self.add_capabilities,
            # Add resource limits directly
            **resource_config,
        }
        
        # Handle network configuration
        # network_disabled and network_mode are mutually exclusive
        if self.network_disabled:
            config["network_disabled"] = True
        else:
            config["network_mode"] = self.network_mode

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

        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            # Test connection
            self.docker_client.ping()
            self.docker_available = True
            self.logger.info("Docker client initialized successfully")
        except DockerException as e:
            self.logger.warning(f"Docker not available: {e}. Running in simulation mode.")
            self.docker_client = None
            self.docker_available = False

        # Detect best sandbox
        self.default_sandbox = self.sandbox_selector.detect_best_sandbox()
        self.logger.info(
            "ContainerManager initialized",
            extra={
                "default_sandbox": self.default_sandbox.value,
                "docker_available": self.docker_available,
            },
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
            if self.docker_available:
                # Real Docker container creation
                docker_config = config.to_docker_config()
                
                # Create container
                container = self.docker_client.containers.create(
                    **docker_config
                )
                
                # Store container reference
                self.containers[container_id] = {
                    "id": container_id,
                    "docker_id": container.id,
                    "docker_container": container,
                    "agent_id": str(agent_id),
                    "status": ContainerStatus.CREATING.value,
                    "config": config,
                    "created_at": datetime.utcnow().isoformat(),
                    "started_at": None,
                    "stopped_at": None,
                }
                
                self.logger.info(
                    "Docker container created",
                    extra={
                        "container_id": container_id,
                        "docker_id": container.id,
                    },
                )
            else:
                # Simulation mode
                self.containers[container_id] = {
                    "id": container_id,
                    "docker_id": None,
                    "docker_container": None,
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

        except DockerException as e:
            self.logger.error(
                "Failed to create Docker container",
                extra={
                    "agent_id": str(agent_id),
                    "error": str(e),
                },
            )
            raise RuntimeError(f"Container creation failed: {e}")
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
            if self.docker_available:
                # Real Docker container start
                container = self.containers[container_id]["docker_container"]
                container.start()
                
                # Reload container to get updated status
                container.reload()
                
                # Check if container actually started
                if container.status != "running":
                    # Get container logs to see what went wrong
                    logs = container.logs().decode('utf-8', errors='replace')
                    self.logger.error(
                        f"Container failed to start. Status: {container.status}",
                        extra={
                            "container_id": container_id,
                            "docker_status": container.status,
                            "logs": logs[:500] if logs else "No logs",
                        },
                    )
                    self.containers[container_id]["status"] = ContainerStatus.FAILED.value
                    return False
                
            self.containers[container_id]["status"] = ContainerStatus.RUNNING.value
            self.containers[container_id]["started_at"] = datetime.utcnow().isoformat()

            self.logger.info(
                "Container started",
                extra={"container_id": container_id},
            )

            return True

        except DockerException as e:
            self.logger.error(
                "Failed to start Docker container",
                extra={
                    "container_id": container_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            self.containers[container_id]["status"] = ContainerStatus.FAILED.value
            return False
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
            if self.docker_available:
                container = self.containers[container_id]["docker_container"]
                container.stop(timeout=timeout)
            
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

        except DockerException as e:
            self.logger.error(
                "Failed to stop Docker container",
                extra={
                    "container_id": container_id,
                    "error": str(e),
                },
            )
            return False
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

            if self.docker_available:
                # Remove Docker container
                container = self.containers[container_id]["docker_container"]
                container.remove(force=True)

            self.containers[container_id]["status"] = ContainerStatus.TERMINATED.value

            self.logger.info(
                "Container terminated",
                extra={"container_id": container_id},
            )

            return True

        except DockerException as e:
            self.logger.error(
                "Failed to terminate Docker container",
                extra={
                    "container_id": container_id,
                    "error": str(e),
                },
            )
            return False
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

        if self.docker_available:
            try:
                container = self.containers[container_id]["docker_container"]
                stats = container.stats(stream=False)
                
                # Parse Docker stats
                cpu_percent = self._calculate_cpu_percent(stats)
                memory_mb = stats['memory_stats'].get('usage', 0) / (1024 * 1024)
                memory_limit = stats['memory_stats'].get('limit', 1)
                memory_percent = (stats['memory_stats'].get('usage', 0) / memory_limit) * 100
                
                return ResourceUsage(
                    cpu_percent=cpu_percent,
                    memory_mb=memory_mb,
                    memory_percent=memory_percent,
                    execution_time_seconds=0.0,  # Will be set by caller
                )
            except Exception as e:
                self.logger.warning(f"Failed to get container stats: {e}")
                return None
        
        # Simulation mode - return mock data
        return ResourceUsage(
            cpu_percent=25.5,
            memory_mb=256.0,
            memory_percent=50.0,
            execution_time_seconds=5.0,
        )
    
    def _calculate_cpu_percent(self, stats: Dict[str, Any]) -> float:
        """Calculate CPU percentage from Docker stats.
        
        Args:
            stats: Docker stats dictionary
            
        Returns:
            CPU percentage
        """
        try:
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * 100.0
                return round(cpu_percent, 2)
        except (KeyError, ZeroDivisionError):
            pass
        
        return 0.0
    
    def exec_in_container(
        self,
        container_id: str,
        command: str,
        workdir: Optional[str] = None,
        environment: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, str, str]:
        """Execute a command in a running container.
        
        Args:
            container_id: Container ID
            command: Command to execute (string or list)
            workdir: Working directory for command
            environment: Environment variables
            
        Returns:
            Tuple of (exit_code, stdout, stderr)
            
        Raises:
            RuntimeError: If container not found or not running
        """
        if container_id not in self.containers:
            raise RuntimeError(f"Container {container_id} not found")
        
        container_info = self.containers[container_id]
        
        if container_info["status"] != ContainerStatus.RUNNING.value:
            raise RuntimeError(
                f"Container {container_id} is not running (status: {container_info['status']})"
            )
        
        if not self.docker_available:
            # Simulation mode
            self.logger.warning("Docker not available, simulating command execution")
            return (0, "Simulated output", "")
        
        try:
            container = container_info["docker_container"]
            
            # Prepare exec command
            exec_config = {
                "cmd": command if isinstance(command, list) else ["/bin/sh", "-c", command],
                "stdout": True,
                "stderr": True,
            }
            
            if workdir:
                exec_config["workdir"] = workdir
            
            if environment:
                exec_config["environment"] = environment
            
            # Execute command
            exec_instance = container.exec_run(**exec_config)
            
            exit_code = exec_instance.exit_code
            output = exec_instance.output.decode('utf-8', errors='replace')
            
            # Docker exec_run combines stdout and stderr
            # We'll return output in stdout and empty stderr
            stdout = output
            stderr = ""
            
            self.logger.debug(
                "Command executed in container",
                extra={
                    "container_id": container_id,
                    "command": command if isinstance(command, str) else " ".join(command),
                    "exit_code": exit_code,
                },
            )
            
            return (exit_code, stdout, stderr)
        
        except DockerException as e:
            self.logger.error(
                f"Failed to execute command in container: {e}",
                extra={"container_id": container_id},
            )
            raise RuntimeError(f"Command execution failed: {e}")
    
    def write_file_to_container(
        self,
        container_id: str,
        file_path: str,
        content: str,
        mode: int = 0o644,
    ) -> bool:
        """Write a file to a container.
        
        Args:
            container_id: Container ID
            file_path: Path in container
            content: File content
            mode: File permissions (octal)
            
        Returns:
            True if successful
            
        Raises:
            RuntimeError: If operation fails
        """
        if container_id not in self.containers:
            raise RuntimeError(f"Container {container_id} not found")
        
        if not self.docker_available:
            self.logger.warning("Docker not available, simulating file write")
            return True
        
        try:
            # Use exec to write file (works with read-only root + tmpfs)
            # Escape content for shell
            import base64
            content_b64 = base64.b64encode(content.encode('utf-8')).decode('ascii')
            
            # Write using base64 to avoid shell escaping issues
            commands = [
                f"echo '{content_b64}' | base64 -d > {file_path}",
                f"chmod {oct(mode)[2:]} {file_path}"
            ]
            
            for cmd in commands:
                exit_code, stdout, stderr = self.exec_in_container(
                    container_id,
                    cmd
                )
                
                if exit_code != 0:
                    raise RuntimeError(
                        f"Command failed with exit code {exit_code}: {stderr}"
                    )
            
            self.logger.debug(
                f"File written to container",
                extra={
                    "container_id": container_id,
                    "file_path": file_path,
                    "size": len(content),
                },
            )
            
            return True
        
        except Exception as e:
            self.logger.error(
                f"Failed to write file to container: {e}",
                extra={"container_id": container_id, "file_path": file_path},
            )
            raise RuntimeError(f"File write failed: {e}")

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
            cid
            for cid, info in self.containers.items()
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
