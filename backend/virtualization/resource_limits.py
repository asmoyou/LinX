"""Resource limits and usage tracking for agent containers.

This module defines resource limits and tracks resource usage for containerized agents.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.5: Runtime Security Policies
"""

import logging
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MIN_MEMORY_MB = 128
MAX_MEMORY_MB = 262144
DEFAULT_HOST_MEMORY_MB = 4096
DEFAULT_DYNAMIC_MAX_MEMORY_MB = 65536
SANDBOX_IO_DEVICE_PATH = os.getenv("LINX_SANDBOX_IO_DEVICE_PATH", "").strip()


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
        config = {
            "cpu_period": 100000,  # 100ms
            "cpu_quota": int(self.cpu_cores * 100000),
            "cpu_shares": self.cpu_shares,
            "mem_limit": f"{self.memory_mb}m",
            "memswap_limit": f"{self.memory_swap_mb}m",
        }
        
        # blkio controls are highly runtime-dependent and break on Docker Desktop/
        # LinuxKit where io.weight and specific device paths may not exist.
        # Only enable them when the operator explicitly provides a device path.
        import platform

        if platform.system() == "Linux":
            if SANDBOX_IO_DEVICE_PATH:
                config["blkio_weight"] = 500
                config["device_read_bps"] = [
                    {"Path": SANDBOX_IO_DEVICE_PATH, "Rate": self.disk_read_bps}
                ]
                config["device_write_bps"] = [
                    {"Path": SANDBOX_IO_DEVICE_PATH, "Rate": self.disk_write_bps}
                ]
        
        return config

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

        if self.memory_mb < MIN_MEMORY_MB or self.memory_mb > MAX_MEMORY_MB:
            logger.error(f"Invalid memory limit: {self.memory_mb}MB")
            return False

        if self.execution_timeout_seconds <= 0:
            logger.error(f"Invalid timeout: {self.execution_timeout_seconds}s")
            return False

        return True


def _parse_positive_int_env(key: str) -> Optional[int]:
    """Parse a positive integer from env or return None."""
    raw_value = os.getenv(key)
    if raw_value is None:
        return None

    try:
        parsed = int(str(raw_value).strip())
    except ValueError:
        logger.warning("Invalid integer value for %s: %s", key, raw_value)
        return None

    if parsed <= 0:
        logger.warning("Non-positive integer value for %s: %s", key, raw_value)
        return None

    return parsed


def _read_linux_meminfo_mb() -> Optional[int]:
    """Read total system memory from /proc/meminfo (Linux)."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as meminfo:
            for line in meminfo:
                if line.startswith("MemTotal:"):
                    # Example: MemTotal:       16328856 kB
                    fields = line.split()
                    if len(fields) >= 2:
                        kb = int(fields[1])
                        if kb > 0:
                            return max(1, kb // 1024)
    except Exception:
        return None
    return None


def _read_cgroup_memory_limit_mb() -> Optional[int]:
    """Read cgroup memory limit so defaults respect container ceilings."""
    cgroup_paths = (
        "/sys/fs/cgroup/memory.max",  # cgroup v2
        "/sys/fs/cgroup/memory/memory.limit_in_bytes",  # cgroup v1
    )

    for path in cgroup_paths:
        try:
            if not os.path.exists(path):
                continue
            raw_value = Path(path).read_text(encoding="utf-8").strip()
            if not raw_value or raw_value == "max":
                continue
            value = int(raw_value)
            # Some runtimes use very large sentinel values to represent "unlimited".
            if value <= 0 or value >= (1 << 60):
                continue
            return max(1, value // (1024 * 1024))
        except Exception:
            continue
    return None


@lru_cache(maxsize=1)
def _detect_available_memory_mb() -> int:
    """Detect available memory budget from host/container context."""
    env_override = _parse_positive_int_env("LINX_SANDBOX_HOST_MEMORY_MB")
    if env_override:
        return env_override

    detected_total_mb: Optional[int] = _read_linux_meminfo_mb()

    if detected_total_mb is None:
        try:
            page_size = int(os.sysconf("SC_PAGE_SIZE"))
            phys_pages = int(os.sysconf("SC_PHYS_PAGES"))
            if page_size > 0 and phys_pages > 0:
                detected_total_mb = (page_size * phys_pages) // (1024 * 1024)
        except (ValueError, OSError, AttributeError):
            detected_total_mb = None

    if detected_total_mb is None or detected_total_mb <= 0:
        detected_total_mb = DEFAULT_HOST_MEMORY_MB

    cgroup_limit_mb = _read_cgroup_memory_limit_mb()
    if cgroup_limit_mb and cgroup_limit_mb > 0:
        detected_total_mb = min(detected_total_mb, cgroup_limit_mb)

    return max(1, detected_total_mb)


def _resolve_dynamic_memory_limit_mb(task_type: str, floor_mb: int) -> int:
    """Resolve default memory cap from host capacity, task profile and env overrides."""
    memory_override_mb = _parse_positive_int_env("LINX_SANDBOX_MEMORY_MB")
    dynamic_max_mb = _parse_positive_int_env("LINX_SANDBOX_MAX_MEMORY_MB")
    if dynamic_max_mb is None:
        dynamic_max_mb = DEFAULT_DYNAMIC_MAX_MEMORY_MB
    dynamic_max_mb = max(MIN_MEMORY_MB, min(dynamic_max_mb, MAX_MEMORY_MB))

    if memory_override_mb is not None:
        return max(MIN_MEMORY_MB, min(memory_override_mb, dynamic_max_mb))

    total_mb = _detect_available_memory_mb()
    ratio_by_task = {
        "default": 0.25,
        "data_processing": 0.35,
        "code_execution": 0.30,
        "ml_inference": 0.50,
        "lightweight": 0.15,
    }
    ratio = ratio_by_task.get(task_type, ratio_by_task["default"])
    dynamic_mb = int(total_mb * ratio)
    resolved_mb = max(floor_mb, dynamic_mb)
    resolved_mb = max(MIN_MEMORY_MB, min(resolved_mb, dynamic_max_mb))
    # Align to 64MB to avoid noisy values from host probes.
    return ((resolved_mb + 63) // 64) * 64


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
    task_profiles = {
        "default": {"cpu_cores": 0.5, "memory_floor_mb": 512, "timeout_seconds": 30},
        "data_processing": {
            "cpu_cores": 1.0,
            "memory_floor_mb": 1024,
            "timeout_seconds": 120,
        },
        "code_execution": {
            "cpu_cores": 0.5,
            "memory_floor_mb": 1024,
            "timeout_seconds": 30,
        },
        "ml_inference": {"cpu_cores": 2.0, "memory_floor_mb": 2048, "timeout_seconds": 60},
        "lightweight": {"cpu_cores": 0.25, "memory_floor_mb": 256, "timeout_seconds": 15},
    }

    profile = task_profiles.get(task_type, task_profiles["default"])
    memory_mb = _resolve_dynamic_memory_limit_mb(task_type, profile["memory_floor_mb"])
    return ResourceLimits(
        cpu_cores=profile["cpu_cores"],
        memory_mb=memory_mb,
        memory_swap_mb=memory_mb,
        execution_timeout_seconds=profile["timeout_seconds"],
    )


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
    cpu_delta = cpu_stats.get("cpu_usage", {}).get("total_usage", 0) - stats.get(
        "precpu_stats", {}
    ).get("cpu_usage", {}).get("total_usage", 0)
    system_delta = cpu_stats.get("system_cpu_usage", 0) - stats.get("precpu_stats", {}).get(
        "system_cpu_usage", 0
    )
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
