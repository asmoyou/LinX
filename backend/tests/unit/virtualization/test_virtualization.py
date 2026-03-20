"""Tests for Virtualization System.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5: Code Execution Environment and Security Isolation
"""

import platform
from unittest.mock import Mock
from uuid import uuid4

import pytest
from docker.errors import DockerException, NotFound

from virtualization.container_manager import (
    ContainerConfig,
    ContainerManager,
    ContainerStatus,
    DockerCleanupManager,
    get_container_manager,
)
from virtualization.resource_limits import (
    ResourceLimits,
    ResourceUsage,
    get_default_limits,
    parse_resource_usage_from_docker_stats,
)
from virtualization.sandbox_pool import SandboxPool
from virtualization.sandbox_selector import (
    SandboxSelector,
    SandboxType,
    get_sandbox_selector,
)


class TestSandboxSelector:
    """Test SandboxSelector functionality."""

    def test_sandbox_selector_initialization(self):
        """Test sandbox selector initializes correctly."""
        selector = SandboxSelector()
        assert selector is not None
        assert selector._platform == platform.system()

    def test_detect_best_sandbox(self):
        """Test sandbox detection returns valid type."""
        selector = SandboxSelector()
        sandbox_type = selector.detect_best_sandbox()

        assert isinstance(sandbox_type, SandboxType)
        assert sandbox_type in [
            SandboxType.GVISOR,
            SandboxType.FIRECRACKER,
            SandboxType.DOCKER_ENHANCED,
        ]

    def test_detect_best_sandbox_caching(self):
        """Test sandbox detection caches result."""
        selector = SandboxSelector()
        first_result = selector.detect_best_sandbox()
        second_result = selector.detect_best_sandbox()

        assert first_result == second_result

    def test_get_sandbox_config(self):
        """Test getting sandbox configuration."""
        selector = SandboxSelector()

        for sandbox_type in SandboxType:
            config = selector.get_sandbox_config(sandbox_type)

            assert "runtime" in config
            assert "security_level" in config
            assert "overhead" in config
            assert "startup_time_ms" in config
            assert "platform" in config
            assert "features" in config

    def test_get_platform_info(self):
        """Test getting platform information."""
        selector = SandboxSelector()
        info = selector.get_platform_info()

        assert "system" in info
        assert "release" in info
        assert "version" in info
        assert "machine" in info

    def test_validate_sandbox_requirements(self):
        """Test sandbox requirements validation."""
        selector = SandboxSelector()

        # Docker Enhanced should always be valid
        assert selector.validate_sandbox_requirements(SandboxType.DOCKER_ENHANCED)

        # gVisor and Firecracker depend on platform
        if platform.system() == "Linux":
            # May or may not be available
            result = selector.validate_sandbox_requirements(SandboxType.GVISOR)
            assert isinstance(result, bool)
        else:
            # Should not be available on non-Linux
            assert not selector.validate_sandbox_requirements(SandboxType.GVISOR)
            assert not selector.validate_sandbox_requirements(SandboxType.FIRECRACKER)

    def test_get_sandbox_selector_singleton(self):
        """Test global sandbox selector is singleton."""
        selector1 = get_sandbox_selector()
        selector2 = get_sandbox_selector()

        assert selector1 is selector2


class TestResourceLimits:
    """Test ResourceLimits functionality."""

    def test_resource_limits_defaults(self):
        """Test default resource limits."""
        limits = ResourceLimits()

        assert limits.cpu_cores == 0.5
        assert limits.memory_mb == 512
        assert limits.execution_timeout_seconds == 30

    def test_resource_limits_validation(self):
        """Test resource limits validation."""
        # Valid limits
        valid_limits = ResourceLimits(cpu_cores=1.0, memory_mb=1024)
        assert valid_limits.validate()

        # Invalid CPU
        invalid_cpu = ResourceLimits(cpu_cores=0)
        assert not invalid_cpu.validate()

        invalid_cpu_high = ResourceLimits(cpu_cores=10)
        assert not invalid_cpu_high.validate()

        # Invalid memory
        invalid_memory = ResourceLimits(memory_mb=50)
        assert not invalid_memory.validate()

        invalid_memory_high = ResourceLimits(memory_mb=300000)
        assert not invalid_memory_high.validate()

    def test_resource_limits_to_docker_config(self):
        """Test conversion to Docker configuration."""
        limits = ResourceLimits(cpu_cores=1.0, memory_mb=1024)
        config = limits.to_docker_config()

        assert "cpu_period" in config
        assert "cpu_quota" in config
        assert "mem_limit" in config
        assert config["mem_limit"] == "1024m"

    def test_resource_limits_to_kubernetes_config(self):
        """Test conversion to Kubernetes configuration."""
        limits = ResourceLimits(cpu_cores=2.0, memory_mb=2048)
        config = limits.to_kubernetes_config()

        assert "limits" in config
        assert "requests" in config
        assert config["limits"]["cpu"] == "2.0"
        assert config["limits"]["memory"] == "2048Mi"

    def test_get_default_limits(self, monkeypatch):
        """Test getting default limits by task type."""
        monkeypatch.setenv("LINX_SANDBOX_MEMORY_MB", "1536")

        default = get_default_limits("default")
        assert default.cpu_cores == 0.5
        assert default.memory_mb == 1536

        data_processing = get_default_limits("data_processing")
        assert data_processing.cpu_cores == 1.0
        assert data_processing.memory_mb == 1536

        lightweight = get_default_limits("lightweight")
        assert lightweight.cpu_cores == 0.25
        assert lightweight.memory_mb == 1536


class TestResourceUsage:
    """Test ResourceUsage functionality."""

    def test_resource_usage_defaults(self):
        """Test default resource usage."""
        usage = ResourceUsage()

        assert usage.cpu_percent == 0.0
        assert usage.memory_mb == 0.0
        assert usage.execution_time_seconds == 0.0

    def test_resource_usage_to_dict(self):
        """Test conversion to dictionary."""
        usage = ResourceUsage(
            cpu_percent=50.5,
            memory_mb=256.0,
            execution_time_seconds=10.5,
        )

        data = usage.to_dict()

        assert data["cpu"]["percent"] == 50.5
        assert data["memory"]["mb"] == 256.0
        assert data["execution_time_seconds"] == 10.5

    def test_resource_usage_is_within_limits(self):
        """Test checking if usage is within limits."""
        limits = ResourceLimits(memory_mb=512, execution_timeout_seconds=30)

        # Within limits
        usage_ok = ResourceUsage(memory_mb=256.0, execution_time_seconds=15.0)
        assert usage_ok.is_within_limits(limits)

        # Memory exceeded
        usage_memory = ResourceUsage(memory_mb=600.0, execution_time_seconds=15.0)
        assert not usage_memory.is_within_limits(limits)

        # Timeout exceeded
        usage_timeout = ResourceUsage(memory_mb=256.0, execution_time_seconds=35.0)
        assert not usage_timeout.is_within_limits(limits)

    def test_parse_resource_usage_from_docker_stats(self):
        """Test parsing Docker stats."""
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 1000000000},
                "system_cpu_usage": 10000000000,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 500000000},
                "system_cpu_usage": 9000000000,
            },
            "memory_stats": {
                "usage": 268435456,  # 256 MB
                "limit": 536870912,  # 512 MB
            },
            "blkio_stats": {
                "io_service_bytes_recursive": [
                    {"op": "Read", "value": 10485760},  # 10 MB
                    {"op": "Write", "value": 5242880},  # 5 MB
                ],
            },
            "networks": {
                "eth0": {
                    "rx_bytes": 1048576,  # 1 MB
                    "tx_bytes": 524288,  # 0.5 MB
                },
            },
        }

        usage = parse_resource_usage_from_docker_stats(stats)

        assert usage.cpu_percent > 0
        assert usage.memory_mb == 256.0
        assert usage.memory_percent == 50.0
        assert usage.disk_read_mb == 10.0
        assert usage.disk_write_mb == 5.0
        assert usage.network_rx_mb == 1.0
        assert usage.network_tx_mb == 0.5


class TestContainerManager:
    """Test ContainerManager functionality."""

    def test_container_manager_initialization(self):
        """Test container manager initializes correctly."""
        manager = ContainerManager()

        assert manager is not None
        assert manager.default_sandbox in SandboxType
        assert len(manager.containers) == 0

    def test_create_container(self):
        """Test creating a container."""
        manager = ContainerManager()
        agent_id = uuid4()

        container_id = manager.create_container(agent_id)

        assert container_id is not None
        assert container_id in manager.containers
        assert manager.containers[container_id]["agent_id"] == str(agent_id)
        assert manager.containers[container_id]["status"] == ContainerStatus.CREATING.value

    def test_start_container(self):
        """Test starting a container."""
        manager = ContainerManager()
        agent_id = uuid4()

        container_id = manager.create_container(agent_id)
        success = manager.start_container(container_id)

        assert success
        assert manager.containers[container_id]["status"] == ContainerStatus.RUNNING.value
        assert manager.containers[container_id]["started_at"] is not None

    def test_start_container_recovers_missing_network(self):
        """Test starting container retries after creating missing custom network."""
        manager = ContainerManager()
        manager.docker_available = True
        manager.docker_client = Mock()
        manager.docker_client.networks.get.side_effect = NotFound("network not found")

        container = Mock()

        def _reload_status():
            container.status = "running"

        container.reload.side_effect = _reload_status
        container.start.side_effect = [
            DockerException("failed to set up container networking: network isolated-network not found"),
            None,
        ]
        container.status = "created"

        container_id = "sandbox-123"
        manager.containers[container_id] = {
            "id": container_id,
            "docker_id": "docker-123",
            "docker_container": container,
            "agent_id": str(uuid4()),
            "status": ContainerStatus.CREATING.value,
            "config": ContainerConfig(network_mode="isolated-network", network_disabled=False),
            "created_at": None,
            "started_at": None,
            "stopped_at": None,
        }

        success = manager.start_container(container_id)

        assert success is True
        assert container.start.call_count == 2
        manager.docker_client.networks.create.assert_called_once()
        assert manager.containers[container_id]["status"] == ContainerStatus.RUNNING.value

    def test_stop_container(self):
        """Test stopping a container."""
        manager = ContainerManager()
        agent_id = uuid4()

        container_id = manager.create_container(agent_id)
        manager.start_container(container_id)
        success = manager.stop_container(container_id)

        assert success
        assert manager.containers[container_id]["status"] == ContainerStatus.STOPPED.value
        assert manager.containers[container_id]["stopped_at"] is not None

    def test_terminate_container(self):
        """Test terminating a container."""
        manager = ContainerManager()
        agent_id = uuid4()

        container_id = manager.create_container(agent_id)
        manager.start_container(container_id)
        success = manager.terminate_container(container_id)

        assert success
        assert manager.containers[container_id]["status"] == ContainerStatus.TERMINATED.value

    def test_get_container_status(self):
        """Test getting container status."""
        manager = ContainerManager()
        agent_id = uuid4()

        container_id = manager.create_container(agent_id)
        status = manager.get_container_status(container_id)

        assert status == ContainerStatus.CREATING

        # Non-existent container
        status_none = manager.get_container_status("nonexistent")
        assert status_none is None

    def test_get_container_status_marks_terminated_when_missing_in_docker(self):
        """Missing Docker container should be marked as terminated."""
        manager = ContainerManager()
        manager.docker_available = True

        docker_container = Mock()
        docker_container.reload.side_effect = NotFound("No such container")
        docker_container.status = "running"

        container_id = "sandbox-missing-1"
        manager.containers[container_id] = {
            "id": container_id,
            "docker_id": "docker-missing-1",
            "docker_container": docker_container,
            "agent_id": str(uuid4()),
            "status": ContainerStatus.RUNNING.value,
            "config": ContainerConfig(),
            "created_at": None,
            "started_at": None,
            "stopped_at": None,
        }

        status = manager.get_container_status(container_id)

        assert status == ContainerStatus.TERMINATED
        assert manager.containers[container_id]["status"] == ContainerStatus.TERMINATED.value

    def test_exec_in_container_marks_terminated_when_missing_in_docker(self):
        """Exec should fail fast and mark status when Docker reports missing container."""
        manager = ContainerManager()
        manager.docker_available = True

        docker_container = Mock()
        docker_container.status = "running"
        docker_container.exec_run.side_effect = NotFound("No such container")

        container_id = "sandbox-missing-2"
        manager.containers[container_id] = {
            "id": container_id,
            "docker_id": "docker-missing-2",
            "docker_container": docker_container,
            "agent_id": str(uuid4()),
            "status": ContainerStatus.RUNNING.value,
            "config": ContainerConfig(),
            "created_at": None,
            "started_at": None,
            "stopped_at": None,
        }

        with pytest.raises(RuntimeError, match="no longer exists"):
            manager.exec_in_container(container_id, "echo hello")

        assert manager.containers[container_id]["status"] == ContainerStatus.TERMINATED.value

    def test_get_container_stats(self):
        """Test getting container statistics."""
        manager = ContainerManager()
        agent_id = uuid4()

        container_id = manager.create_container(agent_id)
        manager.start_container(container_id)

        stats = manager.get_container_stats(container_id)

        assert stats is not None
        assert isinstance(stats, ResourceUsage)

    def test_list_containers(self):
        """Test listing containers."""
        manager = ContainerManager()
        agent_id1 = uuid4()
        agent_id2 = uuid4()

        container_id1 = manager.create_container(agent_id1)
        container_id2 = manager.create_container(agent_id2)
        manager.start_container(container_id1)

        # List all
        all_containers = manager.list_containers()
        assert len(all_containers) == 2

        # Filter by agent
        agent_containers = manager.list_containers(agent_id=agent_id1)
        assert len(agent_containers) == 1
        assert agent_containers[0]["agent_id"] == str(agent_id1)

        # Filter by status
        running_containers = manager.list_containers(status=ContainerStatus.RUNNING)
        assert len(running_containers) == 1

    def test_cleanup_terminated_containers(self):
        """Test cleaning up terminated containers."""
        manager = ContainerManager()
        agent_id = uuid4()

        container_id = manager.create_container(agent_id)
        manager.start_container(container_id)
        manager.terminate_container(container_id)

        assert container_id in manager.containers

        count = manager.cleanup_terminated_containers()

        assert count == 1
        assert container_id not in manager.containers

    def test_get_container_manager_singleton(self):
        """Test global container manager is singleton."""
        manager1 = get_container_manager()
        manager2 = get_container_manager()

        assert manager1 is manager2


class TestContainerConfig:
    """Test ContainerConfig functionality."""

    def test_container_config_defaults(self):
        """Test default container configuration."""
        config = ContainerConfig()

        assert config.sandbox_type == SandboxType.DOCKER_ENHANCED
        assert config.read_only_root is True
        assert config.no_new_privileges is True
        assert "ALL" in config.drop_capabilities

    def test_container_config_to_docker_config(self):
        """Test conversion to Docker configuration."""
        config = ContainerConfig(
            agent_id=uuid4(),
            name="test-container",
            image="test-image:latest",
            labels={"com.linx.runtime_scope": "persistent_conversation"},
        )

        docker_config = config.to_docker_config()

        assert docker_config["name"] == "test-container"
        assert docker_config["image"] == "test-image:latest"
        assert docker_config["read_only"] is True
        assert "security_opt" in docker_config
        assert "no-new-privileges:true" in docker_config["security_opt"]
        assert docker_config["labels"]["com.linx.managed"] == "true"
        assert docker_config["labels"]["com.linx.type"] == "sandbox"
        assert docker_config["labels"]["com.linx.container_id"] == config.container_id
        assert docker_config["labels"]["com.linx.agent_id"] == str(config.agent_id)
        assert docker_config["labels"]["com.linx.runtime_scope"] == "persistent_conversation"


class TestDockerCleanupManager:
    """Test DockerCleanupManager functionality."""

    def test_cleanup_container_by_internal_id(self):
        """Test force-removing container by LinX internal ID label."""
        manager = DockerCleanupManager()
        manager.docker_available = True

        mock_container = Mock()
        mock_container.id = "abc123456789"
        mock_client = Mock()
        mock_client.containers.list.return_value = [mock_container]
        manager.docker_client = mock_client

        removed = manager.cleanup_container_by_internal_id("sandbox-123")

        assert removed is True
        mock_client.containers.list.assert_called_once_with(
            all=True,
            filters={
                "label": [
                    "com.linx.managed=true",
                    "com.linx.container_id=sandbox-123",
                ]
            },
        )
        mock_container.remove.assert_called_once_with(force=True)

    def test_cleanup_container_by_internal_id_not_found(self):
        """Test cleanup returns False when no matching container exists."""
        manager = DockerCleanupManager()
        manager.docker_available = True

        mock_client = Mock()
        mock_client.containers.list.return_value = []
        manager.docker_client = mock_client

        removed = manager.cleanup_container_by_internal_id("sandbox-missing")

        assert removed is False


class TestSandboxPool:
    """Test SandboxPool functionality."""

    @pytest.mark.asyncio
    async def test_sandbox_pool_initialization(self):
        """Test sandbox pool initializes correctly."""
        pool = SandboxPool(pool_size=3)

        assert pool.pool_size == 3
        assert not pool._initialized

    @pytest.mark.asyncio
    async def test_sandbox_pool_initialize(self):
        """Test initializing sandbox pool."""
        pool = SandboxPool(pool_size=2)
        await pool.initialize_pool()

        assert pool._initialized
        stats = pool.get_pool_stats()
        assert stats["pool_size"] == 2

    @pytest.mark.asyncio
    async def test_acquire_and_release_sandbox(self):
        """Test acquiring and releasing sandbox."""
        pool = SandboxPool(pool_size=2)
        await pool.initialize_pool()

        agent_id = uuid4()

        # Acquire sandbox
        container_id = await pool.acquire_sandbox(agent_id, timeout=1.0)
        assert container_id is not None
        assert container_id in pool.active_sandboxes

        # Release sandbox
        success = await pool.release_sandbox(container_id)
        assert success
        assert container_id not in pool.active_sandboxes

    @pytest.mark.asyncio
    async def test_get_pool_stats(self):
        """Test getting pool statistics."""
        pool = SandboxPool(pool_size=2)
        await pool.initialize_pool()

        stats = pool.get_pool_stats()

        assert "pool_size" in stats
        assert "available" in stats
        assert "active" in stats
        assert "warming" in stats
        assert "total" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
