"""Sandbox Selector for automatic platform detection and sandbox selection.

This module implements automatic detection of the best available sandbox technology
based on platform capabilities and availability.

References:
- Requirements 6: Agent Virtualization and Isolation
- Design Section 5.3: Automatic Sandbox Selection
"""

import logging
import os
import platform
import subprocess
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SandboxType(Enum):
    """Available sandbox technologies."""

    GVISOR = "gvisor"
    FIRECRACKER = "firecracker"
    DOCKER_ENHANCED = "docker_enhanced"


class PlatformType(Enum):
    """Supported platform types."""

    LINUX = "Linux"
    MACOS = "Darwin"
    WINDOWS = "Windows"
    UNKNOWN = "Unknown"


class SandboxSelector:
    """Automatically select best available sandbox technology.

    Priority:
    1. gVisor (if Linux + Kubernetes + gVisor available)
    2. Firecracker (if Linux + KVM available)
    3. Docker Enhanced (fallback for all platforms)
    """

    def __init__(self):
        """Initialize the sandbox selector."""
        self.logger = logging.getLogger(__name__)
        self._detected_sandbox: Optional[SandboxType] = None
        self._platform = self._detect_platform()
        self._platform_details = self._get_detailed_platform_info()

    def detect_best_sandbox(self) -> SandboxType:
        """Detect and return the best available sandbox technology.

        Returns:
            SandboxType enum value for the best available sandbox
        """
        if self._detected_sandbox:
            return self._detected_sandbox

        self.logger.info(
            "Detecting best sandbox technology",
            extra={
                "platform": self._platform,
                "platform_details": self._platform_details,
            },
        )

        # Check gVisor (Linux only)
        if self._platform == PlatformType.LINUX.value:
            if self._is_gvisor_available():
                self.logger.info(
                    "Using gVisor sandbox (highest security)",
                    extra={"security_level": "high", "overhead": "10-15%"},
                )
                self._detected_sandbox = SandboxType.GVISOR
                return self._detected_sandbox

            # Check Firecracker (Linux with KVM)
            if self._is_firecracker_available():
                self.logger.info(
                    "Using Firecracker sandbox (high security)",
                    extra={"security_level": "very_high", "overhead": "20-30%"},
                )
                self._detected_sandbox = SandboxType.FIRECRACKER
                return self._detected_sandbox

        # Fallback to Docker Enhanced (all platforms)
        security_warning = self._get_security_warning()
        self.logger.warning(
            f"Using Docker Enhanced sandbox on {self._platform}",
            extra={
                "reason": "gVisor/Firecracker not available",
                "security_level": "medium",
                "overhead": "5%",
                "warning": security_warning,
            },
        )
        self._detected_sandbox = SandboxType.DOCKER_ENHANCED
        return self._detected_sandbox

    def _detect_platform(self) -> str:
        """Detect the current platform.

        Returns:
            Platform name (Linux, Darwin, Windows, or Unknown)
        """
        system = platform.system()

        # Normalize platform names
        if system in ["Linux", "Darwin", "Windows"]:
            return system

        self.logger.warning(
            f"Unknown platform detected: {system}",
            extra={"detected_system": system},
        )
        return "Unknown"

    def _get_detailed_platform_info(self) -> Dict[str, Any]:
        """Get detailed platform information.

        Returns:
            Dictionary with detailed platform information
        """
        info = {
            "system": self._platform,
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": platform.python_version(),
        }

        # Add Linux-specific information
        if self._platform == PlatformType.LINUX.value:
            try:
                # Check for distribution info
                if os.path.exists("/etc/os-release"):
                    with open("/etc/os-release", "r") as f:
                        os_release = {}
                        for line in f:
                            if "=" in line:
                                key, value = line.strip().split("=", 1)
                                os_release[key] = value.strip('"')
                        info["distribution"] = os_release.get("NAME", "Unknown")
                        info["distribution_version"] = os_release.get("VERSION", "Unknown")

                # Check for KVM support
                info["kvm_available"] = os.path.exists("/dev/kvm")

                # Check for cgroup v2
                info["cgroup_v2"] = os.path.exists("/sys/fs/cgroup/cgroup.controllers")

            except Exception as e:
                self.logger.debug(f"Failed to get Linux-specific info: {e}")

        # Add macOS-specific information
        elif self._platform == PlatformType.MACOS.value:
            try:
                # Get macOS version
                mac_ver = platform.mac_ver()
                info["macos_version"] = mac_ver[0]
                info["macos_arch"] = mac_ver[2]
            except Exception as e:
                self.logger.debug(f"Failed to get macOS-specific info: {e}")

        # Add Windows-specific information
        elif self._platform == PlatformType.WINDOWS.value:
            try:
                # Get Windows version
                win_ver = platform.win32_ver()
                info["windows_version"] = win_ver[0]
                info["windows_build"] = win_ver[1]
            except Exception as e:
                self.logger.debug(f"Failed to get Windows-specific info: {e}")

        return info

    def _get_security_warning(self) -> str:
        """Get security warning message for fallback mode.

        Returns:
            Security warning message
        """
        if self._platform == PlatformType.LINUX.value:
            return (
                "Running in Docker Enhanced mode on Linux. "
                "For enhanced security, consider installing gVisor (runsc) or Firecracker. "
                "See documentation for installation instructions."
            )
        elif self._platform == PlatformType.MACOS.value:
            return (
                "Running in Docker Enhanced mode on macOS. "
                "gVisor and Firecracker are not available on macOS. "
                "This provides container-level isolation with resource limits."
            )
        elif self._platform == PlatformType.WINDOWS.value:
            return (
                "Running in Docker Enhanced mode on Windows. "
                "gVisor and Firecracker are not available on Windows. "
                "This provides container-level isolation with resource limits."
            )
        else:
            return (
                "Running in Docker Enhanced mode on unknown platform. "
                "Advanced sandbox technologies are not available."
            )

    def _is_gvisor_available(self) -> bool:
        """Check if gVisor is available on the system.

        Returns:
            True if gVisor is available, False otherwise
        """
        try:
            # Check if runsc binary exists
            result = subprocess.run(
                ["which", "runsc"],
                capture_output=True,
                timeout=1,
                text=True,
            )
            if result.returncode != 0:
                self.logger.debug("gVisor not available: runsc binary not found")
                return False

            # Check if Docker supports gVisor runtime
            result = subprocess.run(
                ["docker", "info", "--format", "{{.Runtimes}}"],
                capture_output=True,
                timeout=2,
                text=True,
            )

            if result.returncode == 0 and "runsc" in result.stdout:
                self.logger.debug("gVisor is available")
                return True

            self.logger.debug("gVisor not available: Docker runtime not configured")
            return False

        except subprocess.TimeoutExpired:
            self.logger.debug("gVisor check timed out")
            return False
        except FileNotFoundError:
            self.logger.debug("gVisor check failed: command not found")
            return False
        except Exception as e:
            self.logger.debug(f"gVisor check failed: {e}")
            return False

    def _is_firecracker_available(self) -> bool:
        """Check if Firecracker is available on the system.

        Returns:
            True if Firecracker is available, False otherwise
        """
        try:
            # Check if KVM is available
            if not os.path.exists("/dev/kvm"):
                self.logger.debug("Firecracker not available: /dev/kvm not found")
                return False

            # Check if firecracker binary exists
            result = subprocess.run(
                ["which", "firecracker"],
                capture_output=True,
                timeout=1,
                text=True,
            )

            if result.returncode == 0:
                self.logger.debug("Firecracker is available")
                return True

            self.logger.debug("Firecracker not available: binary not found")
            return False

        except subprocess.TimeoutExpired:
            self.logger.debug("Firecracker check timed out")
            return False
        except FileNotFoundError:
            self.logger.debug("Firecracker check failed: command not found")
            return False
        except Exception as e:
            self.logger.debug(f"Firecracker check failed: {e}")
            return False

    def get_sandbox_config(self, sandbox_type: Optional[SandboxType] = None) -> Dict[str, Any]:
        """Get configuration for specified sandbox type.

        Args:
            sandbox_type: Sandbox type to get config for. If None, uses detected sandbox.

        Returns:
            Dictionary with sandbox configuration
        """
        if sandbox_type is None:
            sandbox_type = self.detect_best_sandbox()

        configs = {
            SandboxType.GVISOR: {
                "runtime": "runsc",
                "security_level": "high",
                "overhead": "10-15%",
                "startup_time_ms": 150,
                "platform": "linux",
                "features": [
                    "system_call_filtering",
                    "network_namespace_isolation",
                    "filesystem_isolation",
                    "resource_limits",
                ],
            },
            SandboxType.FIRECRACKER: {
                "runtime": "firecracker",
                "security_level": "very_high",
                "overhead": "20-30%",
                "startup_time_ms": 125,
                "platform": "linux",
                "features": [
                    "hardware_isolation",
                    "minimal_guest_kernel",
                    "strong_memory_isolation",
                    "secure_boot",
                ],
            },
            SandboxType.DOCKER_ENHANCED: {
                "runtime": "docker",
                "security_level": "medium",
                "overhead": "5%",
                "startup_time_ms": 50,
                "platform": "all",
                "features": [
                    "container_isolation",
                    "resource_limits",
                    "network_isolation",
                    "capability_dropping",
                ],
            },
        }

        return configs[sandbox_type]

    def get_platform_info(self) -> Dict[str, Any]:
        """Get current platform information.

        Returns:
            Dictionary with platform details
        """
        return {
            "system": self._platform,
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
        }

    def validate_sandbox_requirements(self, sandbox_type: SandboxType) -> bool:
        """Validate if system meets requirements for specified sandbox type.

        Args:
            sandbox_type: Sandbox type to validate

        Returns:
            True if requirements are met, False otherwise
        """
        if sandbox_type == SandboxType.GVISOR:
            return self._platform == PlatformType.LINUX.value and self._is_gvisor_available()
        elif sandbox_type == SandboxType.FIRECRACKER:
            return self._platform == PlatformType.LINUX.value and self._is_firecracker_available()
        elif sandbox_type == SandboxType.DOCKER_ENHANCED:
            # Docker Enhanced works on all platforms
            return True

        return False

    def log_platform_detection(self) -> None:
        """Log detailed platform detection information."""
        self.logger.info(
            "Platform detection complete",
            extra={
                "platform": self._platform,
                "details": self._platform_details,
                "selected_sandbox": (
                    self._detected_sandbox.value if self._detected_sandbox else "not_detected"
                ),
            },
        )

        # Log security recommendations
        if (
            self._platform == PlatformType.LINUX.value
            and self._detected_sandbox == SandboxType.DOCKER_ENHANCED
        ):
            self.logger.warning(
                "Security recommendation: Install gVisor for enhanced isolation",
                extra={
                    "current_security": "medium",
                    "recommended_security": "high",
                    "installation_guide": "https://gvisor.dev/docs/user_guide/install/",
                },
            )


# Global sandbox selector instance
_sandbox_selector: Optional[SandboxSelector] = None


def get_sandbox_selector() -> SandboxSelector:
    """Get the global sandbox selector instance.

    Returns:
        SandboxSelector instance
    """
    global _sandbox_selector
    if _sandbox_selector is None:
        _sandbox_selector = SandboxSelector()
    return _sandbox_selector
