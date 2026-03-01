"""Container Manager for agent virtualization.

This module manages Docker containers for agent execution with security isolation
and resource limits.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5: Code Execution Environment and Security Isolation
"""

import json
import logging
import os
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
DEFAULT_SANDBOX_PYTHON_IMAGE = (
    os.getenv("LINX_SANDBOX_PYTHON_IMAGE", "python:3.11-bookworm").strip()
    or "python:3.11-bookworm"
)


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
    image: str = DEFAULT_SANDBOX_PYTHON_IMAGE

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

    # Volume mounts: host_path -> container_path (persistent storage)
    volume_mounts: Dict[str, str] = field(default_factory=dict)

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

        labels = {
            "com.linx.managed": "true",
            "com.linx.type": "sandbox",
            "com.linx.container_id": self.container_id,
        }
        if self.agent_id is not None:
            labels["com.linx.agent_id"] = str(self.agent_id)

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
            "labels": labels,
            # Add resource limits directly
            **resource_config,
        }

        # Add volume mounts (persistent storage for pip cache, etc.)
        if self.volume_mounts:
            config["volumes"] = {
                host_path: {"bind": container_path, "mode": "rw"}
                for host_path, container_path in self.volume_mounts.items()
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

                # Auto-pull image if not available locally
                image_name = docker_config.get("image", DEFAULT_SANDBOX_PYTHON_IMAGE)
                try:
                    self.docker_client.images.get(image_name)
                except Exception:
                    self.logger.info(
                        f"Image {image_name} not found locally, pulling...",
                        extra={"image": image_name, "agent_id": str(agent_id)},
                    )
                    try:
                        self.docker_client.images.pull(image_name)
                        self.logger.info(
                            f"Successfully pulled image {image_name}",
                            extra={"image": image_name},
                        )
                    except Exception as pull_error:
                        self.logger.error(
                            f"Failed to pull image {image_name}: {pull_error}",
                            extra={"image": image_name, "error": str(pull_error)},
                        )
                        raise RuntimeError(f"Failed to pull image {image_name}: {pull_error}")

                # Create container
                container = self.docker_client.containers.create(**docker_config)

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
                    logs = container.logs().decode("utf-8", errors="replace")
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
            if self._retry_start_after_network_recovery(container_id, e):
                return True
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

    def _ensure_network_exists(self, network_name: str) -> bool:
        """Ensure a Docker network exists before container startup."""
        if not self.docker_available or not self.docker_client:
            return False

        try:
            self.docker_client.networks.get(network_name)
            return True
        except NotFound:
            try:
                self.logger.warning(
                    "Docker network not found, creating it",
                    extra={"network_name": network_name},
                )
                self.docker_client.networks.create(
                    name=network_name,
                    driver="bridge",
                    check_duplicate=True,
                    labels={
                        "com.linx.managed": "true",
                        "com.linx.type": "sandbox-network",
                    },
                )
                self.logger.info(
                    "Docker network created successfully",
                    extra={"network_name": network_name},
                )
                return True
            except DockerException as create_error:
                self.logger.error(
                    "Failed to create Docker network",
                    extra={"network_name": network_name, "error": str(create_error)},
                )
                return False
        except DockerException as lookup_error:
            self.logger.error(
                "Failed to inspect Docker network",
                extra={"network_name": network_name, "error": str(lookup_error)},
            )
            return False

    def _retry_start_after_network_recovery(
        self, container_id: str, start_error: DockerException
    ) -> bool:
        """Retry container start once after creating missing Docker network."""
        container_meta = self.containers.get(container_id)
        if not container_meta:
            return False

        config = container_meta.get("config")
        network_mode = getattr(config, "network_mode", None)
        network_disabled = bool(getattr(config, "network_disabled", False))
        error_message = str(start_error).lower()

        if network_disabled or not network_mode:
            return False
        if network_mode in {"bridge", "host", "none"}:
            return False
        if "network" not in error_message or "not found" not in error_message:
            return False

        if not self._ensure_network_exists(network_mode):
            return False

        container = container_meta.get("docker_container")
        if container is None:
            return False

        try:
            self.logger.warning(
                "Retrying container start after recovering missing network",
                extra={
                    "container_id": container_id,
                    "network_mode": network_mode,
                },
            )
            container.start()
            container.reload()

            if container.status != "running":
                self.logger.error(
                    "Container still failed after network recovery",
                    extra={
                        "container_id": container_id,
                        "docker_status": container.status,
                        "network_mode": network_mode,
                    },
                )
                self.containers[container_id]["status"] = ContainerStatus.FAILED.value
                return False

            self.containers[container_id]["status"] = ContainerStatus.RUNNING.value
            self.containers[container_id]["started_at"] = datetime.utcnow().isoformat()
            self.logger.info(
                "Container started after network recovery",
                extra={
                    "container_id": container_id,
                    "network_mode": network_mode,
                },
            )
            return True
        except DockerException as retry_error:
            self.logger.error(
                "Retry start failed after network recovery",
                extra={
                    "container_id": container_id,
                    "network_mode": network_mode,
                    "error": str(retry_error),
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
                # Use short timeout for sandbox - no need for graceful shutdown
                self.stop_container(container_id, timeout=1)

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
                memory_mb = stats["memory_stats"].get("usage", 0) / (1024 * 1024)
                memory_limit = stats["memory_stats"].get("limit", 1)
                memory_percent = (stats["memory_stats"].get("usage", 0) / memory_limit) * 100

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
            cpu_delta = (
                stats["cpu_stats"]["cpu_usage"]["total_usage"]
                - stats["precpu_stats"]["cpu_usage"]["total_usage"]
            )
            system_delta = (
                stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
            )

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
                "demux": True,  # Separate stdout and stderr
            }

            if workdir:
                exec_config["workdir"] = workdir

            if environment:
                exec_config["environment"] = environment

            # Execute command
            exec_instance = container.exec_run(**exec_config)

            exit_code = exec_instance.exit_code

            # With demux=True, output is a tuple (stdout_bytes, stderr_bytes)
            raw_output = exec_instance.output
            if isinstance(raw_output, tuple):
                stdout = (raw_output[0] or b"").decode("utf-8", errors="replace")
                stderr = (raw_output[1] or b"").decode("utf-8", errors="replace")
            else:
                # Fallback if demux didn't work
                stdout = raw_output.decode("utf-8", errors="replace") if raw_output else ""
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

            content_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")

            # Write using base64 to avoid shell escaping issues
            commands = [
                f"echo '{content_b64}' | base64 -d > {file_path}",
                f"chmod {oct(mode)[2:]} {file_path}",
            ]

            for cmd in commands:
                exit_code, stdout, stderr = self.exec_in_container(container_id, cmd)

                if exit_code != 0:
                    raise RuntimeError(f"Command failed with exit code {exit_code}: {stderr}")

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


class DockerCleanupManager:
    """Manages cleanup of Docker resources created by LinX sandbox system.

    Handles cleanup of:
    - Orphaned containers (exited LinX sandbox containers)
    - Sandbox-derived images (tagged with com.linx labels)
    - Dangling images (<none>:<none>)
    - Docker build cache

    Protects infrastructure and base images from accidental deletion.
    """

    # Image prefixes that must never be deleted
    PROTECTED_IMAGE_PREFIXES = [
        "postgres:",
        "redis:",
        "minio/",
        "milvusdb/",
        "quay.io/coreos/etcd:",
        "python:",
    ]

    LINX_LABEL_FILTER = {"label": "com.linx.managed=true"}

    def __init__(self):
        """Initialize DockerCleanupManager."""
        self.logger = logging.getLogger(__name__)
        try:
            self.docker_client = docker.from_env()
            self.docker_client.ping()
            self.docker_available = True
        except DockerException:
            self.docker_client = None
            self.docker_available = False
            self.logger.warning("DockerCleanupManager: Docker not available")

    def _is_protected_image(self, image_tags: List[str]) -> bool:
        """Check if an image matches any protected prefix.

        Args:
            image_tags: List of image tags (e.g. ["python:3.11-slim"])

        Returns:
            True if the image should be protected from deletion
        """
        for tag in image_tags:
            for prefix in self.PROTECTED_IMAGE_PREFIXES:
                if tag.startswith(prefix):
                    return True
        return False

    def cleanup_orphaned_containers(self) -> int:
        """Remove exited containers created by LinX sandbox.

        Only removes containers with the com.linx.managed=true label
        that are in 'exited' or 'dead' status.

        Returns:
            Number of containers removed
        """
        if not self.docker_available:
            return 0

        removed = 0
        try:
            # Find exited containers with LinX label
            containers = self.docker_client.containers.list(
                all=True,
                filters={
                    **self.LINX_LABEL_FILTER,
                    "status": ["exited", "dead"],
                },
            )

            for container in containers:
                try:
                    container_name = container.name
                    container.remove(force=True)
                    removed += 1
                    self.logger.debug(
                        f"Removed orphaned container: {container_name}",
                    )
                except DockerException as e:
                    self.logger.warning(f"Failed to remove container {container.id[:12]}: {e}")

        except DockerException as e:
            self.logger.error(f"Error listing orphaned containers: {e}")

        return removed

    def cleanup_container_by_internal_id(self, container_id: str) -> bool:
        """Force-remove a LinX container by internal container ID label.

        Args:
            container_id: LinX internal container ID (not Docker short ID)

        Returns:
            True if at least one matching container is removed, False otherwise
        """
        if not self.docker_available:
            return False

        try:
            containers = self.docker_client.containers.list(
                all=True,
                filters={
                    "label": [
                        "com.linx.managed=true",
                        f"com.linx.container_id={container_id}",
                    ]
                },
            )

            removed = False
            for container in containers:
                try:
                    container.remove(force=True)
                    removed = True
                except DockerException as e:
                    self.logger.warning(
                        f"Failed to force-remove container {container.id[:12]}: {e}"
                    )

            return removed
        except DockerException as e:
            self.logger.error(f"Error finding container by internal ID {container_id}: {e}")
            return False

    def cleanup_sandbox_images(self) -> int:
        """Remove sandbox-derived images tagged with LinX labels.

        Only removes images with com.linx.managed=true label,
        and never removes protected base/infrastructure images.

        Returns:
            Number of images removed
        """
        if not self.docker_available:
            return 0

        removed = 0
        try:
            images = self.docker_client.images.list(filters=self.LINX_LABEL_FILTER)

            for image in images:
                tags = image.tags or []

                if self._is_protected_image(tags):
                    self.logger.debug(f"Skipping protected image: {tags}")
                    continue

                try:
                    image_id = image.short_id
                    self.docker_client.images.remove(image.id, force=True)
                    removed += 1
                    self.logger.debug(f"Removed sandbox image: {image_id} ({tags})")
                except DockerException as e:
                    self.logger.warning(f"Failed to remove image {image.short_id}: {e}")

        except DockerException as e:
            self.logger.error(f"Error listing sandbox images: {e}")

        return removed

    def cleanup_dangling_images(self) -> int:
        """Remove dangling images (<none>:<none>).

        Dangling images are safe to remove — they are not referenced
        by any container or tagged image. Protected images are still
        checked as a safety measure.

        Returns:
            Number of dangling images removed
        """
        if not self.docker_available:
            return 0

        removed = 0
        try:
            images = self.docker_client.images.list(filters={"dangling": True})

            for image in images:
                tags = image.tags or []

                if self._is_protected_image(tags):
                    continue

                try:
                    image_id = image.short_id
                    self.docker_client.images.remove(image.id, force=True)
                    removed += 1
                    self.logger.debug(f"Removed dangling image: {image_id}")
                except DockerException as e:
                    self.logger.warning(f"Failed to remove dangling image {image.short_id}: {e}")

        except DockerException as e:
            self.logger.error(f"Error listing dangling images: {e}")

        return removed

    def cleanup_build_cache(self) -> int:
        """Prune Docker build cache.

        Returns:
            Amount of space reclaimed in bytes, or -1 on error
        """
        if not self.docker_available:
            return 0

        try:
            result = self.docker_client.api.prune_builds()
            space_reclaimed = result.get("SpaceReclaimed", 0)
            self.logger.debug(
                f"Build cache pruned, reclaimed {space_reclaimed / (1024 * 1024):.1f} MB"
            )
            return space_reclaimed
        except DockerException as e:
            self.logger.error(f"Error pruning build cache: {e}")
            return -1

    def run_full_cleanup(self) -> Dict[str, Any]:
        """Execute full Docker cleanup and return statistics.

        Returns:
            Dictionary with cleanup statistics
        """
        stats: Dict[str, Any] = {
            "containers_removed": 0,
            "sandbox_images_removed": 0,
            "dangling_images_removed": 0,
            "build_cache_bytes_reclaimed": 0,
        }

        if not self.docker_available:
            self.logger.info("Docker cleanup skipped: Docker not available")
            return stats

        stats["containers_removed"] = self.cleanup_orphaned_containers()
        stats["sandbox_images_removed"] = self.cleanup_sandbox_images()
        stats["dangling_images_removed"] = self.cleanup_dangling_images()
        stats["build_cache_bytes_reclaimed"] = self.cleanup_build_cache()

        total_cleaned = (
            stats["containers_removed"]
            + stats["sandbox_images_removed"]
            + stats["dangling_images_removed"]
        )

        if total_cleaned > 0 or stats["build_cache_bytes_reclaimed"] > 0:
            self.logger.info(
                "Docker cleanup completed",
                extra=stats,
            )
        else:
            self.logger.debug("Docker cleanup completed: nothing to clean")

        return stats


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


# Global Docker cleanup manager instance
_docker_cleanup_manager: Optional[DockerCleanupManager] = None


def get_docker_cleanup_manager() -> DockerCleanupManager:
    """Get the global DockerCleanupManager instance.

    Returns:
        DockerCleanupManager instance
    """
    global _docker_cleanup_manager
    if _docker_cleanup_manager is None:
        _docker_cleanup_manager = DockerCleanupManager()
    return _docker_cleanup_manager
