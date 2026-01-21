"""Resource limits and usage tracking for agent containers.

This module defines resource limits and tracks resource usage for containerized agents.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.5: Runtime Security Policies
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ResourceLimits:
    """Resource limits for agent containers."""
    
    # CPU limits
    cpu_cores: float = 0.5  # Number of CPU cores
    cpu_shares: int = 512  # CPU shares (relative weight)
    
    # Memory limits
    memory_mb: int = 512  # Memory limit in MB
    memory_swap_mb: int = 512  # Memory + swap limit in MB
    
    # Execution time limits
    execution_timeout_seconds: int = 30  # Maximum execution time
    max_execution_time_seconds: int = 300  # Absolute maximum (5 minutes)
    
    # Disk I/O limits
    disk_read_bps: int = 10 * 1024 * 1024  # 10 MB/s
    disk_write_bps: int = 5 * 1024 * 1024  # 5 MB/s
    
    # Network limits
    network_bandwidth_bps: int = 1 * 1024 * 1024  # 1 MB/s
    max_connections: int = 5  # Maximum concurrent connections
    
    # Storage limits
    tmp_storage_mb: int = 50  # /tmp storage limit
    output_storage_mb: int = 10  # /output storage limit
    
    def to_docker_config(self) -> Dict[str, Any]:
        """Convert to Docker container configuration.
        
        Returns:
            Dictionary with Docker resource configuration
        """
        return {
            "cpu_period": 100000,  # 100ms
            "cpu_quota": int(self.cpu_cores * 100000),
            "cpu_shares": self.cpu_shares,
            "mem_limit": f"{self.memory_mb}m",
            "memswap_limit": f"{self.memory_swap_mb}m",
            "blkio_weight": 500,
            "device_read_bps": [
                {"Path": "/dev/sda", "Rate": self.disk_read_bps}
            ],
            "device_write_bps": [
                {"Path": "/dev/sda", "Rate": self.disk_write_bps}
            ],
        }
    
    def to_kubernetes_config(self) -> Dict[str, Any]:
        """Convert to Kubernetes resource configuration.
        
        Returns:
            Dictionary with Kubernetes resource configuration
        """
        return {
            "limits": {
                "cpu": str(self.cpu_cores),
                "memory": f"{self.memory_mb}Mi",
            },
            "requests": {
                "cpu": str(self.cpu_cores / 2),  # Request half of limit
                "memory": f"{self.memory_mb // 2}Mi",
            },
        }
    
    def validate(self) -> bool:
        """Validate resource limits are within acceptable ranges.
        
        Returns:
            True if valid, False otherwise
        """
        if self.cpu_cores <= 0 or self.cpu_cores > 4:
            logger.error(f"Invalid CPU cores: {self.cpu_cores}")
            return False
        
        if self.memory_mb < 128 or self.memory_mb > 4096:
            logger.error(f"Invalid memory limit: {self.memory_mb}MB")
            return False
        
        if self.execution_timeout_seconds <= 0:
            logger.error(f"Invalid timeout: {self.execution_timeout_seconds}s")
            return False
        
        return True


@dataclass
class ResourceUsage:
    """Current resource usage for a container."""
    
    # CPU usage
    cpu_percent: float = 0.0  # CPU usage percentage
    cpu_time_seconds: float = 0.0  # Total CPU time used
    
    # Memory usage
    memory_mb: float = 0.0  # Current memory usage in MB
    memory_percent: float = 0.0  # Memory usage percentage
    
    # Disk I/O
    disk_read_mb: float = 0.0  # Total disk read in MB
    disk_write_mb: float = 0.0  # Total disk write in MB
    
    # Network I/O
    network_rx_mb: float = 0.0  # Total network received in MB
    network_tx_mb: float = 0.0  # Total network transmitted in MB
    
    # Execution time
    execution_time_seconds: float = 0.0  # Current execution time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.
        
        Returns:
            Dictionary with resource usage data
        """
        return {
            "cpu": {
                "percent": round(self.cpu_percent, 2),
                "time_seconds": round(self.cpu_time_seconds, 2),
            },
            "memory": {
                "mb": round(self.memory_mb, 2),
                "percent": round(self.memory_percent, 2),
            },
            "disk": {
                "read_mb": round(self.disk_read_mb, 2),
                "write_mb": round(self.disk_write_mb, 2),
            },
            "network": {
                "rx_mb": round(self.network_rx_mb, 2),
                "tx_mb": round(self.network_tx_mb, 2),
            },
            "execution_time_seconds": round(self.execution_time_seconds, 2),
        }
    
    def is_within_limits(self, limits: ResourceLimits) -> bool:
        """Check if current usage is within specified limits.
        
        Args:
            limits: Resource limits to check against
        
        Returns:
            True if within limits, False otherwise
        """
        if self.memory_mb > limits.memory_mb:
            logger.warning(
                "Memory limit exceeded",
                extra={
                    "current_mb": self.memory_mb,
                    "limit_mb": limits.memory_mb,
                },
            )
            return False
        
        if self.execution_time_seconds > limits.execution_timeout_seconds:
            logger.warning(
                "Execution timeout exceeded",
                extra={
                    "current_seconds": self.execution_time_seconds,
                    "limit_seconds": limits.execution_timeout_seconds,
                },
            )
            return False
        
        return True


def get_default_limits(task_type: str = "default") -> ResourceLimits:
    """Get default resource limits for a task type.
    
    Args:
        task_type: Type of task (default, data_processing, code_execution, etc.)
    
    Returns:
        ResourceLimits instance with appropriate defaults
    """
    limits_by_type = {
        "default": ResourceLimits(
            cpu_cores=0.5,
            memory_mb=512,
            execution_timeout_seconds=30,
        ),
        "data_processing": ResourceLimits(
            cpu_cores=1.0,
            memory_mb=1024,
            execution_timeout_seconds=120,
        ),
        "code_execution": ResourceLimits(
            cpu_cores=0.5,
            memory_mb=512,
            execution_timeout_seconds=30,
        ),
        "ml_inference": ResourceLimits(
            cpu_cores=2.0,
            memory_mb=2048,
            execution_timeout_seconds=60,
        ),
        "lightweight": ResourceLimits(
            cpu_cores=0.25,
            memory_mb=256,
            execution_timeout_seconds=15,
        ),
    }
    
    return limits_by_type.get(task_type, limits_by_type["default"])


def parse_resource_usage_from_docker_stats(stats: Dict[str, Any]) -> ResourceUsage:
    """Parse resource usage from Docker stats API response.
    
    Args:
        stats: Docker stats dictionary
    
    Returns:
        ResourceUsage instance
    """
    cpu_stats = stats.get("cpu_stats", {})
    memory_stats = stats.get("memory_stats", {})
    blkio_stats = stats.get("blkio_stats", {})
    networks = stats.get("networks", {})
    
    # Calculate CPU percentage
    cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - \
                stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
    system_delta = cpu_stats.get("system_cpu_usage", 0) - \
                   stats.get("precpu_stats", {}).get("system_cpu_usage", 0)
    cpu_percent = 0.0
    if system_delta > 0:
        cpu_percent = (cpu_delta / system_delta) * 100.0
    
    # Memory usage
    memory_usage = memory_stats.get("usage", 0)
    memory_limit = memory_stats.get("limit", 1)
    memory_percent = (memory_usage / memory_limit) * 100.0 if memory_limit > 0 else 0.0
    
    # Disk I/O
    disk_read = 0
    disk_write = 0
    for io_stat in blkio_stats.get("io_service_bytes_recursive", []):
        if io_stat.get("op") == "Read":
            disk_read += io_stat.get("value", 0)
        elif io_stat.get("op") == "Write":
            disk_write += io_stat.get("value", 0)
    
    # Network I/O
    network_rx = sum(net.get("rx_bytes", 0) for net in networks.values())
    network_tx = sum(net.get("tx_bytes", 0) for net in networks.values())
    
    return ResourceUsage(
        cpu_percent=cpu_percent,
        cpu_time_seconds=cpu_stats.get("cpu_usage", {}).get("total_usage", 0) / 1e9,
        memory_mb=memory_usage / (1024 * 1024),
        memory_percent=memory_percent,
        disk_read_mb=disk_read / (1024 * 1024),
        disk_write_mb=disk_write / (1024 * 1024),
        network_rx_mb=network_rx / (1024 * 1024),
        network_tx_mb=network_tx / (1024 * 1024),
    )
